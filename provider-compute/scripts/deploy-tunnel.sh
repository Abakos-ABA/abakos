#!/usr/bin/env bash
# Deploy provider tunnel + update host URI
#
# This script automates the provider tunnel setup and on-chain host URI registration.
#
# Usage:
#   bash scripts/deploy-tunnel.sh [--validate-only] [--dns DNS_NAME]
#
# Options:
#   --validate-only    Run checks but don't modify systemd/on-chain
#   --dns DNS_NAME     Skip tunnel, directly update to DNS name (e.g., provider.abakos.ai)
#
# Environment:
#   TUNNEL_HOST        SSH reverse tunnel target (default: 217.154.169.211)
#   TUNNEL_USER        SSH user on TUNNEL_HOST (default: root)
#   TUNNEL_KEY         SSH key path (default: ~/.ssh/abakos_tunnel)
#   PROVIDER_KEY       Keyring key name (default: provider)
#   ABA_NETWORK        Network name (default: sandbox)
#
# Prerequisites:
#   - abakosd in PATH
#   - Provider key in keyring
#   - SSH connectivity to TUNNEL_HOST
#   - abakos repo at ~/abakos (or $ABA_REPO)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERE="$SCRIPT_DIR"

# Source network config if available
if [ -f "$HERE/provider-compute/config/network.sh" ]; then
  source "$HERE/provider-compute/config/network.sh"
fi

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Defaults
TUNNEL_HOST="${TUNNEL_HOST:-217.154.169.211}"
TUNNEL_USER="${TUNNEL_USER:-root}"
TUNNEL_KEY="${TUNNEL_KEY:-$HOME/.ssh/abakos_tunnel}"
PROVIDER_KEY="${PROVIDER_KEY:-provider}"
ABA_NETWORK="${ABA_NETWORK:-sandbox}"
VALIDATE_ONLY=false
DNS_NAME=""

# Parse args
for arg in "$@"; do
  case "$arg" in
    --validate-only) VALIDATE_ONLY=true ;;
    --dns)
      shift
      DNS_NAME="$1"
      ;;
    *) echo "Unknown arg: $arg"; exit 1 ;;
  esac
done

log_info() { echo -e "${BLUE}==>${NC} $*"; }
log_ok() { echo -e "${GREEN}✓${NC} $*"; }
log_warn() { echo -e "${YELLOW}⚠${NC} $*"; }
log_error() { echo -e "${RED}✗${NC} $*"; exit 1; }

log_info "Provider Tunnel Deployment"
echo "  Network: $ABA_NETWORK"
echo "  Tunnel target: $TUNNEL_USER@$TUNNEL_HOST"
echo "  Validate only: $VALIDATE_ONLY"
if [ -n "$DNS_NAME" ]; then
  echo "  DNS mode: $DNS_NAME"
fi
echo ""

# ===== VALIDATION =====
log_info "Validation checks..."

# Check abakosd
if ! command -v abakosd &>/dev/null; then
  log_error "abakosd not found in PATH"
fi
log_ok "abakosd found"

# Check provider key
if ! abakosd keys list --keyring-backend file | grep -q "$PROVIDER_KEY"; then
  log_error "Provider key '$PROVIDER_KEY' not in keyring"
fi
PROVIDER_ADDR=$(abakosd keys show "$PROVIDER_KEY" -a --keyring-backend file)
log_ok "Provider account: $PROVIDER_ADDR"

# Check network config
if [ -z "${ABA_CHAIN_ID:-}" ] || [ -z "${ABA_RPC:-}" ]; then
  log_warn "Network config not loaded; using defaults"
  ABA_CHAIN_ID="${ABA_CHAIN_ID:-abakos-sandbox-1}"
  ABA_RPC="${ABA_RPC:-https://rpc.abakos.ai}"
  ABA_KEYRING_BACKEND="${ABA_KEYRING_BACKEND:-file}"
  ABA_GAS_PRICES="${ABA_GAS_PRICES:-0uaba}"
fi
log_ok "Network: $ABA_CHAIN_ID ($ABA_RPC)"

# Check provider is registered on-chain
if ! abakosd query provider get "$PROVIDER_ADDR" --node "$ABA_RPC" &>/dev/null; then
  log_warn "Provider not yet registered on-chain"
  log_info "Run: abakosd tx provider create provider-register.yaml --from $PROVIDER_KEY"
else
  CURRENT_HOST_URI=$(abakosd query provider get "$PROVIDER_ADDR" --node "$ABA_RPC" -o json | jq -r '.host_uri // "none"')
  log_ok "Provider registered (current host_uri: $CURRENT_HOST_URI)"
fi

# SSH connectivity (unless DNS mode)
if [ -z "$DNS_NAME" ]; then
  if ! ssh -i "$TUNNEL_KEY" -o BatchMode=yes -o ConnectTimeout=5 "$TUNNEL_USER@$TUNNEL_HOST" "hostname" &>/dev/null; then
    log_warn "SSH connectivity test failed"
    echo "Ensure:"
    echo "  1. Outbound SSH (22) to $TUNNEL_HOST is open"
    echo "  2. SSH key exists at $TUNNEL_KEY"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
      exit 1
    fi
  else
    log_ok "SSH connectivity verified"
  fi
fi

log_ok "All validation checks passed"

# ===== TUNNEL SETUP (unless DNS mode or validate-only) =====
if [ -z "$DNS_NAME" ] && [ "$VALIDATE_ONLY" = "false" ]; then
  log_info "Setting up SSH reverse tunnel..."
  
  # Run tunnel setup script
  if [ ! -f "$HERE/provider-compute/scripts/tunnel-remote.sh" ]; then
    log_error "tunnel-remote.sh not found at $HERE/provider-compute/scripts/"
  fi
  
  export TUNNEL_HOST TUNNEL_USER TUNNEL_KEY
  bash "$HERE/provider-compute/scripts/tunnel-remote.sh"
  
  log_ok "Tunnel setup complete"
fi

# ===== HOST URI UPDATE =====
if [ "$VALIDATE_ONLY" = "true" ]; then
  log_info "Validate-only mode: skipping on-chain update"
else
  log_info "Updating host URI on-chain..."
  
  if [ -z "$DNS_NAME" ]; then
    HOST_URI="https://$TUNNEL_HOST:8443"
  else
    HOST_URI="https://$DNS_NAME:8443"
  fi
  
  log_info "Host URI: $HOST_URI"
  
  if [ ! -f "$HERE/provider-compute/scripts/40-update-host-uri.sh" ]; then
    log_error "40-update-host-uri.sh not found at $HERE/provider-compute/scripts/"
  fi
  
  export HOST_URI PROVIDER_KEY
  export REGISTER_YAML="$HERE/provider-compute/provider-register.local.yaml"
  export DAEMON_YAML="$HERE/provider-compute/provider.local.yaml"
  bash "$HERE/provider-compute/scripts/40-update-host-uri.sh"
  
  log_ok "Host URI updated on-chain"
fi

# ===== SUMMARY =====
echo ""
log_info "=========================================="
log_ok "Tunnel deployment complete!"
echo ""

if [ "$VALIDATE_ONLY" = "false" ]; then
  if [ -z "$DNS_NAME" ]; then
    echo "Current status:"
    echo "  - SSH tunnel: $(systemctl is-active abakos-provider-tunnel || echo 'inactive')"
    echo "  - Host URI: $(abakosd query provider get "$PROVIDER_ADDR" --node "$ABA_RPC" -o json | jq -r '.host_uri')"
    echo ""
    echo "Next steps:"
    echo "  1. Wait 1-2 minutes for tunnel to stabilize"
    echo "  2. Test connectivity:"
    echo "     curl -sk https://$TUNNEL_HOST:8443/status"
    echo "  3. Verify with:"
    echo "     abakosd query provider get $PROVIDER_ADDR --node $ABA_RPC -o json | jq '.host_uri'"
    echo "  4. When DNS ready, re-run with:"
    echo "     bash scripts/deploy-tunnel.sh --dns provider.abakos.ai"
  else
    echo "DNS mode:"
    echo "  Host URI: $HOST_URI"
    echo "  Updated on-chain: ✓"
    echo "  Next: test with curl -sk $HOST_URI/status"
  fi
else
  echo "Validation mode: no changes made"
  echo "To proceed: bash scripts/deploy-tunnel.sh"
fi
