# Manufacturing checklist: Ti60F225 control card (JLCPCB, 6 layers, assembly)

Go through this before ordering. Each line is a check with how to do it; the Status column holds what was found on
the board merged at `d9effa4` (2026-11-13). Re-check every line after any board change. Mark `[x]` when it passes,
and write the reason next to anything accepted as is.

JLC limits change: confirm every number against https://jlcpcb.com/capabilities (6-layer, advanced) on the day
of ordering. The values below are the ones the project rules use (`hardware/control_card.kicad_dru`, checked
2026-10-17).

**Board facts:** 32.64 × 33.90 mm, 6 layers, 1.6 mm. 153 parts: 43 top, 110 bottom (two-sided assembly).
THT: J1 (power-board header), J2 (JTAG). Ti60F225 BGA, 0.65 mm pitch, via-in-pad.

## 1. Automated checks (run first)

| ✓ | Check | How | Status |
|---|---|---|---|
| [ ] | DRC clean, zones refilled | `tools/phase5_check.sh hardware/control_card.kicad_pcb` | 0 errors; 3 dangling old +5V stubs, 26 silk-to-edge, 1 silk overlap, 6 library warnings |
| [ ] | 0 unconnected items | same | 0 |
| [ ] | Schematic parity 0 | same | 0 |
| [ ] | ERC 0, schematic check 0 errors | `tools/sch_check.sh` | 0 / 0 at merge |
| [ ] | Pin plan compiles, timing met | `efinity/pinplan/run.sh --compile` | PASS at merge |
| [ ] | Planes: each net one island, every plane via on its plane | `tools/phase5_check.sh` (plane part), `tools/phase5_islands.py` | **L3 +1V8: main island + 8 small ones (13 vias)** |
| [ ] | No tracks on GND layers L2/L5; L4 only its own nets | same | L2/L5 clean; 7 tracks on L4 (from the placed board): check nets |
| [ ] | Library warnings understood | DRC `lib_footprint_issues` | 6: check each (footprints modified vs library) |

## 2. Fabrication limits (JLC 6-layer)

| ✓ | Check | How | Status |
|---|---|---|---|
| [ ] | Track width ≥ 0.09 mm | board stats | min 0.09 (210 segments, J1 area), mostly 0.1 |
| [ ] | Copper clearance ≥ 0.1 mm (routing used 0.125) | DRC | passes |
| [ ] | Via hole to other copper ≥ 0.2 mm | DRC `hole_clearance` | passes |
| [x] | Via sizes within JLC limits (min drill 0.15, ring per capability page) | board stats | 283 × 0.30/0.15, 20 × 0.35/0.20, 17 × 0.45/0.25; the 0.25/0.15 GND via at (99.69, 96.75) enlarged by `tools/phase5_fab.py` (DRC clean) |
| [ ] | Via-in-pad ordered as filled and capped (POFV) | order option | U1 plane balls, caps under the BGA, pads with vias: must be filled + capped, else solder wicks |
| [ ] | PTH hole to copper ≥ 0.28 mm, PTH hole to hole ≥ 0.45 mm | DRC (project rules) | passes |
| [ ] | Copper to board edge ≥ 0.3 mm | DRC `copper_edge_clearance` | passes |
| [ ] | Annular rings of J1/J2 pads | footprint vs capability | check |
| [ ] | Solder-mask dams between BGA pads (0.3 mm pads, 0.35 mm gaps) | mask layer view, JLC minimum dam | check mask expansion; with too small a dam JLC removes the dam (bridging risk) |
| [ ] | Silkscreen: line ≥ 0.15 mm, text ≥ 0.8 mm high, not on pads, not off board | DRC silk warnings, Gerber view | 26 silk-to-edge, 1 overlap: fix or accept each |
| [ ] | Stackup / impedance | JLC stackup choice | no controlled-impedance nets required; HyperRAM short (< 15 mm): note the stackup used |

## 3. Design items still open (from routing)

| ✓ | Check | Status |
|---|---|---|
| [ ] | L3 +1V8 small islands joined to the main pour (bunch or move the LED and J1-fan tracks; `tools/phase5_islands.py` lists each) | 8 islands open |
| [ ] | Decide: JTAG, PG_0V95/PG_1V8, CLK100M on B.Cu (318 mm of bottom-side signal copper) | user decision |
| [ ] | HyperRAM skew accepted or meandered (lengths 8.6–14.2 mm; rule widened to match) | user decision |
| [ ] | Delete the 3 dangling old +5V stubs | open |
| [ ] | Bank 3A caps C178/C179 are 3–4 mm from F14/G12: accept or move | open |
| [ ] | Old Agilex +5V trace on L3 above J1: still needed? | check |

## 4. Assembly (JLC two-sided SMT)

| ✓ | Check | How | Status |
|---|---|---|---|
| [ ] | Every SMT part has an LCSC number and is in stock for the order quantity | `fab_outputs.sh`, then `python3 -I tools/jlc/stock_check.py hardware/fab/bom_jlcpcb.csv --boards N` | no LCSC: U1 (FPGA: Global Sourcing or consigned), J1, J2 (THT) |
| [ ] | Extended-part count and cost acceptable | JLC BOM view | check |
| [ ] | CPL rotations correct, especially bottom side (110 parts) and polarised parts | JLC's placement preview after upload | check every IC, LED, diode, the flash (BGA-24), U1, translators (UQFN-16) |
| [ ] | Pin 1 / polarity marks visible on silk for every IC, LED, diode, electrolytic | Gerber view | check |
| [ ] | Two-sided assembly: heavy parts on the bottom (bucks, inductors) are fine for second reflow | part masses | check L1–L3, U2–U4 |
| [ ] | Parts not too close to the edge for JLC's handling; rails or panel needed? | closest SMD pad centre 0.85 mm from the edge (D1) | check JLC's edge rule for this board size; add rails/panel if required |
| [x] | Fiducials (global fiducials help with the 0.65 mm BGA) | footprint list | FID1–3 top (76.65, 102.35), (101.65, 107.10), (84.15, 123.60); FID4–6 bottom (77.40, 96.35), (101.65, 102.10), (89.15, 124.60): 1 mm copper, 2 mm mask, board-only, not in BOM/CPL (`tools/phase5_fab.py`) |
| [ ] | BGA X-ray inspection option for U1 (and the HyperRAM / flash BGAs) | order option | recommended |
| [ ] | THT J1/J2: JLC through-hole assembly or hand soldering | order option | decide |
| [ ] | Moisture-sensitive parts (U1, BGAs) baked/handled by JLC | part MSL | note |
| [ ] | 0201 parts: 47n/100n/1u/4u7 decaps, resistors: JLC 0201 assembly accepted | order option | check |

## 5. Mechanical and mating

| ✓ | Check | How | Status |
|---|---|---|---|
| [ ] | J1 position, pitch (1.27 mm), pin 1 and orientation match the power board | compare with the power board's footprint | check |
| [ ] | Board outline, size and any keep-outs against the power board / enclosure | 3D view | check |
| [ ] | No mounting holes: the card is held by J1 only (intended?) | | **none on the board**: confirm |
| [ ] | Bottom-side part heights clear the power board under the card | 3D view, J1 stacking height | check |
| [ ] | JTAG J2 reachable with the cable when mounted | 3D view | check |
| [ ] | 3D view: no overlapping bodies, all models present | KiCad 3D viewer | check |

## 6. Electrical sanity (last look)

| ✓ | Check | Status |
|---|---|---|
| [ ] | Supply power-up order: 0.95 V → PG → 1.8 V → PG → 3.3 V, PG lines routed | PG lines routed (on B.Cu) |
| [ ] | Buck feedback dividers give 0.95 / 1.8 / 3.3 V (R values in the BOM) | check |
| [ ] | 47 µF at each regulator (C106, C125, C147) placed at the inductor outputs | yes |
| [ ] | VCCA_BL filter (FB8, C96, C100) routed to L5; VCCA_TL/TR/BR on VCC | check |
| [ ] | Configuration: flash (IS25WP128) on CCK/SSL_N/CDI0–3, pull-ups, CRESET_N RC, CDONE, TEST_N | checked in schematic; check routing |
| [ ] | Translator OE pull-up (R67) and B-side pull-downs R40/R41 placed | yes |
| [ ] | Flash QE bit / x4 boot: programming plan for bring-up | open (bring-up item) |

## 7. Order files

| ✓ | Check | How |
|---|---|---|
| [ ] | Gerbers, drill, BOM, CPL generated from the final board | `KICAD_ROOT=<squashfs-root> tools/jlc/fab_outputs.sh hardware/control_card.kicad_pcb hardware/fab --skip J1,J2` (skip only if THT is hand-soldered) |
| [ ] | Gerbers reviewed in a viewer (JLC's online viewer or gerbv): every layer, drill, mask, paste, outline | upload preview |
| [ ] | Order options: 6 layers, 1.6 mm, via-in-pad POFV, surface finish (ENIG recommended for 0.65 mm BGA and 0201), stackup chosen, assembly both sides, X-ray | order form |
| [ ] | Files and order settings committed / noted with the commit hash they came from | git |
