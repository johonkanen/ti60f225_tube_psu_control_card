"""Phase 3 of CONVERSION_PLAN.md: convert the Agilex 3 schematic to the Ti60F225.

Run once from the repository root, on the copied Agilex sheets:
    python3 -I tools/phase3_schematic.py

It edits hardware/sheets/*.kicad_sch in place (see tools/sch_edit.py). Re-running it on
an already converted schematic is not supported: restore the sheets from git first.

FPGA ball assignment here is provisional (by bank and board side); phase 4 checks it in
Efinity and phase 5 reassigns balls after placement. The HyperRAM uses the pin map of the
user's own controller on the AC PSU Ti60 card (ti60_ac_psu tsemac_soc.peri.xml, bank 1B).
"""
import csv
import glob
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sch_edit import Sheet, check_geometry, load_project_lib, normalize_labels  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
HW = ROOT / "hardware"
LIB = HW / "lib"
FPGA = "ti60f225:Ti60F225"
G = 2.54

# ------------------------------------------------------------------ parts
C0201 = "Capacitor_SMD:C_0201_0603Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
R0201 = "Resistor_SMD:R_0201_0603Metric"
R0402 = "Resistor_SMD:R_0402_1005Metric"
PARTS = {
    # value: (lib_id, footprint, LCSC, MPN)
    "47u": ("Device:C", C0603, "C140782", "GRM188R60J476ME15D"),
    "10u": ("Device:C", C0603, "C19702", "CL10A106KP8NNNC"),
    "4u7": ("Device:C", C0201, "C2880368", "JDK063BBJ475MV-AT"),
    "1u": ("Device:C", C0201, "C170152", "CL03A105MQ3CSNC"),
    "1u_0402": ("Device:C", C0402, "C52923", "CL05A105KA5NQNC"),
    "100n": ("Device:C", C0201, "C49062", "CL03A104KP3NNNC"),
    "100n_0402": ("Device:C", C0402, "C1525", "CL05B104KO5NNNC"),
    "10n": ("Device:C", C0201, "C272853", "CC0201KRX7R7BB103"),
    "1n": ("Device:C", C0201, "C66942", "0201B102K500NT"),
    "10k": ("Device:R", R0201, "C473048", "0201WMF1002TEE"),
    "330k": ("Device:R", R0402, "C25778", "0402WGF3303TCE"),
    "bead": ("Device:FerriteBead", "Inductor_SMD:L_0603_1608Metric", "C14709", "BLM18PG121SN1D"),
}
VALUE = {"1u_0402": "1u", "100n_0402": "100n", "bead": "120R@100MHz"}


class Refs:
    """New references continue after the highest number the Agilex schematic used."""
    def __init__(self, sheets):
        self.next = {}
        for sh in sheets:
            for _, _, d in sh.symbols():
                m = re.match(r"(#?[A-Z]+)(\d+)$", d["ref"])
                if m:
                    self.next[m.group(1)] = max(self.next.get(m.group(1), 1), int(m.group(2)) + 1)

    def __call__(self, prefix):
        n = self.next.get(prefix, 1)
        self.next[prefix] = n + 1
        return f"{prefix}{n}"


# ------------------------------------------------------------------ layout
def label_len(net):
    return 0 if not net else len(net) * 1.0 + 2.5


def extents(lib, unit, nets, rot=0):
    """(left, top, right, bottom) around the symbol origin, sheet coordinates, incl. labels."""
    xs, ys = [], []
    for n, p in lib.unit_pins(unit).items():
        x, y = p["x"], -p["y"]
        ang = p["angle"]
        L = 2 * G + label_len(nets.get(n))
        if ang == 0:      # pin on the left, points right
            xs.append(x - L); ys.append(y)
        elif ang == 180:
            xs.append(x + L); ys.append(y)
        elif ang == 90:   # pin at the bottom, points up
            xs.append(x); ys.append(y + L)
        else:
            xs.append(x); ys.append(y - L)
    for x0, y0, x1, y1 in lib.bodies.get(unit, []) + lib.bodies.get(0, []):
        xs += [x0, x1]; ys += [-y0, -y1]
    return min(xs) - 2 * G, min(ys) - 2 * G, max(xs) + 3 * G, max(ys) + 2 * G


def snap(v):
    return round(round(v / G) * G, 2)


class Flow:
    """Places items left to right in rows, inside a width."""
    def __init__(self, x0, y0, width):
        self.x0, self.y, self.width = x0, y0, width
        self.x, self.row_h, self.max_x = x0, 0, x0

    def put(self, ext):
        left, top, right, bottom = ext
        w, h = right - left, bottom - top
        if self.x + w > self.x0 + self.width and self.x > self.x0:
            self.newline()
        X, Y = snap(self.x - left), snap(self.y - top)
        self.x += w
        self.row_h = max(self.row_h, h)
        self.max_x = max(self.max_x, self.x)
        return X, Y

    def newline(self, gap=G):
        self.y += self.row_h + gap
        self.x, self.row_h = self.x0, 0

    def bottom(self):
        return self.y + self.row_h


def place_passive(sh, flow, refs, kind, top, bottom, prefix=None, ref=None):
    lib_id, fp, lcsc, mpn = PARTS[kind]
    lib = sh.libs[lib_id]
    nets = {"1": top, "2": bottom}
    ref = ref or refs(prefix or ("FB" if kind == "bead" else lib_id.split(":")[1][0]))
    X, Y = flow.put(extents(lib, 1, nets))
    sh.place(lib_id, ref, X, Y, nets, value=VALUE.get(kind, kind),
             props={"Footprint": fp, "LCSC": lcsc, "MPN": mpn})
    return ref


def place_unit(sh, flow, lib_id, ref, unit, nets, value, props=None):
    X, Y = flow.put(extents(sh.libs[lib_id], unit, nets))
    sh.place(lib_id, ref, X, Y, nets, unit=unit, value=value, props=props)


def content_bbox(sh):
    xs, ys = [], []
    for m in re.finditer(r"\(at ([-\d.]+) ([-\d.]+)", sh.text[sh.text.index("\n\t(lib_symbols"):]):
        xs.append(float(m.group(1))); ys.append(float(m.group(2)))
    for m in re.finditer(r"\(xy ([-\d.]+) ([-\d.]+)\)", sh.text):
        xs.append(float(m.group(1))); ys.append(float(m.group(2)))
    return (min(xs), min(ys), max(xs), max(ys)) if xs else (0, 0, 0, 0)


def fit_paper(sh, flow_max_x, flow_bottom):
    x1 = max(flow_max_x, content_bbox(sh)[2]) + 20
    y1 = max(flow_bottom, content_bbox(sh)[3]) + 30
    for name, w, h in (("A3", 420, 297), ("A2", 594, 420), ("A1", 841, 594), ("A0", 1189, 841)):
        if x1 <= w and y1 <= h:
            sh.set_paper(name)
            return name
    sh.set_paper("A0")
    return "A0"


# ------------------------------------------------------------------ FPGA pin data
PINS = list(csv.DictReader(open(ROOT / "reference" / "ti60f225_pinout.csv")))


def unit_nets(lib, unit, assign):
    """All pins of a unit: assigned net, else no-connect."""
    return {n: assign.get(n) for n in lib.unit_pins(unit)}


def bank_balls(bank, kind="HSIO"):
    def key(r):
        m = re.match(r"GPIO[LRTB]_([PN])_(\d+)", r["pad"]) or re.match(r"GPIO[LRTB]_()(\d+)", r["pad"])
        return (int(m.group(2)), m.group(1))
    return [r["ball"] for r in sorted((r for r in PINS if r["bank"] == bank and r["type"] == kind), key=key)]


def ball(pad_prefix):
    hits = [r["ball"] for r in PINS if r["pad"] == pad_prefix or r["pad"].startswith(pad_prefix + "_")]
    assert len(hits) == 1, (pad_prefix, hits)
    return hits[0]


# HyperRAM: the AC PSU card's pin map for the user's controller (bank 1B).
HYPERRAM = {
    "HR_CK": "GPIOL_N_16", "HR_CS_N": "GPIOL_P_18", "HR_DQ0": "GPIOL_P_14", "HR_DQ1": "GPIOL_N_09",
    "HR_DQ2": "GPIOL_N_17", "HR_DQ3": "GPIOL_N_15", "HR_DQ4": "GPIOL_P_16", "HR_DQ5": "GPIOL_N_14",
    "HR_DQ6": "GPIOL_N_10", "HR_DQ7": "GPIOL_P_10", "HR_RESET_N": "GPIOL_P_17", "HR_RWDS": "GPIOL_P_15",
}

# Header outputs through the translators, in J1 pin order (4 per SN74AVC4T774).
XLAT = [["PRI_DHB_HI", "EPWM6A", "PRI_DHB_LO", "EPWM5A"],
        ["CUK_CS", "HT_CS", "EPWM2A", "SYNCH_2"],
        ["EPWM2B", "CUK_CLK", "SYNCH_1", "HT_CLK"],
        ["GPIO_BYPASS_RLY", "PFC_PWM1", "EPWM1A", "PFC_PWM2"]]


def fpga_assignment():
    a = {}
    for net, pad in HYPERRAM.items():
        a[ball(pad)] = net
    # translator A side + OE: bank 3A, then 3B (right side of the package)
    xl = [f"{n}_1V8" for grp in XLAT for n in grp] + ["XLAT_OE_N"]
    for b, n in zip(bank_balls("3A") + bank_balls("3B"), xl):
        a[b] = n
    # ADC chain A on 4A, chain B on 4B (bottom side)
    for bank, ch in (("4A", "A"), ("4B", "B")):
        nets = [f"ADC{ch}_CS_N", f"ADC{ch}_SCLK", f"ADC{ch}_SDO", f"AD{ch}SEL0", f"AD{ch}SEL1", f"AD{ch}SEL2"]
        for b, n in zip(bank_balls(bank), nets):
            a[b] = n
    # 3.3 V HVIO: at most 6 outputs per bank, one header input per bank TL/TR/BR
    hv = {
        "TL": ["LED1_R", "LED1_G", "LED1_B", "LED2_R", "LED2_G", "LED2_B", "HT_SDATA"],
        "TR": ["CUK_SDATA", "TX", "J1_P17", "J1_P19", "J1_P22", "J1_P24", "J1_P26"],
        "BR": ["RX", "J1_P27", "J1_P28", "J1_P29", "J1_P30", "J1_P31", "J1_P32"],
        "BL": ["J1_P33"],
    }
    for bank, nets in hv.items():
        for b, n in zip(bank_balls(bank, "HVIO"), nets):
            a[b] = n
    return a


# ------------------------------------------------------------------ sheets
def main():
    libs = {}
    sheets = {Path(p).stem: Sheet(p, libs) for p in sorted(glob.glob(str(HW / "sheets" / "*.kicad_sch")))}
    bad = check_geometry(sheets.values())
    if bad:
        sys.exit(f"pin geometry check failed: {bad[:5]}")
    if any(d["lib_id"] == FPGA for sh in sheets.values() for _, _, d in sh.symbols()):
        sys.exit("already converted: restore hardware/sheets from git first")
    load_project_lib(libs, LIB / "ti60f225.kicad_sym", "Ti60F225", FPGA)
    for name in ("TMUX1308PW", "IS25WP128-RHLE"):
        load_project_lib(libs, LIB / "control_card.kicad_sym", name, f"control_card:{name}")
    refs = Refs(sheets.values())
    fl = libs[FPGA]
    units = {re.search(r'unit_name "([^"]+)"', b).group(1): int(u)
             for u, b in re.findall(r'\(symbol "Ti60F225_(\d+)_1"(.*?)\(rectangle', fl.block, re.S)}
    assign = fpga_assignment()
    fpga_props = {"Footprint": "control_card:Efinix_F225", "MPN": "Ti60F225C4",
                  "Description": "Efinix Titanium Ti60 FPGA, 225-ball FBGA"}

    # ---------------------------------------------------- fpga_power: rebuilt
    sh = sheets["fpga_power"]
    sh.clear()
    sh.set_title("Ti60F225 power and decoupling")
    flow = Flow(25.4, 30.48, 520)
    pw = {}
    for r in PINS:
        p = r["pad"]
        if p == "VCC":
            pw[r["ball"]] = "+0V95"
        elif p.startswith("VCCA_"):
            pw[r["ball"]] = "+0V95_" + p
        elif p == "VCCAUX" or re.match(r"VCCIO\d[AB]$", p):
            pw[r["ball"]] = "+1V8"
        elif p.startswith("VCCIO33"):
            pw[r["ball"]] = "+3V3"
        elif p in ("GND", "VQPS_GND"):
            pw[r["ball"]] = "GND"
    place_unit(sh, flow, FPGA, "U1", units["POWER"], unit_nets(fl, units["POWER"], pw), "Ti60F225C4", fpga_props)
    place_unit(sh, flow, FPGA, "U1", units["GND"], unit_nets(fl, units["GND"], pw), "Ti60F225C4", fpga_props)
    flow.newline(5 * G)
    # VCCA: separate bead filter per VCCA ball (Efinix HWC), 2x100n 2x10n 1n each
    for corner in ("TL", "TR", "BL", "BR"):
        net = f"+0V95_VCCA_{corner}"
        place_passive(sh, flow, refs, "bead", "+0V95", net)
        for kind in ("100n", "100n", "10n", "10n", "1n"):
            place_passive(sh, flow, refs, kind, net, "GND")
        flow.x += 2 * G
    flow.newline(3 * G)
    # VCC (HWC: 100u 47u 4u7 1u 5x100n 5x10n 2x1n; the 100u is covered by the buck output caps)
    for kind in ["47u", "4u7", "1u"] + ["100n"] * 5 + ["10n"] * 5 + ["1n"] * 2:
        place_passive(sh, flow, refs, kind, "+0V95", "GND")
    flow.newline(3 * G)
    # VCCAUX 4u7 100n 10n 1n; VCCIO (all eight HSIO banks on +1V8): shared 47u 10u 4u7, 1u + 100n per bank
    for kind in ["4u7", "100n", "10n", "1n", "47u", "10u", "4u7"] + ["1u", "100n"] * 8:
        place_passive(sh, flow, refs, kind, "+1V8", "GND")
    flow.newline(3 * G)
    # VCCIO33, four HVIO banks: 4u7 1u 100n each
    for kind in ["4u7", "1u", "100n"] * 4:
        place_passive(sh, flow, refs, kind, "+3V3", "GND")
    # power flags for the bead-filtered VCCA nets
    for corner in ("TL", "TR", "BL", "BR"):
        lib = sh.libs["power:PWR_FLAG"]
        X, Y = flow.put(extents(lib, 1, {"1": f"+0V95_VCCA_{corner}"}))
        sh.place("power:PWR_FLAG", refs("#FLG"), X, Y, {"1": f"+0V95_VCCA_{corner}"}, value="PWR_FLAG")
    fit_paper(sh, flow.max_x, flow.bottom())

    # ---------------------------------------------------- fpga_io: rebuilt
    sh = sheets["fpga_io"]
    sh.clear()
    sh.set_title("Ti60F225 I/O banks (provisional balls)")
    flow = Flow(25.4, 30.48, 520)
    for uname in ("HSIO_1B", "HSIO_2A", "HSIO_2B", "HSIO_3A", "HSIO_3B", "HSIO_4A", "HSIO_4B", "HVIO"):
        u = units[uname]
        place_unit(sh, flow, FPGA, "U1", u, unit_nets(fl, u, assign), "Ti60F225C4", fpga_props)
    fit_paper(sh, flow.max_x, flow.bottom())

    # ---------------------------------------------------- config: rebuilt around J2
    sh = sheets["config"]
    u7_uuid = next(d["uuid"] for _, _, d in sh.symbols() if d["ref"] == "U7")
    sh.clear(keep_refs=("J2",))
    sh.set_title("Configuration (SPI active x4), JTAG, reset")
    j2 = next(d for _, _, d in sh.symbols() if d["ref"] == "J2")
    sh.move("J2", 45.72 - j2["x"], 40.64 - j2["y"])       # J2 keeps its UUID (it is placed on the PCB)
    _, _, _, ybot = content_bbox(sh)
    flow = Flow(25.4, ybot + 12.7, 360)
    cfg = {ball("CRESET_N"): "CRESET_N", ball("CDONE"): "CDONE", ball("TCK"): "TCK", ball("TMS"): "TMS",
           ball("TDI"): "TDI", ball("TDO"): "TDO",
           ball("REF_RES_2A"): "REF_RES_2A", ball("REF_RES_3A"): "REF_RES_3A", ball("REF_RES_4A"): "REF_RES_4A",
           ball("GPIOL_P_01_SSL_N"): "FLASH_CS_N", ball("GPIOL_N_01_CCK"): "FLASH_CLK",
           ball("GPIOL_P_03_CDI0"): "FLASH_IO0", ball("GPIOL_N_03_CDI1"): "FLASH_IO1",
           ball("GPIOL_P_04_CDI2"): "FLASH_IO2", ball("GPIOL_N_04_CDI3"): "FLASH_IO3",
           ball("GPIOL_P_02_CSI"): "CSI", ball("GPIOL_P_00_PLLIN0"): "CLK100M"}
    for uname in ("CONFIG_JTAG", "HSIO_1A"):
        u = units[uname]
        place_unit(sh, flow, FPGA, "U1", u, unit_nets(fl, u, cfg), "Ti60F225C4", fpga_props)
    flash = libs["control_card:IS25WP128-RHLE"]
    fnets = {"B4": "+1V8", "B3": "GND", "C2": "FLASH_CS_N", "B2": "FLASH_CLK", "A4": "FLASH_RESET_N",
             "D3": "FLASH_IO0", "D2": "FLASH_IO1", "C4": "FLASH_IO2", "D4": "FLASH_IO3"}
    fnets.update({n: None for n in flash.unit_pins(1) if n not in fnets})
    X, Y = flow.put(extents(flash, 1, fnets))
    sh.place("control_card:IS25WP128-RHLE", "U7", X, Y, fnets, value="IS25WP128-RHLE", sym_uuid=u7_uuid,
             props={"LCSC": "C1349419", "MPN": "IS25WP128-RHLE",
                    "Description": "128 Mbit 1.8 V QSPI flash, 24-ball BGA; Ti60 SPI active x4 bitstream"})
    flow.newline(4 * G)
    place_passive(sh, flow, refs, "100n_0402", "+1V8", "GND")          # flash decoupling
    place_passive(sh, flow, refs, "330k", "+1V8", "CRESET_N")           # CRESET_N RC (proven card)
    place_passive(sh, flow, refs, "1u_0402", "CRESET_N", "GND")
    for net in ("CDONE", "FLASH_CS_N", "CSI", "HR_DQ3", "FLASH_IO2", "FLASH_IO3", "FLASH_RESET_N"):
        place_passive(sh, flow, refs, "10k", "+1V8", net)                # HR_DQ3 is TEST_N (E2)
    for net in ("TCK", "TMS", "TDI", "TDO"):
        place_passive(sh, flow, refs, "10k", "+3V3", net)                # JTAG at 3.3 V (bank BL)
    for net in ("REF_RES_2A", "REF_RES_3A", "REF_RES_4A"):
        place_passive(sh, flow, refs, "10k", net, "GND")                 # 10 k 1 %
    fit_paper(sh, flow.max_x, flow.bottom())

    # ---------------------------------------------------- connector: 4 x SN74AVC4T774 translators
    sh = sheets["connector"]
    _, _, _, ybot = content_bbox(sh)
    flow = Flow(25.4, ybot + 15, 380)
    xl_id = "control_card:SN74AXC4T774RSV"
    for grp in XLAT:
        nets = {"14": "+1V8", "13": "+3V3", "8": "GND", "7": "XLAT_OE_N",
                "15": "+1V8", "16": "+1V8", "5": "+1V8", "6": "+1V8"}       # DIRn high: A to B
        for i, n in enumerate(grp):
            nets[str(1 + i)] = f"{n}_1V8"                                  # A1..A4 = pins 1..4
            nets[str(12 - i)] = n                                          # B1..B4 = pins 12..9
        X, Y = flow.put(extents(sh.libs[xl_id], 1, nets))
        sh.place(xl_id, refs("U"), X, Y, nets, value="SN74AVC4T774RSVR",
                 props={"Footprint": "Package_DFN_QFN:UQFN-16_1.8x2.6mm_P0.4mm", "LCSC": "C779392",
                        "MPN": "SN74AVC4T774RSVR",
                        "Description": "4-bit 1.8 V to 3.3 V translator, DIR high = A to B, OE low = enabled"})
    flow.newline(3 * G)
    for _ in XLAT:
        place_passive(sh, flow, refs, "100n", "+1V8", "GND")
        place_passive(sh, flow, refs, "100n", "+3V3", "GND")
    place_passive(sh, flow, refs, "10k", "+1V8", "XLAT_OE_N")               # outputs off until the FPGA drives OE low
    fit_paper(sh, flow.max_x, flow.bottom())

    # ---------------------------------------------------- adc: TMUX1308 muxes, ADC DVDD on +1V8
    sh = sheets["adc"]
    for ref in ("U10", "U13"):
        (_, _, d), = [(s, e, d) for s, e, d in sh.symbols() if d["ref"] == ref]
        old = {n: sh.stub_net(ref, n) for n in sh.libs[d["lib_id"]].unit_pins(1)}
        sh.remove(ref)
        old["7"] = None                    # TMUX1308 pin 7 is N.C. (VEE on the 4051)
        sh.place("control_card:TMUX1308PW", ref, d["x"], d["y"], old, value="TMUX1308APWR", sym_uuid=d["uuid"],
                 props={"LCSC": "C39707757", "MPN": "TMUX1308APWR",
                        "Description": "8:1 analog mux, 1.8 V logic selects"})
    for ref, pin in (("U12", "4"), ("U15", "4"), ("C59", "1"), ("C64", "1")):
        assert sh.stub_net(ref, pin) == "+3V3", (ref, pin, sh.stub_net(ref, pin))
        sh.relabel_pin(ref, pin, "+1V8")

    # ---------------------------------------------------- power: drop the 1.2 V and 1.8 V_HR bucks, core to 0.95 V
    sh = sheets["power"]
    flags = [d["ref"] for _, _, d in sh.symbols() if d["ref"].startswith("#FLG")
             and sh.stub_net(d["ref"], "1") in ("+1V2", "+1V8_HR", "VCC_SENSE_P", "VCC_SENSE_N", "+0V75_PLLDIG",
                                                "+1V8_PLL", "+1V8_ADC", "+1V2_RCORE")]
    for ref in ["U17", "L4", "C81", "C82", "R42", "R43", "C80", "U18", "L5", "C84", "C85", "R44", "R45", "C83",
                "C11", "R3", "R4", "R50", "R51"] + flags:
        sh.remove(ref)
    sh.relabel_pin("U4", "6", None)                     # PG_3V3 no longer used
    sh.relabel_pin("R1", "1", "+0V95")                  # local feedback: no sense balls on the Ti60
    sh.relabel_pin("C77", "1", "+0V95")
    sh.relabel_pin("R2", "2", "GND")
    sh.set_props("R1", Value="118k", LCSC="C25748", MPN="0402WGF1183TCE")   # 0.6 V x (1 + 118k/200k) = 0.954 V
    sh.set_props("C77", Value="47p", LCSC="C1567", MPN="0402CG470J500NT")   # same zero as 100p x 51k

    # ---------------------------------------------------- renames on every sheet
    for sh in sheets.values():
        for old, new in (("+0V75", "+0V95"), ("FB_0V75", "FB_0V95"), ("SW_0V75", "SW_0V95"),
                         ("EN_0V75", "EN_0V95"), ("PG_0V75", "PG_0V95"), ("+1V8_HR", "+1V8")):
            sh.relabel(old, new)
    for name, title in (("memory", "HyperRAM and 100 MHz clock"), ("power", "Power: 0.95 V, 1.8 V, 3.3 V bucks, analog 3.3 V LDO")):
        sheets[name].set_title(title)

    for sh in sheets.values():
        sh.text = re.sub(r'\(comment 1 "[^"]*"\)', '(comment 1 "Agilex 3 card converted by tools/phase3_schematic.py")', sh.text, count=1)
    normalize_labels(sheets.values())
    bad = check_geometry(sheets.values())
    if bad:
        sys.exit(f"pin geometry check failed after editing: {bad[:5]}")
    for sh in sheets.values():
        sh.prune_lib_symbols()
        sh.save()

    root = HW / "control_card.kicad_sch"
    t = root.read_text()
    t = re.sub(r'(\(title_block\s*\(title )"[^"]*"', r'\1"Ti60F225 control card (tube PSU)"', t, count=1)
    root.write_text(t)
    print("converted:", ", ".join(sheets))


if __name__ == "__main__":
    main()
