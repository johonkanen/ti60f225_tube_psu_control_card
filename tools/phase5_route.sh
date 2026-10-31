#!/usr/bin/env bash
# Phase 5 routing chain with KiCadRoutingTools, on the placed board from tools/phase5_layout.sh.
#   tools/phase5_route.sh [IN.kicad_pcb] [OUT.kicad_pcb]   (default: hardware/control_card.kicad_pcb, in place)
# Work files in build/phase5/route/. Rules for every routing step: 0.1 mm tracks at 0.125 mm clearance with
# 0.30/0.15 vias (0.125 + 0.075 via ring = JLC's 0.2 mm via-hole-to-track; KRT itself holds hole clearance only at
# NPTH walls), signal layers F.Cu, L3 (In2.Cu) and B.Cu; the GND layers and the split L4 are never routed.
#  1. L4 (In3.Cu): old zones dropped, KRT route_planes splits it between +0V95 and +3V3, phase5_planes notches
#     the +0V95 island for the +3V3 vias it caught
#  2. L3 +1V8 pour dropped: KRT routes no track through another net's pour; it is poured again in step 5
#  3. HyperRAM: HR_DQ3 (three pads, FPGA / RAM / TEST_N pull-up) alone first, then the rest with earlier copper
#     protected, as one length-match group (DQ, RWDS, CS#)
#  4. every other net on a 0.025 mm grid (J1 is a 1.27 mm header: a track between its pads only fits centred);
#     supply pads are tapped into their planes by the route step
#  5. +1V8 poured on L3 around the tracks (KRT route_planes)
set -euo pipefail
R="$(cd "$(dirname "$0")/.." && pwd)"
IN="${1:-$R/hardware/control_card.kicad_pcb}"
OUT="${2:-$IN}"
W="$R/build/phase5/route"
K="${KRT:-$HOME/dev/KiCadRoutingTools}"
E="${KICAD_ENV:-$HOME/dev/proteus2kicad/bin/kicad_env.sh}"
KP="$K/.venv/bin/python -X utf8"
kpy() { "$E" bash -c '"$KICAD_MOUNT/bin/python3.11" -I "$@" 2>&1 | grep -v "memory leak"' kpy "$@"; }
sib() { for x in kicad_pro kicad_dru; do cp "$R/hardware/control_card.$x" "${1%.kicad_pcb}.$x"; done; }
mkdir -p "$W"
COMMON=(--clearance 0.125 --fab-tier advanced --escalation off --no-fix-drc-settings)
ROUTE=(--layers F.Cu In2.Cu B.Cu --track-width 0.1 --via-size 0.3 --via-drill 0.15 --no-bga-zones U1 U7 U9 "${COMMON[@]}")

cp "$IN" "$W/r0.kicad_pcb"; sib "$W/r0.kicad_pcb"
# 1.-2. planes
kpy "$R/tools/phase5_planes.py" drop "$W/r0.kicad_pcb" "$W/r0.kicad_pcb" In3.Cu
(cd "$K" && $KP py_router/route_planes.py "$W/r0.kicad_pcb" "$W/r1.kicad_pcb" --nets +0V95 +3V3 \
    --plane-layers In3.Cu In3.Cu --zone-clearance 0.15 --min-thickness 0.15 --no-thermal-vias "${COMMON[@]}" \
    > "$W/r1.log" 2>&1) || { tail -20 "$W/r1.log"; exit 1; }
sib "$W/r1.kicad_pcb"
kpy "$R/tools/phase5_planes.py" notch "$W/r1.kicad_pcb" "$W/r1.kicad_pcb" | tail -1
kpy "$R/tools/phase5_planes.py" drop "$W/r1.kicad_pcb" "$W/r1.kicad_pcb" In2.Cu
# 3. HyperRAM
(cd "$K" && $KP py_router/route.py "$W/r1.kicad_pcb" "$W/r2.kicad_pcb" --nets HR_DQ3 "${ROUTE[@]}" \
    --layer-costs 1 4 1.5 --grid-step 0.025 > "$W/r2.log" 2>&1) || { tail -20 "$W/r2.log"; exit 1; }
sib "$W/r2.kicad_pcb"
(cd "$K" && KICAD_RIP_PREEXISTING=0 $KP py_router/route.py "$W/r2.kicad_pcb" "$W/r3.kicad_pcb" \
    --nets HR_DQ0 HR_DQ1 HR_DQ2 HR_DQ4 HR_DQ5 HR_DQ6 HR_DQ7 HR_RWDS HR_CS_N HR_CK HR_RESET_N "${ROUTE[@]}" \
    --layer-costs 1 4 1.5 --grid-step 0.025 --length-match-group 'HR_DQ*' HR_RWDS HR_CS_N \
    --length-match-tolerance 0.2 > "$W/r3.log" 2>&1) || { tail -20 "$W/r3.log"; exit 1; }
sib "$W/r3.kicad_pcb"
# 4. everything else
(cd "$K" && $KP py_router/route.py "$W/r3.kicad_pcb" "$W/r4.kicad_pcb" --nets '*' "${ROUTE[@]}" \
    --layer-costs 1 1.3 1.2 --grid-step 0.025 --no-smoothing \
    --power-nets '+0V95' '+1V8' '+3V3' '+5V' '+3V3A' '*VCCA*' --power-nets-widths 0.3 0.3 0.3 0.3 0.25 0.2 \
    --json-out "$W/r4.json" > "$W/r4.log" 2>&1) || { tail -20 "$W/r4.log"; exit 1; }
grep -E "Single-ended:|Multi-point:|Ships" "$W/r4.log" | tail -3
sib "$W/r4.kicad_pcb"
# 5. +1V8 pour on L3
(cd "$K" && $KP py_router/route_planes.py "$W/r4.kicad_pcb" "$W/r5.kicad_pcb" --nets +1V8 --plane-layers In2.Cu \
    --zone-clearance 0.15 --min-thickness 0.15 --no-thermal-vias "${COMMON[@]}" > "$W/r5.log" 2>&1) \
    || { tail -20 "$W/r5.log"; exit 1; }
cp "$W/r5.kicad_pcb" "$OUT"
echo "wrote $OUT"
