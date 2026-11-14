"""Phase 5, step 2: floorplan placements that follow from the Ti60's rotation (absolute poses, rerunnable).

    $KICAD_MOUNT/bin/python3.11 -I tools/phase5_place.py hardware/control_card.kicad_pcb

- U1 sits at 180 deg (tools/phase5_sync.py): bank 1A (flash) and the JTAG balls are in the top-right corner of
  the package, next to J2; banks 4A/4B (HyperRAM since the 180 deg experiment) face north, 3A/3B (ADC) west,
  2A/2B (translator inputs) south. So the flash U7 stays in the east memory place of the Agilex board and the
  HyperRAM U9 in the west one (SWAP_MEMORIES False; at U1 -90 deg they traded places). The HyperRAM's
  decoupling and reset pull-up sit on VCC/VSS ball pairs of their memory.
- U9 sits at 90 deg, its data balls nearest to the FPGA balls it goes to.
- The four SN74AVC4T774 translators sit in a row on the top side between the BGA and J1, A side (1.8 V,
  pins 1-4) facing the FPGA, B side (3.3 V, pins 9-12) facing J1, ordered like their J1 pins.
"""
import sys

import pcbnew

MM = pcbnew.FromMM
SWAP_MEMORIES = False       # True: HyperRAM east, flash west (the layout with U1 at -90 deg)


def fp(board, ref):
    f = board.FindFootprintByReference(ref)
    if f is None:
        sys.exit(f"{ref} not on the board")
    return f


def pad_xy(f, num):
    p = [p for p in f.Pads() if p.GetNumber() == num][0].GetPosition()
    return pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)


def put(f, x, y, rot, bottom):
    if f.IsFlipped() != bottom:
        f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    f.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
    f.SetOrientationDegrees(rot)


def cap_on_pair(board, cap, mem, pad_a, pad_b):
    """0402 on the bottom, centred between two balls of a memory, along the line between them."""
    (xa, ya), (xb, yb) = pad_xy(fp(board, mem), pad_a), pad_xy(fp(board, mem), pad_b)
    rot = 0 if abs(xa - xb) > abs(ya - yb) else 90
    put(fp(board, cap), (xa + xb) / 2, (ya + yb) / 2, rot, True)
    c = fp(board, cap)
    # pad 1 of the cap on the supply ball
    p1 = pad_xy(c, "1")
    supply = (xa, ya) if [p for p in fp(board, mem).Pads() if p.GetNumber() == pad_a][0].GetNetname() != "GND" else (xb, yb)
    if (p1[0] - supply[0]) ** 2 + (p1[1] - supply[1]) ** 2 > 0.1:
        c.SetOrientationDegrees(rot + 180)


def courtyard(f):
    c = f.GetCourtyard(pcbnew.B_CrtYd if f.IsFlipped() else pcbnew.F_CrtYd)
    return c.BBox() if not c.IsEmpty() else f.GetBoundingBox(False)


def free_spot(board, f, near, pad, bottom, step=0.25, rmax=4.0):
    """Move f to the free spot (no courtyard overlap on its side, inside the board) nearest a pad of `near`."""
    x0, y0 = pad_xy(near, pad)
    edge = board.GetBoardEdgesBoundingBox()
    edge.Inflate(-MM(0.4))
    others = [courtyard(o) for o in board.GetFootprints() if o is not f and o.IsFlipped() == bottom]
    cands = sorted(((dx * step, dy * step) for dx in range(-int(rmax / step), int(rmax / step) + 1)
                    for dy in range(-int(rmax / step), int(rmax / step) + 1)), key=lambda d: d[0] ** 2 + d[1] ** 2)
    for dx, dy in cands:
        for rot in (0, 90):
            put(f, x0 + dx, y0 + dy, rot, bottom)
            c = courtyard(f)
            if edge.Contains(c) and not any(c.Intersects(o) for o in others):
                return
    sys.exit(f"no free spot for {f.GetReference()} near {near.GetReference()}.{pad}")


def main(path):
    b = pcbnew.LoadBoard(path)
    u7, u9 = fp(b, "U7"), fp(b, "U9")
    x7, x9 = pcbnew.ToMM(u7.GetPosition().x), pcbnew.ToMM(u9.GetPosition().x)
    if SWAP_MEMORIES and x9 < x7:   # first run: swap (HyperRAM to the right, over bank 1B), moving each memory's vias with it
        dx = x7 - x9
        y = pcbnew.ToMM(u9.GetPosition().y)
        # via-in-pads move with their memory; the memories' other old fan-out copper is dropped (redone later)
        moves, drop = [], {}
        for t in b.GetTracks():
            for mem, d in ((u9, dx), (u7, -dx)):
                box = mem.GetBoundingBox(False)
                if not (box.Contains(t.GetStart()) or box.Contains(t.GetEnd())):
                    continue
                if t.Type() == pcbnew.PCB_VIA_T and any(p.GetPosition() == t.GetPosition() for p in mem.Pads()):
                    moves.append((t, d))
                else:
                    drop[t.m_Uuid.AsString()] = t
        for t, d in moves:
            t.Move(pcbnew.VECTOR2I(MM(d), 0))
        for t in drop.values():
            b.Remove(t)
        put(u9, x7, y, u9.GetOrientationDegrees(), False)
        put(u7, x9, y, u7.GetOrientationDegrees(), False)
        print(f"swapped U7/U9: {len(moves)} via-in-pads moved with them, {len(drop)} other tracks/vias dropped")
    # HyperRAM at 90 deg: its DQ columns (D, E) on the east side, over the FPGA's north-edge balls of banks 4A/4B
    # (its plane balls get their via-in-pad in phase5_vias.py)
    u9.SetOrientationDegrees(90)
    if not SWAP_MEMORIES:   # the memories' old Agilex copper goes, but for a via in a ball of its own net
        drop = {}
        for mem in (u7, u9):
            box = mem.GetBoundingBox(False)
            for t in b.GetTracks():
                via = t.Type() == pcbnew.PCB_VIA_T
                if not (box.Contains(t.GetStart()) or box.Contains(t.GetEnd())):
                    continue
                if via and any(p.GetPosition() == t.GetPosition() and p.GetNetCode() == t.GetNetCode() for p in mem.Pads()):
                    continue
                drop[t.m_Uuid.AsString()] = t
        for t in drop.values():
            b.Remove(t)
        print(f"U7/U9 stay: {len(drop)} old tracks/vias under them dropped")
    # memory decoupling on VCC/VSS ball pairs (HyperRAM: B3/B4, C1/D1, E4/E5; flash: B3/B4)
    cap_on_pair(b, "C51", "U9", "B4", "B3")
    cap_on_pair(b, "C53", "U9", "D1", "C1")
    cap_on_pair(b, "C52", "U9", "E4", "E5")
    flash_cap = [f.GetReference() for f in b.GetFootprints() if f.GetReference().startswith("C")
                 and {p.GetNetname() for p in f.Pads()} == {"+1V8", "GND"}
                 and f.GetSheetname().startswith("Configuration")]
    cap_on_pair(b, flash_cap[0], "U7", "B4", "B3")

    # R24 (HyperRAM RESET# pull-up), R59 (flash RESET#), R57 (FLASH_IO2) and R58 (FLASH_IO3) go to the bottom, onto
    # the via in their memory ball (tools/phase5_decaps.py). R54 (CS#, the western flash line) sits on top just
    # south of the flash body, west of the bundle of flash lines
    for ref, mem_pad, dx in (("R54", "B2", -1.15),):
        r = fp(b, ref)
        x0, _ = pad_xy(u7, mem_pad)
        y0 = max(pad_xy(u7, p.GetNumber())[1] for p in u7.Pads()) + 2.0
        put(r, x0 + dx, y0, 0, False)
        sig = next(p for p in r.Pads() if p.GetNumber() and p.GetNetname() not in ("+1V8", "GND"))
        if (pcbnew.ToMM(sig.GetPosition().x) - (x0 + dx)) * dx > 0:    # the signal pad faces the flash lines
            r.SetOrientationDegrees(180)
    # The oscillator with its supply filter and series resistor, and the HyperRAM's bulk cap, sat under the two
    # memories on the bottom, where their supply vias now meet the memories' F.Cu escapes (and the oscillator's
    # output pad the flash RESET# ball). The oscillator goes between the memories and the BGA, east of the
    # HyperRAM fan and west of the flash lines, with R25 at the CLK100M ball (P2, the BGA's north-east corner);
    # its bead and cap just north of it, the bulk cap under the HyperRAM's west edge. Old copper on them goes.
    osc = [("X1", 94.9, 104.3, "1", (-1, -1)), ("R25", 96.55, 107.1, "1", (0, -1)), ("C54", 93.6, 101.95, "1", (-1, 0)),
           ("FB5", 92.9, 99.9, "1", (0, -1)), ("C75", 85.0, 100.4, "1", (0, -1))]
    nets = set()
    for ref, x, y, first, (sx, sy) in osc:
        f = fp(b, ref)
        nets |= {p.GetNetCode() for p in f.Pads() if p.GetNetname() not in ("GND", "+1V8")}
        for rot in (0, 90, 180, 270):       # pad `first` on the side (sx, sy) of the part
            put(f, x, y, rot, True)
            px, py = pad_xy(f, first)
            if (sx == 0 or (px - x) * sx > 0.05) and (sy == 0 or (py - y) * sy > 0.05):
                break
        else:
            sys.exit(f"{ref}: no rotation puts pad {first} on side {(sx, sy)}")
    old = [tr for tr in b.GetTracks() if tr.GetNetCode() in nets]
    under = [tr for tr in b.GetTracks() if tr.Type() == pcbnew.PCB_VIA_T and tr.GetNetname() in ("GND", "+1V8")
             and 84.0 < pcbnew.ToMM(tr.GetPosition().x) < 102.5 and pcbnew.ToMM(tr.GetPosition().y) < 102.5
             and not any(p.GetPosition() == tr.GetPosition() for m in (u7, u9) for p in m.Pads())]
    for tr in {t.m_Uuid.AsString(): t for t in old + under}.values():
        b.Remove(tr)
    print(f"oscillator group and C75 moved: {len(old)} old tracks of their nets and {len(under)} supply vias under "
          f"the memories dropped")

    # translators: row between the BGA (south edge y 118) and J1 (pads from y 125.8)
    xl = sorted((f for f in b.GetFootprints() if str(f.GetFPID().GetLibItemName()).startswith("UQFN-16")
                 and any(p.GetNetname() == "XLAT_OE_N" for p in f.Pads())), key=lambda f: f.GetReference())
    order = []
    for f in xl:   # J1 pin of channel B1 orders the row: lowest J1 pin to the east, next to J1 pin 1
        b1 = [p for p in f.Pads() if p.GetNumber() == "12"][0].GetNetname().split("/")[-1]
        j1 = [p for p in fp(b, "J1").Pads() if p.GetNetname().split("/")[-1] == b1][0]
        order.append((-pcbnew.ToMM(j1.GetPosition().x), f))
    for i, (_, f) in enumerate(sorted(order, key=lambda t: t[0])):
        put(f, 104.5 - 4.0 * i, 122.5, 0, False)
        # rotate until pins 1-4 (A side) face north
        for rot in (0, 90, 180, 270):
            f.SetOrientationDegrees(rot)
            ay = sum(pad_xy(f, str(n))[1] for n in range(1, 5)) / 4
            by = sum(pad_xy(f, str(n))[1] for n in range(9, 13)) / 4
            if ay < by - 0.5:
                break
    # copper left under a moved part on a pad of another net (old power copper in the translator row)
    stale = {}
    for t in b.GetTracks():
        via = t.Type() == pcbnew.PCB_VIA_T
        for f in b.GetFootprints():
            for p in f.Pads():
                for pt in (t.GetStart(), t.GetEnd()):
                    if p.GetNetCode() != t.GetNetCode() and (via or p.IsOnLayer(t.GetLayer())) and p.HitTest(pt):
                        stale[t.m_Uuid.AsString()] = t
                if not via and p.IsOnLayer(t.GetLayer()) and p.GetNetCode() != t.GetNetCode() \
                        and t.GetEffectiveShape().Collide(p.GetEffectiveShape(t.GetLayer()), 0):
                    stale[t.m_Uuid.AsString()] = t
    for t in stale.values():
        b.Remove(t)
    print(f"deleted {len(stale)} tracks/vias touching a pad of another net")
    b.Save(path)
    for r in ["U7", "U9", "R24", "C51", "C52", "C53", flash_cap[0]] + [f.GetReference() for f in xl]:
        f = fp(b, r)
        print(f"{r:5} {pcbnew.ToMM(f.GetPosition().x):7.2f} {pcbnew.ToMM(f.GetPosition().y):7.2f} "
              f"{f.GetOrientationDegrees():6.1f} {'B' if f.IsFlipped() else 'F'}")


if __name__ == "__main__":
    main(sys.argv[1])
