"""Write the Ti60F225 symbol library and the new parts of the conversion.

Run from the repository root with any python3:
    python3 -I tools/make_symbols.py

Outputs:
- hardware/lib/ti60f225.kicad_sym: Ti60F225 (12 units) from reference/ti60f225_pinout.csv.
- hardware/lib/control_card.kicad_sym: adds or replaces SN74AXC8T245PW, TMUX1308PW and
  IS25WP128-RHLE; every other symbol in the file is left as it is.

Pinout sources:
- Ti60F225: Efinix ti60_pinout-v1.0.xlsx (via reference/ti60f225_pinout.csv).
- SN74AXC8T245 PW (TSSOP-24): TI data sheet SCES885, Table 4-1. Pin 11 is DIR2, not GND
  (DIR1 = H, DIR2 = L gives A to B on all 8 bits).
- TMUX1308 PW (TSSOP-16): TI data sheet SCDS426E, Table 6-1. Same pinout as the 4051 except
  pin 7, which is N.C. (VEE on the 4051).
- IS25WP128-RHLE (24-ball 6x8 mm BGA, 5x5 layout): same ball functions as the MT25QU256ABA8E12
  already in the library and the IS25WP128-RHLE symbol of ~/dev/efinix_soc_board. Still to be
  checked against the ISSI data sheet.
"""
import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "hardware" / "lib"
GRID = 2.54
PIN_LEN = 2.54
CHAR_W = 1.0  # rough width of a 1.27 mm font character, for sizing the body


def snap(x):
    return round(round(x / GRID) * GRID, 4)


def fmt(x):
    s = f"{x:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def font(indent, hide=False):
    t = "\t" * indent
    h = f"\n{t}\t(hide yes)" if hide else ""
    return f"{t}(effects\n{t}\t(font\n{t}\t\t(size 1.27 1.27)\n{t}\t){h}\n{t})"


def prop(name, value, y, hide, indent=2):
    t = "\t" * indent
    hide_line = f"\n{t}\t(hide yes)" if hide else ""
    return (f'{t}(property "{name}" "{value}"\n{t}\t(at 0 {fmt(y)} 0){hide_line}\n'
            f"{font(indent + 1)}\n{t})")


def pin(etype, x, y, angle, name, number, indent=3):
    t = "\t" * indent
    return (f"{t}(pin {etype} line\n{t}\t(at {fmt(x)} {fmt(y)} {angle})\n{t}\t(length {fmt(PIN_LEN)})\n"
            f'{t}\t(name "{name}"\n{font(indent + 2)}\n{t}\t)\n'
            f'{t}\t(number "{number}"\n{font(indent + 2)}\n{t}\t)\n{t})')


def unit_block(sym, unit, left, right, unit_name=None):
    """left/right: lists of (etype, name, number) or None for a gap, top to bottom."""
    rows = max(len(left), len(right), 1)
    lw = max([len(p[1]) for p in left if p] + [0])
    rw = max([len(p[1]) for p in right if p] + [0])
    half_w = snap(max((lw + rw) * CHAR_W / 2 + 2 * GRID, 3 * GRID) + GRID / 2)
    top = snap((rows - 1) * GRID / 2)
    y0 = top + GRID
    y1 = top - (rows - 1) * GRID - GRID
    out = []
    t = "\t\t"
    name_line = f'\n{t}\t(unit_name "{unit_name}")' if unit_name else ""
    body = (f'{t}(symbol "{sym}_{unit}_1"{name_line}\n'
            f"{t}\t(rectangle\n{t}\t\t(start {fmt(-half_w)} {fmt(y0)})\n{t}\t\t(end {fmt(half_w)} {fmt(y1)})\n"
            f"{t}\t\t(stroke\n{t}\t\t\t(width 0.254)\n{t}\t\t\t(type default)\n{t}\t\t)\n"
            f"{t}\t\t(fill\n{t}\t\t\t(type background)\n{t}\t\t)\n{t}\t)")
    out.append(body)
    for side, pins, x, ang in (("L", left, -half_w - PIN_LEN, 0), ("R", right, half_w + PIN_LEN, 180)):
        for i, p in enumerate(pins):
            if p:
                out.append(pin(p[0], x, top - i * GRID, ang, p[1], p[2]))
    out.append(f"{t})")
    return "\n".join(out), y1


def symbol(name, units, props, pin_names_offset=1.016):
    """units: list of (unit_name, left, right). props: dict with Reference/Value/Footprint/..."""
    blocks = []
    bottom = 0.0
    top = 0.0
    for i, (uname, left, right) in enumerate(units, start=1):
        b, y1 = unit_block(name, i, left, right, uname if len(units) > 1 else None)
        blocks.append(b)
        bottom = min(bottom, y1)
        rows = max(len(left), len(right), 1)
        top = max(top, snap((rows - 1) * GRID / 2) + GRID)
    t = "\t"
    head = [f'{t}(symbol "{name}"', f"{t}\t(pin_names\n{t}\t\t(offset {pin_names_offset})\n{t}\t)",
            f"{t}\t(exclude_from_sim no)", f"{t}\t(in_bom yes)", f"{t}\t(on_board yes)"]
    y = top + GRID
    head.append(prop("Reference", props["Reference"], y, False))
    y = bottom - GRID
    for k in ("Value", "Footprint", "Datasheet", "Description", "LCSC", "MPN"):
        if k in props:
            head.append(prop(k, props[k], y, k != "Value"))
            y -= GRID
    return "\n".join(head + blocks) + f"\n{t})"


def write_lib(path, symbols):
    text = "(kicad_symbol_lib\n\t(version 20241209)\n\t(generator \"make_symbols\")\n\t(generator_version \"10.0\")\n"
    text += "\n".join(symbols) + "\n)\n"
    path.write_text(text)


def replace_in_lib(path, new):
    """Replace or append top-level symbols in an existing library; keep everything else."""
    text = path.read_text()
    for name, body in new.items():
        start = text.find(f'\n\t(symbol "{name}"\n')
        if start >= 0:
            depth, i = 0, start + 2
            for j in range(i, len(text)):
                depth += text[j] == "("
                depth -= text[j] == ")"
                if depth == 0:
                    break
            text = text[:start + 1] + body + text[j + 1:]
        else:
            end = text.rstrip().rfind(")")
            text = text[:end].rstrip("\n") + "\n" + body + "\n)\n"
    path.write_text(text)


# ---------------------------------------------------------------- Ti60F225

def natural(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def ti60f225():
    rows = list(csv.DictReader(open(ROOT / "reference" / "ti60f225_pinout.csv")))

    def by(pred):
        return sorted((r for r in rows if pred(r)), key=lambda r: (natural(r["pad"]), natural(r["ball"])))

    def P(etype, r):
        return (etype, r["pad"], r["ball"])

    supplies = by(lambda r: r["type"] == "power" and r["pad"].startswith("VCC"))
    vcc = [P("power_in", r) for r in supplies if r["pad"] == "VCC" or r["pad"].startswith("VCCA_")]
    vccaux = [P("power_in", r) for r in supplies if r["pad"] == "VCCAUX"]
    vccio = [P("power_in", r) for r in supplies if re.match(r"VCCIO\d[AB]$", r["pad"])]
    vccio33 = [P("power_in", r) for r in supplies if r["pad"].startswith("VCCIO33")]
    power_left = vcc + [None] + vccaux + [None] + vccio33
    power_right = vccio
    gnd = [P("power_in", r) for r in by(lambda r: r["pad"] in ("GND", "VQPS_GND"))]

    ded = {r["pad"]: r for r in rows if r["type"] == "dedicated"}
    cfg_left = [P("input", ded["CRESET_N"]), P("open_collector", ded["CDONE"]), None,
                P("input", ded["TCK"]), P("input", ded["TMS"]), P("input", ded["TDI"]), P("output", ded["TDO"])]
    cfg_right = [P("passive", r) for r in by(lambda r: r["pad"].startswith("REF_RES"))]

    units = [("POWER", power_left, power_right),
             ("GND", gnd[: (len(gnd) + 1) // 2], gnd[(len(gnd) + 1) // 2:]),
             ("CONFIG_JTAG", cfg_left, cfg_right)]

    for bank in ("1A", "1B", "2A", "2B", "3A", "3B", "4A", "4B"):
        io = [r for r in rows if r["bank"] == bank and r["type"] == "HSIO"]
        # one row per pair: P on the left, N on the right
        idx = sorted({int(re.match(r"GPIO[LRTB]_[PN]_(\d+)", r["pad"]).group(1)) for r in io})
        left, right = [], []
        for n in idx:
            p = [r for r in io if re.match(rf"GPIO[LRTB]_P_{n:02d}(_|$)", r["pad"])]
            q = [r for r in io if re.match(rf"GPIO[LRTB]_N_{n:02d}(_|$)", r["pad"])]
            left.append(P("bidirectional", p[0]) if p else None)
            right.append(P("bidirectional", q[0]) if q else None)
        units.append((f"HSIO_{bank}", left, right))

    hvio = {b: by(lambda r, b=b: r["bank"] == b and r["type"] == "HVIO") for b in ("TL", "TR", "BL", "BR")}
    left = [P("bidirectional", r) for r in hvio["TL"]] + [None] + [P("bidirectional", r) for r in hvio["BL"]]
    right = [P("bidirectional", r) for r in hvio["TR"]] + [None] + [P("bidirectional", r) for r in hvio["BR"]]
    units.append(("HVIO", left, right))

    used = sum(1 for _, l, r in units for p in l + r if p)
    assert used == 225, used
    assert len({p[2] for _, l, r in units for p in l + r if p}) == 225

    return symbol("Ti60F225", units, {
        "Reference": "U",
        "Value": "Ti60F225C4",
        "Footprint": "control_card:Efinix_F225",
        "Datasheet": "${KIPRJMOD}/../reference/efinix/titanium60-ds-v3.9.pdf",
        "Description": "Efinix Titanium Ti60 FPGA, 225-ball FBGA 10x10 mm 0.65 mm; HSIO banks 1A-4B (1.2-1.8 V), "
                       "HVIO TL/TR/BL/BR (1.8-3.3 V)",
        "MPN": "Ti60F225C4",
    })


# ---------------------------------------------------------------- other new parts

def sn74axc8t245():
    a = [("bidirectional", f"A{i}", str(2 + i)) for i in range(1, 9)]
    b = [("bidirectional", f"B{i}", str(22 - i)) for i in range(1, 9)]
    left = [("power_in", "VCCA", "1"), None, ("input", "DIR1", "2"), ("input", "DIR2", "11"),
            ("input", "~{OE}", "22"), None] + a + [None, ("power_in", "GND", "12"), ("power_in", "GND", "13")]
    right = [("power_in", "VCCB", "23"), ("power_in", "VCCB", "24"), None, None, None, None] + b
    return symbol("SN74AXC8T245PW", [(None, left, right)], {
        "Reference": "U",
        "Value": "SN74AXC8T245PWR",
        "Footprint": "Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm",
        "Datasheet": "https://www.ti.com/lit/ds/symlink/sn74axc8t245.pdf",
        "Description": "8-bit dual-supply level translator, 0.65-3.6 V, DIR1/DIR2 per nibble "
                       "(DIR1=H, DIR2=L: A to B on all bits), active-low OE, TSSOP-24",
        "LCSC": "C882718",
        "MPN": "SN74AXC8T245PWR",
    })


def tmux1308():
    s = [("passive", f"S{i}", n) for i, n in enumerate(["13", "14", "15", "12", "1", "5", "2", "4"])]
    left = s + [None, ("passive", "D", "3")]
    right = [("power_in", "VDD", "16"), None, ("input", "A0", "11"), ("input", "A1", "10"), ("input", "A2", "9"),
             ("input", "~{EN}", "6"), None, ("no_connect", "NC", "7"), None, ("power_in", "GND", "8")]
    return symbol("TMUX1308PW", [(None, left, right)], {
        "Reference": "U",
        "Value": "TMUX1308APWR",
        "Footprint": "Package_SO:TSSOP-16_4.4x5mm_P0.65mm",
        "Datasheet": "https://www.ti.com/lit/ds/symlink/tmux1308.pdf",
        "Description": "8:1 analog mux, 1.62-5.5 V, 1.8 V logic-compatible selects, 4051 pinout "
                       "(pin 7 N.C.), TSSOP-16",
        "LCSC": "C39707757",
        "MPN": "TMUX1308APWR",
    })


def is25wp128():
    left = [("power_in", "VCC", "B4"), None, ("input", "~{CS}", "C2"), ("input", "SCLK", "B2"),
            ("input", "~{RESET}", "A4"), None, ("power_in", "GND", "B3")]
    right = [("bidirectional", "SI/IO0", "D3"), ("bidirectional", "SO/IO1", "D2"),
             ("bidirectional", "~{WP}/IO2", "C4"), ("bidirectional", "~{HOLD}/IO3", "D4")]
    nc = ["A2", "A3", "A5", "B1", "B5", "C1", "C3", "C5", "D1", "D5", "E1", "E2", "E3", "E4", "E5"]
    right += [None] + [("no_connect", "NC", n) for n in nc]
    return symbol("IS25WP128-RHLE", [(None, left, right)], {
        "Reference": "U",
        "Value": "IS25WP128-RHLE",
        "Footprint": "control_card:BGA-24_6x8mm_Layout5x5_P1.0mm_CY0.5",
        "Datasheet": "",
        "Description": "128 Mbit 1.8 V quad SPI NOR flash, 133 MHz, 24-ball TFBGA 6x8 mm (5x5 ball layout), "
                       "dedicated RESET#",
        "LCSC": "C1349419",
        "MPN": "IS25WP128-RHLE",
    })


def main():
    write_lib(LIB / "ti60f225.kicad_sym", [ti60f225()])
    replace_in_lib(LIB / "control_card.kicad_sym", {
        "SN74AXC8T245PW": sn74axc8t245(),
        "TMUX1308PW": tmux1308(),
        "IS25WP128-RHLE": is25wp128(),
    })
    print("wrote hardware/lib/ti60f225.kicad_sym and updated hardware/lib/control_card.kicad_sym")


if __name__ == "__main__":
    main()
