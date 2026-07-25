# Security Policy

Abakos runs a public sandbox that **intentionally carries real value rails** — real Circle
USDC flows in over IBC (Noble), a live DEX trades it, and mining payouts settle on-chain.
That is a deliberate decision: we want the stack attacked *before* mainnet, while amounts
are small. If you break something interesting, we want to hear from you — and meaningful
findings are rewarded.

## Reporting a vulnerability

- **Preferred:** GitHub **[private vulnerability reporting](https://github.com/Abakos-ABA/abakos/security/advisories/new)** on this repository.
- **Email:** [info@abakos.ai](mailto:info@abakos.ai) with subject `SECURITY`.

Please include reproduction steps and, where relevant, chain height / tx hashes. We aim to
acknowledge within 72 hours. Please give us reasonable time to fix before public disclosure.

## Scope (the interesting stuff)

| Area | Where |
|---|---|
| Chain / consensus | `chain/` — Cosmos SDK app, `x/escrow` settlement fee split |
| EVM & precompiles | `cosmos/evm` integration, ERC20 <-> IBC middleware (single token representation), bank/staking/bech32 precompiles |
| DEX | Uniswap-v2 fork contracts (Factory/Router/Pair `ABA-LP`), protocol `feeTo` path |
| Bridge inflow path | Skip/CCTP -> Noble forwarding accounts -> IBC -> ERC20 conversion (`bridge-relayer/`) |
| Payout engine | `provider-agent/` (share attribution, buyback swaps, splits) |
| Desktop app | `desktop/` (Tauri) — updater, key handling |
| Web | abakos.ai wallet/dex/explorer pages |

## Out of scope

- Denial of service / transaction spam (the network is zero-fee by design; abuse bounds
  are consensus & mempool limits — reports about "I can send many free txs" are known).
- Social engineering, phishing, physical attacks.
- Findings that require a compromised operator machine.

## Rewards

There is no fixed bounty table on the sandbox yet — rewards are case-by-case in USDC/ABA,
scaled by impact and report quality, plus credit in the release notes and (if you want) a
public hall-of-fame entry. Funds-at-risk findings on the bridge/DEX/escrow paths rate
highest. A formal bounty program with published tiers is a mainnet gate.
