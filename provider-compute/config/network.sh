# Abakos network profile — source from provider-compute scripts.
# Same binaries and flows for sandbox and mainnet; only endpoints/keys differ.
#
#   export ABA_NETWORK=mainnet   # after abakos-1 launch
#   export ABA_NETWORK=sandbox   # default (live testnet)
#
# Override any variable before sourcing or in the environment.

ABA_NETWORK="${ABA_NETWORK:-sandbox}"

case "$ABA_NETWORK" in
  sandbox)
    : "${ABA_CHAIN_ID:=abakos-sandbox-1}"
    : "${ABA_RPC:=https://rpc.abakos.ai:443}"
    : "${ABA_REST:=https://rest.abakos.ai}"
    : "${ABA_FAUCET:=https://explorer.abakos.ai/faucet}"
    : "${ABA_EXPLORER:=https://explorer.abakos.ai}"
    : "${ABA_KEYRING_BACKEND:=test}"
    : "${ABA_GAS_PRICES:=0uaba}"
  ;;
  mainnet)
    : "${ABA_CHAIN_ID:=abakos-1}"
    : "${ABA_RPC:=https://rpc.abakos.ai:443}"
    : "${ABA_REST:=https://rest.abakos.ai}"
    : "${ABA_FAUCET:=}"
    : "${ABA_EXPLORER:=https://explorer.abakos.ai}"
    : "${ABA_KEYRING_BACKEND:=file}"
    : "${ABA_GAS_PRICES:=0uaba}"
  ;;
  *)
    echo "!! unknown ABA_NETWORK=$ABA_NETWORK (use sandbox or mainnet)" >&2
    return 1 2>/dev/null || exit 1
  ;;
esac

# Provider / lease DNS (mainnet-style: real domain under abakos.ai, not .local)
: "${ABA_PROVIDER_DOMAIN:=${DOMAIN:-provider.abakos.ai}}"
: "${ABA_LEASE_DOMAIN:=${ABA_PROVIDER_DOMAIN}}"
: "${ABA_PROVIDER_GATEWAY_PORT:=8443}"
: "${ABA_PROVIDER_GRPC_PORT:=8444}"

# Marketplace economics (same on sandbox and mainnet — uaba only)
: "${ABA_BID_DEPOSIT:=5000000uaba}"
: "${ABA_DEPLOY_DEPOSIT:=5000000uaba}"
: "${ABA_MIN_DEPOSIT_BLOCKS:=500000}"

# Public gateway URL for tenants (send-manifest / lease-status)
if [ -z "${ABA_PROVIDER_URL:-}" ]; then
  if [ -n "${HOST_URI:-}" ]; then
    ABA_PROVIDER_URL="$HOST_URI"
  else
  _pub="${PUBLIC_IP:-}"
  if [ -z "$_pub" ]; then
    _pub="$(curl -4sf --max-time 3 ifconfig.me 2>/dev/null || true)"
  fi
  if [ -z "$_pub" ]; then
    _pub="$(hostname -I 2>/dev/null | awk '{print $1}')"
  fi
  if [ -n "$_pub" ]; then
    ABA_PROVIDER_URL="https://${_pub}:${ABA_PROVIDER_GATEWAY_PORT}"
  fi
  fi
fi

# SDL example hostname: hello.<lease-domain>
: "${ABA_EXAMPLE_SERVICE_HOST:=hello.${ABA_LEASE_DOMAIN}}"

export ABA_NETWORK ABA_CHAIN_ID ABA_RPC ABA_REST ABA_FAUCET ABA_EXPLORER
export ABA_KEYRING_BACKEND ABA_GAS_PRICES
export ABA_PROVIDER_DOMAIN ABA_LEASE_DOMAIN
export ABA_PROVIDER_GATEWAY_PORT ABA_PROVIDER_GRPC_PORT
export ABA_BID_DEPOSIT ABA_DEPLOY_DEPOSIT ABA_MIN_DEPOSIT_BLOCKS
export ABA_PROVIDER_URL ABA_EXAMPLE_SERVICE_HOST
