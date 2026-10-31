"""Phase 5: L4 (In3.Cu) split between the +0V95 island and +3V3, after KiCadRoutingTools' route_planes.

    $KICAD_MOUNT/bin/python3.11 -I tools/phase5_planes.py drop IN.kicad_pcb OUT.kicad_pcb [LAYER]
    (KRT) route_planes.py OUT --nets +0V95 +3V3 --plane-layers In3.Cu In3.Cu ...
    $KICAD_MOUNT/bin/python3.11 -I tools/phase5_planes.py notch IN.kicad_pcb OUT.kicad_pcb

drop:  deletes the old zones of a layer: L4 (default; the Agilex card's +0V75 island and the full-board +3V3),
       or L3 (In2.Cu, the +1V8 pour) before routing, since KiCadRoutingTools routes no track through a pour
       of another net; the +1V8 pour is made again around the routed tracks.
notch: route_planes splits L4 by Voronoi regions of each net's vias; a +3V3 via that ends up inside the +0V95
       island (the HVIO corner balls P4/B4/B13, which sit among the core balls, and vias at the island's
       edge) would have no +3V3 plane. For each one a NOTCH_W wide channel is cut from the via to the island's
       edge, in the shortest of 8 directions that keeps NOTCH_KEEP from every +0V95 via, and the +3V3 pour
       flows in. The island keeps the higher zone priority.
"""
import math
import sys

import pcbnew

IU, MM = pcbnew.FromMM, pcbnew.ToMM
L4 = "In3.Cu"
NOTCH_W, NOTCH_KEEP, NOTCH_MAX = 0.9, 0.5, 8.0


def drop(b, layer=L4):
    lay = b.GetLayerID(layer)
    n = 0
    for z in list(b.Zones()):
        if z.IsOnLayer(lay) and not z.GetIsRuleArea():
            b.Remove(z)
            n += 1
    print(f"phase5_planes: {n} old zones removed from {layer}")


def rect(a, c, w):
    """Polygon of a w-wide band from point a to point c (VECTOR2I), square ends."""
    dx, dy = c.x - a.x, c.y - a.y
    d = math.hypot(dx, dy)
    nx, ny = -dy / d * w / 2, dx / d * w / 2
    ex, ey = dx / d * w / 2, dy / d * w / 2
    s = pcbnew.SHAPE_POLY_SET()
    s.NewOutline()
    for px, py in ((a.x - ex + nx, a.y - ey + ny), (c.x + ex + nx, c.y + ey + ny),
                   (c.x + ex - nx, c.y + ey - ny), (a.x - ex - nx, a.y - ey - ny)):
        s.Append(int(px), int(py))
    return s


def notch(b):
    lay = b.GetLayerID(L4)
    island = [z for z in b.Zones() if z.IsOnLayer(lay) and z.GetNetname() == "+0V95"]
    if len(island) != 1:
        sys.exit(f"expected one +0V95 zone on {L4}, found {len(island)}")
    z = island[0]
    vias = [v for v in b.GetTracks() if v.Type() == pcbnew.PCB_VIA_T]
    core = [v.GetPosition() for v in vias if v.GetNetname() == "+0V95"]
    core += [p.GetPosition() for f in b.GetFootprints() for p in f.Pads()
             if p.GetNetname() == "+0V95" and p.HasHole()]
    cut = 0
    for v in vias:
        if v.GetNetname() != "+3V3" or not z.Outline().Contains(v.GetPosition()):
            continue
        a = v.GetPosition()
        best = None
        for k in range(8):
            ang = k * math.pi / 4
            for step in range(1, int(NOTCH_MAX / 0.1)):
                c = pcbnew.VECTOR2I(int(a.x + math.cos(ang) * IU(step * 0.1)), int(a.y + math.sin(ang) * IU(step * 0.1)))
                if not z.Outline().Contains(c):
                    break
            else:
                continue
            band = rect(a, c, IU(NOTCH_W + 2 * NOTCH_KEEP))
            if any(band.Contains(p) for p in core):
                continue
            if best is None or step < best[0]:
                best = (step, c)
        if best is None:
            print(f"  no notch for the +3V3 via at ({MM(a.x):.2f}, {MM(a.y):.2f})")
            continue
        o = z.Outline()
        o.BooleanSubtract(rect(a, best[1], IU(NOTCH_W)))
        cut += 1
        print(f"  notch for the +3V3 via at ({MM(a.x):.2f}, {MM(a.y):.2f}), {best[0] * 0.1:.1f} mm")
    print(f"phase5_planes: {cut} notches in the L4 +0V95 island")


def main():
    mode, src, dst = sys.argv[1:4]
    b = pcbnew.LoadBoard(src)
    if mode == "drop":
        drop(b, *sys.argv[4:5])
    else:
        notch(b)
    b.Save(dst)


if __name__ == "__main__":
    main()
