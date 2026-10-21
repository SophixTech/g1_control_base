#!/usr/bin/env bash
set -euo pipefail
OPEN_RAIL_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SOPHIX_ROOT="$(dirname -- "$OPEN_RAIL_ROOT")"
LINGBOT_V2_REPO_PATH="${LINGBOT_V2_REPO_PATH:-$SOPHIX_ROOT/ORI-lingbot-vlaV2}"
LINGBOT_V2_PYTHON="${LINGBOT_V2_PYTHON:-$LINGBOT_V2_REPO_PATH/.venv/bin/python}"
export QWEN3VL_PATH="${QWEN3VL_PATH:-$SOPHIX_ROOT/models/Qwen3-VL-4B-Instruct}"
export PYTHONPATH="$LINGBOT_V2_REPO_PATH:$OPEN_RAIL_ROOT"
export PYTHONNOUSERSITE=1
cd -- "$OPEN_RAIL_ROOT"
exec "$LINGBOT_V2_PYTHON" "$OPEN_RAIL_ROOT/run_server.py" \
    "$@" --model_type lingbot_v2 --repo_path "$LINGBOT_V2_REPO_PATH"
