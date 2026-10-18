#!/usr/bin/env bash
# Recreate only the local mode configs and SDK-to-Open-RAIL startup adapter.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
GDK_DIR="${GDK_DIR:-$ROOT/hardware/g1/vendor_packages/a2d_sdk-1.5.0}"
mkdir -p "$GDK_DIR/conf" "$GDK_DIR/scripts"
for mode in idle copilot; do
    cp "$ROOT/hardware/g1/conf/$mode.pbtxt" "$GDK_DIR/conf/$mode.pbtxt.new"
    mv "$GDK_DIR/conf/$mode.pbtxt.new" "$GDK_DIR/conf/$mode.pbtxt"
done
# Keep SDK's literal trailing '&' argument out of the strict repository wrapper.
printf '#!/usr/bin/env bash\nexec bash %q "${1:-}"\n' "$ROOT/hardware/g1/ros_env_wrapper.sh" > "$GDK_DIR/scripts/ros_env_wrapper.sh"
chmod +x "$GDK_DIR/scripts/ros_env_wrapper.sh"
echo "Mode configs and launch adapter prepared: $GDK_DIR"
echo 'This does not install missing forwarder binaries/libraries or SDK wheels.'
