"""One-off schematic edit (2026-11-14, layout experiment "U1 at 180 deg"): parts that follow the new bank use.

    python3 -I tools/sch_rot180.py

1. Bank 3B now carries ADC nets (it faces the ADC parts on the west side): one 47 nF 0201 per VCCIO3B ball
   (J11, L14) as C180, C181 on the fpga_power sheet, like the other used banks. tools/phase5_decaps.py places them.
2. HR_DQ3 leaves ball E2 (the HyperRAM moves from bank 1B to 4A/4B, see tools/swap_balls.py call in
   CONVERSION_PLAN.md): E2 stays TEST_N and keeps its 10 k pull-up R56, on a net of its own, TEST_N.
Refuses to run twice.
"""
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase3_schematic import Flow, content_bbox, fit_paper, place_passive  # noqa: E402
from sch_edit import Sheet, check_geometry, load_project_lib, normalize_labels  # noqa: E402

HW = Path(__file__).resolve().parent.parent / "hardware"
NEW = ["C180", "C181"]


def main():
    libs = {}
    sheets = {Path(p).stem: Sheet(p, libs) for p in sorted(glob.glob(str(HW / "sheets" / "*.kicad_sch")))}
    for lib_id in {d["lib_id"] for sh in sheets.values() for _, _, d in sh.symbols()} - set(libs):
        lib, name = lib_id.split(":")
        load_project_lib(libs, HW / "lib" / f"{lib}.kicad_sym", name, lib_id)
    if bad := check_geometry(sheets.values()):
        sys.exit(f"pin geometry check failed: {bad[:5]}")
    have = {d["ref"] for s in sheets.values() for _, _, d in s.symbols()}
    if set(NEW) & have:
        sys.exit("already done")
    sh = sheets["fpga_power"]
    _, _, _, ybot = content_bbox(sh)
    flow = Flow(25.4, ybot + 12.7, 360)
    for ref in NEW:
        place_passive(sh, flow, None, "47n", "+1V8", "GND", ref=ref)
    fit_paper(sh, flow.max_x, flow.bottom())
    # TEST_N: the pull-up's signal pin and ball E2 on a net of their own
    done = 0
    for s in sheets.values():
        for _, _, d in s.symbols():
            if d["ref"] == "R56":
                for pin in libs[d["lib_id"]].unit_pins(d["unit"]):
                    if s.stub_net("R56", pin) == "HR_DQ3":
                        s.relabel_pin("R56", pin, "TEST_N")
                        done += 1
            if d["ref"] == "U1" and "E2" in libs[d["lib_id"]].unit_pins(d["unit"]):
                if s.stub_net("U1", "E2") is not None:
                    sys.exit(f"U1.E2 still carries {s.stub_net('U1', 'E2')}: move HR_DQ3 off it first (swap_balls.py)")
                s.relabel_pin("U1", "E2", "TEST_N")
                done += 1
    if done != 2:
        sys.exit(f"TEST_N: {done} of 2 pins found")
    normalize_labels(sheets.values())
    if bad := check_geometry(sheets.values()):
        sys.exit(f"pin geometry check failed after editing: {bad[:5]}")
    for s in sheets.values():
        s.save()
    print(f"sch_rot180: added {', '.join(NEW)}; TEST_N on U1.E2 and R56")


if __name__ == "__main__":
    main()
