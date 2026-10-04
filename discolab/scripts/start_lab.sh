#!/usr/bin/env bash
# Start a local Omnigent server + host for the discolab agent bundle.
# Run from the discolab directory:  scripts/start_lab.sh [lab_name] [port]
#
# Environment notes (Windows / Git Bash, verified with omnigent 0.16):
#  - PYTHONUTF8=1: the host tunnel crashes on cp1252 console encoding otherwise.
#  - PATH entries that contain an unrelated `srt` executable are dropped: Omnigent
#    would mistake it for its sandbox runtime and fail to launch tools.
#  - The lab venv goes first on PATH so the MCP command `python` is the lab's.
# Stop the stack with:  scripts/stop_lab.sh [lab_name]
set -euo pipefail
cd "$(dirname "$0")/.."

LAB_NAME="${1:-main}"
PORT="${2:-6810}"
export DISCOLAB_HOME="$(pwd)/lab_home/${LAB_NAME}"
mkdir -p "$DISCOLAB_HOME/.omnigent"

if [ -d .venv/Scripts ]; then VENV_BIN="$(pwd)/.venv/Scripts"; else VENV_BIN="$(pwd)/.venv/bin"; fi
CLEAN_PATH=""
IFS=':' read -ra PARTS <<< "$PATH"
for d in "${PARTS[@]}"; do
  if [ -n "$d" ] && [ -e "$d/srt" ] && [ ! -e "$d/srt.exe" ]; then continue; fi
  CLEAN_PATH="${CLEAN_PATH:+$CLEAN_PATH:}$d"
done
export PATH="$VENV_BIN:$CLEAN_PATH"
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8 OMNIGENT_HOST_NO_OPEN=1
# Runners spawned by the host get an allow-listed environment; pass the lab
# location (and an optional OpenAlex key) through explicitly.
export OMNIGENT_RUNNER_ENV_PASSTHROUGH="DISCOLAB_HOME${OPENALEX_API_KEY:+,OPENALEX_API_KEY}"

: "${ANTHROPIC_API_KEY:?ANTHROPIC_API_KEY must be set}"

if [ ! -f "$DISCOLAB_HOME/ledger.jsonl" ]; then
  python -m discolab.cli init
fi

DB="sqlite:///$(cd "$DISCOLAB_HOME/.omnigent" && pwd -W 2>/dev/null || pwd)/chat.db"
nohup python -m omnigent.cli server --host 127.0.0.1 --port "$PORT" --database-uri "$DB" \
  --artifact-location "$DISCOLAB_HOME/.omnigent/artifacts" --agent omnigent/lab_pi \
  > "$DISCOLAB_HOME/.omnigent/server.log" 2>&1 &
echo $! > "$DISCOLAB_HOME/.omnigent/server.pid"
for _ in $(seq 1 60); do curl -s -m 2 "http://127.0.0.1:$PORT/health" >/dev/null && break; sleep 1; done

nohup python -m omnigent.cli host --server "http://127.0.0.1:$PORT" --no-open --non-interactive \
  > "$DISCOLAB_HOME/.omnigent/host.log" 2>&1 &
echo $! > "$DISCOLAB_HOME/.omnigent/host.pid"
for _ in $(seq 1 60); do
  if curl -s -m 2 "http://127.0.0.1:$PORT/v1/hosts" | grep -q '"status":"online"'; then
    echo "discolab lab '$LAB_NAME' up: http://127.0.0.1:$PORT  (DISCOLAB_HOME=lab_home/$LAB_NAME)"
    exit 0
  fi
  sleep 1
done
echo "host did not come online; see lab_home/$LAB_NAME/.omnigent/host.log" >&2
exit 1
