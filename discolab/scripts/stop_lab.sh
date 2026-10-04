#!/usr/bin/env bash
# Stop the Omnigent server and host started by scripts/start_lab.sh.
# On Windows a venv's python.exe is a launcher that spawns the real
# interpreter, so the whole process tree is killed (taskkill /T); killing only
# the launcher leaves the interpreter running and holding the lab database.
set -uo pipefail
cd "$(dirname "$0")/.."
D="lab_home/${1:-main}/.omnigent"
for f in host server; do
  [ -f "$D/$f.pid" ] || continue
  pid="$(cat "$D/$f.pid")"
  if command -v taskkill >/dev/null 2>&1; then
    wpid="$(ps | awk -v p="$pid" '$1 == p { print $4 }')"  # MSYS ps: PID PPID PGID WINPID ...
    taskkill //T //F //PID "${wpid:-$pid}" >/dev/null 2>&1 && echo "stopped $f (process tree)"
  else
    kill "$pid" 2>/dev/null && echo "stopped $f"
  fi
  rm -f "$D/$f.pid"
done
