# Symbol library

`pvsld-symbols.dxf` (DXF R2018, UTF-8, LF) is the master file of the drawing symbols
([ADR-0005](../docs/decisions/ADR-0005-cfe-symbol-library.md)). Every symbol is a named block
`PVSLD_<FUNCTION>` with attributes and ports, plus three paper-space layouts `Legend`, `Legend2` and
`Legend3` (A3) with the table *Símbolo | Designación | Fuente*, grouped by family (generation and
storage, conversion, protection, switching, measurement, grid and loads, earthing, medium voltage,
conductors and annotation).

* Library version: **0.6.0**, 57 blocks (stored in every block record and printed on the Legend).
* Owner decisions of the v0.5.0 review (2026-10-08): the generator draws the thermomagnetic breaker
  in the CFE form `PVSLD_CB` (`PVSLD_CB_IEC` stays as a documented alternative); the fuse has a DC
  (`PVSLD_FUSE`) and an AC (`PVSLD_FUSE_AC`) variant; the combiner box follows the number of
  strings. `PVSLD_COMBINER` in the library is its two-string legend form; the generator calls
  `pvsld.symbols.cfe.loader.ensure_combiner(doc, n)`, which defines `PVSLD_COMBINER_<n>S` (1 to 24
  strings, ports `IN1`..`INn`, `OUT`, `PE`) from `definitions.combiner_box(n)`.
* The DC protection box (owner's reference, library 0.8.0): `PVSLD_FUSE_DISC_DC` (gPV fuse holder)
  or `PVSLD_CB_DC` per string, `PVSLD_SPD_DC_BOX` fed by both strings, and one ganged
  `PVSLD_DC_DISCONNECT_<n>S` (the library holds the two-string form `PVSLD_DC_DISCONNECT_2S`; the
  generator defines 1 to 12 strings with `loader.ensure_symbol`, ports `IN<i>`/`OUT<i>`, 20 mm
  apart). `PVSLD_PV_CONNECTOR` marks the field connector where a string enters the box, and
  `PVSLD_TERMINAL` (BYBLOCK colour) the box terminals.
* Shapes, by source priority **CFE G0100-04 > NMX-J-136-ANCE-2019 > IEC 60617**: the 13 symbols of
  CFE Appendix C and the usage of Appendix D (earth, ticks, polarity, junction, combiner, ground-fault
  detector, monitoring subsystem); the NMX figures (fuse, fuse-switch, safety switch, battery,
  contactor, MV transformer, cutout, arrester, disconnect, CT/VT, earth bus, terminal, crossing,
  export meter `M`); IEC through the Peruvian DGE norm (transfer switch, protective relay) and the
  UNE-EN 60617 sheet of the owner (IEC thermomagnetic breaker, residual-current device); and
  compositions where no official symbol exists (hybrid inverter, optimizer, microinverter, charge
  controller, AFCI, CFE/user boundary, combiner), recorded as `pvsld (composición)`. Each block's
  source names the clause, figure or code. All geometry is redrawn as vectors; no image or text of
  any standard is embedded. `pvsld symbols list` shows each block with its source.
* Source of truth: `src/pvsld/symbols/cfe/definitions.py`. Do not edit the DXF by hand; the
  committed bytes must equal what the definitions render (a test and `pvsld symbols build --check`
  enforce it).

## DWG

`pvsld-symbols.dwg` is the same library saved by AutoCAD as DWG 2018 (TrustedDWG, AUDIT 0/0), for opening and inserting the blocks directly in AutoCAD. `pvsld-symbols.dwg.json` records the SHA-256 of the DXF and the library version it was exported from; a test fails when the DXF changes and the DWG is not exported again. The DXF remains the source of truth.

```powershell
pvsld symbols dwg            # export with the Core Console (licensed AutoCAD)
pvsld symbols dwg --check    # verify the committed DWG (no AutoCAD needed)
```

## Regenerate and validate

```powershell
pvsld symbols build --png out/pvsld-symbols-legend.png   # writes legend-1.png, -2, -3
pvsld symbols validate                                   # audit 0/0, attributes, ports, sources, Legend
pvsld symbols build --check                              # exit 1 when symbols/pvsld-symbols.dxf is stale
```

Bump `LIBRARY_VERSION` in `src/pvsld/symbols/cfe/model.py` with the rules of ADR-0005, section 7.

## Review in AutoCAD

1. Open `pvsld-symbols.dxf`. It opens on the `Legend` layout (tabs `Legend2`, `Legend3` follow);
   compare each row with its source named in the *Fuente* column.
2. Run `AUDIT` (expect 0 errors) and `-INSERT` a few blocks into a new drawing: `TAG` and `DESC`
   prompt, the other attributes are hidden; `ATTDISP` set to `On` shows them.
3. Look at the layers: every entity uses the house layer standard, none lies on layer `0` except the
   overall viewport of the layout.

## Conventions

* Millimetres, 1:1. The base point is the upstream connection or the left-middle of the symbol;
  vertical devices hang below it. Ports sit on the 2.5 mm grid and touch the drawing.
* Attributes: visible `TAG`, `DESC`; hidden `COMP_ID`, `IEC_REF`, `NMX_REF`, `SOURCE_STANDARD`;
  function-specific tags carry their unit (`RATING_A`, `VOLT_V`). Annotation blocks (conductor
  tick, polarity, junction dot) hide `TAG` and `DESC` too.
* Port kinds are `DC`, `AC`, `PE`, plus `SIG` (signal or control link) and `ANY` (terminal, crossing).
  In-line devices run left to right (IN at the origin); shunt devices (varistor, arrester, earth) hang
  below it.
* Ports are block-record XDATA (application `PVSLD`, `pvsld.block/1`); the library version follows
  the port count, six tags per port, and the source of the symbol is the last tag.
* Importing blocks into another drawing: ezdxf's `Importer` does not copy block-record XDATA, so use
  `pvsld.symbols.cfe.loader.import_blocks`, which does.
