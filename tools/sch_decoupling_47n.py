"""One-off schematic edit (2026-11-13): leaner Ti60 decoupling, the user's scheme instead of the HWC table.

    python3 -I tools/sch_decoupling_47n.py

- one 47 nF 0201 at every used power ball (8 VCC, 4 VCCAUX, 12 HSIO VCCIO, 4 VCCIO33, 1 VCCA_BL); no 1 nF/10 nF;
- one 100 nF per rail near the FPGA: VCC (C109), VCCAUX (C122), HSIO VCCIO (C129), VCCIO33 (C153);
- one 47 uF per rail, placed at its regulator's output (HWC: at least 47 uF there): +0V95 C106, +1V8 C125,
  +3V3 C147 (was 4u7, now 47u 0603); the FPGA-side 10u/4u7/1u go;
- VCCA: only PLL_BL0 is used (efinity/pinplan, HyperRAM clock). VCCA_TL/TR/BR go straight to +0V95 without caps
  or bead (HWC: unused PLLs need no decoupling, VCCA always on VCC); VCCA_BL keeps FB8 with 1u (C96) + 47n (C100).
VCCIO33_BL stays decoupled: bank BL carries JTAG (M4/N3/N4/P3). tools/phase5_decaps.py places the caps.
Refuses to run twice.
"""
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sch_edit import Sheet, check_geometry, load_project_lib, normalize_labels  # noqa: E402

HW = Path(__file__).resolve().parent.parent / "hardware"
C = lambda *n: [f"C{i}" for i in n]
C47N = C(110, 114, 115, 116, 117, 118, 119, 120,          # VCC
         123, 124, 131, 133,                              # VCCAUX
         *range(166, 178),                                # HSIO VCCIO, 2 per used bank
         146, 149, 152, 155,                              # VCCIO33 TL TR BL BR
         100)                                             # VCCA_BL
SET = {"C96": "1u", "C153": "100n"}
C47U = "C147"
DROP = (C(107, 108, 111, 112, 113)                                          # VCC
        + C(*range(86, 96), *range(101, 106), 97, 98, 99) + ["FB6", "FB7", "FB9"]   # VCCA
        + C(121, 126, 127, 128, 130, 132, 134, 135, 140, 141, 142, 143)    # VCCAUX, HSIO
        + C(144, 145, 148, 150, 151, 154))                                  # VCCIO33
DIRECT = ["TL", "TR", "BR"]                      # VCCA of unused PLLs: on +0V95
FLAGS = {"TL": "#FLG15", "TR": "#FLG16", "BR": "#FLG18"}   # their PWR_FLAGs (+0V95 has its own)


def main():
    libs = {}
    sheets = {Path(p).stem: Sheet(p, libs) for p in sorted(glob.glob(str(HW / "sheets" / "*.kicad_sch")))}
    for lib_id in {d["lib_id"] for sh in sheets.values() for _, _, d in sh.symbols()} - set(libs):
        lib, name = lib_id.split(":")
        load_project_lib(libs, HW / "lib" / f"{lib}.kicad_sym", name, lib_id)
    if bad := check_geometry(sheets.values()):
        sys.exit(f"pin geometry check failed: {bad[:5]}")
    sh = sheets["fpga_power"]
    have = {d["ref"]: d for _, _, d in sh.symbols()}
    if "FB6" not in have:
        sys.exit("already done")
    missing = [r for r in DROP + C47N + list(SET) + [C47U] if r not in have]
    if missing:
        sys.exit(f"not on fpga_power: {missing}")
    for ref in DROP + [FLAGS[c] for c in DIRECT]:
        sh.remove(ref)
    for ref in C47N:
        sh.set_props(ref, Value="47n")
    for ref, v in SET.items():
        sh.set_props(ref, Value=v)
    sh.set_props(C47U, Value="47u", Footprint="Capacitor_SMD:C_0603_1608Metric")
    for c in DIRECT:
        n = sh.relabel(f"+0V95_VCCA_{c}", "+0V95")
        if n != 1:
            sys.exit(f"+0V95_VCCA_{c}: {n} labels left after removing its filter (want 1, the U1 ball)")
    normalize_labels(sheets.values())
    if bad := check_geometry(sheets.values()):
        sys.exit(f"pin geometry check failed after editing: {bad[:5]}")
    for s in sheets.values():
        s.save()
    print(f"sch_decoupling_47n: removed {len(DROP)} parts, {len(C47N)} caps now 47n, {C47U} 47u, "
          f"VCCA_{'/'.join(DIRECT)} on +0V95")


if __name__ == "__main__":
    main()
