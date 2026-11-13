"""One-off schematic edit (2026-11-13): compact the fpga_power sheet after tools/sch_decoupling_47n.py.

    python3 -I tools/sch_compact_fpga_power.py

The U1 power/GND units stay; the VCCA_BL filter moves beside them; the caps go into one row per rail
(47n per ball, then the rail's 100n and 47u): VCC, 1.8 V (VCCAUX, HSIO VCCIO), 3.3 V (VCCIO33). Paper A2 -> A3.
"""
import glob
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase3_schematic import fit_paper  # noqa: E402
from sch_edit import Sheet, check_geometry, load_project_lib  # noqa: E402

HW = Path(__file__).resolve().parent.parent / "hardware"
PITCH, X0 = 12.7, 30.48
ROWS = [
    (119.38, "C119 C120 C114 C115 C116 C117 C118 C110 C109 C106"),                          # VCC
    (152.40, "C123 C124 C131 C133 C166 C167 C168 C169 C170 C171 C172 C173 C174 C175 C176 C177 C122 C129 C125"),
    (185.42, "C146 C149 C152 C155 C153 C147"),                                                # VCCIO33
]
FILTER = {"FB8": (180.34, 45.72)}                 # C96/C100/#FLG17 keep their places relative to FB8
FOLLOW = {"C96": (12.7, 10.16), "C100": (25.4, 10.16), "#FLG17": (38.1, 7.62)}


def main():
    libs = {}
    sheets = [Sheet(p, libs) for p in sorted(glob.glob(str(HW / "sheets" / "*.kicad_sch")))]
    for lib_id in {d["lib_id"] for sh in sheets for _, _, d in sh.symbols()} - set(libs):
        lib, name = lib_id.split(":")
        load_project_lib(libs, HW / "lib" / f"{lib}.kicad_sym", name, lib_id)
    sh = next(s for s in sheets if s.name == "fpga_power")
    at = {}
    for s, e, d in sh.symbols():
        m = re.search(r"\(at ([-\d.]+) ([-\d.]+)", sh.text[s:e])
        at[d["ref"]] = (float(m.group(1)), float(m.group(2)))
    if "A2" not in sh.text[:400]:
        sys.exit("already done")
    target = {}
    for y, refs in ROWS:
        for i, r in enumerate(refs.split()):
            target[r] = (X0 + i * PITCH, y)
    fx, fy = FILTER["FB8"]
    target["FB8"] = (fx, fy)
    target.update({r: (fx + dx, fy + dy) for r, (dx, dy) in FOLLOW.items()})
    left = {d["ref"] for _, _, d in sh.symbols()} - set(target) - {"U1"}
    if left:
        sys.exit(f"not placed: {sorted(left)}")
    for r, (x, y) in target.items():
        sh.move(r, round(x - at[r][0], 2), round(y - at[r][1], 2))
    paper = fit_paper(sh, 0, 0)
    if bad := check_geometry(sheets):
        sys.exit(f"pin geometry check failed: {bad[:5]}")
    sh.save()
    print(f"sch_compact_fpga_power: {len(target)} symbols moved, paper {paper}")


if __name__ == "__main__":
    main()
