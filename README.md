# Ti60F225 control card

An FPGA control card for the tube_power_5_1 power board, built around an Efinix Titanium Ti60F225C4, designed in
KiCad 10. It is a conversion of the Agilex 3 control card (`~/dev/ti60f225_control_card`, GitHub
`agilex3_control_card`): same outline, 2×25 1.27 mm power-board header and JTAG header positions.

**Status: phase 0 of the conversion (2026-10-30).** `hardware/` is still the unchanged Agilex 3 design copied from
the source at commit `43b9ec7`. The plan, the decisions and the remaining steps are in
[`CONVERSION_PLAN.md`](CONVERSION_PLAN.md).

## Repository layout

| Path | Contents |
|---|---|
| `hardware/` | KiCad project (`control_card.kicad_pro`), sheets, project libraries, JLCPCB design rules |
| `reference/ti60f225_pinout.csv` | All 225 Ti60F225 balls: pad, bank, HVIO/HSIO type, configuration function, LVDS pair, clock region |
| `reference/` | Power-board header pinout, ADC mux channel table, JLC part cache, the Agilex pin list (for net names) |
| `docs/` | JLCPCB production checklist |
| `tools/jlc/` | Submodule [jlc-tools](https://github.com/johonkanen/jlc-tools): JLC part search, stock check, BOM/CPL and Gerber export |

Clone with `git clone --recursive`, or run `git submodule update --init` after cloning.

## License

[MIT](LICENSE).
