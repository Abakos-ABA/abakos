# Spec · Reward Split Implementation

Status: **Implemented in Phase 0 simnet** (2026-07). Full marketplace escrow still Phase 2.

## 1. Goal

Make the Abakos claim *“empty mining earns 25%, paid work earns 100%”* **consensus-enforced**, not honor-system CLI flags.

## 2. Formula (integer, consensus-critical)

```
reward = base_subsidy * (FLOOR_BPS*10000 + (10000-FLOOR_BPS)*useful_bps) / 100_000_000
FLOOR_BPS = 2500   // 25%
useful_bps ∈ [0, 10000]
```

| useful_bps | multiplier | example base=50e8 |
|---|---|---|
| 0 | 25% | 12.5e8 |
| 5000 | 62.5% | 31.25e8 |
| 10000 | 100% | 50e8 |

Unrewarded remainder is **burned** (never created in the coinbase).

Code: `node/economics/CoinbaseSubsidy`, `ValidateCoinbaseSubsidy`.

## 3. Job commitment (economic binding, Phase 0)

Until the marketplace ships, `useful_bps > 0` requires:

1. `header.ProofCommitment` = 32-byte **job ID**
2. Job exists in `jobs.Registry`
3. Job is **funded** and **not expired**

`useful_bps == 0` requires `ProofCommitment == 0` (empty mining).

Code: `node/jobs/registry.go`, `consensus.CheckJobCommitment`.

> Cryptographic PoW↔input binding remains an open research item (`docs/spec-marketplace.md` §5). Phase 0 security is **economic**: you cannot claim useful_ratio without a funded job stub.

## 4. Where enforcement runs

| Path | Check |
|---|---|
| In-memory simnet (`chain.Chain.validate`) | PoUW + job commitment |
| btcd PoUW verifier (`fork.RegisterPoUWVerifier`) | PoUW + job commitment |
| btcd coinbase connect (`blockchain/validate.go`) | Exact coinbase == reward-split (Abakos versions) |
| btcd `blockNode` (`blockchain/blockindex.go`) | Persists `UsefulRatioBps` + `ProofCommitment` |
| Miner (`p2p.Server.mineNext`, `chain.MineNext`) | Sets adjusted subsidy + demo job when useful>0 |

## 5. CLI

```
abkd --simnet --mine --useful-bps 0      # empty → 25% coinbase, no job
abkd --simnet --mine --useful-bps 10000  # auto-registers demo job "simnet-paid"
```

## 6. Tests

- `economics.TestCoinbaseSubsidy`
- `jobs.TestValidateCommitment_*`
- `consensus.TestCheckJobCommitment_Enforced`
- `consensus.TestCheckCoinbaseSubsidy_Enforced`
- `chain.TestUsefulWithoutJobRejected`
- `chain.TestUsefulRatioReward` (requires job commitment)

## 7. Not yet (Phase 1–2)

- [ ] On-chain marketplace escrow (replace in-memory registry)
- [ ] Multi-job Merkle commitment in header
- [ ] Halving wired into Abakos emission (still using btcd base subsidy for coinbase sats)
- [ ] Public testnet genesis finalization
