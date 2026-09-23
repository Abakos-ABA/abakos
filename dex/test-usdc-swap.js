/* Proof swap on the real-USDC pool: 0.03 USDC -> native ABA (buyback direction). */
const { ethers } = require("ethers");
const fs = require("fs");
const D = JSON.parse(fs.readFileSync("deployed-uniswap.json", "utf8"));
const KEY = fs.readFileSync(".deployer.key", "utf8").trim();

(async () => {
  const p = new ethers.JsonRpcProvider(D.rpc, { chainId: D.chainId, name: "abakos" });
  const w = new ethers.Wallet(KEY, p);
  const r = new ethers.Contract(D.router, D.routerAbi, w);
  const USDC = D.usdcIbc.erc20;
  const dl = Math.floor(Date.now() / 1000) + 600;

  const before = await p.getBalance(w.address);
  const tx = await r.swapExactTokensForETH(30000n, 0n, [USDC, D.waba], w.address, dl, { gasLimit: 300000 });
  const rc = await tx.wait();
  const after = await p.getBalance(w.address);
  console.log("status:", rc.status, "| tx:", rc.hash);
  console.log("ABA received:", ethers.formatEther(after - before));

  const usdc = new ethers.Contract(USDC, ["function balanceOf(address) view returns (uint256)"], p);
  console.log("pair reserves now:", (await usdc.balanceOf(D.usdcIbc.pair)).toString(), "uusdc /",
    ethers.formatEther(await new ethers.Contract(D.waba, ["function balanceOf(address) view returns (uint256)"], p).balanceOf(D.usdcIbc.pair)), "WABA");
})().catch((e) => { console.error("revert:", e.shortMessage || e.message); process.exit(1); });
