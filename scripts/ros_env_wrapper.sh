#!/usr/bin/env bash
# Run the vendor PC forwarder using Open-RAIL's G1 environment.
# Vendor/ROS environment scripts do not support nounset.
set -e

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <start|stop>" >&2
    exit 2
fi
case "$1" in
    stop)
        # Match only the bridge binary, not ROS CLI tools in the same directory.
        pkill -9 -f '/forwarder/app/bin/forwarder$' || true
        exit 0
        ;;
    start)
        if pgrep -f '/forwarder/app/bin/forwarder$' > /dev/null; then
            echo "forwarder is already running"
            exit 0
        fi
        ;;
    *)
        echo "Usage: $0 <start|stop>" >&2
        exit 2
        ;;
esac

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
readonly FORWARDER_GDK_DIR="${GDK_DIR:-$(dirname -- "$REPO_DIR")/g1/vendor_packages/a2d_sdk-1.5.0}"
readonly FORWARDER_APP="$FORWARDER_GDK_DIR/forwarder/app"

if [[ ! -f /opt/ros/humble/setup.sh ]]; then
    echo "ROS 2 Humble environment not found: /opt/ros/humble/setup.sh" >&2
    exit 1
fi
if [[ ! -x "$FORWARDER_APP/bin/forwarder" ]]; then
    echo "forwarder not found: $FORWARDER_APP/bin/forwarder" >&2
    exit 1
fi

export CB_PROC_THREADS_NUM=5
export AORTA_DISPATCHER_THREAD_NUM=5
export DYLOG_ASYNC_INTERVAL=5000
export DYLOG_log_dir="$FORWARDER_GDK_DIR/forwarder/"
export DYLOG_LOG_SIZE=20000

if [[ -f "$FORWARDER_APP/env.sh" ]]; then
    source "$FORWARDER_APP/env.sh" "$FORWARDER_APP"
fi
# Load vendor/ROS libraries and then select the route-specific Aorta address.
# Keep this last so the vendor environment cannot overwrite that selection.
GDK_DIR="$FORWARDER_GDK_DIR"
source "$SCRIPT_DIR/g1_pc_gdk_env.sh"

exec "$FORWARDER_APP/bin/forwarder"
