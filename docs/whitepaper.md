# Abakos: A PoS Compute Network for Maximum Hardware Income

**Whitepaper v0.2, draft.** Public-facing. Figures and parameters are
illustrative starting assumptions, not final.

> *Hardware that stays fully used.*

## Abstract

Abakos is a Proof-of-Stake Layer-1 for decentralized compute, forked from
open Akash-style marketplace modules (Cosmos SDK + CometBFT) onto its own
chain so **ABA** can be the settlement and staking asset. The product thesis
is **maximum income from every machine**. It runs the product suite Akash
proved, the Console for deploys, Abakos Chat, and an OpenAI-compatible API,
on its own chain. Buyers deploy resource bundles (CPU + RAM + disk, optional
GPU) and optional add-ons (persistent storage, IP lease) through the Console,
paid from an ABA wallet. When GPU or CPU capacity would sit idle, a Provider
Agent mines the most profitable coin, auto-converts the proceeds into ABA,
and pays the host. Providers are not paid by minting ABA for compute. Earlier
Proof-of-Useful-Work / `btcd` research is archived and is not the live
product claim.

## 1. Background & motivation

AI and cloud workloads need cheap, available compute. Hyperscalers still
control most data-center GPU capacity. Decentralized rental networks proved
that self-serve container deployment can work (Akash, Vast.ai and similar),
but they leave a structural hole: **idle GPU and CPU hours usually earn
nothing**. Mining-only DePIN designs often mint tokens to hosts whether or
not anyone bought capacity, which decouples provider pay from real demand.

Abakos starts from Akash-like rental rails, then adds an Agent that keeps
idle compute earning by mining the most profitable coin and auto-converting
it into ABA, plus AI-native demand surfaces (Chat and API). Settlement at MVP
is ABA wallet only. Fiat credits (card to market-buy ABA) may come later as
an onramp, not as a substitute for ABA demand.

## 2. Design principle: utilization first, no provider inflation

```
if demand for slice/add-on:
    earn ABA from buyer escrow
else if GPU or CPU free:
    mine best coin -> auto-convert -> ABA to host (12% cut; 88% to host)
else:
    storage / RAM wait for rental (no mining path)
```

- Compute hosts are paid from **real money paths** (buyer ABA or mining
  proceeds auto-converted to ABA), not from minting ABA for idle work.
- Chain security is paid from **protocol fees plus the staker share of the
  mining and Chat cuts** — ABA has **zero inflation** (fixed 10B supply), not a
  minting subsidy.
- Buyers never rent a naked GPU. A deployment is always a **bundle**.

## 3. Architecture

### 3.1 Consensus & chain
- Own PoS app-chain, CosmWasm-capable Cosmos stack, forked so ABA captures
  fees, genesis allocation and validator economics.
- Technical base: open Akash marketplace modules (Apache-2.0 lineage) adapted
  to Abakos parameters and settlement.
- **Native EVM** (`cosmos/evm`, EIP-155 chain id 9721): Ethereum JSON-RPC and
  MetaMask alongside the Cosmos side, so Solidity contracts run natively.
- **Zero-fee (gasless):** transactions cost nothing on both the Cosmos and EVM
  sides (`no_base_fee`, `min_gas_price = 0`, `eth_gasPrice = 0`); spam is bounded
  by consensus `block.max_gas` and a capped mempool, not by price.
- **On-chain ABA/USDT DEX:** a Uniswap-v2 fork (0.30% swap fee to LPs) is the
  buyback venue and price oracle. Stablecoin standard is USDT (BEP20).
- Earlier PoUW / GEMM / reward-split work remains research archive only.

### 3.2 Console & marketplace
Two entry points into the same settlement rails:

- **Templates / hourly bundles:** one-click or browse; auto-match cheapest
  qualified provider or pick a listing.
- **Funded batch jobs:** used by the Developer API and Abakos Chat; ABA
  locked in escrow until delivery.

**What buyers pay for (not all "free in the container"):**

| Product | Required? | Notes |
|---|---|---|
| Base bundle | Yes | CPU + RAM + ephemeral disk |
| GPU | Optional | Attached to the same slice |
| Persistent storage | Optional | Survives restarts on same provider; lease-scoped |
| IP lease | Optional | Dedicated public IPv4 for the lease |
| Default hostname / ports | Included | Rides with base compute |

Providers list once and stay active. Matching assigns funded work
automatically. That is required for Chat and streaming API UX.

### 3.3 Provider Agent
- Serves paid Console jobs and rentals first.
- When GPU/CPU would be idle: mine the most profitable coin, auto-convert,
  pay host in ABA.
- Protocol cut on buyback conversion: **12%** (88% to host; 4% to stakers,
  4% to treasury, 4% burn). Conversion is automatic; hosts always earn the
  network asset.
- **Payout by verified shares:** miners connect to the Abakos stratum proxy with
  their ABA address as the login; the proxy relays to the upstream pool (Kryptex,
  auto-exchange to USDT) and counts difficulty-weighted *accepted* shares per
  address. The Agent pays each host proportional to those verified shares, so
  self-reported hashrate cannot inflate a payout.
- Provider Dashboard shows utilization, rentals, add-on earnings, mining
  buyback, connected providers, verified shares, uptime and reputation.

### 3.4 Model registry & AI workloads
Open-weight models only for network-served inference (Llama, Qwen, DeepSeek
and similar). Closed frontier APIs are never falsely claimed. Large models
stay inside one provider's multi-GPU box; no weight sharding across the
public internet in v1.

### 3.5 Current implementation status (Public sandbox live)

Radical transparency is part of the design. Live status: **status.abakos.ai**.

- **Live today (public sandbox):** PoS chain + EVM (id 9721), zero-fee
  transactions, web wallet, public explorer, faucet, on-chain ABA/USDT DEX, and
  the Provider Agent + Dashboard with a real on-chain buyback and payout by
  verified shares. Single-operator for now.
- **In design / not live:** Console (bundles, add-ons, on-chain escrow),
  Developer API, Chat, external validators (decentralization), fiat onramp,
  mainnet.
- Nothing above is a ship-date promise.

## 4. Abakos Chat & Developer API

- **Developer API (Phase 3):** OpenAI-compatible batch embeddings and
  completions that create Console jobs settled in ABA. Open-weight models,
  the same idea as a managed inference API like AkashML.
- **Chat + streaming (Phase 4):** consumer demand on the same rails. Chat
  may later hide crypto on the surface; MVP settlement remains ABA.
  Product markup: **+12%** (4% stakers, 4% treasury, 4% burn); provider net
  matches the Console, then the usual 3% fee applies.

## 5. Economics & token (ABA)

- **Genesis supply:** 10,000,000,000 ABA (fixed), **zero inflation**. No
  provider mining-emission allocation.
- **Illustrative allocation:** Liquidity 32%, Treasury 18%, Ecosystem 15%,
  Reserve 15%, Team 12% (1-year cliff, 3-year linear), Community 8%.
- **Illustrative DEX start:** ~$0.002 (~$20M FDV), staged liquidity seeding.
- **Transaction fees:** **zero** (gasless L1; `eth_gasPrice = 0`). The figures
  below are the protocol *revenue share* on real activity, not gas.
- **Protocol revenue:**
  - Console / API / CPU / storage settlement: **3%** = 1% stakers + 1% burn +
    1% treasury.
  - Idle mining buyback cut: **12%** (88% host, 4% stakers, 4% treasury, 4% burn).
  - Chat / API product markup: **+12%** = 4% stakers + 4% treasury + 4% burn,
    then standard settlement fee.
- **Stablecoin standard:** USDT (BEP20) for pool payouts and the ABA/USDT DEX
  (0.30% swap fee to LPs).
- **Burn:** a burn slice on every revenue source (1% of Console/Marketplace
  settlement; 4% of the idle-mining, Chat and API cuts) permanently removes ABA
  from supply. Zero inflation plus these burns makes ABA net **deflationary**.
- **MVP payments:** ABA wallet. Fiat to ABA onramp post-launch.
- **Fundraising preference:** compute vouchers / grants / strategic capital
  against fixed-supply design, not a public token-sale page.

## 6. Security & trust

- Novel surface: marketplace escrow, Agent buyback pipeline, matching and
  Console tooling. Base Cosmos/Akash lineage reduces reinventing consensus
  from scratch, but **Abakos-specific modules need audit before mainnet**.
- Launch gate: public sandbox (live) → external audit → mainnet + liquidity.
- Honesty policy: status badges distinguish live vs planned; no claim that
  PoUW reward-split is the product.

## 7. Go-to-market (summary)

1. Provider Agent + Dashboard (supply and utilization story).
2. Console templates (demand that fills hardware).
3. API batch, then Chat/streaming.
4. Fiat onramp when UX and compliance justify it.

## 8. Roadmap

Phase numbers match **status.abakos.ai**.

- **Phase 0 (done):** Architecture pivot.
- **Phase 1 (live):** Public sandbox &mdash; PoS chain + EVM, zero-fee, wallet, explorer, ABA/USDT DEX, faucet, Provider Agent + Dashboard.
- **Phase 2:** Console, bundles, add-ons, ABA escrow, idle buyback.
- **Phase 3:** Developer API (batch).
- **Phase 4:** Chat + streaming API.
- **Launch:** Audit, liquidity, mainnet.
- **Post-launch:** Fiat to ABA, broader VPS/storage products.

## 9. Risks

Bootstrap (supply and demand must both show up); oracle and conversion risk
on idle buyback; ABA price volatility for hosts and buyers in a wallet-first
MVP; latency for decentralized inference (hybrid capacity may be labeled
explicitly in early Chat); competition from Akash, Vast.ai, io.net and
others (differentiate on utilization Agent + ABA economics + Chat/API);
legal classification of ABA (counsel before any public sale). Internal
numbered docs under `docs/` may still contain older PoUW wording until
rewritten; prefer this whitepaper and the website for the current thesis.

## 10. References

- Akash Network docs (SDL, providers, IP leases, persistent storage):
  https://akash.network/docs/
- Akash AEP-76 (Burn-Mint Equilibrium / credit card → AKT demand design):
  https://akash.network/roadmap/aep-76/
- Pearl / PoUW background (historical contrast, not Abakos product claim):
  https://pearlresearch.ai/

---

*This document is for information only and is not financial advice or an
offer of securities. ABA parameters are drafts subject to legal and audit
review.*
