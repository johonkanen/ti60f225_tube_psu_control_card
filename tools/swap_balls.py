"""Move nets to other Ti60F225 balls on the schematic (U1 stubs only), in the sheets' drawing style.

    python3 -I tools/swap_balls.py NET=BALL [NET=BALL ...]

Each NET's label leaves the U1 ball(s) it is on now, which get a no-connect flag, and goes onto BALL.
BALL must be a free user I/O (no-connect now) or one of the balls being vacated in the same call, so
nets can also trade balls. Afterwards rerun efinity/pinplan/run.sh --compile and tools/check_schematic.py.
"""
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sch_edit import Sheet, check_geometry, load_project_lib, normalize_labels  # noqa: E402

HW = Path(__file__).resolve().parent.parent / "hardware"
FPGA = "ti60f225:Ti60F225"


def main():
    moves = dict(a.split("=", 1) for a in sys.argv[1:])
    if not moves:
        sys.exit(__doc__)
    libs = {}
    sheets = [Sheet(p, libs) for p in sorted(glob.glob(str(HW / "sheets" / "*.kicad_sch")))]
    load_project_lib(libs, HW / "lib" / "ti60f225.kicad_sym", "Ti60F225", FPGA)
    for lib_id in {d["lib_id"] for sh in sheets for _, _, d in sh.symbols()} - set(libs):
        lib, name = lib_id.split(":")            # project symbols not embedded where the sheet expects them
        load_project_lib(libs, HW / "lib" / f"{lib}.kicad_sym", name, lib_id)
    if bad := check_geometry(sheets):
        sys.exit(f"pin geometry check failed: {bad[:5]}")
    where = {}                                   # ball -> (sheet, net or None)
    for sh in sheets:
        for _, _, d in sh.symbols():
            if d["ref"] == "U1":
                for pin in libs[d["lib_id"]].unit_pins(d["unit"]):
                    where[pin] = (sh, sh.stub_net("U1", pin))
    vacated = {b for b, (_, n) in where.items() if n in moves}
    for net, b in moves.items():
        if b not in where:
            sys.exit(f"{b}: not a U1 ball")
        if where[b][1] is not None and b not in vacated:
            sys.exit(f"{b} carries {where[b][1]}: not free")
        if not any(n == net for _, n in where.values()):
            sys.exit(f"{net}: not on U1")
    for b in sorted(vacated):
        where[b][0].relabel_pin("U1", b, None)
    for net, b in moves.items():
        where[b][0].relabel_pin("U1", b, net)
        print(f"  {net} -> {b}")
    normalize_labels(sheets)
    if bad := check_geometry(sheets):
        sys.exit(f"pin geometry check failed after editing: {bad[:5]}")
    for sh in sheets:
        sh.save()
    print(f"swap_balls: {len(moves)} nets moved, {len(vacated - set(moves.values()))} balls freed")


if __name__ == "__main__":
    main()
