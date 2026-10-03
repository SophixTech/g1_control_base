#!/usr/bin/env bash
# Switch this G1 from any current scene (including VR) to idle, then COPILOT.
# Default is read-only validation; --execute needs an exact confirmation.
set -euo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
readonly LEGACY_G1_DIR="$(dirname -- "$REPO_DIR")/g1"
readonly A2D_GDK_DIR="${GDK_DIR:-$LEGACY_G1_DIR/vendor_packages/a2d_sdk-1.5.0}"
readonly ORIN_HOST="agi@10.42.0.101"
readonly ORIN_KEY="${ORIN_KEY:-$LEGACY_G1_DIR/orin_g1_ed25519}"
readonly CLIENT_PYTHON="$REPO_DIR/.venv/bin/python"
readonly CONFIRMATION="SWITCH_FROM_VR_TO_COPILOT"
readonly SYSTEM_SSH="/usr/bin/ssh"

# The sourced GDK sets LD_LIBRARY_PATH to the forwarder's newer OpenSSL. Use
# system ssh with system libraries for the Orin service-status check.
clean_ssh() {
  env -u LD_LIBRARY_PATH -u LD_PRELOAD \
    PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    "$SYSTEM_SSH" "$@"
}

execute=false
if [[ "${1:-}" == "--execute" ]]; then
  execute=true
  shift
fi
if [[ "${1:-}" == "--confirm" ]]; then
  confirmation="${2:-}"
  shift 2
else
  confirmation=""
fi
if [[ $# -ne 0 ]]; then
  echo "Usage: $0 [--execute --confirm $CONFIRMATION]" >&2
  exit 2
fi
if [[ "$execute" == true && "$confirmation" != "$CONFIRMATION" ]]; then
  echo "--execute requires --confirm $CONFIRMATION" >&2
  exit 2
fi
if [[ ! -f "$A2D_GDK_DIR/conf/idle.pbtxt" || ! -f "$A2D_GDK_DIR/conf/copilot.pbtxt" ]]; then
  echo "Missing GDK mode configuration under: $A2D_GDK_DIR/conf" >&2
  exit 2
fi
if [[ ! -r "$ORIN_KEY" ]]; then
  echo "Missing SSH private key: $ORIN_KEY" >&2
  exit 2
fi

echo 'Checking the Orin mode-switch API and persistent service...'
clean_ssh -i "$ORIN_KEY" -o BatchMode=yes -o ConnectTimeout=8 "$ORIN_HOST" \
  'systemctl is-active --quiet a2d_mode_switch_server.service && ss -ltn | grep -q ":8848"' \
  || {
    echo 'REFUSED: the persistent Orin mode-switch service is not active on TCP 8848.' >&2
    echo "Use $LEGACY_G1_DIR/g1_install_orin_mode_service_fix.sh for the existing service repair procedure, then retry." >&2
    exit 3
  }

if [[ "$execute" != true ]]; then
  cat <<EOF
Dry run complete: no robot mode was changed.
Planned standard GDK sequence:
  1. Send $A2D_GDK_DIR/conf/idle.pbtxt to 10.42.0.101:8848 (stops the current scene and PC forwarder).
  2. Send $A2D_GDK_DIR/conf/copilot.pbtxt (starts the Orin COPILOT scene).
  3. The GDK client checks robot/cameras and starts the PC forwarder.
To execute manually: $0 --execute --confirm $CONFIRMATION
EOF
  exit 0
fi

# ROS 2 Humble setup.bash intentionally references optional variables that
# may be unset. Temporarily disable nounset only while sourcing the vendor
# environment, then restore the script's strict mode before mode switching.
set +u
GDK_DIR="$A2D_GDK_DIR"
source "$SCRIPT_DIR/g1_pc_gdk_env.sh"
set -u
echo 'Switching current scene to idle; this stops VR/COPILOT and the local forwarder.'
"$CLIENT_PYTHON" -m a2d_sdk.tools.robot_service --start --config "$A2D_GDK_DIR/conf/idle.pbtxt"
sleep 3
echo 'Switching Orin to COPILOT; the GDK client validates readiness and starts the local forwarder.'
"$CLIENT_PYTHON" -m a2d_sdk.tools.robot_service --start --config "$A2D_GDK_DIR/conf/copilot.pbtxt"

# The persistent launcher keeps its original argv (often vr.json) even after
# scene_control changes its child component set. Verify COPILOT by components:
# the current G01 2.3.5 stack starts motion_control and camera_copilot, while
# the VR-only teleop_it process must be absent. Do not require the old
# vr_arm_control process name; it is not present in this installed stack.
scene_processes=""
for _ in $(seq 1 15); do
  scene_processes="$(clean_ssh -i "$ORIN_KEY" -o BatchMode=yes -o ConnectTimeout=8 "$ORIN_HOST" \
    'ps -eo args' || true)"
  if grep -q '[g]enie_motion_control' <<<"$scene_processes" \
     && grep -q '[c]amera_copilot' <<<"$scene_processes" \
     && ! grep -q '[t]eleop_it' <<<"$scene_processes"; then
    break
  fi
  sleep 2
done
if ! grep -q '[g]enie_motion_control' <<<"$scene_processes" \
   || ! grep -q '[c]amera_copilot' <<<"$scene_processes" \
   || grep -q '[t]eleop_it' <<<"$scene_processes"; then
  echo 'REFUSED: the mode API replied, but the Orin COPILOT component set was not active within 30 s.' >&2
  echo 'Check /data/logs/sdk_wrapper.txt on Orin before any motion.' >&2
  exit 4
fi

echo
echo 'COPILOT transition completed and its component set is active. Verify no competing command publisher before any motion:'
echo 'Waiting up to 30 s for the asynchronously started PC forwarder to expose HAL topics...'
hal_ready=false
for _ in $(seq 1 15); do
  hal_info="$(ros2 topic info /hal/whole_body_status 2>&1 || true)"
  if grep -Eq 'Publisher count: [1-9][0-9]*' <<<"$hal_info"; then
    hal_ready=true
    break
  fi
  sleep 2
done
if [[ "$hal_ready" != true ]]; then
  echo 'REFUSED: COPILOT is active but PC forwarder did not expose /hal/whole_body_status within 30 s.' >&2
  echo 'Do not move the robot; inspect the PC forwarder log before retrying.' >&2
  exit 5
fi
echo 'HAL topic is visible through the PC forwarder.'
if ! timeout 8 ros2 topic echo --once /hal/whole_body_status; then
  echo 'WARNING: no status message was printed within 8 s; forwarder is still running.' >&2
  echo 'Run: ros2 topic echo --once /hal/whole_body_status  (in a separate terminal) before motion.' >&2
fi
ros2 topic info /wbc/arm_command
