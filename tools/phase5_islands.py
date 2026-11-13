"""Islands of the L3 +1V8 pour on a board with filled zones: for every island but the largest, its area, box,
the +1V8 vias and pads it holds, and the nets whose In2.Cu tracks fence it in.

    $KICAD_MOUNT/bin/python3.11 -I tools/phase5_islands.py BOARD.kicad_pcb [LAYER NET]
"""
import collections
import sys

import pcbnew

MM, IU = pcbnew.ToMM, pcbnew.FromMM
b = pcbnew.LoadBoard(sys.argv[1])
lname, net = (sys.argv[2:4] + ["In2.Cu", "+1V8"])[:2] if len(sys.argv) > 3 else ("In2.Cu", "+1V8")
lay = b.GetLayerID(lname)
for z in b.Zones():
    if z.GetIsRuleArea() or not z.IsOnLayer(lay) or z.GetNetname() != net:
        continue
    f = z.GetFilledPolysList(lay)
    isl = sorted(range(f.OutlineCount()), key=lambda i: -f.Outline(i).Area())
    pts = [(t.GetPosition(), "via") for t in b.GetTracks() if t.Type() == pcbnew.PCB_VIA_T and t.GetNetname() == net]
    pts += [(p.GetPosition(), f"{fp.GetReference()}.{p.GetNumber()}") for fp in b.GetFootprints() for p in fp.Pads()
            if p.GetNetname() == net and p.HasHole()]
    for i in isl[1:]:
        o = f.Outline(i)
        bb = o.BBox()
        inside = [(MM(q.x), MM(q.y), what) for q, what in pts if o.PointInside(q)]
        fence = collections.Counter()
        for t in b.GetTracks():
            if t.Type() != pcbnew.PCB_VIA_T and t.GetLayer() == lay and t.GetNetname() != net:
                m = pcbnew.VECTOR2I((t.GetStart().x + t.GetEnd().x) // 2, (t.GetStart().y + t.GetEnd().y) // 2)
                if o.Distance(m) < IU(0.35) or o.Distance(t.GetStart()) < IU(0.35):
                    fence[t.GetNetname()] += 1
        print(f"island {o.Area() / 1e12:.2f} mm2 box ({MM(bb.GetX()):.1f},{MM(bb.GetY()):.1f})-({MM(bb.GetRight()):.1f},"
              f"{MM(bb.GetBottom()):.1f}): {len(inside)} {net} vias/pads {[(round(x, 2), round(y, 2)) for x, y, _ in inside][:6]}")
        print("    fenced by:", ", ".join(f"{n} ({c})" for n, c in fence.most_common(8)))
