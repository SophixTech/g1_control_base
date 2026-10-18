#!/usr/bin/env bash
# Source this file to prepare the Open-RAIL client environment.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    echo "Please source this file: source ${BASH_SOURCE[0]}" >&2
    exit 1
fi

OPEN_RAIL_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
export GDK_DIR="${GDK_DIR:-$OPEN_RAIL_ROOT/hardware/g1/vendor_packages/a2d_sdk-1.5.0}"
if [[ -z "${ORIN_KEY:-}" ]]; then
    ORIN_KEY="$OPEN_RAIL_ROOT/.local/robot/orin_g1_ed25519"
fi
export ORIN_KEY
if [[ ! -x "$OPEN_RAIL_ROOT/.venv/bin/python" ]]; then
    echo "Missing client Python: $OPEN_RAIL_ROOT/.venv/bin/python" >&2
    return 1
fi

source "$OPEN_RAIL_ROOT/.venv/bin/activate" || return
# RobotDds and CosineCamera communicate directly through the installed Cosine
# libraries. ROS and the optional forwarder are additional diagnostic bridges.
# Rebuild the original environment locally, without sourcing the deleted g1 repo.
if [[ -f /opt/ros/humble/setup.bash ]]; then
    source /opt/ros/humble/setup.bash || return
fi
export ROS_DOMAIN_ID=0 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
if [[ -d "$GDK_DIR/forwarder/app/lib" ]]; then
    export LD_LIBRARY_PATH="$GDK_DIR/forwarder/app/lib:${LD_LIBRARY_PATH:-}"
    export AMENT_PREFIX_PATH="$GDK_DIR/forwarder/app:${AMENT_PREFIX_PATH:-}"
fi
mkdir -p "$OPEN_RAIL_ROOT/.local/robot/log" || return
export DYLOG_log_dir="$OPEN_RAIL_ROOT/.local/robot/log"
export CB_PROC_THREADS_NUM=5 AORTA_DISPATCHER_THREAD_NUM=5

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

echo "SDK environment ready: python=$OPEN_RAIL_ROOT/.venv/bin/python, LOCATOR_IP=$LOCATOR_IP, USE_PTP_CLOCK=$USE_PTP_CLOCK"
