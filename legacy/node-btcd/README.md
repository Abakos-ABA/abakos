# node/: `abkd` (Abakos full node)

Proof-of-Useful-Work L1, planned as a fork of [btcd](https://github.com/btcsuite/btcd) (ISC).

## Status (T0)

| Component | Status |
|---|---|
| `params/` + `economics/` | Reward-split, emission (tested) |
| `pouw/` | `WorkVerifier`, **CPU GEMM** (default) + SHA-256 stub |
| `wire/` + `consensus/` | Abakos header + `CheckProofOfUsefulWork` (fork precursor) |
| `chain/` | In-memory chain + mining |
| `simnet/` | Simple TCP block sync (T0 default) |
| `p2p/` | btcd-style P2P + `netsync` (`--p2p btcd`) |
| `fork/` | btcd `replace` fork + PoUW patches |

## Build

```bash
cd node
go build -o abkd ./cmd/abkd
go test ./...
```

## T0 simnet: 2 nodes

**Simple P2P (default):**

Terminal 1 (seed + miner):
```bash
./abkd --simnet --datadir ./data/seed --listen :18555 --mine --verifier gemm
```

Terminal 2 (follower):
```bash
./abkd --simnet --datadir ./data/follower --connect 127.0.0.1:18555
```

**btcd netsync (`--p2p btcd`):**

Terminal 1:
```bash
./abkd --simnet --p2p btcd --datadir ./data/seed --listen :18555 --mine --http :13080
```

Terminal 2:
```bash
./abkd --simnet --p2p btcd --datadir ./data/follower --connect 127.0.0.1:18555
```

Windows: `scripts/simnet-two-nodes.ps1` (starts seed; open a second terminal for follower).

## Flags

| Flag | Description |
|---|---|
| `--simnet` | Local T0 network |
| `--verifier gemm` | INT8 matmul PoUW (default) |
| `--verifier sha256` | Legacy SHA-256 placeholder |
| `--p2p btcd` | Use btcd P2P + `netsync` (ffldb chain DB) |
| `--listen :port` | Accept peer connections |
| `--connect host:port` | Seed peer(s), comma-separated |
| `--mine` | Mine blocks (seed) |
| `--datadir path` | Chain data (`chain.json` or ffldb with `--p2p btcd`) |
| `--http :port` | Explorer API (`/api/v1/stats`, `/api/v1/blocks`) |

## Layout

```
node/
  cmd/abkd/           entry point
  pouw/               PoUW verifiers (gemm, sha256 stub)
  wire/               Block header + certificate encoding
  consensus/          CheckProofOfUsefulWork
  chain/              Chain + mining
  simnet/             Simple T0 P2P
  p2p/                btcd P2P + netsync
  api/                Explorer read API
  fork/               btcd fork plan
  chaincfg/           Network constants
```

See [`docs/spec-pouw-integration.md`](../docs/spec-pouw-integration.md) and [`docs/17-testnet-plan.md`](../docs/17-testnet-plan.md).

## License

MIT for Abakos code; btcd ISC when vendored/forked.
