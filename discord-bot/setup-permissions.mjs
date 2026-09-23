// One-off: set channel write rules across the server + lock stat voice channels.
// Uses the bot (needs Manage Roles + Manage Channels). Run:
//   node --env-file=.env setup-permissions.mjs
import { Client, GatewayIntentBits, ChannelType, PermissionFlagsBits } from "discord.js";

const GUILD = process.env.DISCORD_GUILD_ID || "1520089164744495234";
// Read-only text channels: @everyone can view + read history, but not post.
const READONLY = ["rules", "welcome-verify", "announcements", "genesis-quests", "product-updates", "leaderboard"];
// Voice stat channels (by id): nobody may join.
const STAT_VOICE = ["1530585705196028024", "1530586273176092793", "1530591440307097680"];
// Roles allowed to post in read-only channels (besides the owner).
const STAFF_ROLES = ["Council"];

const c = new Client({ intents: [GatewayIntentBits.Guilds] });
c.once("clientReady", async () => {
  const g = await c.guilds.fetch(GUILD);
  await g.roles.fetch();
  const everyone = g.roles.everyone;
  const staff = STAFF_ROLES.map((n) => g.roles.cache.find((r) => r.name === n)).filter(Boolean);
  const chans = await g.channels.fetch();

  const denyPost = { SendMessages: false, SendMessagesInThreads: false, CreatePublicThreads: false, CreatePrivateThreads: false };

  for (const ch of chans.values()) {
    if (!ch) continue;
    // MEE6 check
    if (ch.type === ChannelType.GuildText && READONLY.includes(ch.name)) {
      await ch.permissionOverwrites.edit(everyone, denyPost, { reason: "read-only channel" });
      for (const s of staff) await ch.permissionOverwrites.edit(s, { SendMessages: true, SendMessagesInThreads: true }, { reason: "staff may post" });
      console.log(`read-only: #${ch.name}`);
    }
    if (ch.type === ChannelType.GuildVoice && STAT_VOICE.includes(ch.id)) {
      await ch.permissionOverwrites.edit(everyone, { Connect: false }, { reason: "stat channel (display only)" });
      console.log(`locked voice: ${ch.name}`);
    }
  }

  // report members (to confirm MEE6 presence)
  const members = await g.members.fetch();
  console.log("MEMBERS:", members.map((m) => `${m.user.username}${m.user.bot ? "(bot)" : ""}`).join(", "));
  await c.destroy();
  process.exit(0);
});
c.login(process.env.DISCORD_TOKEN);
