# CFE symbol library

`pvsld-symbols-cfe.dxf` (DXF R2018, UTF-8, LF) is the master file of the drawing symbols
([ADR-0005](../docs/decisions/ADR-0005-cfe-symbol-library.md)). Every symbol is a named block
`PVSLD_<FUNCTION>` with attributes and ports, plus a paper-space layout `Legend` (A3) with the table
*Símbolo | Designación | Fuente*.

* Library version: **0.4.0** (stored in every block record and printed on the Legend).
* Shapes: the 13 symbols of CFE G0100-04 Appendix C, redrawn as vector geometry from the
  specification; earth, conductor-count ticks, polarity and junction dot as used in Appendix D
  (figures D1 and D2); and the symbols the generator needs that CFE does not define (PV string
  built from the module, point of interconnection, load center, title block). No image or text of
  the specification is embedded. `pvsld symbols list` shows each block with its source.
* Source of truth: `src/pvsld/symbols/cfe/definitions.py`. Do not edit the DXF by hand; the
  committed bytes must equal what the definitions render (a test and `pvsld symbols build --check`
  enforce it).

## Regenerate and validate

```powershell
pvsld symbols build --png out/pvsld-symbols-legend.png   # or: python scripts/build_symbol_library.py
pvsld symbols validate                                   # audit 0/0, attributes, ports, sources, Legend
pvsld symbols build --check                              # exit 1 when symbols/pvsld-symbols-cfe.dxf is stale
```

Bump `LIBRARY_VERSION` in `src/pvsld/symbols/cfe/model.py` with the rules of ADR-0005, section 7.

## Review in AutoCAD

1. Open `pvsld-symbols-cfe.dxf`. It opens on the `Legend` layout; compare each row with Appendix C
   (page 40 of 43 of CFE G0100-04) and figures D1 and D2.
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
* Ports are block-record XDATA (application `PVSLD`, `pvsld.block/1`); the library version follows
  the port count, six tags per port, and the source of the symbol is the last tag.
* Importing blocks into another drawing: ezdxf's `Importer` does not copy block-record XDATA, so use
  `pvsld.symbols.cfe.loader.import_blocks`, which does.
