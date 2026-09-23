// Central config for the Abakos community bot.
// All on-chain values verified against the repo (chain 9721, sandbox DEX deploy).

export const CFG = {
  // ---- Discord ----
  token: process.env.DISCORD_TOKEN,
  clientId: process.env.DISCORD_CLIENT_ID || "1530579158953099388", // Abakos Bot application id (public)
  guildId: process.env.DISCORD_GUILD_ID || "1520089164744495234", // Abakos server

  // Elegant "live" stat channels: the bot RENAMES these (no repeated posting).
  // Make them locked voice channels at the top of the list. Paste their ids.
  priceStatChannelId: process.env.PRICE_STAT_CHANNEL_ID || "", // e.g. renamed to "💰 ABA $0.0021"
  memberStatChannelId: process.env.MEMBER_STAT_CHANNEL_ID || "", // e.g. "👥 Members: 42"
  minerStatChannelId: process.env.MINER_STAT_CHANNEL_ID || "", // e.g. "⛏️ Miners: 7"

  // #leaderboard — the bot keeps ONE embed here (top miners by earned ABA + top inviters), edited each stat tick.
  leaderboardChannelId: process.env.LEADERBOARD_CHANNEL_ID || "1530542473355591851",
  // Invite-reward ladder: reaching `count` invites auto-grants `role` and shouts it in #gm.
  inviteRewards: [
    { count: 3, role: "Contributor" },
    { count: 10, role: "OG" },
  ],

  // Verification method: "tx" (send a free on-chain tx from your wallet — recommended,
  // no message-signing UI needed) or "sig" (sign a message). "trust" = link without proof.
  verifyMethod: (process.env.VERIFY_METHOD || "tx").toLowerCase(),

  // For the "tx" method: the bot's verify wallet. Users send any amount here from their
  // wallet to prove ownership; the bot detects it, links them, and sends it back.
  // Fund it with a little ABA so it can refund. Keep the key secret.
  verifyAddress: process.env.VERIFY_ADDRESS || "",
  verifyPrivkey: process.env.VERIFY_PRIVKEY || "",
  verifyScanIntervalMs: Number(process.env.VERIFY_SCAN_INTERVAL_MS || "20000"),
  // Cold-start lookback: on first run (no verify.json) scan this many recent blocks for
  // un-refunded incoming txs, so ABA sent before a /link (or while the bot was down) is refunded.
  verifyBackfillBlocks: Number(process.env.VERIFY_BACKFILL_BLOCKS || "2000"),

  // ---- Abakos chain (verified) ----
  evmRpc: process.env.EVM_RPC || "https://evm-rpc.abakos.ai",
  cosmosRest: process.env.COSMOS_REST || "https://rest.abakos.ai",
  chainId: 9721,
  bech32Prefix: "abakos",

  // Public agent stats endpoint: { aba_price_usd, aba_price_source, providers: [{address, earned_aba, active, ...}] }
  agentStats: process.env.AGENT_STATS || "https://explorer.abakos.ai/agent/stats",

  // DEX (Uniswap-v2 fork) — from dex/deployed-uniswap.json (v2, after the ABA-LP migration).
  router: "0xa1F065A4f30B06945D54c164861c54390B925c1F",
  factory: "0x5022f3F6C54dd05ccB28e51806bA64061F4523b9",
  waba: "0x380Dc585E9437362821F55d6237090Db9BF67c73",
  usdc: "0x4E46004562C46AB7EC0cC4C1ca14E9e20E2545B5", // IBC USDC from Noble, 6 decimals (agent/stats labels the buyback stablecoin "USDT" — same token)
  pair: "0x270F1f5B2192C418B76F2555bDae9352004986f2", // USDC/WABA (current pool, used for the on-chain price fallback)
  // 💱 Trader is granted on a Swap to the user on EITHER pool, so pre-migration trades still count.
  tradePairs: [
    "0x270F1f5B2192C418B76F2555bDae9352004986f2", // current
    "0x233cCefd6ea87a3987B13D948117Ec51957F960b", // legacy (pre ABA-LP migration)
  ],

  // Mining payouts arrive from this buyback wallet (agent.py). Kept for reference / future checks.
  buybackCosmos: "abakos175wca4q7lej002hs37lyyptr22kdksdm90sepj",

  // ---- Role names the bot manages (created automatically if missing) ----
  roles: {
    genesis: "Genesis Tester",
    holder: "💎 Holder",
    provider: "🛠️ Provider",
    trader: "💱 Trader",
  },

  // The RPC node caps eth_getLogs at this many blocks per query, so Swap scans are chunked.
  logChunkBlocks: Number(process.env.LOG_CHUNK_BLOCKS || "10000"),

  // Thresholds
  holderMinAba: Number(process.env.HOLDER_MIN_ABA || "0"), // > this ABA (18-dec on EVM) => Holder
  syncIntervalMs: Number(process.env.SYNC_INTERVAL_MS || String(30 * 60 * 1000)), // re-verify linked users
  // Stat-channel renames (price/members/miners). Discord limits renames to 2 / 10 min
  // per channel, so keep this >= 5 min. 15 min is a safe, live-feeling default.
  statIntervalMs: Number(process.env.STAT_INTERVAL_MS || String(15 * 60 * 1000)),

  // Message signed by users to prove ownership (must match the wallet's signMessage output).
  signMessage: (discordId) => `Abakos Discord verification\nDiscord ID: ${discordId}\nI own this wallet.`,
};

export function assertConfig() {
  const missing = [];
  if (!CFG.token) missing.push("DISCORD_TOKEN");
  if (!CFG.clientId) missing.push("DISCORD_CLIENT_ID");
  if (missing.length) {
    throw new Error(`Missing env vars: ${missing.join(", ")}. Copy .env.example to .env and fill it.`);
  }
}
