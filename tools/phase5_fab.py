"""Manufacturing fixes on the routed board (docs/manufacturing_checklist.md), rerunnable.

    $KICAD_MOUNT/bin/python3.11 -I tools/phase5_fab.py IN.kicad_pcb OUT.kicad_pcb

1. Vias: every via with a pad under VIA_D (0.30 mm) or a drill under VIA_DRILL is set to 0.30/0.15, the
   project's via (JLC's ring on a 0.15 mm drill); DRC afterwards shows whether it still clears.
2. Fiducials: FIDS_PER_SIDE KiCad Fiducial_1mm_Mask2mm (1 mm copper, 2 mm mask opening, 0.6 mm clearance) per
   side, as far apart as the free space allows. A spot is free when no pad, track or via on that side comes within
   the fiducial's clearance (pours flow around it), no courtyard on that side overlaps, and it is EDGE_KEEP from
   the board edge. Of the free spots nearest each corner, the three with the largest triangle are kept.
   They are board-only footprints (no schematic symbol), excluded from the BOM and the placement file, so
   schematic parity and the JLC BOM/CPL do not change. Existing FIDn footprints are replaced.
"""
import itertools
import math
import os
import sys

import pcbnew

IU, MM = pcbnew.FromMM, pcbnew.ToMM
VIA_D, VIA_DRILL = 0.30, 0.15
FID_LIB, FID_NAME = "Fiducial", "Fiducial_1mm_Mask2mm"
FID_R = 0.5 + 0.6 + 0.1            # copper radius + its clearance + the other item's clearance
EDGE_KEEP = 1.5                    # fiducial centre from the board edge (mask opening 1 mm radius + margin)
GRID = 0.25
FIDS_PER_SIDE = 3


def fix_vias(b):
    n = 0
    for v in b.GetTracks():
        if v.Type() != pcbnew.PCB_VIA_T:
            continue
        if v.GetWidth(pcbnew.F_Cu) < IU(VIA_D) - 1 or v.GetDrillValue() < IU(VIA_DRILL) - 1:
            p = v.GetPosition()
            print(f"  via {v.GetNetname()} at ({MM(p.x):.2f}, {MM(p.y):.2f}): "
                  f"{MM(v.GetWidth(pcbnew.F_Cu)):.2f}/{MM(v.GetDrillValue()):.2f} -> {VIA_D:.2f}/{VIA_DRILL:.2f}")
            v.SetWidth(IU(VIA_D))
            v.SetDrill(IU(max(MM(v.GetDrillValue()), VIA_DRILL)))
            n += 1
    print(f"phase5_fab: {n} vias enlarged")


def obstacles(b, layer):
    shapes = []
    for f in b.GetFootprints():
        if f.GetReference().startswith("FID"):
            continue
        for p in f.Pads():
            if p.IsOnLayer(layer):
                shapes.append(p.GetEffectiveShape(layer))
    for t in b.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T or t.GetLayer() == layer:
            shapes.append(t.GetEffectiveShape(layer))
    return shapes


def courtyards(b, back):
    out = []
    for f in b.GetFootprints():
        if f.IsFlipped() == back and not f.GetReference().startswith("FID"):
            c = f.GetCourtyard(pcbnew.B_CrtYd if back else pcbnew.F_CrtYd)
            out.append(c.BBox() if not c.IsEmpty() else f.GetBoundingBox(False))
    return out


def free_spots(b, back):
    layer = pcbnew.B_Cu if back else pcbnew.F_Cu
    shapes = obstacles(b, layer)
    courts = courtyards(b, back)
    e = b.GetBoardEdgesBoundingBox()
    x0, y0, x1, y1 = (MM(v) for v in (e.GetX(), e.GetY(), e.GetRight(), e.GetBottom()))
    spots = []
    y = y0 + EDGE_KEEP
    while y <= y1 - EDGE_KEEP:
        x = x0 + EDGE_KEEP
        while x <= x1 - EDGE_KEEP:
            c = pcbnew.VECTOR2I(IU(x), IU(y))
            circ = pcbnew.SHAPE_CIRCLE(c, IU(FID_R))
            box = pcbnew.BOX2I(pcbnew.VECTOR2I(IU(x - 1.25), IU(y - 1.25)), pcbnew.VECTOR2L(IU(2.5), IU(2.5)))
            if not any(cb.Intersects(box) for cb in courts) and not any(s.Collide(circ, 0) for s in shapes):
                spots.append((x, y))
            x += GRID
        y += GRID
    return spots, (x0, y0, x1, y1)


def pick(spots, edge):
    """The free spot nearest each board corner, then the three of those spanning the largest triangle."""
    x0, y0, x1, y1 = edge
    near = []
    for cx, cy in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
        if spots:
            near.append(min(spots, key=lambda s: math.hypot(s[0] - cx, s[1] - cy)))
    near = list(dict.fromkeys(near))
    if len(near) < FIDS_PER_SIDE:
        return near
    area = lambda a, b, c: abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) / 2
    return list(max(itertools.combinations(near, FIDS_PER_SIDE), key=lambda t: area(*t)))


def add_fiducials(b):
    for f in list(b.GetFootprints()):
        if f.GetReference().startswith("FID"):
            b.Delete(f)
    lib = os.path.join(os.environ.get("KICAD_MOUNT", ""), "share", "kicad", "footprints", f"{FID_LIB}.pretty")
    n = 0
    for back in (False, True):
        spots, edge = free_spots(b, back)
        chosen = pick(spots, edge)
        side = "bottom" if back else "top"
        if len(chosen) < FIDS_PER_SIDE:
            print(f"  only {len(chosen)} free fiducial spots on the {side}")
        for x, y in chosen:
            n += 1
            f = pcbnew.FootprintLoad(lib, FID_NAME)
            f.SetReference(f"FID{n}")
            f.SetValue("Fiducial")
            f.SetPosition(pcbnew.VECTOR2I(IU(x), IU(y)))
            b.Add(f)                    # before Flip: flipping a footprint with no board crashes KiCad 10
            if back:
                f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
            f.SetBoardOnly(True)
            f.SetExcludedFromBOM(True)
            f.SetExcludedFromPosFiles(True)
            f.Reference().SetVisible(False)
            f.Value().SetVisible(False)
            print(f"  FID{n} {side} at ({x:.2f}, {y:.2f})")
    print(f"phase5_fab: {n} fiducials")


def main(src, dst):
    b = pcbnew.LoadBoard(src)
    fix_vias(b)
    b.Save(dst)                 # KiCad 10's Python: save and reload between removing/adding steps
    b = pcbnew.LoadBoard(dst)
    add_fiducials(b)
    b.Save(dst)


if __name__ == "__main__":
    main(*sys.argv[1:3])
