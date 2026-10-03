#!/usr/bin/env bash
# Source this file to prepare the Open-RAIL client environment.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    echo "Please source this file: source ${BASH_SOURCE[0]}" >&2
    exit 1
fi

OPEN_RAIL_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
GDK_DIR="${GDK_DIR:-$(dirname -- "$OPEN_RAIL_ROOT")/g1/vendor_packages/a2d_sdk-1.5.0}"
if [[ ! -x "$OPEN_RAIL_ROOT/.venv/bin/python" || ! -f "$GDK_DIR/env.sh" ]]; then
    echo "Run scripts/setup_g1_env.sh and check GDK_DIR before preparing G1." >&2
    return 1
fi

source "$OPEN_RAIL_ROOT/.venv/bin/activate" || return
# Preserve vendor library paths, logging and ROS setup; do not activate its old venv.
source "$GDK_DIR/env.sh" || return

locator_ip="$(ip route get 10.42.0.101 2>/dev/null | awk '{for (i=1; i<=NF; i++) if ($i == "src") {print $(i+1); exit}}')"
if [[ -z "$locator_ip" ]]; then
    echo "No route to 10.42.0.101; check the Debug-port cable and PC network." >&2
    return 1
fi
export LOCATOR_IP="$locator_ip"
export AORTA_DISCOVERY_URI="http://10.42.0.101:2379"
export AORTA_DISCOVERY_MODE=1
export AORTA_IP_MASK="10.42.0.0/24"
export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python
export USE_PTP_CLOCK=OFF

echo "GDK ready: python=$OPEN_RAIL_ROOT/.venv/bin/python, LOCATOR_IP=$LOCATOR_IP, USE_PTP_CLOCK=$USE_PTP_CLOCK"
