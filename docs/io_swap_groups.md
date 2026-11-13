# Interchangeable I/O (for routing)

While routing, swap pins inside a group whenever that removes a crossing or a via. Apply FPGA swaps with
`tools/swap_balls.py NET=BALL ...`, then `efinity/pinplan/run.sh --compile` and `tools/check_schematic.py`.
State as of 2026-11-13 (`reference/pin_assignment.csv`).

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

### 1. Translator inputs: HSIO banks 2A + 2B (1.8 V), 17 nets, 13 free balls

Any net to any ball of either bank (XLAT_OE_N included).

| Bank | Used | Free |
|---|---|---|
| 2A | A5 PRI_DHB_HI, A6 EPWM6A, A7 EPWM5A, A8 HT_CS, B6 PRI_DHB_LO, B7 CUK_CS, B8 EPWM2A, C6 XLAT_OE_N | D5 D7 E6 E7 F7 F8 |
| 2B | A9 SYNCH_2, A10 CUK_CLK, A11 HT_CLK, B9 EPWM2B, B10 SYNCH_1, C8 GPIO_BYPASS_RLY, C9 PFC_PWM1, C10 EPWM1A, D10 PFC_PWM2 | B11 D8 E8 E9 E10 F9 F10 |

(Net names without the `_1V8` suffix.) If 2A/2B ever run out, banks 3A/3B (VCCIO on +1V8, 40 free balls) could
take nets too, but they have no decoupling now: their VCCIO balls F14/G12 (3A) and J11/L14 (3B) would need a 47n each.

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
a channel swap edits the connector sheet's translator pins (not scripted yet).

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
| 4A | K7 ADCA_SCLK, K8 ADASEL2, K9 ADASEL1, L8 ADCA_CS_N, L9 ADCA_SDO, M9 ADASEL0 | M10 N10 P9 P10 P11 P12 R9 R10 R11 R12 |
| 4B | P5 ADCB_CS_N, P6 ADCB_SDO, P7 ADBSEL1, R5 ADCB_SCLK, R6 ADBSEL0, R7 ADBSEL2 | K6 L7 M6 M7 M8 N6 N8 P8 R8 (L6 is SSU_N) |

### 5. Direct 3.3 V nets: HVIO banks TL, TR, BR, BL, 22 nets, 1 free ball (R4)

Within a bank: any net to any ball. Across banks: trade nets so each bank keeps ≤ 6 outputs (Efinix 3.3 V limit;
TL, TR and BR are at 6 now, BL at 1), e.g. output for output, or an input for an input.

| Bank | Used (in = input) | Free |
|---|---|---|
| TL | A3 LED1_R, A4 LED2_G, B3 LED1_G, B5 LED2_B, C3 LED1_B, C4 LED2_R, C5 HT_SDATA (in) | – |
| TR | A12 TX, A13 CUK_SDATA (in), A14 J1_P24, B12 J1_P17, B14 J1_P22, C12 J1_P19, D12 J1_P26 | – |
| BR | N13 J1_P28, N14 RX (in), P13 J1_P30, P14 J1_P27, P15 J1_P29, R13 J1_P32, R14 J1_P31 | – |
| BL | R3 J1_P33 (JTAG also on this bank: M4/N3/N4/P3) | R4 |

