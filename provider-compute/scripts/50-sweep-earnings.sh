#!/usr/bin/env bash
# Step 5 (Ebene 1): sweep the operator/provider key's lease earnings home to the
# main account. Provider lease income lands in the provider-owner key (Akash has
# no provider withdraw-address); this moves the free (spendable) balance to your
# main wallet on a schedule, keeping a reserve for bid deposits + safety.
#
# SAFE BY DEFAULT: dry-run unless ABA_SWEEP_APPLY=1. Never touches escrowed
# deposits (those aren't "spendable"); only sweeps spendable minus the reserve.
#
#   ABA_SWEEP_DEST   (required) main account to receive earnings (abakos1...)
#   ABA_SWEEP_KEY    provider/operator key name in the VM keyring (default: provider)
#   ABA_SWEEP_RESERVE_UABA  keep this much for future bid deposits + safety
#                           (default 25000000 = 25 ABA; set 0 once sponsoring is live)
#   ABA_SWEEP_MIN_UABA      don't bother sending below this (default 1000000 = 1 ABA)
#   ABA_SWEEP_APPLY=1       actually broadcast (otherwise dry-run only)
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=/dev/null
source "$HERE/config/network.sh"

KEY="${ABA_SWEEP_KEY:-${PROVIDER_KEY:-provider}}"
DEST="${ABA_SWEEP_DEST:-}"
RESERVE="${ABA_SWEEP_RESERVE_UABA:-25000000}"
MIN="${ABA_SWEEP_MIN_UABA:-1000000}"
APPLY="${ABA_SWEEP_APPLY:-0}"

if [ -z "$DEST" ]; then
  echo "!! ABA_SWEEP_DEST is required (your main account, abakos1...)." >&2
  echo "   e.g. export ABA_SWEEP_DEST=abakos1cy93rz4spyy4n84hmklclvc7ay9dk8kf37u725" >&2
  exit 1
fi
[[ "$DEST" == abakos1* ]] || { echo "!! ABA_SWEEP_DEST must be an abakos1 address" >&2; exit 1; }

FROM="$(abakosd keys show "$KEY" -a --keyring-backend "$ABA_KEYRING_BACKEND" 2>/dev/null || true)"
[ -n "$FROM" ] || { echo "!! key '$KEY' not found in keyring ($ABA_KEYRING_BACKEND)" >&2; exit 1; }
if [ "$FROM" = "$DEST" ]; then
  echo "== operator key already equals dest ($FROM) — nothing to sweep (Ebene 2 setup?)."
  exit 0
fi

spendable_uaba() {
  abakosd query bank spendable-balances "$1" --node "$ABA_RPC" -o json 2>/dev/null \
    | jq -r '[.balances[]? | select(.denom=="uaba") | .amount] | first // "0"'
}

BAL="$(spendable_uaba "$FROM")"
SEND=$(( BAL - RESERVE ))

echo "== sweep earnings =="
echo "   from (operator): $FROM"
echo "   to   (main):     $DEST"
echo "   spendable:       ${BAL}uaba   reserve: ${RESERVE}uaba   min: ${MIN}uaba"

if [ "$SEND" -lt "$MIN" ]; then
  echo "   -> nothing to sweep (spendable-reserve = ${SEND}uaba < ${MIN}uaba). done."
  exit 0
fi

echo "   -> would send: ${SEND}uaba"
if [ "$APPLY" != "1" ]; then
  echo "   DRY-RUN (set ABA_SWEEP_APPLY=1 to broadcast). Command:"
  echo "     abakosd tx bank send $FROM $DEST ${SEND}uaba \\"
  echo "       --chain-id $ABA_CHAIN_ID --node $ABA_RPC --keyring-backend $ABA_KEYRING_BACKEND \\"
  echo "       --gas auto --gas-adjustment 1.4 --gas-prices $ABA_GAS_PRICES -y -o json"
  exit 0
fi

abakosd tx bank send "$FROM" "$DEST" "${SEND}uaba" \
  --chain-id "$ABA_CHAIN_ID" --node "$ABA_RPC" --keyring-backend "$ABA_KEYRING_BACKEND" \
  --gas auto --gas-adjustment 1.4 --gas-prices "$ABA_GAS_PRICES" -y -o json \
  | jq '{txhash, code, raw_log}'
echo "== swept ${SEND}uaba -> $DEST =="
