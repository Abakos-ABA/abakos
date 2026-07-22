#!/usr/bin/env bash
# Abakos provider bid pricing — mainnet formula (uaba per block).
# Same script on sandbox and mainnet; tune weights via env if needed.
#
# provider-services calls this once per order with resources JSON on stdin.
set -euo pipefail

data="$(cat)"

cpu_milli="$(echo "$data" | jq '[.resources[]? | (.cpu.units.val // .cpu.units // 0 | tonumber) * (.count // 1)] | add // 0' 2>/dev/null || echo 0)"
mem_bytes="$(echo "$data" | jq '[.resources[]? | (.memory.size.val // .memory.quantity.val // 0 | tonumber) * (.count // 1)] | add // 0' 2>/dev/null || echo 0)"
storage_bytes="$(echo "$data" | jq '[.resources[]? | (.storage[]?.size.val // .storage[]?.quantity.val // 0 | tonumber) * (.count // 1)] | add // 0' 2>/dev/null || echo 0)"

# Weights (uaba/block) — mainnet defaults; override for competitive markets:
#   PRICE_CPU_WEIGHT=0.5 PRICE_MEM_PER_MIB=0.001 PRICE_STORAGE_PER_GIB=0.01
cpu_w="${PRICE_CPU_WEIGHT:-0.5}"
mem_w="${PRICE_MEM_PER_MIB:-0.001}"
stor_w="${PRICE_STORAGE_PER_GIB:-0.01}"

price="$(python3 - "$cpu_milli" "$mem_bytes" "$storage_bytes" "$cpu_w" "$mem_w" "$stor_w" <<'PY'
import sys
cpu = float(sys.argv[1] or 0)
mem = float(sys.argv[2] or 0)
stor = float(sys.argv[3] or 0)
cw, mw, sw = map(float, sys.argv[4:7])
mib = mem / (1024 * 1024)
gib = stor / (1024 ** 3)
p = cpu * cw + mib * mw + gib * sw
print(max(1, int(round(p))))
PY
)"
echo "$price"
