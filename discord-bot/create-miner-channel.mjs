// One-off: create the ⛏️ Miners voice stat channel and print its id. Run:
//   node --env-file=.env create-miner-channel.mjs
import { Client, GatewayIntentBits, ChannelType } from "discord.js";
const c = new Client({ intents: [GatewayIntentBits.Guilds] });
c.once("clientReady", async () => {
  const g = await c.guilds.fetch(process.env.DISCORD_GUILD_ID || "1520089164744495234");
  const chans = await g.channels.fetch();
  let ch = chans.find((x) => x && x.type === ChannelType.GuildVoice && /Miners/i.test(x.name));
  if (!ch) ch = await g.channels.create({ name: "⛏️ Miners", type: ChannelType.GuildVoice });
  console.log("MINER_CHANNEL_ID=" + ch.id);
  await c.destroy();
  process.exit(0);
});
c.login(process.env.DISCORD_TOKEN);
