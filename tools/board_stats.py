"""Board statistics for the routing review: tracks and vias per layer, signal vias, B.Cu signal copper.

    kicad python -I tools/board_stats.py BOARD.kicad_pcb [--nets]
"""
import collections
import sys

import pcbnew

PLANE = {"GND", "+1V8", "+0V95", "+3V3", "+5V", "+3V3A", "+12V"}


def is_signal(net):
    return bool(net) and net not in PLANE and "VCCA" not in net and "/Power/" not in net


def main():
    b = pcbnew.LoadBoard(sys.argv[1])
    per_layer = collections.Counter()
    vias = collections.Counter()
    bcu = collections.Counter()
    for t in b.GetTracks():
        n = t.GetNetname()
        if t.Type() == pcbnew.PCB_VIA_T:
            vias[n] += 1
        else:
            per_layer[t.GetLayerName()] += 1
            if t.GetLayer() == pcbnew.B_Cu:
                bcu[n] += pcbnew.ToMM(t.GetLength())
    sig = {n: c for n, c in vias.items() if is_signal(n)}
    print("tracks per layer:", dict(per_layer))
    print("vias:", sum(vias.values()), "signal vias:", sum(sig.values()), "on", len(sig), "nets")
    print("B.Cu signal track mm:", round(sum(v for n, v in bcu.items() if is_signal(n)), 2))
    if "--nets" in sys.argv:
        for n in sorted(set(sig) | {k for k in bcu if is_signal(k)}):
            print(f"  {n}: {sig.get(n, 0)} vias, B.Cu {bcu.get(n, 0):.2f} mm")


main()
