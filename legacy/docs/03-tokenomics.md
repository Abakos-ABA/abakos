# 03 · Tokenomics

> ⚠️ **DEPRECATED / HISTORICAL.** This note describes the old btcd Proof-of-Useful-Work design (2.1B supply, 70% mining emission, halving-style block reward). It does **not** reflect the current Abakos model. For the live tokenomics — 10B fixed supply, **zero inflation**, 3% settlement fee (1% staker / 1% burn / 1% treasury), 10% idle-mining buyback cut (90% host / 5% staker / 5% treasury), Chat +10% markup (4% staker / 3% treasury / 3% burn) — see [`litepaper.md`](litepaper.md) and [`whitepaper.md`](whitepaper.md).

## Key facts

- **Token:** `ABA`
- **Max supply:** 2,100,000,000 ABA (like Pearl → market recognition)
- **Block time:** ~120 s (start)
- **Start emission:** ~50,000 ABA/h, halving-style decline (Bitcoin-style)

## Distribution

| Bucket | Share | Vesting / note |
|---|---|---|
| Mining emission | 70% | over years, halving-style |
| Treasury / development | 10% | 4 yr vesting |
| Team | 8% | 1 yr cliff, 4 yr vesting |
| Liquidity & listing | 7% | DEX pools + CEX market-making (see Doc 12) |
| Ecosystem / grants | 5% | researchers, early buyers, Abakos Chat credits |

## Reward formula

```
reward_block = base * (0.25 + 0.75 * useful_ratio)
```

See Doc 02 (architecture) for `useful_ratio`. The unpaid "penalty share" for empty mining (up to 75%) is **burned** (✅ decision): deflationary, clean, no central pool. Changeable via governance later.

## Protocol fees

- **Marketplace fee:** 2% on every compute trade, split by settlement currency (buyer's choice, see Doc 04):
  - Paid in stablecoin: 1% → treasury (stablecoin, operations); 1% → **buyback-and-burn** (treasury periodically buys ABA on the open market with this share, then burns it). This is how stablecoin-denominated volume still deflates supply, without pretending a stablecoin itself can be burned.
  - Paid in ABA: 1% → treasury (as ABA); 1% → burned directly (no market operation needed).
- **Abakos Chat margin:** markup on raw inference cost (see Doc 05).

## Two separate money flows (important!)

1. **Subsidy** = token block reward (volatile, price-dependent).
2. **Revenue** = marketplace fee + chat margin, **normally stablecoin** (price-independent). When a buyer opts to pay in ABA for the discount (see Doc 04), that specific job's fee is collected in ABA instead, and gets burned directly rather than routed through the stablecoin buyback. Revenue accounting tracks both, but treasury runway planning (Doc 12) assumes the stablecoin share, since ABA-denominated volume is deliberately optional and cannot be relied on for fixed costs.

Keep these strictly separate, technically *and* legally (see Doc 10).

## Token utility

- **Discounted payment for compute / Abakos Chat.** Buyers can pay in ABA instead of stablecoin for a discount set by the provider/listing. This is real, usage-linked buy pressure: to use the discount, a buyer has to acquire ABA to pay for actual work, not to speculate. Providers who accept ABA payment are then paid in ABA for that job (see Doc 04); it is a listing-level opt-in, not forced on providers who want price-stable income.
- Mining reward (the block-reward subsidy leg, always ABA, independent of how the job itself was paid).
- Optional: staking for job priority / miner reputation boost.
- Optional: governance (later).

## Anti-speculation hygiene

- Clear utility before big marketing.
- No anonymous team dumping (vesting transparent on-chain).
- "% useful compute" as honest north-star metric instead of price hype.

## Financing & treasury

Budget, runway, funding sources, and listing plan: see **[`docs/12-funding-and-treasury.md`](12-funding-and-treasury.md)**. In short: treasury (10%) + liquidity & listing (7%) cover development and listing in tokens; early fiat need (~$0.8–1.5M) comes from pre-seed + strategic partner.
