#!/usr/bin/env bash
# Re-genesis the Abakos SANDBOX (wipe + fresh ABA-only genesis, 10-min gov).
# Run on the sandbox validator as root. Idempotent-safe: backs up first and
# auto-rolls-back if the patched genesis fails validation.
#
# Strategy: patch the existing height-0 genesis.json (preserves EVM/wasm/module
# wiring, chain-id, validator key, faucet + genesis accounts) and only:
#   - reduce to a single native coin (uaba / ABA), drop ACT (uact)
#   - force deployment/market min-deposits to uaba
#   - set governance voting to ~10 minutes (fast sandbox iteration)
#   - reset chain state to height 0 (wipes deployments/leases/runtime balances)
#
# After this runs, re-fund a tenant via faucet, re-register the provider on the
# VM, and re-run the E2E (see provider-compute).
set -euo pipefail

CHAIN_ID="${CHAIN_ID:-abakos-sandbox-1}"
BIN="${BIN:-$(command -v abakosd || echo /usr/local/bin/abakosd)}"
HOME_DIR="${HOME_DIR:-/root/.abakos}"
GEN="$HOME_DIR/config/genesis.json"
TS="$(date -u +%Y%m%d-%H%M%S)"
BAK="$HOME_DIR.bak.$TS"

log(){ echo "[regenesis] $*"; }
die(){ echo "[regenesis][FATAL] $*" >&2; exit 1; }

[ "$(id -u)" = "0" ] || die "run as root"
command -v jq >/dev/null || die "jq required (apt-get install -y jq)"
[ -x "$BIN" ] || die "abakosd not found at $BIN"
[ -f "$GEN" ] || die "genesis not found at $GEN"

# --- detect systemd unit running the node ---
SVC="${SVC:-}"
if [ -z "$SVC" ]; then
  for c in abakosd abakos-validator cosmovisor abakos; do
    if systemctl list-units --type=service --all 2>/dev/null | grep -q "${c}.service"; then SVC="$c"; break; fi
  done
fi
log "chain=$CHAIN_ID bin=$BIN home=$HOME_DIR service=${SVC:-<none>}"

# --- stop node ---
if [ -n "$SVC" ]; then log "stopping $SVC"; systemctl stop "$SVC" || true; sleep 2; fi
pkill -f "$BIN start" 2>/dev/null || true; sleep 1

# --- backup whole home (config + data + keys) ---
log "backup -> $BAK"
cp -a "$HOME_DIR" "$BAK"

# --- patch genesis.json (guarded: only touch keys that exist) ---
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
TMP="$(mktemp)"
jq --arg now "$NOW" '
  .genesis_time = $now

  # single native coin: keep only uaba metadata, drop ACT
  | (if (.app_state.bank | has("denom_metadata"))
       then .app_state.bank.denom_metadata |= map(select(.base=="uaba"))
       else . end)
  | .app_state.bank.send_enabled = [ {"denom":"uaba","enabled":true} ]

  # deployment escrow: uaba only
  | (if (.app_state.deployment.params | has("min_deposits"))
       then .app_state.deployment.params.min_deposits = [ {"denom":"uaba","amount":"500000"} ]
       else . end)

  # market bid deposit: uaba only (handle both singular + plural forms)
  | (if (.app_state.market.params | has("bid_min_deposit"))
       then .app_state.market.params.bid_min_deposit = {"denom":"uaba","amount":"500000"}
       else . end)
  | (if (.app_state.market.params | has("bid_min_deposits"))
       then .app_state.market.params.bid_min_deposits = [ {"denom":"uaba","amount":"500000"} ]
       else . end)

  # fast sandbox governance (~10 min instead of 24h)
  | (if (.app_state.gov | has("params")) then
        .app_state.gov.params.voting_period = "600s"
      | .app_state.gov.params.expedited_voting_period = "300s"
      | .app_state.gov.params.max_deposit_period = "600s"
     else . end)

  # ABA-only: no oracle feeder => BME can never mint uact (kills the ACT path)
  | (if (.app_state | has("oracle")) and (.app_state.oracle | has("params")) and (.app_state.oracle.params | has("sources"))
       then .app_state.oracle.params.sources = []
       else . end)
' "$GEN" > "$TMP" || die "jq patch failed"

mv "$TMP" "$GEN"

# --- validate (auto-rollback on failure) ---
log "validating patched genesis"
if ! ( "$BIN" genesis validate --home "$HOME_DIR" 2>/dev/null \
     || "$BIN" genesis validate-genesis --home "$HOME_DIR" 2>/dev/null \
     || "$BIN" validate-genesis "$GEN" 2>/dev/null ); then
  log "VALIDATION FAILED -> restoring backup"
  rm -rf "$HOME_DIR"; mv "$BAK" "$HOME_DIR"
  die "patched genesis invalid; original restored (no wipe performed)"
fi

# --- reset state to height 0 ---
log "resetting chain state"
"$BIN" comet unsafe-reset-all --home "$HOME_DIR" --keep-addr-book 2>/dev/null \
  || "$BIN" tendermint unsafe-reset-all --home "$HOME_DIR" --keep-addr-book 2>/dev/null \
  || die "unsafe-reset-all failed"

# --- start node ---
if [ -n "$SVC" ]; then
  log "starting $SVC"; systemctl start "$SVC"
else
  log "no systemd unit detected -> start manually: $BIN start --home $HOME_DIR"
fi

cat <<EOF

[regenesis] done.
  chain-id : $CHAIN_ID (fresh, height 0)
  genesis  : single coin uaba, deployment/market = uaba, gov voting = 10min
  backup   : $BAK   (rollback: systemctl stop ${SVC:-abakosd}; rm -rf $HOME_DIR; mv $BAK $HOME_DIR; systemctl start ${SVC:-abakosd})

Next:
  - confirm blocks:  $BIN status --home $HOME_DIR | jq .sync_info
  - re-fund tenant via faucet, re-register provider on the VM, re-run E2E
EOF
