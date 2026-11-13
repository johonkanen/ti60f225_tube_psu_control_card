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
| 15 PWM / gate-drive / SPI outputs + GPIO_BYPASS_RLY to J1 | HSIO → **4 × SN74AVC4T774RSVR** (1.8 V → 3.3 V, DIR1–4 tied high = A→B), all 16 channels used | **[new]** (changed 2026-10-30 from 2 × SN74AXC8T245PWR TSSOP-24): UQFN-16 1.8 × 2.6 mm, JLC C779392 (~108k in stock), the part the Agilex card used as JTAG shifter, so symbol and footprint already exist. 380 Mbps, ±12 mA. One active-low OE per chip (referenced to VCCA), all on `XLAT_OE_N`, a **dedicated FPGA HSIO pin** with a 10 k pull-up to +1V8, so the outputs stay Hi-Z during and before configuration and the power board's pull-downs hold them low until the design enables them. The relay output goes through a translator too: every Ti60 user pin has a weak **pull-up** during reset and configuration (DS Table 75), which a direct HVIO pin would put on the relay driver. Rated −40 to 85 °C (the C4 FPGA is 0–85 °C Tj) |
| 3 header inputs (HT_SDATA, CUK_SDATA, RX) | HVIO, one per bank TL/TR/BR | direct 3.3 V |
| TX | HVIO | direct (UART idles high, so the configuration pull-up is harmless) |
| LEDs (6) | HVIO | direct; common anode, so the configuration pull-ups keep them off |
| J1 spares (12: pins 17, 19, 22, 24, 26–33) | HVIO | **all 12 spares connected**, directly; one HVIO ball (BL) stays free. They see the weak pull-up during configuration; a spare that later drives something on the power board that must start low needs an external pull-down |

HVIO is then fully used. Efinix recommends at most 6 HVIO used as 3.3 V outputs or bidirectional per bank
(Efinity warns, it doesn't fail). With the 3 inputs spread one per bank, TL/TR/BR have 6 output-capable balls each
and BL 2, i.e. 20 for TX + 6 LEDs + 12 spares (one left over). If placement needs room, one RGB LED instead of two frees 3.

Pin placement rules for later (to be checked in Efinity Interface Designer before layout is frozen):
- HyperRAM in one HSIO bank. The FPGA side uses the user's own HyperRAM controller (`~/dev/ti60_ac_psu`,
  `fpga/source/hyperram/`), not Efinix's IP: take the pin rules (DDIO, clock-capable pins for RWDS/CK) from how
  that controller is constrained on the AC PSU Ti60 card.
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
| — | **[new]** 4 × SN74AVC4T774RSVR (U19–U22) + 100 nF per supply, OE from an FPGA pin | JLC C779392 |
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
- [x] TMUX1308 (TI SCDS426E, 2026-10-30): same TSSOP-16 pinout as the 4051 except pin 7 (N.C. instead of VEE),
  so the footprint and routing carry over. Selects: VIH 1.15 V at VDD 3.3 V, so 1.8 V logic drives them. RON
  120 Ω typ / 350 Ω max at 3.3 V (SN74LV4051A: 225 Ω max at 3 V), CD(ON) 40 pF, charge injection −1 pC, leakage
  ±45 nA max to 85 °C. The OPA365 buffer follows the mux, so the higher RON only slows channel settling slightly
  (τ ≈ 350 Ω × ~45 pF ≈ 16 ns).

### Phase 2: libraries
- [x] Symbol `hardware/lib/ti60f225.kicad_sym` (`tools/make_symbols.py`, from `reference/ti60f225_pinout.csv`):
  12 units: POWER, GND, CONFIG_JTAG (CRESET_N, CDONE, JTAG, REF_RES), HSIO_1A … HSIO_4B (one row per P/N pair),
  HVIO (TL/BL left, TR/BR right). All 225 balls once; parses in kicad-cli. Added to `hardware/sym-lib-table`
  (the `agilex3` library stays until phase 3 removes U1).
- [x] Footprint `control_card:Efinix_F225` (`tools/make_f225_footprint.py`, KiCad's Python): 15 × 15 at 0.65 mm,
  10 × 10 mm body, 0.30 mm NSMD pads, 0.35 mm mask, 0.30 mm paste, 0.5 mm courtyard margin. Top view, not
  mirrored: A1 top left; checked against the proven card's IPC-356 ball positions.
- [x] New parts in `control_card.kicad_sym` (existing symbols untouched):
  - `SN74AXC8T245PW` (TSSOP-24, C882718). **Pin 11 is DIR2, not GND**: DIR1 (pin 2) high and DIR2 low gives
    A→B on all 8 bits (TI SCES885 Table 7-1); the data inputs must never float.
  - `TMUX1308PW` (TSSOP-16, C39707757).
  - `IS25WP128-RHLE` (existing `BGA-24_6x8mm_Layout5x5_P1.0mm_CY0.5` footprint, C1349419). Ball functions taken
    from the MT25QU256 symbol and the Ti135 project's IS25WP128 symbol; ISSI's site blocks downloads, so the
    ISSI data sheet check is still open.
- [x] Smaller translator: 4 × SN74AVC4T774RSVR, existing `SN74AXC4T774RSV` symbol (same RSV pinout, checked against TI SCES693I) and `Package_DFN_QFN:UQFN-16_1.8x2.6mm_P0.4mm`. Compare that footprint with TI's RSV land pattern before layout. The `SN74AXC8T245PW` symbol stays in the library unused.

### Phase 3: schematic (done 2026-10-30)
Done by `tools/phase3_schematic.py` (run once on the copied Agilex sheets; it refuses to run twice) with the
sheet editor `tools/sch_edit.py`, which keeps the generator's style (pin → stub → label) and checks every pin
position against the sheets before and after editing. `tools/check_schematic.py` checks the netlist against the
plan; with `--before` (Agilex netlist) it also checks that every untouched part kept its nets.
- [x] `fpga_power`: rebuilt. Ti60 POWER and GND units; decoupling per the Efinix checklist, with these
  deviations: no 100 µF on VCC (the buck has 2 × 22 µF plus 47 µF here), and VCCIO gets a shared 47 µ + 10 µ +
  4.7 µ on +1V8 plus 1 µ + 100 n per HSIO bank instead of the full 7-cap set × 8 banks. VCCA: one bead (FB6–FB9)
  and 2 × 100 n, 2 × 10 n, 1 n per VCCA ball, nets `+0V95_VCCA_TL/TR/BL/BR`.
- [x] `fpga_io`: rebuilt with units HSIO_1B, 2A, 2B, 3A, 3B, 4A, 4B and HVIO. **Provisional balls**:
  HyperRAM on bank 1B with the AC PSU card's map (TEST_N ball E2 = HR_DQ3 with a 10 k pull-up, NSTATUS E1 =
  HR_RWDS); translator inputs `*_1V8` and `XLAT_OE_N` on 3A/3B; ADC A SPI + selects on 4A, ADC B on 4B; HVIO
  TL = LEDs + HT_SDATA, TR = CUK_SDATA, TX, 5 spares, BR = RX + 6 spares, BL = J1_P33 + 1 free. Banks 2A/2B unused.
- [x] `config`: rebuilt around J2 (moved, same UUID). CONFIG_JTAG and HSIO_1A units, IS25WP128-RHLE (U7, x4:
  CDI0–3 = IO0–3), CLK100M on P2 (GPIOL_P_00_PLLIN0, PLL_BL). CRESET_N RC 330 k / 1 µF (proven card); 10 k
  pull-ups to +1V8 on CDONE, SSL_N, CSI, TEST_N, IO2, IO3, flash RESET#; JTAG 10 k pull-ups to +3V3 (no shifter);
  REF_RES_2A/3A/4A 10 k 1 % to GND.
- [x] `power`: U17/U18 cells, C11, the sense fallbacks R3/R4 and the PG_3V3 divider R50/R51 removed; U4 PG open.
  Core divider R1 118 k (C25748) over R2 200 k → 0.954 V with local feedback; C77 47 pF (C1567) keeps the
  100 pF × 51 k feed-forward zero. Chain unchanged: 0.95 V PG enables 1.8 V, its PG enables 3.3 V (all forced PWM).
- [x] `memory`: +1V8_HR → +1V8 (HyperRAM, its reset pull-up, oscillator bead). `adc`: U10/U13 → TMUX1308APWR
  (same UUIDs and positions; pin 7 no-connect), ADS7056 DVDD and its 1 µF caps → +1V8.
- [x] `connector`: U19–U22 SN74AVC4T774RSVR, 8 × 100 nF, R67 10 k OE pull-up. J1 nets unchanged.
- [x] Renamed on all sheets: +0V75 → +0V95 (and FB/SW/EN/PG_0V75 → _0V95). Net classes in `control_card.kicad_pro`
  updated (PWR_CORE = +0V95; +1V2 and the SENSE class patterns removed).
- [x] ERC: 0 violations (all severities). Netlist check: 0 errors. BOM: 187 parts, 44 lines; every part has an LCSC
  number except U1 (Global Sourcing) and the hand-soldered J1/J2.
- New references continue after the Agilex numbering (C86–C165, R52–R67, FB6–FB9, U19–U22); U1, U7, U10, U13
  keep their references, and U7/U10/U13/J2 keep their symbol UUIDs, so "Update PCB from schematic" keeps their
  footprints and placement.
- Open for phase 4/5: the provisional ball assignment; the mux-channel table (`reference/mux_assignment.csv`)
  is unchanged; `reference/agilex3_pin_assignment.csv` is history only.

### Phase 4: pin plan in Efinity (done 2026-10-30)
`efinity/pinplan/run.sh [--compile]` (Efinity 2026.1, KiCad 10):
1. exports the schematic netlist and builds an Interface Designer design (`pinplan.py`) with **every FPGA user I/O
   taken from the netlist** (U1 ball → net), I/O standards 1.8 V LVCMOS on HSIO and 3.3 V LVCMOS on HVIO, banks
   1A–4B at 1.8 V and TL/TR/BL/BR at 3.3 V;
2. imports the HyperRAM GPIOs **unchanged from the user's AC PSU design** (`hyperram_gpio.isf`, exported from
   `ti60_ac_psu` `tsemac_soc.peri.xml`: DDIO resync inputs on `ram_clk_cal`, DDIO outputs on inverted `ram_clk`,
   CK on `ram_clk90`, the same balls) and stops if a ball differs from the schematic;
3. moves its PLL (`hyperram_pll.isf`, PLL_TR0, 50 MHz × M 4) to **PLL_BL0 with the board's 100 MHz on P2** and
   M = 2: same VCO (4000 MHz) and the same 200 MHz `ram_clk`/`ram_clk90`/`ram_clk_cal`; the AC PSU's Ethernet clock
   is dropped;
4. with `--compile` (`stub.py`): a placeholder core (LFSR on `ram_clk`, all inputs folded in) through synthesis,
   place and route and bitstream, with **configuration SPI active x4** in the project.

Results:
- [x] Interface Designer design check: **passed, 0 issues**. No HVIO drive warning (≤ 6 outputs per bank).
- [x] Compile: map, interface, pnr and pgm **pass**; reports say "Configuration Mode: active (x4)". Timing met at
  200 MHz (worst setup +1.27 ns on the rise-to-fall DDIO path, worst hold +0.035 ns); the only warnings are the
  periphery-only clocks `ram_clk90` and `clk100m` being unused by the stub core.
- [x] `reference/pin_assignment.csv` (71 signals: net, direction, ball, pad, bank) is written from the check and is
  the contract between the board and the FPGA design. Kept in git: the `.peri.xml`, `.isf`, project, SDC, stub and
  the pinout/timing reports in `efinity/pinplan/build/` (the rest of the build is ignored).
- The FPGA design for this card can start from `efinity/pinplan/build/ti60f225_pinplan.peri.xml`.
- Phase 5 may still swap balls for routing (translator channels, ADC SPI, HVIO spares, within the same bank
  type); after any swap, rerun `efinity/pinplan/run.sh --compile` and `tools/check_schematic.py`. The HyperRAM balls
  stay as they are (they are the AC PSU card's proven map).
- [x] **Ball swap for routing** (2026-10-31, `tools/swap_balls.py NET=BALL ...`, which moves U1 labels on the sheets):
  the 16 translator inputs and `XLAT_OE_N` moved from bank 3A to the east banks 2A/2B, so they no longer cross
  the band between the BGA and J1. In translator order (U19 → U22, J1 order): A5 A6 B6 A7 | B7 A8 B8 A9 | B9 A10
  B10 A11 | C8 C9 C10 D10, OE on C6. Rows A/B escape east on F.Cu, the U22 group drops south through the middle
  columns that 3A/3B left free. Banks 3A/3B are now unused (VCCIO3A/3B stay on +1V8 with their caps, REF_RES_3A
  stays). ERC 0, `check_schematic.py` 0 errors, Efinity compile passes (map/interface/pnr/pgm), timing met.
- [x] **HSIO decoupling** (2026-11-01, `tools/sch_vccio_caps.py`): 10 nF + 1 nF (0201) added per used HSIO bank
  (1A 1B 2A 2B 4A 4B, C166–C177), so each used bank now has the checklist's 1n/10n/100n/1u; the shared
  47µ/10µ/4µ7 stay shared (one +1V8 plane). The 1µ + 100n of the unused banks 3A/3B (C136–C139) removed, as the
  checklist asks no caps for an unused bank. ERC 0, `check_schematic.py` 0 errors. On the board each bank's
  four caps sit 2.6–5.7 mm from its VCCIO balls (bottom side, own plane vias; no room for more vias in the
  ball field).

### Phase 5: PCB (in progress)
Pipeline, rerunnable from the copied Agilex board (`git checkout` the board first):
`tools/phase5_sync.py OLD_NET NEW_NET board` then `tools/phase5_place.py board` (KiCad 10's Python).
- [x] **Sync** (`phase5_sync.py`, 2026-10-31): like Update PCB from Schematic with re-link by reference.
  81 footprints deleted, U1 replaced by `Efinix_F225`, 104 new footprints parked east of the board; pad nets,
  values and LCSC fields from the new netlist; renamed nets (+0V75 → +0V95, the header nets now local to the
  connector sheet) renamed on copper and zones. Deleted: every track/via of the Agilex FPGA's signal nets (1189),
  copper of vanished nets (72), copper inside the old BGA area (394) or ending on a deleted pad (66), the old
  4051 VEE ties, the +3V3 taps at the ADS7056 DVDD pins; zones of the deleted bucks and of +1V2. Kept: J1, J2,
  LEDs, both ADC chains, the analog LDO, the 0.95/1.8/3.3 V buck cells with their pours, the L2/L5 GND planes,
  the L3 +1V8 and L4 +0V95/+3V3 pours.
- [x] **Floorplan** (`phase5_place.py`): U1 at (92, 113), rotated 90° clockwise: banks 1A (flash) north-west,
  1B (HyperRAM) north-east, 4A/4B (ADC) west, 3A/3B (unused since the ball swap) and HVIO TR/BR south towards
  J1, 2A/2B (translator inputs) east, HVIO TL north-east and BL north-west. Because 1B ends up east of 1A, **U9 (HyperRAM) and U7
  (flash) swapped places**, their via-in-pads moving with them; the HyperRAM's three 0402s and the flash's
  100 nF sit on VCC/VSS ball pairs underneath; R24 beside the HyperRAM. **Translators U19–U22** in a row on the
  top side at y 122.5, x 104.5 → 92.5 (4 mm pitch, ordered by J1 pin), 1.8 V side towards the FPGA.
- [x] DRC: 0 errors other than unconnected items (419) and the HyperRAM length rule (nets unrouted);
  schematic parity 0.
- [x] **Fan-out and placement** (`tools/phase5_layout.sh`, 2026-10-31): the whole chain from the Agilex board in
  git, rerunnable (~3 min, work files in `build/phase5/`): sync → floorplan → `phase5_vias.py` → KiCadRoutingTools
  `bga_fanout` → `phase5_decaps.py` → KiCadRoutingTools `place_simple` (inputs `tools/phase5/groups.json`,
  `intent.json`) → `phase5_decaps.py --legalise`.
  - **Via-in-pad on U1** (JLC fills and caps via-in-pad free on 6+ layers): every plane ball has a 0.30/0.15 via in
    its 0.30 mm pad; KRT escapes the 84 signal balls under-pad, 74 on F.Cu between the balls and 10 through a
    via in their pad, 0.09 mm tracks at 0.125 mm clearance. The via is the pad's size, so 0.125 mm copper
    clearance is JLC's 0.2 mm via-hole-to-track on every layer (a dog-bone fan-out, as on the proven card,
    was tried first: it fills the diagonal gaps the decaps and routing want).
  - **Decoupling** (`phase5_decaps.py`, each pose checked with pcbnew's collision tests at 0.1 mm copper, 0.2 mm
    hole): all on the bottom. Core VCC 1n/10n first, straight on adjacent VCC/GND ball vias in the centre;
    each other cap at the nearest spot where its pads reach their plane through an existing via (≤ 0.8 mm
    stub) or a new 0.30/0.15 via in the pad. U1 has only 11 GND balls and a new via under the ball field would
    hit the F.Cu escapes, so most VCCIO/VCCAUX/VCCIO33 caps sit 2–5 mm out, each with its own vias into the
    planes. Escape corridors (2.5 mm beyond every escape end) are kept free. VCCA caps next to their ball,
    VCCA side left to the router; beads further out. CRESET_N RC, CDONE/CSI/TEST_N pull-ups and REF_RES at
    their balls; translator caps (pin 14 VCCA, pin 13 VCCB) and R67 under the translators.
  - **KRT place_simple** placed the flash pull-ups (near U7) and the JTAG pull-ups (near J2). Its generic decap
    placement was tried for all parked parts first and dropped: caps on other nets' fan-out vias, translator
    caps in the J1 path.
  - DRC (zones refilled, original rules): no clearance, hole or courtyard errors; unconnected 228, HyperRAM
    length rule (11, unrouted), dangling escape stubs and vias, silk; schematic parity 0.
  - Later changes (same day): U9 (HyperRAM) turned to 270° (7 HyperRAM airwire crossings instead of 59);
    R25 moved off its caps; U7/U9 plane balls get via-in-pad too; no FPGA decap or bead in the band between the
    BGA's south edge and J1 (`SOUTH_BAND`), which carries ~24 translator/header nets (FB7 now 10 mm from G10).
- [x] **Supply copper** (2026-11-11, `tools/phase5_power.py`, step 7 of `phase5_layout.sh`). An audit found the
  pours still in their Agilex shapes: the L4 +0V95 island missed M3 and the west core decaps, neither buck output
  pour on B.Cu had a via to L4 (the 3.3 V one sat under the stale island), U2's feedback divider (R1/C77/R2) was
  open, the L3 +1V8 outline stopped short of the translators, ~20 supply/GND pads had lost their via, plus a dead
  via and a PG_1V8 track on L4. Now: dead copper removed; 6 + 5 stitching vias in the 0.95 V and 3.3 V buck pours;
  23 pad taps (via in pad, or a short stub); one +1V8 pour over all of L3; L4 split by KRT route_planes with
  `phase5_planes.py notch` now trying each channel, refilling and keeping it only if the +3V3 via joins the main
  +3V3 fill (8 notches). Result: every +0V95/+3V3/+1V8 via reaches its plane, one island per plane net, nothing
  orphaned; DRC clean apart from routing, schematic parity 0. Left for routing: the translators' supply pins to
  their cap vias, U10/U13 GND (TSSOP, no room for a tap), the U6 LDO (+5V in, +3V3A out, C15), the PG_0V95/PG_1V8
  enable lines (two PG_1V8 vias at (77.73, 102.28) and (79.81, 104.60) are the old layer change), VCCA filters.
- [x] **Decoupling under the BGA** (2026-11-13, `tools/phase5_decaps.py`). The 1n/10n/100n 0201s may now sit
  inside U1's ball field on the lattice of ball vias and diagonal gaps (pads 0.64 mm apart on the 0.65 mm pitch:
  one pad on a plane ball's via, the other on a new via in a gap); nothing else may go under the field (R65, the
  unused bank 3A's REF_RES, goes there as a last resort). Plan order changed: core 1n/10n/100n, each VCCA's 1n,
  bank 1n/10n, one 10n per VCCA, bank 100n, VCCAUX and HVIO small caps, then the other VCCA 10n/100n. Limit found: of the 196 gaps only 42 take a via, since the F.Cu under-pad
  escapes run through the rest, and the I/O banks have almost no GND balls, so most bank caps need a gap via
  for GND; with clean 0201 courtyards (one free ball between caps) the field holds about 25 caps. Result
  (same fanned-out board, old → new mean distance to the balls): HSIO+VCCAUX 21 caps 4.14 → 2.81 mm, HVIO 100n
  4.25 → 2.02 mm, core 12 caps 1.66 → 1.46 mm; VCCA 10n/100n worse (TL 1.67 → 4.14, TR 4.37 → 5.77 mm).
  With one 10n per VCCA moved ahead of the bank 100n, that 10n lands 2.5–4.5 mm from its VCCA ball (TL 2.5, TR
  3.8, BL 4.5, BR 3.8); the VCCA balls sit where the gaps are taken by escapes, and their pads join by routing.
  Also: the placers keep the SW netclass's 0.15 mm from the switch nodes; `phase5_planes.py notch` keeps a via's
  holes in the +3V3 fill test (a via in a hole of the island was taken as joined), starts the channel at the via,
  tries 1.5 mm wide and closer to +0V95 vias when 0.9 mm fails, and rejects a channel that cuts a +0V95 via off.
- [x] **Leaner decoupling** (2026-11-13, user's scheme, `tools/sch_decoupling_47n.py`; see docs/ti60_requirements.md).
  One 47n per used power ball, one 100n per rail, one 47u per rail at its regulator; no 1n/10n, no FPGA-side
  bulk; VCCA_TL/TR/BR on VCC (only PLL_BL0 is used), VCCA_BL: FB8 + 1u + 47n. 44 parts removed (41 caps,
  FB6/FB7/FB9) plus 3 PWR_FLAGs, 29 caps re-valued to 47n, C147 now 47u 0603. J1_P33 stays on HVIO BL: that bank
  carries JTAG, so moving it would not make BL unused (BR and TR are full anyway). ERC 0, check_schematic 0 errors.
  Layout: every 47n placed at its own ball (VCC 0–2.2 mm, mean 1.0; HSIO 0.2–4.1, mean 2.1; VCCAUX 2.1–3.4;
  VCCIO33 0.5–0.8 mm), the 47u caps 1.7–2.2 mm from their inductor's output pad; planes one island each, parity 0,
  unconnected 162 (was 183).
- [ ] **Planes and routing** (`tools/phase5_route.sh` → `build/phase5/routed.kicad_pcb`, not yet in `hardware/`):
  L4 split by KRT route_planes (+0V95 island, +3V3 around) with notches for the +3V3 vias it caught
  (`phase5_planes.py`); L3 +1V8 pour dropped before routing and poured again after; HyperRAM; all nets on a
  0.025 mm grid. First result: 65 unconnected items in KiCad (≈ 28 signal nets), 2 clearance (old Agilex JTAG arcs
  against PG_0V95), 2 vias at the board edge. Open, in order of weight:
  After the ball swap to 2A/2B (2026-10-31, FB7 allowed in the band's free middle): 44 unconnected items
  (was 65), 27 KRT-failed nets. Translator inputs all routed except EPWM2B_1V8 and one XLAT_OE_N pad; still open:
  9 translator outputs to J1, the HVIO header nets J1_P26/28/30/32, TX, HT_SDATA, JTAG (TCK/TMS/TDI), CRESET_N,
  VCCA_TR/BL, HR_CS_N/HR_DQ2 (broken by the run), a few +1V8/+3V3/GND taps; 2 clearance (HR_DQ3 against R56's
  pad, 0.097 mm), R56/C87 courtyards. The user may finish the band by hand.
  1. **South band congestion** (before the swap). The translator inputs (3A/3B), the translator outputs and the direct HVIO header
     nets (J1_P19–P32, TX, CUK/HT data) all cross the 8 mm between the BGA and J1; the translators sit at 4 mm pitch
     with no channel between them on F.Cu, and J1's 1.27 mm row-2 pins are reachable only through one centred
     channel each. Options: move translator inputs to the unused east banks 2A/2B (pin plan + Efinity check),
     translators on the bottom, or hand-route the band.
  2. **Old Agilex copper** that phase5_sync kept is broken: JTAG arcs near J2, the PG_1V8/PG_0V95 enable lines
     (cut where the old BGA was), J1-side stubs. Strip and reroute.
  3. **HyperRAM matching:** routed 10.9–16.9 mm, no room for meanders; the `.kicad_dru` rule (10.8 ± 0.1 mm,
     Agilex geometry) needs a new target or a window.

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
2. **3.3 V I/O:** 4 × SN74AVC4T774RSVR (UQFN-16) for the 15 header outputs + relay (changed from 2 × SN74AXC8T245PWR, TSSOP-24, after a stock search for a smaller package); all 12 J1 spares connected directly to HVIO.
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
- **Efinity Power Estimator** for the Ti60 core current.
- Optional: Titanium Packaging User Guide (F225 drawing, ball size) and the Ti60F225 3D STEP model.
