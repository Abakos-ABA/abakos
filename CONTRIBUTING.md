# Contributing to Abakos

Thanks for your interest! Abakos is a zero-fee, EVM-compatible PoS compute chain with a
desktop miner app — there is plenty of surface to help on.

## Quick orientation

| I want to… | Go to |
|---|---|
| Report a bug | [Open an issue](https://github.com/Abakos-ABA/abakos/issues/new/choose) (templates provided) |
| Report a security issue | **[SECURITY.md](SECURITY.md)** — please do not open a public issue |
| Discuss ideas | [GitHub Discussions](https://github.com/Abakos-ABA/abakos/discussions) or [Discord](https://discord.gg/zBxNvdMjtM) |
| Find a first task | [Good first issues](https://github.com/Abakos-ABA/abakos/labels/good%20first%20issue) · [help wanted](https://github.com/Abakos-ABA/abakos/labels/help%20wanted) |
| See where it's heading | [ROADMAP.md](ROADMAP.md) |
| Understand the design | [`docs/litepaper.md`](docs/litepaper.md) · [`docs/whitepaper.md`](docs/whitepaper.md) · [`docs/fee-model.md`](docs/fee-model.md) |

## Building

- **Chain (`chain/`):** Cosmos SDK app, builds on Linux (Go 1.25+, CosmWasm `libwasmvm`).
  `cd chain && go build ./cmd/akash`. Windows: edit only, build in WSL.
- **Desktop app (`desktop/`):** Tauri v2 — `npm install && npm run tauri:dev`
  (Rust + Node required).
- **DEX (`dex/`):** Node scripts compile the Uniswap-v2 fork with solc and deploy against
  the public sandbox EVM (`https://evm-rpc.abakos.ai`, chain id 9721).

The public sandbox is free to use for testing — transactions cost 0 gas.

## Running the tests

- **Signing regression tests (chain, Linux):**
  `cd chain && go test ./cmd/akash/cmd/ -run 'TestNodeAccepts|TestEthAccount|TestCosmosAccount'`
  and `go test github.com/cosmos/cosmos-sdk/x/auth/signing -run EthPersonal` (run via the chain module).
- **Amino sign doc (chain-sdk):** `cd chain-sdk/go && go test ./sdkutil/ -run Amino`
- **Desktop:** `cd desktop && npm run build` (type check + bundle).

Please run the tests that touch your change and mention the result in the PR.

## Pull requests

- Keep PRs focused; describe the *why*, not just the *what*.
- Match the surrounding code style; no drive-by reformatting.
- Anything touching payout splits, the escrow fee, DEX contracts or the bridge path must
  reference [`docs/fee-model.md`](docs/fee-model.md) — code and docs stay in lockstep.

## Ground rules

- Be kind and concrete. Criticism of the design is welcome — open an issue or a discussion.
- We never reward stars, upvotes or follows (no tokens, roles or giveaways) — that would violate
  GitHub's Acceptable Use Policies.
- The public sandbox is experimental: never ask users to deposit real funds in docs or examples.

## License

Contributions are accepted under the repository's [MIT license](LICENSE). The chain keeps
upstream Akash attributions (see [NOTICE](NOTICE)).
