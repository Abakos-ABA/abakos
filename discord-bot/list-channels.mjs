// One-off helper: print voice channel ids (for the stat-channel .env values). Run:
//   node --env-file=.env list-channels.mjs
import { Client, GatewayIntentBits } from "discord.js";
const c = new Client({ intents: [GatewayIntentBits.Guilds] });
c.once("clientReady", async () => {
  const g = await c.guilds.fetch(process.env.DISCORD_GUILD_ID || "1520089164744495234");
  const chans = await g.channels.fetch();
  console.log("VOICE CHANNELS (id  name):");
  chans.forEach((ch) => { if (ch && ch.type === 2) console.log(`${ch.id}  ${ch.name}`); });
  await c.destroy();
  process.exit(0);
});
c.login(process.env.DISCORD_TOKEN);
