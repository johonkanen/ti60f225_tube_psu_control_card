#!/usr/bin/env bash
# Phase 5 routing chain with KiCadRoutingTools, on the placed board from tools/phase5_layout.sh.
#   tools/phase5_route.sh [IN.kicad_pcb] [OUT.kicad_pcb] [LAST_STEP]
#   (default: build/phase5/placed.kicad_pcb -> build/phase5/routed.kicad_pcb, every step)
# Work files in build/phase5/route/ (NN_step.kicad_pcb, .log, .json). Rules for every routing step: 0.1 mm tracks
# at 0.125 mm clearance with 0.30/0.15 vias (0.125 + 0.075 via ring = JLC's 0.2 mm via-hole-to-track), signal
# layers F.Cu and L3 (In2.Cu), F.Cu preferred; the GND layers and the split L4 are never routed; B.Cu only in the
# steps for nets whose parts sit on the bottom. Each step routes one group of tools/phase5/route_groups.json with
# the earlier copper protected (tools/krt_route.py); one run over every net at once tangles the south band.
#  prep   L3 +1V8 pour dropped (KRT routes no track through another net's pour; poured again at the end), old
#         power-good copper stripped, J1 second-row stubs and resistor stubs
#  band   translator outputs (F.Cu only, second-row nets first), translator inputs (F.Cu only, innermost fan
#         first, so every later net passes outside the earlier ones), then the direct header nets
#  rest   HyperRAM, flash, ADC, LEDs, JTAG, configuration, power control
#  pour   +1V8 on L3 around the tracks (KRT route_planes), then the supply stubs
set -euo pipefail
R="$(cd "$(dirname "$0")/.." && pwd)"
IN="${1:-$R/build/phase5/placed.kicad_pcb}"
OUT="${2:-$R/build/phase5/routed.kicad_pcb}"
LAST="${3:-}"
W="$R/build/phase5/route"
K="${KRT:-$HOME/dev/KiCadRoutingTools}"
KP="$K/.venv/bin/python -X utf8"
kpy() { "$R/tools/kpy.sh" "$@"; }
sib() { for x in kicad_pro kicad_dru; do cp "$R/hardware/control_card.$x" "${1%.kicad_pcb}.$x"; done; }
rm -rf "$W"; mkdir -p "$W"
CUR="$W/00_in.kicad_pcb"; cp "$IN" "$CUR"; sib "$CUR"
N=0
step() {    # step NAME GROUPS [route.py options]: routes from $CUR into NN_NAME.kicad_pcb
    N=$((N + 1)); local out; out="$W/$(printf %02d "$N")_$1.kicad_pcb"
    echo "== $1"
    python3 -I "$R/tools/krt_route.py" "$CUR" "$out" "${@:2}" 2>&1 | cut -c1-400
    CUR="$out"
    if [ "$LAST" = "$1" ]; then cp "$CUR" "$OUT"; echo "stopped after $1: wrote $OUT"; exit 0; fi
}
BOT=(--layers F.Cu In2.Cu B.Cu --layer-costs 1 4 2)        # for nets with bottom-side parts
lock() { kpy "$R/tools/phase5_lock_tracks.py" "$CUR" lock "$1" | tail -1; }   # finished nets: never ripped later

# prep
kpy "$R/tools/phase5_planes.py" drop "$CUR" "$W/00_a.kicad_pcb" In2.Cu
kpy "$R/tools/phase5_strip.py" "$W/00_a.kicad_pcb" "$W/00_b.kicad_pcb"
kpy "$R/tools/phase5_j1.py" "$W/00_b.kicad_pcb" "$W/00_c.kicad_pcb" stubs
kpy "$R/tools/phase5_j1.py" "$W/00_c.kicad_pcb" "$W/00_d.kicad_pcb" pulldowns
cp "$W/00_d.kicad_pcb" "$W/00_prep.kicad_pcb"
CUR="$W/00_prep.kicad_pcb"; sib "$CUR"
# the configuration parts on the bottom at their balls (REF_RES, CRESET_N, CDONE, CSI): down at the escape's end
# and across on B.Cu, before the band closes around the balls
step bottom_cfg bottom_cfg --layers F.Cu In2.Cu B.Cu --layer-costs 3 8 1;   lock bottom_cfg
# band
step xlat_out xlat_out --layers F.Cu --ordering original;        lock xlat_out
step xlat_in xlat_in --layers F.Cu --ordering original;          lock xlat_in
step j1_west j1_west --layers F.Cu --ordering original;          lock j1_west
step j1_east j1_east --layer-costs 4 1 --via-cost 60 --ordering original;  lock j1_east
step xlat_oe xlat_oe "${BOT[@]}";                                lock xlat_oe
# rest
step hyperram hyperram --layers F.Cu --ordering original        # (reports the two bottom pull-ups as open)
step hr_pullups hr_pullups "${BOT[@]}";                          lock hyperram
# LEDs: around U9 and along the top edge on F.Cu, the inner one first (ball order = resistor order)
step leds leds --layers F.Cu --ordering original
step leds_l3 leds --layer-costs 3 1 --via-cost 50 --ordering original --keepout;   lock leds   # the rest: two vias each
step flash flash --layer-costs 1 4;                              lock flash
# JTAG crosses the whole board from the BGA's north-west corner to J2: on L3 its four tracks fenced VCCIO vias off
# the +1V8 pour, so it goes down at the escapes and runs on B.Cu to the header pins and their pull-ups
step jtag jtag --layers F.Cu In2.Cu B.Cu --layer-costs 2 10 1 --via-cost 100;   lock jtag
step adc adc "${BOT[@]}";                                        lock adc
step config config --layers F.Cu In2.Cu B.Cu --layer-costs 1 5 1.5;  lock config
# the power-good lines join bottom-side parts across the board: on B.Cu, not through the L3 pour under the BGA
step power_ctl power_ctl,adc_analog --layers F.Cu In2.Cu B.Cu --layer-costs 2 8 1
# whatever a step left open, with B.Cu allowed as the last resort
step leftovers leds,led_k,jtag,config,bottom_cfg,adc,flash,j1_east,hyperram --layers F.Cu In2.Cu B.Cu --layer-costs 1 10 2
# pour, then the supply stubs (with the pour dropped the router would join the +1V8 pads by tracks)
N=$((N + 1)); P="$W/$(printf %02d "$N")_pour.kicad_pcb"
(cd "$K" && $KP py_router/route_planes.py "$CUR" "$P" --nets +1V8 --plane-layers In2.Cu \
    --zone-clearance 0.15 --min-thickness 0.15 --no-thermal-vias --clearance 0.125 --fab-tier advanced \
    --escalation off --no-fix-drc-settings > "${P%.kicad_pcb}.log" 2>&1) || { tail -20 "${P%.kicad_pcb}.log"; exit 1; }
CUR="$P"; sib "$CUR"
if [ "$LAST" = "pour" ]; then kpy "$R/tools/phase5_lock_tracks.py" "$CUR" unlock | tail -1; cp "$CUR" "$OUT"; echo "stopped after pour: wrote $OUT"; exit 0; fi
step supply supply "${BOT[@]}" --power-nets '+0V95' '+1V8' '+3V3' '+5V' '+3V3A' '*VCCA*' '+1V8_OSC' \
    --power-nets-widths 0.3 0.3 0.3 0.3 0.25 0.2 0.2
kpy "$R/tools/phase5_lock_tracks.py" "$CUR" unlock | tail -1
cp "$CUR" "$OUT"
echo "wrote $OUT"
