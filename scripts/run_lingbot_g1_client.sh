#!/usr/bin/env bash
# Vendor/ROS environment scripts do not support nounset; keep it disabled.
set -e

OPEN_RAIL_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

# Without this file the web client would fall back to its default task.
if [[ ! -f "$OPEN_RAIL_ROOT/conf/lingbot_package.yaml" ]]; then
    echo "Missing conf/lingbot_package.yaml: complete M08 before starting the G1 client." >&2
    exit 1
fi

source "$OPEN_RAIL_ROOT/scripts/g1_pc_gdk_env.sh"
cd -- "$OPEN_RAIL_ROOT"
# The web process and RobotProxy's spawned worker share the local client environment.
exec "$OPEN_RAIL_ROOT/.venv/bin/python" "$OPEN_RAIL_ROOT/run_web_client.py" \
    "$@" --conf lingbot_package.yaml
