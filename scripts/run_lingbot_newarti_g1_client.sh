#!/usr/bin/env bash
# Vendor/ROS environment scripts do not support nounset.
set -e

OPEN_RAIL_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! -f "$OPEN_RAIL_ROOT/conf/lingbot_newarti_package.yaml" ]]; then
    echo 'Missing conf/lingbot_newarti_package.yaml' >&2
    exit 1
fi
source "$OPEN_RAIL_ROOT/scripts/g1_pc_gdk_env.sh"
cd -- "$OPEN_RAIL_ROOT"
exec "$OPEN_RAIL_ROOT/.venv/bin/python" "$OPEN_RAIL_ROOT/run_web_client.py" \
    --host 127.0.0.1 --port 9000 "$@" --conf lingbot_newarti_package.yaml
