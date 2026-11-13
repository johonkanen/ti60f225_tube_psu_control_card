"""One KiCadRoutingTools route.py step with this board's rules, nets passed from Python (names contain spaces).

    python3 -I tools/krt_route.py IN.kicad_pcb OUT.kicad_pcb GROUP[,GROUP...] [route.py options...]

GROUP is a key of tools/phase5/route_groups.json (a list of net names or patterns) or a literal net pattern.
Rules as in tools/phase5_route.sh: F.Cu + In2.Cu, 0.1 mm tracks, 0.125 mm clearance, 0.30/0.15 vias, 0.025 mm grid.
The project and rule files are copied next to OUT; the log goes to OUT with .log, the summary to .json.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

R = Path(__file__).resolve().parent.parent
K = Path(os.environ.get("KRT", Path.home() / "dev/KiCadRoutingTools"))
BASE = ["--layers", "F.Cu", "In2.Cu", "--track-width", "0.1", "--via-size", "0.3", "--via-drill", "0.15",
        "--no-bga-zones", "U1", "U7", "U9", "--clearance", "0.125", "--fab-tier", "advanced", "--escalation", "off",
        "--no-fix-drc-settings", "--grid-step", "0.025"]


def main():
    src, dst, groups, *opts = sys.argv[1:]
    src, dst = Path(src).resolve(), Path(dst).resolve()
    table = json.load(open(R / "tools/phase5/route_groups.json"))
    nets = []
    for g in groups.split(","):
        nets += table.get(g, [g])
    if "--layers" in opts:                       # a step may override the layer set (B.Cu hops to bottom parts)
        base = BASE[:]
        del base[0:3]
    else:
        base = BASE
    if not any(o == "--layer-costs" for o in opts) and "--layers" not in opts:
        opts += ["--layer-costs", "1", "3"]
    cmd = [str(K / ".venv/bin/python"), "-X", "utf8", "py_router/route.py", str(src), str(dst), "--nets", *nets,
           *base, *opts, "--json-out", str(dst.with_suffix(".json"))]
    env = dict(os.environ)
    env.setdefault("KICAD_RIP_PREEXISTING", "0")
    with open(dst.with_suffix(".log"), "w") as log:
        rc = subprocess.run(cmd, cwd=K, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
    for x in ("kicad_pro", "kicad_dru"):
        shutil.copy(R / f"hardware/control_card.{x}", dst.with_suffix(f".{x}"))
    text = open(dst.with_suffix(".log"), errors="replace").read().splitlines()
    for line in text:
        if line.lstrip().startswith(("Single-ended:", "Multi-point:", "Total vias:", "Ships")):
            print("  " + line.strip())
    try:
        s = json.load(open(dst.with_suffix(".json")))
        failed = [n for k, v in s.items() if "fail" in k or "open" in k if isinstance(v, list) for n in v]
        if failed:
            print("  not routed:", ", ".join(map(str, failed)))
    except (OSError, ValueError):
        pass
    if rc:
        print("\n".join(text[-15:]))
        sys.exit(rc)


if __name__ == "__main__":
    main()
