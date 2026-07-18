/* Fund the Provider-Agent buyback wallet on the Abakos EVM (chain 9721).
 *
 *   node fund-buyback.js <buyback0x> [usdcAmount] [abaAmount]
 *
 * Mints test USDC to the buyback wallet (deployer is TestUSDC owner) and tops up
 * a little native ABA for gas. Defaults: 10000 USDC + 50 ABA. Idempotent-ish:
 * safe to re-run to top up. Uses .deployer.key + deployed-uniswap.json. */
const fs = require("fs");
const path = require("path");
const { ethers } = require("ethers");

const RPC = "https://evm-rpc.abakos.ai", CHAIN = 9721;
const U = JSON.parse(fs.readFileSync(path.join(__dirname, "deployed-uniswap.json"), "utf8"));
const KEYFILE = path.join(__dirname, ".deployer.key");

async function main() {
  const target = (process.argv[2] || "").trim();
  if (!/^0x[0-9a-fA-F]{40}$/.test(target)) {
    console.error("usage: node fund-buyback.js <buyback0x> [usdcAmount] [abaAmount]");
    process.exit(1);
  }
  const usdcAmount = BigInt(Math.round(Number(process.argv[3] || "10000") * 1e6)); // 6-dec
  const abaAmount = ethers.parseEther(String(process.argv[4] || "50"));

  const provider = new ethers.JsonRpcProvider(RPC, CHAIN);
  const w = new ethers.Wallet(fs.readFileSync(KEYFILE, "utf8").trim(), provider);
  console.log("deployer:", w.address, "|", ethers.formatEther(await provider.getBalance(w.address)), "ABA");
  console.log("target  :", target);

  const usdc = new ethers.Contract(U.usdc, [
    "function mint(address,uint256)",
    "function balanceOf(address) view returns (uint256)",
  ], w);
  console.log("minting", Number(usdcAmount) / 1e6, "USDC ...");
  await (await usdc.mint(target, usdcAmount)).wait();

  console.log("sending", ethers.formatEther(abaAmount), "ABA for gas ...");
  await (await w.sendTransaction({ to: target, value: abaAmount })).wait();

  const [ub, ab] = [await usdc.balanceOf(target), await provider.getBalance(target)];
  console.log("buyback now holds:", Number(ub) / 1e6, "USDC /", ethers.formatEther(ab), "ABA");
  console.log("FUND_BUYBACK_DONE");
}

main().catch((e) => { console.error(e.shortMessage || e.message || e); process.exit(1); });
