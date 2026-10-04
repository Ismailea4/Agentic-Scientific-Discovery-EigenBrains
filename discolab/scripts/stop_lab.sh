#!/usr/bin/env bash
# Stop the Omnigent server and host started by scripts/start_lab.sh.
set -uo pipefail
cd "$(dirname "$0")/.."
D="lab_home/${1:-main}/.omnigent"
for f in host server; do
  if [ -f "$D/$f.pid" ]; then kill "$(cat "$D/$f.pid")" 2>/dev/null && echo "stopped $f"; rm -f "$D/$f.pid"; fi
done
