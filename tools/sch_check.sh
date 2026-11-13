#!/usr/bin/env bash
# Schematic checks after a pin swap: ERC (0 violations wanted) and tools/check_schematic.py on a fresh netlist.
#   tools/sch_check.sh
set -euo pipefail
R="$(cd "$(dirname "$0")/.." && pwd)"
E="${KICAD_ENV:-$HOME/dev/proteus2kicad/bin/kicad_env.sh}"
W="$R/build/sch_check"; mkdir -p "$W"
"$E" kicad-cli sch erc --severity-all --format json -o "$W/erc.json" "$R/hardware/control_card.kicad_sch" > /dev/null || true
python3 -I -c "
import json, sys
d = json.load(open(sys.argv[1]))
v = [x for s in d.get('sheets', []) for x in s.get('violations', [])]
print('ERC violations:', len(v))
for x in v[:10]:
    print('  ', x['severity'], x['description'], '|', '; '.join(i['description'] for i in x['items'])[:150])
" "$W/erc.json"
"$E" kicad-cli sch export netlist --format kicadsexpr -o "$W/check.net" "$R/hardware/control_card.kicad_sch" > /dev/null
python3 -I "$R/tools/check_schematic.py" "$W/check.net" | tail -4
