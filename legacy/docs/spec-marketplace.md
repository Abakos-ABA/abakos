# Spec · Reward Split + Compute Marketplace + Escrow

Status: Design v0.1 (workstream B). Core differentiation of Abakos vs. Pearl & Gonka. Terms/parameters are starting assumptions.

## 1. Design principle (why this works)

Pearl's weakness: the protocol verifies only that a matmul was *correct*, not that it was *useful*. Statistical matrix "authenticity" checks are trivially bypassable per arXiv 2606.04819.

**Abakos solves this economically, not statistically:** full block rewards exist only when matmul work performed is bound to a **paid escrow job**. Empty mining remains allowed (for chain security) but is made financially unattractive. Thus "useful compute" is the dominant strategy.

## 2. Actors

| Role | Task |
|---|---|
| **Buyer** | orders compute (batch/real-time/training), pays stablecoin or ABA (discounted) into escrow |
| **Miner/provider** | registers a standing listing (models, capacity, price, accepted currencies) and stays active; the matching engine assigns jobs to it automatically (see §6a), it doesn't browse and accept jobs one by one; computes GEMM, produces PoUW proof, produces blocks |
| **Model owner** | registers model weights (hash) in registry |
| **Validators/nodes** | verify blocks + job binding + escrow |
| **Abakos Chat / SDK** | technical buyer frontends (see Doc 05) |

## 3. Model registry (on-chain)

```
ModelRegistryEntry {
  model_id:        bytes32      // unique ID
  weights_hash:    bytes32      // Merkle root of quantized weights
  precision:       enum         // INT8 | FP8 | BF16
  min_vram_gb:     uint16
  owner:           address
  active:          bool
}
```

Jobs reference `model_id`; the PoUW proof binds input matrices to `weights_hash` (see §5). A miner cannot claim to have run "model X" without using its weights.

## 4. Reward split (core mechanism)

```
reward_block = base_subsidy * (FLOOR + (1 - FLOOR) * useful_ratio)
FLOOR = 0.25          // empty mining gets 25%
useful_ratio ∈ [0,1]  // share of block work bound to paid jobs
```

**`useful_ratio` definition:**
```
useful_ratio = matmul_work_bound_to_paid_jobs / total_matmul_work_in_block_PoW
```
- `total_matmul_work` = GEMM tiles/MADs proven in PoW.
- `bound_to_paid_jobs` = the share whose input matrices provably (a) match committed job inputs and (b) are covered by a valid, funded escrow.

Examples:
| Scenario | useful_ratio | reward share |
|---|---|---|
| pure random mining | 0.0 | 25% |
| half paid / half filler | 0.5 | 62.5% |
| fully paid work | 1.0 | 100% |

**Penalty share (unpaid up to 75%): burn** (decision made, see Doc 03) → deflationary, no central pool.

## 5. Anti-gaming: PoW ↔ job binding

The block header commits in addition to Pearl's fields:
```
job_commitment = {
  job_ids:        [bytes32]     // served jobs
  input_roots:    [bytes32]     // Merkle roots of actually computed inputs
  escrow_refs:    [bytes32]     // references to funded escrows
}
```
Verifier checks:
1. For each `job_id`: escrow exists, is **funded**, and not expired.
2. `input_roots` == those committed in the job's `input_commitment` (hash equality).
3. NoisyGEMM inputs of PoW (jackpot derivation) come from exactly these `input_roots`.
4. `weights_hash` of referenced model matches.

> **Open research question (hard):** cryptographically clean binding "the PoW jackpot was produced from *exactly these* job inputs" is the hardest part. Approach: derive jackpot seed from `input_roots` + Plonky2 proof that tiled NoisyGEMM ran on committed inputs. If perfect cryptographic binding is too expensive, security falls back to the **economic** line (escrow payment must exist for useful_ratio > 0), that alone tilts economics against empty mining.

## 6. Job lifecycle (state machine)

```
CREATED ──fund()──► FUNDED ──auto_match()──► ASSIGNED
   │                   │                          │
   │                   │                     compute+prove
   │                   ▼                          ▼
   └──cancel()──►  REFUNDED            PROVEN ──verify()──► SETTLED
                       ▲                          │
                       └────timeout/dispute───────┘
                              (reassign, see §6a, before falling back to REFUNDED)
```

| State | Description |
|---|---|
| CREATED | job created, not yet paid |
| FUNDED | escrow funded (stablecoin or ABA locked) |
| ASSIGNED | matching engine auto-assigned an active, eligible provider (deadline running); no manual accept step |
| PROVEN | output + ZK proof submitted |
| SETTLED | proof ok → provider paid (in the funding currency) + reward share; penalty share burned |
| REFUNDED | cancel before assignment, timeout with no reassignment left to try, or failed verification → buyer refunded |

## 6a. Matching: active listings, not job acceptance

**The provider-facing model is "go active," not "browse and accept."** A provider registers a standing listing once (models served, VRAM/capacity, price per currency, min job size, region) and then simply keeps their node online and idle. The matching engine, not the provider, decides which job goes where and does it automatically the moment a job is `FUNDED`. This removes the two problems a manual accept-or-reject job board has: latency (a job sitting unclaimed while providers aren't looking) and unusable UX for real-time products (nobody can wait for a human to click "accept" while a chat message is pending).

```
Listing {
  provider, model_ids: [bytes32],
  min_vram_gb, capacity_slots: uint,
  price: { currency: enum{STABLE, ABA}, rate: uint }[],   // can list both
  region, min_job_size, active: bool,       // active = online + idle + eligible
  reputation_score: float                    // from §8, read by the matcher
}
```

**Matching rule (default, all job types):** among listings that are `active`, serve the job's `model_id`, have free `capacity_slots`, and accept the buyer's chosen `payment_currency`, select the lowest-price listing **above a minimum reputation floor**. Pure cheapest-price-wins would let an unreliable, unrated new listing win every job it can undercut on; the reputation floor (§8) exists specifically to stop that. Ties break toward higher reputation, then round-robin, to avoid concentrating volume on one provider.

**By job type:**
- **Real-time (Chat, Developer API):** auto-match is not optional here, it's the only mode; there is no "browse and pick a provider" step for a synchronous chat message. Sub-second matching against currently-active listings serving the requested model.
- **Batch jobs:** auto-match is the default. A buyer never has to wait for a provider to notice their job.
- **Hourly rental (self-serve marketplace UI):** buyers can either take the auto-matched cheapest available listing for instant launch, or browse listings and pick a specific one manually (region, exact GPU model, a host they trust). Auto-match is the fast default; manual browsing is an option, not a requirement.
- **Enterprise offtake:** intentionally the exception. Negotiated, manually arranged capacity (Doc 04), not run through the auto-matcher.

**Failure handling:** if the assigned provider misses the deadline or fails verification, the matching engine automatically reassigns to the next-best active listing instead of returning the job to a pool for someone to notice. Only if no eligible active listing exists does the job fall back to REFUNDED. This is a strict improvement over "provider accepts, then may still no-show": reassignment is automatic either way, but there's no accept step to begin with, so there's nothing to abandon.

**What this does not change:** the reward-split and job-commitment mechanics (§4, §5) don't care whether a provider was auto-matched or manually claimed a job, only that a valid proof exists for a funded job. Auto-matching is an application/matching-layer decision, not a consensus rule.

## 7. Escrow

- **Asset:** USDC/USDT, or ABA at a listing-set discount, buyer's choice among whatever the listing accepts. The two legs of a job (payment vs. block-reward subsidy) settle independently: the subsidy leg is always ABA; the payment leg is whichever currency funded the escrow. See Doc 04 §"Settlement currency" for the full mechanic and the fee/burn split by currency.
- **Fee:** 2% per settlement. If funded in stablecoin: 1% treasury (stablecoin) + 1% buyback-and-burn (treasury swaps for ABA on the open market, then burns it). If funded in ABA: 1% treasury (ABA) + 1% burned directly.
- **Deadline/timeout:** if a provider does not deliver on time → the matching engine auto-reassigns to the next-best active listing (§6a); refund to buyer in the funding currency only if no eligible listing remains.
- **Dispute:** verification failed → no payout, refund; miner reputation drops, optional stake slash.
- **Partial delivery (batch):** settle large batches in chunks (milestones) to manage risk/latency.

## 8. Reputation & optional stake

- **Reputation score** per provider from successful/failed jobs → directly read by the matching engine (§6a) as the reputation floor and tie-breaker, not just an informational badge.
- **Optional stake** (ABA) as security for high-value/real-time jobs; slash on non-delivery/fraud.
- Prevents Sybil spam on supply side, and specifically prevents a new, unrated listing from winning volume purely by undercutting price.

## 9. Data structures (overview)

```
Job {
  job_id, buyer, model_id,
  input_commitment: bytes32,
  job_type: enum{BATCH, REALTIME, TRAIN},
  payment_currency: enum{STABLE, ABA},   // buyer's choice, must be accepted by the listing
  payment_escrow: uint,                  // amount in payment_currency
  deadline: timestamp,
  status: enum,
  assigned_miner: address?
}
Proof {
  job_id, miner,
  output_hash: bytes32,
  zk_proof: bytes,
  work_units: uint                // for useful_ratio, independent of payment_currency
}
Settlement {
  job_id, miner_payout, payout_currency,   // = payment_currency
  fee, fee_disposition: enum{BUYBACK_BURN, DIRECT_BURN},  // depends on payment_currency
  buyer_refund, block_reward_share         // always ABA
}
```

## 10. Real-time (chat) vs. batch

- **Batch** (MVP, phase 2; Developer API's batch endpoints land phase 3 on the same infra): latency-insensitive, escrow + async settlement, auto-matched (§6a). Ideal for embeddings/labeling/synthetic data.
- **Real-time** (phase 4, for Abakos Chat *and* the Developer API's streaming endpoint together, not phase 3: they need the same low-latency infra, so they land at the same time): low latency needed → staked/reputed active listings only, auto-matched sub-second (§6a), session escrow with streaming billing; initially **hybrid** (reliable partner GPUs), later decentralized.

## 11. MVP scope (phase 2)

Included: model registry (1 model), batch jobs, stablecoin escrow, the auto-matching engine (§6a, simplified: price + reputation floor, no capacity forecasting yet), verification, settlement, reward split with useful_ratio (simplified binding), "% useful" dashboard.
Later: real-time path, training jobs, stake/slashing, multi-model, non-AI GEMM, smarter matching (latency/region-aware, capacity forecasting).

## 12. Open items (to resolve)

- Cryptographic PoW↔job binding vs. purely economic binding (cost/benefit, §5).
- Measure Plonky2 overhead on FP path.
- Deterministic reproducibility for re-verification (cf. Gonka, fixed seeds).
- Precise measurement of `work_units` (TMADs/tiles) as basis for useful_ratio.
- Anti-collusion: buyer = miner (self-dealing). Mitigation: fee makes self-dealing expensive + minimum third-party demand heuristic.
