#!/usr/bin/env bash
# Run a pcbnew Python script in the KiCad 10 environment:  tools/kpy.sh SCRIPT.py [ARGS...]
E="${KICAD_ENV:-$HOME/dev/proteus2kicad/bin/kicad_env.sh}"
# (the script's exit status is kept: a failed step must stop the chain that called it)
"$E" bash -c 'set -o pipefail; "$KICAD_MOUNT/bin/python3.11" -I "$@" 2>&1 | { grep -v "memory leak" || true; }' kpy "$@"
