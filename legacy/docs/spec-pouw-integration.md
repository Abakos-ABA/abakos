# Spec · PoUW Integration (btcd → Abakos)

> **Phase 0 deliverable (week 1).** Where SHA-256 PoW in btcd is replaced, what Pearl does as reference, and how Abakos builds leaner (fresh btcd + reward split).
>
> **Note on labels below:** this spec also uses `T0`, `T0.5`, `T1`, `T1.5+`, `T2`. Those are **PoUW kernel maturity versions** (plain proof → ZK-optional → production → ZK path → job-bound), a different axis from the delivery **Phase 0–4/Launch** scheme used on the website and in `docs/07-roadmap.md`. Kernel version T0 ships in delivery Phase 0; kernel version T2 ships in delivery Phase 2. The numbers coincide there but are not the same concept.

**References:** [cuPOW paper](https://eprint.iacr.org/2025/685) · [Pearl repo](https://github.com/pearl-research-labs/pearl) (study only, do not fork blindly) · [`docs/17-testnet-plan.md`](17-testnet-plan.md)

---

## 1. Strategy

| Approach | Decision |
|---|---|
| Fork Pearl monorepo | **No**, wrong economics, bad optics, merge burden |
| Fresh **btcd** (ISC) + port PoUW | **Yes**, Pearl/`zk-pow` as reference only |
| License | Abakos code MIT; vendored btcd ISC; Rust/ZK separate (Apache/MIT per crate) |

**Critical path:** `wire` (header + certificate) → `pouw` (verify) → `blockchain/validate` → `mining` → `economics` (reward split).

---

## 2. Vanilla btcd: where SHA-256 PoW lives

| File / package | Function | What happens today |
|---|---|---|
| `wire/blockheader.go` | `BlockHeader` | 80 bytes: version, prevBlock, merkleRoot, **nonce**, timestamp, bits |
| `wire/blockheader.go` | `BlockHash()` | double-SHA256 over header → hash < target |
| `blockchain/validate.go` | `checkProofOfWork()` | `header.BlockHash()` vs. `CompactToBig(header.Bits)` |
| `blockchain/validate.go` | `CheckBlockSanity()` | calls `checkProofOfWork` |
| `mining/cpuminer.go` | CPU miner | increments **nonce** until hash < target |
| `chaincfg/params.go` | `PowLimit`, genesis | network-specific difficulty |
| `btcutil/block.go` | block wrapper | thin wrapper around `wire.MsgBlock` |

**Abakos replaces:** the semantics of "brute-force nonce → SHA-256 hash" with "NoisyGEMM + Blake3 jackpot + ZK/plain proof → certificate."

---

## 3. Pearl: what they changed (reference)

Pearl vendors btcd **inline** under `pearl/node/` (no separate Go module). Key deviations:

### 3.1 Block header (`node/wire/blockheader.go`)

- **Nonce removed** (80 → 92 bytes effectively with commitment).
- **`ProofCommitment`** added (32 bytes), binds certificate to header chain.
- `BlockHash()` = double-SHA256 over version, prevBlock, merkleRoot, timestamp, bits, **ProofCommitment** (not over nonce).

### 3.2 Block certificate (`node/wire/`: `MsgHeader`, `CertificateV1/V2`)

- PoUW proof **not** in 80-byte header, but as **certificate** at block start (before transactions).
- `MsgBlock` → `MsgHeader` = header + certificate.
- `BlockCertificate()` interface; V1/V2 with `PublicData` + `ProofData` (ZK via Rust FFI).

### 3.3 Validation (`node/blockchain/validate.go`)

```go
func checkProofOfWork(header *wire.BlockHeader, cert wire.BlockCertificate,
    powLimit *big.Int, flags BehaviorFlags) error {
    // ... bits/target sanity (like btcd) ...
    if cert == nil {
        return ruleError(ErrCertificateMissing, "certificate is missing")
    }
    if flags&BFNoPoWCheck != BFNoPoWCheck {
        if err := zkpow.VerifyCertificate(header, cert); err != nil {
            return ruleError(ErrHighHash, ...)
        }
    }
    return nil
}
```

**Important:** Pearl does **not** check `header.BlockHash() < target`. Difficulty is in **ZK/GEMM verification** (`verify_zk_proof_v2` in `zk-pow`).

### 3.4 Verifier (`node/zkpow/verify.go`)

- Go package with `//go:build zkpow` + **cgo** → `zk-pow/bindings/go/libzk_pow_ffi.a`.
- `VerifyCertificate(header, cert)`: jackpot, Merkle, matrix range, difficulty.
- Stub build without GPU/ZK: `zkpow_stub.go`.

### 3.5 Mining (`node/zkpow/miner.go`, `miner/` Python)

- External vLLM miner produces shares → certificate.
- Node-side: coordination via RPC, no longer nonce loop.

### 3.6 What Pearl does **not** have (Abakos delta)

- No **reward split** (`useful_ratio`).
- No on-chain **escrow** / job binding in PoW check.
- No `% useful` field in block/explorer (only implicitly 0%).

---

## 4. Abakos target architecture

```
┌─────────────────────────────────────────────────────────────┐
│  wire.BlockHeader  (+ ProofCommitment, optional useful_meta) │
│  wire.WorkCertificate  (PoUW proof blob)                   │
└──────────────────────────┬──────────────────────────────────┘
                           │
              ┌────────────▼────────────┐
              │  pouw.WorkVerifier      │  ← interface (Go)
              │  impl: CPU stub / ZK FFI │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │  blockchain.checkPoUW     │  (fork validate.go)
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │  economics.BlockReward  │  useful_ratio ∈ [0,1]
              └─────────────────────────┘
```

### 4.1 Go interface (implemented in `node/pouw/`)

```go
type WorkVerifier interface {
    Verify(header *Header, proof []byte) error
    WorkUnits(proof []byte) uint64
}
```

- `Header` = Abakos header snapshot (independent of btcd fork state).
- `proof` = serialized certificate (format T0: plain; T0.5+: ZK).
- `WorkUnits` = GEMM tiles / normalized work for explorer hashrate.

### 4.2 Abakos header fields (planned)

| Field | Type | Purpose |
|---|---|---|
| Standard btcd fields | n/a | version, prevBlock, merkleRoot, timestamp, bits |
| `ProofCommitment` | 32 B | like Pearl, certificate commit |
| `UsefulRatio` | uint16 (bps) | share of paid work in block (T2+) |
| `JobRoot` | 32 B (optional) | Merkle over escrow job IDs in block |

*T0:* `UsefulRatio` hardcoded `0` in coinbase metadata or stub; full on-chain binding in T2.

### 4.3 Certificate (MVP)

| Phase | Content |
|---|---|
| **T0** | Plain proof: matrix commits, jackpot hash, difficulty, small Merkle proof |
| **T0.5** | Plonky2/STARKy like Pearl `zk-pow` (port or FFI) |
| **T2** | + escrow job reference, model hash from registry |

---

## 5. File mapping: btcd → Abakos fork

*("Priority" below is P0–P2 implementation urgency, not a delivery Phase;
see `docs/07-roadmap.md` for Phase 0–4/Launch.)*

| btcd (upstream) | Abakos action | Priority |
|---|---|---|
| `wire/blockheader.go` | remove nonce, add `ProofCommitment` | P0 |
| `wire/msgblock.go` | `MsgHeader` + certificate before txs | P0 |
| `wire/protocol.go` | new `ServiceFlag`, magic bytes `ABA*` | P0 |
| `blockchain/validate.go` | `checkProofOfWork` → `checkProofOfUsefulWork` | P0 |
| `blockchain/error.go` | `ErrCertificateMissing`, PoUW errors | P0 |
| `mining/cpuminer.go` | delegate to `pouw` / external miner | P1 |
| `chaincfg/genesis.go` | Abakos testnet genesis | P0 |
| `chaincfg/params.go` | `PowLimit`, subsidy, halving from `node/params` | P0 |
| `server.go` | `--mine` flag → PoUW backend | P1 |
| Block subsidy / coinbase | `economics.BlockReward(base, useful_ratio)` | P1 |
| Rest (mempool, peer, rpc) | vanilla btcd, minimal diff | P2 |

**Narrow fork:** only touch P0–P1; no XMSS, no Pearl-specific RPC.

---

## 6. Vendoring plan

*(Steps A/B below are implementation sub-steps, not delivery Phases; see
`docs/07-roadmap.md` for the Phase 0–4/Launch scheme used everywhere else.)*

### Step A (now: `node/go.mod`)

```bash
cd node
go get github.com/btcsuite/btcd@v0.24.2
go mod tidy
```

- btcd as **Go module dependency**; `abkd` imports `chaincfg`, `wire` to verify toolchain.
- No copy-paste of entire btcd tree into repo (too large for git).

### Step B (before first public testnet)

- Fork `github.com/rexmarlon/btcd` (or `abakos-chain`) with P0 patches.
- `go.mod`: `replace github.com/btcsuite/btcd => github.com/rexmarlon/btcd v0.x.x-abakos.1`
- Or: btcd subtree under `node/vendor/btcd/` + `replace` (only if audit/license requires).

### CI

GitHub Actions (`node/`) runs `go vet` + `go test`; btcd dep resolved there.

---

## 7. Simnet / local 2-node test (Phase 0, week 1)

| Step | Command / artifact |
|---|---|
| 1 | `abkd --simnet --datadir=./data/node1` |
| 2 | `abkd --simnet --datadir=./data/node2 --connect=127.0.0.1:18555` |
| 3 | Node1: `--generate` with SHA-256 stub **or** `pouw/mock` |
| 4 | Log: `PoUW verify OK`, `useful_ratio=0`, `reward=25%` |

*Week 1 exit:* two nodes connect; one block (even with placeholder PoW).

---

## 8. Abakos vs. Pearl: integration differences

| Topic | Pearl | Abakos |
|---|---|---|
| PoW check | ZK FFI only | interface; CPU plain T0, ZK T0.5 |
| Useful work | not enforced | `useful_ratio` → reward split + burn |
| Block reward | 100% with valid PoUW | `25% + 75% × useful_ratio` |
| Certificate | V1/V2 complex | start plain; ZK later |
| Miner | vLLM required | batch GPU + CPU CI stub |
| Explorer | standard | **% useful** mandatory metric |

---

## 9. Open items (T0 → T1)

1. **Exact certificate wire format**: in `docs/spec-pouw-kernel.md` (week 2).
2. **useful_ratio source**: coinbase OP_RETURN vs. header field vs. escrow events.
3. **Difficulty retarget**: Pearl algorithm 1:1 or simplified for testnet?
4. **FFI boundary**: rewrite Rust `zk-pow` vs. Pearl code as reference (check license).

---

## 10. Next commits (order)

1. ✅ this document
2. ✅ `node/pouw/`: `WorkVerifier`, mock, SHA-256 stub
3. ✅ `node/chaincfg/`: testnet genesis constants
4. ✅ `go.mod` btcd dep; `abkd` builds against simnet params
5. ✅ Phase 0 local chain: `node/chain/` + `abkd --simnet --mine`
6. ✅ fork patch: `wire/` + `consensus/` (full btcd `replace` next)
7. ✅ CPU GEMM spike (`pouw/gemm.go`) + 2-node simnet
8. ⬜ btcd `replace` fork + `netsync` integration

---

*Status: Phase 0 week 1 · Abakos pre-testnet*
