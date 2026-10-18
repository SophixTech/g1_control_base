#!/usr/bin/env bash
# Compatibility entry; canonical hardware scripts live under hardware/g1.
exec bash "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/hardware/g1/g1_check_communication.sh" "$@"
