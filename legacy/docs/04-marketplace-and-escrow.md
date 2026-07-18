# 04 · Compute Marketplace & Escrow

The **core differentiator** vs. Pearl: a working on-chain market that connects buyers and GPU providers and settles payment atomically.

> **Important, no proprietary stablecoin:** Abakos does **not** issue its own stablecoin. Creating a real stablecoin would require reserves/collateral (capital) + regulation, and that is **not** our plan. We use **existing** stablecoins (USDC/USDT) as the payment rail (integration costs dev work only, no capital), optionally ABA with a discount, and fiat (card) in Abakos Chat via a payment provider (e.g. Stripe). "Stablecoin escrow" means: we accept USDC/USDT; we do not mint them.

## Job flow

1. **Order:** buyer selects a model from the registry, uploads a batch (e.g. 1M embeddings) or opens an inference session, picks a **settlement currency** (stablecoin, or ABA at a discount, see below), and locks payment in **escrow**.
2. **Matching (automatic):** the matching engine assigns the job to the cheapest active, eligible listing above a minimum reputation floor, instantly. Providers don't browse a pool and accept jobs; they register a standing listing once and stay active, see spec-marketplace.md §6a for the full mechanic.
3. **Computation:** the assigned provider computes → produces **output + PoUW/ZK proof** binding inputs to the model hash.
4. **Verification:** node checks proof + job reference.
5. **Settlement (atomic):** escrow pays the miner in whichever currency the buyer funded it with, **and** the miner separately receives the ABA block-reward share (always ABA, unaffected by settlement currency). Dashboard counts this compute as "useful" either way.

Result: when the buyer pays stablecoin, they pay **below market price** because the miner also earns ABA on top → the "2-for-1" economics. When the buyer instead pays in ABA (see §"Settlement currency" below), the discount comes from the provider's side, and the miner's payout for that job is ABA end to end, not stablecoin.

## Settlement currency: stablecoin vs. ABA (important, this is not a detail)

Every job has **two independent legs**: the **job payment** (what the buyer owes the provider for the work) and the **block-reward subsidy** (what the protocol mints to whoever mined the block, per Doc 03's reward-split rule). The subsidy leg is **always ABA**, regardless of how the job was paid. The job-payment leg is where the buyer has a choice:

| Buyer pays in | Provider receives (job payment) | Provider receives (subsidy, same job) | Net for provider |
|---|---|---|---|
| Stablecoin (default) | Stablecoin | ABA | Mixed: price-stable job income + ABA upside |
| ABA (discounted) | ABA | ABA | 100% ABA for that job, more token-price exposure, won the job on price |

**Why offer an ABA discount at all?** Because it creates real, usage-linked buy pressure: a buyer who wants the discount has to acquire ABA on the open market to pay for a real compute job, not to speculate. That is a genuine utility-demand mechanism for the token, separate from (and additive to) the mining subsidy and the fee burn below.

**This is a provider choice, not a forced mechanic.** Each listing declares which settlement currencies it accepts: stablecoin only, ABA only, or both. Providers who want zero token-price exposure simply don't list ABA as an accepted currency. Providers who want ABA exposure (or want to win price-sensitive buyers) opt in and set their own discount.

**Fee handling by currency** (2% marketplace fee either way, see Doc 03):
- **Paid in stablecoin:** 1% to treasury (stablecoin, funds operations); 1% is periodically used to **buy ABA on the open market and burn it** ("buyback-and-burn"). This is how stablecoin-denominated volume still contributes to ABA deflation without pretending you can burn a stablecoin.
- **Paid in ABA:** 1% to treasury (as ABA); 1% burned directly, no market operation needed.

Reward-split eligibility (`useful_ratio`, Doc 03/spec-reward-split-impl) does not care which currency funded the job, only that it was funded. Paying in ABA counts exactly the same as paying in stablecoin for "useful" accounting.

## Job types

| Type | Latency | Example | Phase priority |
|---|---|---|---|
| Batch inference | non-critical | embeddings, classification, labeling | MVP (phase 2), API batch endpoints land phase 3 |
| Real-time inference | critical | Abakos Chat, API streaming | phase 4 (both land together, same real-time infra) |
| Fine-tuning / training | non-critical | LoRA, full FT | phase 3–4 |
| Non-AI GEMM | non-critical | simulation, bioinformatics | phase 4 |

## Provider side: active listings, not job acceptance

A provider sets up a listing once (models served, capacity, price per currency, region) and keeps their node online and idle. That's the whole provider-side interaction for standard jobs. The matching engine picks the job for them; they don't pick jobs. This matters for real-time jobs (Chat, Developer API) specifically: there is no acceptable UX where a chat message waits for a human to click "accept," so auto-matching isn't an optimization there, it's the only workable design. For hourly rental on the self-serve marketplace UI, a buyer can still browse and manually pick a specific listed GPU instead of taking the auto-matched cheapest one, if they want control over exact hardware or region. Full mechanic, including the reputation-floor rule that stops pure price-undercutting: **spec-marketplace.md §6a**.

## Escrow design

- **Asset:** stablecoin (USDC/USDT) or ABA, buyer's choice from what the listing accepts (see settlement currency above).
- **Dispute/timeout:** if the assigned provider does not deliver on time or verification fails → the matching engine auto-reassigns to the next-best active listing; escrow only returns to the buyer, in the same currency it was funded with, if no eligible listing remains. The provider that failed may lose reputation/stake share.
- **Reputation:** provider score from successful jobs → read directly by the matching engine as a floor and tie-breaker, not just a display badge.

## Data structures (sketch)

```
ModelRegistryEntry { model_id, weights_hash, precision, min_vram, owner }
Listing { provider, model_ids, capacity_slots, price_by_currency, region, active, reputation_score }
Job { job_id, buyer, model_id, input_commitment, payment_currency, payment_escrow, deadline, status, assigned_provider }
Proof { job_id, provider, output_hash, zk_proof, useful_ratio }
Settlement { job_id, provider_payout, buyer_refund, block_reward_share }
```

## Solving the chicken-and-egg problem

- **Supply first:** 1–2 neocloud partners + solo miners with a simple installer.
- **Bootstrap demand:** ecosystem pool funds first batch jobs & Abakos Chat free credits.
- **Reference case** with one partner (like Pearl↔Together, but as open SDK instead of exclusive deal).
