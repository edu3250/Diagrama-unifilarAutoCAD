# ADR-0003: Symbol Library Format and Naming

| Field | Value |
|---|---|
| Status | **Accepted** |
| Decision date | proposed 2026-10-05, accepted 2026-10-06 |
| Phase / stage | Phase 2, Stage 2.1 (spike S1) |
| Deciders | edu3250 (project owner) |
| Supersedes | none; settles the open question "symbol naming (`PVSLD_` vs `MXPV_`)" of ADR-0001 |
| Vault original | `wiki/decisions/ADR-0003 Symbol Library Format.md` |

> [!NOTE]
> This file mirrors the ADR kept in the author's local Obsidian research vault, which is not part of this repository. A citation such as "(Source: Block-Based Symbol Libraries)" names a vault note. The measurements quoted here come from the S1 implementation in this repository (`src/pvsld/symbols/`, `src/pvsld/backends/`, `tests/`); the vault note "Spike S1 Results 2026-10" holds the commands and the environment.

> [!NOTE]
> **Decision in one paragraph.**
> Name blocks `PVSLD_<FUNCTION>` and use the XDATA application id `PVSLD`. Every component is an `INSERT` of such a block with visible `TAG` and `DESC` attributes and the hidden `COMP_ID` (the parameter-model id), `IEC_REF` and `NMX_REF`, plus function-specific attributes whose tags carry their unit (`RATING_A`, `VOLT_V`). Ports live as data in the block record XDATA, component identity in the `INSERT` XDATA, conductor connectivity in the XDATA of the conductor polyline. The symbol catalogue is defined in code and the DXF backend materializes it.

## Context

ADR-0001 (decision 6) fixed three things whichever naming scheme won: ports in block-record XDATA, component identity as a hidden `COMP_ID` attribute plus per-`INSERT` XDATA, and Spanish text in attribute values, never in tags. It left the block-name prefix and the XDATA application id to spike S1, because two vault notes disagree (Source: PV Electrical Symbology, Block-Based Symbol Libraries).

S1 built a working library and a read-back verifier on it (Stage 2.1), so the choice rests on code that runs rather than on prose.

## Options considered

| | Scheme A (PV Electrical Symbology) | Scheme B (Block-Based Symbol Libraries) |
|---|---|---|
| Block names | `PVSLD_<FUNCTION>`, for example `PVSLD_CB`, `PVSLD_INV` | `MXPV_<SYMBOL>`, for example `MXPV_BREAKER_2P` |
| Common attributes | `TAG`, `DESC`, `COMP_ID` (hidden), `IEC_REF`, `NMX_REF`, `MFR`, `MODEL` | `TAG`, `RATING`, `MFG`, `MODEL`, `QTY`, `DESC1` (AutoCAD Electrical names) |
| Function attributes | one typed tag per datum, unit in the tag (`RATING_A`, `VOLT_V`, `KAIC_KA`) | generic `RATING` |
| XDATA application | `PVSLD` (as in the R6 probe) | `MXPVSLD` |

## Decision

**Scheme A, with the adjustments below.**

1. **Block names.** `PVSLD_<FUNCTION>`: uppercase ASCII letters, digits and underscore. The library version is not part of the name; it is stored in the block record XDATA (`LIBRARY_VERSION`, semantic version, bumped when a port or an attribute tag changes).
2. **XDATA application id `PVSLD`.** One application id for three record formats, each starting with a format tag so a reader can reject what it does not understand:
   - Block record: `1000 "pvsld.block/1"`, `1000 <library version>`, `1070 <port count>`, then per port `1000 id`, `1000 kind` (`DC`, `AC`, `PE`), `1000 direction` (`left`, `right`, `up`, `down`), `1040 x`, `1040 y`, `1070 required`. Coordinates are block-local millimetres stored as reals (group 1040), so a CAD transform of an instance cannot alter them.
   - `INSERT`: `1000 "pvsld.instance/1"`, `1000 <COMP_ID>`.
   - Conductor `LWPOLYLINE`: `1000 "pvsld.wire/1"`, connection id, circuit id (empty for conductors the model does not name), kind, start port, end port. A port is written `COMP_ID.PORT`, for example `S1.OUT`.
3. **Attributes.**
   - Every component has visible `TAG` (reference designation) and `DESC` (Spanish description), and hidden `COMP_ID`, `IEC_REF`, `NMX_REF`.
   - Equipment (PV string, inverter) adds `MFR` and `MODEL`.
   - Function-specific tags follow the vault catalogue and carry the unit: `PMAX_W`, `VOC_MAX_V`, `RATING_A`, `KAIC_KA`, and so on.
   - Hidden attributes use the ATTDEF/ATTRIB invisible flag. Values are strings formatted for NOM-008 (decimal point, space before the unit). Spanish text appears only in values.
   - `IEC_REF` and `NMX_REF` are ordinary hidden attributes, not constant attributes (the one deviation from Scheme A, see Rationale 5).
4. **Ports.** Defined in the catalogue with id, block-local position on a 2.5 mm grid, direction, kind and `required`. An optional port (the second MPPT input) may stay unconnected; a required port that no conductor reaches is a *dangling port* and a verification failure. The block base point is the upstream connection or the left-middle of the symbol, and power flows left to right.
5. **Layers.** Every entity in a block definition names a layer of the house standard explicitly (Source: SLD Drafting Conventions), so no drawing content, blocks included, lies on layer `0`. The one exception is the overall paper-space viewport (id 1), which AutoCAD requires on layer `0` (AUDIT: `Paperspace vport layer Not "0"`, spike S4). The cost is that a block no longer takes the layer of its `INSERT`.
6. **Standard.** IEC 60617 shapes, with the IEC 60617 identifiers the vault catalogue lists; the point-of-interconnection marker and the utility network have none and carry `-`. `NMX_REF` holds a placeholder until the purchased NMX-J-136-ANCE text confirms the figure numbers.
7. **The library is code.** `src/pvsld/symbols/catalogue.py` is the single source; the backend turns it into blocks and `render_symbol_library()` emits a master DXF with every block. A drawing defines only the blocks it uses.
8. **The title block is a symbol.** `PVSLD_TTLB` is inserted in paper space with the Mexican fields as attributes (`PROYECTO`, `UBICACION`, `RPU`, `NUM_SERVICIO`, `RESPONSABLE`, `CEDULA`, `FECHA`, `PLANO_NO`, `ESCALA`, and others), so the same read-back verifies it.
9. **Ids the model does not name** get a fixed `COMP_ID`: `GRID-1` (utility network), `PT-1` (grounding electrode), `TTLB-1` (title block).

## Rationale

1. **One namespace.** The package, the repository, the MCP resources (`pvsld://schema/...`, `pvsld://symbols`) and now the blocks and the XDATA application share the name `pvsld`.
2. **Typed attributes make the round trip exact.** Rule DRW-008 compares attribute values with the model by `COMP_ID`. `RATING_A`, `VOLT_V` and `KAIC_KA` are unambiguous for a breaker; one generic `RATING` is not, and an SPD or a meter needs several numbers.
3. **Jurisdiction-neutral blocks.** The shapes are IEC, usable anywhere. What is Mexican (rule pack, legends, units, title block fields) lives in the rule pack and in the Spanish values, so a `MX` in every block name adds nothing.
4. **Evidence already in hand.** The R6 probe used the application id `PVSLD`; S1 kept it.
5. **Hidden regular attributes instead of constant ones.** A constant attribute exists only in the block definition, so an `INSERT` read-back (`ATTRIB` extraction) cannot see it, and ezdxf's `add_auto_attribs` would copy it as an ordinary attribute anyway. Regular hidden attributes round-trip like all others and make the identity of the symbol standard visible in the data.
6. **Cost accepted.** The attribute names of AutoCAD Electrical (`MFG`, `RATING`, `QTY`, `DESC1`) are not mirrored. The vault's own note keeps Electrical interoperability optional, and ADR-0001 lists AutoCAD Electrical integration under reversal trigger T9. An alias layer (`MFG` for `MFR`, `X?TERMnn` port attributes) can be added without renaming anything.

## Consequences

**Positive**
- Both backends insert identical block definitions generated from one catalogue.
- Identity, ports and connectivity are plain data. A test, or any other CAD tool, can rebuild the graph from the file alone. S1 verifies: 11 components, 147 of 147 attribute values equal to the model, 0 dangling ports among 18 required ports, every conductor end within 0.01 mm of its port, 0 entities on layer `0`, `AUDIT` 0 errors and 0 fixes (ezdxf).
- A format tag on each XDATA record gives a migration path (`.../2`).

**Negative / risks**
- AutoCAD itself has not yet opened the file. The manual `AUDIT` is pending in spike S4; until then, acceptance by AutoCAD of the XDATA, the invisible attributes and the paper-space layout is unverified.
- ANSI/NEC symbol variants (`layout.symbol_style: ANSI`) are not designed. The proposal is a separate block set, for example `PVSLD_ANSI_<FUNCTION>`, with identical attribute tags and ports.
- Explicit layers inside blocks mean a user who recolours by layer must edit the layer table, not the `INSERT`.
- Rotated or scaled `INSERT`s are not supported by the S1 read-back (ports are transformed by translation only); the layout template never rotates.
- XDATA holds 16 kB per entity; a block record with ports uses well under 1 kB.

## Open questions

- `NMX_REF` values, which need the purchased NMX-J-136-ANCE text.
- Whether `LIBRARY_VERSION` should also be written to each `INSERT`, to detect drawings made with an older library.
- Dynamic blocks for IEC/ANSI variants (ADR-0001 trigger T9).
- Symbol legend pictograms: the S1 legend lists block names, descriptions and IEC references as text only.

## References

Vault notes: Block-Based Symbol Libraries, PV Electrical Symbology, SLD Drafting Conventions, CAD Output Testing Strategies, ezdxf, R6 ezdxf Probe Experiment 2026-10-04, Spike S1 Results 2026-10, ADR-0001 Integration Approach.

---

**Last updated:** 2026-10-06
