#!/usr/bin/env bash
# Phase 5 routing chain with KiCadRoutingTools, on the placed board from tools/phase5_layout.sh.
#   tools/phase5_route.sh [IN.kicad_pcb] [OUT.kicad_pcb] [LAST_STEP]
#   (default: build/phase5/placed.kicad_pcb -> build/phase5/routed.kicad_pcb, every step)
#   FROM=STEP tools/phase5_route.sh ...   resumes at STEP on the work files of an earlier run (the steps before it
#                                         are not run again; their NN_step.kicad_pcb must exist)
# Work files in build/phase5/route/ (NN_step.kicad_pcb, .log, .json). Rules for every routing step: 0.1 mm tracks
# at 0.125 mm clearance with 0.30/0.15 vias (0.125 + 0.075 via ring = JLC's 0.2 mm via-hole-to-track), signal
# layers F.Cu and L3 (In2.Cu), F.Cu preferred; the GND layers and the split L4 are never routed; B.Cu only in the
# steps for nets whose parts sit on the bottom. Each step routes one group of tools/phase5/route_groups.json with
# the earlier copper protected (tools/krt_route.py); one run over every net at once tangles the south band.
# Layout with U1 at 180 deg (2026-11-14): translator inputs leave the BGA's south edge, the HyperRAM its north
# edge (banks 4A/4B), the ADC nets its west edge (3A/3B), flash and JTAG its north-east corner next to J2.
#  prep   L3 +1V8 pour dropped (KRT routes no track through another net's pour; poured again at the end), old
#         power-good, JTAG and Agilex plane-layer copper stripped, J1 second-row stubs and resistor stubs,
#         escape stubs out of the memories' ball fields (tools/phase5_mem.py)
#  band   translator outputs (F.Cu only, second-row nets first), translator inputs (F.Cu only, innermost fan
#         first, so every later net passes outside the earlier ones), then the direct header nets: bank TR
#         (south-west) on F.Cu, bank TL (south-east) on L3 from vias in the ball pads
#  rest   HyperRAM, flash, JTAG, the two header nets of bank BL (north-east), LEDs, ADC, configuration, power control
#  pour   +1V8 on L3 around the tracks (KRT route_planes), filled, then the supply stubs
set -euo pipefail
R="$(cd "$(dirname "$0")/.." && pwd)"
IN="${1:-$R/build/phase5/placed.kicad_pcb}"
OUT="${2:-$R/build/phase5/routed.kicad_pcb}"
LAST="${3:-}"
FROM="${FROM:-}"
W="$R/build/phase5/route"
K="${KRT:-$HOME/dev/KiCadRoutingTools}"
E="${KICAD_ENV:-$HOME/dev/proteus2kicad/bin/kicad_env.sh}"
KP="$K/.venv/bin/python -X utf8"
# KRT checks pours and planes with KiCad's own filler when it finds a python with pcbnew; without it those checks
# are silently off
KICAD_PYTHON="$("$E" bash -c 'echo "$KICAD_MOUNT/bin/python3.11"')"; export KICAD_PYTHON
kpy() { "$R/tools/kpy.sh" "$@"; }
sib() { for x in kicad_pro kicad_dru; do cp "$R/hardware/control_card.$x" "${1%.kicad_pcb}.$x"; done; }
SKIP=0
if [ -n "$FROM" ]; then SKIP=1; else rm -rf "$W"; fi
mkdir -p "$W"
CUR="$W/00_in.kicad_pcb"
N=0
step() {    # step NAME GROUPS [route.py options]: routes from $CUR into NN_NAME.kicad_pcb
    N=$((N + 1)); local out; out="$W/$(printf %02d "$N")_$1.kicad_pcb"
    if [ "$SKIP" = 1 ] && [ "$1" != "$FROM" ]; then CUR="$out"; return; fi
    if [ "$SKIP" = 1 ]; then SKIP=0; [ -f "$CUR" ] || { echo "FROM=$FROM: $CUR missing"; exit 1; }; fi
    echo "== $1"
    python3 -I "$R/tools/krt_route.py" "$CUR" "$out" "${@:2}" 2>&1 | cut -c1-400
    CUR="$out"
    if [ "$LAST" = "$1" ]; then cp "$CUR" "$OUT"; echo "stopped after $1: wrote $OUT"; exit 0; fi
}
BOT=(--layers F.Cu In2.Cu B.Cu --layer-costs 1 4 2)        # for nets with bottom-side parts
lock() { [ "$SKIP" = 1 ] || kpy "$R/tools/phase5_lock_tracks.py" "$CUR" lock "$1" | tail -1; }   # finished nets: never ripped later

# prep
if [ "$SKIP" = 0 ]; then
    cp "$IN" "$CUR"; sib "$CUR"
    kpy "$R/tools/phase5_planes.py" drop "$CUR" "$W/00_a.kicad_pcb" In2.Cu
    kpy "$R/tools/phase5_strip.py" "$W/00_a.kicad_pcb" "$W/00_b.kicad_pcb"
    kpy "$R/tools/phase5_j1.py" "$W/00_b.kicad_pcb" "$W/00_c.kicad_pcb" stubs
    kpy "$R/tools/phase5_j1.py" "$W/00_c.kicad_pcb" "$W/00_e.kicad_pcb" pulldowns
    kpy "$R/tools/phase5_mem.py" "$W/00_e.kicad_pcb" "$W/00_d.kicad_pcb"
    cp "$W/00_d.kicad_pcb" "$W/00_prep.kicad_pcb"; sib "$W/00_prep.kicad_pcb"
    # the scripted copper must be legal before the router builds on it
    "$E" kicad-cli pcb drc --severity-all --format json -o "$W/00_prep.json" "$W/00_prep.kicad_pcb" > /dev/null 2>&1 || true
    python3 -I "$R/tools/phase5_prep_check.py" "$W/00_prep.json"
fi
CUR="$W/00_prep.kicad_pcb"; [ "$SKIP" = 1 ] || sib "$CUR"
# the configuration parts on the bottom at their balls (REF_RES, CRESET_N, CDONE, CSI): down at the escape's end
# and across on B.Cu, before the band closes around the balls
step bottom_cfg bottom_cfg --layers F.Cu In2.Cu B.Cu --layer-costs 3 8 1;   lock bottom_cfg
# band
step xlat_out xlat_out --layers F.Cu --ordering original;        lock xlat_out
step xlat_in xlat_in --layers F.Cu --ordering original;          lock xlat_in
step j1_west j1_west --layers F.Cu --ordering original;          lock j1_west
# the nets with a via in their ball pad: on L3 only, straight to the header pin (or its scripted L3 stub)
step j1_west_l3 j1_west_l3 --layers In2.Cu --ordering original;  lock j1_west_l3
step j1_east j1_east --layers In2.Cu --ordering original;        lock j1_east
step xlat_oe xlat_oe "${BOT[@]}";                                lock xlat_oe
# rest
# (the HyperRAM bus and five of the flash lines are drawn and locked by tools/phase5_mem.py in the prep)
# the flash pull-ups on the bottom (IO2, IO3, RESET#) to the via in their flash ball, where they do not sit on it
step flash_pu flash_pu --layers F.Cu In2.Cu B.Cu --layer-costs 3 8 1;   lock flash_pu
# J1_P17 and HT_SDATA come from bank BL in the north-east corner: from their scripted vias north of the BGA
# (tools/phase5_mem.py) on L3 only, down the east side (--keepout: not under the BGA, where L3 tracks fence VCCIO
# vias off the +1V8 pour)
step j1_far j1_far --layers In2.Cu --ordering original --keepout;               lock j1_far
# JTAG: the balls sit 10 mm from J2 now, but the flash lines run between them and the header on F.Cu: down at the
# escape's end (or in the ball), on B.Cu to the header pins (through-hole) and the pull-ups beside them
step jtag jtag --layers F.Cu In2.Cu B.Cu --layer-costs 2 10 1 --via-cost 100;   lock jtag
# LEDs: from the north-west corner to their resistors on F.Cu, the inner one first (ball order = resistor order)
step leds leds --layers F.Cu --ordering original
step leds_l3 leds --layer-costs 3 1 --via-cost 50 --ordering original --keepout;   lock leds   # the rest, if any
step adc adc "${BOT[@]}";                                        lock adc
step config config --layers F.Cu In2.Cu B.Cu --layer-costs 1 5 1.5;  lock config
# the power-good lines join bottom-side parts across the board: on B.Cu, not through the L3 pour under the BGA
step power_ctl power_ctl,adc_analog --layers F.Cu In2.Cu B.Cu --layer-costs 2 8 1
# whatever a step left open, with B.Cu allowed as the last resort
step leftovers leds,led_k,jtag,config,bottom_cfg,adc,flash,flash_pu,j1_east,j1_west_l3,j1_far,hyperram --layers F.Cu In2.Cu B.Cu --layer-costs 1 10 2
# pour, then the supply stubs (with the pour dropped or not filled the router joins the +1V8 pads by tracks)
N=$((N + 1)); P="$W/$(printf %02d "$N")_pour.kicad_pcb"
if [ "$SKIP" = 1 ] && [ "$FROM" != pour ]; then CUR="$P"; else
    SKIP=0
    (cd "$K" && $KP py_router/route_planes.py "$CUR" "$P" --nets +1V8 --plane-layers In2.Cu \
        --zone-clearance 0.15 --min-thickness 0.15 --no-thermal-vias --clearance 0.125 --fab-tier advanced \
        --escalation off --no-fix-drc-settings > "${P%.kicad_pcb}.log" 2>&1) || { tail -20 "${P%.kicad_pcb}.log"; exit 1; }
    kpy "$R/tools/phase5_fill.py" "$P" "$P" | tail -1     # the router reads a pour's connectivity from its fill
    CUR="$P"; sib "$CUR"
fi
if [ "$LAST" = "pour" ]; then kpy "$R/tools/phase5_lock_tracks.py" "$CUR" unlock | tail -1; cp "$CUR" "$OUT"; echo "stopped after pour: wrote $OUT"; exit 0; fi
step supply supply --layers F.Cu In2.Cu B.Cu --layer-costs 1 6 1 --power-nets '+0V95' '+1V8' '+3V3' '+5V' '+3V3A' '*VCCA*' '+1V8_OSC' \
    --power-nets-widths 0.3 0.3 0.3 0.3 0.25 0.2 0.2
kpy "$R/tools/phase5_lock_tracks.py" "$CUR" unlock | tail -1
# L4: a signal via placed by the router can cut the channel that joins a +3V3 ball via inside the +0V95 island to the
# +3V3 plane (the HVIO corner balls): the notch step again, on the vias as they are now
kpy "$R/tools/phase5_planes.py" notch "$CUR" "$CUR" | grep -E "NO NOTCH|notch" || true
# manufacturing fixes: undersized vias to 0.30/0.15, three fiducials per side (tools/phase5_fab.py)
kpy "$R/tools/phase5_fab.py" "$CUR" "$OUT"
echo "wrote $OUT"
