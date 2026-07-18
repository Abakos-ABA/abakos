# T0 CPU PoUW spike (INT8 matmul + Blake3 jackpot)
# Full GPU NoisyGEMM lives in ../pouw/ (CUDA). This package is the on-chain verifier
# used by abkd until ZK/plain certificate wire format is finalized.

T0 dimensions: **8×8×8** INT8, fast in CI, not production hashrate.

## Verifiers

| Name | Flag | Use |
|---|---|---|
| `CPUGEMMVerifier` | `--verifier gemm` | Default, real matmul PoUW |
| `SHA256StubVerifier` | `--verifier sha256` | Legacy placeholder |

## Algorithm (simplified cuPOW)

1. Derive matrices `A`, `B` from header + nonce (Blake3 seed)
2. INT32 tile matmul + light noise term
3. XOR-accumulate → Blake3 jackpot
4. Jackpot meets compact `bits` target

Block ID (GEMM): Blake3(header ‖ jackpot).

See `gemm.go`, `docs/spec-pouw-integration.md`.
