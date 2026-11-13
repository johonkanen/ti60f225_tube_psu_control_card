"""Phase 5 routing: lock (or unlock) the tracks and vias of finished nets between router steps.

    $KICAD_MOUNT/bin/python3.11 -I tools/phase5_lock_tracks.py BOARD.kicad_pcb lock GROUP[,GROUP...]
    $KICAD_MOUNT/bin/python3.11 -I tools/phase5_lock_tracks.py BOARD.kicad_pcb lock-all | unlock

KiCadRoutingTools never rips KiCad-locked copper. Without the lock a later step that cannot finish one of its own
nets may still rip a finished net of an earlier step (its reconciliation pass) and bring it back with vias.
GROUP: a key of tools/phase5/route_groups.json (exact net names only). unlock clears every track lock.
"""
import json
import os
import sys

import pcbnew


def main():
    path, mode = sys.argv[1:3]
    b = pcbnew.LoadBoard(path)
    if mode == "unlock":
        n = 0
        for t in b.GetTracks():
            n += t.IsLocked()
            t.SetLocked(False)
        for d in list(b.GetDrawings()):         # the router's keep-out box (tools/phase5_strip.py)
            if d.GetLayer() == pcbnew.User_2:
                b.Delete(d)
    elif mode == "lock-all":
        n = 0
        for t in b.GetTracks():
            t.SetLocked(True)
            n += 1
    else:
        table = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "phase5", "route_groups.json")))
        nets = {x for g in sys.argv[3].split(",") for x in table[g]}
        n = 0
        for t in b.GetTracks():
            if t.GetNetname() in nets:
                t.SetLocked(True)
                n += 1
    b.Save(path)
    print(f"phase5_lock_tracks: {n} tracks and vias: {mode}")


main()
