# Manufacturing checklist: Ti60F225 control card (JLCPCB, 6 layers, assembly)

Go through this before ordering. Each line is a check with how to do it; the Status column holds what was found on
the board at `7772952` (2026-11-14: U1 at 180°, rotated-FPGA routing merged, +5V/C15 and PLL filter hand fixes,
U3/U4 AP61203). Re-check every line after any board change. Mark `[x]` when it passes, and write the reason next to
anything accepted as is.

JLC limits change: confirm every number against https://jlcpcb.com/capabilities (6-layer, advanced) on the day
of ordering. The values below are the ones the project rules use (`hardware/control_card.kicad_dru`, checked
2026-10-17).

**Board facts:** 32.64 × 33.90 mm, 6 layers, 1.6 mm. 155 parts: 41 top, 114 bottom (two-sided assembly), plus six
board-only fiducials. THT: J1 (power-board header), J2 (JTAG). Ti60F225 BGA, 0.65 mm pitch, via-in-pad.
Hand-soldered by the user: J1, J2, U12/U15 (ADS7056, own stock), so JLC assembles 151 parts.

## 1. Automated checks (run first)

| ✓ | Check | How | Status |
|---|---|---|---|
| [x] | DRC clean, zones refilled | `tools/phase5_check.sh hardware/control_card.kicad_pcb` | 0 violations of any severity (no library warnings, no dangling copper; silkscreen rules ignored, no silkscreen printed) |
| [x] | 0 unconnected items | same | 0 |
| [x] | Schematic parity 0 | same | 0 |
| [x] | ERC 0, schematic check 0 errors | `tools/sch_check.sh` | 0 / 0; HVIO 3.3 V outputs per bank BL 1, TL 6, TR 6, BR 6 (limit 6) |
| [x] | Pin plan compiles | `efinity/pinplan/run.sh --compile` | map, interface, pnr, pgm PASS |
| [ ] | Planes: each net one island, every plane via on its plane | `tools/phase5_check.sh` (plane part), `tools/phase5_islands.py` | L3 +1V8: main island + 2 small (18.7 and 5.0 mm², 2 vias each, both also joined by other copper); L2/L4/L5 one island per net. Accept or close |
| [x] | No tracks on GND layers L2/L5 or on L4 | same | 0 / 0 / 0 |

## 2. Fabrication limits (JLC 6-layer)

| ✓ | Check | How | Status |
|---|---|---|---|
| [x] | Track width ≥ 0.09 mm | board stats | min 0.09 (246 segments, J1 area), mostly 0.1 |
| [x] | Copper clearance ≥ 0.1 mm (routing used 0.125) | DRC | passes |
| [x] | Via hole to other copper ≥ 0.2 mm | DRC `hole_clearance` | passes |
| [x] | Via sizes within JLC limits (min drill 0.15, ring per capability page) | board stats | 265 × 0.30/0.15, 20 × 0.35/0.20, 17 × 0.45/0.25 (`tools/phase5_fab.py` enlarges any smaller one) |
| [ ] | Via-in-pad ordered as filled and capped (POFV) | order option | U1 plane balls, caps under the BGA, memory pull-ups on ball vias: must be filled + capped, else solder wicks |
| [x] | PTH hole to copper ≥ 0.28 mm, PTH hole to hole ≥ 0.45 mm | DRC (project rules) | passes |
| [x] | Copper to board edge ≥ 0.3 mm | DRC `copper_edge_clearance` | passes |
| [ ] | Annular rings of J1/J2 pads | footprint vs capability | check |
| [ ] | Solder-mask dams between BGA pads (0.3 mm pads, 0.35 mm gaps) | mask layer view, JLC minimum dam | check mask expansion; with too small a dam JLC removes the dam (bridging risk) |
| [x] | Silkscreen | – | **no silkscreen printed** (decided 2026-11-13); silk layers left out of the Gerbers (`--no-silk`) |
| [ ] | Stackup / impedance | JLC stackup choice | no controlled-impedance nets required; HyperRAM short (< 14 mm): note the stackup used |

## 3. Design items still open (from routing)

| ✓ | Check | Status |
|---|---|---|
| [ ] | HyperRAM on banks 4A/4B (moved from 1B for the rotation; Efinity compile passes): accepted | user accepted the merge 2026-11-14 |
| [ ] | B.Cu signals: JTAG (63 mm, flash lines sit between the balls and J2 on F.Cu), PG lines, LED hops; 244 mm in all | user decision |
| [ ] | HyperRAM skew accepted or meandered (lengths 8.3–13.1 mm, DQ/RWDS 8.3–12.7; rule `hyperram_length` 8.2–13.2) | user decision |
| [ ] | L3 +1V8 small islands (section 1) | accept or close |
| [x] | PLL_BL0 filter (FB8, C96, C100) next to ball L5 | moved by hand (29eae45); **not in the routing chain**: a re-route puts them back |
| [x] | +5V: C15 at J1 pin 1, 0.8 mm B.Cu trunk to U6 | `tools/phase5_5v.py` (chain step); XLAT_OE_N re-routed around it |
| [x] | Dangling copper | none (`tools/phase5_fab.py` step 3) |
| [ ] | TDO has 3 vias | accept |

## 4. Assembly (JLC two-sided SMT)

| ✓ | Check | How | Status |
|---|---|---|---|
| [x] | Every assembled SMT part has an LCSC number and stock | `fab_outputs.sh`, then `python3 -I tools/jlc/stock_check.py hardware/fab/bom_jlcpcb.csv --boards N` | all in stock for 5 boards except: U3/U4 AP61203 C5244557 (public stock reserved: **use the user's 48 in My Parts**); U1 has no LCSC number (Global Sourcing or consigned) |
| [ ] | U1 sourcing | order | Global Sourcing or consign |
| [ ] | Extended-part count and cost acceptable | JLC BOM view | check |
| [ ] | CPL rotations correct, especially bottom side (114 parts) and polarised parts | JLC's placement preview after upload | check every IC, LED, diode, both memories (BGA-24), U1, translators (UQFN-16); package offsets applied by `fab_outputs.sh`: U6 +180, U13 +270, U14 +180, U10 +270, U11 +180 |
| [ ] | Orientation without silkscreen: no pin-1 marks on the board, so assembly relies on the CPL; keep a printed assembly drawing (fab layer) for hand rework | JLC preview, fab-layer PDF | check |
| [ ] | Two-sided assembly: heavy parts on the bottom (bucks, inductors) are fine for second reflow | part masses | check L1–L3, U2–U4 |
| [ ] | Parts not too close to the edge for JLC's handling; rails or panel needed? | closest SMD pad centre 0.85 mm from the edge (D1), C59 0.865 mm | check JLC's edge rule for this board size; add rails/panel if required |
| [x] | Fiducials | footprint list | FID1–3 top (76.65, 102.35), (100.65, 103.60), (84.90, 123.60); FID4–6 bottom (77.40, 96.35), (101.15, 96.35), (89.15, 124.60): 1 mm copper, 2 mm mask, board-only, not in BOM/CPL |
| [ ] | BGA X-ray inspection option for U1 (and the HyperRAM / flash BGAs) | order option | recommended |
| [x] | THT J1/J2 and ADS7056 U12/U15 | – | hand-soldered by the user: left out with `--skip J1,J2,U12,U15` |
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
| [x] | Supply power-up order: 0.95 V → PG → 1.8 V → PG → 3.3 V, PG lines routed | U2 PG → U3 EN, U3 PG → U4 EN (R5/R48, R8/R49 dividers from +5V: 3.33 V, below VIN + 0.3 V) |
| [x] | Buck parts: U2 AP61302, U3/U4 AP61203 (forced PWM, same SOT-563 pinout FB/GND/VIN/SW/EN/PG, 0.6 V ref) | dividers 200k/118k (0.95 V), 200k/100k (1.8 V), 200k/44k2 (3.3 V); 33 pF feed-forward and 1 µH as in the AP6120x data sheet Table 1 |
| [x] | 47 µF at each regulator (C106, C125, C147) placed at the inductor outputs | yes |
| [x] | VCCA_BL filter (FB8, C96, C100) at L5; VCCA_TL/TR/BR on VCC | yes |
| [ ] | Configuration: flash (IS25WP128) on CCK/SSL_N/CDI0–3, pull-ups, CRESET_N RC, CDONE, TEST_N | checked in schematic; routing check on the rotated board |
| [x] | Translator OE pull-up (R67) and B-side pull-downs R40/R41 placed | yes |
| [ ] | Flash QE bit / x4 boot: programming plan for bring-up | open (bring-up item) |

## 7. Order files

| ✓ | Check | How |
|---|---|---|
| [ ] | Gerbers, drill, BOM, CPL generated from the final board | `KICAD_ROOT=<squashfs-root> tools/jlc/fab_outputs.sh hardware/control_card.kicad_pcb hardware/fab --no-silk --skip J1,J2,U12,U15` (generated from `7772952`: 39 BOM lines, 151 placements) |
| [ ] | Gerbers reviewed in a viewer (JLC's online viewer or gerbv): every layer, drill, mask, paste, outline; no silkscreen layers | upload preview |
| [ ] | Order options: 6 layers, 1.6 mm, via-in-pad POFV, surface finish (ENIG recommended for 0.65 mm BGA and 0201), stackup chosen, assembly both sides, X-ray, AP61203 from My Parts | order form |
| [ ] | Files and order settings committed / noted with the commit hash they came from | git (`hardware/fab/` is git-ignored: note the hash) |
