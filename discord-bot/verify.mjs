// Test-transaction ownership proof (elegant on a zero-fee chain):
// the user sends any amount from their wallet to the bot's verify address; the bot
// scans incoming txs, matches the sender to a pending /link, then sends it back.
import { ethers } from "ethers";
import { provider } from "./chain.mjs";
import { CFG } from "./config.mjs";

let refundWallet = null;
export function refunder() {
  if (!refundWallet && CFG.verifyPrivkey) refundWallet = new ethers.Wallet(CFG.verifyPrivkey, provider);
  return refundWallet;
}

// Scan a block range for native transfers whose recipient is the verify address.
export async function scanIncoming(fromBlock, toBlock) {
  const hits = [];
  const target = CFG.verifyAddress.toLowerCase();
  for (let n = fromBlock; n <= toBlock; n++) {
    let block;
    try { block = await provider.getBlock(n, true); } catch { continue; }
    if (!block) continue;
    const txs = block.prefetchedTransactions || [];
    for (const tx of txs) {
      if (tx.to && tx.to.toLowerCase() === target && tx.value > 0n) {
        hits.push({ from: ethers.getAddress(tx.from), value: tx.value, hash: tx.hash, block: n });
      }
    }
  }
  return hits;
}

// Send the proof amount back to the owner. Abakos is zero-fee, so we force
// gasPrice:0 and refund the FULL received value (the incoming tx funds its own refund).
export async function refund(to, valueWei) {
  const w = refunder();
  if (!w) throw new Error("VERIFY_PRIVKEY not set — cannot refund.");
  const tx = await w.sendTransaction({ to, value: valueWei, gasPrice: 0n, gasLimit: 21000n });
  return tx.hash;
}
