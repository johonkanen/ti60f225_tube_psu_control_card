"""Fill every zone of a board and save it (KiCadRoutingTools reads a pour's connectivity from its fill; a zone
written by route_planes has none yet, and the router then joins the net's pads by tracks).

    $KICAD_MOUNT/bin/python3.11 -I tools/phase5_fill.py IN.kicad_pcb OUT.kicad_pcb
"""
import sys

import pcbnew

b = pcbnew.LoadBoard(sys.argv[1])
zones = b.Zones()                      # held: Fill on a temporary zone list crashes KiCad 10's Python
pcbnew.ZONE_FILLER(b).Fill(zones)
b.Save(sys.argv[2])
print(f"phase5_fill: {len(zones)} zones filled")
