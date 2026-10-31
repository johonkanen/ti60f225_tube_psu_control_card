"""Lock every footprint inside the board outline (the placed ones), unlock the rest: KiCadRoutingTools' placer
then moves only the parts still parked off the board.

    $KICAD_MOUNT/bin/python3.11 -I tools/phase5_lock.py IN.kicad_pcb OUT.kicad_pcb [--unlock]

--unlock unlocks every footprint (the chain's last step, so the finished board edits normally in KiCad).
"""
import sys

import pcbnew

b = pcbnew.LoadBoard(sys.argv[1])
edge = b.GetBoardEdgesBoundingBox()
n = 0
for f in b.GetFootprints():
    inside = edge.Contains(f.GetPosition()) and "--unlock" not in sys.argv
    f.SetLocked(inside)
    n += inside
b.Save(sys.argv[2])
print(f"phase5_lock: {n} footprints locked" if "--unlock" not in sys.argv else "phase5_lock: all footprints unlocked")
