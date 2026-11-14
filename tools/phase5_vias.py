"""Phase 5: via-in-pad on every plane ball of U1, U7 and U9 (GND, +0V95, +1V8, +3V3), rerunnable.

    $KICAD_MOUNT/bin/python3.11 -I tools/phase5_vias.py IN.kicad_pcb OUT.kicad_pcb

The signal balls are fanned out by KiCadRoutingTools (bga_fanout --escape-method underpad --plane-drop off): most
escape on F.Cu between the balls, the rest through a 0.30/0.15 via in their pad. Every plane ball gets the same
0.25/0.15 via at its pad centre and reaches its plane by fill. JLC fills and caps via-in-pad on 6-layer boards at
no cost (IPC-4761 type VII); this keeps the diagonal gaps free for the routing and puts supply and GND vias
0.65 mm apart, where an 0201 decap sits straight across them. A ball that already has a via at its centre is skipped. The memories (1 mm pitch, 0.32 mm
pads) get the same via on their supply and GND balls, under the bottom-side decaps that sit on those pairs; their
signal balls are routed from the pads.
"""
import sys

import pcbnew

PLANES = {"GND", "+0V95", "+1V8", "+3V3"}
# U1 signal balls that go down in their pad instead of an F.Cu escape (left out of the fan-out by
# tools/phase5_layout.sh): the header nets of HVIO bank TL and of TR's inner balls, which run to J1 on L3, and
# FLASH_IO2 on its deep ball. Their vias are made here, before the decoupling is placed, so no cap pad lands on one.
SIGNAL_IN_PAD = {"J1_P19", "J1_P22", "J1_P24", "J1_P26", "J1_P27", "TX", "CUK_SDATA", "J1_P29", "J1_P31",
                 "/Configuration/FLASH_IO2"}
b = pcbnew.LoadBoard(sys.argv[1])
have = {(v.GetPosition().x, v.GetPosition().y) for v in b.GetTracks() if v.Type() == pcbnew.PCB_VIA_T}
n = 0
for p in [p for r in ("U1", "U7", "U9") for p in b.FindFootprintByReference(r).Pads()]:
    pos = p.GetPosition()
    if (pos.x, pos.y) in have:
        continue
    if p.GetNetname() not in PLANES and not (p.GetParentFootprint().GetReference() == "U1" and p.GetNetname() in SIGNAL_IN_PAD):
        continue
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(pos)
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetWidth(pcbnew.FromMM(0.30))
    v.SetDrill(pcbnew.FromMM(0.15))
    v.SetNet(p.GetNet())
    b.Add(v)
    n += 1
b.Save(sys.argv[2])
print("phase5_vias: U1/U7/U9 plane balls (and U1 signal balls that go down in the pad) with a via in pad:", n)
