# pouw/: Proof-of-Useful-Work kernel

The work function: tiled, noised matrix multiplication (NoisyGEMM) on GPU,
with a Blake3 jackpot under the difficulty target and a Plonky2 ZK proof for
cheap on-chain verification. Based on the open cuPOW paper
(https://eprint.iacr.org/2025/685).

## Status
Plan only. No code yet.

## Scope
- CUDA/CUTLASS (NVIDIA) + ROCm/HIP (AMD) GEMM kernels.
- INT8 first, then FP8/BF16 (standard-compatible, vLLM/SGLang drop-in).
- Model-hash commitment binding inputs to a registered weights hash.
- Proof generation + verifier usable by `node/`.

## Key open question
Cryptographically binding "this PoW jackpot came from *these* paid-job inputs"
is the hard part. Fallback is the economic binding (reward only with a funded
escrow job). See /docs/spec-marketplace.md §5.
