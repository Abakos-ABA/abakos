# 09 · Competitive Landscape & Moat

> **Core thesis:** Not "also PoUW," but **measurable, enforced usefulness + real demand + mining subsidy**. Pearl proved PoUW alone is not enough. Gonka and GPU marketplaces have demand without PoW subsidy. Abakos combines both, if testnet, marketplace, and metrics deliver.

---

## The moat (combination: nobody has it complete)

| Pillar | Pearl | Gonka | io.net/Akash | OpenRouter/AWS |
|---|---|---|---|---|
| Enforced usefulness (economic) | ✗ | ~ | n/a | n/a |
| On-chain escrow (stablecoin) | ✗ | ~ | ~ | centralized |
| PoW mining subsidy (2-for-1 price) | ✓ (wasted) | ✗ | ✗ | ✗ |
| Consumer chat (mainstream) | ✗ | ✗ | ✗ | ✓ (centralized) |
| OpenAI API (Cursor/IDE) | gated | ? | ✗ | ✓ |
| Public **% useful** metric | ✗ (0%) | ? | n/a | n/a |

**Single lever that beats all:** prove live in the explorer that **paid jobs** feed the chain. Pearl's documented weakness becomes our marketing.

---

## One sentence per competitor

| Competitor | Abakos is better because… |
|---|---|
| **Pearl (PRL)** | …we **enforce** usefulness, not just matmul correctness |
| **Gonka (GNK)** | …we combine PoW subsidy + stablecoin settlement + consumer app |
| **io.net / Akash** | …the same GPU hour also mines and is subsidized (2-for-1) |
| **OpenRouter / Together** | …effective price is co-paid by block rewards |
| **AWS / OpenAI** | …we are open, cheaper (open weights), and without vendor lock-in |

---

## Direct PoUW / "useful work" chains

### Pearl (PRL): technical reference point, not fork target

- Bitcoin/btcd fork, PoUW via NoisyGEMM, mainnet since 2026-04-27, 2.1B supply.
- **Weaknesses (documented):** verifies correctness only → ~320,000 GPUs, ~112 MW, **~0% useful AI** (arXiv 2606.04819). No open marketplace, Hopper/int7, 1 subsidized partner (Together), no consumer product.
- **Where we are better:**

| Area | Pearl | Abakos |
|---|---|---|
| Usefulness | claimed | reward split + escrow **enforced** |
| Marketplace | ✗ (gated) | on-chain + stablecoin escrow |
| Metric | no useful-% | explorer: **% useful live** |
| Developer access | 1 endpoint | OpenAI API, Cursor/VS Code |
| Hardware | Hopper, int7 | consumer + datacenter, BF16/FP8, AMD (planned) |
| Mainstream | ✗ | Abakos Chat |

### Gonka (GNK): philosophically closest rival

- L1, Cosmos-SDK, "Proof of Compute": reward for verifiably useful AI tasks; DiLoCo for distributed training; deterministic reproducibility.
- **Where Gonka is strong:** real tasks from day one, no random-matmul problem, serious verification story.
- **Where we can be better:**

| Area | Gonka | Abakos |
|---|---|---|
| Consensus | Cosmos/BFT | Nakamoto PoW (miner story, 4090 ROI) |
| Payment | primarily token | **stablecoin escrow** + token subsidy separate |
| Price lever | compute reward | compute reward **+** block mining (2-for-1) |
| Mainstream | crypto-native | Abakos Chat (card/email, crypto-invisible) |
| Miner onboarding | hosts | solo miner 1-click + neocloud idle capacity |
| PoUW basis | own path | cuPOW/matmul (Pearl-proven) + economic fix |

**Watch:** Gonka verification vs. our economic binding. Compare in testnet.

---

## Decentralized GPU marketplaces (no PoUW consensus)

**Akash, io.net, Render, Vast.ai, RunPod**

- **Their advantage:** liquidity, UX, many models, established customers.
- **Our advantage:**
  - **Price:** PoW subsidy on the same watt-hour → effective price below pure rental.
  - **Miner incentive:** job income **+** ABA block reward.
  - **One network:** security and compute coupled, not just brokerage.
  - **Deflation with real volume:** fee burn + empty-mining burn with real jobs.

**Pitch to neoclouds:** "Idle GPUs: with us **rental + mining** on the same hardware cycle."

---

## Centralized providers

**AWS/Azure/GCP, OpenAI/Anthropic, OpenRouter, Together**

| Where we can win | How to make it credible |
|---|---|
| **Price** (20–40% below OpenRouter) | worked example: subsidy + escrow |
| **Open models** | Llama, Qwen, DeepSeek, no lock-in |
| **IDE virality** | Cursor/Continue, copy-paste, not just API docs |
| **Decentral / open** | niche, but real for some buyers |

| Where we **don't** win (honestly) | Strategy |
|---|---|
| Latency, enterprise SLA, frontier models | batch first; chat hybrid; never promise closed models |
| Trust / brand | audit, testnet, researcher grants, reference neocloud |

---

## Differentiation beyond features

| Lever | Benefit |
|---|---|
| **Transparency** | "% useful" live, open source from testnet, no price predictions |
| **Two cash flows** | stablecoin revenue ≠ token speculation (legal + buyer trust) |
| **Academic validation** | grants + paper; Pearl has counter-evidence (arXiv), we answer with data |
| **Consumer without crypto UI** | chat with card/email; Gonka/Pearl are crypto-native |
| **Solo-miner democracy** | 3060–4090 ROI positive (arXiv), broader than Pearl Hopper-only |
| **Anti-scam stance** | mainnet only after audit, trust in a burned market |

---

## Prioritized differentiation roadmap

**Note:** "Prio" (P0–P3) below ranks *importance*, not delivery order. A
different axis from the "Phase 0–4 / Launch" delivery phases used everywhere
else (website, roadmap, whitepaper). Don't confuse the two: a P0 item can
still land in a later phase if it depends on that phase's infrastructure.

| Prio | Differentiator | Primarily against | Provable when |
|---|---|---|---|
| **P0** | % useful live + reward split | Pearl | public testnet (Phase 1) |
| **P0** | marketplace + stablecoin escrow | Pearl, Gonka | marketplace (Phase 2) |
| **P1** | cheapest batch price (2-for-1) | io.net, OpenRouter | first batch jobs |
| **P1** | OpenAI API → testnet jobs | Pearl, APIs | after marketplace (Phase 3) |
| **P2** | Abakos Chat (mainstream demand) | all crypto-compute | Phase 4 |
| **P2** | consumer GPU miner (1-click) | Pearl (Hopper) | miner installer (Phase 1) |
| **P3** | AMD, training, non-AI GEMM | broader market | post-testnet |

---

## What we deliberately do **not** compete on

- More hashrate / EH/s than Pearl: irrelevant at 0% useful.
- Frontier closed models (GPT, Claude, Gemini): technically impossible decentrally.
- Fastest token launch / CEX hype: contradicts mainnet-first + audit.
- "The next Bitcoin": financial hype, not our brand (see Doc 15).

---

## Positioning in one sentence

> Abakos = Pearl's proven PoUW base **+** Gonka's seriousness about real usefulness **+** stablecoin marketplace **+** consumer chat **+** uncompromising price undercut via mining subsidy, **publicly measured**.

---

## Investor moat (3 bullets for deck)

1. **Enforced usefulness**: only paid escrow work earns full rewards; Pearl's 0% useful is structurally impossible to repeat.
2. **2-for-1 economics**: same GPU hour earns mining subsidy *and* produces paid AI output; beats io.net/OpenRouter on unit price.
3. **Demand engine**: marketplace + Abakos Chat + IDE API channel mainstream and developer demand into the chain (no competitor combines all three).

---

## Competitive intelligence to-do

- [ ] Compare Gonka whitepaper & verification mechanics vs. reward split
- [ ] Price benchmark Abakos vs. OpenRouter/io.net/Akash (monthly, in `model/`)
- [ ] Track Pearl: hashrate, PRL price, useful-% (external studies)
- [ ] After testnet (Phase 1): own **% useful** vs. Pearl figure (0%) in all outreach materials
- [ ] 1 neocloud case study: document "rental + mining" unit economics
