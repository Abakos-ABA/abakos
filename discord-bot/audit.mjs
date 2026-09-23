// One-shot server audit: dumps roles, channels + @everyone overwrites, members, onboarding,
// community features. Read-only. Run: node --env-file=.env audit.mjs
import { Client, GatewayIntentBits, PermissionsBitField, ChannelType, Routes } from "discord.js";
import { CFG } from "./config.mjs";

const client = new Client({ intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMembers] });

const CH = {
  [ChannelType.GuildText]: "text", [ChannelType.GuildVoice]: "voice",
  [ChannelType.GuildCategory]: "category", [ChannelType.GuildAnnouncement]: "announcement",
  [ChannelType.GuildForum]: "forum", [ChannelType.GuildStageVoice]: "stage",
};
const P = PermissionsBitField.Flags;

client.once("ready", async () => {
  const g = await client.guilds.fetch(CFG.guildId);
  const full = await g.fetch();
  console.log("===== GUILD =====");
  console.log(`name: ${full.name} | members: ${full.memberCount} | features: ${full.features.join(", ") || "(none)"}`);
  console.log(`verificationLevel: ${full.verificationLevel} | boostTier: ${full.premiumTier} | boosts: ${full.premiumSubscriptionCount}`);
  console.log(`rulesChannel: ${full.rulesChannelId} | publicUpdates: ${full.publicUpdatesChannelId} | systemChannel: ${full.systemChannelId}`);

  console.log("\n===== ROLES (top→bottom) =====");
  const roles = [...g.roles.cache.values()].sort((a, b) => b.position - a.position);
  for (const r of roles) {
    const perms = [];
    if (r.permissions.has(P.Administrator)) perms.push("ADMIN");
    if (r.permissions.has(P.ManageGuild)) perms.push("ManageGuild");
    if (r.permissions.has(P.ManageRoles)) perms.push("ManageRoles");
    if (r.permissions.has(P.ManageChannels)) perms.push("ManageChannels");
    if (r.permissions.has(P.KickMembers)) perms.push("Kick");
    if (r.permissions.has(P.BanMembers)) perms.push("Ban");
    if (r.permissions.has(P.MentionEveryone)) perms.push("MentionEveryone");
    console.log(`  #${r.position} ${r.name} | hoist:${r.hoist ? "YES" : "no"} | members:${r.members.size} | color:${r.hexColor} | ${r.managed ? "MANAGED(bot) " : ""}${perms.join(",") || "basic"}`);
  }

  console.log("\n===== CHANNELS (by category) =====");
  const chans = [...g.channels.cache.values()];
  const cats = chans.filter(c => c.type === ChannelType.GuildCategory).sort((a, b) => a.position - b.position);
  const orphan = chans.filter(c => !c.parentId && c.type !== ChannelType.GuildCategory);
  const printChan = (c) => {
    const ov = c.permissionOverwrites?.cache?.get(g.id);
    const denies = [], allows = [];
    if (ov) {
      for (const [flag, name] of [[P.ViewChannel, "View"], [P.SendMessages, "Send"], [P.Connect, "Connect"], [P.AddReactions, "React"], [P.CreatePublicThreads, "Threads"]]) {
        if (ov.deny.has(flag)) denies.push(name);
        if (ov.allow.has(flag)) allows.push(name);
      }
    }
    const evy = denies.length || allows.length ? ` | @everyone deny:[${denies.join(",")}] allow:[${allows.join(",")}]` : "";
    console.log(`    [${CH[c.type] || c.type}] ${c.name}${evy}`);
  };
  for (const cat of cats) {
    console.log(`  ▼ ${cat.name}`);
    chans.filter(c => c.parentId === cat.id).sort((a, b) => a.position - b.position).forEach(printChan);
  }
  if (orphan.length) { console.log("  ▼ (no category)"); orphan.sort((a, b) => a.position - b.position).forEach(printChan); }

  console.log("\n===== MEMBERS =====");
  const members = await g.members.fetch();
  for (const m of members.values()) {
    const rs = [...m.roles.cache.values()].filter(r => r.name !== "@everyone").sort((a, b) => b.position - a.position).map(r => r.name);
    console.log(`  ${m.user.bot ? "[bot] " : ""}${m.user.username} — ${rs.join(", ") || "(no roles)"}`);
  }

  console.log("\n===== ONBOARDING =====");
  try {
    const ob = await client.rest.get(Routes.guildOnboarding(g.id));
    console.log(`enabled: ${ob.enabled} | mode: ${ob.mode} | prompts: ${ob.prompts?.length || 0} | defaultChannels: ${ob.default_channel_ids?.length || 0}`);
    (ob.prompts || []).forEach(p => console.log(`  prompt "${p.title}" (${p.options?.length || 0} options, required:${p.required})`));
  } catch (e) { console.log("onboarding fetch failed:", e.message); }

  console.log("\n===== WELCOME SCREEN =====");
  try {
    const ws = await client.rest.get(Routes.guildWelcomeScreen(g.id));
    console.log(`description: ${ws.description || "(none)"} | channels: ${ws.welcome_channels?.length || 0}`);
  } catch (e) { console.log("welcome screen: not enabled / " + e.message); }

  await client.destroy();
  process.exit(0);
});

client.login(CFG.token);
