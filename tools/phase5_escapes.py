"""Where each U1 signal ball's fan-out escape ends (for planning pin swaps on a placed, fanned-out board).

    tools/kpy.sh tools/phase5_escapes.py PLACED.kicad_pcb [BANK...]

Prints ball, bank, net, the escape's outer end (the point of the net's copper farthest from U1's centre, among
the tracks that hang on the ball), its side of the package and its layers. Sorted by side, then along the edge.
Balls without a net are listed with the position of the ball itself (no escape is drawn for them).
"""
import csv
import os
import sys

import pcbnew

MM = pcbnew.ToMM


def main():
    b = pcbnew.LoadBoard(sys.argv[1])
    banks = set(sys.argv[2:])
    here = os.path.dirname(os.path.abspath(__file__))
    pins = {r["ball"]: r for r in csv.DictReader(open(os.path.join(here, "..", "reference", "ti60f225_pinout.csv")))}
    u1 = b.FindFootprintByReference("U1")
    c = u1.GetPosition()
    rows = []
    for p in u1.Pads():
        r = pins[p.GetNumber()]
        if r["type"] not in ("HSIO", "HVIO") or (banks and r["bank"] not in banks):
            continue
        pos = p.GetPosition()
        net = p.GetNetname()
        end, layers, via = pos, set(), False
        if not net.startswith("unconnected"):
            tr = [t for t in b.GetTracks() if t.GetNetCode() == p.GetNetCode()]
            seen, todo = set(), [pos]
            while todo:
                q = todo.pop()
                for t in tr:
                    if id(t) in seen:
                        continue
                    if t.Type() == pcbnew.PCB_VIA_T:
                        if t.GetPosition() == q:
                            seen.add(id(t)); via = True
                        continue
                    for a, e in ((t.GetStart(), t.GetEnd()), (t.GetEnd(), t.GetStart())):
                        if a == q:
                            seen.add(id(t)); layers.add(b.GetLayerName(t.GetLayer()).split(".")[0]); todo.append(e)
                            if (e.x - c.x) ** 2 + (e.y - c.y) ** 2 > (end.x - c.x) ** 2 + (end.y - c.y) ** 2:
                                end = e
        dx, dy = MM(end.x - c.x), MM(end.y - c.y)
        side = ("E" if dx > 0 else "W") if abs(dx) > abs(dy) else ("S" if dy > 0 else "N")
        rows.append((side, MM(end.x) if side in "NS" else MM(end.y), p.GetNumber(), r["bank"], net.split("/")[-1],
                     MM(end.x), MM(end.y), "+".join(sorted(layers)) + ("+via" if via else "")))
    for side, _, ball, bank, net, x, y, lay in sorted(rows):
        print(f"{side} {ball:4} {bank:3} {net:24} {x:8.3f} {y:8.3f} {lay}")


if __name__ == "__main__":
    main()
