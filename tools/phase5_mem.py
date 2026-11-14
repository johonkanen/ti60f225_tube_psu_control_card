"""Phase 5 routing: the HyperRAM and flash buses drawn by script, before the router runs.

    $KICAD_MOUNT/bin/python3.11 -I tools/phase5_mem.py IN.kicad_pcb OUT.kicad_pcb [buses|edge]

Left to itself KiCadRoutingTools takes several HyperRAM nets around the outside of the package (three of twelve
then fail on F.Cu, and the loop walls the LED nets in) and crosses the flash nets with a dozen vias. With U1 at
180 deg both buses are short fans without a crossing, so they are drawn here, 0.1 mm on F.Cu, and locked (the
router never rips locked copper):

1. Escape out of the memory's ball field (BGA-24, 1 mm pitch): 45 deg from the ball into the channel between two
   ball columns (two lanes per channel, 0.225 mm apart, on the router's 0.025 mm grid; the ball further from the
   south edge takes the far lane), then south to a line EXIT below the southern ball row.
2. Fan to the FPGA: south, one 45 deg stretch, south again (HyperRAM, to the fan-out escapes on U1's north edge);
   the flash lines leave U1's east edge, turn north in five lanes east of the BGA corner and bend to their exits.
   Neighbouring 45 deg stretches are staggered so they keep 0.225 mm between centres.

U9 (HyperRAM, at 90 deg: column A west, row 1 south), west to east, as the balls of banks 4A/4B on U1's north edge:
    RESET# CS# | CK | DQ2 RWDS | DQ4 DQ3 | DQ1 DQ0 | DQ7 | DQ6 DQ5
U7 (flash, at 90 deg), west to east: CS# (around the north of the CLK ball), CLK, IO0, IO1, IO3, IO2 (east of the
ball field, back in between rows 4 and 5): the order in which the six leave U1's east edge, north to south.
IO2, IO3 and RESET# have a via in their flash ball for a pull-up on the bottom (tools/phase5_vias.py).
Mode edge (run in the layout chain, after the fan-out and before the decoupling is placed, so no bottom pad of
another net lands there): the two other nets that leave U1's east edge between the flash balls (CSI, CDONE) get a
via at the end of their escape, in line with it, west of the flash lanes; their pull-ups then sit on those vias.
J1_P17 and HT_SDATA get their via to L3 beside the end of their escape on the north edge (FAR_VIA).
The top-side flash pull-up (R54 on CS#; tools/phase5_place.py) is joined to its line.
"""
import math
import sys

import pcbnew

IU, MM = pcbnew.FromMM, pcbnew.ToMM
W = 0.1
PITCH = 0.225           # lane pitch: 0.1 mm track + 0.125 mm clearance
OUT = 0.445             # first lane outside the ball field, from the outer column
EXIT = 0.905            # the escapes end this far south of the southern ball row (on the grid)
DIAG = PITCH * math.sqrt(2) + 0.005     # stagger of neighbouring 45 deg stretches, along the lane
HR_DIAG_Y = 104.0       # where the western HyperRAM line starts its 45 deg stretch
FL_VIA_X, FL_LANE_X = 97.2, 97.6        # east of U1: the config/JTAG vias, then the first (western) flash lane
FL_BEND_Y = {"C2": 103.6, "B2": 103.4, "D3": 102.6, "D2": 102.9, "D4": 103.3, "C4": 103.7}   # each lane's bend
EDGE_VIA = ("/Configuration/CSI", "/Configuration/CDONE")
# the two header nets of bank BL (balls R4, R3 on the north edge) go to L3 beside their escape's end: 45 deg to a via
# dx to the side. Straight north of them lies the L4 channel (0.9 mm wide at x 94.6) that joins the +3V3 ball P4
# to the +3V3 plane through the +0V95 island: no via may sit in it, so HT_SDATA steps west and J1_P17 east
FAR_VIA = (("HT_SDATA", -0.75), ("J1_P17", 0.65))
# From those vias the two run on L3 as a pair: east, north of the BGA (HT_SDATA 0.45 mm north of J1_P17, clear of
# its via), around the corner and south down the east side to FAR_END_Y, where the router takes them on to their
# J1 stubs. Drawn here because the router ran them 2-3 mm apart, with a strip of the +1V8 pour cut off in between
FAR_L3 = {"J1_P17": (107.35, 99.0), "HT_SDATA": (106.9, 99.45)}     # y of the east run, x of the south run
FAR_END_Y = 119.5


def grid(v, g=0.025):
    return round(round(v / g) * g, 4)


def track(b, net, pts, layer=pcbnew.F_Cu):
    for a, c in zip(pts, pts[1:]):
        if abs(a[0] - c[0]) < 1e-6 and abs(a[1] - c[1]) < 1e-6:
            continue
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(pcbnew.VECTOR2I(IU(a[0]), IU(a[1])))
        t.SetEnd(pcbnew.VECTOR2I(IU(c[0]), IU(c[1])))
        t.SetWidth(IU(W))
        t.SetLayer(layer)
        t.SetNet(net)
        t.SetLocked(True)
        b.Add(t)


def xy(pad):
    p = pad.GetPosition()
    return MM(p.x), MM(p.y)


def lane(pad, lx, y_end):
    """Points: the ball, 45 deg to the lane at x = lx, south to y_end."""
    x, y = xy(pad)
    return [(x, y), (lx, y + abs(lx - x)), (lx, y_end)]


def escape_end(b, pad, c):
    """The outer end of a U1 ball's fan-out escape: the point of the copper hanging on the ball farthest from c."""
    tr = [t for t in b.GetTracks() if t.GetNetCode() == pad.GetNetCode() and t.Type() == pcbnew.PCB_TRACE_T
          and t.GetLayer() == pcbnew.F_Cu]
    end, seen, todo = pad.GetPosition(), set(), [pad.GetPosition()]
    while todo:
        q = todo.pop()
        for t in tr:
            if id(t) in seen:
                continue
            for a, e in ((t.GetStart(), t.GetEnd()), (t.GetEnd(), t.GetStart())):
                if a == q:
                    seen.add(id(t)); todo.append(e)
                    if (e.x - c.x) ** 2 + (e.y - c.y) ** 2 > (end.x - c.x) ** 2 + (end.y - c.y) ** 2:
                        end = e
    return MM(end.x), MM(end.y)


def memory(b, ref):
    f = b.FindFootprintByReference(ref)
    pad = {p.GetNumber(): p for p in f.Pads()}
    col = {c: xy(pad[c + "3"])[0] for c in "ABCDE"}
    if not (col["A"] < col["B"] < col["E"] and xy(pad["E1"])[1] > xy(pad["E5"])[1]):
        sys.exit(f"phase5_mem: {ref} is not at 90 deg (column A west, row 1 south)")
    mid = lambda a, c: (col[a] + col[c]) / 2
    two = lambda a, c: (grid(mid(a, c) - 0.12), grid(mid(a, c) - 0.12) + PITCH)     # the two lanes of a channel
    return pad, col, mid, two, grid(xy(pad["E1"])[1] + EXIT)


def via(b, net, pos):
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(pcbnew.VECTOR2I(IU(pos[0]), IU(pos[1])))
    v.SetWidth(pcbnew.F_Cu, IU(0.30))
    v.SetDrill(IU(0.15))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetNet(net)
    v.SetLocked(True)
    b.Add(v)


def main(src, dst, mode="buses"):
    b = pcbnew.LoadBoard(src)
    u1 = b.FindFootprintByReference("U1")
    c1 = u1.GetPosition()
    ball = {p.GetNetCode(): p for p in u1.Pads()}
    if mode == "edge":
        for name in EDGE_VIA:
            p = next(p for p in u1.Pads() if p.GetNetname() == name)
            ex, ey = escape_end(b, p, c1)
            if ex >= FL_VIA_X or ex < c1.x / 1e6:
                sys.exit(f"phase5_mem: the escape of {name} does not end on U1's east edge, west of x {FL_VIA_X}")
            track(b, p.GetNet(), [(ex, ey), (FL_VIA_X, ey)])
            via(b, p.GetNet(), (FL_VIA_X, ey))
        for name, dx in FAR_VIA:
            p = next(p for p in u1.Pads() if p.GetNetname() == name)
            ex, ey = escape_end(b, p, c1)
            if ey > c1.y / 1e6 or abs(ex - xy(p)[0]) > 0.01:
                sys.exit(f"phase5_mem: the escape of {name} does not run straight north from its ball")
            v = (grid(ex + dx), grid(ey - 0.1 - abs(dx)))
            track(b, p.GetNet(), [(ex, ey), (ex, v[1] + abs(v[0] - ex)), v])
            via(b, p.GetNet(), v)
        b.Save(dst)
        print(f"phase5_mem: {len(EDGE_VIA)} vias at the escapes between the flash lines, {len(FAR_VIA)} for the "
              f"header nets of bank BL")
        return

    # HyperRAM
    pad, col, mid, two, y_end = memory(b, "U9")
    w0 = grid(col["A"] - OUT)
    plan = [("A4", w0 - PITCH), ("A3", w0),                                     # RESET#, CS#: west of the field
            ("B2", grid(mid("A", "B"))),                                        # CK
            ("C4", two("B", "C")[0]), ("C3", two("B", "C")[1]),                 # DQ2, RWDS
            ("D5", two("C", "D")[0]), ("D4", two("C", "D")[1]),                 # DQ4, DQ3
            ("D2", two("D", "E")[0]), ("D3", two("D", "E")[1]),                 # DQ1, DQ0
            ("E1", grid(col["E"])),                                             # DQ7
            ("E2", grid(col["E"] + OUT)), ("E3", grid(col["E"] + OUT) + PITCH)]  # DQ6, DQ5: east of the field
    ends = [escape_end(b, ball[pad[k].GetNetCode()], c1) for k, _ in plan]
    if [e[0] for e in ends] != sorted(e[0] for e in ends) or any(abs(e[1] - ends[0][1]) > 0.01 for e in ends):
        sys.exit(f"phase5_mem: the HyperRAM balls on U1 are not in the order of the exits: "
                 f"{[(pad[k].GetNetname(), e) for (k, _), e in zip(plan, ends)]}")
    a = HR_DIAG_Y
    for i, ((k, lx), (fx, fy)) in enumerate(zip(plan, ends)):
        if i:       # a 45 deg stretch starts at least DIAG further north per PITCH it stands closer to its neighbour
            a = min(a, a + (lx - plan[i - 1][1]) - DIAG)
        if fx < lx or a + (fx - lx) > fy - 0.2 or a < y_end:
            sys.exit(f"phase5_mem: no room for the fan of {pad[k].GetNetname()}")
        track(b, pad[k].GetNet(), lane(pad[k], lx, y_end) + [(lx, a), (fx, a + (fx - lx)), (fx, fy)])
    print("phase5_mem: U9 west to east:", " ".join(pad[k].GetNetname() for k, _ in plan))

    # flash
    pad, col, mid, two, y_end = memory(b, "U7")
    y23 = (xy(pad["C2"])[1] + xy(pad["C3"])[1]) / 2          # between rows 2 and 3
    ab, c = grid(mid("A", "B")), 0.15
    esc = {"B2": lane(pad["B2"], grid(mid("B", "C")), y_end),                   # CLK
           "D3": lane(pad["D3"], grid(mid("C", "D")), y_end),                   # IO0
           "D2": lane(pad["D2"], two("D", "E")[0], y_end),                      # IO1
           "D4": lane(pad["D4"], two("D", "E")[1], y_end)}                      # IO3
    # CS# (C2): north-west into the gap between rows 2 and 3, west past the CLK ball (B2), then south between
    # columns A and B
    esc["C2"] = [xy(pad["C2"]), (mid("B", "C"), y23), (ab + c, y23), (ab, y23 + c), (ab, y_end)]
    # IO2 (C4): north-east into the gap between rows 4 and 5, east past columns D and E, then south outside the field
    y45, ex = (xy(pad["C4"])[1] + xy(pad["C5"])[1]) / 2, grid(col["E"] + OUT) + 0.025
    esc["C4"] = [xy(pad["C4"]), (mid("C", "D"), y45), (ex - c, y45), (ex, y45 + c), (ex, y_end)]
    order = ("C2", "B2", "D3", "D2", "D4", "C4")
    ends = {k: escape_end(b, ball[pad[k].GetNetCode()], c1) for k in order}
    if [ends[k][1] for k in order] != sorted(ends[k][1] for k in order) or any(ends[k][0] < c1.x / 1e6 for k in order):
        sys.exit(f"phase5_mem: the flash escapes do not leave U1's east edge north to south: {ends}")
    corner = {}
    for i, k in enumerate(order):
        lx, sx, by = FL_LANE_X + PITCH * i, esc[k][-1][0], FL_BEND_Y[k]
        ex, ey = ends[k]
        pts = esc[k] + [(sx, by - abs(lx - sx)), (lx, by), (lx, ey - c), (lx - c, ey), (ex, ey)]
        track(b, pad[k].GetNet(), pts)
        corner[k] = (sx, by - abs(lx - sx))
    for ref, k in (("R54", "C2"),):                         # the top-side pull-up, joined to its line
        r = next(p for p in b.FindFootprintByReference(ref).Pads() if p.GetNetCode() == pad[k].GetNetCode())
        px, py = xy(r)
        sx = esc[k][-1][0]
        on = (sx, py) if y_end <= py <= corner[k][1] else corner[k]
        track(b, r.GetNet(), [(px, py), on])
    print("phase5_mem: U7 west to east:", " ".join(pad[k].GetNetname().split("/")[-1] for k in order))
    # J1_P17 and HT_SDATA on L3 from their vias (edge mode) east and down the east side
    l3, c = b.GetLayerID("In2.Cu"), 0.15
    for name, (ry, rx) in FAR_L3.items():
        net = next(p for p in u1.Pads() if p.GetNetname() == name).GetNet()
        v = [t for t in b.GetTracks() if t.Type() == pcbnew.PCB_VIA_T and t.GetNetCode() == net.GetNetCode()]
        if len(v) != 1:
            sys.exit(f"phase5_mem: {name} has {len(v)} vias, expected the one of the layout chain")
        vx, vy = MM(v[0].GetPosition().x), MM(v[0].GetPosition().y)
        d = abs(vy - ry)
        pts = [(vx, vy), (vx + d, ry), (rx - c, ry), (rx, ry + c), (rx, FAR_END_Y)]
        track(b, net, pts, l3)
    b.Save(dst)
    print("phase5_mem: HyperRAM and flash buses and the two L3 lines of bank BL drawn and locked")


if __name__ == "__main__":
    main(*sys.argv[1:4])
