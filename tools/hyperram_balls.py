"""Set the HyperRAM balls in the two places outside the schematic that hold them (after tools/swap_balls.py).

    python3 -I tools/hyperram_balls.py HR_DQ0=R12 HR_CK=P8 ...

- efinity/pinplan/hyperram_gpio.isf: the design.assign_pkg_pin lines of the hbc_* GPIOs;
- tools/check_schematic.py: the HYPERRAM table.
Nets not named keep their ball.
"""
import re
import sys
from pathlib import Path

R = Path(__file__).resolve().parent.parent
GPIO = {"HR_CK": "hbc_ck_p", "HR_CS_N": "hbc_cs_n", "HR_RESET_N": "hbc_rst_n", "HR_RWDS": "hbc_rwds",
        **{f"HR_DQ{i}": f"hbc_dq{i}" for i in range(8)}}


def main():
    moves = dict(a.split("=", 1) for a in sys.argv[1:])
    if not moves or set(moves) - set(GPIO):
        sys.exit(__doc__)
    isf = R / "efinity/pinplan/hyperram_gpio.isf"
    t = isf.read_text()
    for net, ball in moves.items():
        t, n = re.subn(rf'(design\.assign_pkg_pin\("{GPIO[net]}",")[A-R]\d+("\))', rf"\g<1>{ball}\g<2>", t)
        if n != 1:
            sys.exit(f"{net}: {n} assign_pkg_pin lines in {isf.name}")
    isf.write_text(t)
    chk = R / "tools/check_schematic.py"
    t = chk.read_text()
    s, e = t.index("HYPERRAM = {"), t.index("}", t.index("HYPERRAM = {")) + 1
    table = dict(re.findall(r'"(HR_\w+)": "([A-R]\d+)"', t[s:e]))
    table.update(moves)
    if len(set(table.values())) != len(table):
        sys.exit(f"two HyperRAM nets on one ball: {table}")
    items = [f'"{k}": "{v}"' for k, v in sorted(table.items())]
    body = "HYPERRAM = {" + ", ".join(items[:6]) + ",\n            " + ", ".join(items[6:]) + "}"
    chk.write_text(t[:s] + body + t[e:])
    print("hyperram_balls:", " ".join(f"{k}={v}" for k, v in sorted(table.items())))


if __name__ == "__main__":
    main()
