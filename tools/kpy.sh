#!/usr/bin/env bash
# Run a pcbnew Python script in the KiCad 10 environment:  tools/kpy.sh SCRIPT.py [ARGS...]
E="${KICAD_ENV:-$HOME/dev/proteus2kicad/bin/kicad_env.sh}"
"$E" bash -c '"$KICAD_MOUNT/bin/python3.11" -I "$@" 2>&1 | grep -v "memory leak"' kpy "$@"
