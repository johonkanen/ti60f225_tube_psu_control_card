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
NOTCH_W, NOTCH_KEEP, NOTCH_MAX, NOTCH_PAST = 0.9, 0.5, 8.0, 0.6
NOTCH_TRIES = ((NOTCH_W, NOTCH_KEEP), (1.5, NOTCH_KEEP), (NOTCH_W, 0.05), (1.5, 0.05))   # width, keep from +0V95
NOTCH_BACK = 0.25                   # the channel starts this far behind the via (its pad is 0.15 in radius)
BAY_KEEP = 0.6                      # the north bay's edges keep this far from the nearest +0V95 via


def drop(b, layer=L4):
    lay = b.GetLayerID(layer)
    n = 0
    for z in list(b.Zones()):
        if z.IsOnLayer(lay) and not z.GetIsRuleArea():
            b.Remove(z)
            n += 1
    print(f"phase5_planes: {n} old zones removed from {layer}")


def rect(a, c, w, back):
    """Polygon of a w-wide band from `back` behind point a to point c (VECTOR2I)."""
    dx, dy = c.x - a.x, c.y - a.y
    d = math.hypot(dx, dy)
    nx, ny = -dy / d * w / 2, dx / d * w / 2
    ex, ey = dx / d * back, dy / d * back
    s = pcbnew.SHAPE_POLY_SET()
    s.NewOutline()
    for px, py in ((a.x - ex + nx, a.y - ey + ny), (c.x + nx, c.y + ny),
                   (c.x - nx, c.y - ny), (a.x - ex - nx, a.y - ey - ny)):
        s.Append(int(px), int(py))
    return s


def largest(f):
    """The largest island of a fill, with its holes (a point in a hole is not on it)."""
    k = max(range(f.OutlineCount()), key=lambda i: abs(f.Outline(i).Area()))
    s = pcbnew.SHAPE_POLY_SET()
    s.AddOutline(f.Outline(k))
    for h in range(f.HoleCount(k)):
        s.AddHole(f.Hole(k, h))
    return s


def main_fill(b, lay, core):
    """The largest island of the +3V3 fill on L4 (refilled now), and how many of the +0V95 vias `core` are off
    the largest +0V95 island."""
    zones = b.Zones()                      # held: Fill on a temporary zone list crashes KiCad 10's Python
    pcbnew.ZONE_FILLER(b).Fill(zones)
    fill = lambda net: [x for x in zones if x.IsOnLayer(lay) and x.GetNetname() == net][0].GetFilledPolysList(lay)
    island = largest(fill("+0V95"))
    return largest(fill("+3V3")), sum(not island.Contains(p) for p in core)


def north_bay(b, z):
    """route_planes draws the +0V95 island as the box of all +0V95 vias plus a margin. Its north edge follows the
    buck's output caps east of the BGA, so north of the BGA's own +0V95 balls it covers ball rows that hold no
    +0V95 via at all, the +3V3 ball P4 (VCCIO33_BL) among them; the straight notch that joined P4 to the +3V3
    plane ran through the place where the router puts the vias of the north-edge escapes, and was cut by them.
    That bay is given back to +3V3: everything north of the northernmost +0V95 via under and around the BGA
    (less BAY_KEEP), from the island's west edge to BAY_KEEP short of the eastern +0V95 vias that reach so far
    north."""
    u1 = b.FindFootprintByReference("U1")
    x_split = max(p.GetPosition().x for p in u1.Pads()) + IU(1.0)
    core = [v.GetPosition() for v in b.GetTracks() if v.Type() == pcbnew.PCB_VIA_T and v.GetNetname() == "+0V95"]
    core += [p.GetPosition() for f in b.GetFootprints() for p in f.Pads() if p.GetNetname() == "+0V95" and p.HasHole()]
    west = [p for p in core if p.x < x_split]
    if not west:
        return
    y_cut = min(p.y for p in west) - IU(BAY_KEEP)
    east = [p.x for p in core if p.x >= x_split and p.y < y_cut + IU(BAY_KEEP)]
    bb = z.Outline().BBox()
    x_cut = (min(east) - IU(BAY_KEEP)) if east else bb.GetRight() + IU(1)
    if y_cut <= bb.GetY() or x_cut <= bb.GetX():
        return
    s = pcbnew.SHAPE_POLY_SET()
    s.NewOutline()
    for px, py in ((bb.GetX() - IU(1), bb.GetY() - IU(1)), (x_cut, bb.GetY() - IU(1)), (x_cut, y_cut),
                   (bb.GetX() - IU(1), y_cut)):
        s.Append(int(px), int(py))
    z.Outline().BooleanSubtract(s)
    print(f"phase5_planes: north bay of the +0V95 island given to +3V3: north of y {MM(y_cut):.2f}, west of x {MM(x_cut):.2f}")


def notch(b):
    lay = b.GetLayerID(L4)
    island = [z for z in b.Zones() if z.IsOnLayer(lay) and z.GetNetname() == "+0V95"]
    if len(island) != 1:
        sys.exit(f"expected one +0V95 zone on {L4}, found {len(island)}")
    z = island[0]
    north_bay(b, z)
    vias = [v for v in b.GetTracks() if v.Type() == pcbnew.PCB_VIA_T]
    core = [v.GetPosition() for v in vias if v.GetNetname() == "+0V95"]
    core += [p.GetPosition() for f in b.GetFootprints() for p in f.Pads()
             if p.GetNetname() == "+0V95" and p.HasHole()]
    cut = 0
    n_core0 = main_fill(b, lay, core)[1]
    for v in vias:
        a = v.GetPosition()
        if v.GetNetname() != "+3V3" or main_fill(b, lay, core)[0].Contains(a):
            continue
        # candidate channels: 8 directions, from the via to NOTCH_PAST beyond the island's edge, clear of +0V95;
        # NOTCH_W first, then wider (another net's via in a narrow channel leaves only slivers beside its antipad),
        # then closer to the +0V95 vias (the refill check below rejects one that cuts a +0V95 via off)
        cands = []
        for n_try, (w, keep_d) in enumerate(NOTCH_TRIES):
            for k in range(8):
                ang = k * math.pi / 4
                for step in range(1, int(NOTCH_MAX / 0.1)):
                    c = pcbnew.VECTOR2I(int(a.x + math.cos(ang) * IU(step * 0.1)), int(a.y + math.sin(ang) * IU(step * 0.1)))
                    if not z.Outline().Contains(c):
                        break
                else:
                    continue
                c = pcbnew.VECTOR2I(int(c.x + math.cos(ang) * IU(NOTCH_PAST)), int(c.y + math.sin(ang) * IU(NOTCH_PAST)))
                if not any(rect(a, c, IU(w + 2 * keep_d), IU(NOTCH_BACK + keep_d)).Contains(p) for p in core):
                    cands.append((n_try, step, c, w))
        # narrowest, then shortest first; keep the first one after which the via really sits in the main +3V3 fill
        # (an antipad or a pocket of the island can still cut the channel off), else undo it
        for _, step, c, w in sorted(cands, key=lambda s: s[:2]):
            keep = pcbnew.SHAPE_POLY_SET(z.Outline())
            z.Outline().BooleanSubtract(rect(a, c, IU(w), IU(NOTCH_BACK)))
            fill, n_core = main_fill(b, lay, core)
            if fill.Contains(a) and n_core <= n_core0:      # and no +0V95 via is cut off
                cut += 1
                print(f"  notch for the +3V3 via at ({MM(a.x):.2f}, {MM(a.y):.2f}), {step * 0.1:.1f} mm long, {w} mm wide")
                break
            z.Outline().RemoveAllContours()
            z.Outline().Append(keep)
        else:
            print(f"  NO NOTCH for the +3V3 via at ({MM(a.x):.2f}, {MM(a.y):.2f})")
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
