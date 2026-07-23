#!/usr/bin/env bash
# Update on-chain provider host_uri (and local yaml copies).
#
# Usage (on the provider VM, keyring already has `provider`):
#   HOST_URI=https://217.154.169.211:8443 bash scripts/40-update-host-uri.sh
#
# Optional:
#   PROVIDER_KEY=provider
#   REGISTER_YAML=~/abakos/provider-compute/provider-register.local.yaml
#   DAEMON_YAML=~/abakos/provider-compute/provider.local.yaml
#
# Does not restart abakos-provider: host_uri is on-chain discovery for tenants;
# the daemon listens locally and is reached via tunnel/DNS independently.
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=/dev/null
source "$HERE/config/network.sh"

HOST_URI="${HOST_URI:?set HOST_URI e.g. https://217.154.169.211:8443}"
KEY="${PROVIDER_KEY:-provider}"
REGISTER_YAML="${REGISTER_YAML:-$HERE/provider-register.local.yaml}"
DAEMON_YAML="${DAEMON_YAML:-$HERE/provider.local.yaml}"

TX=(--chain-id "$ABA_CHAIN_ID" --node "$ABA_RPC" --keyring-backend "$ABA_KEYRING_BACKEND"
    --gas auto --gas-adjustment 1.4 --gas-prices "$ABA_GAS_PRICES" -y -o json)

echo "== network: $ABA_NETWORK chain=$ABA_CHAIN_ID =="
echo "== HOST_URI: $HOST_URI =="

ADDR="$(abakosd keys show "$KEY" -a --keyring-backend "$ABA_KEYRING_BACKEND")"
echo "provider: $ADDR"

if [ ! -f "$REGISTER_YAML" ]; then
  echo "== creating $REGISTER_YAML from template =="
  sed "s|https://HOST_IP:8443|$HOST_URI|" "$HERE/provider-register.yaml" > "$REGISTER_YAML"
else
  echo "== updating host in $REGISTER_YAML =="
  python3 - "$REGISTER_YAML" "$HOST_URI" <<'PY'
import pathlib, re, sys
path = pathlib.Path(sys.argv[1])
uri = sys.argv[2]
text = path.read_text()
if re.search(r'^host:\s*', text, re.M):
    text = re.sub(r'^host:\s*".*"', f'host: "{uri}"', text, count=1, flags=re.M)
else:
    text = f'host: "{uri}"\n' + text
path.write_text(text)
print(path.read_text())
PY
fi

if [ -f "$DAEMON_YAML" ]; then
  echo "== updating host_uri in $DAEMON_YAML =="
  python3 - "$DAEMON_YAML" "$HOST_URI" <<'PY'
import pathlib, re, sys
path = pathlib.Path(sys.argv[1])
uri = sys.argv[2]
text = path.read_text()
if re.search(r'^host_uri:\s*', text, re.M):
    text = re.sub(r'^host_uri:\s*".*"', f'host_uri: "{uri}"', text, count=1, flags=re.M)
else:
    text = text.rstrip() + f'\nhost_uri: "{uri}"\n'
path.write_text(text)
print("host_uri line:", [ln for ln in path.read_text().splitlines() if "host_uri" in ln][0])
PY
else
  echo "== skip daemon yaml (missing $DAEMON_YAML) =="
fi

echo "== tx provider update =="
abakosd tx provider update "$REGISTER_YAML" --from "$KEY" "${TX[@]}"
sleep 6

echo "== verify =="
abakosd query provider get "$ADDR" --node "$ABA_RPC" -o json | jq '{owner, host_uri, attributes}'

cat <<EOF

Updated on-chain host_uri to:
  $HOST_URI

When DNS is ready, re-run with:
  HOST_URI=https://provider.abakos.ai:8443 bash scripts/40-update-host-uri.sh

IONOS A record (manual): provider.abakos.ai -> 217.154.169.211
EOF
