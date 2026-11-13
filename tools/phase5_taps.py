"""Phase 5 routing: a via in the pad of bottom-side parts on nets that are routed on F.Cu / In2.Cu only.

    $KICAD_MOUNT/bin/python3.11 -I tools/phase5_taps.py IN.kicad_pcb OUT.kicad_pcb

The routing chain keeps B.Cu out of the signal steps, so a bottom-side SMD pad of such a net (the HR_RESET_N
and TEST_N pull-ups, the ADC B series resistors) has no way in.
Via-in-pad is free on this order (filled and capped), so each of these pads gets a 0.30/0.15 via at its centre,
or at the nearest point inside the pad that is legal on every layer; the router then ends on the via.
"""
import math
import sys

import pcbnew

IU, MM = pcbnew.FromMM, pcbnew.ToMM
VIA_D, VIA_DRILL, CLR, HOLE_CLR, HOLE_HOLE = 0.30, 0.15, 0.125, 0.2, 0.2
NETS = ("HR_RESET_N", "HR_DQ3", "ADCB_CS_N", "ADCB_SCLK", "ADCB_SDO")


def obstacles(b):
    cu, holes = [], []
    for t in b.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            holes.append((t.GetPosition(), t.GetDrillValue() / 2))
            cu += [(t.GetEffectiveShape(l), t.GetNetCode()) for l in b.GetEnabledLayers().CuStack()]
        else:
            cu.append((t.GetEffectiveShape(t.GetLayer()), t.GetNetCode()))
    for f in b.GetFootprints():
        for p in f.Pads():
            if p.HasHole():
                holes.append((p.GetPosition(), p.GetDrillSizeX() / 2))
            for l in p.GetLayerSet().CuStack():
                if b.IsLayerEnabled(l):
                    cu.append((p.GetEffectiveShape(l), p.GetNetCode()))
    for z in b.Zones():
        if not z.GetIsRuleArea() and (z.IsOnLayer(pcbnew.F_Cu) or z.IsOnLayer(pcbnew.B_Cu)):
            cu.append((z.Outline(), z.GetNetCode()))
    return cu, holes


def legal(pos, net, cu, holes):
    circ = pcbnew.SHAPE_CIRCLE(pos, IU(VIA_D / 2))
    hole = pcbnew.SHAPE_CIRCLE(pos, IU(VIA_DRILL / 2))
    for sh, n in cu:
        if n != net and (sh.Collide(circ, IU(CLR) - 1) or sh.Collide(hole, IU(HOLE_CLR) - 1)):
            return False
    return all(math.hypot(hp.x - pos.x, hp.y - pos.y) >= hr + IU(VIA_DRILL / 2 + HOLE_HOLE) for hp, hr in holes)


def main(src, dst):
    b = pcbnew.LoadBoard(src)
    cu, holes = obstacles(b)
    vias = [(t.GetPosition(), t.GetNetCode()) for t in b.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
    n = 0
    for f in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
        for p in f.Pads():
            if p.GetNetname() not in NETS or p.IsOnLayer(pcbnew.F_Cu) or not p.IsOnLayer(pcbnew.B_Cu):
                continue
            sh = p.GetEffectiveShape(pcbnew.B_Cu)
            if any(nc == p.GetNetCode() and sh.Collide(pcbnew.VECTOR2I(vp), 0) for vp, nc in vias):
                continue
            c = p.GetPosition()
            cand = sorted(((dx, dy) for dx in range(-12, 13) for dy in range(-12, 13)),
                          key=lambda d: d[0] ** 2 + d[1] ** 2)
            for dx, dy in cand:
                pos = pcbnew.VECTOR2I(c.x + IU(0.025) * dx, c.y + IU(0.025) * dy)
                if sh.Collide(pos, 0) and legal(pos, p.GetNetCode(), cu, holes):
                    v = pcbnew.PCB_VIA(b)
                    v.SetPosition(pos)
                    v.SetWidth(pcbnew.F_Cu, IU(VIA_D))
                    v.SetDrill(IU(VIA_DRILL))
                    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                    v.SetNet(p.GetNet())
                    b.Add(v)
                    holes.append((pos, IU(VIA_DRILL / 2)))
                    cu += [(v.GetEffectiveShape(l), v.GetNetCode()) for l in b.GetEnabledLayers().CuStack()]
                    vias.append((pos, p.GetNetCode()))
                    n += 1
                    print(f"  {f.GetReference()}.{p.GetNumber()} {p.GetNetname()}: via ({MM(pos.x):.3f}, {MM(pos.y):.3f})")
                    break
            else:
                print(f"  NO TAP for {f.GetReference()}.{p.GetNumber()} {p.GetNetname()}")
    b.Save(dst)
    print(f"phase5_taps: {n} vias in bottom pads")


if __name__ == "__main__":
    main(*sys.argv[1:3])
