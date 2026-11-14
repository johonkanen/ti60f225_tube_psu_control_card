"""The user's hand fixes of 7962419 / f023e90, as a rerunnable step after routing.

    $KICAD_MOUNT/bin/python3.11 -I tools/phase5_5v.py IN.kicad_pcb OUT.kicad_pcb

1. C15 (+5V input cap) moves from its Agilex place to J1 pin 1: bottom, 180 deg, pad 1 on the +5V trunk.
2. +5V from J1 pin 1 to the ADC reference regulator U6 runs as one 0.8 mm track on B.Cu (the router's 0.3 mm
   route and its two vias between U6 and the east supplies are removed first). U2/U4 stay fed by the L3 trunk.
Run before tools/phase5_fab.py; DRC in phase5_check.sh shows whether the trunk clears.
"""
import sys

import pcbnew

IU, MM = pcbnew.FromMM, pcbnew.ToMM
C15_AT, C15_ROT = (105.725, 124.225), 180.0
TRUNK_W = 0.8
TRUNK = [(106.62, 126.25), (106.62, 121.27), (105.48, 120.12), (103.1, 120.12), (102.78, 119.8),
         (91.65, 119.8), (88.97, 122.48), (85.8, 122.48)]
GND_VIA = (105.53, 124.28)            # 0.45/0.25, C15's ground
RIP = (86.3, 117.9, 105.5, 124.1)     # router +5V copper wholly inside this box (U6 east to U4/C8) is replaced


def inside(p):
    x, y = MM(p.x), MM(p.y)
    return RIP[0] <= x <= RIP[2] and RIP[1] <= y <= RIP[3]


def main(src, dst):
    b = pcbnew.LoadBoard(src)
    net = b.FindNet("+5V")
    gone = 0
    for t in list(b.GetTracks()):
        if t.GetNetCode() != net.GetNetCode():
            continue
        ends = [t.GetPosition()] if t.Type() == pcbnew.PCB_VIA_T else [t.GetStart(), t.GetEnd()]
        if all(inside(p) for p in ends):
            b.Delete(t)
            gone += 1
    c15 = b.FindFootprintByReference("C15")
    c15.SetPosition(pcbnew.VECTOR2I(IU(C15_AT[0]), IU(C15_AT[1])))
    c15.SetOrientationDegrees(C15_ROT)
    def seg(n, pts, w):
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            s = pcbnew.PCB_TRACK(b)
            s.SetStart(pcbnew.VECTOR2I(IU(x0), IU(y0)))
            s.SetEnd(pcbnew.VECTOR2I(IU(x1), IU(y1)))
            s.SetWidth(IU(w))
            s.SetLayer(pcbnew.B_Cu)
            s.SetNet(n)
            b.Add(s)
    seg(net, TRUNK, TRUNK_W)
    gnd = b.FindNet("GND")             # C15 pad 2: stub west of the cap to a GND via, as on the hand-fixed board
    seg(gnd, [(104.78, 124.22), (105.47, 124.22), (105.53, 124.28)], 0.3)
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(pcbnew.VECTOR2I(IU(GND_VIA[0]), IU(GND_VIA[1])))
    v.SetWidth(IU(0.45))
    v.SetDrill(IU(0.25))
    v.SetNet(gnd)
    b.Add(v)
    b.Save(dst)
    print(f"phase5_5v: {gone} router +5V items removed, C15 at J1 pin 1, {len(TRUNK) - 1} trunk segments at {TRUNK_W} mm")


if __name__ == "__main__":
    main(*sys.argv[1:3])
