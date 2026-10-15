#!/usr/bin/env bash
set -euo pipefail

# Each invocation is a fresh process. No legacy LingBot config/env overrides are used.
OPEN_RAIL_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SOPHIX_ROOT="$(dirname -- "$OPEN_RAIL_ROOT")"
ORI_REPO_PATH="${ORI_REPO_PATH:-$SOPHIX_ROOT/ORI-lingbot-vla}"
# The supplied interpreter can be reused without importing the legacy model source.
# Set ORI_PYTHON to a dedicated environment for dependency-level isolation.
ORI_PYTHON="${ORI_PYTHON:-$SOPHIX_ROOT/lingbot-vla/.venv/bin/python}"
ORI_TOKENIZER_PATH="${ORI_TOKENIZER_PATH:-$SOPHIX_ROOT/models/Qwen2.5-VL-3B-Instruct-tokenizer}"
export QWEN25_PATH="$ORI_TOKENIZER_PATH"
export PYTHONPATH="$ORI_REPO_PATH:$OPEN_RAIL_ROOT"
export PYTHONNOUSERSITE=1

cd -- "$OPEN_RAIL_ROOT"
exec "$ORI_PYTHON" "$OPEN_RAIL_ROOT/run_server.py" \
    "$@" --model_type lingbot_ori --repo_path "$ORI_REPO_PATH"
