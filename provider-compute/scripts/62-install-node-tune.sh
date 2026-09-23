#!/usr/bin/env bash
# Install + enable node tuning so EVERY tenant/Console deployment on this provider
# mines RandomX at full speed — automatically, on vanilla Linux, with no per-template
# config. Sets Transparent Huge Pages (enabled=always, defrag=defer+madvise) + loads
# msr at every boot; reserves NO fixed RAM (THP promotes on demand, so rentable lease
# memory is untouched).
#
# Called automatically by scripts/00-install-k3s.sh. Idempotent — safe to re-run.
#
#   sudo bash scripts/62-install-node-tune.sh
set -euo pipefail

[ "$(id -u)" = 0 ] || { echo "!! run as root: sudo bash scripts/62-install-node-tune.sh" >&2; exit 1; }

HERE="$(cd "$(dirname "$0")/.." && pwd)"

echo "== install + enable abakos-node-tune.service (THP + msr for tenant mining) =="
sed -e "s|__HERE__|$HERE|g" \
  "$HERE/systemd/abakos-node-tune.service" > /etc/systemd/system/abakos-node-tune.service
systemctl daemon-reload
systemctl enable --now abakos-node-tune.service

echo "== result =="
systemctl --no-pager --lines=0 status abakos-node-tune.service 2>/dev/null | head -n 4 || true
echo "   THP: $(cat /sys/kernel/mm/transparent_hugepage/enabled 2>/dev/null || echo '?')"
echo "   msr: $([ -e /dev/cpu/0/msr ] && echo present || echo 'not present (ok if built-in / unprivileged host)')"
cat <<'EOF'

Node tuning active. Every deployment scheduled here now gets Transparent Huge Pages
automatically — no SDL changes, no capabilities, no commands for the leaser. Re-runs
on every boot. To also mine idle CPU on the host itself, see scripts/61-install-miner.sh.
EOF
