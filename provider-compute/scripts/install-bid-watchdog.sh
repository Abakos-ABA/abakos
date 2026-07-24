#!/usr/bin/env bash
# Installs a watchdog that restarts provider-services when its bid engine stops tracking orders.
#
# The provider's chain-event subscription dies silently (node restarts, dropped websockets) and
# it also strands inventory reservations from closed leases — both leave "Waiting for bids"
# forever while the process looks healthy, so systemd's Restart=always never helps. A restart
# resyncs orders and frees stranded reservations.
#
# Paste this whole file into a root shell on the provider VM.
set -euo pipefail

cat > /usr/local/bin/abakos-bid-watchdog <<'WATCHDOG'
#!/usr/bin/env bash
# Restart provider-services when the chain has open orders the bid engine does not track.
# Rate-limited to one restart per 15 minutes: an open order this provider legitimately cannot
# serve (e.g. persistent storage) would otherwise trigger a restart on every run.
set -u
REST="${REST:-https://rest.abakos.ai}"
STATUS_URL="${STATUS_URL:-https://localhost:8443/status}"
STAMP=/run/abakos-bid-watchdog.last

open=$(curl -sk --max-time 10 "$REST/akash/market/v1beta5/orders/list?filters.state=open" | grep -o '"state":"open"' | wc -l)
tracked=$(curl -sk --max-time 10 "$STATUS_URL" | grep -o '"orders":[0-9]*' | head -1 | cut -d: -f2)

if [ "${open:-0}" -gt 0 ] && [ "${tracked:-0}" -eq 0 ]; then
  now=$(date +%s)
  last=$(cat "$STAMP" 2>/dev/null || echo 0)
  if [ $((now - last)) -ge 900 ]; then
    echo "$now" > "$STAMP"
    logger -t abakos-bid-watchdog "chain has $open open orders, bid engine tracks 0 - restarting provider-services"
    systemctl restart provider-services
  fi
fi
WATCHDOG
chmod +x /usr/local/bin/abakos-bid-watchdog

cat > /etc/systemd/system/abakos-bid-watchdog.service <<'UNIT'
[Unit]
Description=Restart provider-services when its bid engine goes stale

[Service]
Type=oneshot
ExecStart=/usr/local/bin/abakos-bid-watchdog
UNIT

cat > /etc/systemd/system/abakos-bid-watchdog.timer <<'UNIT'
[Unit]
Description=Run the abakos bid watchdog every 2 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=2min

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl enable --now abakos-bid-watchdog.timer
echo "watchdog installed; next run: $(systemctl list-timers abakos-bid-watchdog.timer --no-pager | sed -n 2p)"
