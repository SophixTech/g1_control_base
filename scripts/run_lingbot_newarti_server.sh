#!/usr/bin/env bash
set -euo pipefail

# Each invocation is a fresh process. No legacy LingBot config/env overrides are used.
OPEN_RAIL_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SOPHIX_ROOT="$(dirname -- "$OPEN_RAIL_ROOT")"
NEWARTI_REPO_PATH="${NEWARTI_REPO_PATH:-$SOPHIX_ROOT/ORI-lingbo-vla-newarti}"
# The supplied interpreter can be reused without importing the legacy model source.
# Set NEWARTI_PYTHON to a dedicated environment for dependency-level isolation.
NEWARTI_PYTHON="${NEWARTI_PYTHON:-$SOPHIX_ROOT/lingbot-vla/.venv/bin/python}"
NEWARTI_TOKENIZER_PATH="${NEWARTI_TOKENIZER_PATH:-$SOPHIX_ROOT/models/Qwen2.5-VL-3B-Instruct-tokenizer}"
export QWEN25_PATH="$NEWARTI_TOKENIZER_PATH"
export PYTHONPATH="$NEWARTI_REPO_PATH:$OPEN_RAIL_ROOT"
export PYTHONNOUSERSITE=1

cd -- "$OPEN_RAIL_ROOT"
exec "$NEWARTI_PYTHON" "$OPEN_RAIL_ROOT/run_server.py" \
    "$@" --model_type lingbot_newarti --repo_path "$NEWARTI_REPO_PATH"
