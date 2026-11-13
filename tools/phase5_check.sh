#!/usr/bin/env bash
# Checks after a routing run: DRC with zones refilled and schematic parity, summarised; plane islands, plane vias,
# tracks on plane layers; signal via count.
#   tools/phase5_check.sh BOARD.kicad_pcb [WORKDIR]      (default work dir: build/phase5/check)
# The refilled board is left in WORKDIR/control_card.kicad_pcb (render that one to see the pours).
set -euo pipefail
R="$(cd "$(dirname "$0")/.." && pwd)"
B="$1"; W="${2:-$R/build/phase5/check}"
E="${KICAD_ENV:-$HOME/dev/proteus2kicad/bin/kicad_env.sh}"
rm -rf "$W"; mkdir -p "$W"
cp "$B" "$W/control_card.kicad_pcb"
cp "$R/hardware/control_card.kicad_pro" "$R/hardware/control_card.kicad_dru" "$R/hardware/control_card.kicad_sch" \
   "$R/hardware/fp-lib-table" "$R/hardware/sym-lib-table" "$W/"
cp -r "$R/hardware/sheets" "$R/hardware/lib" "$W/"
"$E" kicad-cli pcb drc --refill-zones --save-board --severity-all --schematic-parity --format json \
    -o "$W/drc.json" "$W/control_card.kicad_pcb" > "$W/drc.log" 2>&1 || true
python3 -I "$R/tools/phase5_check_summary.py" "$W/drc.json"
"$R/tools/kpy.sh" "$R/tools/phase5_check_planes.py" "$W/control_card.kicad_pcb"
"$R/tools/kpy.sh" "$R/tools/board_stats.py" "$W/control_card.kicad_pcb"
