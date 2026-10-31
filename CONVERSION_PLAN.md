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
  1B (HyperRAM) north-east, 4A/4B (ADC) west, 3A/3B (translators) and HVIO TR/BR south towards J1, 2A/2B
  (unused) east, HVIO TL north-east and BL north-west. Because 1B ends up east of 1A, **U9 (HyperRAM) and U7
  (flash) swapped places**, their via-in-pads moving with them; the HyperRAM's three 0402s and the flash's
  100 nF sit on VCC/VSS ball pairs underneath; R24 beside the HyperRAM. **Translators U19–U22** in a row on the
  top side at y 122.5, x 104.5 → 92.5 (4 mm pitch, ordered by J1 pin), 1.8 V side towards the FPGA.
- [x] DRC: 0 errors other than unconnected items (419) and the HyperRAM length rule (nets unrouted);
  schematic parity 0.
- [ ] Place the rest: Ti60 decoupling (centre VCC/GND ball pairs for 0201s; VCCIO, VCCAUX, VCCIO33 and the
  four VCCA bead filters around the BGA on the bottom, as the full 0.65 mm array leaves no room for extra vias),
  configuration passives near bank 1A / the CONFIG balls, translator decoupling and the OE pull-up.
- [ ] BGA fan-out (via-in-pad on supply/GND balls), plane rework (L3 +1V8, L4 +0V95 island over the new core
  balls + +3V3), routing (HyperRAM length-matched, ADC SPI, translators, HVIO, JTAG, config), DRC clean.

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
