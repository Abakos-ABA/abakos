/* Fresh Uniswap-v2 deploy for the Abakos EVM (chain 9721), paired against REAL USDC.
 *
 * The previous sandbox reset wiped the old factory/router/WABA and the drip()
 * test-USDT (which also closes that faucet security hole for good). This deploy
 * pairs WABA directly with the Noble-backed IBC USDC (x/erc20 dynamic
 * precompile, single token representation) — no test stablecoin anymore.
 *
 *   - UniswapV2Factory + Pair (v2-core, solc 0.5.16)
 *   - WABA (WETH9) + UniswapV2Router02 (v2-periphery, solc 0.6.6, init-hash patched)
 *   - seed WABA/USDC pool from the deployer's real USDC + native ABA
 *   - proof swap USDC -> native ABA (the buyback call the provider agent uses)
 *
 * Writes deployed-uniswap.json (new usdcIbc block; legacy usdt/pair keys dropped).
 */
const fs = require("fs");
const path = require("path");
const solc = require("solc");
const { ethers } = require("ethers");

const RPC = "https://evm-rpc.abakos.ai", CHAIN = 9721;
const NM = path.join(__dirname, "node_modules");
const KEYFILE = path.join(__dirname, ".deployer.key");
const CORE_V = "v0.5.16+commit.9c3226ce";
const PERI_V = "v0.6.6+commit.6c089d02";

const USDC_DENOM = "ibc/8E27BA2D5493AF5636760E354E46004562C46AB7EC0CC4C1CA14E9E20E2545B5";
const USDC = "0x4E46004562C46AB7EC0cC4C1ca14E9e20E2545B5"; // erc20 precompile of the denom

const SEED_USDC = 150000n;                 // 0.15 USDC (6-dec)
const SEED_ABA = ethers.parseEther("0.6"); // 0.6 native ABA -> ~0.25 USDC/ABA
const TEST_SWAP_USDC = 30000n;             // 0.03 USDC proof swap

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
  const usdcR = new ethers.Contract(USDC, ["function balanceOf(address) view returns (uint256)", "function approve(address,uint256) returns (bool)"], w);
  console.log("deployer:", w.address, "|", ethers.formatEther(await provider.getBalance(w.address)), "ABA |",
    (await usdcR.balanceOf(w.address)).toString(), "uusdc");

  const factory = await new ethers.ContractFactory(factoryC.abi, factoryC.evm.bytecode.object, w).deploy(w.address);
  await factory.waitForDeployment(); const factoryAddr = await factory.getAddress(); console.log("Factory :", factoryAddr);

  const waba = await new ethers.ContractFactory(wabaC.abi, wabaC.evm.bytecode.object, w).deploy();
  await waba.waitForDeployment(); const wabaAddr = await waba.getAddress(); console.log("WABA    :", wabaAddr);

  const router = await new ethers.ContractFactory(routerC.abi, routerC.evm.bytecode.object, w).deploy(factoryAddr, wabaAddr);
  await router.waitForDeployment(); const routerAddr = await router.getAddress(); console.log("Router02:", routerAddr);

  console.log("seeding WABA/USDC:", ethers.formatEther(SEED_ABA), "ABA +", Number(SEED_USDC) / 1e6, "USDC ...");
  await (await usdcR.approve(routerAddr, ethers.MaxUint256)).wait();
  const routerW = new ethers.Contract(routerAddr, routerC.abi, w);
  const deadline = Math.floor(Date.now() / 1000) + 1200;
  await (await routerW.addLiquidityETH(USDC, SEED_USDC, 0, 0, w.address, deadline, { value: SEED_ABA })).wait();

  const fac = new ethers.Contract(factoryAddr, ["function getPair(address,address) view returns (address)"], provider);
  const pair = await fac.getPair(wabaAddr, USDC);
  const rWaba = await new ethers.Contract(wabaAddr, ["function balanceOf(address) view returns (uint256)"], provider).balanceOf(pair);
  const rUsdc = await usdcR.balanceOf(pair);
  console.log("Pair (WABA/USDC):", pair);
  console.log("reserves:", ethers.formatEther(rWaba), "WABA /", rUsdc.toString(), "uusdc",
    "| price:", (Number(rUsdc) / 1e6 / Number(ethers.formatEther(rWaba))).toFixed(4), "USDC/ABA");

  // proof swap: USDC -> native ABA (buyback direction, swapExactTokensForETH)
  const abaBefore = await provider.getBalance(w.address);
  console.log("test swap: 0.03 USDC -> ABA ...");
  await (await routerW.swapExactTokensForETH(TEST_SWAP_USDC, 0, [USDC, wabaAddr], w.address, deadline)).wait();
  const abaAfter = await provider.getBalance(w.address);
  console.log("swap OK, ABA received:", ethers.formatEther(abaAfter - abaBefore));

  fs.writeFileSync(path.join(__dirname, "deployed-uniswap.json"), JSON.stringify({
    chainId: CHAIN, rpc: RPC, factory: factoryAddr, router: routerAddr, waba: wabaAddr,
    usdcIbc: { denom: USDC_DENOM, erc20: USDC, pair }, initHash,
    routerAbi: routerC.abi,
  }, null, 2));
  console.log("UNISWAP_USDC_DEPLOY_DONE");
}

main().catch((e) => { console.error(e.shortMessage || e.message || e); process.exit(1); });
