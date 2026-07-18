# Abakos (ABA): Litepaper

> Public-facing overview for builders, providers and investors.

**Tagline:** *Hardware that stays fully used.*

---

## TL;DR

Abakos is a **Proof-of-Stake compute network** (an Akash-based Cosmos fork) built so hardware earns the maximum it can. It runs the product suite Akash proved, the **Console** for deploys, **Abakos Chat**, and an OpenAI-compatible **API**, on its own chain. Buyers deploy **resource bundles** (CPU + RAM + disk, optional GPU) plus optional add-ons (persistent storage, IP lease) through the **Console**, paid from an **ABA wallet**. When GPU or CPU capacity would sit idle, a **Provider Agent** mines the most profitable coin, auto-converts the proceeds into ABA, and pays the host. Providers are not paid by minting ABA for compute.

## The problem

- AI and cloud workloads need cheap, available compute, still concentrated in a few hyperscalers.
- Decentralized rental networks (Akash, Vast.ai and similar) make self-serve rental real, but **idle GPU/CPU hours are often wasted**.
- Mining-only networks pay hosts whether or not anyone bought useful capacity, which dilutes token value.
- Fiat-credit Consoles improve UX, but Abakos starts simpler: **ABA wallet settlement first**, fiat to ABA later.

## The Abakos solution: three pillars

1. **Full utilization.** Rent CPU, RAM, GPU and storage via the Console when there is demand. Idle-mine GPU and CPU into ABA when there is not. Storage and RAM earn on rental only.
2. **Own PoS chain + marketplace rails.** Fork open Akash-style modules onto Abakos so ABA is the settlement and staking asset, with native fee capture. Listings are always bundles; GPU, persistent storage and IP leases are priced add-ons.
3. **Demand surfaces.** The Console, Developer API and Abakos Chat all fund the same escrow and settlement path.

## How it works (in one paragraph)

A buyer deploys from a template or funds a batch job, locking ABA in escrow against a base slice (CPU + RAM + ephemeral disk) and any add-ons (GPU, persistent volume, dedicated IP). The Console auto-matches the cheapest qualified active provider. The Provider Agent serves the rental or job. If GPU or CPU capacity would otherwise be free, the Agent mines the most profitable coin, takes a 10% protocol cut (90% to the host), auto-converts to ABA, and pays the host. Settlement releases ABA to the provider; the settlement fee is 3% (1% staker, 1% burn, 1% treasury). ABA has zero inflation: validators and stakers are paid from protocol fees plus the staker share of the mining and Chat cuts, never from minting.

## Token (ABA) & value accrual

- **Utility:** pay for compute and add-ons; receive earnings (jobs or idle buyback); stake for validators; later governance.
- **MVP settlement:** ABA wallet only. Fiat to ABA (card purchase that market-buys ABA) is post-launch, not MVP.
- **Fees:** 3% on Console / API / rental settlement (1% staker + 1% burn + 1% treasury). Idle mining buyback cut 10% (90% host, 5% stakers, 5% treasury). Chat adds a +10% product markup (4% stakers, 3% treasury, 3% burn); provider net matches the Console before the 3% fee.
- **Supply:** **10B ABA** fixed at genesis, **zero inflation** (deflationary via fee burns). No mining-emission bucket for providers. Illustrative allocation: Liquidity 32%, Treasury 18%, Ecosystem 15%, Reserve 15%, Team 12% (1y cliff, 3y linear), Community 8%.
- **Illustrative DEX start:** about $0.002 (~$20M FDV), with meaningful pool depth rather than dumping the full liquidity bucket at once.

## Who buys / who supplies

- **Buyers:** startups, indie developers, data teams, enterprises (offtake), everyday users via Chat.
- **Suppliers:** independent hosts and data-center partners running the Provider Agent and Dashboard.

## Differentiation

| | Akash | Vast.ai / io.net | **Abakos** |
|---|---|---|---|
| Deploy Console + templates | ✓ | partial | **✓ (bundles + add-ons)** |
| Chat + OpenAI-style API | ✓ (Chat, AkashML) | ✗ / limited | **✓ planned** |
| Idle GPU/CPU still earns | only while serving inference | usually wasted | **✓ mine best coin → ABA** |
| Settlement asset | AKT or fiat credits | fiat | **ABA wallet first** |
| Provider token inflation for compute | no | varies | **no** |

## Roadmap

Phase numbers match **status.abakos.ai**.

- **Phase 0:** Architecture pivot (PoS fork design, Provider Agent spec, ABA wallet economics).
- **Phase 1:** Public testnet, explorer, Provider Agent + Provider Dashboard.
- **Phase 2:** Console (templates, bundles, persistent storage, IP leases), ABA escrow, idle buyback pipeline.
- **Phase 3:** Developer API (batch).
- **Phase 4:** Abakos Chat + API streaming.
- **Launch:** Audit, liquidity seeding, mainnet.
- **Post-launch:** Fiat to ABA onramp, broader storage/VPS surfaces.

## Status & contact

Website and waitlist are live. Public PoS testnet, the Console, API and Chat are not live yet. Continuously updated status: **status.abakos.ai**.

CTA: **join the waitlist** · **become a provider** · **partner / invest** · **Discord** (https://discord.gg/zBxNvdMjtM).

*Disclaimer: Litepaper for information only; not financial advice or a securities offer. Parameters are drafts subject to legal and audit review.*
