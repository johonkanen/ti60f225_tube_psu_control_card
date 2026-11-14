"""Phase 5 routing: strip the old Agilex copper of nets that are routed anew (never a net with a U1 fan-out).

    $KICAD_MOUNT/bin/python3.11 -I tools/phase5_strip.py IN.kicad_pcb OUT.kicad_pcb

The power-good / enable lines still carry their Agilex tracks, cut where the old BGA was; the PG_1V8 one runs
down the east edge on F.Cu and across to U4, fencing U19 off from the translator inputs. All their tracks and vias
go; tools/phase5_route.sh routes them again after the signals. The JTAG nets lose their Agilex arcs at J2 and on
the bottom (everything outside U1's ball field; the fan-out escapes stay).
Two more pieces of Agilex copper go: the analog lines ADA0/ADA5/ADA6 on L4 (In3.Cu, the split supply plane; they are
routed again with the other analog nets), and the 0.8 mm +5V branch on L3 that ran west from J1 pin 1 just north of
the header's first row, across the L3 access to pins 1-13 (U6's +5V is routed with the supply stubs instead).
"""
import sys

import pcbnew

NETS = ("/Power/PG_1V8", "/Power/PG_0V95")
JTAG = ("/Configuration/TCK", "/Configuration/TMS", "/Configuration/TDI", "/Configuration/TDO")
FIELD = (86.9, 107.9, 97.1, 118.1)      # U1's ball field with its fan-out escapes: copper in here stays
KEEP = (87.3, 108.3, 96.7, 117.7)       # the ball field itself, inside the escapes' ends: the router's keep-out
PLUS5_JOINT = (106.425, 124.81)         # where the old +5V branch on L3 leaves the trunk at J1 pin 1


def outside(t):
    pts = [t.GetPosition()] if t.Type() == pcbnew.PCB_VIA_T else [t.GetStart(), t.GetEnd()]
    return all(not (FIELD[0] <= pcbnew.ToMM(q.x) <= FIELD[2] and FIELD[1] <= pcbnew.ToMM(q.y) <= FIELD[3]) for q in pts)


def main(src, dst):
    b = pcbnew.LoadBoard(src)
    gone = [t for t in b.GetTracks() if t.GetNetname() in NETS or t.GetNetname() in JTAG and outside(t)]
    mm = pcbnew.ToMM
    at_joint = lambda q: abs(mm(q.x) - PLUS5_JOINT[0]) < 0.03 and abs(mm(q.y) - PLUS5_JOINT[1]) < 0.03
    old = [t for t in b.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T and
           (t.GetLayer() == pcbnew.In3_Cu and t.GetNetname().startswith("ADA")
            or t.GetLayer() == pcbnew.In2_Cu and t.GetNetname() == "+5V" and (at_joint(t.GetStart()) or at_joint(t.GetEnd())))]
    print(f"phase5_strip: {len(old)} Agilex tracks removed (ADA on L4, the +5V branch on L3 above J1)")
    gone += old
    for t in gone:
        b.Delete(t)
    # a keep-out for the router (--keepout, User.2) over U1's ball field: the LED step that falls back to L3 stays
    # out from under the FPGA, where its tracks fenced VCCIO vias off the +1V8 pour (removed again at the end)
    box = pcbnew.PCB_SHAPE(b)
    box.SetShape(pcbnew.SHAPE_T_POLY)
    box.SetLayer(pcbnew.User_2)
    box.SetPolyPoints([pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)) for x, y in
                       ((KEEP[0], KEEP[1]), (KEEP[2], KEEP[1]), (KEEP[2], KEEP[3]), (KEEP[0], KEEP[3]))])
    box.SetWidth(pcbnew.FromMM(0.05))
    b.Add(box)
    b.Save(dst)
    print(f"phase5_strip: {len(gone)} old tracks and vias of the power-good and JTAG nets removed")


if __name__ == "__main__":
    main(*sys.argv[1:3])
