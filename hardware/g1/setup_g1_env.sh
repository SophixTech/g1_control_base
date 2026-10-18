#!/usr/bin/env bash
# Create the client/SDK environment without touching LingBot's training environment.
set -euo pipefail

OPEN_RAIL_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
GDK_DIR="${GDK_DIR:-$OPEN_RAIL_ROOT/hardware/g1/vendor_packages/a2d_sdk-1.5.0}"
UV_BIN="${UV_BIN:-uv}"
CLIENT_PYTHON="$OPEN_RAIL_ROOT/.venv/bin/python"

if [[ ! -d "$OPEN_RAIL_ROOT/.venv" ]]; then
    "$UV_BIN" venv --python "${OPEN_RAIL_BASE_PYTHON:-/usr/bin/python3.10}" "$OPEN_RAIL_ROOT/.venv"
fi
"$CLIENT_PYTHON" -c 'import sys; assert sys.version_info[:2] == (3, 10), "G1 SDK wheels require Python 3.10"'

# ruckig 0.14 may build from source. Use its compatible build tools and limit CPU load.
build_constraints="$(mktemp)"
trap 'rm -f "$build_constraints"' EXIT
printf '%s\n' 'scikit-build-core<0.10' 'pybind11<3' > "$build_constraints"
export CMAKE_BUILD_PARALLEL_LEVEL="${CMAKE_BUILD_PARALLEL_LEVEL:-2}"
"$UV_BIN" pip install --python "$CLIENT_PYTHON" --build-constraints "$build_constraints" \
    --editable "$OPEN_RAIL_ROOT" \
    'protobuf==3.12.4' 'ruckig==0.14.0' \
    "$GDK_DIR/a2d_sdk-1.5.0-py3-none-any.whl" \
    "$GDK_DIR/genie_msgs_pb-0.8.0-py3-none-any.whl" \
    "$GDK_DIR/cosine_bus-2.0.0-cp310-cp310-linux_$(uname -m).whl"
"$UV_BIN" pip check --python "$CLIENT_PYTHON"
echo "Open-RAIL client environment ready: $CLIENT_PYTHON"
