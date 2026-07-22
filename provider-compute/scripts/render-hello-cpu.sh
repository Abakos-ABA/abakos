#!/usr/bin/env bash
# Render examples/hello-cpu.yaml from template using config/network.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=/dev/null
source "$HERE/config/network.sh"
OUT="${1:-$HERE/examples/hello-cpu.yaml}"
export ABA_EXAMPLE_SERVICE_HOST
if command -v envsubst >/dev/null 2>&1; then
  envsubst '${ABA_EXAMPLE_SERVICE_HOST}' < "$HERE/examples/hello-cpu.yaml.template" > "$OUT"
else
  sed "s/\${ABA_EXAMPLE_SERVICE_HOST}/$ABA_EXAMPLE_SERVICE_HOST/g" \
    "$HERE/examples/hello-cpu.yaml.template" > "$OUT"
fi
echo "wrote $OUT (hostname=$ABA_EXAMPLE_SERVICE_HOST)"
