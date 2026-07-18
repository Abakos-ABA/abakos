# 02 · Technical Architecture

## Component overview

| Component | Base / stack | Role |
|---|---|---|
| `abkd` (node) | Fork of `btcd` (Go), like Pearl | consensus, mempool, P2P, wallet |
| PoUW kernel | cuPOW/NoisyGEMM from eprint 2025/685; CUDA/CUTLASS + ROCm/HIP | matmul PoW + Plonky2 ZK proof |
| Model registry | on-chain module | registers model/weight hashes; jobs bind inputs to them |
| Marketplace + escrow | on-chain module + off-chain indexer | job ordering, payment, matching, settlement |
| Miner client | Go + GPU kernel + vLLM/SGLang plugin | takes paid jobs, computes, proves |
| Developer API (`api.abakos.ai`) | OpenAI-compatible gateway (REST/SSE) | Cursor, VS Code, CLI, LangChain, no custom SDK needed |
| Abakos Chat | web/mobile frontend + gateway | consumer access, token/balance → inference |
| Explorer + dashboard | web | hashrate, % useful, prices, jobs |

## Consensus & PoUW

- Base: Nakamoto consensus (longest chain) like Bitcoin/Pearl.
- Work: tiled, "noised" matrix multiplication (NoisyGEMM), Blake3 jackpot under difficulty target, Plonky2 ZK proof for cheap on-chain verification.
- **New vs. Pearl:** FP path (BF16/FP8) in addition to INT8, plus **model-hash commitment**: proof binds input matrices to a registered weight hash. That closes the "adversarial Gaussian" gap (pure distribution checks are trivially bypassable per arXiv, so we solve it **economically**, not only statistically).

## Reward split (core mechanism)

```
reward_block = base * (0.25 + 0.75 * useful_ratio)
```

- `useful_ratio` = share of block work bound to a **paid escrow job**.
- Empty mining (random matrices) → `useful_ratio = 0` → only 25% reward.
- Fully paid work → `useful_ratio = 1` → 100% reward.
- Effect: unlike Pearl, useful work is the most profitable strategy.

## Verification flow (simplified)

1. Miner commits input matrices (bound to model hash from registry).
2. Computes tiled NoisyGEMM on GPU.
3. Produces jackpot hash + Plonky2 proof.
4. `abkd` verifies: value range, Merkle consistency, recomputed tile == jackpot, difficulty met, **escrow job reference valid**.
5. Block accepted → reward per split + escrow payout to miner.

## Hardware strategy

- **Tier 1:** NVIDIA Hopper/Ada/Blackwell, AMD MI300/MI325 (datacenter, for marketplace jobs).
- **Tier 2:** consumer GPUs (RTX 3060–4090), per arXiv ROI positive here → simpler installer.
- **Tier 3 (light):** CPU/Apple Silicon for light mining/tests (arXiv proved feasibility) → onboarding feature.

## Model sizes & provider tiers (open weights only)

- **Open-weight models only.** Closed frontier models (Claude Opus, GPT, Gemini) have secret weights and cannot be run decentrally by **anyone**, not by us, not by io.net/Akash. We serve strong open models (Llama, Qwen, DeepSeek, Mistral, Gemma) → "good enough + much cheaper." (Optional later: closed models only as API passthrough, without subsidy.)
- **Job routing by VRAM** (registry field `min_vram`): each job goes to a provider with enough memory.

| Model class | Requirement | Provider tier |
|---|---|---|
| 7B–70B (quantized) | 1 GPU | consumer/single-datacenter GPU, the simple, parallel case |
| 100B–700B (e.g. DeepSeek-V3, Llama 405B) | local multi-GPU box (e.g. 8×H100, tightly connected) | neocloud/datacenter provider |

- **Important:** model sharding (tensor/pipeline parallelism) happens **inside a provider box**, never across the internet (latency). Single GPUs run **whole** jobs independently (data-parallel).
- **Phasing:** start with single-GPU models + batch (largest immediately addressable volume, fastest revenue). Large models come via neocloud partners (supply side, Doc 06) + quantization (fp8/int4).

## Repos (planned)

```
abakos/
  abkd/              # btcd fork, chain node (Go)
  pouw-kernel/       # CUDA/ROCm matmul + ZK (C++/Rust)
  miner/             # miner client + vLLM/SGLang plugin
  marketplace/       # on-chain modules + indexer
  api/gateway/       # OpenAI-compatible managed gateway (IDE + apps)
  sdk-python/        # optional: thin wrapper; standard is `openai` + base_url
  chat/              # Abakos Chat frontend + gateway
  explorer/          # block explorer + useful-compute dashboard
  docs/              # whitepaper, litepaper, specs
```

## Open technical questions (to resolve)

- Plonky2 proof cost on FP path: measure overhead.
- Deterministic reproducibility for re-verification (cf. Gonka's approach with fixed seeds).
- Latency vs. batch: real-time inference (chat) needs different job paths than latency-insensitive batch jobs.
