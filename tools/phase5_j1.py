"""Phase 5 routing: escape stubs for J1's second row (even pins), before the router runs.

    $KICAD_MOUNT/bin/python3.11 -I tools/phase5_j1.py IN.kicad_pcb OUT.kicad_pcb [stubs|pulldowns]

J1 is a 2 x 25, 1.27 mm header with 0.9 mm pads: a 0.1 mm track fits between two first-row pads only exactly
centred (0.135 mm to each pad, 0.306 mm to each hole against JLC's 0.28), which KiCadRoutingTools does not find
on its grid. So every second-row pin in use gets a stub from its pad through the first-row gap on its west side,
ending north of the first row at STUB_Y, where the router picks it up:

    pad (x, 127.52) -> 45 deg -> (x - 0.635, 126.885) -> north -> (x - 0.635, STUB_Y)

F.Cu for the nets that arrive on top (translator outputs, the south-west HVIO nets), In2.Cu for the direct nets that
arrive on L3. PFC_PWM2 (pin 34, far west of its translator) instead runs south of the second row and comes up
through both rows between pins 21/23 and 22/24, so it crosses none of the HVIO nets that drop onto pins 23-33.
The EPWM2A/EPWM2B pull-downs R40/R41 sit on the bottom just north of pins 9 and 11: a B.Cu stub joins each to its
(through-hole) pin, so they need no via.
"""
import sys

import pcbnew

IU, MM = pcbnew.FromMM, pcbnew.ToMM
W = 0.1
PITCH = 1.27
STUB_Y = 125.45
F_PINS = (4, 6, 8, 10, 14, 16, 18, 20, 28, 30, 32)      # second-row pins reached on F.Cu
L3_PINS = (12, 22, 24, 26)                               # second-row pins reached on In2.Cu
POCKET = ()                                                      # east-edge escapes, north to south
BALL = ("J1_P26",)                                               # via in the ball pad
PULLDOWNS = (("R40", 9), ("R41", 11))                    # placed above their pins by tools/phase5_decaps.py
LOOP_PIN, LOOP_GAP_PINS, LOOP_Y = 34, (22, 24), 128.22   # PFC_PWM2: south of row 2, up between pins 22 and 24


def seg(b, net, layer, a, c):
    t = pcbnew.PCB_TRACK(b)
    t.SetStart(pcbnew.VECTOR2I(IU(a[0]), IU(a[1])))
    t.SetEnd(pcbnew.VECTOR2I(IU(c[0]), IU(c[1])))
    t.SetWidth(IU(W))
    t.SetLayer(layer)
    t.SetNet(net)
    b.Add(t)


def path(b, net, layer, pts):
    for a, c in zip(pts, pts[1:]):
        seg(b, net, layer, a, c)


def add_via(b, net, pos):
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(pcbnew.VECTOR2I(IU(pos[0]), IU(pos[1])))
    v.SetWidth(pcbnew.F_Cu, IU(0.30))
    v.SetDrill(IU(0.15))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetNet(net)
    b.Add(v)


def direct(b):
    """Vias for the direct HVIO nets that go to J1 on L3 (the router then runs them on In2.Cu only).

    POCKET: the five TR-bank nets that leave the BGA's east edge south of the translator inputs. Their escapes are
    enclosed by the translator input fans, so each drops to L3 right there: a staircase of vias, the northern
    escape reaching furthest east, 0.45 mm apart in x and each 0.1 mm below its own track, so the L3 tracks leave
    southwards in the order of their J1 pins and no F.Cu track passes a via closer than 0.2 mm.
    BALL: nets taken down in the ball pad (no F.Cu escape; left out of the fan-out by tools/phase5_layout.sh)."""
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from phase5_taps import legal, obstacles
    cu, holes = obstacles(b)
    u1 = b.FindFootprintByReference("U1")
    ball = {p.GetNetname(): p for p in u1.Pads()}
    if POCKET:
        ends = []
        for name in POCKET:
            pts = [q for t in b.GetTracks() if t.Type() != pcbnew.PCB_VIA_T and t.GetNetname() == name
                   and t.GetLayer() == pcbnew.F_Cu for q in (t.GetStart(), t.GetEnd())]
            e = max(pts, key=lambda q: q.x)
            ends.append((MM(e.x), MM(e.y)))
        if [e[1] for e in ends] != sorted(e[1] for e in ends) or min(e[0] for e in ends) < 96.8:
            sys.exit(f"phase5_j1: pocket escapes not in J1 order on the east edge: {list(zip(POCKET, ends))}")
        for shift in range(0, 30):
            x0 = max(e[0] for e in ends) + 0.4 + 0.45 * (len(POCKET) - 1) + 0.05 * shift
            vias = [(round(x0 - 0.45 * k, 3), round(e[1] + 0.1, 3)) for k, e in enumerate(ends)]
            if all(legal(pcbnew.VECTOR2I(IU(v[0]), IU(v[1])), ball[n].GetNetCode(), cu, holes)
                   for n, v in zip(POCKET, vias)):
                break
        else:
            sys.exit("phase5_j1: no legal via staircase in the pocket")
        for name, e, v in zip(POCKET, ends, vias):
            path(b, ball[name].GetNet(), pcbnew.F_Cu, [e, (v[0] - 0.1, e[1]), v])
            add_via(b, ball[name].GetNet(), v)
    for name in BALL:
        c = ball[name].GetPosition()
        if not legal(c, ball[name].GetNetCode(), cu, holes):
            sys.exit(f"phase5_j1: no via fits in ball {ball[name].GetNumber()} ({name})")
        add_via(b, ball[name].GetNet(), (MM(c.x), MM(c.y)))
    print(f"phase5_j1: {len(POCKET)} pocket vias, {len(BALL)} vias in ball pads")


def main(src, dst, mode="stubs"):
    b = pcbnew.LoadBoard(src)
    j1 = b.FindFootprintByReference("J1")
    pad = {int(p.GetNumber()): p for p in j1.Pads()}
    xy = {n: (MM(p.GetPosition().x), MM(p.GetPosition().y)) for n, p in pad.items()}
    half = PITCH / 2
    n = 0
    if mode == "pulldowns":                     # after the translator outputs are routed (else the router ends
        for ref, k in PULLDOWNS:                # a track on the stub with a via instead of on the pin)
            f = b.FindFootprintByReference(ref)
            p = next(p for p in f.Pads() if p.GetNumber() and p.GetNetCode() == pad[k].GetNetCode())
            px, py = MM(p.GetPosition().x), MM(p.GetPosition().y)
            x, y = xy[k]
            pts = [(px, py)] + ([(x, py + abs(x - px))] if abs(x - px) > 0.01 else []) + [(x, y)]
            path(b, pad[k].GetNet(), pcbnew.B_Cu, pts)
        b.Save(dst)
        print(f"phase5_j1: {len(PULLDOWNS)} pull-down stubs on B.Cu")
        return
    for pins, layer in ((F_PINS, pcbnew.F_Cu), (L3_PINS, b.GetLayerID("In2.Cu"))):
        for k in pins:
            x, y = xy[k]
            if pad[k].GetNetname().startswith("unconnected") or not pad[k].GetNetname():
                sys.exit(f"J1.{k} carries no net")
            path(b, pad[k].GetNet(), layer, [(x, y), (x - half, y - half), (x - half, STUB_Y)])
            n += 1
    x, y = xy[LOOP_PIN]
    gx = (xy[LOOP_GAP_PINS[0]][0] + xy[LOOP_GAP_PINS[1]][0]) / 2
    c = 0.2
    path(b, pad[LOOP_PIN].GetNet(), pcbnew.F_Cu,
         [(x, y), (x, LOOP_Y - c), (x + c, LOOP_Y), (gx - c, LOOP_Y), (gx, LOOP_Y - c), (gx, STUB_Y)])
    direct(b)
    b.Save(dst)
    print(f"phase5_j1: {n} second-row stubs, {pad[LOOP_PIN].GetNetname()} looped south of row 2")


if __name__ == "__main__":
    main(*sys.argv[1:4])
