/* End-to-end swap test: swap 1000 ABA -> USDC on the deployed AbakosDEX and
 * verify the USDC received + reserve shift. Uses the deployer key. */
const fs = require("fs");
const { ethers } = require("ethers");

(async () => {
  const d = JSON.parse(fs.readFileSync(require("path").join(__dirname, "deployed.json"), "utf8"));
  const key = fs.readFileSync(require("path").join(__dirname, ".deployer.key"), "utf8").trim();
  const p = new ethers.JsonRpcProvider(d.rpc, d.chainId);
  const w = new ethers.Wallet(key, p);
  const dex = new ethers.Contract(d.dex, d.dexAbi, w);
  const usdc = new ethers.Contract(d.usdc, d.usdcAbi, w);

  const inWei = ethers.parseEther("1000");
  const quote = await dex.getAmountOutABAtoUSDC(inWei);
  console.log("quote: 1000 ABA ->", Number(quote) / 1e6, "USDC");

  const before = await usdc.balanceOf(w.address);
  const tx = await dex.swapABAForUSDC((quote * 99n) / 100n, { value: inWei });
  console.log("swap tx:", tx.hash);
  await tx.wait();
  const after = await usdc.balanceOf(w.address);
  console.log("USDC received:", Number(after - before) / 1e6);
  console.log("reserves now:", ethers.formatEther(await dex.reserveABA()), "ABA /", Number(await dex.reserveUSDC()) / 1e6, "USDC");
  console.log("SWAP_TEST_DONE");
})().catch((e) => { console.error(e.shortMessage || e.message || e); process.exit(1); });
