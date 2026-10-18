#!/usr/bin/env bash
# Compatibility entry; canonical hardware scripts live under hardware/g1.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    echo "Please source this file: source ${BASH_SOURCE[0]}" >&2
    exit 1
fi
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/hardware/g1/g1_pc_gdk_env.sh"
