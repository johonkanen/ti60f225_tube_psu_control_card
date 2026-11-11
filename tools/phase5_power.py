"""Phase 5: supply copper of the synced board made to fit the Ti60 (run after placement, before the L4 split).

    $KICAD_MOUNT/bin/python3.11 -I tools/phase5_power.py IN.kicad_pcb OUT.kicad_pcb

The pours and taps kept from the Agilex board no longer fit (audit 2026-11-11):
1. dead copper: tracks on L4 (In3.Cu, the +0V95/+3V3 split plane) other than the Agilex analog lines ADA*
   (a cut PG_1V8 piece), then every via that touches no copper of its net on any layer;
2. the 0.95 V and 3.3 V buck output pours on B.Cu had no via to L4: STITCH_N vias each, on a grid inside the pour;
3. supply and GND pads that lost their via (U2's feedback divider, U6/U12/U15, oscillator, HyperRAM caps, ...):
   every outer-layer pad of a plane net whose copper on its side reaches no via or hole gets one: a stub of at
   most 0.8 mm to an existing via of its net, else a 0.30/0.15 via in the pad (filled and capped on 6 layers),
   else a via beside it with a 0.2 mm stub. The BGAs (via-in-pad already) and the UQFN translators (their pins
   go to the cap vias by routing) are left out;
4. L3 (In2.Cu): the Agilex +1V8 outline (which stopped short of the translators) and the old +1V8_HR rectangle
   replaced by one +1V8 pour over the whole board.
The L4 split itself comes next (KiCadRoutingTools route_planes + phase5_planes.py notch), from the vias as they
are after this step.
"""
import math
import sys

import pcbnew

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from phase5_decaps import CLR, HOLE_CLR, IU, MM, STUB_W, VIA_D, VIA_DRILL, Board, stub_to_via  # noqa: E402

PLANES = {"GND", "+0V95", "+1V8", "+3V3"}
SKIP = {"U1", "U7", "U9", "U19", "U20", "U21", "U22"}
STITCH = {"+0V95": 6, "+3V3": 6}
L3, L4 = pcbnew.In2_Cu, pcbnew.In3_Cu


def net(i):
    return i.GetNetname().split("/")[-1]


def dead_copper(b):
    fills = [(z.GetNetCode(), l, z.Outline()) for z in list(b.Zones()) if not z.GetIsRuleArea()
             for l in b.GetEnabledLayers().CuStack() if z.IsOnLayer(l)]
    n = 0
    for t in list(b.GetTracks()):
        if t.Type() == pcbnew.PCB_TRACE_T and t.GetLayer() == L4 and not net(t).startswith("ADA"):
            b.Delete(t)
            n += 1
    pads = [p for f in b.GetFootprints() for p in f.Pads()]
    dead = []
    for v in b.GetTracks():
        if v.Type() != pcbnew.PCB_VIA_T:
            continue
        p, nc, r = v.GetPosition(), v.GetNetCode(), v.GetWidth(pcbnew.F_Cu) // 2
        circ = pcbnew.SHAPE_CIRCLE(p, r)
        if any(nc == zn and o.Collide(p, r) for zn, l, o in fills):
            continue
        if any(t.GetNetCode() == nc and t.Type() != pcbnew.PCB_VIA_T and t.GetEffectiveShape().Collide(circ, 0)
               for t in b.GetTracks()):
            continue
        if any(q.GetNetCode() == nc and any(q.IsOnLayer(l) and q.GetEffectiveShape(l).Collide(circ, 0)
                                            for l in (pcbnew.F_Cu, pcbnew.B_Cu)) for q in pads):
            continue
        dead.append(v)
    for v in dead:
        print(f"  dead via {net(v)} at ({MM(v.GetPosition().x):.2f}, {MM(v.GetPosition().y):.2f}) removed")
        b.Delete(v)
    print(f"phase5_power: {n} tracks removed from L4, {len(dead)} dead vias")


def add_via(b, board, pos, netinfo):
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(pos); v.SetWidth(IU(VIA_D)); v.SetDrill(IU(VIA_DRILL)); v.SetNet(netinfo)
    b.Add(v)
    board.add_via_obj(v)
    return v


def add_stub(b, board, a, c, netinfo, layer):
    t = pcbnew.PCB_TRACK(b)
    t.SetStart(a); t.SetEnd(c); t.SetWidth(IU(STUB_W)); t.SetNet(netinfo); t.SetLayer(layer)
    b.Add(t)
    board.items[layer].append((t.GetEffectiveShape(layer), t.GetNetCode(), t.GetBoundingBox()))


def stitch(b, board):
    for z in list(b.Zones()):
        if z.GetIsRuleArea() or not z.IsOnLayer(pcbnew.B_Cu) or net(z) not in STITCH:
            continue
        o = z.Outline()
        bb = o.BBox()
        c = bb.Centre()
        inset = IU(0.35)
        ring = [(inset * math.cos(k * math.pi / 4), inset * math.sin(k * math.pi / 4)) for k in range(8)]
        pts = []
        for x in range(bb.GetX(), bb.GetRight(), IU(0.6)):
            for y in range(bb.GetY(), bb.GetBottom(), IU(0.6)):
                if all(o.Contains(pcbnew.VECTOR2I(int(x + dx), int(y + dy))) for dx, dy in ring):
                    pts.append(pcbnew.VECTOR2I(x, y))
        pts.sort(key=lambda p: math.hypot(p.x - c.x, p.y - c.y))
        placed = []
        for p in pts:
            if len(placed) >= STITCH[net(z)]:
                break
            if all(math.hypot(p.x - q.x, p.y - q.y) >= IU(0.6) for q in placed) and board.via_ok(p, z.GetNetCode()):
                add_via(b, board, p, z.GetNet())
                placed.append(p)
        print(f"phase5_power: {len(placed)} stitching vias in the {net(z)} buck pour on B.Cu")


def reaches_via(b, pad, side, fills):
    """Does the pad's same-net copper on its side (pads, tracks, outer pours) reach a via or a plated hole?"""
    nc = pad.GetNetCode()
    tracks = [t for t in b.GetTracks() if t.GetNetCode() == nc and t.Type() == pcbnew.PCB_TRACE_T and t.GetLayer() == side]
    vias = [t for t in b.GetTracks() if t.GetNetCode() == nc and t.Type() == pcbnew.PCB_VIA_T]
    pads = [q for f in b.GetFootprints() for q in f.Pads() if q.GetNetCode() == nc and q.IsOnLayer(side)]
    polys = [s for zn, s in fills.get(side, []) if zn == nc]
    shape = lambda i: i.GetEffectiveShape(side)
    todo, seen = [pad], {id(pad)}
    while todo:
        cur = todo.pop()
        s = shape(cur)
        if any(v.GetEffectiveShape(side).Collide(s, 0) for v in vias):
            return True
        if isinstance(cur, pcbnew.PAD) and cur.HasHole():
            return True
        for p in polys:
            if p.Collide(s, 0):
                # a pour: everything it touches joins (its vias included)
                if any(p.Collide(v.GetPosition(), v.GetWidth(pcbnew.F_Cu) // 2) for v in vias):
                    return True
                for q in pads:
                    if id(q) not in seen and p.Collide(q.GetPosition(), 0):
                        seen.add(id(q)); todo.append(q)
        for i in tracks + pads:
            if id(i) not in seen and shape(i).Collide(s, 0):
                seen.add(id(i)); todo.append(i)
    return False


def taps(b, board):
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    fills = {}
    for z in list(b.Zones()):
        for l in (pcbnew.F_Cu, pcbnew.B_Cu):
            if not z.GetIsRuleArea() and z.IsOnLayer(l):
                fills.setdefault(l, []).append((z.GetNetCode(), z.GetFilledPolysList(l)))
    n = {"stub": 0, "in pad": 0, "beside": 0, "none": 0}
    for f in b.GetFootprints():
        if f.GetReference() in SKIP:
            continue
        side = pcbnew.B_Cu if f.IsFlipped() else pcbnew.F_Cu
        for p in f.Pads():
            if not p.GetNumber() or p.HasHole() or net(p) not in PLANES or not p.IsOnLayer(side):
                continue
            if reaches_via(b, p, side, fills):
                continue
            s = stub_to_via(board, f, p, side)
            if s is not None:
                add_stub(b, board, s[0], s[1], p.GetNet(), side)
                n["stub"] += 1
                continue
            if board.via_ok(p.GetPosition(), p.GetNetCode()):
                add_via(b, board, p.GetPosition(), p.GetNet())
                n["in pad"] += 1
                continue
            done = False
            a = p.GetPosition()
            for rr in (0.45, 0.6, 0.75):
                for k in range(16):
                    ang = k * math.pi / 8
                    q = pcbnew.VECTOR2I(int(a.x + math.cos(ang) * IU(rr)), int(a.y + math.sin(ang) * IU(rr)))
                    seg = pcbnew.SHAPE_SEGMENT(a, q, IU(STUB_W))
                    box = pcbnew.BOX2I(pcbnew.VECTOR2I(min(a.x, q.x), min(a.y, q.y)),
                                       pcbnew.VECTOR2L(abs(a.x - q.x) + 1, abs(a.y - q.y) + 1))
                    if not board.via_ok(q, p.GetNetCode()) or not board.clear(seg, box, side, p.GetNetCode(), CLR):
                        continue
                    if any(o.GetNumber() and o.GetNetCode() != p.GetNetCode() and o.IsOnLayer(side)
                           and o.GetEffectiveShape(side).Collide(seg, IU(CLR) - 1) for o in f.Pads()):
                        continue
                    if any(hn != p.GetNetCode() and seg.Collide(pcbnew.SHAPE_CIRCLE(hp, hr), IU(HOLE_CLR) - 1)
                           for hp, hr, hn in board.holes):
                        continue
                    add_via(b, board, q, p.GetNet())
                    add_stub(b, board, a, q, p.GetNet(), side)
                    done = True
                    break
                if done:
                    break
            n["beside" if done else "none"] += 1
            if not done:
                print(f"  NO TAP for {f.GetReference()}.{p.GetNumber()} ({net(p)})")
    print(f"phase5_power: pad taps: {n}")


def l3_pour(b):
    old = [z for z in list(b.Zones()) if not z.GetIsRuleArea() and z.IsOnLayer(L3) and net(z) == "+1V8"]
    tmpl = max(old, key=lambda z: z.Outline().Area())
    gnd = next(z for z in list(b.Zones()) if z.IsOnLayer(pcbnew.In1_Cu) and net(z) == "GND")   # board-size outline
    o = tmpl.Outline()                 # the largest keeps its settings and takes the board outline
    o.RemoveAllContours()
    o.Append(gnd.Outline())
    tmpl.SetAssignedPriority(0)
    for z in old:
        if z is not tmpl:
            b.Delete(z)
    print(f"phase5_power: L3 +1V8: {len(old)} Agilex zones replaced by one board-size pour")


def main(src, dst):
    # KiCad 10's Python: zone access fails after items are removed in the same session, so each removing step
    # saves and the next one reloads
    b = pcbnew.LoadBoard(src)
    dead_copper(b)
    b.Save(dst)
    b = pcbnew.LoadBoard(dst)
    l3_pour(b)
    b.Save(dst)
    b = pcbnew.LoadBoard(dst)
    board = Board(b)
    for f in b.GetFootprints():
        board.add_footprint(f)
    stitch(b, board)
    taps(b, board)
    b.Save(dst)


if __name__ == "__main__":
    main(*sys.argv[1:3])
