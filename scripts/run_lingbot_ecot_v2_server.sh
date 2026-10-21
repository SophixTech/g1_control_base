#!/usr/bin/env bash
set -euo pipefail

# Each invocation is a fresh process. No legacy LingBot config/env overrides are used.
OPEN_RAIL_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SOPHIX_ROOT="$(dirname -- "$OPEN_RAIL_ROOT")"
ECOT_V2_REPO_PATH="${ECOT_V2_REPO_PATH:-$SOPHIX_ROOT/worktrees/branch-ecot-v2}"
# The supplied interpreter can be reused without importing the legacy model source.
# Set ECOT_V2_PYTHON to a dedicated environment for dependency-level isolation.
ECOT_V2_PYTHON="${ECOT_V2_PYTHON:-$SOPHIX_ROOT/lingbot-vla/.venv/bin/python}"
ECOT_V2_TOKENIZER_PATH="${ECOT_V2_TOKENIZER_PATH:-$SOPHIX_ROOT/models/Qwen2.5-VL-3B-Instruct-tokenizer}"
export QWEN25_PATH="$ECOT_V2_TOKENIZER_PATH"
export PYTHONPATH="$ECOT_V2_REPO_PATH:$OPEN_RAIL_ROOT"
export PYTHONNOUSERSITE=1

cd -- "$OPEN_RAIL_ROOT"
exec "$ECOT_V2_PYTHON" "$OPEN_RAIL_ROOT/run_server.py" \
    "$@" --model_type lingbot_ecot_v2 --repo_path "$ECOT_V2_REPO_PATH"
