/* Deploy a full Uniswap-v2 fork to the Abakos EVM (chain 9721):
 *   - UniswapV2Factory + UniswapV2Pair (v2-core, solc 0.5.16)
 *   - WABA (wrapped ABA / WETH9) + UniswapV2Router02 (v2-periphery, solc 0.6.6)
 * Computes the Pair init-code-hash from our compiled bytecode and patches it into
 * UniswapV2Library before compiling the periphery, so Router.pairFor() resolves
 * correctly. Reuses the existing TestUSDT + funded deployer key, then seeds a
 * WABA/USDT pool via addLiquidityETH. Writes deployed-uniswap.json for the UI.
 */
const fs = require("fs");
const path = require("path");
const solc = require("solc");
const { ethers } = require("ethers");

const RPC = "https://evm-rpc.abakos.ai", CHAIN = 9721;
const NM = path.join(__dirname, "node_modules");
const KEYFILE = path.join(__dirname, ".deployer.key");
const MINI = JSON.parse(fs.readFileSync(path.join(__dirname, "deployed.json"), "utf8"));
const USDT = MINI.usdc; // legacy deployed.json still uses the "usdc" key; same test-USDT token
const CORE_V = "v0.5.16+commit.9c3226ce";
const PERI_V = "v0.6.6+commit.6c089d02";
const ABA_SEED = ethers.parseEther("500000");
const USDT_SEED = 125000n * 10n ** 6n;

const read = (p) => fs.readFileSync(p, "utf8");
function findImport(p) {
  const full = path.join(NM, p);
  if (fs.existsSync(full)) return { contents: read(full) };
  return { error: "not found: " + p };
}
const loadSolc = (v) => new Promise((res, rej) => solc.loadRemoteVersion(v, (e, s) => (e ? rej(e) : res(s))));

async function compile(version, sources) {
  const sc = await loadSolc(version);
  const input = {
    language: "Solidity",
    sources,
    settings: { optimizer: { enabled: true, runs: 999999 }, outputSelection: { "*": { "*": ["abi", "evm.bytecode.object"] } } },
  };
  const out = JSON.parse(sc.compile(JSON.stringify(input), { import: findImport }));
  let hard = false;
  for (const e of out.errors || []) if (e.severity === "error") { console.error(e.formattedMessage); hard = true; }
  if (hard) throw new Error("compile errors (" + version + ")");
  return out.contracts;
}

function findContract(contracts, name) {
  for (const f in contracts) if (contracts[f][name]) return contracts[f][name];
  return null;
}

async function main() {
  console.log("compiling v2-core (0.5.16) ...");
  const core = await compile(CORE_V, {
    "@uniswap/v2-core/contracts/UniswapV2Factory.sol": { content: read(path.join(NM, "@uniswap/v2-core/contracts/UniswapV2Factory.sol")) },
  });
  const factoryC = findContract(core, "UniswapV2Factory");
  const pairC = findContract(core, "UniswapV2Pair");
  if (!factoryC || !pairC) throw new Error("core: missing Factory/Pair");
  const initHash = ethers.keccak256("0x" + pairC.evm.bytecode.object).slice(2);
  console.log("pair init code hash:", initHash);

  const libPath = path.join(NM, "@uniswap/v2-periphery/contracts/libraries/UniswapV2Library.sol");
  let lib = read(libPath);
  if (lib.includes("hex'" + initHash + "'")) {
    console.log("UniswapV2Library init hash already correct");
  } else {
    const patched = lib.replace(/hex'[0-9a-fA-F]{64}'/, "hex'" + initHash + "'");
    if (patched === lib) throw new Error("could not patch init hash in UniswapV2Library");
    fs.writeFileSync(libPath, patched);
    console.log("patched UniswapV2Library init hash");
  }

  console.log("compiling v2-periphery + WABA (0.6.6) ...");
  const peri = await compile(PERI_V, {
    "@uniswap/v2-periphery/contracts/UniswapV2Router02.sol": { content: read(path.join(NM, "@uniswap/v2-periphery/contracts/UniswapV2Router02.sol")) },
    "WABA.sol": { content: read(path.join(__dirname, "contracts/WABA.sol")) },
  });
  const routerC = findContract(peri, "UniswapV2Router02");
  const wabaC = findContract(peri, "WABA");
  if (!routerC || !wabaC) throw new Error("periphery: missing Router/WABA");

  const key = read(KEYFILE).trim();
  const provider = new ethers.JsonRpcProvider(RPC, CHAIN);
  const w = new ethers.Wallet(key, provider);
  console.log("deployer:", w.address, "|", ethers.formatEther(await provider.getBalance(w.address)), "ABA");

  const factory = await new ethers.ContractFactory(factoryC.abi, factoryC.evm.bytecode.object, w).deploy(w.address);
  await factory.waitForDeployment(); const factoryAddr = await factory.getAddress(); console.log("Factory :", factoryAddr);

  const waba = await new ethers.ContractFactory(wabaC.abi, wabaC.evm.bytecode.object, w).deploy();
  await waba.waitForDeployment(); const wabaAddr = await waba.getAddress(); console.log("WABA    :", wabaAddr);

  const router = await new ethers.ContractFactory(routerC.abi, routerC.evm.bytecode.object, w).deploy(factoryAddr, wabaAddr);
  await router.waitForDeployment(); const routerAddr = await router.getAddress(); console.log("Router02:", routerAddr);

  console.log("seeding WABA/USDT:", ethers.formatEther(ABA_SEED), "ABA +", Number(USDT_SEED) / 1e6, "USDT ...");
  const usdc = new ethers.Contract(USDT, ["function mint(address,uint256)", "function approve(address,uint256) returns (bool)"], w);
  await (await usdc.mint(w.address, USDT_SEED)).wait();
  await (await usdc.approve(routerAddr, USDT_SEED)).wait();
  const routerW = new ethers.Contract(routerAddr, routerC.abi, w);
  const deadline = Math.floor(Date.now() / 1000) + 1200;
  await (await routerW.addLiquidityETH(USDT, USDT_SEED, 0, 0, w.address, deadline, { value: ABA_SEED })).wait();

  const fac = new ethers.Contract(factoryAddr, ["function getPair(address,address) view returns (address)"], provider);
  const pair = await fac.getPair(wabaAddr, USDT);
  console.log("Pair (WABA/USDT):", pair);

  fs.writeFileSync(path.join(__dirname, "deployed-uniswap.json"), JSON.stringify({
    chainId: CHAIN, rpc: RPC, factory: factoryAddr, router: routerAddr, waba: wabaAddr, usdt: USDT, pair, initHash,
    routerAbi: routerC.abi,
  }, null, 2));
  console.log("UNISWAP_DEPLOY_DONE");
}

main().catch((e) => { console.error(e.shortMessage || e.message || e); process.exit(1); });
