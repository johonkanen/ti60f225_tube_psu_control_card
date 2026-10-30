#!/usr/bin/env bash
# Phase 4 pin plan: export the schematic netlist with KiCad, check it in Efinity's Interface Designer,
# and with --compile also build a stub design through synthesis, place and route and bitstream (x4).
#   efinity/pinplan/run.sh [--compile]
# Needs the KiCad 10 AppImage environment (~/dev/proteus2kicad/bin/kicad_env.sh) and Efinity 2026.1 (~/efinity/2026.1).
set -euo pipefail
R="$(cd "$(dirname "$0")/../.." && pwd)"
B="$R/efinity/pinplan/build"
mkdir -p "$B"
"${KICAD_ENV:-$HOME/dev/proteus2kicad/bin/kicad_env.sh}" kicad-cli sch export netlist --format kicadsexpr \
    -o "$B/schematic.net" "$R/hardware/control_card.kicad_sch" >/dev/null
# shellcheck disable=SC1091
set +eu
source "${EFINITY_HOME:-$HOME/efinity/2026.1}/bin/setup.sh" >/dev/null 2>&1
set -eu
cd "$B"
python3 "$R/efinity/pinplan/pinplan.py" "$B/schematic.net"
if [ "${1:-}" = "--compile" ]; then
    python3 "$R/efinity/pinplan/stub.py"
    rm -rf work_syn work_pnr
    efx_run ti60f225_pinplan.xml --prj --flow compile > compile.log 2>&1 || { tail -20 compile.log; exit 1; }
    grep -E 'PASS|FAIL' compile.log
    sed -n '/Clock Relationship Summary (begin)/,/Clock Relationship Summary (end)/p' outflow/ti60f225_pinplan.timing.rpt
fi
