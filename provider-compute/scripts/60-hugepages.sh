#!/usr/bin/env bash
# Step 6: RandomX host tuning — reserve huge pages + load the msr module so xmrig
# mines in FAST mode with the MSR mod on this provider host. This is the big
# hashrate win for the host miner (scripts/61-install-miner.sh):
#   * RandomX FAST mode needs a ~2080 MiB dataset. Backing it with huge pages
#     (2 MiB or 1 GiB) instead of 4 KiB pages removes TLB misses -> typically
#     +30-50% hashrate vs light/default mode.
#   * The MSR mod (msr kernel module + root) tweaks CPU cache/prefetch MSRs ->
#     another ~5-15% on Ryzen/Intel. xmrig applies it itself when run as root.
#
# SAFE BY DEFAULT: reserves a bounded block of 2 MiB pages and loads msr. It does
# NOT touch tenant workloads and needs NO reboot. The bigger levers (1 GiB pages,
# THP for pods, k3s re-advertise) are opt-in via env because they edit boot config
# or disrupt running leases.
#
#   ABA_HUGEPAGES_2M=N   total 2 MiB pages to reserve. Default: 1280 per NUMA node
#                        (~2.5 GiB/node — one RandomX dataset + cache + scratchpads),
#                        clamped to 50% of RAM. Set 0 to skip 2 MiB reservation.
#   ABA_HUGEPAGES_1G=N   ALSO reserve N x 1 GiB pages (bigger win, but edits the
#                        kernel cmdline in /etc/default/grub and needs a REBOOT).
#                        3 covers RandomX. Off by default.
#   ABA_THP=always|madvise|never
#                        Transparent Huge Pages. Console/tenant pods can't request
#                        hugepages resources via SDL, so THP is the only huge-page
#                        lever they get. Default: leave the kernel setting untouched.
#   ABA_RESTART_K3S=1    restart k3s so the kubelet re-advertises node hugepages
#                        capacity. DISRUPTS running leases — off by default.
#
#   sudo -E bash scripts/60-hugepages.sh
set -euo pipefail

[ "$(id -u)" = 0 ] || { echo "!! run as root: sudo -E bash scripts/60-hugepages.sh" >&2; exit 1; }

TWO_M_BASE="${ABA_HUGEPAGES_2M:-}"
ONE_G="${ABA_HUGEPAGES_1G:-0}"
THP="${ABA_THP:-}"
RESTART_K3S="${ABA_RESTART_K3S:-0}"

mem_kib="$(awk '/^MemTotal:/{print $2}' /proc/meminfo)"
nodes="$(find /sys/devices/system/node -maxdepth 1 -name 'node[0-9]*' 2>/dev/null | wc -l)"
[ "${nodes:-0}" -ge 1 ] || nodes=1

echo "== RandomX host tuning =="
echo "   MemTotal: $((mem_kib/1024)) MiB | NUMA nodes: $nodes | CPU: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ //')"
echo "   before:  $(awk '/^HugePages_Total|^HugePages_Free|^Hugepagesize/{printf "%s=%s ", $1, $2$3} END{print ""}' /proc/meminfo)"

# ---------------------------------------------------------------- 2 MiB pages
if [ "${TWO_M_BASE:-1280}" != "0" ]; then
  base="${TWO_M_BASE:-$((1280 * nodes))}"
  # Clamp to 50% of RAM so we never starve k3s / tenant leases. 1 page = 2 MiB = 2048 KiB.
  cap=$(( mem_kib / 4096 ))
  pages="$base"
  if [ "$pages" -gt "$cap" ]; then
    echo "   (clamping ${pages} -> ${cap} pages = 50% of RAM)"
    pages="$cap"
  fi
  echo "== reserve ${pages} x 2 MiB pages ($((pages*2)) MiB) =="
  # Persist across reboots + apply now. (`sysctl -w` fills from free memory; on a
  # long-running host with fragmented RAM the kernel may grant fewer than asked —
  # the verify block below prints what actually landed.)
  cat > /etc/sysctl.d/60-abakos-hugepages.conf <<EOF
# Abakos RandomX host miner — 2 MiB huge pages for the xmrig dataset.
# Managed by provider-compute/scripts/60-hugepages.sh
vm.nr_hugepages = ${pages}
EOF
  sysctl -w vm.nr_hugepages="${pages}" >/dev/null
else
  echo "== skip 2 MiB reservation (ABA_HUGEPAGES_2M=0) =="
fi

# ---------------------------------------------------------------- MSR module
echo "== load msr kernel module (for the RandomX MSR mod) =="
if modprobe msr 2>/dev/null; then
  echo "msr" > /etc/modules-load.d/abakos-msr.conf
  if [ -e /dev/cpu/0/msr ]; then
    echo "   msr loaded (/dev/cpu/0/msr present). xmrig will apply the MSR mod as root."
  else
    echo "   msr loaded but /dev/cpu/0/msr missing — CONFIG_X86_MSR may be built-in; usually still fine."
  fi
else
  echo "   !! could not load msr (no module / locked-down kernel). MSR mod will be skipped; pages still help."
fi

# ---------------------------------------------------------------- THP (for pods)
if [ -n "$THP" ]; then
  thp_file=/sys/kernel/mm/transparent_hugepage/enabled
  if [ -w "$thp_file" ]; then
    echo "== set Transparent Huge Pages -> ${THP} (every tenant/Console pod gets 2 MiB pages transparently) =="
    echo "$THP" > "$thp_file" || true
    # Softer compaction so THP promotion never stalls a latency-sensitive tenant.
    [ -w /sys/kernel/mm/transparent_hugepage/defrag ] && echo "defer+madvise" > /sys/kernel/mm/transparent_hugepage/defrag || true
    # Persistence across reboots is owned by abakos-node-tune.service (installed for
    # every provider by scripts/62-install-node-tune.sh via 00-install-k3s.sh); it
    # re-runs this script at boot, so there's no separate THP unit to drift here.
  else
    echo "   !! THP control file not writable — kernel may lack THP; skipping."
  fi
fi

# ---------------------------------------------------------------- 1 GiB pages (GRUB)
if [ "${ONE_G:-0}" != "0" ]; then
  GRUB=/etc/default/grub
  if [ ! -f "$GRUB" ]; then
    echo "   !! $GRUB not found — can't configure 1 GiB pages automatically. Add"
    echo "      'default_hugepagesz=1G hugepagesz=1G hugepages=${ONE_G}' to your kernel cmdline manually."
  else
    echo "== configure ${ONE_G} x 1 GiB pages via kernel cmdline (needs REBOOT) =="
    cp -a "$GRUB" "${GRUB}.abakos.bak.$(date +%s 2>/dev/null || echo bak)" 2>/dev/null \
      || cp -a "$GRUB" "${GRUB}.abakos.bak"
    # Idempotent: strip any prior hugepage tokens we (or anyone) added, then append ours.
    line="$(grep -E '^GRUB_CMDLINE_LINUX_DEFAULT=' "$GRUB" | head -n1 | sed 's/^GRUB_CMDLINE_LINUX_DEFAULT=//; s/^"//; s/"$//')"
    cleaned="$(echo "$line" | tr ' ' '\n' | grep -vE '^(default_hugepagesz|hugepagesz|hugepages)=' | tr '\n' ' ' | sed 's/ *$//; s/^ *//')"
    newline="${cleaned} default_hugepagesz=1G hugepagesz=1G hugepages=${ONE_G}"
    newline="$(echo "$newline" | sed 's/^ *//')"
    if grep -qE '^GRUB_CMDLINE_LINUX_DEFAULT=' "$GRUB"; then
      # Use a non-/ delimiter; the value has no '|'.
      sed -i "s|^GRUB_CMDLINE_LINUX_DEFAULT=.*|GRUB_CMDLINE_LINUX_DEFAULT=\"${newline}\"|" "$GRUB"
    else
      echo "GRUB_CMDLINE_LINUX_DEFAULT=\"${newline}\"" >> "$GRUB"
    fi
    if command -v update-grub >/dev/null 2>&1; then
      update-grub
    elif command -v grub2-mkconfig >/dev/null 2>&1; then
      grub2-mkconfig -o "$(readlink -f /etc/grub2.cfg 2>/dev/null || echo /boot/grub2/grub.cfg)"
    else
      echo "   !! neither update-grub nor grub2-mkconfig found — regenerate your grub config manually."
    fi
    echo "   1 GiB pages will be reserved after a REBOOT. Set 1gb-pages:true in the miner"
    echo "   (scripts/61-install-miner.sh auto-detects them post-reboot)."
  fi
fi

# ---------------------------------------------------------------- k3s re-advertise
if [ "${RESTART_K3S:-0}" = "1" ]; then
  if systemctl list-unit-files 2>/dev/null | grep -q '^k3s\.service'; then
    echo "== restart k3s so the kubelet re-advertises hugepages capacity (disrupts leases) =="
    systemctl restart k3s
  else
    echo "   (no k3s.service found — skipping restart)"
  fi
fi

# ---------------------------------------------------------------- verify
echo "== result =="
awk '/^HugePages_Total|^HugePages_Free|^HugePages_Rsvd|^Hugepagesize/{printf "   %-18s %s %s\n", $1, $2, $3}' /proc/meminfo
for d in /sys/kernel/mm/hugepages/hugepages-*; do
  [ -d "$d" ] || continue
  echo "   $(basename "$d"): nr=$(cat "$d/nr_hugepages" 2>/dev/null) free=$(cat "$d/free_hugepages" 2>/dev/null)"
done
[ -n "$THP" ] && echo "   THP: $(cat /sys/kernel/mm/transparent_hugepage/enabled 2>/dev/null)"
echo
echo "Next: sudo -E bash scripts/61-install-miner.sh   (installs the huge-page-aware host miner)"
