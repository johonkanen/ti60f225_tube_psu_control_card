"""Phase 5, step 1: bring the Ti60F225 schematic into the routed Agilex board.

    kicad-cli sch export netlist --format kicadsexpr -o /tmp/ti60.net hardware/control_card.kicad_sch
    $KICAD_MOUNT/bin/python3.11 -I tools/phase5_sync.py OLD_NETLIST NEW_NETLIST hardware/control_card.kicad_pcb [--dry-run]

OLD_NETLIST is the Agilex schematic's netlist (git show 43b9ec7 / ad36d00), used to know which copper
belonged to the FPGA. Like Update PCB from Schematic with "re-link by reference", plus copper cleanup:
- footprints no longer in the schematic are deleted; new ones are added, parked east of the board;
  U1 becomes control_card:Efinix_F225, centred where the Agilex was, rotated 90 deg clockwise
  (banks 1A/1B north to the memories, 3A/3B and HVIO TR/BR south to J1, 4A/4B west to the ADCs);
- pad nets, values and fields come from the new netlist; footprints keep their symbol links;
- renamed nets (+0V75 -> +0V95 etc.) are renamed on tracks, vias and zones;
- tracks and vias are deleted when their net is gone, when their net was an FPGA signal (it is rerouted),
  when they lie inside the old BGA area, or when they end on a pad of a deleted footprint;
- zones are deleted when their net is gone or they served a deleted buck cell.
"""
import os
import re
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_LIBS = {"control_card": os.path.join(HERE, "..", "hardware", "lib", "control_card.pretty")}
RENAMES = {"+0V75": "+0V95", "/Power/FB_0V75": "/Power/FB_0V95", "/Power/SW_0V75": "/Power/SW_0V95",
           "/Power/EN_0V75": "/Power/EN_0V95", "/Power/PG_0V75": "/Power/PG_0V95", "+1V8_HR": "+1V8"}
POWER = {"GND", "+5V", "+3V3", "+1V8", "+0V95", "+3V3A"}
U1_POS = (92.0, 113.0)
U1_ROT = -90.0
MM = pcbnew.FromMM


def blocks(text, head):
    for m in re.finditer(r"\(%s\b" % head, text):
        depth, i, in_str = 0, m.start(), False
        while True:
            c = text[i]
            if in_str:
                if c == "\\":
                    i += 1
                elif c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    yield text[m.start():i + 1]
                    break
            i += 1


def parse(path):
    t = open(path).read()
    comps = []
    for b in blocks(t[t.index("(components"):t.index("(libparts")], "comp"):
        g = lambda k: (re.search(r'\(%s "([^"]*)"\)' % k, b) or [None, ""])[1]   # noqa: E731
        sp = re.search(r'\(sheetpath\s*\(names "[^"]*"\)\s*\(tstamps "([^"]*)"\)\s*\)', b)
        ts = re.search(r'\(tstamps "([^"]+)"', b[sp.end():]).group(1)
        fields = {n: v for n, v in re.findall(r'\(field\s*\(name "([^"]+)"\)\s*(?:"([^"]*)")?\s*\)', b)}
        comps.append(dict(ref=g("ref"), value=g("value"), footprint=g("footprint"), path=sp.group(1) + ts,
                          sheetname=re.search(r'\(names "([^"]*)"\)', b).group(1), fields=fields))
    nets = {}
    for b in blocks(t[t.index("(nets"):], "net"):
        name = re.search(r'\(name "([^"]*)"\)', b).group(1)
        nets[name] = re.findall(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', b)
    return comps, nets


def load_fp(lib_id):
    lib, name = lib_id.split(":")
    path = PROJECT_LIBS.get(lib) or os.path.join(os.environ["KICAD_MOUNT"], "share", "kicad", "footprints", lib + ".pretty")
    fp = pcbnew.FootprintLoad(path, name)
    if fp is None:
        raise SystemExit(f"footprint {lib_id} not found in {path}")
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def main(old_net, new_net, pcb_path, dry):
    _, old_nets = parse(old_net)
    comps, nets = parse(new_net)
    board = pcbnew.LoadBoard(pcb_path)
    have = {fp.GetReference(): fp for fp in board.GetFootprints()}
    want = {c["ref"]: c for c in comps if c["footprint"] and not c["ref"].startswith("#")}

    # FPGA signal nets of the Agilex board (copper to be rerouted)
    fpga_nets = {n for n, nodes in old_nets.items() if any(r == "U1" for r, _ in nodes)} - set(RENAMES) - POWER
    old_u1 = have["U1"]
    area = old_u1.GetCourtyard(pcbnew.F_CrtYd).BBox() if not old_u1.GetCourtyard(pcbnew.F_CrtYd).IsEmpty() \
        else old_u1.GetBoundingBox(False)
    area.Inflate(MM(0.3))

    # footprints to delete (gone from the schematic, or footprint changed)
    gone = [r for r in have if r not in want]
    changed = [r for r in have if r in want and str(have[r].GetFPID().GetLibItemName()) != want[r]["footprint"].split(":")[1]]
    removed_pads = []
    for r in gone + changed:
        for p in have[r].Pads():
            removed_pads.append(p)

    def on_removed_pad(t, pt):
        via = t.Type() == pcbnew.PCB_VIA_T
        for p in removed_pads:
            if p.HitTest(pt) and (via or p.IsOnLayer(t.GetLayer())):
                return True
        return False

    new_names = set(nets)
    # nets whose label changed scope (global <-> local) only change their sheet prefix: rename by bare name
    bare = {}
    for n in new_names:
        bare.setdefault(n.split("/")[-1], []).append(n)
    for o in old_nets:
        if o not in new_names and o not in RENAMES and len(bare.get(o.split("/")[-1], [])) == 1:
            RENAMES[o] = bare[o.split("/")[-1]][0]
    print("renamed nets:", ", ".join(f"{o} -> {n}" for o, n in sorted(RENAMES.items())))
    stats = dict(renamed=0, gone_net=0, fpga=0, area=0, removed_pad=0)
    to_delete = []
    gone_nets = {}
    for t in board.GetTracks():
        o = t.GetNetname()
        n = RENAMES.get(o, o)
        if o in fpga_nets:
            stats["fpga"] += 1
            to_delete.append(t)
            continue
        if n != o:
            stats["renamed"] += 1
        if n and n not in new_names:
            stats["gone_net"] += 1
            gone_nets[n] = gone_nets.get(n, 0) + 1
            to_delete.append(t)
        elif False:
            stats["fpga"] += 1
            to_delete.append(t)
        elif area.Contains(t.GetStart()) or area.Contains(t.GetEnd()):
            stats["area"] += 1
            to_delete.append(t)
        elif on_removed_pad(t, t.GetStart()) or on_removed_pad(t, t.GetEnd()):
            stats["removed_pad"] += 1
            to_delete.append(t)
    zones_del, zones_ren = [], []
    gone_boxes = [have[r].GetBoundingBox(False) for r in gone]
    for z in board.Zones():
        n = z.GetNetname()
        n2 = RENAMES.get(n, n)
        zb = z.GetBoundingBox()
        if n2 and n2 not in new_names:
            zones_del.append((z, f"net {n} gone"))
        elif z.GetLayer() == pcbnew.B_Cu and n2 in ("GND", "+5V", "+1V8") and any(zb.Intersects(g) for g in gone_boxes) \
                and not any(zb.Intersects(have[r].GetBoundingBox(False)) for r in ("U2", "U3", "U4")):
            zones_del.append((z, f"{n} pour of a deleted buck cell"))
        elif n in RENAMES and not (n == "+1V8_HR" and z.GetLayer() == pcbnew.B_Cu):
            zones_ren.append((z, n2))
        elif n == "+1V8_HR":
            zones_del.append((z, "+1V8_HR output pour of the deleted U18 cell"))

    print("footprints deleted:", " ".join(sorted(gone)))
    print("footprints replaced:", " ".join(sorted(changed)))
    print("footprints added:", " ".join(sorted(r for r in want if r not in have)))
    print("copper deleted:", stats, "of", len(list(board.GetTracks())), "tracks/vias")
    print("  nets gone:", ", ".join(f"{n} {c}" for n, c in sorted(gone_nets.items(), key=lambda x: -x[1])))
    for z, why in zones_del:
        print(f"zone deleted: {z.GetNetname()} on {board.GetLayerName(z.GetLayer())} ({why})")
    for z, n2 in zones_ren:
        print(f"zone renamed: {z.GetNetname()} -> {n2} on {board.GetLayerName(z.GetLayer())}")
    if dry:
        return

    for t in to_delete:
        board.Remove(t)
    for z, _ in zones_del:
        board.Remove(z)
    for r in gone + changed:
        board.Remove(have[r])

    def net(name):
        ni = board.FindNet(name)
        if ni is None:
            ni = pcbnew.NETINFO_ITEM(board, name)
            board.Add(ni)
        return ni
    for t in board.GetTracks():
        if t.GetNetname() in RENAMES:
            t.SetNet(net(RENAMES[t.GetNetname()]))
    for z, n2 in zones_ren:
        z.SetNet(net(n2))

    have = {fp.GetReference(): fp for fp in board.GetFootprints()}
    bb = board.GetBoardEdgesBoundingBox()
    park_x, park_y, added = bb.GetRight() + MM(8), bb.GetTop(), 0
    for ref, c in sorted(want.items()):
        fp = have.get(ref)
        if fp is None:
            fp = load_fp(c["footprint"])
            fp.SetReference(ref)
            board.Add(fp)
            if ref == "U1":
                fp.SetPosition(pcbnew.VECTOR2I(MM(U1_POS[0]), MM(U1_POS[1])))
                fp.SetOrientationDegrees(U1_ROT)
            else:
                fp.SetPosition(pcbnew.VECTOR2I(park_x + MM(6) * (added // 30), park_y + MM(1.6) * (added % 30)))
                added += 1
        fp.SetValue(c["value"])
        for k in ("LCSC", "MPN", "Description", "Group"):
            v = c["fields"].get(k, "")
            if not v and (k == "Description" or k not in c["fields"]):
                continue
            fp.SetField(k, v)
            fld = fp.GetField(k)
            if fld is not None:
                fld.SetVisible(False)
                fld.SetLayer(pcbnew.F_Fab)
        fp.SetPath(pcbnew.KIID_PATH(c["path"]))
        fp.SetSheetname(c["sheetname"].strip("/"))
        fp.Reference().SetVisible(False)   # as on the Agilex board: references on Fab only
    refs = {fp.GetReference(): fp for fp in board.GetFootprints()}
    for fp in refs.values():
        for pad in fp.Pads():
            pad.SetNetCode(0)
    missing = []
    for name, nodes in nets.items():
        ni = net(name)
        for ref, pin in nodes:
            pads = [p for p in refs[ref].Pads() if p.GetNumber() == pin] if ref in refs else []
            if not pads:
                missing.append(f"{ref}.{pin}")
            for p in pads:
                p.SetNet(ni)
    # ADS7056 DVDD (pin 4) and its 1 uF moved from +3V3 to +1V8: drop the +3V3 taps beside those pads
    dvdd = [p for r, n in (("U12", "4"), ("U15", "4"), ("C59", "1"), ("C64", "1")) for p in refs[r].Pads()
            if p.GetNumber() == n]
    old_tap = []
    for t in board.GetTracks():
        if t.GetNetname() == "+3V3":
            for p in dvdd:
                d = min((pt - p.GetPosition()).EuclideanNorm() for pt in (t.GetStart(), t.GetEnd()))
                if d < MM(0.6):
                    old_tap.append(t)
    for t in {x.m_Uuid.AsString(): x for x in old_tap}.values():
        board.Remove(t)
    # copper that now ends on a pad of another net (e.g. the 4051's VEE ties to GND on the TMUX1308's N.C. pin 7)
    stale = []
    for t in board.GetTracks():
        via = t.Type() == pcbnew.PCB_VIA_T
        for pt in (t.GetStart(), t.GetEnd()):
            for fp in refs.values():
                for p in fp.Pads():
                    if p.HitTest(pt) and (via or p.IsOnLayer(t.GetLayer())) and p.GetNetCode() != t.GetNetCode():
                        stale.append(t)
    uniq = {t.m_Uuid.AsString(): t for t in stale}
    for t in uniq.values():
        board.Remove(t)
    print(f"deleted {len(uniq)} tracks/vias ending on a pad of another net")
    board.BuildConnectivity()
    board.Save(pcb_path)
    print(f"saved: {len(want)} footprints ({added} parked), {len(nets)} nets")
    if missing:
        print("pads not found:", " ".join(missing[:40]))


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    main(a[0], a[1], a[2], "--dry-run" in sys.argv)
