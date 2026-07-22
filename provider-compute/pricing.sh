#!/usr/bin/env bash
# Abakos provider bid-pricing script.
#
# provider-services calls this once per order with the order's resources as a JSON
# document on stdin, and expects a single number on stdout: the bid price as an
# integer amount of uaba PER BLOCK. Keep it simple and cheap for the sandbox.
#
# Resources JSON (per group) looks like: { "resources": [ { "cpu": {"units": ...},
# "memory": {"size": ...}, "storage": [ {"size": ...} ], "count": N } ], "price": {...} }
set -euo pipefail

data="$(cat)"

# millicpu, memory bytes, storage bytes summed over the group (best-effort with jq).
cpu_milli="$(echo "$data"  | jq '[.resources[]? | (.cpu.units.val // .cpu.units // 0 | tonumber) * (.count // 1)] | add // 0' 2>/dev/null || echo 0)"
mem_bytes="$(echo "$data"  | jq '[.resources[]? | (.memory.size.val // .memory.quantity.val // 0 | tonumber) * (.count // 1)] | add // 0' 2>/dev/null || echo 0)"

# Price weights (uaba/block). Tune later; sandbox values.
# ~0.5 uaba per cpu-milli-block + ~0.000001 uaba per MiB-block, min 1.
price="$(python3 - "$cpu_milli" "$mem_bytes" <<'PY'
import sys
cpu = float(sys.argv[1] or 0)          # millicpu
mem = float(sys.argv[2] or 0)          # bytes
mib = mem / (1024*1024)
p = cpu * 0.5 + mib * 0.001
print(max(1, int(round(p))))
PY
)"
echo "$price"
