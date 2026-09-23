#!/usr/bin/env bash
# Step 6b: install the huge-page-aware host miner as a systemd service. Runs xmrig
# against the Abakos proxy (mine.abakos.ai) in RandomX FAST mode with 1 GiB pages
# (if reserved) and the MSR mod — so this provider host mints ABA at full hashrate,
# survives reboots, and restarts on crash.
#
# Reserve the pages FIRST (or let this script do it): scripts/60-hugepages.sh.
#
#   ABA_MINER_ADDR    abakos1... to credit (default: /etc/abakos/sweep.env
#                     ABA_SWEEP_DEST, else the 'provider' key's address).
#   ABA_MINER_WORKER  rig label (default: this host's short name). Sent as
#                     user=ADDR.WORKER; forward-compatible with worker-labels.
#   ABA_MINER_POOL    stratum endpoint (default: mine.abakos.ai:3355).
#   ABA_MINER_KEY     keyring key to derive the address from (default: provider).
#   ABA_MINER_MSR=0   disable the MSR mod (default: on when /dev/cpu/*/msr exists).
#   ABA_MINER_MAX_CPU percent of cores to mine with (default: unset = all). Lower
#                     it (e.g. 75) to leave headroom for paid tenant leases.
#   ABA_XMRIG         path to an existing xmrig binary (skips the download).
#   ABA_HUGEPAGES_AUTO=1  run scripts/60-hugepages.sh now if no pages are reserved.
#
#   sudo -E bash scripts/61-install-miner.sh
set -euo pipefail

[ "$(id -u)" = 0 ] || { echo "!! run as root: sudo -E bash scripts/61-install-miner.sh" >&2; exit 1; }

HERE="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=/dev/null
source "$HERE/config/network.sh"

RUN_USER="${SUDO_USER:-root}"
RUN_HOME="$(getent passwd "$RUN_USER" 2>/dev/null | cut -d: -f6)"; RUN_HOME="${RUN_HOME:-$HOME}"
KEY="${ABA_MINER_KEY:-provider}"
POOL="${ABA_MINER_POOL:-mine.abakos.ai:3355}"

# ---------------------------------------------------------------- payout address
ADDR="${ABA_MINER_ADDR:-}"
if [ -z "$ADDR" ] && [ -f /etc/abakos/sweep.env ]; then
  ADDR="$(sed -n 's/^ABA_SWEEP_DEST=//p' /etc/abakos/sweep.env | head -n1)"
  [ -n "$ADDR" ] && echo "   using ABA_SWEEP_DEST from /etc/abakos/sweep.env as payout address"
fi
if [ -z "$ADDR" ]; then
  ADDR="$(sudo -u "$RUN_USER" env HOME="$RUN_HOME" abakosd keys show "$KEY" -a --keyring-backend "$ABA_KEYRING_BACKEND" 2>/dev/null || true)"
  [ -n "$ADDR" ] && echo "   derived payout address from key '$KEY'"
fi
[ -n "$ADDR" ] || { echo "!! no address — set ABA_MINER_ADDR=abakos1..." >&2; exit 1; }
[[ "$ADDR" == abakos1* ]] || { echo "!! ABA_MINER_ADDR must be an abakos1 address (got: $ADDR)" >&2; exit 1; }

# ---------------------------------------------------------------- worker label
raw_worker="${ABA_MINER_WORKER:-$(hostname -s 2>/dev/null || hostname 2>/dev/null || echo host)}"
WORKER="$(printf '%s' "$raw_worker" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9' | cut -c1-16)"
[ -n "$WORKER" ] || WORKER="host"

echo "== host miner =="
echo "   payout:  $ADDR"
echo "   worker:  $WORKER   (login = ${ADDR}.${WORKER})"
echo "   pool:    $POOL"

# ---------------------------------------------------------------- huge pages check
HP_TOTAL="$(awk '/^HugePages_Total:/{print $2}' /proc/meminfo)"
if [ "${HP_TOTAL:-0}" = "0" ]; then
  if [ "${ABA_HUGEPAGES_AUTO:-0}" = "1" ]; then
    echo "== no huge pages reserved — running scripts/60-hugepages.sh =="
    bash "$HERE/scripts/60-hugepages.sh"
    HP_TOTAL="$(awk '/^HugePages_Total:/{print $2}' /proc/meminfo)"
  else
    echo "   !! WARNING: 0 huge pages reserved — xmrig will fall back to slow mode."
    echo "      Run 'sudo -E bash scripts/60-hugepages.sh' first (or ABA_HUGEPAGES_AUTO=1)."
  fi
fi
# 1 GiB pages present? (needs 60-hugepages.sh ABA_HUGEPAGES_1G + a reboot)
ONEGB_FILE=/sys/kernel/mm/hugepages/hugepages-1048576kB/nr_hugepages
ONEGB="false"; [ -r "$ONEGB_FILE" ] && [ "$(cat "$ONEGB_FILE" 2>/dev/null || echo 0)" -gt 0 ] && ONEGB="true"
# MSR available?
MSR="true"; [ "${ABA_MINER_MSR:-1}" = "0" ] && MSR="false"
[ -e /dev/cpu/0/msr ] || { modprobe msr 2>/dev/null || true; }
[ -e /dev/cpu/0/msr ] || { [ "$MSR" = "true" ] && echo "   (no /dev/cpu/0/msr — MSR mod may be a no-op)"; }
echo "   tuning:  mode=fast 1gb-pages=$ONEGB msr=$MSR"

# ---------------------------------------------------------------- xmrig binary
XMRIG="${ABA_XMRIG:-}"
if [ -n "$XMRIG" ] && [ -x "$XMRIG" ]; then
  echo "== using existing xmrig: $XMRIG =="
else
  DEST=/opt/abakos/xmrig
  install -d -m 0755 "$DEST"
  found="$(find "$DEST" -maxdepth 2 -type f -name xmrig 2>/dev/null | head -n1 || true)"
  if [ -n "$found" ]; then
    XMRIG="$found"
    echo "== using xmrig from previous install: $XMRIG =="
  else
    echo "== download xmrig (official xmrig/xmrig release) =="
    command -v jq >/dev/null 2>&1 || { echo "!! jq required to resolve the release" >&2; exit 1; }
    REL="$(curl -fsSL -H 'Accept: application/vnd.github+json' https://api.github.com/repos/xmrig/xmrig/releases/latest)"
    URL="$(echo "$REL" | jq -r '.assets[].browser_download_url | select(test("linux-static-x64.*\\.tar\\.gz$"))' | head -n1)"
    [ -n "$URL" ] || URL="$(echo "$REL" | jq -r '.assets[].browser_download_url | select(test("linux-x64.*\\.tar\\.gz$"))' | head -n1)"
    [ -n "$URL" ] || { echo "!! no linux x64 tarball in the latest xmrig release" >&2; exit 1; }
    TAR="$DEST/$(basename "$URL")"
    echo "   $URL"
    curl -fSL -o "$TAR" "$URL"
    # Best-effort integrity check against the release SHA256SUMS (guards a corrupt download).
    SUMS_URL="$(echo "$REL" | jq -r '.assets[].browser_download_url | select(test("SHA256SUMS"))' | head -n1)"
    if [ -n "$SUMS_URL" ] && command -v sha256sum >/dev/null 2>&1; then
      want="$(curl -fsSL "$SUMS_URL" | awk -v f="$(basename "$URL")" '$2==f || $2=="*"f {print $1}' | head -n1)"
      if [ -n "$want" ]; then
        got="$(sha256sum "$TAR" | awk '{print $1}')"
        [ "$want" = "$got" ] || { echo "!! sha256 mismatch for $(basename "$URL")" >&2; exit 1; }
        echo "   sha256 verified"
      fi
    else
      echo "   (no SHA256SUMS asset — skipping checksum; sha256=$(sha256sum "$TAR" 2>/dev/null | awk '{print $1}'))"
    fi
    tar -xzf "$TAR" -C "$DEST"
    XMRIG="$(find "$DEST" -maxdepth 2 -type f -name xmrig 2>/dev/null | head -n1 || true)"
    [ -n "$XMRIG" ] || { echo "!! xmrig binary not found after extract" >&2; exit 1; }
    chmod +x "$XMRIG"
  fi
fi
"$XMRIG" --version | head -n1 || true

# ---------------------------------------------------------------- render config
echo "== write /etc/abakos/xmrig.json =="
install -d -m 0755 /etc/abakos
# Optional trailing line (with its own newline) so the JSON stays valid whether or
# not a CPU cap is set.
MAXHINT=""
[ -n "${ABA_MINER_MAX_CPU:-}" ] && printf -v MAXHINT '    "max-threads-hint": %s,\n' "${ABA_MINER_MAX_CPU}"
cat > /etc/abakos/xmrig.json <<EOF
{
  "autosave": false,
  "background": false,
  "donate-level": 1,
  "cpu": {
    "enabled": true,
    "huge-pages": true,
    "huge-pages-jit": true,
${MAXHINT}    "yield": false
  },
  "randomx": {
    "mode": "fast",
    "1gb-pages": ${ONEGB},
    "rdmsr": ${MSR},
    "wrmsr": ${MSR},
    "numa": true
  },
  "pools": [
    {
      "url": "${POOL}",
      "user": "${ADDR}.${WORKER}",
      "pass": "x",
      "algo": "rx/0",
      "keepalive": true,
      "tls": false
    }
  ]
}
EOF
chmod 0644 /etc/abakos/xmrig.json
# Validate the JSON before we hand it to systemd (a typo here = crash-loop).
if command -v jq >/dev/null 2>&1; then
  jq -e . /etc/abakos/xmrig.json >/dev/null || { echo "!! rendered xmrig.json is invalid" >&2; exit 1; }
fi

# ---------------------------------------------------------------- install unit
echo "== install + enable abakos-miner.service =="
sed -e "s|__XMRIG__|$XMRIG|g" \
    -e "s|__USER__|root|g" \
  "$HERE/systemd/abakos-miner.service" > /etc/systemd/system/abakos-miner.service
systemctl daemon-reload
systemctl enable --now abakos-miner.service

sleep 3
echo "== status =="
systemctl --no-pager --lines=0 status abakos-miner.service || true
cat <<EOF

Host miner active (root, huge pages, MSR=${MSR}, 1gb-pages=${ONEGB}).
  - Watch:          journalctl -u abakos-miner -f
  - Confirm shares: journalctl -u abakos-miner | grep -i accepted
  - Change address/worker/tuning: edit /etc/abakos/xmrig.json then
                    sudo systemctl restart abakos-miner
  - Stop / disable: sudo systemctl disable --now abakos-miner
  - Verify huge pages are actually used: xmrig logs 'huge pages 100%' at startup;
    if it says 1%/0%, re-run scripts/60-hugepages.sh (need free pages before start).
EOF
