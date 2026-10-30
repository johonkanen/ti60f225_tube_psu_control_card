"""Edit the existing KiCad schematic sheets in the generator's drawing style.

The sheets come from the Agilex card's gen_schematic.py and were hand-edited
afterwards, so they are edited in place rather than regenerated. Style (as in
tools/schgen.py): every symbol pin has a 2.54 mm wire stub ending in a net
label (global label if the net is used on more than one sheet), unused pins
get a no-connect flag.

Operations:
- remove(ref): delete a symbol (all units) with its pin stubs, the labels at
  the stub ends and its no-connect flags;
- place(...): add a symbol unit with stubs, labels and no-connects;
- relabel(old, new): rename a net on a sheet; relabel_pin(ref, pin, net)
  renames only the label on one pin's stub (net None = no-connect);
- set_props(ref, **props): change Value, LCSC, MPN, ...;
- normalize_labels(sheets): label vs global label by how many sheets use a net.

Pin geometry is checked against the existing sheets by check_geometry().
"""
import math
import re
import uuid
from pathlib import Path

from schgen import LibSymbol, _block_at, q, rnd, symbol_from_file, STUB

NS = uuid.UUID("7d0b1f8e-2c49-4f0a-9b67-5e3a1c2d4f60")


def uid(*parts):
    return str(uuid.uuid5(NS, "/".join(str(p) for p in parts)))


def top_items(text):
    """(start, end, kind) of every depth-1 item of a kicad_sch file."""
    out = []
    i = text.index("\n\t(", 0)
    while True:
        m = re.compile(r"\n\t\((\w+)").search(text, i)
        if not m:
            break
        s = m.start() + 2
        blk = _block_at(text, s)
        out.append((s, s + len(blk), m.group(1)))
        i = s + len(blk)
    return out


def xy(v):
    return (rnd(float(v[0])), rnd(float(v[1])))


class Sheet:
    def __init__(self, path, libs):
        self.path = Path(path)
        self.text = self.path.read_text()
        self.libs = libs          # lib_id -> LibSymbol, shared across sheets
        self.name = self.path.stem
        self._load_lib_symbols()
        self._path = next((d["path"] for _, _, d in self.symbols() if d["path"]), None)

    # ------------------------------------------------------------ parsing
    def items(self, kind=None):
        return [(s, e, k) for s, e, k in top_items(self.text) if kind is None or k == kind]

    def _load_lib_symbols(self):
        s = self.text.index("\n\t(lib_symbols") + 1
        blk = _block_at(self.text, s)
        for m in re.finditer(r'\n\t\t\(symbol "([^"]+)"', blk):
            lib_id = m.group(1)
            if lib_id not in self.libs:
                self.libs[lib_id] = LibSymbol(lib_id, _block_at(blk, m.start() + 1))

    def symbols(self):
        """[(start, end, dict)] for placed symbols."""
        out = []
        for s, e, k in self.items("symbol"):
            b = self.text[s:e]
            m = re.match(r'\(symbol\s*\(lib_id "([^"]+)"\)\s*\(at ([-\d.]+) ([-\d.]+) ([-\d.]+)\)', b)
            ref = re.search(r'\(property "Reference" "([^"]*)"', b).group(1)
            unit = int(re.search(r"\(unit (\d+)\)", b).group(1))
            mir = re.search(r"\n\t\t\(mirror (\w)\)", b)
            path = re.search(r'\(path "([^"]+)"', b)
            out.append((s, e, dict(lib_id=m.group(1), x=float(m.group(2)), y=float(m.group(3)),
                                   rot=float(m.group(4)), ref=ref, unit=unit, mirror=mir.group(1) if mir else None,
                                   path=path.group(1) if path else None,
                                   uuid=re.search(r'\n\t\t\(uuid "([^"]+)"\)', b).group(1),
                                   props=dict(re.findall(r'\(property "([^"]+)" "([^"]*)"', b)))))
        return out

    def pin_positions(self, sym):
        lib = self.libs[sym["lib_id"]]
        out = {}
        for n, p in lib.unit_pins(sym["unit"]).items():
            px, py = p["x"], p["y"]
            r = math.radians(sym["rot"])
            rx = px * math.cos(r) - py * math.sin(r)
            ry = px * math.sin(r) + py * math.cos(r)
            sx, sy = rx, -ry               # sheet orientation (y down)
            if sym["mirror"] == "x":
                sy = -sy
            elif sym["mirror"] == "y":
                sx = -sx
            ang = (p["angle"] + sym["rot"]) % 360
            out[n] = (rnd(sym["x"] + sx), rnd(sym["y"] + sy), ang)
        return out

    def wires(self):
        out = []
        for s, e, k in self.items("wire"):
            pts = re.findall(r"\(xy ([-\d.]+) ([-\d.]+)\)", self.text[s:e])
            out.append((s, e, xy(pts[0]), xy(pts[-1])))
        return out

    def labels(self):
        out = []
        for s, e, k in self.items():
            if k in ("label", "global_label"):
                b = self.text[s:e]
                m = re.match(r'\((?:global_)?label "((?:[^"\\]|\\.)*)"', b)
                at = re.search(r"\(at ([-\d.]+) ([-\d.]+) ([-\d.]+)\)", b)
                out.append((s, e, k, m.group(1), xy(at.groups()[:2]), int(float(at.group(3)))))
        return out

    def no_connects(self):
        return [(s, e, xy(re.search(r"\(at ([-\d.]+) ([-\d.]+)\)", self.text[s:e]).groups()))
                for s, e, k in self.items("no_connect")]

    def sheet_path(self):
        if not self._path:
            raise SystemExit(f"{self.name}: no symbol to take the instance path from")
        return self._path

    # ------------------------------------------------------------ editing primitives
    def _delete(self, spans):
        for s, e in sorted(set(spans), reverse=True):
            # remove the item and its leading newline+tab
            self.text = self.text[:s - 2] + self.text[e:]

    def _append(self, blocks):
        end = self.text.rindex("\n\t(embedded_fonts") if "\n\t(embedded_fonts" in self.text else self.text.rindex("\n)")
        self.text = self.text[:end] + "\n" + "\n".join(blocks) + self.text[end:]

    def _stub_spans(self, pins):
        """Spans of the stub wires, stub-end labels and no-connects at the given pin points."""
        wires = self.wires()
        labels = self.labels()
        ncs = self.no_connects()
        points = set(pins)
        spans, ends = [], []
        for s, e, a, b in wires:
            if a in points or b in points:
                spans.append((s, e))
                ends.append(b if a in points else a)
        remaining = [(a, b) for s, e, a, b in wires if (s, e) not in spans]
        for end in ends:
            if any(end in w for w in remaining):
                continue  # end joins other wiring: keep its label
            spans += [(s, e) for s, e, k, n, p, ang in labels if p == end]
        spans += [(s, e) for s, e, p in ncs if p in points]
        spans += [(s, e) for s, e, k, n, p, ang in labels if p in points]  # labels sitting on a pin
        return spans

    # ------------------------------------------------------------ operations
    def remove(self, ref):
        syms = [(s, e, d) for s, e, d in self.symbols() if d["ref"] == ref]
        if not syms:
            raise SystemExit(f"{self.name}: {ref} not found")
        pins = [p[:2] for _, _, d in syms for p in self.pin_positions(d).values()]
        spans = self._stub_spans(pins) + [(s, e) for s, e, _ in syms]
        self._delete(spans)
        return syms

    def stub_net(self, ref, pin):
        """Net label at the end of a pin's stub (None if no label)."""
        sym = [d for _, _, d in self.symbols() if d["ref"] == ref and pin in self.libs[d["lib_id"]].unit_pins(d["unit"])]
        x, y, _ = self.pin_positions(sym[0])[pin]
        for _, _, a, b in self.wires():
            if (x, y) in (a, b):
                end = b if a == (x, y) else a
                for _, _, k, n, p, _ in self.labels():
                    if p == end:
                        return n
        return None

    def relabel_pin(self, ref, pin, net):
        sym = [d for _, _, d in self.symbols() if d["ref"] == ref and pin in self.libs[d["lib_id"]].unit_pins(d["unit"])]
        if not sym:
            raise SystemExit(f"{self.name}: {ref}.{pin} not found")
        x, y, ang = self.pin_positions(sym[0])[pin]
        self._delete(self._stub_spans([(x, y)]))
        self._draw_pin(x, y, ang, net, f"{ref}.{pin}")

    def relabel(self, old, new):
        n = 0
        for s, e, k, name, p, ang in sorted(self.labels(), reverse=True):
            if name == old:
                b = self.text[s:e]
                b = b.replace(f'({k} {q(old)}', f'({k} {q(new)}', 1)
                self.text = self.text[:s] + b + self.text[e:]
                n += 1
        return n

    def set_props(self, ref, **props):
        for s, e, d in sorted(self.symbols(), key=lambda t: -t[0]):
            if d["ref"] != ref:
                continue
            b = self.text[s:e]
            for k, v in props.items():
                b, cnt = re.subn(r'(\(property %s )"[^"]*"' % re.escape(q(k)), lambda m: m.group(1) + q(v), b, count=1)
                if not cnt:
                    raise SystemExit(f"{ref}: no property {k}")
            self.text = self.text[:s] + b + self.text[e:]

    def ensure_lib_symbol(self, lib_id):
        s = self.text.index("\n\t(lib_symbols") + 1
        blk = _block_at(self.text, s)
        if f'(symbol "{lib_id}"' in blk:
            return
        body = "\n".join("\t" + ln for ln in self.libs[lib_id].block.split("\n"))
        new = blk[:-1].rstrip() + "\n" + body + "\n\t)"
        self.text = self.text[:s] + new + self.text[s + len(blk):]

    def _draw_pin(self, x, y, ang, net, key):
        blocks = []
        if net is None:
            blocks.append(f"\t(no_connect\n\t\t(at {x} {y})\n\t\t(uuid {q(uid(self.name, 'nc', key, x, y))})\n\t)")
        elif net != "":
            out = (ang + 180) % 360
            dx = round(math.cos(math.radians(out)), 6) * STUB
            dy = -round(math.sin(math.radians(out)), 6) * STUB
            x2, y2 = rnd(x + dx), rnd(y + dy)
            blocks.append(f"""\t(wire
\t\t(pts
\t\t\t(xy {x} {y}) (xy {x2} {y2})
\t\t)
\t\t(stroke
\t\t\t(width 0)
\t\t\t(type default)
\t\t)
\t\t(uuid {q(uid(self.name, 'w', key, x, y))})
\t)""")
            blocks.append(label_block("label", net, x2, y2, int(out), uid(self.name, "l", key, net, x2, y2)))
        if blocks:
            self._append(blocks)

    def place(self, lib_id, ref, X, Y, nets, unit=1, rot=0, value="", props=None, key=None, sym_uuid=None):
        """nets: {pin number: net | None (no-connect) | '' (open)}; every pin of the unit must be listed."""
        lib = self.libs[lib_id]
        pins = lib.unit_pins(unit)
        missing, extra = set(pins) - set(nets), set(nets) - set(pins)
        if missing or extra:
            raise SystemExit(f"{ref}.{unit}: missing pins {sorted(missing)} unknown pins {sorted(extra)}")
        self.ensure_lib_symbol(lib_id)
        key = key or f"{ref}.{unit}"
        props = dict(props or {})
        fp = props.pop("Footprint", lib.footprint)
        two_pin = len(lib.pins) <= 2
        if two_pin:
            vert = rot % 180 == 0
            rx, ry, vx, vy = ((X + 2.54, Y - 1.27, X + 2.54, Y + 1.27) if vert
                              else (X - 2.54, Y - 3.81, X - 2.54, Y + 3.81))
        else:
            xs = [p["x"] for p in pins.values()]
            ys = [p["y"] for p in pins.values()]
            rx, ry = X + min(xs) + 2.54, Y - max(ys) - 3.81
            vx, vy = X + min(xs) + 2.54, Y - min(ys) + 3.81
        rx, ry, vx, vy = map(rnd, (rx, ry, vx, vy))

        def prop(name, val, x, y, hide=True):
            h = "\n\t\t\t(hide yes)" if hide else ""
            return (f"\t\t(property {q(name)} {q(val)}\n\t\t\t(at {x} {y} 0){h}\n\t\t\t(effects\n\t\t\t\t(font\n"
                    f"\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t\t(justify left)\n\t\t\t)\n\t\t)")
        plist = [prop("Reference", ref, rx, ry, False), prop("Value", value, vx, vy, False),
                 prop("Footprint", fp, X, Y), prop("Datasheet", props.pop("Datasheet", ""), X, Y),
                 prop("Description", props.pop("Description", ""), X, Y)]
        for k in ("LCSC", "MPN", "Group"):
            plist.append(prop(k, props.pop(k, ""), X, Y))
        for k, v in props.items():
            plist.append(prop(k, v, X, Y))
        pin_s = "\n".join(f"\t\t(pin {q(n)}\n\t\t\t(uuid {q(uid(self.name, key, 'pin', n))})\n\t\t)" for n in sorted(pins))
        block = f"""\t(symbol
\t\t(lib_id {q(lib_id)})
\t\t(at {X} {Y} {rot})
\t\t(unit {unit})
\t\t(exclude_from_sim no)
\t\t(in_bom yes)
\t\t(on_board yes)
\t\t(dnp no)
\t\t(uuid {q(sym_uuid or uid(self.name, key))})
{chr(10).join(plist)}
{pin_s}
\t\t(instances
\t\t\t(project "control_card"
\t\t\t\t(path {q(self.sheet_path())}
\t\t\t\t\t(reference {q(ref)})
\t\t\t\t\t(unit {unit})
\t\t\t\t)
\t\t\t)
\t\t)
\t)"""
        self._append([block])
        sym = dict(lib_id=lib_id, x=X, y=Y, rot=rot, unit=unit, mirror=None)
        drawn = set()
        for n, (x, y, ang) in self.pin_positions(sym).items():
            if (x, y) in drawn:
                continue
            drawn.add((x, y))
            self._draw_pin(x, y, ang, nets[n], f"{key}.{n}")

    def move(self, ref, dx, dy):
        """Move a symbol (all units with this reference) with its stubs, stub-end labels and no-connects."""
        def shift(block):
            return re.sub(r"\((at|xy) ([-\d.]+) ([-\d.]+)",
                          lambda m: f"({m.group(1)} {rnd(float(m.group(2)) + dx)} {rnd(float(m.group(3)) + dy)}", block)
        syms = [(s, e, d) for s, e, d in self.symbols() if d["ref"] == ref]
        pins = {p[:2] for _, _, d in syms for p in self.pin_positions(d).values()}
        spans = set(self._stub_spans(pins)) | {(s, e) for s, e, _ in syms}
        for s, e in sorted(spans, reverse=True):
            self.text = self.text[:s] + shift(self.text[s:e]) + self.text[e:]

    def set_title(self, title):
        self.text = re.sub(r'(\(title_block\s*\(title )"[^"]*"', lambda m: m.group(1) + q(title), self.text, count=1)

    def set_paper(self, paper):
        self.text = re.sub(r'\(paper "[^"]*"\)', f'(paper {q(paper)})', self.text, count=1)

    def clear(self, keep_refs=()):
        """Remove every symbol except keep_refs, with their stubs; also stray wires/labels/texts."""
        for ref in sorted({d["ref"] for _, _, d in self.symbols()} - set(keep_refs)):
            self.remove(ref)
        keep_pts = set()
        for _, _, d in self.symbols():
            keep_pts |= {p[:2] for p in self.pin_positions(d).values()}
        wires = self.wires()
        keep_w = [(s, e, a, b) for s, e, a, b in wires if a in keep_pts or b in keep_pts]
        ends = {b if a in keep_pts else a for _, _, a, b in keep_w}
        spans = [(s, e) for s, e, a, b in wires if (s, e, a, b) not in keep_w]
        spans += [(s, e) for s, e, k, n, p, a in self.labels() if p not in ends]
        spans += [(s, e) for s, e, p in self.no_connects() if p not in keep_pts]
        spans += [(s, e) for s, e, k in self.items("text")]
        self._delete(spans)

    def prune_lib_symbols(self):
        used = {d["lib_id"] for _, _, d in self.symbols()}
        s = self.text.index("\n\t(lib_symbols") + 1
        blk = _block_at(self.text, s)
        new = blk
        for m in reversed(list(re.finditer(r'\n\t\t\(symbol "([^"]+)"', blk))):
            if m.group(1) not in used:
                b = _block_at(blk, m.start() + 1)
                new = new[:m.start()] + new[m.start() + 1 + len(b):]
        self.text = self.text[:s] + new + self.text[s + len(blk):]

    def save(self):
        self.path.write_text(self.text)


def label_block(kind, net, x, y, ang, u):
    just = "left" if ang in (0, 90) else "right"
    if kind == "global_label":
        return f"""\t(global_label {q(net)}
\t\t(shape passive)
\t\t(at {x} {y} {ang})
\t\t(fields_autoplaced yes)
\t\t(effects
\t\t\t(font
\t\t\t\t(size 1.27 1.27)
\t\t\t)
\t\t\t(justify {just})
\t\t)
\t\t(uuid {q(u)})
\t\t(property "Intersheetrefs" "${{INTERSHEET_REFS}}"
\t\t\t(at {x} {y} 0)
\t\t\t(hide yes)
\t\t\t(effects
\t\t\t\t(font
\t\t\t\t\t(size 1.27 1.27)
\t\t\t\t)
\t\t\t)
\t\t)
\t)"""
    return f"""\t(label {q(net)}
\t\t(at {x} {y} {ang})
\t\t(effects
\t\t\t(font
\t\t\t\t(size 1.27 1.27)
\t\t\t)
\t\t\t(justify {just} bottom)
\t\t)
\t\t(uuid {q(u)})
\t)"""


def normalize_labels(sheets):
    """Global label for nets on more than one sheet, local label otherwise."""
    use = {}
    for sh in sheets:
        for *_, n, p, a in sh.labels():
            use.setdefault(n, set()).add(sh.name)
    for sh in sheets:
        for s, e, k, n, p, a in sorted(sh.labels(), reverse=True):
            want = "global_label" if len(use[n]) > 1 else "label"
            if k != want:
                u = re.search(r'\(uuid "([^"]+)"\)', sh.text[s:e]).group(1)
                sh.text = sh.text[:s] + label_block(want, n.replace('\\"', '"'), p[0], p[1], a, u).lstrip("\t") + sh.text[e:]
    return {n for n, s in use.items() if len(s) > 1}


def check_geometry(sheets):
    """Every pin of every placed symbol must touch a wire end, label or no-connect."""
    bad = []
    for sh in sheets:
        pts = set()
        for _, _, a, b in sh.wires():
            pts |= {a, b}
        pts |= {p for *_, p, a in sh.labels()}
        pts |= {p for *_, p in sh.no_connects()}
        for _, _, d in sh.symbols():
            for n, (x, y, _) in sh.pin_positions(d).items():
                if (x, y) not in pts:
                    bad.append((sh.name, d["ref"], n, x, y))
    return bad


def load_project_lib(libs, path, name, lib_id):
    libs[lib_id] = LibSymbol(lib_id, symbol_from_file(str(path), name))
    return libs[lib_id]
