# Usage: source ./activate_uv.sh
_ORI_V2_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
source "$_ORI_V2_ROOT/.venv/bin/activate"
export PYTHONNOUSERSITE=1
unset PYTHONPATH PYTHONHOME
export UV_CACHE_DIR="$_ORI_V2_ROOT/../.cache/uv"
unset _ORI_V2_ROOT
