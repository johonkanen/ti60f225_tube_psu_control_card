"""Phase 5 routing: the short supply stubs the planes leave open, drawn from KiCad's own list of unconnected items.

    $KICAD_MOUNT/bin/python3.11 -I tools/phase5_stubs.py IN.kicad_pcb DRC.json OUT.kicad_pcb

DRC.json: kicad-cli pcb drc --refill-zones --format json of IN (tools/phase5_check.sh leaves one). For every
unconnected pair of a plane net (GND, +1V8, +3V3, +0V95) whose two ends lie on one outer layer no more than MAXLEN
apart (a translator's supply pin and its cap via, two pins of one supply side by side, a GND pin and its via), a
STUB_W track joins them: straight, or as an L when the straight line would come too close to other copper.
The router is not used for these: with a plane net in its list it joins every pad of the net by tracks. Pairs
between zone islands and pairs that need a via are reported and left.
"""
import json
import math
import re
import sys

import pcbnew

IU, MM = pcbnew.FromMM, pcbnew.ToMM
NETS = {"GND", "+1V8", "+3V3", "+0V95"}
STUB_W, CLR, HOLE_CLR, MAXLEN = 0.15, 0.125, 0.2, 3.0
LAYERS = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu}


def parse(item):
    d = item["description"]
    m = re.search(r"\[([^\]]+)\]", d)
    kind = d.split(" ", 1)[0]
    layers = [n for n in LAYERS if re.search(rf"\b{re.escape(n)}\b", d)]
    return kind, m.group(1) if m else None, layers, (item["pos"]["x"], item["pos"]["y"])


def anchor(b, kind, net, layers, pos, other):
    """The point of the item to draw to: pad or via centre, or the track's end nearest the other item."""
    if kind != "Track":
        return pos
    best = None
    for t in b.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T or t.GetNetname() != net or b.GetLayerName(t.GetLayer()) not in layers:
            continue
        ends = [(MM(q.x), MM(q.y)) for q in (t.GetStart(), t.GetEnd())]
        if min(math.dist(e, pos) for e in ends) < 0.02:
            for e in ends:
                if best is None or math.dist(e, other) < math.dist(best, other):
                    best = e
    return best or pos


def obstacles(b, layer):
    out = []
    for t in b.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            out.append((t.GetEffectiveShape(layer), t.GetNetCode(), CLR))
            out.append((pcbnew.SHAPE_CIRCLE(t.GetPosition(), t.GetDrillValue() // 2), t.GetNetCode(), HOLE_CLR))
        elif t.GetLayer() == layer:
            out.append((t.GetEffectiveShape(layer), t.GetNetCode(), CLR))
    for f in b.GetFootprints():
        for p in f.Pads():
            if p.IsOnLayer(layer):
                out.append((p.GetEffectiveShape(layer), p.GetNetCode(), CLR))
            if p.HasHole():
                out.append((pcbnew.SHAPE_CIRCLE(p.GetPosition(), p.GetDrillSizeX() // 2), p.GetNetCode(), HOLE_CLR))
    for z in b.Zones():
        if not z.GetIsRuleArea() and z.IsOnLayer(layer):
            out.append((z.Outline(), z.GetNetCode(), CLR))
    return out


def clear(obs, netcode, a, c):
    seg = pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(IU(a[0]), IU(a[1])), pcbnew.VECTOR2I(IU(c[0]), IU(c[1])), IU(STUB_W))
    return not any(n != netcode and seg.Collide(sh, IU(clr) - 1) for sh, n, clr in obs)


def main(src, drc, dst):
    b = pcbnew.LoadBoard(src)
    report = json.load(open(drc))
    obs = {}
    done = left = 0
    for u in report.get("unconnected_items", []):
        (k1, net, l1, p1), (k2, _, l2, p2) = (parse(i) for i in u["items"][:2])
        if net not in NETS:
            continue
        common = [n for n in l1 if n in l2]
        if "Zone" in (k1, k2) or not common:
            print(f"  left: {net} {u['items'][0]['description'][:50]} | {u['items'][1]['description'][:50]}")
            left += 1
            continue
        lname = common[0] if len(common) == 1 else ("F.Cu" if k1 == "Via" and k2 == "Via" else common[0])
        layer = LAYERS[lname]
        a, c = anchor(b, k1, net, l1, p1, p2), anchor(b, k2, net, l2, p2, p1)
        if math.dist(a, c) > MAXLEN:
            print(f"  left (too far, {math.dist(a, c):.1f} mm): {net} at ({a[0]:.2f}, {a[1]:.2f}) - ({c[0]:.2f}, {c[1]:.2f})")
            left += 1
            continue
        if layer not in obs:
            obs[layer] = obstacles(b, layer)
        nc = b.GetNetcodeFromNetname(net)
        for pts in ([a, c], [a, (a[0], c[1]), c], [a, (c[0], a[1]), c]):
            if all(clear(obs[layer], nc, s, e) for s, e in zip(pts, pts[1:])):
                for s, e in zip(pts, pts[1:]):
                    t = pcbnew.PCB_TRACK(b)
                    t.SetStart(pcbnew.VECTOR2I(IU(s[0]), IU(s[1])))
                    t.SetEnd(pcbnew.VECTOR2I(IU(e[0]), IU(e[1])))
                    t.SetWidth(IU(STUB_W))
                    t.SetLayer(layer)
                    t.SetNetCode(nc)
                    b.Add(t)
                    obs[layer].append((t.GetEffectiveShape(layer), nc, CLR))
                done += 1
                break
        else:
            print(f"  left (no clear path): {net} on {lname} ({a[0]:.2f}, {a[1]:.2f}) - ({c[0]:.2f}, {c[1]:.2f})")
            left += 1
    b.Save(dst)
    print(f"phase5_stubs: {done} supply stubs drawn, {left} pairs left")


if __name__ == "__main__":
    main(*sys.argv[1:4])
