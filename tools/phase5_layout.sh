#!/usr/bin/env bash
# Phase 5 layout chain: the copied Agilex board -> the Ti60 board, placed and fanned out (routing comes after).
#   tools/phase5_layout.sh [OUT.kicad_pcb]       (default: hardware/control_card.kicad_pcb)
# Needs the KiCad 10 AppImage environment (~/dev/proteus2kicad/bin/kicad_env.sh) and KiCadRoutingTools
# (~/dev/KiCadRoutingTools with its .venv). Work files go to build/phase5/.
#  1. phase5_sync     the Agilex board (git ad36d00) synced to the Ti60 schematic
#  2. phase5_place    floorplan: U1 rotated, memories swapped, translators in a row
#  3. phase5_vias     a 0.30/0.15 via in the pad of every U1 plane ball (JLC fills and caps via-in-pad on 6 layers)
#  4. bga_fanout      KRT, under-pad: 0.09 mm tracks at 0.125 mm clearance (0.2 mm to every 0.15 mm hole)
#                     (not REF_RES_2A on F6 and CRESET_N on J5: deep balls whose parts sit on the bottom; their
#                     F.Cu escapes came out on the south edge among the translator inputs, so the routing chain
#                     takes them down in the pad instead; nor J1_P26 on D12, which
#                     goes to J1 on L3 from a via in the ball pad: tools/phase5_j1.py)
#  5. phase5_decaps   Ti60 decoupling, VCCA filters, configuration parts, translator caps on the bottom at their pins
#  6. (none)          the flash pull-ups: R54/R58 on top south of the flash (phase5_place), R57/R59 and the
#                     HyperRAM's R24 on the bottom at a via in their memory ball (phase5_decaps)
#  7. phase5_power    supply copper fitted to the Ti60: dead Agilex copper out, buck output pours stitched to L4,
#                     supply/GND pads that lost their via tapped, one +1V8 pour over the whole of L3; then L4 split
#                     between +0V95 and +3V3 (KRT route_planes) and phase5_planes notch for the +3V3 vias it caught
set -euo pipefail
R="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$R/hardware/control_card.kicad_pcb}"
W="$R/build/phase5"
K="${KRT:-$HOME/dev/KiCadRoutingTools}"
E="${KICAD_ENV:-$HOME/dev/proteus2kicad/bin/kicad_env.sh}"
KP="$K/.venv/bin/python -X utf8"
# KRT checks pours and planes with KiCad's own filler when it finds a python with pcbnew
KICAD_PYTHON="$("$E" bash -c 'echo "$KICAD_MOUNT/bin/python3.11"')"; export KICAD_PYTHON
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
# 4. fan-out (plane balls already have their via; signals only). Not the seven header nets of HVIO bank TL (the
#    BGA's south-east corner) and the two on TR's inner balls C12/D12 (south-west): they go to J1 on L3 from a via
#    in the ball pad (tools/phase5_vias.py). Nor CLK100M on P2: down in the pad to R25 on the bottom, which keeps
#    one escape and its via out of the crowded north-east corner (JTAG, J1_P17, HT_SDATA)
TL=('!J1_P19' '!J1_P22' '!J1_P24' '!J1_P26' '!J1_P27' '!TX' '!CUK_SDATA' '!J1_P29' '!J1_P31' '!CLK100M')
(cd "$K" && $KP py_router/bga_fanout.py "$W/b1.kicad_pcb" -o "$W/b2.kicad_pcb" --component U1 --layers F.Cu B.Cu \
    --track-width 0.09 --clearance 0.125 --via-size 0.30 --via-drill 0.15 --escape-method underpad \
    --same-net-pad-clearance -1 --grid-step 0.025 --nets '*' '!GND' '!+1V8' '!+0V95' '!+3V3' '!/Configuration/REF_RES_2A' '!/Configuration/CRESET_N' "${TL[@]}" --plane-drop off \
    --fab-tier advanced --escalation off --no-fix-drc-settings > "$W/fanout.log" 2>&1) || { tail -20 "$W/fanout.log"; exit 1; }
grep -E "Under-pad escape" "$W/fanout.log" | head -1
# 5. decoupling and the rest at their pins (first the vias of CSI and CDONE at their escapes' ends, between the
#    flash lines that tools/phase5_mem.py draws in the routing chain, and those of J1_P17 and HT_SDATA)
kpy "$R/tools/phase5_mem.py" "$W/b2.kicad_pcb" "$W/b2.kicad_pcb" edge
kpy "$R/tools/phase5_lock.py" "$W/b2.kicad_pcb" "$W/b2.kicad_pcb"
kpy "$R/tools/phase5_decaps.py" "$W/b2.kicad_pcb" "$W/b3.kicad_pcb" > "$W/decaps.log"
grep -E "NO LEGAL|placed" "$W/decaps.log"
cp "$W/b0.kicad_pro" "$W/b3.kicad_pro"; cp "$W/b0.kicad_dru" "$W/b3.kicad_dru"
# 6. (the flash pull-ups are placed by phase5_place and phase5_decaps now: no KRT placer step)
cp "$W/b3.kicad_pcb" "$W/b4.kicad_pcb"
# 7. supply copper and the L4 split
kpy "$R/tools/phase5_power.py" "$W/b4.kicad_pcb" "$W/b5.kicad_pcb" | grep -v "memory leak"
kpy "$R/tools/phase5_planes.py" drop "$W/b5.kicad_pcb" "$W/b5.kicad_pcb" In3.Cu | grep -v "memory leak"
cp "$W/b0.kicad_pro" "$W/b5.kicad_pro"; cp "$W/b0.kicad_dru" "$W/b5.kicad_dru"
(cd "$K" && $KP py_router/route_planes.py "$W/b5.kicad_pcb" "$W/b6.kicad_pcb" --nets +0V95 +3V3 \
    --plane-layers In3.Cu In3.Cu --zone-clearance 0.15 --min-thickness 0.15 --no-thermal-vias --clearance 0.125 \
    --fab-tier advanced --escalation off --no-fix-drc-settings > "$W/planes.log" 2>&1) || { tail -20 "$W/planes.log"; exit 1; }
kpy "$R/tools/phase5_planes.py" notch "$W/b6.kicad_pcb" "$OUT" | grep -E "NO NOTCH|notches|north bay"
echo "wrote $OUT"
