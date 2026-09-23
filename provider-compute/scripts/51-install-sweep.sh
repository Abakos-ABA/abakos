#!/usr/bin/env bash
# Install (and enable) the daily earnings-sweep timer. Deliberate, separate step
# from install.sh because it moves real ABA (operator earnings -> main account).
#
# Required: ABA_SWEEP_DEST=<your main abakos1 address>
# Optional: ABA_SWEEP_RESERVE_UABA (default 25000000), ABA_SWEEP_KEY (default provider)
#
#   ABA_SWEEP_DEST=abakos1... sudo -E bash scripts/51-install-sweep.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=/dev/null
source "$HERE/config/network.sh"

DEST="${ABA_SWEEP_DEST:-}"
[ -n "$DEST" ] || { echo "!! set ABA_SWEEP_DEST=<your main abakos1 address>" >&2; exit 1; }
[[ "$DEST" == abakos1* ]] || { echo "!! ABA_SWEEP_DEST must be an abakos1 address" >&2; exit 1; }

RUN_USER="${SUDO_USER:-$USER}"
RESERVE="${ABA_SWEEP_RESERVE_UABA:-25000000}"
KEY="${ABA_SWEEP_KEY:-provider}"

echo "== dry-run once as $RUN_USER (no broadcast) to confirm amounts =="
sudo -u "$RUN_USER" env ABA_SWEEP_DEST="$DEST" ABA_SWEEP_RESERVE_UABA="$RESERVE" \
  ABA_SWEEP_KEY="$KEY" ABA_NETWORK="$ABA_NETWORK" \
  bash "$HERE/scripts/50-sweep-earnings.sh" || true

echo "== write /etc/abakos/sweep.env =="
install -d -m 0755 /etc/abakos
cat > /etc/abakos/sweep.env <<EOF
ABA_SWEEP_DEST=$DEST
ABA_SWEEP_KEY=$KEY
ABA_SWEEP_RESERVE_UABA=$RESERVE
ABA_SWEEP_APPLY=1
EOF
chmod 0644 /etc/abakos/sweep.env

echo "== install units =="
sed -e "s|__USER__|$RUN_USER|g" \
    -e "s|__HERE__|$HERE|g" \
    -e "s|__ABA_NETWORK__|$ABA_NETWORK|g" \
  "$HERE/systemd/abakos-sweep.service" > /etc/systemd/system/abakos-sweep.service
cp "$HERE/systemd/abakos-sweep.timer" /etc/systemd/system/abakos-sweep.timer
systemctl daemon-reload
systemctl enable --now abakos-sweep.timer

echo "== done. status: =="
systemctl list-timers abakos-sweep.timer --no-pager || true
cat <<EOF

Sweep timer active (daily). It sends spendable earnings above ${RESERVE}uaba from
key '$KEY' to $DEST.
  - Run once now:   sudo systemctl start abakos-sweep.service
  - Watch:          journalctl -u abakos-sweep.service -n 20 --no-pager
  - Disable:        sudo systemctl disable --now abakos-sweep.timer
  - After Ebene-1 sponsoring is live, set ABA_SWEEP_RESERVE_UABA=0 in
    /etc/abakos/sweep.env (operator no longer funds its own deposits).
EOF
