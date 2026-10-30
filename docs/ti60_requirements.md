# Ti60F225C4 board requirements

What the FPGA needs from the board: supply rails, I/O bank voltages, power-up order, configuration and JTAG pins,
and what the proven Ti60 card did for each. Device: **Ti60F225C4** (commercial, speed grade 4, standard 0.95 V
core; "L" grades would be 0.85 V).

Sources (checked 2026-10-30):
- *Ti60 Data Sheet* v3.9, `reference/efinix/titanium60-ds-v3.9.pdf` (DS);
- *Hardware Design Checklist and Guidelines: Ti60 F225, SPI Active x4*, `reference/efinix/ti60_hw_checklist.htm`
  (HWC);
- *Ti60 pinout* v1.0, `reference/efinix/ti60_pinout-v1.0.xlsx` → `reference/ti60f225_pinout.csv`;
- the user's **proven Ti60F225 PSU control card** (Proteus, built and tested), `reference/ti60_psu_card/`:
  schematic PDF, project `.pdsprj`, and two CADCAM exports (`_v1` from 2023-04-02 is the one ordered; the later
  export has the same parts and differs in coordinates);
- Efinix Ti60F225 dev board layout (`~/Downloads/ti60f225-layout-v1.0.zip`, PADS ASCII): uses a socket footprint,
  so its pads are not a reference for a soldered part. Only the 0.65 mm pitch is taken from it.

## 1. Package

| Item | Value | Source |
|---|---|---|
| Package | 225-ball FBGA, 10 × 10 mm, **0.65 mm pitch**, 15 × 15 full array, rows A–R (no I, O, Q) | DS Table 3; dev board decal |
| Land | **0.30 mm round copper pads** | proven card's IPC-356 (U10 pads `X0300`); same as the Agilex B18A footprint |
| Proven card build | 4 layers (Inner 1, Inner 2), vias 0.2 and 0.3 mm drill | proven card CADCAM |

The proven card fanned out the 0.65 mm BGA on 4 layers. This card stays on 6 layers with via-in-pad (the Agilex
stackup), which is easier; 4 layers is a possible cost reduction later.

## 2. Supply rails

| Rail | Balls | Nominal (C4) | Rule | Proven card | This card |
|---|---|---|---|---|---|
| VCC | E13 G7 G9 H6 H8 J7 J9 M3 | 0.95 V (0.92–0.98) | regulator must supply ≥ 500 mA transient at power-up (DS Table 30) | AP61202, 200k / (680k ‖ 680k) = 0.953 V, 2 × 10 µF out | +0V95 |
| VCCA_TL/TR/BL/BR | E5 G10 L10 L5 | 0.95 V (as VCC) | **separate filter per VCCA**; unused PLL: still connect to VCC | from 1V via filter | 4 × bead + caps from +0V95 |
| VCCAUX | D4 E11 L4 M11 | 1.8 V **±50 mV** (1.75–1.85) | tight: check buck FB accuracy + divider tolerance | 1V8 | +1V8 |
| VCCIO (HSIO) 1A…4B | C11 C7 D2 D6 D9 F14 F4 G12 J11 J4 L14 L2 N11 N5 N7 N9 | 1.2/1.35/1.5/1.8 V | no mixed voltages in a bank; config bank 1A must match the flash | all 1V8 | all +1V8 |
| VCCIO33 TL/TR/BL/BR | B4 B13 P4 N15 | 1.8/2.5/3.0/3.3 V | BL also powers JTAG | all 3V3 | all +3V3 |
| VQPS_GND | G6 | — | to GND (fuses never blown) | DGND | GND |

Decoupling recommended by HWC (per supply; "per bank" for VCCA, VCCIO, VCCIO33; unused banks need none):

| Supply | 100 µ | 47 µ | 10 µ | 4.7 µ | 1 µ | 100 n | 10 n | 1 n |
|---|---|---|---|---|---|---|---|---|
| VCC | 1 | 1 | – | 1 | 1 | 5 | 5 | 2 |
| VCCA (each) | – | – | – | – | – | 2 | 2 | 1 |
| VCCAUX | – | – | – | 1 | – | 1 | 1 | 1 |
| VCCIO (each HSIO bank) | – | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| VCCIO33 (each HVIO bank) | – | – | – | 1 | 1 | 1 | – | – |

HWC also asks for at least one 47 µF at each regulator output, and a π or τ filter (bead/inductor) on every power
outlet, with VCCA filtered separately. The proven card used much less (10 µF out, no per-rail beads) and works;
this card follows the checklist where it fits, prioritising VCCA filters and the 47 µF bulk caps.

## 3. Power-up order (DS p. 57/58, HWC)

1. VCC and VCCA first (any order).
2. VCCAUX and all VCCIO after VCC/VCCA are stable; for F225 lots marked "S", at least 10 µs after VCC/VCCA reach
   90 %.
3. CRESET_N low until all supplies are up, released at least 10 µs after the last one reaches 90 %
   (tCRESET_N ≥ 320 ns for a reconfiguration pulse).
4. Ramp rate for every supply: 0.1 × V per ms to 10 V/ms (i.e. ramp in ≤ 10 ms, not faster than 10 V/ms).
5. No power-down order (VQPS is grounded).
6. Do not drive any FPGA pin before its bank is powered: an external voltage on CRESET_N during power-up can leave
   the FPGA stuck in configuration mode.

Proven card: core buck EN tied to 5 V; its PG (pulled to 5 V by 10k) enables the 1.8 V and 3.3 V bucks together;
CRESET_N held low by an RC (330 k to 1V8, 1 µF to GND, τ ≈ 0.33 s).
This card: same chain (0.95 V → PG → 1.8 V and 3.3 V), with the Agilex card's forced-PWM EN dividers. CRESET_N
from an RC like the proven card or a supervisor (HWC prefers a supervisor IC; decide in phase 3).

## 4. Configuration (SPI active)

| Pin | Ball | Rule (DS Table 73/74, HWC) | Proven card | This card |
|---|---|---|---|---|
| CRESET_N | J5 | pull-up; held low at power-up (§3) | 330 k + 1 µF RC | RC or supervisor |
| CDONE | L3 | open drain, pull-up to VCCIO; never held low | 100 k to 1V8 | 10 k to 1V8 (HWC value) |
| SSL_N | P1 | pull-up = active mode; chip select to the flash | 100 k to 1V8 | 10 k |
| CCK | N1 | flash clock | DCLK, 100 k pull-up | direct |
| CDI0–CDI3 | M1 L1 H5 H4 | x4: all four to the flash IO0–IO3 | **x2**: CDI0/1 only; flash IO2/IO3 tied to 1V8 | **x4** wiring with 10 k pull-ups on IO2/IO3; x2 stays possible from Efinity settings |
| CSI | N2 | pull-up (high = selected; must stay high) | 100 k | 10 k |
| TEST_N | E2 | pull-up | 100 k | 10 k |
| CBSEL0/1 | F3 E3 | no resistors needed for single image | open | open (or pulls if multi-image is wanted) |
| NSTATUS | E1 | optional LED | open | open / optional |
| EXT_CONFIG_CLK | J2 | optional | unused | unused (internal oscillator) |
| REF_RES_2A, 4A | F6, N12 | **must** have 10 k 1 % to GND | all 8 REF_RES with 10 k | 2A, 4A, 3A |
| REF_RES_3A | B15 | 10 k 1 % if the internal oscillator is used (active configuration clock) | — | yes |
| other REF_RES | — | only for LVDS/MIPI TX banks | — | open |

Configuration clock: internal oscillator, up to DIV1 = 80 MHz typical. The flash must be faster than that, at
1.8 V (bank 1A), and hold a 13,960,000-bit image (Ti60 maximum). **IS25WP128-RHLE** (128 Mbit, 1.8 V, 133 MHz):
9 images fit. Before layout: check its 24-ball ball map and dedicated RESET# against the BGA-24 footprint and
whether x4 active mode needs the QE bit set (AN 033).

## 5. JTAG

TCK N4, TMS N3, TDI P3, TDO M4, all in bank BL → VCCIO33_BL. With BL at 3.3 V the JTAG header connects directly
(no level shifter). HWC: 10 k pull-ups on all four to VCCIO; the proven card used 4.7 k to 3V3 and works.

## 6. I/O

- **HVIO** (23 balls, 3.3 V): TL 7, TR 7, BR 7, BL 2. VIH 2.1 V, VIL 0.8 V at 3.3 V LVCMOS.
  **At most 6 HVIO used as output or bidirectional per bank** at 3.0/3.3 V (switching noise; Efinity warns).
- **HSIO** (140 balls): 1.8 V LVCMOS in all 8 banks. When HSIO is used as GPIO, keep one unassigned pair between it
  and any LVDS/MIPI pins (none planned). Unused pins float.
- **Pin states:** every user HSIO/HVIO pin is a tri-stated input with weak pull-up during reset and configuration,
  and when unused. Anything on the power-board header that must stay low before the design runs needs a
  translator with OE (or a stronger external pull-down).
- **PLL reference** 16–800 MHz. PLLIN balls: PLL_BL: P2 (GPIOL_P_00_PLLIN0), R5 (GPIOB_P_00_PLLIN1);
  PLL_TL: B2 (GPIOL_P_18_PLLIN0), E6 (GPIOT_P_00_PLLIN1), C5 (GPIOL_11_PLLIN2, HVIO);
  PLL_TR: C14 (GPIOR_P_19_PLLIN0), A11 (GPIOT_P_17_PLLIN1); PLL_BR: L11 (GPIOR_P_00_PLLIN0),
  P11 (GPIOB_P_17_PLLIN1), R13 (GPIOR_29_PLLIN2, HVIO). The proven card fed its 32 MHz oscillator to C14.
- **Global clock inputs** (CLKn): A8 B8 C8 C9 D8 E8 G1 G14 G2 H1 H10–H15 H2 H3 J1 J15 J2 K1 K7 L8 L9 M8 M9 N8 P8 R8.

## 7. Operating temperature

C4 is commercial: **Tj 0–85 °C** (industrial I-grades −40–100 °C). The Agilex part was extended (0–100 °C).
