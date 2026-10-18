#!/bin/zsh
# Legacy entry: use the maintained hardware mode-switch script.
# With no arguments this performs only preflight checks.
ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
exec bash "$ROOT/hardware/g1/g1_enter_copilot.sh" "$@"
