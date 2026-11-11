#!/usr/bin/env bash
# Install Ollama natively on the dev board (Radxa ROCK 5T, ARM64 Linux) and
# pull the candidate models, so the laptop benchmarks can be rerun there.
#
# Usage (on the board, with internet access):
#   bash models/setup_board.sh            # install Ollama + pull all candidates
#   bash models/setup_board.sh qwen3:8b   # pull only the tags given
#
# Ollama runs as the systemd service `ollama`, listening on 127.0.0.1:11434
# (the evaluator only accepts a loopback server). Models are stored under
# /usr/share/ollama/.ollama/models.
set -euo pipefail

# Same Ollama version as the laptop runs, so results are comparable.
OLLAMA_VERSION="${OLLAMA_VERSION:-0.40.3}"

# Candidate tags and the IDs `ollama list` showed for them on the laptop
# (2026-10). A different ID means the tag now points at different weights.
declare -A EXPECTED_ID=(
  [qwen3.5:4b]=d8b0f5e9760c
  [qwen3:4b-instruct-2507-q4_K_M]=0edcdef34593
  [qwen3:8b]=500a1f067a9f
)
DEFAULT_MODELS=(qwen3.5:4b qwen3:4b-instruct-2507-q4_K_M qwen3:8b)
NEEDED_GB=12   # ~11 GB of models plus headroom

models=("$@")
[ ${#models[@]} -eq 0 ] && models=("${DEFAULT_MODELS[@]}")

echo "== Board: $(uname -m), $(grep -m1 PRETTY_NAME /etc/os-release | cut -d= -f2)"
[ "$(uname -m)" = aarch64 ] || echo "warning: expected aarch64, got $(uname -m)"
free -g | awk '/Mem:/ {print "== RAM: " $2 " GB total, " $7 " GB available"}'

# 1. Install (or confirm) Ollama.
installed="$(ollama -v 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | tail -1 || true)"
if [ "$installed" != "$OLLAMA_VERSION" ]; then
  echo "== Installing Ollama $OLLAMA_VERSION (found: ${installed:-none})"
  curl -fsSL https://ollama.com/install.sh | OLLAMA_VERSION="$OLLAMA_VERSION" sh
else
  echo "== Ollama $OLLAMA_VERSION already installed"
fi

sudo systemctl enable --now ollama
for _ in $(seq 30); do
  curl -fs http://127.0.0.1:11434/api/version >/dev/null && break
  sleep 1
done
curl -fs http://127.0.0.1:11434/api/version || { echo "Ollama did not start; see: journalctl -u ollama"; exit 1; }
echo

# 2. Check disk space where the service stores models.
store=/usr/share/ollama
free_gb=$(df -BG --output=avail "$store" | tail -1 | tr -dc 0-9)
if [ "$free_gb" -lt "$NEEDED_GB" ]; then
  echo "error: only ${free_gb} GB free under $store; need ~${NEEDED_GB} GB."
  echo "Free space, or set OLLAMA_MODELS in the service to a larger disk (e.g. NVMe):"
  echo "  sudo systemctl edit ollama   ->   [Service] Environment=\"OLLAMA_MODELS=/path\""
  exit 1
fi

# 3. Pull the models.
for m in "${models[@]}"; do
  echo "== Pulling $m"
  ollama pull "$m"
done

# 4. Compare IDs with the laptop's copies.
echo
echo "== Installed models"
ollama list
status=0
for m in "${models[@]}"; do
  want="${EXPECTED_ID[$m]:-}"
  [ -z "$want" ] && continue
  got="$(ollama list | awk -v m="$m" '$1 == m {print $2}')"
  if [ "$got" = "$want" ]; then
    echo "ok        $m  $got  (same weights as the laptop)"
  else
    echo "MISMATCH  $m  board=$got laptop=$want  (tag was updated; results won't be like-for-like)"
    status=1
  fi
done
exit $status
