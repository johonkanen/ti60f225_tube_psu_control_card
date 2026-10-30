# Conversion plan: Agilex 3 control card → Efinix Ti60F225

Written 2026-10-30. Source design: `~/dev/ti60f225_control_card` (despite the folder name, an Altera Agilex 3
A3CZ065BB18AE7S card; GitHub remote `agilex3_control_card`), state at commit `43b9ec7`, "ready to order",
fully routed, DRC clean. Target: the same card with an Efinix Titanium **Ti60F225** in this repository
(`ti60f225_control_card`).

Legend: **[keep]** reuse as is, **[mod]** reuse with changes, **[new]** new part or block, **[drop]** remove,
**[verify]** fact still to be confirmed from an Efinix document before it is designed in.

Sources used for this plan:
- **`docs/ti60_requirements.md`**: the device requirements (rails, decoupling, power-up order, configuration,
  JTAG, I/O rules) from the Ti60 data sheet v3.9 and Efinix's Ti60 F225 hardware checklist, both in
  `reference/efinix/`, compared with the proven card.
- `reference/ti60f225_pinout.csv` (in this repo): all 225 balls with pad name, bank, type (HVIO/HSIO/power/
  dedicated), configuration function, LVDS pair and clock region. Built from Efinix `ti60_pinout-v1.0.xlsx`
  (sheet F225) and cross-checked against the Efinity 2026.1 device database
  (`~/efinity/2026.1/pt/db/resource/Ti60F225.db`): all 225 balls agree (G6 is `VQPS_GND`, tied to GND).
  v0.5 and v1.0 of the pinout have the same ball map.
- Ti60F225 dev board schematic v1.3 (`~/Downloads/ti60f225-dev-board-schematics-v1.3.pdf`).
- **The user's proven Ti60F225 PSU control card** (Proteus, built and tested), copied to `reference/ti60_psu_card/`
  (schematic PDF, `.pdsprj`, CADCAM exports; the source is in the user's Sync folder under
  `proteus_projektit/.../psu_control_card/efinix_titanium_control_card`): 3 × AP61202 (0.953 V core, 1V8, 3V3),
  all HSIO banks at 1.8 V, HVIO at 3.3 V, REF_RES 10 k to GND, JTAG direct at 3.3 V, CRESET_N RC,
  SPI active x2, W956A8MBYA HyperRAM, W25Q64JW flash, 5 × SN74AXC8T245 level shifters, 4-layer board.
- `~/dev/efinix_soc_board` (Ti135 conversion of a similar card): Titanium configuration straps, JTAG, flash and
  sequencing notes in `MIGRATION_PLAN.md`, `TI135_PCB_NOTES.md` and `HW_CHECKLIST_REVIEW.md`.

---

## 1. What changes, in one table

| Item | Agilex 3 card (source) | Ti60F225 card (target) |
|---|---|---|
| FPGA | A3CZ065, 65k LE, B18A 474 balls | **Ti60F225C4**, 60k LE, 225-ball FBGA, 10 × 10 mm, 0.65 mm pitch, 15 × 15 array (rows A–R); 0.30 mm pads as on the proven card. Commercial: Tj 0–85 °C |
| 3.3 V-capable I/O | ~160 HVIO on 6A–6H, everything direct | **23 HVIO** only: TL 7, TR 7, BR 7, BL 2 (+ JTAG); at most 6 used as outputs per bank. 140 HSIO (1.2–1.8 V) in banks 1A/1B (left), 2A/2B (top), 3A/3B (right), 4A/4B (bottom) |
| Core | 0.75 V, remote sense | **0.95 V** (0.92–0.98) VCC; 4 × VCCA (TL/TR/BL/BR) each separately filtered from VCC; no sense balls |
| Other FPGA rails | 1.8 V (VCCPT…), 1.2 V (VCCRCORE, PIO), 3.3 V HVIO, 1.8 V_HR | 1.8 V: VCCAUX (±50 mV) + all 8 HSIO VCCIO; 3.3 V: VCCIO33_TL/TR/BL/BR. **No 1.2 V, no separate 1.8 V_HR** |
| Configuration | SDM, AS ×4, MSEL straps, RREF, OSC_CLK_1 | **SPI active x4** (decided) from bank 1A (SSL_N P1, CCK N1, CDI0–3 M1/L1/H5/H4), CRESET_N J5, CDONE L3, TEST_N E2, CSI N2; REF_RES 2A/3A/4A 10 k 1 %; IS25WP128-RHLE flash |
| JTAG | 1.8 V SDM, SN74AVC4T774 shifter | dedicated pins TCK N4, TMS N3, TDI P3, TDO M4 in bank BL → VCCIO33_BL at 3.3 V → **shifter dropped** (the proven card does the same) |
| Toolchain | Quartus Pro | Efinity 2026.1 (installed in `~/efinity/2026.1`) |

The board gets simpler: 3 bucks instead of 5, no JTAG shifter, far fewer FPGA supply balls and decoupling caps,
a smaller BGA. It gets harder in one place: there are not enough 3.3 V pins for the header, so level
translators come back (as on the earlier Ti60 card).

---

## 2. I/O budget (the main design decision)

What the card connects at 3.3 V on the Agilex version (63 I/O):

| Group | Signals | Count |
|---|---|---|
| Power-board header J1, used | 17 outputs (PWM, SPI clocks/selects, relay, TX) + 3 inputs (HT_SDATA, CUK_SDATA, RX) | 20 |
| Power-board header J1, spare | J1 pins 17, 19, 22, 24, 26–33 | 13 |
| ADC SPI (2 × CS/SCLK/SDO) | ADS7056 DVDD at 3.3 V | 6 |
| Mux selects (2 × 3) | SN74LV4051A at 3.3 V (VIH 2.31 V) | 6 |
| RGB LEDs (2 × 3) | common anode | 6 |
| HyperRAM + clock | already 1.8 V | 13 |

HVIO available: 23. Allocation (decided 2026-10-30, revised the same day after reading the data sheet):

| Signals | Where | How |
|---|---|---|
| HyperRAM (12 used, CK# unused), CLK100M | HSIO, one 1.8 V bank close to the HyperRAM, clock on a PLLIN ball | direct, 1.8 V |
| ADC SPI (6) | HSIO | **[mod]** ADS7056 **DVDD → +1V8** (DVDD range 1.65–3.6 V, AVDD stays on +3V3A). Frees 6 HVIO; the earlier Ti60 card already did this |
| Mux selects (6) | HSIO | **[mod]** SN74LV4051A → **TMUX1308** (1.8 V-logic selects at a 3.3 V supply, same TSSOP-16 pinout family as the 4051) **[verify]** pin-for-pin match, on-resistance, leakage and charge injection against the ADS7056 front end. JLC 2026-10-30: TMUX1308APWR C39707757 (700), TMUX1308QPWRQ1 C1517403 (536); the DQFN/QFN versions have more stock but need a new footprint |
| 15 PWM / gate-drive / SPI outputs + GPIO_BYPASS_RLY to J1 | HSIO → **2 × SN74AXC8T245PWR** (1.8 V → 3.3 V, DIR fixed A→B), all 16 channels used | **[new]**, TSSOP-24, JLC C882718 (8403 on 2026-10-30; the small UQFN/VQFN versions are out of stock). OE from a **dedicated FPGA HSIO pin** with a pull-up to +1V8 (OE is active low, referenced to VCCA), so the outputs stay Hi-Z during and before configuration and the power board's pull-downs hold them low until the design enables them. The relay output goes through a translator too: every Ti60 user pin has a weak **pull-up** during reset and configuration (DS Table 75), which a direct HVIO pin would put on the relay driver |
| 3 header inputs (HT_SDATA, CUK_SDATA, RX) | HVIO, one per bank TL/TR/BR | direct 3.3 V |
| TX | HVIO | direct (UART idles high, so the configuration pull-up is harmless) |
| LEDs (6) | HVIO | direct; common anode, so the configuration pull-ups keep them off |
| J1 spares (13) | the leftover HVIO (23 − 3 − 1 − 6 = 13) | **all 13 spares connected**, directly. They see the weak pull-up during configuration; a spare that later drives something on the power board that must start low needs an external pull-down |

HVIO is then fully used. Efinix recommends at most 6 HVIO used as 3.3 V outputs or bidirectional per bank
(Efinity warns, it doesn't fail). With the 3 inputs spread one per bank, TL/TR/BR have 6 output-capable balls each
and BL 2, i.e. exactly 20 for TX + 6 LEDs + 13 spares. If placement needs room, one RGB LED instead of two frees 3.

Pin placement rules for later (to be checked in Efinity Interface Designer before layout is frozen):
- HyperRAM in one HSIO bank; RWDS/CK on pins the Efinix HyperRAM controller IP allows **[verify]** in the IP user guide.
- CLK100M on a `PLLINx` ball that can feed the PLL used for the HyperRAM and the ADC SCLK.
- ADC SDO capture with a phase-shifted PLL clock, as on the Agilex card (60 MHz SCLK).
- Prefer translator inputs on the bank facing J1, so the 1.8 V side is short.

---

## 3. Block-by-block mapping

| Source block (sheet) | Fate | Notes |
|---|---|---|
| U1 Agilex 3 + `fpga_power.kicad_sch` | **[drop]** → **[new]** Ti60F225 symbol (units: power/GND, config+JTAG, HSIO 1A/1B, 2A/2B, 3A/3B, 4A/4B, HVIO) generated from `reference/ti60f225_pinout.csv` | Decoupling rebuilt to the Efinix Ti60 checklist and the dev board (per-bank VCCIO, VCCAUX, VCC, 4 × VCCA filters) |
| `fpga_io.kicad_sch` | **[mod]** | Same nets, new balls; translators added between FPGA and J1 |
| `config.kicad_sch`: SDM straps (MSEL, nCONFIG, nSTATUS, RREF), SN74AVC4T774, OSC_CLK_1 link | **[drop]** → **[new]** Efinix straps (`docs/ti60_requirements.md` §4) | CRESET_N held low at power-up: RC as on the proven card (330 k / 1 µF) or a supervisor on the last rail (HWC prefers a supervisor); CDONE, SSL_N (high = active mode), CSI, TEST_N 10 k pull-ups to +1V8; CBSEL0/1 open (single image); NSTATUS open or LED; REF_RES_2A/3A/4A 10 k 1 % to GND (the other five open); VQPS_GND to GND; JTAG 10 k pull-ups to +3V3 |
| MT25QU256 1.8 V QSPI flash (BGA-24) | **[mod]** → **IS25WP128-RHLE** (bought by the user), same BGA-24 footprint | 128 Mbit, 1.8 V, 133 MHz; Ti60 image ≤ 13.96 Mbit. Bank 1A (1.8 V), **x4** (decided): IO0–IO3 to CDI0–CDI3, 10 k pull-ups on IO2/IO3. **[verify]** with the ISSI data sheet: ball map and dedicated RESET# match the footprint (the Ti135 notes say they do), and whether x4 active configuration needs the QE bit set (AN 033). RESET#: 10 k pull-up to +1V8 or an FPGA GPIO |
| HyperRAM W958D8NBYA5I | **[keep]** part, footprint, decoupling; **[mod]** FPGA side | Supply moves from +1V8_HR to +1V8. Re-route and re-match lengths (DRC rule `hyperram_length` kept) |
| 100 MHz oscillator OT3225100MJBA4SL | **[keep]** | One load (PLLIN) instead of two (D18 + OSC_CLK_1). Bead + 470 nF from +1V8 kept. 25 MHz twin fits if a lower reference is preferred |
| U2 AP61302 core buck | **[mod]** to 0.95 V | Proven card: AP61202 with 200 k over 680 k ‖ 680 k (= 340 k) → 0.953 V, 22 pF feed-forward, 4.7 µF in, 2 × 10 µF out, 1 µH. Same SOT-563 pinout as the AP61102/AP61302, so the existing cell takes the proven divider (200 k / 340 k). Ti60 has no VCCLSENSE/GNDSENSE: drop the sense pair and the 100R/10R fallbacks, feed back locally at the output caps. Data sheet: ≥ 500 mA at power-up. Keep the AP61302 unless the power estimate says the AP61102 (1 A) is enough; the AP61202 had only 72 at JLC on 2026-10-12. HWC: 47 µF at each regulator output |
| U3 AP61102 +1V8 | **[keep]**, **[mod]** loads | Now VCCAUX (1.8 V ± 50 mV: use 1 % resistors and check the AP61102 FB tolerance) + all HSIO banks + HyperRAM + flash + oscillator + ADC DVDD + mux logic + translator A sides. Re-check 1 A rating |
| U4 AP61102 +3V3 | **[keep]** | VCCIO33 × 4, translator B sides, LEDs, JTAG pull-ups |
| U17 AP61102 +1V2, U18 AP61102 +1V8_HR | **[drop]** | No 1.2 V or separate HyperRAM rail needed; removes two buck cells (~24 parts) |
| FB1–FB5 ferrite filters (PLLDIG, PLL, ADC, RCORE, OSC) | **[mod]** | → 4 × VCCA filters from VCC, one per VCCA ball (HWC: separate filter each; 2 × 100 n, 2 × 10 n, 1 n per VCCA) + the oscillator bead |
| Forced-PWM EN dividers (R46–R51), PG chain | **[mod]** | Data sheet order: VCC/VCCA first, then VCCAUX and all VCCIO in any order (≥ 10 µs later), then CRESET_N (≥ 10 µs after the last rail); every rail ramps in ≤ 10 ms. Chain: 0.95 V → its PG enables 1.8 V and 3.3 V together (as the proven card) → CRESET_N release. Keep the forced-PWM EN dividers (the proven card tied EN to 5 V, i.e. PFM at light load) |
| U6 TLV75533 +3V3A, ADC chains (4051, OPA365, ADS7056) | **[keep]** OPA365, ADS7056, LDO; **[mod]** mux | ADS7056 DVDD moves to +1V8; the SN74LV4051A muxes become TMUX1308 with selects on HSIO |
| J1 2 × 25 header, J2 JTAG 1 × 5 | **[keep]** footprints and positions | J2 is now direct 3.3 V JTAG to the FTDI cable. Efinix programming (and openFPGALoader `spiOverJtag_efinix_ti60f225`) both work over JTAG |
| RGB LEDs D1/D2 | **[keep]** | on HVIO |
| — | **[new]** 2 × SN74AXC8T245PWR + decoupling, OE from an FPGA pin | JLC C882718; the proven Ti60 card used this part (5 of them) |
| Outline, stackup, JLC rules | **[keep]** | 32.5 × 33.8 mm, 6 layers JLC06161H-3313, via-in-pad, `control_card.kicad_dru`. The proven card fanned out the same BGA on 4 layers, so 4 layers is a later cost option |

---

## 4. Phases

### Phase 0: repository setup (done 2026-10-30)
- [x] `git init`, repository name `ti60f225_control_card` (not yet on GitHub; the source's remote is
  `agilex3_control_card`, so the name is free).
- [x] This plan and `reference/ti60f225_pinout.csv`.
- [x] Copied from the source at commit `43b9ec7` (committed state, via `git archive`): `hardware/` (project, sheets,
  libs, `.kicad_dru`; `fab/` and `.kicad_prl` left out), `LICENSE`, `.gitignore`,
  `docs/jlcpcb_production_checklist.md`, and in `reference/`: `power_board_header.csv`, `mux_assignment.csv`,
  `jlc_parts.csv`, and the Agilex pin list as `agilex3_pin_assignment.csv` (net names and J1 mapping to carry over).
  The project files keep the name `control_card.*`. Until phase 3 the KiCad project is still the unchanged
  Agilex 3 design.
- [x] `tools/jlc` submodule (`https://github.com/johonkanen/jlc-tools.git`).
- Not copied: the Agilex generator chain in `tools/` (the source README says not to rerun it on the hand-edited
  design), Altera pin lists, Agilex requirement docs, design notes and bring-up checklist. Those stay in the source
  repository; the Ti60 versions are written in phase 6. Footprint/symbol generators are written fresh in phase 2
  (ideas from the source's `make_bga_footprint.py` and `efinix_soc_board/tools/gen_symbols.py`).

### Phase 1: device data (before touching KiCad)
- [x] Part: **Ti60F225C4** (commercial, Tj 0–85 °C, speed grade 4, VCC 0.95 V). Check DigiKey / JLC Global
  Sourcing availability before ordering.
- [x] Package: 10 × 10 mm, 0.65 mm pitch (data sheet Table 3); land 0.30 mm round pads (proven card's IPC-356).
- [x] Data sheet v3.9 and the Ti60 F225 hardware checklist read; results in `docs/ti60_requirements.md`.
- [x] Proven card's power, configuration and JTAG circuits read (schematic pages 4 and 5).
- [x] Flash: IS25WP128-RHLE (user's stock); configuration **x4**.
- [ ] IS25WP128 data sheet: ball map, RESET#, QE bit / x4 default (see section 6).
- [ ] Efinity Power Estimator for a realistic design (HyperRAM controller, ADC capture, PWM) → core current → buck
  choice and inductor rating.
- [x] I/O plan in section 2 confirmed (translators, all spares, OE from an FPGA pin, 1.8 V-logic mux).
- [ ] TMUX1308 check: pinout against the SN74LV4051A footprint, select-input thresholds at VDD 3.3 V, and the
  analog specs (on-resistance, leakage, charge injection) against the 2.5 MSPS front end.

### Phase 2: libraries
- [ ] Symbol `hardware/lib/ti60f225.kicad_sym` generated from `reference/ti60f225_pinout.csv`, multi-unit.
- [ ] Footprint `Efinix_F225` (BGA 15 × 15, 0.65 mm, 10 × 10 mm body) generated by script: 0.30 mm copper (not
  mask-defined), 0.35 mm mask, 0.30 mm paste, like the B18A footprint; ball A1 orientation from the pinout and the
  proven card's footprint.
- [ ] New parts in `control_card.kicad_sym`: SN74AXC8T245 (TSSOP-24 or VQFN), any new straps.

### Phase 3: schematic (edit sheets in KiCad, not by regenerating)
- [ ] Remove U1 and `fpga_power`; place the Ti60 units; new `fpga_power` with VCC/VCCA/VCCAUX/VCCIO decoupling.
- [ ] `config` sheet rewritten for Efinix (straps, CRESET_N, CDONE, JTAG without shifter, flash on bank 1A).
- [ ] `power` sheet: drop U17/U18 cells, core divider to 0.95 V, drop sense pair, new PG/CRESET_N chain.
- [ ] `memory` sheet: HyperRAM/flash/oscillator on +1V8.
- [ ] `adc` sheet: ADS7056 DVDD to +1V8 (with its own 100 nF).
- [ ] `connector` / `fpga_io`: translators, OE control, new ball assignment (placement-driven, as before).
- [ ] ERC clean; netlist check that every J1 signal reaches the FPGA (directly or through a translator).

### Phase 4: pin plan in Efinity (before layout is frozen)
- [ ] Efinity project with the Ti60F225, Interface Designer: all GPIOs with their I/O standards (1.8 V LVCMOS on
  HSIO, 3.3 V LVCMOS on HVIO), PLL with CLK100M input, HyperRAM IP pins, SPI ×4 configuration.
- [ ] Compile a stub design so Efinity checks bank voltages, PLLIN reachability, DDIO and HyperRAM pin rules.
- [ ] Export pin list → `reference/pin_assignment.csv`; this is the contract between board and FPGA design.

### Phase 5: PCB
- [ ] Start from the routed Agilex board: keep outline, J1, J2, LEDs, ADC chains, analog LDO, the 1.8 V/3.3 V/core
  buck cells and their pours. Delete U1, its via-in-pads, decoupling, U17/U18 cells, the JTAG shifter, and every
  FPGA-side track.
- [ ] Place the Ti60F225 (smaller than B18A, so there is space to recentre or rotate it so HVIO and the translators
  face J1 and the HSIO bank for the HyperRAM faces the memory strip).
- [ ] Re-run placement-driven pin assignment (min-cost matching idea from `assign_io.py`) within the Efinity-legal
  pin sets; feed back into Phase 4.
- [ ] Fan-out with via-in-pad on supply/GND balls; new plane plan: L4 gets +0V95 island + +3V3, L3 +1V8 pour
  (no +1V2 island any more). Re-check GND balls on the outer ring.
- [ ] Route HyperRAM length-matched; ADC SPI; translator nets; JTAG.
- [ ] DRC clean (JLC rules), zones refilled, schematic parity 0.

### Phase 6: verification and production
- [ ] Independent reviews as for the Agilex card: Efinix hardware checklist, electrical review, JLC production check.
- [ ] BOM/CPL via `tools/jlc`; stock check for 10 boards; FPGA through Global Sourcing if JLC doesn't stock it.
- [ ] Adapt `docs/`: design notes, `ti60_requirements.md` (from `agilex3_requirements.md`), bring-up checklist
  (configuration via Efinity programmer / openFPGALoader, CDONE, HyperRAM, ADCs, translator OE behaviour).
- [ ] README with renders.

---

## 5. Decisions

Made 2026-10-30:
1. **FPGA:** Ti60F225C4.
2. **3.3 V I/O:** 2 × SN74AXC8T245 for the 15 header outputs; all 13 J1 spares connected.
3. **Translator OE:** a dedicated FPGA pin, pulled to the disabled state.
4. **Mux:** 1.8 V-logic mux (TMUX1308), selects on HSIO.
5. **Project file names:** kept as `hardware/control_card.*` (phase 0 default; rename later if wanted).
6. **Flash:** IS25WP128-RHLE (the user has bought them).
7. **Configuration:** SPI active x4.

Still open:
8. **Core regulator:** keep the AP61302 cell or downsize to an AP61102 once the power estimate is in?
9. **Start point:** copy the routed Agilex board and strip the FPGA region (proposed: keeps the solved edge
   placement, buck cells and J1 fan-out), or start a fresh board with only the outline and connectors?

## 6. Documents

Received 2026-10-30 (in `reference/efinix/` unless noted): Ti60 data sheet v3.9, Ti60 F225 hardware checklist
(`ti60_hw_checklist.htm`), Ti60 pinout v1.0, the Efinix Ti60F225 and Ti125F225 dev-board layouts (left in
Downloads: the Ti60 one uses a socket footprint, the Ti125 one is an Allegro `.brd`), and the proven card
(`reference/ti60_psu_card/`).

Still useful:
- **IS25WP128-RHLE data sheet** (ISSI): ball map, RESET#, QE bit / quad default.
- **AN 033: Configuring Titanium FPGAs**: x4 active details, flash requirements, CRESET_N/pull-up sizing.
- **HyperRAM controller core user guide** (Titanium pin rules for CK, RWDS and DQ).
- **Efinity Power Estimator** for the Ti60 core current.
- Optional: Titanium Packaging User Guide (F225 drawing, ball size) and the Ti60F225 3D STEP model.
