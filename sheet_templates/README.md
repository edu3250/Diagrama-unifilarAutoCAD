# Sheet templates

The layout template `a3_plantilla_v1` draws the schematic on the owner's A3 sheet: frame, right column (macrolocation, location, address, installer, owner, system capacity) and lower band (calculation summary, abbreviations and notes, circuit boxes, module and inverter data, symbology, title block). The generator reads the neutral template `sheet_templates/a3_plantilla_v1.dxf` (or `$PVSLD_SHEET_TEMPLATE`) and fills every field from the design.

Fields, their anchors and the layer map are in `src/pvsld/sheets/a3_plantilla_v1.py`. Personal data is never written (owner decision of 2026-10-07):

- Location, address, installer, owner names, contacts and licence numbers stay blank lines to fill by hand.
- The title block reads "COMPAÑÍA INSTALADORA".

## Import the owner's template

```powershell
pvsld sheet import C:\ruta\nueva_plantilla.dwg   # DWG via the Core Console, or a DXF
pvsld sheet check                                 # loads sheet_templates/a3_plantilla_v1.dxf
```

`import` checks the source against the definition (a text at every field anchor, known layers, only TEXT, LINE, LWPOLYLINE and CIRCLE) and writes a neutral DXF:

- house layers;
- every field as a `{name}` placeholder;
- no other text of the source;
- no drawing metadata;
- Open Sans replaced by Arial / Arial Narrow Bold, because Open Sans is not installed with AutoCAD, which would fall back to `simplex.shx` and overflow the boxes.

The DXF files here are git-ignored until the owner approves publishing the neutral template.

## Use it in a design

Set `layout.template: a3_plantilla_v1` in the specification (or in the `template_file` of a sizing request).
