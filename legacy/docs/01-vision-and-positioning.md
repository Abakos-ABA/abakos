# 01 · Vision & Positioning

## Vision

Compute (GPU processing power) is the new foundational resource. Today it is expensive, centralized (AWS, Azure, GCP), and inaccessible to "ordinary people." Abakos makes compute **cheaper than anywhere else** because the same GPU cycles create value twice: AI output *and* chain security (subsidized by block rewards). That subsidy pushes the price below all centralized providers.

## The problem with Pearl (why a fork makes sense)

- Pearl verifies **correctness** of matmul, not **usefulness**. Result: ~320,000 GPUs grinding random matrices, 112 MW for nothing (source: arXiv 2606.04819).
- Exactly **one** real customer (Together AI, subsidized Gemma endpoint), no marketplace (`compute.pearlresearch.ai` is gated).
- Proprietary int7 pipeline, Hopper GPUs only, 3 models → not compatible with industry standard (BF16/FP8).
- The "virtuous loop" (demand → subsidy → compute → security) is **not enforced** by the protocol, only hoped for.

## Our answer (differentiation)

| Area | Pearl today | Abakos |
|---|---|---|
| Usefulness | only claimed | enforced via reward split & escrow |
| Demand side | 1 partner, no marketplace | on-chain marketplace + consumer app |
| Hardware | Hopper-only, int7 | multi-vendor (NVIDIA/AMD), BF16/FP8 |
| Workload | inference only (INT8) | inference **and** training/fine-tuning |
| Settlement | reward in token, customer pays off-chain | stablecoin escrow + token reward, atomic |
| Mainstream access | none | Abakos Chat ("ChatGPT for everyone") |
| Developer API | 1 gated Together endpoint | open OpenAI API: Cursor, VS Code, CLI |

## Positioning statement

> **Abakos = the compute layer with real, paid utility + a ChatGPT app anyone can use with tokens.**

## Target audiences (order of outreach)

1. **GPU providers** (neoclouds with idle capacity, solo miners): supply side first.
2. **Batch compute buyers** (embeddings, synthetic data, labeling): fastest revenue.
3. **End users via Abakos Chat**: mainstream demand, largest long-term lever.
4. **IDE users / indie devs**: Abakos API in **Cursor, VS Code (Continue, Cline)**, CLI; cheaper than OpenRouter/OpenAI.
5. **AI startups**: same API for product backends (batch + real-time).
6. **Researchers / academic labs**: credibility + subsidized GPU hours.

## Core KPI (public, positioned against Pearl)

**"% verified-useful compute"**, live in the explorer. That is our marketing proof and Pearl's documented weakness.

## Brand story

Pearl = pearl (a jewel to speculate on). Abakos = the abacus, the original computing device that turns processing power into real value. Message: not a jewel to hoard, but infrastructure that does real work.
