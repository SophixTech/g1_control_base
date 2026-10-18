#!/usr/bin/env bash
set -e
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT/hardware/g1/g1_pc_gdk_env.sh"
exec timeout --kill-after=3 130 "$ROOT/.venv/bin/python" "$ROOT/hardware/g1/g1_check_communication.py" "$@"
