# Interchangeable I/O (for routing)

While routing, swap pins inside a group whenever that removes a crossing or a via. Apply FPGA swaps with
`tools/swap_balls.py NET=BALL ...`, then `efinity/pinplan/run.sh --compile` and `tools/check_schematic.py`.
State as of 2026-11-13 after the routing swaps (`reference/pin_assignment.csv`; reasons in `CONVERSION_PLAN.md`,
phase 5 routing).

## Fixed: do not move

| What | Balls |
|---|---|
| Flash (SPI active x4) | CCK N1 FLASH_CLK, SSL_N P1 FLASH_CS_N, CDI0–3 M1/L1/H5/H4 FLASH_IO0–3, CSI N2 |
| PLL reference | P2 CLK100M (PLL_BL0 REFCLK0) |
| JTAG, configuration | TCK N4, TMS N3, TDI P3, TDO M4, CRESET_N J5, CDONE L3, TEST_N E2 (also HR_DQ3), REF_RES F6/N12/B15 |
| J1 connector | its pinout belongs to the power board |

Free balls with a configuration function that should stay unused: E3/F3 (CBSEL1/0), J2 (EXT_CONFIG_CLK), M2 (CSO),
L6 (SSU_N). The CDIx balls above CDI3 are only used in x8/x16 modes, so they are ordinary I/O here.

## Groups

### 1. Translator inputs: HSIO banks 2A + 2B + 3A (1.8 V), 17 nets

Any net to any ball of these banks (XLAT_OE_N included). The twelve inputs of U19–U21 leave the BGA's east edge
(rows A/B) in the order of the translator pins, north to south = east to west; the four of U22 and XLAT_OE_N leave
the south edge from bank 3A, straight above U22.

| Bank | Used | Free |
|---|---|---|
| 2A | A5 PRI_DHB_HI, B6 EPWM6A, A6 PRI_DHB_LO, B7 EPWM5A, A7 CUK_CS, B8 HT_CS, A8 EPWM2A | C6 D5 D7 E6 E7 F7 F8 |
| 2B | B9 SYNCH_2, A9 EPWM2B, B10 CUK_CLK, A10 SYNCH_1, B11 HT_CLK | A11 C8 C9 C10 D8 D10 E8 E9 E10 F9 F10 |
| 3A | D15 GPIO_BYPASS_RLY, E15 PFC_PWM1, F15 EPWM1A, G15 PFC_PWM2, H14 XLAT_OE_N | C13 C14 C15 D13 D14 E12 E14 F11 F12 F13 G11 G13 G14 H12 H13 |

(Net names without the `_1V8` suffix.) Bank 3A is decoupled with C178/C179 (47n at F14, G12). Bank 3B (VCCIO on
+1V8, 20 free balls) is still unused and has no caps: its VCCIO balls J11/L14 would need a 47n each.

### 2. Translator channels: U19–U22 (SN74AVC4T774, all A→B)

Any channel of any of the four chips can carry any of the 16 nets; A and B side move together
(A1 pin 1 ↔ B1 pin 12, A2 2 ↔ 11, A3 3 ↔ 10, A4 4 ↔ 9). The J1 pin of each net stays; only which translator
channel carries it changes. Today:

| Chip | Ch 1 (1→12) | Ch 2 (2→11) | Ch 3 (3→10) | Ch 4 (4→9) |
|---|---|---|---|---|
| U19 | PRI_DHB_HI → J1.3 | EPWM6A → J1.4 | PRI_DHB_LO → J1.5 | EPWM5A → J1.6 |
| U20 | CUK_CS → J1.7 | HT_CS → J1.8 | EPWM2A → J1.9 | SYNCH_2 → J1.10 |
| U21 | EPWM2B → J1.11 | CUK_CLK → J1.13 | SYNCH_1 → J1.14 | HT_CLK → J1.16 |
| U22 | GPIO_BYPASS_RLY → J1.18 | PFC_PWM1 → J1.20 | EPWM1A → J1.21 | PFC_PWM2 → J1.34 |

The B-side pull-downs R40 (EPWM2A) and R41 (EPWM2B) go with their nets. `swap_balls.py` moves U1 balls only;
a channel swap edits the connector sheet's translator pins (not scripted yet). The channels were left as they are:
with pin 12 east and pin 9 west on every chip, they already follow the J1 pin order.

### 3. HyperRAM: HSIO bank 1B, 12 nets, 6 usable free balls

Balls can trade within 1B, but each signal keeps its role: DQ0–DQ7 carry command/address bits and must not be
permuted. HR_DQ3 shares E2 with TEST_N (10 k pull-up R56); moving HR_DQ3 off E2 frees TEST_N to its pull-up alone.

| Used | Free |
|---|---|
| B1 HR_RESET_N, B2 HR_CS_N, C1 HR_CK, C2 DQ2, D1 DQ4, E1 RWDS, E2 DQ3, F1 DQ0, F2 DQ5, G1 DQ1, G2 DQ6, H2 DQ7 | A2 F5 G3 G4 G5 H1 (E3/F3 are CBSEL) |

### 4. ADC: HSIO banks 4A + 4B (1.8 V), 12 nets, 18 usable free balls

Any ADC net to any ball of either bank (keep each ADC's SCLK/CS_N/SDO together if it shortens routes).

| Bank | Used | Free |
|---|---|---|
| 4A | P9 ADASEL1, R9 ADASEL0, P10 ADBSEL0, R10 ADBSEL1, P11 ADBSEL2 | K7 K8 K9 L8 L9 M9 M10 N10 P12 R11 R12 |
| 4B | P5 ADCA_SDO, R5 ADCA_CS_N, P6 ADCA_SCLK, R6 ADCB_CS_N, P7 ADCB_SDO, R7 ADCB_SCLK, R8 ADASEL2 | K6 L7 M6 M7 M8 N6 N8 P8 (L6 is SSU_N) |

All twelve now sit on the two outer rows of the west edge, north to south: ADC A (parts north-west), ADC B (series
resistors just west of the edge), mux A selects, mux B selects (muxes south-west).

### 5. Direct 3.3 V nets: HVIO banks TL, TR, BR, BL, 22 nets, 1 free ball (R4)

Within a bank: any net to any ball. Across banks: trade nets so each bank keeps ≤ 6 outputs (Efinix 3.3 V limit;
TL, TR and BR are at 6 now, BL at 1), e.g. output for output, or an input for an input.

| Bank | Used (in = input) | Free |
|---|---|---|
| TL | C4 LED2_G, B3 LED2_B, A3 LED2_R, C3 LED1_G, A4 LED1_B, B5 LED1_R, C5 HT_SDATA (in) | – |
| TR | B12 CUK_SDATA (in), A12 J1_P17, A13 J1_P19, C12 J1_P22, A14 J1_P24, B14 TX, D12 J1_P26 | – |
| BR | N13 RX (in), N14 J1_P27, P15 J1_P28, R14 J1_P29, P14 J1_P30, R13 J1_P31, P13 J1_P32 | – |
| BL | R3 J1_P33 (JTAG also on this bank: M4/N3/N4/P3) | R4 |

