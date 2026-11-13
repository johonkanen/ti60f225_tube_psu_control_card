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
Mode pulldowns: the EPWM2A/EPWM2B pull-downs R40/R41 sit on the bottom just north of J1 pins 9 and 11, the JTAG
pull-ups R60-R63 just west of their J2 pins: a B.Cu stub joins each to its (through-hole) pin, so they need no via.
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
BALL = ("J1_P26", "/Configuration/FLASH_IO2")                    # via in the ball pad
# bottom-side resistors placed at a through-hole pin by tools/phase5_decaps.py: the EPWM2A/2B pull-downs at J1,
# the JTAG pull-ups at J2
PULLDOWNS = (("R40", "J1", 9), ("R41", "J1", 11), ("R60", "J2", 1), ("R62", "J2", 2), ("R61", "J2", 3),
             ("R63", "J2", 4))
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


def clear_strips(b, refs=("U19", "U20", "U21", "U22"), half=0.95, near=1.2, far=2.6):
    """Old Agilex stitching vias left in the strips north of a translator's A pins or south of its B pins (where
    tools/phase5_decaps.py puts no new via either) go, with the stub of copper hanging on them."""
    boxes = []
    for r in refs:
        c = b.FindFootprintByReference(r).GetPosition()
        boxes += [(c.x - IU(half), c.y + IU(a), c.x + IU(half), c.y + IU(e)) for a, e in ((-far, -near), (near, far))]
    inside = lambda q: any(x0 <= q.x <= x1 and y0 <= q.y <= y1 for x0, y0, x1, y1 in boxes)
    pads = [p for f in b.GetFootprints() for p in f.Pads()]
    gone = []
    for v in list(b.GetTracks()):
        if v.Type() == pcbnew.PCB_VIA_T and inside(v.GetPosition()):
            circ = pcbnew.SHAPE_CIRCLE(v.GetPosition(), v.GetWidth(pcbnew.F_Cu) // 2)
            if any(q.GetNetCode() == v.GetNetCode() and any(q.IsOnLayer(l) and q.GetEffectiveShape(l).Collide(circ, 0)
                                                           for l in (pcbnew.F_Cu, pcbnew.B_Cu)) for q in pads):
                continue
            gone.append(v)
    for v in gone:
        for t in list(b.GetTracks()):
            if t.Type() != pcbnew.PCB_VIA_T and t.GetNetCode() == v.GetNetCode() and t.GetLength() < IU(0.3) \
                    and v.GetPosition() in (t.GetStart(), t.GetEnd()):
                b.Delete(t)
        print(f"  old via {v.GetNetname()} at ({MM(v.GetPosition().x):.2f}, {MM(v.GetPosition().y):.2f}) removed")
        b.Delete(v)


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
    if mode == "stubs":
        clear_strips(b)
        b.Save(dst)
        b = pcbnew.LoadBoard(dst)               # (KiCad 10: save and reload after deleting)
        j1 = b.FindFootprintByReference("J1")
        pad = {int(p.GetNumber()): p for p in j1.Pads()}
    if mode == "pulldowns":
        for ref, conn, k in PULLDOWNS:
            f = b.FindFootprintByReference(ref)
            pin = next(q for q in b.FindFootprintByReference(conn).Pads() if q.GetNumber() == str(k))
            p = next(p for p in f.Pads() if p.GetNumber() and p.GetNetCode() == pin.GetNetCode())
            px, py = MM(p.GetPosition().x), MM(p.GetPosition().y)
            x, y = MM(pin.GetPosition().x), MM(pin.GetPosition().y)
            path(b, pin.GetNet(), pcbnew.B_Cu, [(px, py), (x, y)])      # one segment: no vertex to end a via on
        b.Save(dst)
        print(f"phase5_j1: {len(PULLDOWNS)} resistor stubs on B.Cu")
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
