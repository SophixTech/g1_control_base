#!/usr/bin/env bash
set -euo pipefail

# Run from any directory. Override LINGBOT_REPO_PATH, LINGBOT_PYTHON and
# QWEN25_PATH to use a different source checkout, model environment or tokenizer.
# Example (paths and horizon must correspond to the same training run):
#   scripts/run_lingbot_server.sh --model_path /path/to/hf_ckpt \
#     --norm_path /path/to/norm_stats.json --chunk_size 25 --num_denoising_step 10
# Pass --help for the server CLI. No checkpoint is selected automatically.
OPEN_RAIL_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
LINGBOT_REPO_PATH="${LINGBOT_REPO_PATH:-$(dirname -- "$OPEN_RAIL_ROOT")/lingbot-vla}"
LINGBOT_PYTHON="${LINGBOT_PYTHON:-$LINGBOT_REPO_PATH/.venv/bin/python}"
export QWEN25_PATH="${QWEN25_PATH:-$(dirname -- "$OPEN_RAIL_ROOT")/models/Qwen2.5-VL-3B-Instruct-tokenizer}"

cd -- "$OPEN_RAIL_ROOT"
exec "$LINGBOT_PYTHON" "$OPEN_RAIL_ROOT/run_server.py" \
    --model_type lingbot_vla --repo_path "$LINGBOT_REPO_PATH" "$@"
