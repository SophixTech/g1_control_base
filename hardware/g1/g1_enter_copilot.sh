#!/usr/bin/env bash
# Switch this G1 from any current scene (including VR) to idle, then COPILOT.
# Default is read-only validation; --execute needs an exact confirmation.
set -euo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
readonly A2D_GDK_DIR="${GDK_DIR:-$REPO_DIR/hardware/g1/vendor_packages/a2d_sdk-1.5.0}"
readonly ORIN_HOST="agi@10.42.0.101"
readonly ORIN_KEY="${ORIN_KEY:-$REPO_DIR/.local/robot/orin_g1_ed25519}"
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

# Complete all local checks before sending IDLE, which stops the live bridge.
# A deleted-but-running bridge must not be stopped until its replacement loads.
set +u
GDK_DIR="$A2D_GDK_DIR"
source "$SCRIPT_DIR/g1_pc_gdk_env.sh"
set -u
forwarder="$A2D_GDK_DIR/forwarder/app/bin/forwarder"
if [[ ! -x "$forwarder" || ! -x "$A2D_GDK_DIR/scripts/ros_env_wrapper.sh" ]]; then
  echo "REFUSED: incomplete local forwarder runtime under $A2D_GDK_DIR; existing mode was not changed." >&2
  exit 2
fi
if ! loader_check="$(ldd "$forwarder" 2>&1)" || grep -q 'not found' <<<"$loader_check"; then
  echo 'REFUSED: forwarder has unresolved libraries; existing mode was not changed.' >&2
  echo "$loader_check" >&2
  exit 2
fi
"$CLIENT_PYTHON" -c 'import a2d_sdk.robot, a2d_sdk.tools.robot_service'

echo 'Checking the Orin mode-switch API and persistent service...'
clean_ssh -i "$ORIN_KEY" -o BatchMode=yes -o ConnectTimeout=8 "$ORIN_HOST" \
  'systemctl is-active --quiet a2d_mode_switch_server.service && ss -ltn | grep -q ":8848"' \
  || {
    echo 'REFUSED: the persistent Orin mode-switch service is not active on TCP 8848.' >&2
    echo 'Inspect a2d_mode_switch_server.service on Orin before retrying.' >&2
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
echo 'COPILOT component set is active. Checking live SDK feedback and cameras...'
if ! timeout --kill-after=3 35 "$CLIENT_PYTHON" "$SCRIPT_DIR/g1_check_communication.py" --timeout 30; then
  echo 'REFUSED: live SDK communication verification failed; do not send motion commands.' >&2
  exit 5
fi
echo 'Communication verified. Check competing controllers before enabling motion.'
