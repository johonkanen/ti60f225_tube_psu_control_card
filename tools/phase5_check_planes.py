"""Plane audit of a board whose zones are filled: islands per plane zone, vias and through pads of a plane net
that miss its fill, tracks on the plane layers."""
import collections
import sys

import pcbnew

MM = pcbnew.ToMM
PLANES = {"In1.Cu": ("GND",), "In2.Cu": ("+1V8",), "In3.Cu": ("+0V95", "+3V3"), "In4.Cu": ("GND",)}

b = pcbnew.LoadBoard(sys.argv[1])
bad = 0
for lname, nets in PLANES.items():
    lay = b.GetLayerID(lname)
    fills = {}
    for z in b.Zones():
        if z.GetIsRuleArea() or not z.IsOnLayer(lay) or z.GetNetname() not in nets:
            continue
        f = z.GetFilledPolysList(lay)
        areas = sorted((round(f.Outline(i).Area() / 1e12, 2) for i in range(f.OutlineCount())), reverse=True)
        fills.setdefault(z.GetNetname(), []).append(f)
        print(f"{lname} {z.GetNetname()}: {f.OutlineCount()} island(s), mm2 {areas[:6]}")
        bad += f.OutlineCount() != 1
    miss = collections.defaultdict(list)
    items = [(t.GetNetname(), t.GetPosition()) for t in b.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
    items += [(p.GetNetname(), p.GetPosition()) for fp in b.GetFootprints() for p in fp.Pads() if p.HasHole()]
    for net, pos in items:
        if net in fills and not any(f.Contains(pos) for f in fills[net]):
            miss[net].append(f"({MM(pos.x):.2f},{MM(pos.y):.2f})")
    for net, pts in miss.items():
        print(f"  {lname} {net}: {len(pts)} via/pad outside the fill: {' '.join(pts[:12])}")
        bad += len(pts)
    if lname != "In2.Cu":
        n = sum(1 for t in b.GetTracks() if t.Type() != pcbnew.PCB_VIA_T and t.GetLayer() == lay)
        print(f"  {lname}: {n} tracks")
        bad += n
print("plane audit:", "OK" if not bad else f"{bad} to review")
