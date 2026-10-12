#!/usr/bin/env bash
set -euo pipefail

# Each invocation is a fresh process. No legacy LingBot config/env overrides are used.
OPEN_RAIL_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SOPHIX_ROOT="$(dirname -- "$OPEN_RAIL_ROOT")"
ECOT_REPO_PATH="${ECOT_REPO_PATH:-$SOPHIX_ROOT/worktrees/branch-ecot}"
# The supplied interpreter can be reused without importing the legacy model source.
# Set ECOT_PYTHON to a dedicated environment for dependency-level isolation.
ECOT_PYTHON="${ECOT_PYTHON:-$SOPHIX_ROOT/lingbot-vla/.venv/bin/python}"
ECOT_TOKENIZER_PATH="${ECOT_TOKENIZER_PATH:-$SOPHIX_ROOT/models/Qwen2.5-VL-3B-Instruct-tokenizer}"
export QWEN25_PATH="$ECOT_TOKENIZER_PATH"
export PYTHONPATH="$ECOT_REPO_PATH:$OPEN_RAIL_ROOT"
export PYTHONNOUSERSITE=1

cd -- "$OPEN_RAIL_ROOT"
exec "$ECOT_PYTHON" "$OPEN_RAIL_ROOT/run_server.py" \
    "$@" --model_type lingbot_ecot --repo_path "$ECOT_REPO_PATH"
