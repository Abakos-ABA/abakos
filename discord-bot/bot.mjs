// Abakos community bot — verified on-chain roles + live stat channels.
// Start: npm install && npm run register && npm start
import { Client, GatewayIntentBits, Partials, ActivityType } from "discord.js";
import { CFG, assertConfig } from "./config.mjs";
import { loadLinks, saveLinks, loadInvites, saveInvites, loadVerifyState, saveVerifyState, loadMisc, saveMisc } from "./storage.mjs";
import { parseAddress, getAbaBalance, getProviderInfo, hasSwapped, getAbaPriceUsd, getAgentStats, verifySignature } from "./chain.mjs";
import { scanIncoming, refund } from "./verify.mjs";
import { ethers } from "ethers";

assertConfig();
const links = loadLinks();
const invites = loadInvites(); // { inviterId: count }
const inviteCache = new Map(); // code -> uses
const pendingByAddr = {}; // addrLower -> { discordId, evm, cosmos }
const misc = loadMisc(); // { leaderboardMsgId }

const client = new Client({
  intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMembers, GatewayIntentBits.GuildInvites],
  partials: [Partials.GuildMember],
});

const ROLE_COLORS = { [CFG.roles.holder]: 0x22d3ee, [CFG.roles.provider]: 0xf59e0b, [CFG.roles.trader]: 0x22c55e };
const fmtPrice = (p) => (p < 0.01 ? p.toFixed(6) : p.toFixed(4));

async function ensureRoles(guild) {
  const map = {};
  await guild.roles.fetch();
  for (const name of [CFG.roles.genesis, CFG.roles.holder, CFG.roles.provider, CFG.roles.trader]) {
    let role = guild.roles.cache.find((r) => r.name === name);
    if (!role && name !== CFG.roles.genesis) {
      role = await guild.roles.create({ name, color: ROLE_COLORS[name] || 0, hoist: false, mentionable: false, reason: "Abakos bot role" });
      console.log(`Created role ${name}`);
    }
    if (role) map[name] = role;
  }
  return map;
}

async function syncMember(guild, discordId, roles) {
  const link = links[discordId];
  if (!link) return "No wallet linked. Use /link first.";
  const member = await guild.members.fetch(discordId).catch(() => null);
  if (!member) return "Could not find you in the server.";
  const [balance, prov, swapped] = await Promise.all([
    getAbaBalance(link.evm).catch(() => 0),
    getProviderInfo(link).catch(() => ({ earnedAba: 0, active: false })),
    hasSwapped(link.evm).catch(() => false),
  ]);
  const earned = [];
  const add = async (roleName, cond) => {
    const role = roles[roleName];
    if (role && cond && !member.roles.cache.has(role.id)) { await member.roles.add(role, "Abakos on-chain verify"); earned.push(roleName); }
  };
  await add(CFG.roles.genesis, balance > 0 || prov.earnedAba > 0 || swapped);
  await add(CFG.roles.holder, balance > CFG.holderMinAba);
  await add(CFG.roles.provider, prov.earnedAba > 0 || prov.active);
  await add(CFG.roles.trader, swapped);
  return [
    `Wallet: \`${link.evm}\``,
    `• ABA balance: **${balance.toFixed(4)}**`,
    `• Mining earned: **${prov.earnedAba.toFixed(4)} ABA**${prov.active ? " (active ⛏️)" : ""}`,
    `• DEX swap: **${swapped ? "yes" : "not yet"}**`,
    earned.length ? `🎉 New roles: ${earned.join(", ")}` : "Roles up to date.",
  ].join("\n");
}

async function renameChannel(id, name) {
  if (!id) return;
  const ch = await client.channels.fetch(id).catch(() => null);
  if (ch && ch.name !== name) await ch.setName(name).catch((e) => console.error("rename", e.message));
}

// Grant a role by its name (used for invite rewards). Returns true only if newly added.
async function grantRoleByName(guild, memberId, roleName, reason) {
  try {
    let role = guild.roles.cache.find((r) => r.name === roleName);
    if (!role) role = (await guild.roles.fetch()).find((r) => r.name === roleName);
    const member = await guild.members.fetch(memberId).catch(() => null);
    if (!role || !member || member.roles.cache.has(role.id)) return false;
    await member.roles.add(role, reason);
    return true;
  } catch (e) { console.error("grantRole", e.message); return false; }
}

// Keep ONE leaderboard embed in #leaderboard fresh: top miners by earned ABA + top inviters.
async function updateLeaderboard() {
  if (!CFG.leaderboardChannelId) return;
  const ch = await client.channels.fetch(CFG.leaderboardChannelId).catch(() => null);
  if (!ch?.isTextBased?.()) return;
  const stats = await getAgentStats().catch(() => null);
  const cosmosToId = {};
  for (const [id, l] of Object.entries(links)) if (l?.cosmos) cosmosToId[l.cosmos.toLowerCase()] = id;
  const nameFor = (addr) => {
    const id = cosmosToId[String(addr).toLowerCase()];
    return id ? `<@${id}>` : `\`${String(addr).slice(0, 9)}…${String(addr).slice(-4)}\``;
  };
  const rank = ["🥇", "🥈", "🥉", "**4.**", "**5.**"];
  const miners = (stats?.providers || []).filter((p) => p && Number(p.earned_aba) > 0)
    .sort((a, b) => Number(b.earned_aba) - Number(a.earned_aba)).slice(0, 5);
  const minerLines = miners.length
    ? miners.map((p, i) => `${rank[i]} ${nameFor(p.address)} — **${Number(p.earned_aba).toFixed(2)} ABA**${p.active ? " ⛏️" : ""}`).join("\n")
    : "_No miners yet — spin up a Provider Agent and be first!_";
  const inv = Object.entries(invites).filter(([, n]) => n > 0).sort((a, b) => b[1] - a[1]).slice(0, 5);
  const invLines = inv.length
    ? inv.map(([id, n], i) => `${rank[i]} <@${id}> — **${n}** invite${n === 1 ? "" : "s"}`).join("\n")
    : "_No invites yet — share your invite link to climb!_";
  const price = stats?.aba_price_usd != null ? `$${fmtPrice(Number(stats.aba_price_usd))}` : "—";
  const embed = {
    title: "🏆 Abakos Genesis Leaderboard",
    color: 0xf1c40f,
    description: `**⛏️ Top Miners** _(earned ABA)_\n${minerLines}\n\n**🎟️ Top Inviters**\n${invLines}`,
    footer: { text: `ABA ${price} · refreshes every ${Math.round(CFG.statIntervalMs / 60000)} min · earn a role: 3 invites → Contributor, 10 → OG` },
  };
  try {
    if (misc.leaderboardMsgId) {
      const msg = await ch.messages.fetch(misc.leaderboardMsgId).catch(() => null);
      if (msg) return void (await msg.edit({ embeds: [embed] }));
    }
    const msg = await ch.send({ embeds: [embed] });
    misc.leaderboardMsgId = msg.id; saveMisc(misc);
  } catch (e) { console.error("leaderboard", e.message); }
}

client.once("clientReady", async () => {
  console.log(`Logged in as ${client.user.tag}`);
  const guild = await client.guilds.fetch(CFG.guildId);
  const roles = await ensureRoles(guild);
  client.roles = roles;

  // Snapshot current invite uses so we can detect which invite a new member used.
  try {
    const inv = await guild.invites.fetch();
    inv.forEach((i) => inviteCache.set(i.code, i.uses || 0));
    console.log(`Cached ${inviteCache.size} invites.`);
  } catch (e) { console.error("invite cache", e.message); }

  // Re-verify linked members (roles appear as they mine/hold/swap).
  const syncAll = async () => { for (const id of Object.keys(links)) { try { await syncMember(guild, id, roles); } catch (e) { console.error("sync", id, e.message); } } };
  setInterval(syncAll, CFG.syncIntervalMs); syncAll();

  // Live stat channels — rename instead of posting.
  const tickStats = async () => {
    try {
      const { price } = await getAbaPriceUsd();
      client.user.setActivity(`ABA $${fmtPrice(price)}`, { type: ActivityType.Watching });
      await renameChannel(CFG.priceStatChannelId, `💰 ABA $${fmtPrice(price)}`);
    } catch (e) { console.error("price", e.message); }
    try {
      const g = await client.guilds.fetch(CFG.guildId);
      await renameChannel(CFG.memberStatChannelId, `👥 Members: ${g.memberCount}`);
    } catch (e) { console.error("members", e.message); }
    try {
      const stats = await getAgentStats();
      // Match unMineable's worker count: each provider can run a CPU and a GPU worker, and the pool
      // lists a worker that is EITHER verified on the pool OR currently hashing (hashrate dips to 0
      // between samples, and a freshly-connected rig isn't "verified" yet — both are live workers).
      const isUp = (hs, verified) => !!verified || Number(hs) > 0;
      const workers = (stats.providers || []).reduce((n, p) =>
        n + (p && isUp(p.cpu_hs, p.cpu_verified) ? 1 : 0) + (p && isUp(p.gpu_hs, p.gpu_verified) ? 1 : 0), 0);
      await renameChannel(CFG.minerStatChannelId, `⛏️ Workers: ${workers}`);
    } catch (e) { console.error("workers", e.message); }
    await updateLeaderboard().catch((e) => console.error("leaderboard", e.message));
  };
  setInterval(tickStats, CFG.statIntervalMs); tickStats();

  // Test-tx verification poller. Two independent jobs per incoming tx to the verify wallet:
  //   1) ALWAYS refund the ABA back to the sender (even with no /link) — the wallet only ever holds
  //      funds in transit, never keeps them. Idempotent + persisted so it survives restarts.
  //   2) If the sender has a pending /link, link them, grant roles and DM a confirmation.
  if (CFG.verifyMethod === "tx" && CFG.verifyAddress) {
    const chain = await import("./chain.mjs");
    const vstate = loadVerifyState();
    vstate.refunded = vstate.refunded || {};
    const head0 = await chain.provider.getBlockNumber().catch(() => 0);
    const backfill = Math.max(0, CFG.verifyBackfillBlocks || 0);
    // Resume where we left off, but never scan more than `backfill` blocks of history at once.
    let last = Math.max(0, vstate.lastBlock ? Math.max(vstate.lastBlock, head0 - backfill) : head0 - backfill);

    const handleHits = async (hits) => {
      for (const h of hits) {
        // 1) Refund (idempotent) — never send the same incoming tx back twice.
        if (!vstate.refunded[h.hash]) {
          if (CFG.verifyPrivkey) {
            try {
              const rh = await refund(h.from, h.value);
              vstate.refunded[h.hash] = rh || true;
              saveVerifyState(vstate);
              console.log(`refunded ${ethers.formatEther(h.value)} ABA -> ${h.from} (${rh})`);
            } catch (e) { console.error("refund", e.message); }
          }
        }
        // 2) Link + roles only if this sender ran /link.
        const p = pendingByAddr[h.from.toLowerCase()];
        if (!p) continue;
        links[p.discordId] = { evm: p.evm, cosmos: p.cosmos };
        saveLinks(links);
        delete pendingByAddr[h.from.toLowerCase()];
        try {
          const summary = await syncMember(guild, p.discordId, roles);
          const user = await client.users.fetch(p.discordId);
          await user.send(`✅ Wallet verified & linked (I sent your test amount back).\n${summary}`);
          console.log(`verified ${p.discordId} <- ${h.from}`);
        } catch { /* DMs closed — roles still applied, they can /verify */ }
      }
    };

    const scanTo = async (now) => {
      if (now <= last) return;
      await handleHits(await scanIncoming(last + 1, now));
      last = now; vstate.lastBlock = last; saveVerifyState(vstate);
    };

    // Cold-start backfill: refund anything sent before /link or while the bot was down.
    try { await scanTo(await chain.provider.getBlockNumber()); }
    catch (e) { console.error("verify-backfill", e.message); }

    setInterval(async () => {
      try { await scanTo(await chain.provider.getBlockNumber()); }
      catch (e) { console.error("verify-poll", e.message); }
    }, CFG.verifyScanIntervalMs);
  }
});

client.on("interactionCreate", async (i) => {
  if (!i.isChatInputCommand()) return;
  const guild = await client.guilds.fetch(CFG.guildId);
  const roles = client.roles || (await ensureRoles(guild));

  if (i.commandName === "price") {
    await i.deferReply();
    const { price, source } = await getAbaPriceUsd();
    return i.editReply(`**ABA:** $${fmtPrice(price)}  _(source: ${source})_`);
  }
  if (i.commandName === "whoami") {
    const l = links[i.user.id];
    return i.reply({ content: l ? `You linked \`${l.evm}\`` : "No wallet linked yet. Use **/link**.", ephemeral: true });
  }
  if (i.commandName === "invites") {
    const target = i.options.getUser("user") || i.user;
    const n = invites[target.id] || 0;
    const who = target.id === i.user.id ? "You have" : `<@${target.id}> has`;
    return i.reply({ content: `${who} invited **${n}** ${n === 1 ? "person" : "people"}. 🎟️`, ephemeral: true });
  }
  if (i.commandName === "verify") {
    await i.deferReply({ ephemeral: true });
    return i.editReply(await syncMember(guild, i.user.id, roles));
  }
  if (i.commandName === "link") {
    await i.deferReply({ ephemeral: true });
    const raw = i.options.getString("address");
    const sig = i.options.getString("signature");
    let addr;
    try { addr = parseAddress(raw); } catch (e) { return i.editReply(`❌ ${e.message}`); }

    // Method: trust | sig | tx
    if (CFG.verifyMethod === "trust" || CFG.trustMode) {
      links[i.user.id] = { evm: addr.evm, cosmos: addr.cosmos }; saveLinks(links);
      return i.editReply(`✅ Linked!\n${await syncMember(guild, i.user.id, roles)}`);
    }
    if (CFG.verifyMethod === "sig") {
      if (!sig) return i.editReply(["🔐 Sign this exact message and run /link again with the `signature`:", "```", CFG.signMessage(i.user.id), "```"].join("\n"));
      let ok = false; try { ok = verifySignature(i.user.id, addr.evm, sig); } catch { ok = false; }
      if (!ok) return i.editReply("❌ Signature did not match that address.");
      links[i.user.id] = { evm: addr.evm, cosmos: addr.cosmos }; saveLinks(links);
      return i.editReply(`✅ Linked!\n${await syncMember(guild, i.user.id, roles)}`);
    }
    // default: tx method
    if (!CFG.verifyAddress) return i.editReply("⚠️ Verification wallet not configured. Ping an admin.");
    pendingByAddr[addr.evm.toLowerCase()] = { discordId: i.user.id, evm: addr.evm, cosmos: addr.cosmos };
    return i.editReply([
      "🔐 **Prove you own this wallet** — transactions are free on Abakos:",
      `Send **any small amount** (even 0.001 ABA) from \`${addr.evm}\` to:`,
      `\`\`\`${CFG.verifyAddress}\`\`\``,
      "I'll detect it within ~30s, link you, grant your roles, and **send the amount right back**. 💸",
    ].join("\n"));
  }
});

// ---- Invite tracking ----
client.on("inviteCreate", (inv) => inviteCache.set(inv.code, inv.uses || 0));
client.on("inviteDelete", (inv) => inviteCache.delete(inv.code));
client.on("guildMemberAdd", async (member) => {
  if (member.guild.id !== CFG.guildId) return;
  try {
    const current = await member.guild.invites.fetch();
    let used = null;
    for (const inv of current.values()) {
      const before = inviteCache.get(inv.code) || 0;
      if ((inv.uses || 0) > before) used = inv;
      inviteCache.set(inv.code, inv.uses || 0);
    }
    if (used && used.inviter) {
      const inviterId = used.inviter.id;
      invites[inviterId] = (invites[inviterId] || 0) + 1;
      saveInvites(invites);
      const n = invites[inviterId];
      const log = member.guild.channels.cache.find((c) => c.name === "moderator-only" && c.isTextBased?.());
      if (log) log.send(`📥 <@${member.id}> joined — invited by <@${inviterId}> (now ${n} invites).`).catch(() => {});
      // Invite-reward ladder: fires once, exactly when the count reaches a milestone.
      const gmCh = member.guild.channels.cache.find((c) => c.name === "gm" && c.isTextBased?.());
      for (const r of (CFG.inviteRewards || [])) {
        if (n === r.count) {
          const granted = await grantRoleByName(member.guild, inviterId, r.role, `Invite reward: ${r.count} invites`);
          if (granted && gmCh) gmCh.send(`🎉 <@${inviterId}> just hit **${r.count} invites** and earned **${r.role}**! 🏆 Keep recruiting Genesis Testers!`).catch(() => {});
        }
      }
    }

    // Cool public welcome in #gm — numbered for that "early OG" feeling (one clean line).
    const all = await member.guild.members.fetch();
    const num = all.filter((m) => !m.user.bot).size;
    const gm = member.guild.channels.cache.find((c) => c.name === "gm" && c.isTextBased?.());
    if (gm) gm.send(`gm <@${member.id}> 👋 welcome to **Abakos** — you're **Genesis Tester #${num}**. Grab your role in <#1530541493226573894> and say gm! 🚀`).catch(() => {});
  } catch (e) { console.error("memberAdd", e.message); }
});

client.login(CFG.token);
