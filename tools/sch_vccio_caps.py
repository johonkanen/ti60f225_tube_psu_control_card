"""One-off schematic edit (2026-11-01): HSIO bank decoupling closer to the Efinix Ti60 hardware checklist.

    python3 -I tools/sch_vccio_caps.py

- adds 10 nF + 1 nF (0201) per used HSIO bank, 1A 1B 2A 2B 4A 4B, as C166-C177 (bank order, 10n then 1n),
  next to the existing per-bank 1 uF + 100 nF on the fpga_power sheet;
- removes the 1 uF + 100 nF of banks 3A (C136/C137) and 3B (C138/C139), unused since the translator inputs moved
  to 2A/2B (the checklist asks no caps for an unused bank; VCCIO3A/3B stay on +1V8).
tools/phase5_decaps.py places the new caps at their bank's VCCIO balls. Refuses to run twice.
"""
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase3_schematic import Flow, content_bbox, fit_paper, place_passive  # noqa: E402
from sch_edit import Sheet, check_geometry, load_project_lib, normalize_labels  # noqa: E402

HW = Path(__file__).resolve().parent.parent / "hardware"
USED_BANKS = ["1A", "1B", "2A", "2B", "4A", "4B"]
DROP = ["C136", "C137", "C138", "C139"]


def main():
    libs = {}
    sheets = {Path(p).stem: Sheet(p, libs) for p in sorted(glob.glob(str(HW / "sheets" / "*.kicad_sch")))}
    for lib_id in {d["lib_id"] for sh in sheets.values() for _, _, d in sh.symbols()} - set(libs):
        lib, name = lib_id.split(":")
        load_project_lib(libs, HW / "lib" / f"{lib}.kicad_sym", name, lib_id)
    if bad := check_geometry(sheets.values()):
        sys.exit(f"pin geometry check failed: {bad[:5]}")
    sh = sheets["fpga_power"]
    have = {d["ref"] for _, _, d in sh.symbols()}
    if "C166" in have or not set(DROP) <= have:
        sys.exit("already done")
    for ref in DROP:
        sh.remove(ref)
    _, _, _, ybot = content_bbox(sh)
    flow = Flow(25.4, ybot + 12.7, 360)
    n = 166
    for bank in USED_BANKS:
        for kind in ("10n", "1n"):
            place_passive(sh, flow, None, kind, "+1V8", "GND", ref=f"C{n}")
            n += 1
    fit_paper(sh, flow.max_x, flow.bottom())
    normalize_labels(sheets.values())
    if bad := check_geometry(sheets.values()):
        sys.exit(f"pin geometry check failed after editing: {bad[:5]}")
    sh.save()
    print(f"sch_vccio_caps: removed {', '.join(DROP)}; added C166-C{n - 1}")


if __name__ == "__main__":
    main()
