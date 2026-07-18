# 17 · Testnet Plan (Master Plan)

> **Strategic decision (June 2026):** First a **running PoUW Abakos testnet** with reward split and public "% useful" metric. **Then** real products on top: marketplace → developer API → Abakos Chat. No centralized "preview" GPU proxy as the main public product.

Timeframes: guidelines for **1–2 full-time developers + GPU access**. Shorter with 3–4 people in parallel.

---

## 1. Definition of Done: "Public testnet live"

The testnet counts as **launched** when an outsider without team help can:

| # | Criterion |
|---|---|
| 1 | build `abkd` + miner client from GitHub and connect to public seed |
| 2 | produce or help produce a block with **matmul PoUW** (NoisyGEMM + verification) |
| 3 | see hashrate, blocks, and **`% useful compute`** on [explorer.abakos.ai](https://explorer.abakos.ai) (or equivalent) |
| 4 | understand: empty mining = 25% reward, paid jobs = up to 100% |
| 5 | get testnet ABA via faucet (mining rewards + faucet for gas) |

**Not required for launch:** marketplace, API, chat, mainnet, CEX.

---

## 2. Target picture by phase

```
Phase 0 Foundation          → local block, PoUW verified
Phase 1 Public testnet      → P2P, explorer, faucet, incentives, empty mining visible
Phase 2 Marketplace (batch) → escrow, jobs, settlement, useful_ratio > 0 via real jobs
Phase 3 Developer API       → OpenAI shape routes batch jobs into testnet
Phase 4 Abakos Chat         → real-time (hybrid ok), only when batch stable
        ↓
   Audit → Mainnet (Launch)
```

**Product order on testnet (fixed):**

1. **Explorer + dashboard** (with Phase 1)
2. **Compute marketplace** (batch, escrow)
3. **Developer API** (`api.abakos.ai` → testnet jobs)
4. **Abakos Chat** (last)

---

## 3. Workstreams (parallelizable)

| Stream | Owner skill | Repo | Dependency |
|---|---|---|---|
| **W1 Chain** | Go, btcd | `node/` | n/a |
| **W2 PoUW** | CUDA/C++, ZK | `pouw/` | W1 (verifier interface) |
| **W3 Miner** | Go + GPU | `miner/` | W1, W2 |
| **W4 Marketplace** | Go, on-chain | `marketplace/` | W1 |
| **W5 Explorer** | web | `explorer/` | W1 (RPC/indexer) |
| **W6 Infra** | DevOps | server, CI | W1 |

Critical path: **W1 → W2 → W3 → Phase 1**, then **W4 → Phase 2**.

---

## 4. Phase 0: Foundation (weeks 1–6)

### Goals
- integrate `btcd` as vendor/fork in `node/`
- Abakos genesis + `params/` (already in `node/params/`)
- PoUW kernel spike: produce & verify one block locally
- reward split in block-reward logic (even if `useful_ratio = 0` first)

### Deliverables

| Deliverable | Details |
|---|---|
| `abkd` builds | `go build ./cmd/abkd`, connects to local simnet |
| genesis file | chain ID, test allocations, no mainnet money |
| PoUW INT8 MVP | Blake3 jackpot + difficulty; ZK optional in Phase 0.5 |
| `economics` wired | `RewardForUsefulRatio()` in block subsidy |
| CI green | existing `economics_test.go` + new integration tests |

### Technical steps (order)

1. **Study Pearl + btcd**: which files replace SHA-256? where block header?
2. **Vendor btcd**: minimal: P2P, mempool, block validation, wallet RPC
3. **PoUW interface** in Go:
   ```go
   type WorkVerifier interface {
       Verify(header *BlockHeader, proof []byte) error
       WorkUnits(proof []byte) uint64
   }
   ```
4. **pouw/spike**: CUDA NoisyGEMM (cuPOW paper §3), CPU fallback for CI
5. **Local single-node test**: `abkd --mine` produces 10 blocks
6. **Reward-split stub**: `useful_ratio` hardcoded 0/1 for unit tests

### Phase 0 exit criterion
> Demo video: terminal shows `abkd` mined block N, log shows PoUW verify OK + reward at 25% (useful=0).

---

## 5. Phase 1: Public testnet (weeks 7–10)

### Goals
- public seed nodes (at least 3)
- faucet + testnet ABA
- explorer with **% useful compute** (initially 0%, honest)
- miner installer (Docker or 1-script) for NVIDIA
- incentive program documented

### Deliverables

| Component | Spec |
|---|---|
| **Seed nodes** | `seed1.testnet.abakos.ai` …, ports, bootstrap peers |
| **Faucet** | web + API, rate-limit, captcha, Discord link |
| **Explorer** | blocks, difficulty, miner addresses, **useful_ratio per block**, 24h % useful |
| **Miner README** | HW requirements, expected reward, explorer link |
| **Testnet docs** | `docs/testnet-guide.md` (join, mine, troubleshoot) |

### Model registry (minimal)
- **1 reference model** on-chain (e.g. small INT8 model, fixed `weights_hash`)
- **No** real inference jobs yet; preparation for Phase 2 only

### Incentives (testnet)

| Audience | Incentive |
|---|---|
| Miners | testnet ABA (mining + bonus pool from treasury test alloc) |
| Community | leaderboard "useful compute" (once Phase 2) |
| Researchers | grants from ecosystem test alloc (small, documented) |

### Phase 1 exit criterion
> Outsider mines on testnet; explorer shows their address; faucet works; % useful = 0% with clear explanation why.

---

## 6. Phase 2: Marketplace batch (weeks 11–16)

### Goals
- first **paid** (test) job runs through escrow → compute → settlement
- `useful_ratio > 0` in real blocks
- dashboard jumps from 0% to measurable value

### MVP scope (from `spec-marketplace.md` §11)

**Included:**
- model registry (1 model)
- job type: **BATCH** only (embeddings, classification)
- escrow: testnet USDC (wrapped/faucet) **or** ABA test escrow (simpler for v1)
- states: CREATED → FUNDED → ASSIGNED → PROVEN → SETTLED / REFUNDED
- reward split with **economic** job binding (cryptographic perfection optional)
- burn of penalty share (empty mining)

**Not included:**
- real-time/streaming, training, stake/slashing, multi-model

### Off-chain components

```
marketplace/
  indexer/     # reads chain events, job status API
  matcher/     # assigns FUNDED jobs to miners (simple: first-claim)
  executor/    # optional: team node runs reference jobs (bootstrap)
```

### Bootstrap demand (important)
Without buyers, `useful_ratio = 0`. Plan:

1. **Team as first buyer**: daily batch jobs (embeddings) via CLI
2. **1 neocloud partner**: contacted in advance, runs miner + buys own jobs for test
3. **Researcher grant**: 100 GPU hours for public report

### Phase 2 exit criterion
> Public batch job: buyer funds escrow → miner settles → explorer shows useful_ratio > 0 for that block.

---

## 7. Phase 3: Developer API (weeks 17–20)

### Goals
- `api.abakos.ai/v1` OpenAI-compatible
- requests translate into **testnet batch jobs** (not central GPU)
- Cursor/Continue setup guide on website becomes **real**

### MVP endpoints

| Endpoint | Behavior |
|---|---|
| `GET /v1/models` | registry models |
| `POST /v1/chat/completions` | **batch mode** first (async job + poll); streaming in Phase 3.5 |
| `POST /v1/embeddings` | direct batch path (fastest value) |

### Architecture

```
Client → api.abakos.ai (auth, billing, rate-limit)
              → marketplace indexer (create + fund job)
              → miner takes job
              → result back to client
```

### Phase 3 exit criterion
> Cursor with Abakos base URL returns answer; job ID visible on explorer; useful_ratio rises.

---

## 8. Phase 4: Abakos Chat (weeks 21+)

- start only when batch + API stable (error rate, latency documented)
- real-time: initially **hybrid** (1 partner node with SLA), clearly labeled "Testnet Chat Beta"
- session escrow + streaming billing = own spec (later)

---

## 9. Explorer: mandatory metrics

| Metric | Description |
|---|---|
| **% useful compute (24h)** | weighted average `useful_ratio` over blocks |
| **Empty vs. paid work** | chart: matmul work with/without escrow |
| **Active miners** | addresses with block in 24h |
| **Open jobs** | FUNDED, waiting |
| **Pearl comparison** | static: "Pearl measured 0% useful (arXiv 2606.04819)" |

This is the **marketing product** of the testnet, not the API.

---

## 10. What we deliberately do NOT do

| Skip | Why |
|---|---|
| Central preview API proxy | contradicts testnet-first; dilutes story |
| Mainnet before audit | firm decision |
| Chat before marketplace | no escrow loop, no useful_ratio |
| FP8/BF16 in testnet v1 | INT8 enough for PoUW proof |
| AMD in testnet v1 | NVIDIA first |
| Own stablecoin | USDC/USDT or testnet wrap |

---

## 11. Risks & mitigations

| Risk | Mitigation |
|---|---|
| PoUW↔job binding too hard | economic binding first (escrow must exist); iterate ZK |
| No miners | incentives + 1 neocloud + simple Docker miner |
| No buyers | team + grant + partner as first jobs |
| btcd fork takes forever | narrow scope: PoW replacement + reward only, rest vanilla |
| Latency too bad for API | batch + embeddings first; chat later |
| Pearl fork license | btcd ISC; study Pearl code as reference only, do not copy blindly |

---

## 12. Infrastructure (testnet)

| Service | Host | Note |
|---|---|---|
| Seed nodes | VPS / partner | 3×, EU+US if possible |
| Explorer | `explorer.testnet.abakos.ai` | Caddy, like abakos.ai |
| Faucet | `faucet.testnet.abakos.ai` | rate-limited |
| Indexer | same VPS or separate | Postgres or SQLite for MVP |
| CI | GitHub Actions | `go test`, pouw CPU tests |

---

## 13. Documents & repos (to create/update)

| Artifact | When |
|---|---|
| `docs/testnet-guide.md` | Phase 1 |
| `docs/spec-pouw-kernel.md` | Phase 0 week 2 |
| `docs/spec-reward-split-impl.md` | Phase 0 week 4 |
| `explorer/` repo start | Phase 1 week 1 |
| `miner/Dockerfile` | Phase 1 |
| Website: testnet status banner | Phase 1 |

---

## 14. Next 14 days (concrete)

### Week 1
- [x] Pearl repo + btcd: document PoW replacement points (`docs/spec-pouw-integration.md`)
- [x] `btcd` as Go module dep, `abkd` compiles with Abakos `params` + `node/pouw/`
- [x] local simnet: 2 nodes (`--listen` / `--connect`), GEMM PoUW
- [ ] cuPOW paper spike notes (`docs/spec-pouw-kernel.md`, kernel spec ✅)

### Week 2
- [x] PoUW CPU spike (INT8 GEMM + Blake3, `pouw/gemm.go`)
- [x] `WorkVerifier` interface + mock in `node/pouw/`
- [x] first PoUW block locally + 2-node sync
- [ ] contact 1 neocloud + 1 dev from waitlist (testnet beta)

### Parallel (non-blocking)
- [ ] trademark search Abakos vs. abacus.ai
- [x] explorer wireframe (`explorer/index.html` + `abkd --http`)
- [ ] finalize tokenomics parameters in `params/` for testnet genesis

---

## 15. Success metrics (KPIs)

| KPI | Phase 1 target | Phase 2 target |
|---|---|---|
| External miner addresses | ≥ 10 | ≥ 50 |
| % useful compute (24h) | 0% (ok, documented) | ≥ 5% |
| Batch jobs settled | 0 | ≥ 100/week |
| Explorer unique visitors | 500 | 2,000 |
| GitHub stars / forks | track | track |

---

## 16. Link to roadmap

The phase numbers in this plan **are** the roadmap's phase numbers. Phase 0
here is Phase 0 in `docs/07-roadmap.md`, the website and `status.abakos.ai`,
with no translation needed. (An earlier draft of this doc used a separate
"T0–T4" label that required a lookup table to map onto the roadmap; that
label has been retired so there is exactly one numbering.)

See also: `docs/02-architecture.md`, `docs/spec-marketplace.md`, `docs/07-roadmap.md`, `node/params/params.go`.
