# Abakos Discord Bot

On-chain–verified community roles + live stat channels. Everything it grants is backed by a **real, publicly queryable on-chain artifact** — no screenshots, no trust-me.

## What it does

| Command | Effect |
|---|---|
| `/link address [signature]` | Links your Abakos wallet (proves ownership), then grants the roles you qualify for. |
| `/verify` | Re-checks your wallet and updates your roles. |
| `/price` | Shows the current ABA price. |
| `/whoami` | Shows which wallet you linked. |

**Auto-granted roles (verified on-chain):**
- **Genesis Tester** — any real activity (holds ABA, mined, or swapped). Sandbox ABA only exists through the app, so this proves the wallet is installed & used.
- **💎 Holder** — native ABA balance `> HOLDER_MIN_ABA` (`eth_getBalance`, chain 9721).
- **🛠️ Provider** — `earned_aba > 0` / `active` in the public agent stats (`explorer.abakos.ai/agent/stats`). The idle-mining quest: risk-free, spare compute only.
- **💱 Trader** — a Uniswap-v2 `Swap` on the USDC/WABA pair delivered to the wallet (`eth_getLogs`).

Re-verifies every 30 min, so roles appear automatically as people mine/hold/swap.

## Elegant extras
- **Live stat channels (rename, don't spam):** the bot renames locked voice channels instead of posting — put these at the top of the channel list:
  - `PRICE_STAT_CHANNEL_ID` → `💰 ABA $0.0021`
  - `MEMBER_STAT_CHANNEL_ID` → `👥 Members: 42`
  - `MINER_STAT_CHANNEL_ID` → `⛏️ Miners: 7`
  - Bot presence also shows the price ("Watching ABA $0.0021").
- Updated every `STAT_INTERVAL_MS` (default 15 min — Discord caps channel renames at 2 / 10 min).

## Ownership proof (pick one via `VERIFY_METHOD`)
- **`tx` (default, recommended — free on Abakos):** `/link 0x…` → the bot asks you to send **any small amount** from that wallet to its verify address. It detects the tx (~30 s), links you, grants roles, and **sends the amount right back**. No message-signing UI needed. Requires `VERIFY_ADDRESS` + `VERIFY_PRIVKEY` (fund it with a little ABA for refunds).
- **`sig`:** classic EIP-191 message signature (`ethers.verifyMessage`). Use if you prefer signing over a tx.
- **`trust`:** links without proof — spoofable, only for very early testing.

## Setup
1. **Create the bot app**: <https://discord.com/developers/applications> → New Application → **Bot** → copy **token** + **Application ID**. Enable **Server Members Intent**.
2. **Invite** with `bot applications.commands` + **Manage Roles** + **Manage Channels** (for stat renames). Put its role **above** 💎/🛠️/💱 and Genesis Tester.
3. **Create channels/ids**: three locked voice channels for stats; copy their ids into `.env`.
4. **Configure**: `cp .env.example .env` and fill it.
5. **Run**:
   ```bash
   npm install
   npm run register   # once
   npm start
   ```

## Deploy for 24/7 (pick one)
The bot must run continuously. Two ready paths:

**A) VPS / systemd** (same style as the provider agent):
```bash
sudo cp -r discord-bot /opt/abakos-bot && cd /opt/abakos-bot
npm ci --omit=dev
# put your secrets in /opt/abakos-bot/.env  (see .env.example)
sudo cp abakos-bot.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now abakos-bot
journalctl -u abakos-bot -f
```

**B) Docker / Console** (dogfood — run it on Abakos itself):
```bash
docker build -t abakos-bot .
docker run -d --restart=always --env-file .env --name abakos-bot abakos-bot
```
On `console.abakos.ai`, deploy this image (CPU/RAM only) and supply the `.env` values as the deployment's env/secrets.

> Keep `.env` out of the image — it's provided at runtime. `.env` and `links.json` are gitignored/dockerignored.

> Sandbox ABA has **real value** (live DEX vs real Noble USDC) — it's just the sandbox phase, so only risk what you can afford to lose. The mining *hashrate* is simulated; balances, swaps and payouts are real on-chain txs, and the bot only ever verifies those real artifacts.

## Files
- `config.mjs` — addresses/endpoints (verified) + role names, thresholds, stat-channel ids, verify method.
- `chain.mjs` — on-chain checks (balance, agent stats, swap logs, price, signature).
- `verify.mjs` — test-tx scanner + refund.
- `bot.mjs` — client, role sync, stat channels, verify poller, commands.
- `register-commands.mjs` — registers slash commands.
- `storage.mjs` / `links.json` — wallet links (gitignored).
