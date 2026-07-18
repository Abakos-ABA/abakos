# Spec · PoUW kernel (T0 CPU / T1 GPU)

> Certificate wire format and NoisyGEMM parameters for Abakos testnet.
>
> **Note on labels:** `T0`, `T0.5`, `T1`, `T1.5+` below are **PoUW kernel
> maturity versions** (CPU spike → plain certificate → production GPU → ZK
> path), a different axis from the delivery **Phase 0–4/Launch** scheme used
> on the website and in `docs/07-roadmap.md`. Kernel T0 ships in delivery
> Phase 0; that's a coincidence of numbering, not the same concept.

**Reference:** [cuPOW eprint 2025/685](https://eprint.iacr.org/2025/685) · Pearl `zk-pow/` (study only)

---

## 1. T0 (shipped): CPU GEMM spike

Implementation: `node/pouw/gemm.go` · verifier flag `--verifier gemm`

| Parameter | T0 value |
|---|---|
| Matrix dims | 8 × 8 × 8 INT8 |
| Value range | [−64, 64] |
| Proof | 4-byte nonce (brute-force) |
| Jackpot | Blake3(XOR-accumulated tile sums + light noise) |
| Difficulty | Bitcoin compact `bits` (header) |
| Block ID | Blake3(header ‖ jackpot) |

**Not yet:** Merkle proofs, rank chunks, ZK, model-hash binding.

---

## 2. T0.5: Plain certificate on wire

See `node/wire/`, certificate appended after Abakos header (110 bytes).

```
BlockHeader (fixed)
CertificateLength uint64
CertificateBytes  (plain PoUW proof)
Height            uint64   (T0 simnet only; removed in btcd fork)
```

Plain certificate v1 (planned):

| Field | Size | Notes |
|---|---|---|
| `version` | 1 B | = 1 |
| `nonce` | 4 B | mining attempt |
| `jackpot` | 32 B | Blake3 output |
| `tile_proof` | var | Merkle path to recomputed tile (T0.5) |

Header `ProofCommitment` = Blake3(certificate_prefix).

---

## 3. T1: Production INT8 PoUW

Align with cuPOW §3 (Pearl mainnet subset):

- Larger tiles (GPU), rank-R chunking
- Blake3 matrix commitments
- Structured noise from commitment
- Plain verify on node; optional ZK in T1.5

---

## 4. T1.5+: ZK path

- Rust FFI / `zk-pow`-style verifier (Plonky2)
- `node/consensus` calls verifier; build tag `zkpow`
- Pearl reference: `pearl/node/zkpow/verify.go`

---

## 5. Abakos deltas vs Pearl

| Topic | Pearl | Abakos |
|---|---|---|
| Useful work | Not enforced | `useful_ratio_bps` in header → reward split |
| Proof in header | No (certificate) | Same |
| Verify | ZK required | Plain first, ZK optional |
| Miner | vLLM | Batch GPU + CPU CI |

---

*Status: T0.5 planning · see `node/pouw/README.md`*
