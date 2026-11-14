# Interchangeable I/O (for routing)

While routing, swap pins inside a group whenever that removes a crossing or a via. Apply FPGA swaps with
`tools/swap_balls.py NET=BALL ...`, then `efinity/pinplan/run.sh --compile` and `tools/check_schematic.py`
(HyperRAM balls also with `tools/hyperram_balls.py`).
State as of 2026-11-14, the layout experiment with **U1 at 180°** (`reference/pin_assignment.csv`; reasons in
`CONVERSION_PLAN.md`, phase 5, "U1 at 180°"). With U1 at 180° the package sides are: north = rows P/R (banks 4A/4B,
HVIO BR in the north-west corner, BL with JTAG and bank 1A's flash balls in the north-east corner), east = columns
1/2 (1A north, 1B south), south = rows A/B (HVIO TR south-west, 2A/2B, HVIO TL south-east), west = columns 14/15
(3B north, 3A south).

Two things differ from the rules this file had before the experiment, and need the user's approval:
the **HyperRAM is on banks 4A/4B**, not 1B (bank 1B ends up on the east side, 20 mm from any place the HyperRAM
can sit), and **three translator inputs and XLAT_OE_N are on bank 1B** (free after that move, at the south-east
corner next to U19).

## Fixed: do not move

| What | Balls |
|---|---|
| Flash (SPI active x4) | CCK N1 FLASH_CLK, SSL_N P1 FLASH_CS_N, CDI0–3 M1/L1/H5/H4 FLASH_IO0–3, CSI N2 |
| PLL reference | P2 CLK100M (PLL_BL0 REFCLK0) |
| JTAG, configuration | TCK N4, TMS N3, TDI P3, TDO M4, CRESET_N J5, CDONE L3, TEST_N E2 (10 k pull-up R56, a net of its own now), REF_RES F6/N12/B15 |
| J1 connector | its pinout belongs to the power board |

Free balls with a configuration function that should stay unused: E3/F3 (CBSEL1/0), J2 (EXT_CONFIG_CLK), M2 (CSO),
L6 (SSU_N). The CDIx balls above CDI3 are only used in x8/x16 modes, so they are ordinary I/O here.

## Groups

### 1. Translator inputs: HSIO banks 2A + 2B + 1B (1.8 V), 17 nets

Any net to any ball of these banks. The sixteen inputs leave the BGA's south edge (rows A/B) and the south end of
its east edge in the order of the translator pins, west to east = U22 … U19; XLAT_OE_N leaves the east edge.

| Bank | Used | Free |
|---|---|---|
| 2B | B11 PFC_PWM2, A11 EPWM1A, B10 PFC_PWM1, A10 GPIO_BYPASS_RLY (U22); B9 HT_CLK, A9 SYNCH_1 (U21) | C8 C9 C10 D8 D10 E8 E9 E10 F9 F10 |
| 2A | B8 CUK_CLK, A8 EPWM2B (U21); B7 SYNCH_2, A7 EPWM2A, B6 HT_CS, A6 CUK_CS (U20); A5 EPWM5A (U19) | C6 D5 D7 E6 E7 F7 F8 |
| 1B | A2 PRI_DHB_LO, B1 EPWM6A, C1 PRI_DHB_HI (U19); D1 XLAT_OE_N | B2 C2 E1 F1 F2 F5 G1 G2 G3 G4 G5 H1 H2 (E2 is TEST_N, E3/F3 CBSEL) |

(Net names without the `_1V8` suffix.) The row-C balls of 2A/2B are free but poor: their fan-out escapes come out
between the header nets of TR or on the west edge.

### 2. Translator channels: U19–U22 (SN74AVC4T774, all A→B)

Any channel of any of the four chips can carry any of the 16 nets; A and B side move together
(A1 pin 1 ↔ B1 pin 12, A2 2 ↔ 11, A3 3 ↔ 10, A4 4 ↔ 9). The J1 pin of each net stays. Unchanged:

| Chip | Ch 1 (1→12) | Ch 2 (2→11) | Ch 3 (3→10) | Ch 4 (4→9) |
|---|---|---|---|---|
| U19 | PRI_DHB_HI → J1.3 | EPWM6A → J1.4 | PRI_DHB_LO → J1.5 | EPWM5A → J1.6 |
| U20 | CUK_CS → J1.7 | HT_CS → J1.8 | EPWM2A → J1.9 | SYNCH_2 → J1.10 |
| U21 | EPWM2B → J1.11 | CUK_CLK → J1.13 | SYNCH_1 → J1.14 | HT_CLK → J1.16 |
| U22 | GPIO_BYPASS_RLY → J1.18 | PFC_PWM1 → J1.20 | EPWM1A → J1.21 | PFC_PWM2 → J1.34 |

### 3. HyperRAM: HSIO banks 4A + 4B (north edge), 12 nets

Each signal keeps its role (DQ0–DQ7 carry command/address bits). The balls are the outer two rows of the north
edge, west to east in the order in which the lines leave the HyperRAM (U9 at 90°, `tools/phase5_mem.py`):

| P12 | R12 | P11 | R11 | P10 | R10 | P9 | R9 | P8 | R8 | P7 | R7 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| RESET# | CS# | CK | DQ2 | RWDS | DQ4 | DQ3 | DQ1 | DQ0 | DQ7 | DQ6 | DQ5 |

Free on the same two rows: P5 P6 R5 R6 (next to the JTAG balls). The balls also live in
`efinity/pinplan/hyperram_gpio.isf` and in `tools/check_schematic.py`.

### 4. ADC: HSIO banks 3A + 3B (west edge), 12 nets

Any ADC net to any ball of either bank. Bank 3B is decoupled with C180/C181 (47n at J11, L14), 3A with C178/C179.
North to south on the west edge: ADC A (parts north-west), ADC B (series resistors just west of the edge), mux A
selects, mux B selects (muxes south-west).

| Bank | Used | Free |
|---|---|---|
| 3B | M15 ADCA_SCLK, L15 ADCA_SDO, K15 ADCA_CS_N, J14 ADCB_CS_N, J15 ADCB_SCLK, H15 ADCB_SDO | H10 H11 J10 J12 J13 K10–K14 L11 L12 L13 M14 |
| 3A | G15 ADASEL0, F15 ADASEL1, E15 ADASEL2, D15 ADBSEL2, C14 ADBSEL1, C15 ADBSEL0 | C13 D13 D14 E12 E14 F11 F12 F13 G11 G13 G14 H12 H13 H14 |

### 5. Direct 3.3 V nets: HVIO banks TL, TR, BR, BL, 22 nets, 1 free ball (N13)

Within a bank: any net to any ball. Across banks: trade nets so each bank keeps ≤ 6 outputs (Efinix 3.3 V limit;
TL, TR and BR are at 6, BL at 1). There are 19 outputs for 18 places on TL/TR/BR, so one output has to sit on BL.

| Bank | Corner | Used (in = input) | How it reaches its part |
|---|---|---|---|
| BR | north-west | N14 LED1_R, P15 LED1_B, P14 LED1_G, R14 LED2_R, P13 LED2_B, R13 LED2_G | F.Cu to the LED resistors |
| TR | south-west | B14 J1_P33, A14 J1_P32, A13 J1_P30, B12 J1_P28, A12 RX (in) | F.Cu, in J1 pin order |
|  |  | C12 J1_P29, D12 J1_P31 | L3 from a via in the ball pad |
| TL | south-east | C4 J1_P27, C5 J1_P26, B5 TX, A4 J1_P24, A3 J1_P22, B3 J1_P19, C3 CUK_SDATA (in) | L3 from a via in the ball pad, in J1 pin order |
| BL | north-east | R3 J1_P17, R4 HT_SDATA (in) (JTAG also on this bank: M4/N3/N4/P3) | L3 down the east side |

The TL order follows the way each ball's via can leave on L3 between its neighbours' vias (C4 only to the
north-west, C3 only to the east), not the plain column order.
