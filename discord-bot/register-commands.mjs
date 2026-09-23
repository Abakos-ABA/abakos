// Registers the slash commands for the Abakos guild. Run once (and after changing commands):
//   npm run register
import { REST, Routes, SlashCommandBuilder, InteractionContextType, ApplicationIntegrationType } from "discord.js";
import { CFG, assertConfig } from "./config.mjs";

assertConfig();

// Allow every command in servers AND in a DM to the bot, so wallet linking can be
// done privately. (Global commands can take up to ~1h to propagate the first time.)
const CONTEXTS = [InteractionContextType.Guild, InteractionContextType.BotDM, InteractionContextType.PrivateChannel];
const INTEGRATIONS = [ApplicationIntegrationType.GuildInstall];
const withCtx = (b) => b.setContexts(CONTEXTS).setIntegrationTypes(INTEGRATIONS);

const commands = [
  withCtx(new SlashCommandBuilder()
    .setName("link")
    .setDescription("Link your Abakos wallet to earn on-chain roles (private)")
    .addStringOption((o) => o.setName("address").setDescription("Your 0x… or abakos1… address").setRequired(true))
    .addStringOption((o) => o.setName("signature").setDescription("Signature of the verification message (see /link help)").setRequired(false))),
  withCtx(new SlashCommandBuilder().setName("verify").setDescription("Re-check your wallet and update your roles (private)")),
  withCtx(new SlashCommandBuilder().setName("price").setDescription("Show the current ABA price")),
  withCtx(new SlashCommandBuilder().setName("whoami").setDescription("Show which wallet you have linked (private)")),
  withCtx(new SlashCommandBuilder()
    .setName("invites")
    .setDescription("Show how many people you've invited")
    .addUserOption((o) => o.setName("user").setDescription("Check someone else (optional)").setRequired(false))),
].map((c) => c.toJSON());

const rest = new REST({ version: "10" }).setToken(CFG.token);
// Register globally (usable in DMs) and clear the old guild-scoped copies to avoid duplicates.
await rest.put(Routes.applicationCommands(CFG.clientId), { body: commands });
await rest.put(Routes.applicationGuildCommands(CFG.clientId, CFG.guildId), { body: [] });
console.log(`Registered ${commands.length} GLOBAL commands (server + DM) and cleared guild commands.`);
