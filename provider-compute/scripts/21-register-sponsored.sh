#!/usr/bin/env bash
# Step 3 (self-service, multi-user): register THIS host as its own provider with a
# hidden, auto-generated operator key that holds ZERO ABA. Bid deposits are paid by
# the host owner's OWN wallet through a capped DepositAuthorization grant — so a new
# host needs no starting capital, and there is no shared provider address and no
# project treasury involved. Each user runs their own provider, funded by their own
# wallet, capped by their own "Max ABA for hosting" limit.
#
# How it fits together:
#   * operator key (here, hidden on the host)  = the provider identity / bid signer
#   * host owner's main wallet (in the Desktop app) = the SPONSOR (granter)
#   * DepositAuthorization(scope=bid, spend_limit=X) lets the daemon pull each 5-ABA
#     bid deposit from the main wallet, capped at X, revolving (returned on close).
#   * the provider daemon must bid with deposit sources `grant,balance`
#     (scripts/10-build-provider.sh already patches the bid engine for this).
#
# Gas is 0 on Abakos, so a 0-balance operator can publish its cert and register.
#
#   ABA_SPONSOR_FROM   (optional) main-wallet key name IN THIS KEYRING to auto-issue
#                      the grant from here. Normally you leave this UNSET and sign the
#                      grant from the Desktop wallet (Host tab) instead — the main key
#                      does not belong on the host.
#   ABA_SPONSOR_MAX_ABA   spend cap for the grant (default 25 = ~5 simultaneous bids).
#   PROVIDER_KEY       operator key name (default: provider).
#   HOST_URI           public gateway (https://IP:8443) — required.
#
#   HOST_URI=https://1.2.3.4:8443 bash scripts/21-register-sponsored.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=/dev/null
source "$HERE/config/network.sh"

KEY="${PROVIDER_KEY:-provider}"
DOMAIN="$ABA_PROVIDER_DOMAIN"
HOST_URI="${HOST_URI:-$ABA_PROVIDER_URL}"
[ -n "$HOST_URI" ] || { echo "!! set HOST_URI or ensure PUBLIC_IP is reachable" >&2; exit 1; }
MAX_ABA="${ABA_SPONSOR_MAX_ABA:-25}"
LIMIT_UABA="$(awk -v a="$MAX_ABA" 'BEGIN{printf "%d", a*1000000}')"

TX="--chain-id $ABA_CHAIN_ID --node $ABA_RPC --keyring-backend $ABA_KEYRING_BACKEND --gas auto --gas-adjustment 1.4 --gas-prices $ABA_GAS_PRICES -y -o json"

echo "== self-service sponsored provider | network=$ABA_NETWORK domain=$DOMAIN =="
echo "== gateway: $HOST_URI =="

echo "== [1/5] operator key ($KEY) — auto-generated, holds 0 ABA =="
if ! abakosd keys show "$KEY" -a --keyring-backend "$ABA_KEYRING_BACKEND" >/dev/null 2>&1; then
  abakosd keys add "$KEY" --keyring-backend "$ABA_KEYRING_BACKEND" >/dev/null
  echo "   generated new operator key"
fi
ADDR="$(abakosd keys show "$KEY" -a --keyring-backend "$ABA_KEYRING_BACKEND")"
[[ "$ADDR" == abakos1* ]] || { echo "!! operator address is not abakos1..." >&2; exit 1; }
echo "   operator (provider) address: $ADDR"

# NOTE: deliberately NO funding wait. Deposits come from the sponsor grant; gas is 0.

echo "== [2/5] provider config files =="
sed -e "s|PROVIDER_ADDRESS|$ADDR|g" \
    -e "s|ABA_RPC_PLACEHOLDER|$ABA_RPC|g" \
    -e "s|ABA_CHAIN_ID_PLACEHOLDER|$ABA_CHAIN_ID|g" \
    -e "s|ABA_KEYRING_PLACEHOLDER|$ABA_KEYRING_BACKEND|g" \
    -e "s|ABA_PROVIDER_DOMAIN_PLACEHOLDER|$DOMAIN|g" \
    -e "s|ABA_HOST_URI_PLACEHOLDER|$HOST_URI|g" \
  "$HERE/provider.yaml" > "$HERE/provider.local.yaml"
sed "s|https://HOST_IP:8443|$HOST_URI|" "$HERE/provider-register.yaml" > "$HERE/provider-register.local.yaml"

echo "== [3/5] server certificate (0-fee, works at 0 balance) =="
abakosd tx cert generate server "$DOMAIN" --from "$KEY" $TX 2>/dev/null || true
abakosd tx cert publish server --from "$KEY" $TX 2>/dev/null || true
sleep 6

echo "== [4/5] register provider on-chain =="
abakosd tx provider create "$HERE/provider-register.local.yaml" --from "$KEY" $TX | jq '{txhash, code}' 2>/dev/null || \
  abakosd tx provider create "$HERE/provider-register.local.yaml" --from "$KEY" $TX
sleep 6
abakosd query provider get "$ADDR" --node "$ABA_RPC" -o json | jq '.provider.host_uri // .' 2>/dev/null || true

echo "== [5/5] deposit sponsorship (capped, from the host owner's own wallet) =="
if [ -n "${ABA_SPONSOR_FROM:-}" ]; then
  # CLI power-user path: the main wallet key is in this keyring, grant directly.
  echo "   granting ${MAX_ABA} ABA bid-deposit authorization: ${ABA_SPONSOR_FROM} -> ${ADDR}"
  abakosd tx authz grant "$ADDR" deposit --scope bid --spend-limit "${LIMIT_UABA}uaba" \
    --from "$ABA_SPONSOR_FROM" $TX | jq '{txhash, code}' 2>/dev/null || \
    echo "   !! grant failed — check 'abakosd tx authz grant --help' for the deposit-scope flags on this build"
else
  cat <<EOF
   Operator holds 0 ABA on purpose. Authorize its bid deposits from YOUR main wallet:

   Desktop (recommended): Host tab -> "Hosting budget" -> paste operator address
     ${ADDR}
     set Max ABA (= ${MAX_ABA}) -> "Activate hosting" (signs the grant from your wallet).

   or CLI (if your main key is here):
     abakosd tx authz grant ${ADDR} deposit --scope bid --spend-limit ${LIMIT_UABA}uaba \\
       --from <your-main-key> --chain-id ${ABA_CHAIN_ID} --node ${ABA_RPC} \\
       --keyring-backend ${ABA_KEYRING_BACKEND} --gas auto --gas-adjustment 1.4 \\
       --gas-prices ${ABA_GAS_PRICES} -y
EOF
fi

cat <<EOF

Done. This host is a provider under its OWN operator key ($ADDR), with 0 balance.
Once the grant is active, each 5-ABA bid deposit is pulled from your main wallet,
capped at ${MAX_ABA} ABA at any time, and returned when the lease closes.
Kill-switch: revoke the authorization (Desktop "Revoke", or 'abakosd tx authz revoke').
Sweep lease income home with scripts/51-install-sweep.sh.
Next: bash scripts/30-test-deploy.sh
EOF
