# Brief: I/O routing of the Ti60F225 control card

You are routing the signal nets of a placed, fanned-out 6-layer board. Read this whole brief first, then
`docs/io_swap_groups.md` (the pin groups) and the memory notes it mentions. Work in
`/home/jari/dev/ti60f225_tube_psu_control_card` (git, branch main). Commit each finished step, ending the message with
`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Goal

Route every signal net with **F.Cu (top) and In2.Cu (L3) only**, with as few vias as possible, and change the
FPGA pin mapping (and the translator channels) wherever a swap removes a crossing or a via. Done means: DRC clean
apart from silkscreen and library warnings, 0 unconnected items, schematic parity 0, every plane via still on its
plane, and pin plan, schematic and board agreeing.

## The board

- `hardware/control_card.kicad_pcb`, 32.6 × 33.9 mm (x 75.15–107.79, y 94.85–128.75), JLC 6-layer.
- Stack and what each layer carries:

| Layer | KiCad name | Use |
|---|---|---|
| L1 | F.Cu | signals (main routing layer), U1 Ti60F225 (0.65 mm BGA) at (92, 113), translators U19–U22, J1 |
| L2 | In1.Cu | GND plane: never route |
| L3 | In2.Cu | +1V8 pour **and** signals (second routing layer) |
| L4 | In3.Cu | +0V95 island / +3V3 plane split: never route |
| L5 | In4.Cu | GND plane: never route |
| L6 | B.Cu | decoupling caps, bucks, U1 fan-out stubs: avoid; only short last-resort hops |

- Rules: 0.1 mm tracks at 0.125 mm clearance, vias 0.30/0.15 (0.125 + 0.075 ring = JLC's 0.2 mm via-hole to
  track). Netclass SW (buck switch nodes, `/Power/SW_*`) needs 0.15 mm. Via-in-pad is free on this 6-layer order
  (filled and capped), so a via in a pad is fine.
- U1 is already fanned out (every plane ball has a via in its pad; signal balls escape on F.Cu/B.Cu stubs). The
  decoupling caps sit on B.Cu under and around the BGA on their own vias. Do not move them.

## Tools

- KiCad 10 via `~/dev/proteus2kicad/bin/kicad_env.sh`; pcbnew scripts run with `"$KICAD_MOUNT/bin/python3.11" -I`.
- KiCadRoutingTools (KRT) at `~/dev/KiCadRoutingTools`: run from that directory with `.venv/bin/python -X utf8`
  (`py_router/route.py`, `py_router/route_planes.py`). Layer arguments take the canonical names (`In2.Cu`), not the
  board's user names.
- `tools/phase5_route.sh` is the existing routing chain (HyperRAM first with length matching, then everything else,
  then the +1V8 pour again). It routes on F.Cu, In2.Cu **and B.Cu**: change it to `--layers F.Cu In2.Cu`, and use
  `--layer-costs` so F.Cu is preferred. Keep the work reproducible: a script change plus a rerun beats hand edits.
  The layout chain `tools/phase5_layout.sh` (about 5 min) rebuilds the placed board from scratch; rerun it after
  any schematic change, then the routing chain on its output.
- Known traps (memory file `krt-on-ti60-card.md`):
  - KRT routes no track through another net's pour, so the chain drops the L3 +1V8 pour before routing and pours
    it again afterwards.
  - J1 is a 1.27 mm header: route on a 0.025 mm grid.
  - Protect earlier copper with `KICAD_RIP_PREEXISTING=0`.
  - KiCad 10's Python crashes after `BOARD.Remove()` of tracks: use `b.Delete()`, hold `zones = b.Zones()` before
    `ZONE_FILLER.Fill`, and save and reload between removing steps.
  - Never strip a net's copper inside the BGA before rerouting it; that removes its fan-out escape.

## Pin swaps

`docs/io_swap_groups.md` lists the groups, the balls in use and the free balls. In short:

- **Fixed, never move:** flash (N1, P1, M1/L1/H5/H4, N2), CLK100M on P2, JTAG, CRESET_N, CDONE, TEST_N, REF_RES,
  and the J1 pinout (it belongs to the power board). Leave E3/F3 (CBSEL), J2, M2 and L6 (SSU_N) unused.
- **Translator inputs** (16 nets + XLAT_OE_N): any free ball of banks 2A/2B.
- **Translator channels** (U19–U22, SN74AVC4T774, all A→B): any channel of any chip; A and B pins move together,
  the J1 pin of the net stays.
- **ADC** (12 nets): any ball of banks 4A/4B.
- **HyperRAM** (12 nets): balls may trade within bank 1B, but each signal keeps its role (DQ0–7 carry
  command/address bits).
- **Direct 3.3 V nets** (22, HVIO banks TL/TR/BR/BL): free within a bank; between banks only as trades, so that no
  bank drives more than 6 outputs at 3.3 V (TL, TR, BR are at 6 now).

**Banks 3A and 3B are free to use** (40 balls, VCCIO on +1V8, south side of the BGA facing the translators and
J1) for any 1.8 V net of the translator-input or ADC groups, if that shortens routes or saves vias. Using either
bank means its VCCIO balls need decoupling like the other banks: one 47 nF 0201 per ball (3A: F14, G12;
3B: J11, L14), added on the `fpga_power` sheet with `place_passive(sh, flow, None, "47n", "+1V8", "GND", ref=...)` from
`tools/phase3_schematic.py` (its `PARTS["47n"]` sets value, footprint, LCSC and MPN; see `tools/sch_vccio_caps.py`) and
placed by `tools/phase5_decaps.py` (add them to `plan()`, one per ball, and drop the bank from `UNUSED_BANKS`).

Procedure for every swap:

1. `python3 -I tools/swap_balls.py NET=BALL ...` (U1 balls only; nets may trade balls in one call). A
   translator-channel swap edits U19–U22's pins on the `connector` sheet: extend `swap_balls.py` or add a small
   tool in the same style (`tools/sch_edit.py`: `relabel_pin`).
2. `efinity/pinplan/run.sh --compile`: must PASS (it regenerates `reference/pin_assignment.csv`); this checks the
   I/O standards, the HVIO output limit and the PLL reference.
3. ERC (`kicad-cli sch erc`) 0 violations; `kicad-cli sch export netlist ... -o X.net` then
   `python3 -I tools/check_schematic.py X.net`: 0 errors.
4. Rerun the layout chain, then routing. Batch swaps: plan them from a first routing run (crossings, vias), apply
   them together, then route again.
5. Update `docs/io_swap_groups.md` to the new mapping.

## Order of work

1. Change `tools/phase5_route.sh` to F.Cu + In2.Cu and run it on the current board as a baseline. Record
   unconnected count, via count and failed nets.
2. Look at the result (render the copper, or list where nets cross and where vias were added). Plan swaps that
   untangle it: translator inputs against the 2A/2B (and 3A/3B) ball order, translator channels against the J1
   pin order, ADC nets against their ADC chips, HVIO nets against J1.
3. Apply, rerun, repeat until it converges. Prefer moving a pin over adding a via.
4. HyperRAM: the board's design rules (`hardware/control_card.kicad_dru`, rule `hyperram_length`) still hold
   10.8 ± 0.1 mm from the old Agilex layout. Set it from the new geometry (shortest matched length the routes
   allow) and keep DQ0–7, RWDS and CS# matched within the tolerance the chain uses (0.2 mm).
5. Power stubs: the translators' supply pins (+1V8 pin 14, +3V3 pin 13, GND pin 8) to their cap vias, U10/U13 GND
   pin 6, the U6 LDO (+5V in, +3V3A out, C15), the PG_0V95/PG_1V8 enable lines (two old PG_1V8 vias at
   (77.73, 102.28) and (79.81, 104.60) can be reused or deleted), and the VCCA_BL filter (FB8, C96, C100 to ball L5).

## Checks after every routing run

- DRC with zones refilled (`kicad-cli pcb drc --refill-zones --severity-all --format json`) and schematic parity
  (`--schematic-parity`, with the current `.kicad_sch` and `sheets/` next to the board copy).
- L3: the +1V8 pour must stay **one island** and reach every +1V8 via; In2.Cu tracks cut it, so keep them bunched
  and short, and check after each run. Same for L4 (+0V95 one island, +3V3 one island) and the GND layers.
- No track on In1.Cu, In3.Cu, In4.Cu.

## Report back

Unconnected count, via count (new signal vias), DRC summary, the list of pin and channel swaps with the reason for
each, whether 3A/3B were used, and anything left for hand routing. Copy the finished board to
`hardware/control_card.kicad_pcb` and add an entry to `CONVERSION_PLAN.md`.
