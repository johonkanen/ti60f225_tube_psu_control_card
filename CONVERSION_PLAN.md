# Conversion plan: Agilex 3 control card → Efinix Ti60F225

Written 2026-10-30. Source design: `~/dev/ti60f225_control_card` (despite the folder name, an Altera Agilex 3
A3CZ065BB18AE7S card; GitHub remote `agilex3_control_card`), state at commit `43b9ec7`, "ready to order",
fully routed, DRC clean. Target: the same card with an Efinix Titanium **Ti60F225** in this repository
(`ti60f225_control_card`).

Legend: **[keep]** reuse as is, **[mod]** reuse with changes, **[new]** new part or block, **[drop]** remove,
**[verify]** fact still to be confirmed from an Efinix document before it is designed in.

Sources used for this plan:
- `reference/ti60f225_pinout.csv` (in this repo): all 225 balls with pad name, bank, type (HVIO/HSIO/power/
  dedicated), configuration function, LVDS pair and clock region. Built from Efinix `ti60_pinout-v0.5.xlsx`
  (Final, sheet Ti60F225) and cross-checked against the Efinity 2026.1 device database
  (`~/efinity/2026.1/pt/db/resource/Ti60F225.db`): all 225 balls agree. The only difference is G6, which the
  database calls `VQPS_GND` and the spreadsheet `GND`; it goes to GND either way.
- Ti60F225 dev board schematic v1.3 (`~/Downloads/ti60f225-dev-board-schematics-v1.3.pdf`).
- The user's earlier Proteus Ti60F225 PSU control card (`ti60f225_psu_control_card.PDF` and its CADCAM zip in
  Downloads), which is a working Ti60F225 design: 3 × AP61202 (1 V core, 1V8, 3V3), all HSIO banks at 1.8 V,
  HVIO at 3.3 V, REF_RES 10 k to GND, W956A8MBYA HyperRAM, W25Q64JW flash, 5 × SN74AXC8T245 level shifters.
- `~/dev/efinix_soc_board` (Ti135 conversion of a similar card): Titanium configuration straps, JTAG, flash and
  sequencing notes in `MIGRATION_PLAN.md`, `TI135_PCB_NOTES.md` and `HW_CHECKLIST_REVIEW.md`.

---

## 1. What changes, in one table

| Item | Agilex 3 card (source) | Ti60F225 card (target) |
|---|---|---|
| FPGA | A3CZ065, 65k LE, B18A 474 balls | Ti60F225, 60k LE, 225-ball FBGA, 15 × 15 array (rows A–R) **[verify]** pitch and body size from the Efinix package drawing (expected 10 × 10 mm, 0.65 mm) |
| 3.3 V-capable I/O | ~160 HVIO on 6A–6H, everything direct | **23 HVIO** only: TL 7, TR 7, BR 7, BL 2 (+ JTAG). 140 HSIO (1.2–1.8 V) in banks 1A/1B (left), 2A/2B (top), 3A/3B (right), 4A/4B (bottom) |
| Core | 0.75 V, remote sense | **0.95 V** VCC **[verify]** for the chosen grade (dev board: "0.85–0.95 V for VCC"); 4 × VCCA (TL/TR/BL/BR) filtered from VCC; no sense balls |
| Other FPGA rails | 1.8 V (VCCPT…), 1.2 V (VCCRCORE, PIO), 3.3 V HVIO, 1.8 V_HR | 1.8 V: VCCAUX + all 8 HSIO VCCIO; 3.3 V: VCCIO33_TL/TR/BL/BR. **No 1.2 V, no separate 1.8 V_HR** |
| Configuration | SDM, AS ×4, MSEL straps, RREF, OSC_CLK_1 | SPI active ×4 from bank 1A (SSL_N P1, CCK N1, CDI0–3 M1/L1/H5/H4), CRESET_N J5, CDONE L3, CBSEL0/1 F3/E3, TEST_N E2, NSTATUS E1, CSI N2, 8 × REF_RES |
| JTAG | 1.8 V SDM, SN74AVC4T774 shifter | dedicated pins TCK N4, TMS N3, TDI P3, TDO M4 in bank BL → powered by VCCIO33_BL at 3.3 V → **shifter dropped** **[verify]** |
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

HVIO available: 23. Proposed allocation:

| Signals | Where | How |
|---|---|---|
| HyperRAM (12 used, CK# unused), CLK100M | HSIO, one 1.8 V bank close to the HyperRAM, clock on a PLLIN ball | direct, 1.8 V |
| ADC SPI (6) | HSIO | **[mod]** ADS7056 **DVDD → +1V8** (DVDD range 1.65–3.6 V, AVDD stays on +3V3A). Frees 6 HVIO; the earlier Ti60 card already did this |
| 15 PWM / gate-drive / SPI outputs to J1 | HSIO → **2 × SN74AXC8T245** (1.8 V → 3.3 V, DIR fixed A→B) | **[new]**. OE driven so the outputs stay Hi-Z (power board pull-downs hold them low) until the FPGA is configured and the design enables them. 1 channel left for a spare |
| 3 header inputs (HT_SDATA, CUK_SDATA, RX) | HVIO | direct 3.3 V |
| TX, GPIO_BYPASS_RLY | HVIO | direct |
| Mux selects (6) | HVIO | direct, keeps the SN74LV4051A |
| LEDs (6) | HVIO | direct |
| J1 spares | the leftover HVIO (23 − 3 − 2 − 6 − 6 = 6) + 1 translator channel | 7 of 13 spares connected; the rest unconnected (or add a third translator, see decisions) |

Alternatives, if HVIO gets tight during placement:
- Replace the SN74LV4051A with a mux that has 1.8 V-logic selects at 3.3 V supply (e.g. TMUX1308): frees 6 HVIO.
  Needs a check of on-resistance, leakage and charge injection against the ADS7056 front end, and JLC stock.
- One RGB LED instead of two: frees 3 HVIO.
- Put the 3 inputs on HSIO through a translator or a resistor divider: frees 3 HVIO but adds parts.

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
| `config.kicad_sch`: SDM straps (MSEL, nCONFIG, nSTATUS, RREF), SN74AVC4T774, OSC_CLK_1 link | **[drop]** → **[new]** Efinix straps | CRESET_N pull-up + reset release from the last power-good (or a supervisor, as TPS3808 on the Ti135 board); CDONE 10 k pull-up (+ optional LED); SSL_N pull-up (active mode) **[verify]** polarity; CBSEL0/1 pulls (single image); TEST_N pull-up; CSI pull-up; NSTATUS optional; REF_RES_1A…4B 10 k 1 % to GND (8 resistors); VQPS_GND to GND; JTAG pulls per Efinix |
| U? MT25QU256 1.8 V QSPI flash (BGA-24) | **[keep]** part and footprint, **[mod]** connections | Bank 1A (1.8 V) → no level issue. RESET# no longer a configuration pin: 10 k pull-up to +1V8 or an FPGA GPIO. Check the part is on Efinix's supported-flash list for Titanium **[verify]**. Bitstream is far below 256 Mbit; a 128 Mbit part would also do (only if it saves cost/stock trouble) |
| HyperRAM W958D8NBYA5I | **[keep]** part, footprint, decoupling; **[mod]** FPGA side | Supply moves from +1V8_HR to +1V8. Re-route and re-match lengths (DRC rule `hyperram_length` kept) |
| 100 MHz oscillator OT3225100MJBA4SL | **[keep]** | One load (PLLIN) instead of two (D18 + OSC_CLK_1). Bead + 470 nF from +1V8 kept. 25 MHz twin fits if a lower reference is preferred |
| U2 AP61302 core buck | **[mod]** to 0.95 V | 0.6 V FB: R_top/R_bot = 0.583 → e.g. 118 k / 200 k (0.954 V) or 115 k / 200 k (0.945 V); choose JLC basic values. Ti60 has no VCCLSENSE/GNDSENSE: drop the sense pair and the 100R/10R fallbacks, feed back locally or Kelvin to a VCC via under the BGA. Re-check C77 feed-forward for the new divider. Current from the Efinity Power Estimator; AP61302 (3 A) is likely oversized, an AP61102 cell would do if the estimate is under ~0.7 A |
| U3 AP61102 +1V8 | **[keep]**, **[mod]** loads | Now VCCAUX + all HSIO banks + HyperRAM + flash + oscillator + ADC DVDD + translator A sides. Re-check 1 A rating |
| U4 AP61102 +3V3 | **[keep]** | VCCIO33 × 4, translator B sides, LEDs, mux logic |
| U17 AP61102 +1V2, U18 AP61102 +1V8_HR | **[drop]** | No 1.2 V or separate HyperRAM rail needed; removes two buck cells (~24 parts) |
| FB1–FB5 ferrite filters (PLLDIG, PLL, ADC, RCORE, OSC) | **[mod]** | → 4 × VCCA filters from VCC (dev board: VCCA_xx_FIL) + the oscillator bead |
| Forced-PWM EN dividers (R46–R51), PG chain | **[mod]** | Chain becomes 0.95 V → 1.8 V → 3.3 V → CRESET_N release. Sequencing rules **[verify]** in the Ti60 datasheet (power-up sequence section); hold CRESET_N low until all rails are good regardless |
| U6 TLV75533 +3V3A, ADC chains (4051, OPA365, ADS7056) | **[keep]** | Only ADS7056 DVDD moves to +1V8 |
| J1 2 × 25 header, J2 JTAG 1 × 5 | **[keep]** footprints and positions | J2 is now direct 3.3 V JTAG to the FTDI cable. Efinix programming (and openFPGALoader `spiOverJtag_efinix_ti60f225`) both work over JTAG |
| RGB LEDs D1/D2 | **[keep]** | on HVIO |
| — | **[new]** 2 × SN74AXC8T245 + decoupling, OE control | Check JLC stock; the earlier Ti60 card used this part |
| Outline, stackup, JLC rules | **[keep]** | 32.5 × 33.8 mm, 6 layers JLC06161H-3313, via-in-pad, `control_card.kicad_dru`. 4 layers may now be possible but is not the plan |

---

## 4. Phases

### Phase 0: repository setup (now)
- [x] `git init`, repository name `ti60f225_control_card` (not yet on GitHub; the source's remote is
  `agilex3_control_card`, so the name is free).
- [x] This plan and `reference/ti60f225_pinout.csv`.
- [ ] Copy from the source: `hardware/` (project, sheets, libs, `.kicad_dru`), `reference/power_board_header.csv`,
  `reference/mux_assignment.csv`, `reference/jlc_parts.csv`, `docs/` (to adapt), `LICENSE`, `.gitignore`.
  Rename the project files to `ti60f225_control_card.*` (or keep `control_card.*`; see decisions).
- [ ] Add `tools/jlc` as a submodule (`https://github.com/johonkanen/jlc-tools.git`).
- [ ] Copy only the generator scripts worth adapting (`make_bga_footprint.py`, symbol generation idea from
  `efinix_soc_board/tools/gen_symbols.py`); do not bring the Agilex build chain.

### Phase 1: decisions and device data (before touching KiCad)
- [ ] Part number / grade (speed and temperature): e.g. Ti60F225I3 vs C4. Sets the core voltage and availability.
  Check DigiKey / JLC Global Sourcing.
- [ ] Package drawing: pitch, body size, ball diameter, recommended land → footprint. Cross-check against the
  earlier Ti60 card's CADCAM footprint.
- [ ] Ti60 datasheet: supply ranges, power-up sequence, CRESET_N timing, configuration pin polarity, JTAG bank voltage.
- [ ] Efinix Titanium hardware checklist (`Print Checklist and Guidelines titanium.htm` in Downloads) and the
  dev-board schematic: decoupling per rail, VCCA filter values, REF_RES value, strap values.
- [ ] Efinity Power Estimator for a realistic design (HyperRAM controller, ADC capture, PWM) → core current → buck
  choice and inductor rating.
- [ ] Confirm the I/O plan in section 2 (translators, spares, mux choice).

### Phase 2: libraries
- [ ] Symbol `hardware/lib/ti60f225.kicad_sym` generated from `reference/ti60f225_pinout.csv`, multi-unit.
- [ ] Footprint `Efinix_F225` (BGA, 15 × 15) generated by script from the package drawing; NSMD pads like the
  B18A footprint; check against KiCad's generic `BGA-225_..._P0.65mm` if one matches.
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

## 5. Open decisions for the user

1. **FPGA grade** (temperature and speed): which Ti60F225 ordering code?
2. **3.3 V I/O strategy:** translators for the 15 header outputs (proposed), or a different split? How many of the
   13 J1 spare pins must stay connected?
3. **Translator OE source:** a dedicated FPGA pin (held off by a pull-up/pull-down during configuration), CDONE, or both?
4. **Mux:** keep SN74LV4051A on HVIO (proposed), or switch to a 1.8 V-logic mux to free 6 HVIO?
5. **Core regulator:** keep the AP61302 cell or downsize to an AP61102 once the power estimate is in?
6. **Project file names:** keep `hardware/control_card.*` or rename to `ti60f225_control_card.*`?
7. **Start point:** copy the routed Agilex board and strip the FPGA region (proposed: keeps the solved edge
   placement, buck cells and J1 fan-out), or start a fresh board with only the outline and connectors?
