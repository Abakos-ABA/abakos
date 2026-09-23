# Roadmap

Phase numbers match [status.abakos.ai](https://status.abakos.ai) and the [litepaper](docs/litepaper.md).
This is a plan, not a promise — dates move when security or correctness needs it.

## Phase 1 — Public sandbox (live)

- [x] PoS chain (Cosmos SDK + CometBFT) with native EVM, chain id 9721, zero gas
- [x] Web wallet, explorer, ABA/USDC DEX (Uniswap-v2 fork) with in-app USDC bridge (Skip → CCTP → Noble → IBC)
- [x] Abakos Provider desktop app (Tauri, Windows + Linux), signed auto-updates
- [x] Provider Agent: rent-first scheduler, profit-switch idle mining, on-chain 88/4/4/4 payouts
- [x] Live IBC channel to Noble (canonical Circle USDC)

## Phase 2 — Console + compute marketplace (in progress)

- [x] MetaMask-signed Console deployments (EIP-191 fallback, regression tests, end-to-end sandbox suite)
- [ ] Console templates, bundles and add-ons with ABA escrow (3% marketplace fee)
- [ ] Persistent storage and IP leases for deployments
- [ ] Provider onboarding on vanilla Linux without special commands (`provider-compute/`)
- [ ] Manage compute providers from a main account via `authz`

## Trust & distribution

- [ ] Windows code signing (SmartScreen "unknown publisher")
- [ ] macOS build
- [ ] Listing in `cosmos/chain-registry` ([PR #7854](https://github.com/cosmos/chain-registry/pull/7854))
- [ ] Reproducible release checksums published with every release (started with v0.1.29)

## Phase 3 / 4 — Developer API and Abakos Chat (planned)

- [ ] OpenAI-compatible developer API (batch first, then streaming)
- [ ] Abakos Chat on open models, same 88/12 revenue split

## Launch — mainnet (after audit)

- [ ] External security audit
- [ ] External validator onboarding
- [ ] Liquidity seeding and mainnet genesis

Want to help with any of these? See [CONTRIBUTING.md](CONTRIBUTING.md) and the
[good first issues](https://github.com/Abakos-ABA/abakos/labels/good%20first%20issue).

*The sandbox is experimental. Only use amounts you can afford to lose.*
