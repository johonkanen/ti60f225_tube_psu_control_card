"""Build the Efinix F225 footprint (Ti60F225: 225-ball FBGA, 10 x 10 mm, 0.65 mm pitch).

Run with KiCad's bundled Python (pcbnew), from the repository root:
    ~/dev/proteus2kicad/bin/kicad_env.sh bash -c \
        '"$KICAD_MOUNT/bin/python3.11" -I tools/make_f225_footprint.py \
         reference/ti60f225_pinout.csv hardware/lib/control_card.pretty'

Geometry:
- 15 x 15 full array, rows A-R without I, O, Q, columns 1-15, 0.65 mm pitch,
  10 x 10 mm body (Ti60 data sheet v3.9, Table 3).
- Top view, not mirrored: A1 top left, columns increase to the right, rows
  downward. Checked against the proven Ti60F225 card's IPC-356 netlist.
- Pads copy the proven card: 0.30 mm round copper (not mask-defined); 0.35 mm
  mask opening and 0.30 mm paste as on the Agilex B18A footprint.
"""
import csv
import os
import sys

import pcbnew

NAME = "Efinix_F225"
BODY = 10.0
PITCH = 0.65
ROWS = "ABCDEFGHJKLMNPR"
COLS = 15
PAD = 0.30
MASK_EXPANSION = 0.025
COURTYARD_MARGIN = 0.5


def mm(v):
    return pcbnew.FromMM(v)


def v(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


def poly(fp, layer, pts, width):
    for a, b in zip(pts, pts[1:]):
        s = pcbnew.PCB_SHAPE(fp, pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(v(*a))
        s.SetEnd(v(*b))
        s.SetLayer(layer)
        s.SetWidth(mm(width))
        fp.Add(s)


def ball_xy(ball):
    row = ROWS.index(ball[0])
    col = int(ball[1:]) - 1
    off = (COLS - 1) / 2
    return (round((col - off) * PITCH, 4), round((row - off) * PITCH, 4))


def main(table, out_dir):
    balls = [r["ball"] for r in csv.DictReader(open(table))]
    expected = {f"{r}{c}" for r in ROWS for c in range(1, COLS + 1)}
    if set(balls) != expected or len(balls) != len(expected):
        sys.exit(f"{table}: ball list does not match the 15 x 15 array")

    fp = pcbnew.FOOTPRINT(None)
    fp.SetFPID(pcbnew.LIB_ID("control_card", NAME))
    fp.SetLibDescription("Efinix F225 225-ball FBGA, 10x10 mm, 0.65 mm pitch, 15x15 array "
                         "(Titanium Ti60F225); 0.30 mm NSMD pads as on the proven Ti60F225 card")
    fp.SetKeywords("BGA FBGA Efinix Titanium Ti60 F225")
    fp.SetAttributes(pcbnew.FP_SMD)

    for ball in sorted(balls, key=lambda b: (ROWS.index(b[0]), int(b[1:]))):
        pad = pcbnew.PAD(fp)
        pad.SetNumber(ball)
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetLayerSet(pad.SMDMask())
        pad.SetSize(v(PAD, PAD))
        pad.SetLocalSolderMaskMargin(mm(MASK_EXPANSION))
        pad.SetPosition(v(*ball_xy(ball)))
        fp.Add(pad)

    h = BODY / 2
    c = 0.8  # pin-1 chamfer on the fab outline
    poly(fp, pcbnew.F_Fab, [(-h + c, -h), (h, -h), (h, h), (-h, h), (-h, -h + c), (-h + c, -h)], 0.1)
    s = h + 0.11
    a = 1.0  # silkscreen corner arm length
    poly(fp, pcbnew.F_SilkS, [(-s, -s + a), (-s, -s), (-s + a, -s)], 0.12)
    poly(fp, pcbnew.F_SilkS, [(s - a, -s), (s, -s), (s, -s + a)], 0.12)
    poly(fp, pcbnew.F_SilkS, [(s, s - a), (s, s), (s - a, s)], 0.12)
    poly(fp, pcbnew.F_SilkS, [(-s + a, s), (-s, s), (-s, s - a)], 0.12)
    dot = pcbnew.PCB_SHAPE(fp, pcbnew.SHAPE_T_CIRCLE)  # pin-1 marker outside the A1 corner
    dot.SetCenter(v(-s - 0.35, -s - 0.35))
    dot.SetEnd(v(-s - 0.35 + 0.1, -s - 0.35))
    dot.SetLayer(pcbnew.F_SilkS)
    dot.SetWidth(mm(0.2))
    fp.Add(dot)
    k = h + COURTYARD_MARGIN
    poly(fp, pcbnew.F_CrtYd, [(-k, -k), (k, -k), (k, k), (-k, k), (-k, -k)], 0.05)

    fp.Reference().SetPosition(v(0, -k - 1))
    fp.Value().SetText(NAME)
    fp.Value().SetPosition(v(0, k + 1))
    fp.Value().SetLayer(pcbnew.F_Fab)

    os.makedirs(out_dir, exist_ok=True)
    pcbnew.PCB_IO_KICAD_SEXPR().FootprintSave(os.path.abspath(out_dir), fp)
    print(f"wrote {out_dir}/{NAME}.kicad_mod with {len(fp.Pads())} pads")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
