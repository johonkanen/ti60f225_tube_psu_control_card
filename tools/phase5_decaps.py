"""Phase 5: the Ti60's decoupling and VCCA filters on the bottom, at their balls (rerunnable on a fanned-out board).

    $KICAD_MOUNT/bin/python3.11 -I tools/phase5_decaps.py IN.kicad_pcb OUT.kicad_pcb
    $KICAD_MOUNT/bin/python3.11 -I tools/phase5_decaps.py IN.kicad_pcb OUT.kicad_pcb --legalise REF...

U1 is fanned out dog-bone style (KiCadRoutingTools bga_fanout --escape-method dogbone): every connected inner ball
has a 0.30/0.15 via in a diagonal gap of the 0.65 mm grid, as on the proven Ti60F225 card. Each cap is placed
on the bottom with its pads straight on vias where it can:
- a pad of a plane net (GND, +0V95, +1V8, +3V3) sits on an existing via of its net, or gets a new 0.30/0.15 via
  at its centre (a free gap site under the BGA, or anywhere around it); the planes connect those vias by fill;
- a VCCA pad has no plane: the first VCCA cap sits on the VCCA ball's via, the rest and the bead's VCCA pad
  are left to the router, next to it.
The configuration parts (CRESET_N RC, CDONE/CSI/TEST_N pull-ups, REF_RES) go to the ball of their signal.
The translators' 100n caps (VCCA pin 14, VCCB pin 13) and the OE pull-up go under the translators the same way.
Every pose is checked with pcbnew's own collision tests: 0.1 mm copper clearance, 0.2 mm hole clearance and
hole to hole, against every other net's pads, tracks, vias and F.Cu/B.Cu zone outlines; courtyards may not overlap
other bottom courtyards, and stay inside the board.

Which balls each cap serves (tools/sch_decoupling_47n.py): one 47n at every power ball (VCC, VCCA_BL, the used
HSIO banks' VCCIO, VCCAUX, VCCIO33), each at its own ball, first; then one 100n per rail along its balls; the
PLL_BL0 filter (1u, bead) at VCCA_BL; one 47u per rail at its regulator's inductor output. 47n/100n 0201s may sit
under the ball field (Lattice); nothing else goes there.
"""
import math
import sys

import pcbnew

MM, IU = pcbnew.ToMM, pcbnew.FromMM
CLR, HOLE_CLR, HOLE_HOLE = 0.1, 0.2, 0.2
SW_CLR = 0.15                                   # netclass SW (hardware/control_card.kicad_pro)
VIA_D, VIA_DRILL = 0.30, 0.15
STUB_W, STUB_MAX = 0.2, 0.8
# The band between the BGA's south edge and J1 carries the translator outputs and the direct HVIO header nets
# (the translator inputs come from banks 2A/2B, down the east side): no FPGA decap there; only the translators' own
# caps and the OE pull-up.
SOUTH_BAND = (86.0, 118.0, 108.0, 126.0)
BAND_OK = {f"C{n}" for n in range(158, 166)} | {"R67"}
PLANES = {"GND", "+0V95", "+1V8", "+3V3"}
BANK_ORDER = ["1A", "1B", "2A", "2B", "3A", "3B", "4A", "4B"]
UNUSED_BANKS = {"3A", "3B"}                     # no caps (tools/sch_vccio_caps.py)
USED_BANKS = [b for b in BANK_ORDER if b not in UNUSED_BANKS]   # 47n C166-C177 in this order, 2 per bank
HVIO_ORDER = ["TL", "TR", "BL", "BR"]
UNDER_BGA = {"47n", "100n"}                     # 0201s of these values may sit under the ball field (Lattice)


def refs(a, b, p="C"):
    return [f"{p}{i}" for i in range(a, b + 1)]


def pin_balls(u1):
    """Balls per pad name (VCC, VCCAUX, VCCIO1A, VCCA_TL, ...) from reference/ti60f225_pinout.csv."""
    import csv
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reference", "ti60f225_pinout.csv")
    out = {}
    for r in csv.DictReader(open(path)):
        out.setdefault(r["pad"], []).append(r["ball"])
    return out


def plan(u1):
    """(ref, target balls) in placement order (decoupling as in tools/sch_decoupling_47n.py)."""
    pb = pin_balls(u1)
    jobs = []
    # one 47n per power ball, each at its own ball: VCC, VCCA_BL, HSIO VCCIO (2 per used bank), VCCAUX, VCCIO33
    jobs += [(f"C{r}", [bl]) for r, bl in zip((119, 120, 114, 115, 116, 117, 118, 110), pb["VCC"])]
    jobs.append(("C100", pb["VCCA_BL"]))
    for k, bank in enumerate(USED_BANKS):
        jobs += [(f"C{166 + 2 * k + j}", [bl]) for j, bl in enumerate(pb[f"VCCIO{bank}"])]
    jobs += [(f"C{r}", [bl]) for r, bl in zip((123, 124, 131, 133), pb["VCCAUX"])]
    jobs += [(f"C{146 + 3 * i}", pb[f"VCCIO33_{bank}"]) for i, bank in enumerate(HVIO_ORDER)]
    # one 100n per rail, anywhere along its balls
    hsio = [bl for bank in USED_BANKS for bl in pb[f"VCCIO{bank}"]]
    vccio33 = [bl for bank in HVIO_ORDER for bl in pb[f"VCCIO33_{bank}"]]
    jobs += [("C109", pb["VCC"]), ("C122", pb["VCCAUX"]), ("C129", hsio), ("C153", vccio33)]
    # the PLL_BL0 filter: 1u and the bead at VCCA_BL (the unused PLLs' VCCA sit on VCC, no filter)
    jobs += [("C96", pb["VCCA_BL"]), ("FB8", pb["VCCA_BL"])]
    # one 47u per rail at its regulator's output (the inductor's output pad)
    jobs += [("C106", ["L1.2"]), ("C125", ["L2.2"]), ("C147", ["L3.2"])]
    # the translators (U19-U22, schematic order): VCCA (pin 14) 100n and VCCB (pin 13) 100n each, under the part;
    # the OE pull-up under U19, next to its OE pin
    for i in range(4):
        jobs += [(f"C{158 + 2 * i}", [f"U{19 + i}.14"]), (f"C{159 + 2 * i}", [f"U{19 + i}.13"])]
    jobs.append(("R67", ["U19.7"]))
    return jobs


class Board:
    def __init__(self, b):
        self.b = b
        self.layers = list(b.GetEnabledLayers().CuStack())     # new vias are checked on every copper layer
        e = b.GetBoardEdgesBoundingBox()
        e.Inflate(-IU(0.3))
        self.edge = e
        self.items = {l: [] for l in self.layers}   # (shape, net, bbox)
        self.holes = []                             # (pos, radius, net)
        self.court = []                             # bottom courtyard bboxes: (box, ref)
        self.vias = []                              # (pos, net, radius)
        self.field = None                           # U1's ball field: on the bottom only UNDER_BGA caps (set_field)
        # nets of a wider netclass clearance (the project's SW class: the buck switch nodes, 0.15 mm)
        self.net_clr = {n.GetNetCode(): SW_CLR for name, n in b.GetNetsByName().items()
                        if str(name).startswith("/Power/SW_")}
        for t in b.GetTracks():
            if t.Type() == pcbnew.PCB_VIA_T:
                self.add_via_obj(t)
            else:
                if t.GetLayer() in self.items:
                    self.items[t.GetLayer()].append((t.GetEffectiveShape(t.GetLayer()), t.GetNetCode(), t.GetBoundingBox()))
        for z in b.Zones():
            for l in (pcbnew.F_Cu, pcbnew.B_Cu):     # inner planes are refilled around new vias
                if not z.GetIsRuleArea() and z.IsOnLayer(l):
                    self.items[l].append((z.Outline(), z.GetNetCode(), z.GetBoundingBox()))

    def reserve_escapes(self, u1, length=2.5):
        """The fan-out ends its escapes just past the ball field: keep a corridor beyond each end free, so the
        router can carry them on (no cap pad on B.Cu, no new via on either layer)."""
        bb = pcbnew.BOX2I()
        for p in u1.Pads():
            bb.Merge(p.GetPosition())
        inner = pcbnew.BOX2I(bb.GetPosition(), bb.GetSize())
        inner.Inflate(IU(0.15))
        n = 0
        for t in self.b.GetTracks():
            if t.Type() != pcbnew.PCB_TRACE_T or t.GetLayer() not in self.items:
                continue
            for a, c in ((t.GetStart(), t.GetEnd()), (t.GetEnd(), t.GetStart())):
                if inner.Contains(c) and not inner.Contains(a):     # a: the outer end, c: inside the field
                    d = math.hypot(a.x - c.x, a.y - c.y)
                    if d == 0:
                        continue
                    e = pcbnew.VECTOR2I(int(a.x + (a.x - c.x) / d * IU(length)), int(a.y + (a.y - c.y) / d * IU(length)))
                    seg = pcbnew.SHAPE_SEGMENT(a, e, t.GetWidth())
                    box = pcbnew.BOX2I(pcbnew.VECTOR2I(min(a.x, e.x), min(a.y, e.y)),
                                       pcbnew.VECTOR2L(abs(a.x - e.x) + 1, abs(a.y - e.y) + 1))
                    box.Inflate(t.GetWidth())
                    self.items[t.GetLayer()].append((seg, -1, box))
                    n += 1
        return n

    def set_field(self, u1, margin=0.2):
        bb = pcbnew.BOX2I()
        for p in u1.Pads():
            bb.Merge(p.GetPosition())
        self.field = pcbnew.BOX2I(bb.GetPosition(), bb.GetSize())
        self.field.Inflate(IU(margin))

    def add_via_obj(self, v):
        for l in self.layers:
            self.items[l].append((v.GetEffectiveShape(l), v.GetNetCode(), v.GetBoundingBox()))
        self.holes.append((v.GetPosition(), v.GetDrillValue() // 2, v.GetNetCode()))
        self.vias.append((v.GetPosition(), v.GetNetCode(), v.GetWidth(pcbnew.F_Cu) // 2))

    def add_footprint(self, f):
        for p in f.Pads():
            for l in self.layers:
                if p.IsOnLayer(l):
                    self.items[l].append((p.GetEffectiveShape(l), p.GetNetCode(), p.GetBoundingBox()))
            if p.HasHole():
                self.holes.append((p.GetPosition(), max(p.GetDrillSize().x, p.GetDrillSize().y) // 2, p.GetNetCode()))
        c = f.GetCourtyard(pcbnew.B_CrtYd if f.IsFlipped() else pcbnew.F_CrtYd)
        self.court.append((c.BBox() if not c.IsEmpty() else f.GetBoundingBox(False), f.GetReference(), f.IsFlipped()))

    def clear(self, shape, box, layer, net, clr):
        box = pcbnew.BOX2I(box.GetPosition(), box.GetSize())
        box.Inflate(IU(clr + 0.3))
        for s, n, bb in self.items[layer]:
            if n != net and bb.Intersects(box) and s.Collide(shape, IU(max(clr, self.net_clr.get(n, 0))) - 1):
                return False
        return True

    def via_ok(self, pos, net):
        r, hr = IU(VIA_D / 2), IU(VIA_DRILL / 2)
        circ, hole = pcbnew.SHAPE_CIRCLE(pos, r), pcbnew.SHAPE_CIRCLE(pos, hr)
        box = pcbnew.BOX2I(pcbnew.VECTOR2I(pos.x - r, pos.y - r), pcbnew.VECTOR2L(2 * r, 2 * r))
        for l in self.layers:
            if not self.clear(circ, box, l, net, CLR) or not self.clear(hole, box, l, net, HOLE_CLR):
                return False
        for hp, hrr, hn in self.holes:
            if math.hypot(hp.x - pos.x, hp.y - pos.y) < hr + hrr + IU(HOLE_HOLE) and not (hn == net and hp == pos):
                return False
        return self.edge.Contains(pos)


def same_net_via_in(board, pad):
    sh = pad.GetEffectiveShape(pcbnew.B_Cu if pad.IsOnLayer(pcbnew.B_Cu) else pcbnew.F_Cu)
    for pos, n, r in board.vias:
        if n == pad.GetNetCode() and sh.Collide(pcbnew.VECTOR2I(pos), 0):
            return pos
    return None


def under_bga_ok(f):
    return f.GetValue() in UNDER_BGA and "0201" in str(f.GetFPID().GetLibItemName())


def try_pose(board, f, pos, rot, netname):
    """Legal? -> (new via positions) or None."""
    f.SetPosition(pos)
    f.SetOrientationDegrees(rot)
    side = pcbnew.B_Cu if f.IsFlipped() else pcbnew.F_Cu
    c = f.GetCourtyard(pcbnew.B_CrtYd if f.IsFlipped() else pcbnew.F_CrtYd)
    cb = c.BBox() if not c.IsEmpty() else f.GetBoundingBox(False)
    if not board.edge.Contains(cb):
        return None
    if f.GetReference() not in BAND_OK:
        x0, y0, x1, y1 = SOUTH_BAND
        band = pcbnew.BOX2I(pcbnew.VECTOR2I(IU(x0), IU(y0)), pcbnew.VECTOR2L(IU(x1 - x0), IU(y1 - y0)))
        if band.Intersects(cb):
            return None
    for ob, _, flipped in board.court:
        if flipped == f.IsFlipped() and ob.Intersects(cb):
            return None
    if board.field is not None and board.field.Intersects(cb) and not under_bga_ok(f):
        return None
    new = []
    for p in f.Pads():
        if not p.GetNumber() or not p.IsOnLayer(side):
            continue
        sh, bb, net = p.GetEffectiveShape(side), p.GetBoundingBox(), p.GetNetCode()
        if not board.clear(sh, bb, side, net, CLR):
            return None
        for hp, hr, hn in board.holes:      # other nets' holes 0.2 mm from the pad copper
            if hn != net and abs(hp.x - p.GetPosition().x) < IU(1.5) and abs(hp.y - p.GetPosition().y) < IU(1.5) \
                    and sh.Collide(pcbnew.SHAPE_CIRCLE(hp, hr), IU(HOLE_CLR) - 1):
                return None
        if netname(p) in PLANES and same_net_via_in(board, p) is None:
            stub = stub_to_via(board, f, p, side)
            if stub is not None:
                new.append(("stub", stub, p.GetNet()))
                continue
            vp = p.GetPosition()
            if not board.via_ok(vp, net):
                return None
            new.append(("via", vp, p.GetNet()))
    vias = [n[1] for n in new if n[0] == "via"]
    if len(vias) == 2 and math.hypot(vias[0].x - vias[1].x, vias[0].y - vias[1].y) < IU(VIA_D + HOLE_HOLE):
        return None
    return new


def cost(new):
    return sum(0.25 if n[0] == "via" else 0.1 for n in new)


def stub_to_via(board, f, p, side):
    """A short track (STUB_W, at most STUB_MAX long) from the pad centre to an existing via of its net, clear of
    every other net on that side (and of the part's own other pads), or None."""
    a = p.GetPosition()
    best = None
    for pos, n, r in board.vias:
        d = math.hypot(pos.x - a.x, pos.y - a.y)
        if n != p.GetNetCode() or d > IU(STUB_MAX) or (best is not None and d >= best[0]):
            continue
        seg = pcbnew.SHAPE_SEGMENT(a, pcbnew.VECTOR2I(pos), IU(STUB_W))
        box = pcbnew.BOX2I(pcbnew.VECTOR2I(min(a.x, pos.x), min(a.y, pos.y)), pcbnew.VECTOR2L(abs(a.x - pos.x) + 1, abs(a.y - pos.y) + 1))
        if not board.clear(seg, box, side, p.GetNetCode(), CLR):
            continue
        if any(q.GetNumber() and q.GetNetCode() != p.GetNetCode() and q.IsOnLayer(side)
               and q.GetEffectiveShape(side).Collide(seg, IU(CLR) - 1) for q in f.Pads()):
            continue
        if any(hn != p.GetNetCode() and seg.Collide(pcbnew.SHAPE_CIRCLE(hp, hr), IU(HOLE_CLR) - 1)
               for hp, hr, hn in board.holes if abs(hp.x - a.x) < IU(1.5) and abs(hp.y - a.y) < IU(1.5)):
            continue
        best = (d, (a, pcbnew.VECTOR2I(pos)))
    return best[1] if best else None


class Lattice:
    """U1's ball sites and the diagonal gaps between them, in half-pitch steps (both indices even: a ball, both
    odd: a gap). A 0201 (pads 0.64 mm apart) fits the 0.65 mm pitch with each pad on a site: on a plane ball's
    via, or on a new via in a gap."""
    def __init__(self, u1):
        xs = sorted({p.GetPosition().x for p in u1.Pads()})
        ys = sorted({p.GetPosition().y for p in u1.Pads()})
        self.x0, self.y0, self.h = xs[0], ys[0], (xs[1] - xs[0]) / 2
        self.nx, self.ny = 2 * (len(xs) - 1), 2 * (len(ys) - 1)

    def index(self, pos, tol=IU(0.03)):
        i, j = (pos.x - self.x0) / self.h, (pos.y - self.y0) / self.h
        ri, rj = round(i), round(j)
        if abs(i - ri) * self.h > tol or abs(j - rj) * self.h > tol or (ri - rj) % 2:
            return None
        return (ri, rj) if 0 <= ri <= self.nx and 0 <= rj <= self.ny else None

    def sites(self):
        return [pcbnew.VECTOR2I(int(self.x0 + i * self.h), int(self.y0 + j * self.h))
                for i in range(self.nx + 1) for j in range(self.ny + 1) if (i - j) % 2 == 0]


def lattice_poses(f, lat, tpos, reach=2.0):
    """Poses of a 0201 under the ball field with both pads on lattice sites, near the targets."""
    out = []
    for s in lat.sites():
        if min(math.hypot(s.x - t.x, s.y - t.y) for t in tpos) > IU(reach):
            continue
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            c = pcbnew.VECTOR2I(int(s.x + dx * lat.h), int(s.y + dy * lat.h))
            for rot in (0, 90, 180, 270):
                f.SetPosition(c); f.SetOrientationDegrees(rot)
                if all(lat.index(p.GetPosition()) is not None for p in f.Pads() if p.GetNumber()):
                    out.append((c, rot))
    return list({(c.x, c.y, r): (c, r) for c, r in out}.values())


def main(src, dst, legalise=()):
    b = pcbnew.LoadBoard(src)
    u1 = b.FindFootprintByReference("U1")
    netname = lambda p: p.GetNetname().split("/")[-1]
    if legalise:    # parts placed by another tool: each to the nearest legal pose around where it is
        jobs = []
        for r in legalise:
            f = b.FindFootprintByReference(r)
            sig = [p for p in f.Pads() if p.GetNumber() and netname(p) not in PLANES] or list(f.Pads())
            jobs.append((r, [f"{r}.{sig[0].GetNumber()}"]))
    else:
        jobs = plan(u1)
        # configuration parts at the FPGA ball of their signal: CRESET_N RC, CDONE / CSI / TEST_N pull-ups, REF_RES
        for r in ["R56", "R53", "R55", "R64", "R65", "R66", "R52", "C157"]:
            f = b.FindFootprintByReference(r)
            sig = next(p.GetNetCode() for p in f.Pads() if p.GetNumber() and netname(p) not in PLANES)
            jobs.append((r, [p.GetNumber() for p in u1.Pads() if p.GetNetCode() == sig]))
    moving = {r for r, _ in jobs}
    board = Board(b)
    print("escape corridors reserved:", board.reserve_escapes(u1))
    if not legalise:
        board.set_field(u1)
    for f in b.GetFootprints():
        if f.GetReference() not in moving:
            board.add_footprint(f)
    ball = {p.GetNumber(): p.GetPosition() for p in u1.Pads()}
    lat = Lattice(u1)
    for f in b.GetFootprints():
        if f.GetReference() != "U1":    # (a legalised part's own pad is read here, before it moves)
            ball.update({f"{f.GetReference()}.{p.GetNumber()}": p.GetPosition() for p in f.Pads()})
    report = []
    for ref, targets in jobs:
        f = b.FindFootprintByReference(ref)
        if not f.IsFlipped() and not legalise:
            f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        rail = next(netname(p) for p in f.Pads() if p.GetNumber() and (netname(p) not in ("GND", "+1V8")
                    or netname(p) == "+1V8" and ref.startswith("C")))
        if legalise:
            rail = netname([p for p in f.Pads() if p.GetNumber() == targets[0].split(".")[1]][0])
        tpos = [ball[t] for t in targets]

        def rail_dist(pos_rot):
            f.SetPosition(pos_rot[0]); f.SetOrientationDegrees(pos_rot[1])
            rp = next(p for p in f.Pads() if p.GetNumber() and netname(p) == rail).GetPosition()
            return min(math.hypot(rp.x - t.x, rp.y - t.y) for t in tpos) / 1e6

        # candidate poses: a pad's centre on an existing via of its net near the targets, then a grid around them
        cands = []
        for p0 in [p for p in f.Pads() if p.GetNumber()]:
            for vpos, vn, _ in board.vias:
                if vn != p0.GetNetCode() or min(math.hypot(vpos.x - t.x, vpos.y - t.y) for t in tpos) > IU(3.5):
                    continue
                for rot in (0, 90, 180, 270):
                    f.SetPosition(pcbnew.VECTOR2I(0, 0)); f.SetOrientationDegrees(rot)
                    off = [p for p in f.Pads() if p.GetNumber() == p0.GetNumber()][0].GetPosition()
                    cands.append((pcbnew.VECTOR2I(vpos.x - off.x, vpos.y - off.y), rot))
        if under_bga_ok(f):
            cands += lattice_poses(f, lat, tpos)
        best = None
        for c in sorted(cands, key=rail_dist):
            if best is not None and rail_dist(c) >= best[0]:
                break                       # score >= rail distance: nothing later can win
            new = try_pose(board, f, c[0], c[1], netname)
            if new is not None:
                score = rail_dist(c) + cost(new)
                if best is None or score < best[0]:
                    best = (score, c, new)
        field = board.field
        for attempt in (0, 1):  # no place outside the ball field: under it after all, wider (R65)
            if attempt and (best is not None or field is None or under_bga_ok(f)):
                break
            board.field = field if attempt == 0 else None
            if not (best is None or best[0] > 0.6):     # a grid search around the targets, nearest first
                continue
            step, reach = 0.1, (80, 130)[attempt]
            grid = []
            for t in tpos:
                for i in range(-reach, reach + 1):
                    for j in range(-reach, reach + 1):
                        grid.append((pcbnew.VECTOR2I(t.x + IU(i * step), t.y + IU(j * step)), 0))
                        grid.append((pcbnew.VECTOR2I(t.x + IU(i * step), t.y + IU(j * step)), 90))
            grid = sorted(set((g[0].x, g[0].y, g[1]) for g in grid), key=lambda g: rail_dist((pcbnew.VECTOR2I(g[0], g[1]), g[2])))
            for gx, gy, rot in grid:
                c = (pcbnew.VECTOR2I(gx, gy), rot)
                d = rail_dist(c)
                if best is not None and d >= best[0]:
                    break
                new = try_pose(board, f, c[0], c[1], netname)
                if new is not None:
                    score = d + cost(new)
                    if best is None or score < best[0]:
                        best = (score, c, new)
                    break
        board.field = field
        if best is None:
            print(f"NO LEGAL PLACE for {ref}: left where it was")
            continue
        _, (pos, rot), new = best
        f.SetPosition(pos); f.SetOrientationDegrees(rot)
        for kind, geo, net in new:
            if kind == "via":
                v = pcbnew.PCB_VIA(b)
                v.SetPosition(geo); v.SetViaType(pcbnew.VIATYPE_THROUGH)
                v.SetWidth(IU(VIA_D)); v.SetDrill(IU(VIA_DRILL)); v.SetNet(net)
                b.Add(v)
                board.add_via_obj(v)
            else:
                tr = pcbnew.PCB_TRACK(b)
                tr.SetStart(geo[0]); tr.SetEnd(geo[1]); tr.SetWidth(IU(STUB_W)); tr.SetNet(net)
                tr.SetLayer(pcbnew.B_Cu if f.IsFlipped() else pcbnew.F_Cu)
                b.Add(tr)
                board.items[tr.GetLayer()].append((tr.GetEffectiveShape(tr.GetLayer()), tr.GetNetCode(), tr.GetBoundingBox()))
        board.add_footprint(f)
        report.append((ref, f.GetValue(), rail, targets, rail_dist((pos, rot)), sum(n[0] == "via" for n in new),
                       sum(n[0] == "stub" for n in new)))
    b.Save(dst)
    for ref, val, rail, t, d, n, s in report:
        print(f"{ref:5} {val:12} {rail:16} {d:5.2f} mm from {'/'.join(t)[:24]:24} new vias {n} stubs {s}")
    print(f"placed {len(report)} parts, {sum(r[5] for r in report)} new vias, {sum(r[6] for r in report)} stubs")


if __name__ == "__main__":
    if len(sys.argv) > 3 and sys.argv[3] == "--legalise":
        main(sys.argv[1], sys.argv[2], sys.argv[4:])
    else:
        main(sys.argv[1], sys.argv[2])
