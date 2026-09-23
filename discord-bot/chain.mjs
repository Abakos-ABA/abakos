// On-chain verification helpers for Abakos (chain 9721).
// Every check here maps to a real, publicly queryable on-chain artifact.
import { ethers } from "ethers";
import { toBech32, fromBech32, fromHex, toHex } from "@cosmjs/encoding";
import { CFG } from "./config.mjs";

export const provider = new ethers.JsonRpcProvider(CFG.evmRpc, CFG.chainId);

// ---- address helpers (an Abakos account is one keypair with two encodings) ----
export function normalizeEvm(addr) {
  return ethers.getAddress(addr.trim()); // checksums, throws if invalid
}
export function evmToCosmos(evmAddr) {
  const bytes = fromHex(evmAddr.replace(/^0x/, ""));
  return toBech32(CFG.bech32Prefix, bytes);
}
export function cosmosToEvm(bech) {
  const { data } = fromBech32(bech);
  return ethers.getAddress("0x" + toHex(data));
}
// Accept either an 0x... or abakos1... address; return {evm, cosmos}.
export function parseAddress(input) {
  const s = input.trim();
  if (s.startsWith("0x")) {
    const evm = normalizeEvm(s);
    return { evm, cosmos: evmToCosmos(evm) };
  }
  if (s.startsWith(CFG.bech32Prefix + "1")) {
    const evm = cosmosToEvm(s);
    return { evm, cosmos: s };
  }
  throw new Error("Not a valid Abakos address (expected 0x… or abakos1…).");
}

// ---- balance: proves the wallet is installed & funded (ABA only exists via the app/faucet) ----
export async function getAbaBalance(evmAddr) {
  const wei = await provider.getBalance(evmAddr);
  return Number(ethers.formatEther(wei)); // ABA (18-dec on EVM)
}

// ---- mining: read the public agent stats and match this address ----
export async function getAgentStats() {
  const r = await fetch(CFG.agentStats, { headers: { accept: "application/json" } });
  if (!r.ok) throw new Error(`agent/stats ${r.status}`);
  return r.json();
}
export async function getProviderInfo({ evm, cosmos }) {
  let stats;
  try { stats = await getAgentStats(); } catch { return { earnedAba: 0, active: false, price: null }; }
  const list = Array.isArray(stats.providers) ? stats.providers : [];
  const want = new Set([evm.toLowerCase(), cosmos.toLowerCase(), evm.replace(/^0x/, "").toLowerCase()]);
  const p = list.find((x) => x && x.address && want.has(String(x.address).toLowerCase()));
  return {
    earnedAba: p ? Number(p.earned_aba || 0) : 0,
    active: p ? !!p.active : false,
    price: stats.aba_price_usd != null ? Number(stats.aba_price_usd) : null,
  };
}

// ---- trader: detect a real USDC<->ABA trade on either pool ----
// We key on the USDC ERC-20 Transfer, NOT the pair's Swap event: ABA<->USDC swaps go through
// swapExact{ETHForTokens,TokensForETH}, so the router does the WABA wrap/unwrap and the pair's
// Swap `to` is the *router*, never the user. The USDC leg, however, always moves directly
// between the user and the pool — user->pool when selling USDC, pool->user when buying it.
// (This also naturally covers liquidity adds, which likewise move USDC to a pool.)
// The node caps eth_getLogs at CFG.logChunkBlocks, so we scan newest->oldest and stop on first hit.
const TRANSFER_TOPIC = ethers.id("Transfer(address,address,uint256)");
const topicToAddr = (t) => "0x" + t.slice(26).toLowerCase();
export async function hasSwapped(evmAddr) {
  const userTopic = ethers.zeroPadValue(ethers.getAddress(evmAddr), 32);
  const pools = new Set((CFG.tradePairs?.length ? CFG.tradePairs : [CFG.pair]).map((p) => p.toLowerCase()));
  const head = await provider.getBlockNumber();
  const span = Math.max(1, CFG.logChunkBlocks);
  for (let to = head; to >= 0; to -= span + 1) {
    const from = Math.max(0, to - span);
    try {
      const [sent, recv] = await Promise.all([
        provider.getLogs({ address: CFG.usdc, topics: [TRANSFER_TOPIC, userTopic], fromBlock: from, toBlock: to }), // user -> ? (sold USDC)
        provider.getLogs({ address: CFG.usdc, topics: [TRANSFER_TOPIC, null, userTopic], fromBlock: from, toBlock: to }), // ? -> user (bought USDC)
      ]);
      if (sent.some((l) => pools.has(topicToAddr(l.topics[2])))) return true; // to a pool
      if (recv.some((l) => pools.has(topicToAddr(l.topics[1])))) return true; // from a pool
    } catch {
      // range/transient issue on this window — keep scanning older windows
    }
    if (from === 0) break;
  }
  return false;
}

// ---- price: prefer the agent oracle, fall back to on-chain pair reserves ----
const PAIR_ABI = ["function getReserves() view returns (uint112 r0, uint112 r1, uint32 ts)", "function token0() view returns (address)"];
export async function getAbaPriceUsd() {
  try {
    const stats = await getAgentStats();
    if (stats.aba_price_usd != null) return { price: Number(stats.aba_price_usd), source: stats.aba_price_source || "agent" };
  } catch { /* fall through */ }
  // On-chain fallback: price = (usdc reserve /1e6) / (waba reserve /1e18)
  const pair = new ethers.Contract(CFG.pair, PAIR_ABI, provider);
  const [reserves, token0] = await Promise.all([pair.getReserves(), pair.token0()]);
  const usdcIs0 = token0.toLowerCase() === CFG.usdc.toLowerCase();
  const usdcRes = Number(usdcIs0 ? reserves.r0 : reserves.r1) / 1e6;
  const wabaRes = Number(usdcIs0 ? reserves.r1 : reserves.r0) / 1e18;
  return { price: wabaRes > 0 ? usdcRes / wabaRes : 0, source: "uniswap-v2" };
}

// ---- ownership proof ----
export function verifySignature(discordId, address, signature) {
  const recovered = ethers.verifyMessage(CFG.signMessage(discordId), signature);
  return recovered.toLowerCase() === address.toLowerCase();
}
