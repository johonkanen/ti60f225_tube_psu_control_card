#!/usr/bin/env bash
# Render copper layers of a board to PNG images (one per layer, cropped to the board) for visual review.
#   tools/render_layers.sh BOARD.kicad_pcb OUTDIR [LAYERS] [DPI]
# LAYERS: comma list, default F.Cu,In2.Cu,B.Cu; DPI default 1000 (~39 px/mm). Each image shows that layer with the
# board outline; zone fills are as last filled in the file (refill first if they matter). Needs the KiCad 10
# environment (~/dev/proteus2kicad/bin/kicad_env.sh) and pdftoppm (poppler-utils).
set -euo pipefail
B="$1"; O="$2"; LAYERS="${3:-F.Cu,In2.Cu,B.Cu}"; DPI="${4:-1000}"
E="${KICAD_ENV:-$HOME/dev/proteus2kicad/bin/kicad_env.sh}"
mkdir -p "$O"
# board outline in mm (the PDF puts the board at its own page coordinates when not scaled)
read -r X0 Y0 X1 Y1 < <("$E" bash -c '"$KICAD_MOUNT/bin/python3.11" -I -c "
import pcbnew, sys
b = pcbnew.LoadBoard(sys.argv[1]); e = b.GetBoardEdgesBoundingBox()
print(*(round(pcbnew.ToMM(v), 3) for v in (e.GetX(), e.GetY(), e.GetRight(), e.GetBottom())))
" "$1" 2>/dev/null | tail -1' _ "$B")
px() { python3 -c "print(int(round(($1) / 25.4 * $DPI)))"; }
CX=$(px "$X0 - 0.5"); CY=$(px "$Y0 - 0.5"); CW=$(px "$X1 - $X0 + 1"); CH=$(px "$Y1 - $Y0 + 1")
IFS=, read -ra LS <<< "$LAYERS"
for L in "${LS[@]}"; do
    "$E" kicad-cli pcb export pdf --layers "$L,Edge.Cuts" --mode-single -o "$O/$L.pdf" "$B" > /dev/null
    pdftoppm -r "$DPI" -x "$CX" -y "$CY" -W "$CW" -H "$CH" -png -singlefile "$O/$L.pdf" "$O/$L"
    rm -f "$O/$L.pdf"
    echo "$O/$L.png"
done
