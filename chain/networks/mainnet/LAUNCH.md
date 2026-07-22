# abakos-1 mainnet launch (ABA-only, genesis-direct)

Mainnet is launched **ABA-only from genesis** — no governance proposals and no
binary denom-alias are required. The sandbox retrofit proposals (#1 oracle,
#2 uaba params) exist only because `abakos-sandbox-1` was born before the
single-coin work; do **not** replicate them on mainnet.

> **Reality check (verified 2026-07-22).** `abakosd prepare-genesis mainnet`
> currently **cannot** produce an ABA-only genesis on its own — see
> [Known issues](#known-issues-prepare-genesis). Until those are fixed, build the
> genesis with `genesis init` + a **jq post-process** to `uaba` (the same,
> proven approach `chain/networks/sandbox/regenesis.sh` uses for the sandbox).

## What must be true in the final genesis (ABA-only)

| Field | Required value |
| ----- | -------------- |
| bank `denom_metadata` | single entry, base `uaba` (no `uact`) |
| bank `send_enabled` | `uaba` only |
| staking `bond_denom` | `uaba` |
| mint `mint_denom` | `uaba` |
| gov `params.min_deposit` | `uaba` |
| deployment `params.min_deposits` | `[uaba]` |
| market `params.bid_min_deposit(s)` | `uaba` |
| oracle `params.sources` | `[]` (empty → BME can never mint `uact`) |
| gas (`config.go` MinGasPrices) | `0uaba` |

## Launch procedure (reliable path)

```bash
CHAIN_ID=abakos-1
abakosd genesis init <moniker> --chain-id "$CHAIN_ID"

# add genesis accounts (uaba), gentx per validator, collect
abakosd genesis add-genesis-account <addr> <amount>uaba
abakosd genesis gentx <validator> <stake>uaba --chain-id "$CHAIN_ID"
abakosd genesis collect-gentxs

# force ABA-only across all modules (init defaults still carry uakt/uact)
G=~/.akash/config/genesis.json
jq '
    .app_state.staking.params.bond_denom = "uaba"
  | .app_state.mint.params.mint_denom = "uaba"
  | .app_state.gov.params.min_deposit = [ {"denom":"uaba","amount":"10000000"} ]
  | .app_state.bank.denom_metadata |= map(select(.base=="uaba"))
  | .app_state.bank.send_enabled = [ {"denom":"uaba","enabled":true} ]
  | .app_state.deployment.params.min_deposits = [ {"denom":"uaba","amount":"500000"} ]
  | .app_state.market.params.bid_min_deposit = {"denom":"uaba","amount":"500000"}
  | (if (.app_state.market.params|has("bid_min_deposits")) then .app_state.market.params.bid_min_deposits = [ {"denom":"uaba","amount":"500000"} ] else . end)
  | (if (.app_state.oracle.params|has("sources")) then .app_state.oracle.params.sources = [] else . end)
' "$G" > "$G.tmp" && mv "$G.tmp" "$G"

abakosd genesis validate     # must pass before distributing genesis
```

Do **not** run `chain/_run/init.sh` for mainnet — that is the upstream Akash dev
harness (literal `uakt`, deploys Pyth/Wormhole, funds the BME vault, runs
proposal #1) and reintroduces the dual-token/oracle world we intentionally drop.

## Known issues: `prepare-genesis`

`abakosd prepare-genesis mainnet <id>` is currently **broken and incomplete**
(verified). Fix these before relying on it instead of the jq path above:

1. **mint denom blank** — `MainnetGenesisParams()` didn't set `MintParams`, so
   `PrepareGenesis` overwrote the app default with a zero value → `ValidateGenesis`
   fails with `mint denom cannot be blank`. **Fixed in `genesis.go`** (mint denom
   pinned to `uaba`).
2. **gov v1 `Params` nil panic** — `PrepareGenesis` sets only the deprecated
   v1beta1 `DepositParams/TallyParams/VotingParams`; gov **v1** `ValidateGenesis`
   reads `data.Params` (nil) → panic. **Still open**: populate the v1
   `x/gov/types/v1` `Params` (voting/deposit/tally) instead of the v1beta1 split.
3. **structural gap** — `PrepareGenesis` only rewrites
   bank/staking/mint/distribution/gov/crisis/slashing. It never touches
   `deployment`/`market`/`oracle`/`bme`, which keep app-default denoms containing
   `uakt`+`uact`. Add explicit uaba overrides for those modules (or keep using the
   jq post-process).

The single-coin bank metadata (`NativeCoinMetadatas` = ABA only, `SendEnabled` =
uaba) is already set in `genesis.go`; it just can't be exercised until (2)+(3)
are resolved.

## Sandbox vs mainnet

| | sandbox (`abakos-sandbox-1`) | mainnet (`abakos-1`) |
| --- | --- | --- |
| Born ABA-only | via `regenesis.sh` jq-patch of live genesis | **Yes, from genesis** |
| Governance voting period | **10 min** (fast iteration) | 3 days (see `MainnetGenesisParams`) |
| Proposal #1/#2 | wiped by re-genesis; N/A | N/A |
| Denom alias in binary | bridges any legacy on-chain params | remove post-launch (params already uaba) |
| Validators | single hosted | multi-validator ceremony |

## Post-launch cleanup (chain-sdk)

Once no live chain relies on legacy `uakt`/`uact` on-chain params, remove the
compatibility aliases:
- `chain-sdk/go/node/deployment/v1beta4/params.go` — `MinDepositFor` legacy branch
- `chain/x/market/handler/server.go` — bid-deposit `uaba`→`uakt` alias
