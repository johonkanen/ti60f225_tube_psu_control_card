"""Phase 4 pin plan: check the schematic's Ti60F225 ball assignment in Efinity's Interface Designer.

Run with efinity/pinplan/run.sh (exports the KiCad netlist, then runs this with Efinity 2026.1):
    python3 efinity/pinplan/pinplan.py NETLIST

- Every FPGA user I/O comes from the schematic netlist (U1 ball -> net), so the check covers exactly
  what is drawn. Configuration pins (SSL_N, CCK, CDI0-3, CSI) are left to the configuration block.
- The HyperRAM GPIOs are imported unchanged from the user's AC PSU Ti60 design
  (hyperram_gpio.isf, exported from ti60_ac_psu tsemac_soc.peri.xml): DDIO in/out registers, clocks
  ram_clk / ram_clk90 / ram_clk_cal. Their balls must equal the schematic's HR_* balls.
- Their PLL (hyperram_pll.isf: PLL_TR0, 50 MHz reference, M = 4) moves to PLL_BL0 with the board's
  100 MHz oscillator on GPIOL_P_00_PLLIN0 (P2) and M = 2, so the VCO and all output clocks stay the same.
  Unused here: CLKOUT1 (io_tseClk, the AC PSU's Ethernet clock) is disabled.

Writes build/ti60f225_pinplan.peri.xml (+ .isf, outflow reports) and ../../reference/pin_assignment.csv.
"""
import csv
import os
import re
import sys

sys.path.append(os.environ["EFXPT_HOME"] + "/bin")
from api_service.design import DesignAPI  # noqa: E402
import api_service.excp.design_excp as DesignException  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
BUILD = os.path.join(HERE, "build")
DEVICE = "Ti60F225"
NAME = "ti60f225_pinplan"

INPUTS = {"RX", "HT_SDATA", "CUK_SDATA", "ADCA_SDO", "ADCB_SDO"}
CONFIG_NETS = {"FLASH_CS_N", "FLASH_CLK", "FLASH_IO0", "FLASH_IO1", "FLASH_IO2", "FLASH_IO3", "CSI"}
HR_GPIO = {"hbc_ck_p": "HR_CK", "hbc_cs_n": "HR_CS_N", "hbc_rst_n": "HR_RESET_N", "hbc_rwds": "HR_RWDS",
           **{f"hbc_dq{i}": f"HR_DQ{i}" for i in range(8)}}


def read_fpga_nets(netlist):
    """{ball: net} for U1 from a kicadsexpr netlist (net names without sheet prefix)."""
    t = open(netlist).read()
    t = t[t.index("(nets"):]
    balls = {}
    for blk in re.split(r"\n\t\t\(net\n", t)[1:]:
        name = re.search(r'\(name "([^"]*)"\)', blk).group(1).split("/")[-1]
        for nb in re.split(r"\(node\n", blk)[1:]:
            if re.search(r'\(ref "U1"\)', nb):
                balls[re.search(r'\(pin "([^"]+)"\)', nb).group(1)] = name
    return balls


def run_isf(d, path, edit=lambda s: s):
    """Execute an exported ISF file against the API object (ISF lines are `design.<method>(...)`)."""
    for line in open(path):
        line = line.strip()
        if line.startswith("design.") and "set_gpio_unused_state" not in line:
            eval(edit(line), {"design": d})  # noqa: S307  (Efinity's own exported commands)


def main():
    netlist = sys.argv[1]
    pins = {r["ball"]: r for r in csv.DictReader(open(os.path.join(ROOT, "reference", "ti60f225_pinout.csv")))}
    fpga = read_fpga_nets(netlist)
    os.makedirs(BUILD, exist_ok=True)

    d = DesignAPI(False)
    d.create(NAME, DEVICE, BUILD, overwrite=True)
    d.set_gpio_unused_state("INPUT_WEAK_PULLUP")
    for bank in d.get_all_iobank_name():
        if bank in ("TL", "TR", "BL", "BR"):
            d.set_iobank_voltage(bank, "3.3")
        elif re.match(r"\d[AB]$", bank):
            d.set_iobank_voltage(bank, "1.8")
    print("bank voltages:", d.get_iobank_voltage())

    # HyperRAM GPIOs from the AC PSU design, checked against the schematic
    run_isf(d, os.path.join(HERE, "hyperram_gpio.isf"))
    for g, net in HR_GPIO.items():
        ball = d.get_pkg_pin(g)
        if fpga.get(ball) != net:
            sys.exit(f"{g} is on {ball} in the AC PSU design, but the schematic has {fpga.get(ball)} there")

    # PLL: same VCO/outputs, PLL_BL0 with 100 MHz on P2
    def pll_edit(s):
        s = s.replace('"PLL_TR0"', '"PLL_BL0"')
        s = s.replace('"REFCLK_FREQ","50.0"', '"REFCLK_FREQ","100.0"')
        s = s.replace('"M","4"', '"M","2"')
        s = s.replace('"CLKOUT1_EN","1"', '"CLKOUT1_EN","0"')
        return s
    run_isf(d, os.path.join(HERE, "hyperram_pll.isf"), pll_edit)
    d.gen_pll_ref_clock("main_pll", pll_res="PLL_BL0", refclk_src="EXTERNAL", refclk_name="clk100m", ext_refclk_no="0")
    if d.get_pkg_pin("clk100m") != "P2" or fpga.get("P2") != "CLK100M":
        sys.exit(f"PLL_BL0 reference is on {d.get_pkg_pin('clk100m')}, schematic CLK100M on "
                 f"{[b for b, n in fpga.items() if n == 'CLK100M']}")
    print("main_pll:", d.calc_pll_clock("main_pll"))

    # every other user I/O from the schematic
    rows = []
    skip = set(HR_GPIO.values()) | CONFIG_NETS | {"CLK100M"}
    for ball, net in sorted(fpga.items()):
        r = pins[ball]
        if r["type"] not in ("HSIO", "HVIO") or net.startswith("unconnected") or net in skip:
            continue
        name = net.lower()
        g = (d.create_input_gpio if net in INPUTS else d.create_output_gpio)(name)
        d.assign_pkg_pin(g, ball)
        d.set_property(g, "IO_STANDARD", "3.3 V LVCMOS" if r["type"] == "HVIO" else "1.8 V LVCMOS")
        rows.append((net, "in" if net in INPUTS else "out", ball, r["pad"], r["bank"], r["type"]))
    for g, net in HR_GPIO.items():
        ball = d.get_pkg_pin(g)
        rows.append((net, "inout" if "dq" in g or "rwds" in g else "out", ball, pins[ball]["pad"], pins[ball]["bank"],
                     "HSIO (HyperRAM, AC PSU settings)"))
    rows.append(("CLK100M", "pllref", "P2", pins["P2"]["pad"], "1A", "HSIO (PLL_BL0 REFCLK0)"))
    for net in sorted(CONFIG_NETS):
        ball = next(b for b, n in fpga.items() if n == net)
        rows.append((net, "config", ball, pins[ball]["pad"], pins[ball]["bank"], "SPI active x4 configuration"))

    try:
        ok = d.check_design()
    except DesignException.PTDsgCheckException as excp:
        ok = False
        print("design check exception:", excp.get_msg())
    issues = d.get_design_check_issue()
    print("DESIGN CHECK", "PASSED" if ok else "FAILED", f"({len(issues)} issues)")
    for i in issues:
        print("  ", i)
    d.save()
    d.export_design(isf_file=os.path.join(BUILD, NAME + ".isf"))
    try:
        d.generate(enable_bitstream=False)
    except Exception as excp:  # noqa: BLE001
        print("generate failed:", excp)

    out = os.path.join(ROOT, "reference", "pin_assignment.csv")
    with open(out, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["net", "dir", "ball", "pad", "bank", "use"])
        w.writerows(sorted(rows, key=lambda r: (r[4], r[0])))
    print("wrote", out, len(rows), "signals")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
