# 07 · Roadmap & Milestones

> Timeframes are guidelines for a small team (3–4 people). Calibrate based on resources.

> **Phase numbers here match the website exactly** (`abakos.ai`, `status.abakos.ai`, this litepaper/whitepaper): Phase 0 = Foundation, Phase 1 = Public testnet, Phase 2 = Marketplace (+ Enterprise offtake, same rails), Phase 3 = Developer API batch mode, Phase 4 = Abakos Chat + Developer API streaming mode (both need the real-time path, so they ship together), Launch = Audit and mainnet. There is no other numbering. Earlier drafts used "Phase 2b/2c" and "P0–P4," which drifted out of sync with the public site and have been retired.

> **Launch strategy (decision):** **Mainnet-first** as prioritized goal, but **not** without a security gate. Mandatory before mainnet: (1) short **incentivized testnet/canary** (2–4 weeks, doubles as marketing/community/investor proof), (2) **audit** of new modules (reward split, escrow, PoUW kernel, ZK). Reason: the `btcd` foundation is robust, but our new consensus code otherwise carries exploit/fund-loss risk with real money. We shorten testnet + audit maximally but do not skip them.

## Phase 0 · Week 1–4 · Foundation

- [ ] study Pearl/`btcd` code, set up `abkd` repo
- [ ] genesis, branding (Abakos/ABA), tokenomics parameters in code
- [ ] port PoUW kernel from open paper (eprint 2025/685), INT8/inference first
- [ ] internal testnet: block production running

**Milestone:** local block with matmul PoW produced & verified.

## Phase 1 · Week 5–8 · Differentiation

- [ ] implement model-hash commitment + reward split
- [ ] public testnet + explorer with "% useful" metric
- [ ] publish whitepaper + litepaper

**Milestone:** public testnet shows provably paid vs. empty work.

## Phase 2 · Week 9–16 · Marketplace on testnet (batch)

> **Order (decision June 2026):** marketplace **before** API **before** chat. Everything runs on public testnet, no centralized preview proxy. Enterprise offtake and the API's batch mode ride on this same batch infrastructure, which is why they land at Phase 2–3, ahead of anything that needs the real-time path (see Phase 4 note below).

- [ ] escrow + job matching (batch inference: embeddings, classification)
- [ ] indexer + job API for miners
- [ ] first external buyers (team + 1 partner + grant)
- [ ] enterprise offtake track opens (same rails, negotiated volume instead of self-serve)
- [ ] explorer: `useful_ratio > 0` visible

**Milestone:** first real batch job settled on-chain; dashboard shows paid vs. empty work.

## Phase 3 · Week 17–20 · Developer API, batch mode (on testnet)

- [ ] `api.abakos.ai/v1`: OpenAI-compatible, routes to testnet batch jobs (embeddings, non-streaming completions only, no real-time path yet)
- [ ] Cursor/Continue setup guide on website goes live
- [ ] API keys for waitlist developers (limited)

**Milestone:** completion from Cursor creates visible job on explorer.

## Phase 4 · Week 21+ · Abakos Chat + Developer API streaming (testnet beta)

> **Why together:** Abakos Chat and the API's streaming endpoint (chat completions, IDE agents) both need the same real-time job path with session escrow, not just funded batch jobs. That's a shared, harder piece of infrastructure than Phase 3's batch mode, so both ship in this phase rather than the API's streaming mode waiting all the way until Launch.

- [ ] web chat MVP, real-time path (hybrid with SLA node ok, clearly labeled)
- [ ] `api.abakos.ai/v1` streaming (`stream: true`) on the same hybrid real-time infra
- [ ] session escrow (simplified)
- [ ] expand testnet incentive program

**Milestone:** first chat message *and* first streaming API completion with a job on testnet (not central GPU without label).

## Launch · Month 5–7 · Mainnet + first revenue

- [ ] mainnet launch, listing on 1–2 DEX/CEX, liquidity
- [ ] FP8/BF16 path + training/fine-tuning
- [ ] real-time inference path for Abakos Chat **and** the API's streaming endpoint moves off hybrid partner GPUs onto the fully decentralized network (<800 ms first token)
- [ ] 1–2 neocloud partners (supply), first paying batch customers

**Milestone:** first stablecoin revenue from marketplace fee + chat margin.

## Post-launch · Month 7–12 · Scale

- [ ] vLLM/SGLang plugin for external GPU farms
- [ ] managed inference API as standalone product
- [ ] multi-vendor (AMD) in production, non-AI GEMM
- [ ] Abakos Chat: mobile app, ABA payment, subscription, multiple models

**Milestone:** network scales (>10,000 GPU target), recurring revenue.

## Critical path

`abkd` fork → PoUW kernel → reward split → escrow marketplace (+ Enterprise, same rails) → Developer API batch mode → real-time job path → Abakos Chat + Developer API streaming mode (together, same infrastructure) → Launch. Everything after the marketplace builds on it; everything real-time builds on the same real-time path, whichever of Chat or the API's streaming mode gets there first.
