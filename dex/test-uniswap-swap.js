/* Swap 1000 ABA -> USDC through the deployed Uniswap-v2 Router02. */
const fs = require("fs"), path = require("path");
const { ethers } = require("ethers");

(async () => {
  const d = JSON.parse(fs.readFileSync(path.join(__dirname, "deployed-uniswap.json"), "utf8"));
  const key = fs.readFileSync(path.join(__dirname, ".deployer.key"), "utf8").trim();
  const p = new ethers.JsonRpcProvider(d.rpc, d.chainId);
  const w = new ethers.Wallet(key, p);
  const router = new ethers.Contract(d.router, d.routerAbi, w);
  const usdc = new ethers.Contract(d.usdc, ["function balanceOf(address) view returns (uint256)"], p);

  const route = [d.waba, d.usdc];
  const amountIn = ethers.parseEther("1000");
  const outs = await router.getAmountsOut(amountIn, route);
  console.log("quote: 1000 ABA ->", Number(outs[1]) / 1e6, "USDC");

  const before = await usdc.balanceOf(w.address);
  const dl = Math.floor(Date.now() / 1000) + 600;
  const tx = await router.swapExactETHForTokens((outs[1] * 99n) / 100n, route, w.address, dl, { value: amountIn });
  console.log("swap tx:", tx.hash);
  await tx.wait();
  const after = await usdc.balanceOf(w.address);
  console.log("USDC received:", Number(after - before) / 1e6);
  console.log("UNISWAP_SWAP_DONE");
})().catch((e) => { console.error(e.shortMessage || e.message || e); process.exit(1); });
