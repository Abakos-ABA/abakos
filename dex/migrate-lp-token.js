/* Redeploy the Abakos DEX with a properly named LP token, then migrate the
 * deployer's liquidity from the old pool.
 *
 * The stock Uniswap pair hardcodes name/symbol/decimals ('Uniswap V2', 'UNI-V2',
 * 18) in UniswapV2ERC20.sol — MetaMask validates wallet_watchAsset against the
 * contract, so the only way to show a sensible LP token is to bake it in:
 *
 *   name 'Abakos LP' · symbol 'ABA-LP' · decimals 12
 *
 * decimals is pure metadata (never read by core/periphery); 12 makes wallets
 * display the same clean numbers as the site (raw LP amounts are ~1e12 scale
 * because liquidity = sqrt(ABA_1e18 * USDC_1e6)).
 *
 * Keeps the existing WABA. Writes deployed-uniswap.json (old file backed up to
 * deployed-uniswap.v1.json). User LP in the old pool migrates via the site's
 * one-click "Migrate from old pool" flow.
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
const USDC = "0x4E46004562C46AB7EC0cC4C1ca14E9e20E2545B5";
const WABA = "0x380Dc585E9437362821F55d6237090Db9BF67c73";      // reuse
const OLD_ROUTER = "0xAA6c934d3eaD6677C54F6B6e44777bE1653Bc306";
const OLD_PAIR = "0x233cCefd6ea87a3987B13D948117Ec51957F960b";
const PROOF_USDC = 20000n;                                       // 0.02 USDC proof swap

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

function patchLpMetadata() {
  const p = path.join(NM, "@uniswap/v2-core/contracts/UniswapV2ERC20.sol");
  let s = read(p);
  const before = s;
  s = s.replace(/string public constant name = '[^']*';/, "string public constant name = 'Abakos LP';");
  s = s.replace(/string public constant symbol = '[^']*';/, "string public constant symbol = 'ABA-LP';");
  s = s.replace(/uint8 public constant decimals = \d+;/, "uint8 public constant decimals = 12;");
  if (!/Abakos LP/.test(s) || !/ABA-LP/.test(s) || !/decimals = 12/.test(s)) throw new Error("LP metadata patch failed");
  if (s !== before) { fs.writeFileSync(p, s); console.log("patched UniswapV2ERC20: Abakos LP / ABA-LP / 12"); }
  else console.log("UniswapV2ERC20 already patched");
}

async function main() {
  patchLpMetadata();

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
  if (!lib.includes("hex'" + initHash + "'")) {
    const patched = lib.replace(/hex'[0-9a-fA-F]{64}'/, "hex'" + initHash + "'");
    if (patched === lib) throw new Error("could not patch init hash");
    fs.writeFileSync(libPath, patched);
    console.log("patched UniswapV2Library init hash");
  }

  console.log("compiling v2-periphery (0.6.6) ...");
  const peri = await compile(PERI_V, {
    "@uniswap/v2-periphery/contracts/UniswapV2Router02.sol": { content: read(path.join(NM, "@uniswap/v2-periphery/contracts/UniswapV2Router02.sol")) },
  });
  const routerC = findContract(peri, "UniswapV2Router02");
  if (!routerC) throw new Error("periphery: missing Router");

  const provider = new ethers.JsonRpcProvider(RPC, CHAIN);
  const w = new ethers.Wallet(read(KEYFILE).trim(), provider);
  const erc = (a) => new ethers.Contract(a, ["function balanceOf(address) view returns (uint256)", "function approve(address,uint256) returns (bool)", "function allowance(address,address) view returns (uint256)", "function name() view returns (string)", "function symbol() view returns (string)", "function decimals() view returns (uint8)"], w);
  const usdcR = erc(USDC), oldPairR = erc(OLD_PAIR);
  console.log("deployer:", w.address);

  const factory = await new ethers.ContractFactory(factoryC.abi, factoryC.evm.bytecode.object, w).deploy(w.address);
  await factory.waitForDeployment(); const factoryAddr = await factory.getAddress(); console.log("Factory :", factoryAddr);

  const router = await new ethers.ContractFactory(routerC.abi, routerC.evm.bytecode.object, w).deploy(factoryAddr, WABA);
  await router.waitForDeployment(); const routerAddr = await router.getAddress(); console.log("Router02:", routerAddr);
  const routerW = new ethers.Contract(routerAddr, routerC.abi, w);
  const oldRouterW = new ethers.Contract(OLD_ROUTER, routerC.abi, w);

  // migrate the deployer's share out of the old pool
  const lp = await oldPairR.balanceOf(w.address);
  const dl = () => Math.floor(Date.now() / 1000) + 1200;
  console.log("old-pool LP (deployer):", lp.toString());
  const abaBefore = await provider.getBalance(w.address);
  const usdcBefore = await usdcR.balanceOf(w.address);
  if (lp > 0n) {
    if ((await oldPairR.allowance(w.address, OLD_ROUTER)) < lp) await (await oldPairR.approve(OLD_ROUTER, ethers.MaxUint256)).wait();
    await (await oldRouterW.removeLiquidityETH(USDC, lp, 0, 0, w.address, dl())).wait();
  }
  const abaGot = (await provider.getBalance(w.address)) - abaBefore;
  const usdcAll = await usdcR.balanceOf(w.address);
  const usdcAdd = usdcAll - PROOF_USDC;
  console.log("withdrawn:", ethers.formatEther(abaGot), "ABA +", ((Number(usdcAll - usdcBefore)) / 1e6).toFixed(6), "USDC");
  if (abaGot <= 0n || usdcAdd <= 0n) throw new Error("nothing to seed the new pool with");

  console.log("seeding new pool:", ethers.formatEther(abaGot), "ABA +", (Number(usdcAdd) / 1e6).toFixed(6), "USDC ...");
  await (await usdcR.approve(routerAddr, ethers.MaxUint256)).wait();
  await (await routerW.addLiquidityETH(USDC, usdcAdd, 0, 0, w.address, dl(), { value: abaGot })).wait();

  const fac = new ethers.Contract(factoryAddr, ["function getPair(address,address) view returns (address)"], provider);
  const pair = await fac.getPair(WABA, USDC);
  const pairR = erc(pair);
  console.log("Pair    :", pair);
  console.log("LP token:", await pairR.name(), "/", await pairR.symbol(), "/ decimals", await pairR.decimals());
  console.log("LP minted (deployer):", (await pairR.balanceOf(w.address)).toString());

  console.log("proof swap: 0.02 USDC -> ABA ...");
  await (await routerW.swapExactTokensForETH(PROOF_USDC, 0, [USDC, WABA], w.address, dl())).wait();
  console.log("swap OK");

  const oldJson = path.join(__dirname, "deployed-uniswap.json");
  fs.copyFileSync(oldJson, path.join(__dirname, "deployed-uniswap.v1.json"));
  const prev = JSON.parse(read(oldJson));
  fs.writeFileSync(oldJson, JSON.stringify({
    chainId: CHAIN, rpc: RPC, factory: factoryAddr, router: routerAddr, waba: WABA,
    usdcIbc: { denom: USDC_DENOM, erc20: USDC, pair }, initHash,
    legacy: { factory: prev.factory, router: OLD_ROUTER, pair: OLD_PAIR },
    lpToken: { name: "Abakos LP", symbol: "ABA-LP", decimals: 12 },
    routerAbi: routerC.abi,
  }, null, 2));
  console.log("MIGRATE_DONE router=" + routerAddr + " pair=" + pair);
}

main().catch((e) => { console.error(e.shortMessage || e.message || e); process.exit(1); });
