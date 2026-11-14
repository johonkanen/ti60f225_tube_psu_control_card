"""Check the Ti60F225 schematic netlist against the design intent of CONVERSION_PLAN.md.

    kicad-cli sch export netlist --format kicadsexpr -o /tmp/after.net hardware/control_card.kicad_sch
    python3 -I tools/check_schematic.py /tmp/after.net [--before /tmp/agilex.net]

With --before (a netlist of the Agilex schematic at 43b9ec7), every part that phase 3 did not
mean to touch must keep its nets, apart from the listed rail renames.
Net names are compared without their sheet prefix (/Configuration/TCK -> TCK).
"""
import collections
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read_netlist(path):
    t = Path(path).read_text()
    t = t[t.index("(nets"):]
    nets = {}
    for blk in re.split(r"\n\t\t\(net\n", t)[1:]:
        name = re.search(r'\(name "([^"]*)"\)', blk).group(1)
        if not name.startswith("unconnected"):
            name = name.split("/")[-1]
        nodes = []
        for nb in re.split(r"\(node\n", blk)[1:]:
            nodes.append((re.search(r'\(ref "([^"]+)"\)', nb).group(1), re.search(r'\(pin "([^"]+)"\)', nb).group(1)))
        nets.setdefault(name, []).extend(nodes)
    by = collections.defaultdict(dict)
    for n, nodes in nets.items():
        for r, p in nodes:
            by[r][p] = n
    return nets, by


HYPERRAM = {"HR_CK": "P11", "HR_CS_N": "R12", "HR_DQ0": "P8", "HR_DQ1": "R9", "HR_DQ2": "R11", "HR_DQ3": "P9",
            "HR_DQ4": "R10", "HR_DQ5": "R7", "HR_DQ6": "P7", "HR_DQ7": "R8", "HR_RESET_N": "P12", "HR_RWDS": "P10"}
RENAMES = {"+0V75": "+0V95", "FB_0V75": "FB_0V95", "SW_0V75": "SW_0V95", "EN_0V75": "EN_0V95",
           "PG_0V75": "PG_0V95", "+1V8_HR": "+1V8"}
INTENDED = {("U12", "4"): "+1V8", ("U15", "4"): "+1V8", ("C59", "1"): "+1V8", ("C64", "1"): "+1V8",
            ("R1", "1"): "+0V95", ("C77", "1"): "+0V95", ("R2", "2"): "GND",
            ("U4", "6"): "unconnected-(U4-PG-Pad6)"}


def main():
    A, a = read_netlist(sys.argv[1])
    before = sys.argv[sys.argv.index("--before") + 1] if "--before" in sys.argv else None
    pins = {r["ball"]: r for r in csv.DictReader(open(ROOT / "reference" / "ti60f225_pinout.csv"))}
    errs = []

    def chk(c, msg):
        if not c:
            errs.append(msg)

    U1 = a["U1"]
    on_fpga = collections.defaultdict(list)
    for bx, n in U1.items():
        on_fpga[n].append(bx)

    if before:
        B, b = read_netlist(before)
        for r in b:
            if r in ("U1", "U7", "U10", "U13") or r not in a:
                continue
            for p, n in b[r].items():
                want = INTENDED.get((r, p), RENAMES.get(n, n))
                got = a[r].get(p)
                if got != want and not (want.startswith("unconnected") and got.startswith("unconnected")):
                    errs.append(f"changed: {r}.{p} {n} -> {got} (wanted {want})")
        for r in ("U10", "U13"):
            for p, n in b[r].items():
                chk(a[r][p].startswith("unconnected") if p == "7" else a[r][p] == n, f"{r}.{p}: {n} -> {a[r][p]}")
        print("removed:", " ".join(sorted(set(b) - set(a))))
        print("added:  ", " ".join(sorted(set(a) - set(b))))

    # FPGA supplies
    chk(len(U1) == 225, f"U1 has {len(U1)} pins")
    for bx, r in pins.items():
        p, n = r["pad"], U1.get(bx, "")
        want = ("+0V95" if p in ("VCC", "VCCA_TL", "VCCA_TR", "VCCA_BR") else "+0V95_" + p if p == "VCCA_BL" else
                "+1V8" if p == "VCCAUX" or re.match(r"VCCIO\d[AB]$", p) else
                "+3V3" if p.startswith("VCCIO33") else "GND" if p in ("GND", "VQPS_GND") else None)
        if want:
            chk(n == want, f"{bx} {p} on {n}")
    # only PLL_BL0 is used: VCCA_BL filtered (bead, 1u + 47n), the other VCCA straight on VCC (tools/sch_decoupling_47n.py)
    refs = [r for r, _ in A["+0V95_VCCA_BL"]]
    chk(sum(r.startswith("FB") for r in refs) == 1 and sum(r.startswith("C") for r in refs) == 2,
        f"VCCA_BL filter: {refs}")

    # HyperRAM and flash
    for net, bx in HYPERRAM.items():
        chk(U1.get(bx) == net, f"{net} at {bx}: {U1.get(bx)}")
        chk(any(r == "U9" for r, _ in A[net]), f"{net} not at the HyperRAM")
    flash = {"C2": ("FLASH_CS_N", "P1"), "B2": ("FLASH_CLK", "N1"), "D3": ("FLASH_IO0", "M1"),
             "D2": ("FLASH_IO1", "L1"), "C4": ("FLASH_IO2", "H5"), "D4": ("FLASH_IO3", "H4")}
    for fp, (net, bx) in flash.items():
        chk(a["U7"][fp] == net and U1[bx] == net, f"flash {fp}: {a['U7'][fp]} / U1.{bx}: {U1[bx]}")
    chk(a["U7"]["B4"] == "+1V8" and a["U7"]["B3"] == "GND" and a["U7"]["A4"] == "FLASH_RESET_N", "flash power/reset")

    def pulls(net, rail):
        return [r for r, _ in A[net] if r.startswith("R") and any(x == r for x, _ in A[rail])]
    for net, rail in [("FLASH_CS_N", "+1V8"), ("FLASH_IO2", "+1V8"), ("FLASH_IO3", "+1V8"),
                      ("FLASH_RESET_N", "+1V8"), ("CDONE", "+1V8"), ("CSI", "+1V8"), ("CRESET_N", "+1V8"),
                      ("TCK", "+3V3"), ("TMS", "+3V3"), ("TDI", "+3V3"), ("TDO", "+3V3"), ("XLAT_OE_N", "+1V8"),
                      ("TEST_N", "+1V8"), ("REF_RES_2A", "GND"), ("REF_RES_3A", "GND"), ("REF_RES_4A", "GND")]:
        chk(len(pulls(net, rail)) == 1, f"pull-up/down {net} to {rail}: {pulls(net, rail)}")
    chk(any(r.startswith("C") for r, _ in A["CRESET_N"]), "CRESET_N has no RC capacitor")
    for net, bx in (("TCK", "N4"), ("TMS", "N3"), ("TDI", "P3"), ("TDO", "M4"), ("CRESET_N", "J5"), ("TEST_N", "E2"),
                    ("CDONE", "L3"), ("CSI", "N2"), ("CLK100M", "P2")):
        chk(U1[bx] == net, f"{net} at {bx}: {U1[bx]}")
    for net, p in (("TCK", "1"), ("TDI", "2"), ("TMS", "3"), ("TDO", "4")):
        chk(a["J2"][p] == net, f"J2.{p}: {a['J2'][p]}")

    # header: through a translator (HSIO side) or straight to HVIO
    xl = [r for r in a if a[r].get("7") == "XLAT_OE_N"]
    chk(len(xl) == 4, f"translators: {xl}")
    via_xl = set()
    for r in xl:
        d = a[r]
        chk(d["14"] == "+1V8" and d["13"] == "+3V3" and d["8"] == "GND"
            and all(d[p] == "+1V8" for p in ("15", "16", "5", "6")), f"{r} supplies/DIR: {d}")
        for i in range(4):
            an, bn = d[str(1 + i)], d[str(12 - i)]
            via_xl.add(bn)
            chk(an == bn + "_1V8", f"{r} channel {i + 1}: {an} / {bn}")
            chk(len(on_fpga[an]) == 1 and pins[on_fpga[an][0]]["type"] == "HSIO", f"{an} not on one HSIO ball")
    hv_out = collections.Counter()
    for p, net in a["J1"].items():
        if net in ("+5V", "GND") or re.match(r"AD[AB]\d$", net) or net in via_xl:
            continue
        bx = on_fpga[net]
        chk(len(bx) == 1 and pins[bx[0]]["type"] == "HVIO", f"J1.{p} {net}: {bx}")
        if bx and net not in ("RX", "HT_SDATA", "CUK_SDATA"):
            hv_out[pins[bx[0]]["bank"]] += 1
    for net in ("LED1_R", "LED1_G", "LED1_B", "LED2_R", "LED2_G", "LED2_B"):
        bx = on_fpga[net]
        chk(len(bx) == 1 and pins[bx[0]]["type"] == "HVIO", net)
        hv_out[pins[bx[0]]["bank"]] += 1
    chk(max(hv_out.values()) <= 6, f"more than 6 outputs in an HVIO bank: {dict(hv_out)}")

    # ADC and mux
    for ch, mux in (("A", "U10"), ("B", "U13")):
        for s, p in (("SEL0", "11"), ("SEL1", "10"), ("SEL2", "9")):
            net = f"AD{ch}{s}"
            chk(a[mux][p] == net, f"{mux}.{p}: {a[mux][p]}")
            chk(len(on_fpga[net]) == 1 and pins[on_fpga[net][0]]["type"] == "HSIO", net)
        for s in ("CS_N", "SCLK", "SDO"):
            net = f"ADC{ch}_{s}"
            chk(len(on_fpga[net]) == 1 and pins[on_fpga[net][0]]["type"] == "HSIO", net)
    for r in ("U12", "U15"):
        chk(a[r]["4"] == "+1V8", f"{r} DVDD on {a[r]['4']}")

    single = [n for n, nodes in A.items() if len(nodes) == 1 and not n.startswith("unconnected")]
    chk(not single, f"single-node nets: {single}")
    for n in ("+0V75", "+1V2", "+1V8_HR", "VCC_SENSE_P", "VCC_SENSE_N", "+0V75_PLLDIG", "PG_3V3"):
        chk(n not in A, f"{n} still present")

    print("HVIO outputs per bank:", dict(hv_out))
    print(f"{len(errs)} errors")
    for e in errs:
        print("  " + e)
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
