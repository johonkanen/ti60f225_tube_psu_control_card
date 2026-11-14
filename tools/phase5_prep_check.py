"""Phase 5 routing: gate after the scripted prep copper (tools/phase5_j1.py, tools/phase5_mem.py).

    python3 -I tools/phase5_prep_check.py DRC.json

Reads a KiCad DRC report of the prepared board (zones not refilled) and fails when a track or via is shorted to,
crosses or comes too close to another net's track, via or pad. Zone items are left out: the planes are refilled
later around the new vias.
"""
import json
import sys

KINDS = ("shorting_items", "clearance", "tracks_crossing", "hole_clearance", "hole_to_hole")
rep = json.load(open(sys.argv[1]))
bad = []
for v in rep.get("violations", []):
    d = [i["description"] for i in v["items"]]
    if v["type"] in KINDS and not any(x.startswith("Zone") for x in d):
        p = v["items"][0]["pos"]
        bad.append(f"  {v['type']}: {' | '.join(d)[:170]} @({p['x']:.2f}, {p['y']:.2f})")
print(f"phase5_prep_check: {len(bad)} conflicts in the scripted copper")
print("\n".join(bad[:30]))
sys.exit(1 if bad else 0)
