# Abakos (ABA)

> Project name from Greek *abax / abakos* (abacus, the oldest computing device), a direct tie to compute. Ticker `ABA`. Domain `abakos.ai` live.
>
> **Tagline:** Hardware that stays fully used.

**One-line pitch:**
> Abakos is a Proof-of-Stake compute network, a fork of the open Akash stack, where hardware earns the maximum it can: rent CPU, RAM, GPU and storage through the Console, and when GPU or CPU would sit idle the Provider Agent mines the most profitable coin and auto-converts the proceeds into ABA.

---

## What this is

Abakos runs the product suite Akash proved (Console for deploys, Chat, an OpenAI-compatible API, and provider software), on its **own** Proof-of-Stake chain forked from `github.com/akash-network/node` (Cosmos SDK + CometBFT, Apache-2.0), so **ABA** is the settlement and staking asset with native fee capture, genesis allocation and validator economics.

The differentiator versus plain rental networks: a **Provider Agent** keeps every machine fully utilized. Paid rentals fill the machine first; any idle GPU or CPU mines the most profitable coin, auto-converts to ABA (buyback with a 10% protocol cut: 90% to the host, 5% to stakers, 5% to treasury), and pays the host. No ABA is minted as a compute subsidy; supply is fixed.

> Earlier direction: Abakos began as a `btcd` Proof-of-Useful-Work fork (Pearl-style). That prototype is archived under [`legacy/node-btcd/`](legacy/node-btcd/) and is no longer the product. The live thesis is the Akash-based PoS chain described above and on the website.

## Core design decisions

1. **Utilization first, zero inflation.** Hosts are paid from real paths only: buyer ABA for rentals, or mining proceeds auto-converted to ABA. Chain security is paid from protocol fees plus the staker share of the mining/Chat cuts — ABA has **zero inflation** (fixed 10B supply), never minting.
2. **Bundles, not naked GPUs.** A deployment is always CPU + RAM + disk, with optional GPU, persistent storage and IP lease add-ons (same model as Akash leases).
3. **ABA wallet at MVP.** Settlement is ABA wallet only at the start; a fiat to ABA onramp comes later.

## Product pillars

| Pillar | What | For whom |
|---|---|---|
| `abakosd` (chain) | Akash fork, PoS, ABA settlement + staking + marketplace modules | Validators, everyone |
| Console | Deploy templates + bundles + add-ons, ABA escrow (`console.abakos.ai`) | Compute buyers |
| Provider Agent | Rent-first scheduler + idle GPU/CPU mining into ABA + Dashboard | GPU/CPU providers |
| Abakos Chat | Open-model chat, demand engine (`chat.abakos.ai`) | End users |
| Developer API | OpenAI-compatible gateway (`api.abakos.ai`) | Devs, AI startups |

## Repository layout

```
abakos/
  chain/          # abakosd: PoS chain, fork of akash-network/node (Cosmos SDK), ABA
  chain-sdk/      # vendored + rebranded Akash SDK (abakos/uaba prefixes)
  provider-agent/ # Provider Agent: profitability oracle + backend; real miner at site/public/miner.py
  site/           # marketing site + wallet + explorer + provider dashboard (deployed at abakos.ai)
  docs/           # litepaper + whitepaper (canonical)
  marketplace/    # notes (the marketplace lives in the chain modules)
  api/            # notes (OpenAI-compatible gateway, planned)
  legacy/         # ARCHIVED, not the product: node-btcd PoUW prototype, old pouw/miner/model/
                  # explorer/deck, and earlier numbered research docs under legacy/docs/
```

## Networks

- `abakos-sandbox-1`: mainnet-grade **sandbox** (own genesis, validator, gov/staking, marketplace + **EVM** modules, public endpoints). ABA has no market value by design. Live.
- `abakos-1`: future mainnet, same steps with new genesis keys.

Denom `uaba` (6 decimals, display `ABA`), bech32 prefix `abakos`, fixed genesis supply 10,000,000,000 ABA.

## Status

**Live:** https://abakos.ai (site, waitlist) + `console.`/`chat.`/`status.` subdomains. **Sandbox `abakos-sandbox-1` is live:** `abakosd` PoS chain (10B ABA, 0% inflation, ~1s blocks), `rpc.`/`rest.abakos.ai`, web wallet, explorer, faucet, and the Provider Agent (real CPU/GPU mining → ABA payouts). The chain is now also an **EVM** (cosmos/evm, EIP-155 chain id 9721): eth JSON-RPC at `evm-rpc.abakos.ai`, native MetaMask, and a live on-chain **ABA/USDC DEX** at `abakos.ai/dex/`.

- [`docs/litepaper.md`](docs/litepaper.md) and [`docs/whitepaper.md`](docs/whitepaper.md) are the canonical public docs.
- Earlier PoUW/Pearl-era planning notes are archived under [`legacy/`](legacy/) and are not the product.

**Next:** full Uniswap-v2 fork (the current DEX is a minimal constant-product AMM), EVM + precompile + AMM security audit, fiat onramp, mainnet.

## Build (chain)

The chain is a Cosmos SDK app and builds on **Linux** (Go 1.25+, CosmWasm `libwasmvm`). Use WSL or the Linux server; Windows is for editing only. Build/run steps live in [`chain/`](chain/) once the fork is vendored.

## Deployment (site, live)

- **Host:** IONOS VPS `217.160.46.61`, Ubuntu, Caddy (auto-TLS).
- **Site content:** `/opt/sites/abakos.ai/public/`. Deploy with `python scripts/abakos_deploy.py` in the `MarlonMoralesServer` repo after `npm run build` in `site/`.
- **Caddy snippet:** `MarlonMoralesServer/sites/abakos.ai/Caddyfile.snippet`.

---

*Living planning document. Parameters (numbers, allocation) are starting values, subject to legal and audit review before any mainnet.*
