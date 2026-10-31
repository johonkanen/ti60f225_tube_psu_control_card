#!/usr/bin/env bash
# Phase 5 layout chain: the copied Agilex board -> the Ti60 board, placed and fanned out (routing comes after).
#   tools/phase5_layout.sh [OUT.kicad_pcb]       (default: hardware/control_card.kicad_pcb)
# Needs the KiCad 10 AppImage environment (~/dev/proteus2kicad/bin/kicad_env.sh) and KiCadRoutingTools
# (~/dev/KiCadRoutingTools with its .venv). Work files go to build/phase5/.
#  1. phase5_sync     the Agilex board (git ad36d00) synced to the Ti60 schematic
#  2. phase5_place    floorplan: U1 rotated, memories swapped, translators in a row
#  3. phase5_vias     a 0.30/0.15 via in the pad of every U1 plane ball (JLC fills and caps via-in-pad on 6 layers)
#  4. bga_fanout      KRT, under-pad: 0.09 mm tracks at 0.125 mm clearance (0.2 mm to every 0.15 mm hole)
#  5. phase5_decaps   Ti60 decoupling, VCCA filters, configuration parts, translator caps on the bottom at their pins
#  6. place_simple    KRT places the flash and JTAG pull-ups (tools/phase5/groups.json, intent.json); 8 seeds,
#                     the first judged one is kept, then phase5_decaps --legalise moves them off other nets' copper
set -euo pipefail
R="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$R/hardware/control_card.kicad_pcb}"
W="$R/build/phase5"
K="${KRT:-$HOME/dev/KiCadRoutingTools}"
E="${KICAD_ENV:-$HOME/dev/proteus2kicad/bin/kicad_env.sh}"
KP="$K/.venv/bin/python -X utf8"
kpy() { "$E" bash -c '"$KICAD_MOUNT/bin/python3.11" -I "$@"' kpy "$@"; }
mkdir -p "$W/agilex" "$W/place"

# 1. sync (old netlist from the Agilex schematic at ad36d00, new from the current schematic)
git -C "$R" archive ad36d00 hardware | tar -x -C "$W/agilex"
"$E" kicad-cli sch export netlist --format kicadsexpr -o "$W/old.net" "$W/agilex/hardware/control_card.kicad_sch" >/dev/null
"$E" kicad-cli sch export netlist --format kicadsexpr -o "$W/new.net" "$R/hardware/control_card.kicad_sch" >/dev/null
cp "$W/agilex/hardware/control_card.kicad_pcb" "$W/b0.kicad_pcb"
cp "$R/hardware/control_card.kicad_pro" "$W/b0.kicad_pro"
cp "$R/hardware/control_card.kicad_dru" "$W/b0.kicad_dru"
kpy "$R/tools/phase5_sync.py" "$W/old.net" "$W/new.net" "$W/b0.kicad_pcb"
# 2.-3.
kpy "$R/tools/phase5_place.py" "$W/b0.kicad_pcb"
kpy "$R/tools/phase5_vias.py" "$W/b0.kicad_pcb" "$W/b1.kicad_pcb"
cp "$W/b0.kicad_pro" "$W/b1.kicad_pro"; cp "$W/b0.kicad_dru" "$W/b1.kicad_dru"
# 4. fan-out (plane balls already have their via; signals only)
(cd "$K" && $KP py_router/bga_fanout.py "$W/b1.kicad_pcb" -o "$W/b2.kicad_pcb" --component U1 --layers F.Cu B.Cu \
    --track-width 0.09 --clearance 0.125 --via-size 0.30 --via-drill 0.15 --escape-method underpad \
    --same-net-pad-clearance -1 --grid-step 0.025 --nets '*' '!GND' '!+1V8' '!+0V95' '!+3V3' --plane-drop off \
    --fab-tier advanced --escalation off --no-fix-drc-settings > "$W/fanout.log" 2>&1) || { tail -20 "$W/fanout.log"; exit 1; }
grep -E "Under-pad escape" "$W/fanout.log" | head -1
# 5. decoupling and the rest at their pins
kpy "$R/tools/phase5_lock.py" "$W/b2.kicad_pcb" "$W/b2.kicad_pcb"
kpy "$R/tools/phase5_decaps.py" "$W/b2.kicad_pcb" "$W/b3.kicad_pcb" > "$W/decaps.log"
grep -E "NO LEGAL|placed" "$W/decaps.log"
cp "$W/b0.kicad_pro" "$W/b3.kicad_pro"; cp "$W/b0.kicad_dru" "$W/b3.kicad_dru"
# 6. KRT placer for the flash and JTAG pull-ups
kpy "$R/tools/phase5_lock.py" "$W/b3.kicad_pcb" "$W/b3.kicad_pcb"
(cd "$K" && $KP py_placer/place_simple.py "$W/b3.kicad_pcb" "$W/place/s{seed}.kicad_pcb" \
    --groups "$R/tools/phase5/groups.json" --intent "$R/tools/phase5/intent.json" \
    --scattered 4 --clustered 4 --judge 4 --jobs 4 --json "$W/place/s{seed}.json" > "$W/place.log" 2>&1) \
    || { tail -20 "$W/place.log"; exit 1; }
SEED=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['judge'][0])" "$W/place/judge.json")
echo "place_simple: seed $SEED kept"
kpy "$R/tools/phase5_decaps.py" "$W/place/s$SEED.kicad_pcb" "$OUT" --legalise R54 R57 R58 R59 R60 R61 R62 R63 | tail -1
kpy "$R/tools/phase5_lock.py" "$OUT" "$OUT" --unlock
echo "wrote $OUT"
