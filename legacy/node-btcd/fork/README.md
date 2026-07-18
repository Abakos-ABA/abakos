# btcd fork (Abakos PoUW)

Local btcd fork at `node/.btcd-fork/` (gitignored). Initialized via:

```powershell
.\scripts\init-btcd-fork.ps1
```

Branch: `abakos-pouw`

## P0 patches (landed)

| btcd path | Change |
|---|---|
| `wire/abakos.go` | `BlockVersionAbakos`, header size helpers |
| `wire/blockheader.go` | `ProofCommitment`, `UsefulRatioBps`; Abakos 110-byte encoding |
| `wire/msgblock.go` | `Certificate []byte` before transactions |
| `blockchain/abakos_validate.go` | `checkProofOfUsefulWork` → `node/consensus` |
| `blockchain/validate.go` | Abakos branch in header + block sanity |
| `blockchain/error.go` | `ErrCertificateMissing` |

## go.mod wiring

```go
// node/go.mod
replace github.com/btcsuite/btcd => ./.btcd-fork

// node/.btcd-fork/go.mod
require github.com/rexmarlon/abakos/node v0.0.0
replace github.com/rexmarlon/abakos/node => ..
```

## Verify

```bash
cd node
go test ./...
```

Fresh clone: `.\scripts\init-btcd-fork.ps1` applies `fork/patches/abakos-pouw.patch`.

PoUW verifier registration lives in `node/fork/register.go` (avoids import cycles).

## Next (P1)

- `chaincfg/genesis.go`: Abakos testnet genesis
- `mining/cpuminer.go`: delegate to `pouw` miner
- ~~`server.go` / `netsync`~~: **done** in `node/p2p/` (`--p2p btcd`)

See [`docs/spec-pouw-integration.md`](../../docs/spec-pouw-integration.md).
