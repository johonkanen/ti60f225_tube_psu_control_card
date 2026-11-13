"""One-off schematic edit (2026-11-13): decoupling for HSIO bank 3A, now used by translator inputs.

    python3 -I tools/sch_bank3a_caps.py

Adds one 47 nF 0201 per VCCIO3A ball (F14, G12) as C178, C179 on the fpga_power sheet, like the other used banks.
tools/phase5_decaps.py places them at their balls. Refuses to run twice.
"""
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase3_schematic import Flow, content_bbox, fit_paper, place_passive  # noqa: E402
from sch_edit import Sheet, check_geometry, load_project_lib, normalize_labels  # noqa: E402

HW = Path(__file__).resolve().parent.parent / "hardware"
NEW = ["C178", "C179"]


def main():
    libs = {}
    sheets = {Path(p).stem: Sheet(p, libs) for p in sorted(glob.glob(str(HW / "sheets" / "*.kicad_sch")))}
    for lib_id in {d["lib_id"] for sh in sheets.values() for _, _, d in sh.symbols()} - set(libs):
        lib, name = lib_id.split(":")
        load_project_lib(libs, HW / "lib" / f"{lib}.kicad_sym", name, lib_id)
    if bad := check_geometry(sheets.values()):
        sys.exit(f"pin geometry check failed: {bad[:5]}")
    sh = sheets["fpga_power"]
    have = {d["ref"] for s in sheets.values() for _, _, d in s.symbols()}
    if set(NEW) & have:
        sys.exit("already done")
    _, _, _, ybot = content_bbox(sh)
    flow = Flow(25.4, ybot + 12.7, 360)
    for ref in NEW:
        place_passive(sh, flow, None, "47n", "+1V8", "GND", ref=ref)
    fit_paper(sh, flow.max_x, flow.bottom())
    normalize_labels(sheets.values())
    if bad := check_geometry(sheets.values()):
        sys.exit(f"pin geometry check failed after editing: {bad[:5]}")
    sh.save()
    print(f"sch_bank3a_caps: added {', '.join(NEW)}")


if __name__ == "__main__":
    main()
