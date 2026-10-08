# ADR-0005: CFE-Compliant Symbol Library as Versioned DXF Master File

| Field | Value |
|---|---|
| Status | **Accepted** |
| Decision date | proposed 2026-10-07; owner clarification and acceptance 2026-10-07 |
| Phase / stage | Phase 4, Stage 4.1 (symbol library specification) |
| Deciders | edu3250 (project owner) |
| Supersedes | none; settles the open question of how to transition from code-defined to file-based symbol library (ADR-0003 open question) |
| Vault original | `wiki/decisions/ADR-0005 CFE Symbol Library.md` (not yet created; mirrors to this file once accepted) |

> [!NOTE]
> **Decision in one paragraph.**
> The symbol library is a versioned DXF master file (`symbols/pvsld-symbols-cfe.dxf`, R2018) that is the single source of truth. The generator imports block definitions from this file instead of code-defining symbols. Every block is drawn to match CFE G0100-04 Appendix C first; symbols CFE does not define are sourced from NMX-J-136-ANCE or IEC 60617. Each block records its standard source in a hidden attribute or XDATA metadata. A legend layout documents all symbols and their sources. A deterministic regeneration script (`scripts/regenerate_symbol_library.py`) can rebuild the DXF from a canonical definition, ensuring reproducibility across runs and platforms. The finalized library is exported to DWG 2018 via Core Console and committed alongside the DXF.

## Context

ADR-0003 settled the symbol naming scheme (`PVSLD_<FUNCTION>`, attributes per standard, ports in XDATA) and established that "the library is code" (Phase 2, Stage 2.1): the catalogue was defined in `src/pvsld/symbols/catalogue.py`, and the ezdxf backend materialized it. This approach worked for the spike (9 blocks, 11 inserts, audit 0/0), but as the library grows to the full CFE symbol set (13 from Appendix C + supplementary), two problems emerge:

1. **Code-defined symbols are hard to visualize and review.** The owner wants to see the actual CFE symbol shapes and verify they match the standard before committing. A DXF file opens in AutoCAD and is visually reviewable; Python code is not.
2. **Symbol geometry changes require code edits and test regeneration.** If a symbol's geometry is refined (CFE aesthetics, minor tweaks), the code, the backend, and the golden test must all change in lockstep. A file-based library decouples symbol design from diagram generation code.

ADR-0001's decision on integration approach (ezdxf DXF first, AutoCAD .NET plug-in second) did not foreclose this question. Spike S1 and Stage 2.1 produced a working proof-of-concept with code-defined symbols, which was sufficient for the spike's exit gate. Phase 4 now needs to scale the library while keeping the design clean: a single source of truth that is inspectable, versionable, and deterministic.

## Options considered

| | Option A: Code-Defined Library (Current) | Option B: File-Based Library (Proposed) |
|---|---|---|
| **Single source of truth** | `src/pvsld/symbols/catalogue.py` (Python) | `symbols/pvsld-symbols-cfe.dxf` (DXF master file) |
| **Symbol visualization** | Code comments / test output DXF | Open in AutoCAD, inspect visually |
| **Review workflow** | Code review (PR) + manual test inspection | Visual review in AutoCAD + code review of changes |
| **Geometry changes** | Edit Python, regenerate test | Edit DXF blocks directly, regenerate from canonical def |
| **Generator integration** | Code calls `add_block(…)` to materialize symbols | Generator imports blocks via `import_blocks(…)` |
| **Version control** | Code version; symbol version implicit in commit | Explicit library version (semantic, e.g., `0.4.0`) in XDATA |
| **Reproducibility** | Deterministic if Python random is seeded | Deterministic if regeneration script is idempotent (script → canonical def → DXF) |
| **Extensibility** | Adding symbols requires Python code + tests | Adding symbols requires DXF edit + canonical def update + regeneration |
| **Maintenance burden** | Code knowledge required | DXF knowledge required; Python knowledge for regeneration script |

## Decision

**Option B: File-Based Library.**

The symbol library is a versioned DXF master file that is the single source of truth. The generator imports block definitions from this file. Symbols are drawn from CFE G0100-04 Appendix C first, then NMX-J-136-ANCE and IEC 60617 for gaps. A deterministic regeneration script ensures reproducibility.

> [!NOTE]
> **Owner clarification (2026-10-07):** "Build the symbols however works best for the model; they don't have to be single-line symbols if blocks are better." The decision here uses AutoCAD blocks exclusively (per ADR-0003 naming, attributes including hidden COMP_ID, and port metadata), not loose geometry like the reference DWG example. Every symbol is a named block; the legend sheet is the human-facing reference for CFE compliance.

### 1. Library Format and Structure

- **Master file:** `symbols/pvsld-symbols-cfe.dxf` (DWG Reference Format R2018 / AC1021)
- **Block naming and attributes:** Per ADR-0003:
  - Names: `PVSLD_<FUNCTION>` (uppercase ASCII, digits, underscore)
  - Visible attributes: `TAG`, `DESC` (Spanish description)
  - Hidden attributes: `COMP_ID` (component model id), `IEC_REF`, `NMX_REF`, `SOURCE_STANDARD` (new: identifies the standard document the symbol is based on)
  - Function-specific attributes with units: `RATING_A`, `VOLT_V`, `PMAX_W`, etc. (per component type)
- **Ports:** Defined in block record XDATA per ADR-0003 format (format tag `pvsld.block/1`, library version, port list with position, kind, direction, required flag)
- **Metadata:** XDATA application `pvsld`:
  - Block record: format tag `1000 "pvsld.block/1"`, library version (semantic, e.g., `0.4.0`), port definitions
  - INSERT: format tag `1000 "pvsld.instance/1"`, `COMP_ID`
  - Conductor (LWPOLYLINE): format tag `1000 "pvsld.wire/1"`, connection metadata

### 2. Symbol Sources and Coverage

**CFE G0100-04, Appendix C ("Símbolos utilizados en los diagramas esquemáticos de SFV"):** 13 mandatory symbols

1. Módulo fotovoltaico → `PVSLD_PV_STRING`
2. Varistor → `PVSLD_VARISTOR`
3. Interruptor termomagnético (breaker) → `PVSLD_CB` (with variants for DC/AC, string-side/inverter-side if needed)
4. Inversor (box + diagonal, "=" upper-left, "~" lower-right) → `PVSLD_INV`
5. Medidor de energía (kWh meter, box with ↔) → `PVSLD_METER`
6. Red eléctrica de distribución (utility grid, circle with ~) → `PVSLD_GRID`
7. Gabinete o estructura metálica (enclosure, dash-dot rectangle) → `PVSLD_STRUCTURE`
8. Diodo de paso (bypass diode) → `PVSLD_DIODE_BYPASS`
9. Cargas de iluminación (lighting load, circle with X) → `PVSLD_LOAD_LIGHT`
10. Sensor de corriente (current transformer / CT) → `PVSLD_CT`
11. Interruptor manual (manual switch) → `PVSLD_SW_MANUAL`
12. Transformador de aislamiento (isolation transformer) → `PVSLD_TRAFO_ISO`
13. Carga de contactos (contact load, circle with slash) → `PVSLD_LOAD_CONTACT`

**Supplementary symbols (from CFE diagrams D1/D2, NMX-J-136-ANCE, IEC 60617):**
- Tierra / Puesta a tierra (ground/earth symbol) → `PVSLD_GND` (IEC 60617-2-01-01 or NMX equivalent)
- Protector contra sobretensiones (SPD, surge protector) → `PVSLD_SPD` (IEC 60617-2 or CFE varistor variant; deferred if CFE varistor suffices)
- Desconectador de corriente continua (DC disconnect) → `PVSLD_DC_DISCONNECT` (IEC 60617-2)
- Fusible (fuse) → `PVSLD_FUSE` (IEC 60617-2)
- Detector de falla a tierra (ground fault detector / AFDD) → `PVSLD_GFD` (CFE diagram notation or IEC equivalent)
- Batería (battery, hybrid systems) → `PVSLD_BATTERY` (IEC 60617-2 or NMX, Phase 5)
- Transformador (power transformer) → `PVSLD_TRAFO` (IEC 60617-2, distinct from PVSLD_TRAFO_ISO if needed, Phase 5)

**Existing from Phase 2 (redrawn to match CFE aesthetics if needed):**
- `PVSLD_TTLB` (title block with Mexican fields: PROYECTO, UBICACION, RPU, NUM_SERVICIO, RESPONSABLE, CEDULA, FECHA, PLANO_NO, ESCALA, etc.)
- `PVSLD_GND` (if already defined; ground symbol consolidated)
- Conductor marks (`//` for multi-conductor, `+` / `−` for polarity): documented as block symbols or text/line style conventions

### 3. Legend Sheet

- **Layout:** Named `Legend` in paper space
- **Content:** Structured table or list with columns:
  - **Símbolo:** Block thumbnail (INSERT of each block at a nominal size) or symbol identifier
  - **Designación:** DESC attribute value (Spanish description)
  - **Fuente:** SOURCE_STANDARD attribute or XDATA metadata (e.g., "CFE G0100-04 Appendix C", "IEC 60617-2-03-15", "NMX-J-136-ANCE")
- **Header:** Title block or text banner: "pvsld Symbol Library v0.4.0 – CFE G0100-04 Appendix C & IEC 60617"
- **Format:** Suitable for A3 or A4 printout; consistent with the title block design (PVSLD_TTLB layout)

### 4. Regeneration and Determinism

A Python script (`scripts/regenerate_symbol_library.py`) rebuilds the master DXF from a canonical definition:

- **Canonical source:** `symbols/cfe_symbols_0.4.0.yaml` (or inline Python dataclass in the script)
  - Defines each block: name, description, layer, geometry (lines, arcs, circles as primitives), ports, attributes, source standard
  - Human-readable and version-controlled
- **Regeneration:** Script reads the canonical def, creates an ezdxf document, adds blocks, formats legend layout, and exports DXF
- **Idempotency:** Regenerating the library twice from the same canonical definition produces identical file hashes (fixed metadata: author, timestamps, etc.)
- **Reproducibility:** CI runs regeneration on Windows and Linux; hashes match (no platform differences in DXF output)
- **Validation:** Script includes audit hook (call `doc.audit()`, report 0/0 as success criterion)

### 5. Generator Integration (Phase 4, Stage 4.3)

- **Block import:** `src/pvsld/backends/dxf.py` loads the master DXF once per process (`pvsld.symbols.cfe.loader.library_document()`: `$PVSLD_SYMBOL_LIBRARY`, else the repository file, else the same blocks rendered from the definitions; a file of another library version is refused) and copies only the blocks a diagram uses with `pvsld.symbols.cfe.loader.import_blocks`. ezdxf's `Importer` does not copy block-record XDATA, where the ports live, so `import_blocks` copies it after the import.
- **Combiner box:** its shape depends on the number of strings, so the library file holds only the two-string legend form `PVSLD_COMBINER`; the generator defines `PVSLD_COMBINER_<n>S` (1 to 24 strings) with `loader.ensure_combiner` (amended in Stage 4.3).
- **Symbol insertion:** Generator inserts blocks by name (e.g., `diagram_dwg.modelspace().add_blockref('PVSLD_INV', insert=(x, y))`)
- **Attribute assignment:** Function-specific attributes are set on the INSERT via `attribs` dict
- **No code-defined geometry:** Old symbol catalogue code is removed; geometry comes exclusively from the imported DXF

### 6. DWG Finalization (Phase 4, Stage 4.4)

- **Core Console finisher:** On the owner's licensed workstation, `pvsld finish` converts the master DXF to DWG 2018 (TrustedDWG, AC1032 format)
  - Output: `symbols/pvsld-symbols-cfe.dwg`
  - Metadata privacy: "last saved by" field cleared
  - Audit result: 0 errors, 0 fixes (headless check if available; owner manual verification otherwise)
- **Committed files:**
  - `symbols/pvsld-symbols-cfe.dxf` (source, R2018)
  - `symbols/pvsld-symbols-cfe.dwg` (finalized, TrustedDWG 2018)
- **CI validation:** Script checks DWG existence and format; warns if DXF changes without DWG update

### 7. Version Bumping and Golden Test Regeneration

- **Library version:** Semantic version stored in XDATA `pvsld.block/1` record (e.g., `0.4.0` for Phase 4 Stage 2)
- **When to bump:**
  - **Patch (e.g., 0.4.0 → 0.4.1):** Symbol geometry tweaks, attribute value changes, SOURCE_STANDARD corrections (non-breaking)
  - **Minor (e.g., 0.4.0 → 0.5.0):** New blocks added, existing block attributes changed, port additions (diagram generation may be affected)
  - **Major (e.g., 0.4.0 → 1.0.0):** Breaking changes to block names, attribute tags, port structure
- **Golden test regeneration:** When the library version bumps:
  - CI regenerates the golden DXF test file (`tests/fixtures/spike_s1_golden.dxf`)
  - The new golden is uploaded as a CI artifact for owner visual review
  - Owner approves the changes and commits the new golden with a noted approval (commit message: "Update golden test DXF; approved by owner, 2026-10-07")
  - Block-level attribute changes (e.g., new CERT attribute removal) are validated in the golden

### 8. Documentation and Attribution

- **Appendix C source images:** High-res crops of the 13 CFE Appendix C symbols placed in `datasheets/cache/cfe_appendix_c/` (git-ignored, copyrighted; internal reference only)
- **Drawing comments:** Each block definition (in the DXF or the canonical YAML) includes a comment line referencing the source:
  - Example: `# PVSLD_INV: CFE G0100-04 Appendix C, Symbol 4; IEC 60617-2 dynamic inductor shape adapted`
- **README update:** `symbols/README.md` documents:
  - Library version, release date, and CFE Appendix C compliance
  - How to regenerate the library
  - Legend sheet content and how to print it
  - How the generator imports blocks

## Rationale

1. **Single source of truth, visually reviewable.** A DXF file opens in AutoCAD; CFE compliance is verifiable by the owner without code review skills. Geometry errors are caught early.
2. **Decoupling design from generation code.** Symbol refinements do not require Python edits; the regeneration script handles the mechanical transformation from canonical def to DXF.
3. **Version control and auditability.** The canonical definition (YAML or Python dataclass) is compact and git-friendly; block geometry is deterministic and reproducible. The legend provides a permanent record of symbol sources.
4. **Extensibility.** Adding a new symbol is a DXF edit + canonical def line, not a code function. Reduces onboarding friction for contributors who are CAD-savvy but not Python-fluent.
5. **Determinism and CI integration.** The regeneration script ensures the library is reproducible across platforms and time. CI can validate the library passes AUDIT and that regeneration produces no surprises.
6. **Regulatory compliance pathway.** A file-based library with explicit CFE sourcing is defensible in regulatory contexts (UVIE inspections, CFE compliance) as a vetted, documented artifact rather than code-generated.

## Consequences

**Positive**
- Symbol design is decoupled from generation code; visual review happens in AutoCAD before commit.
- The legend sheet provides a permanent reference for regulators and users.
- Regeneration script ensures the library is reproducible and testable in CI.
- Version bumping and golden test regeneration workflows are clear.

**Negative / risks**
- Requires one owner-run step (Core Console DWG finalization) outside CI; the DXF is the CI-testable artifact, and the DWG is a courtesy artifact (not CI-generated).
- The canonical definition (YAML) must stay in sync with the DXF; a CI lint step can help (e.g., regenerate and check for file hash changes), but human discipline is needed.
- If the regeneration script has bugs (e.g., incorrect layer assignment, malformed XDATA), the DXF becomes corrupt; the script must be well-tested before Phase 4 Stage 4.2.
- Existing diagram golden tests will be regenerated; owner must review and approve the new golden (Stage 4.3).

## Open questions

1. **Conductor count marks (`//`) and polarity (`+`, `−`):** Are these block symbols, text styles, or just drawing conventions? Recommend deferring to Phase 5 layout template work.
2. **Symbol geometry detail level:** CFE Appendix C figures are schematic (simple lines); should the DXF blocks match exactly or include annotation (e.g., component ID labels inside the symbol)? Recommend exact match to CFE; annotation lives in the diagram title block and component labeling.
3. **ANSI/NEC variants:** ADR-0003 open question. Recommend a separate block set `PVSLD_ANSI_<FUNCTION>` if Phase 5 requires US export; for now, focus on CFE compliance.
4. **Legend sheet layout:** Is a simple list sufficient, or is a visual grid (symbols as images) needed? Recommend simplicity in Phase 4; Phase 5 can enhance based on owner feedback.

## References

- CFE G0100-04 ("Interconexión a la red eléctrica de baja tensión de sistemas fotovoltaicos con capacidad hasta 30 kW", rev 080822), Appendix C (Informativo): 13 schematic symbols
- CFE G0100-04, Appendix D (Figures D1/D2): sample single-line diagrams with symbol usage
- NMX-J-136-ANCE: Mexican electrical symbol standard (to be purchased; referenced for gaps in CFE)
- IEC 60617-2: International Electrotechnical Commission, Industrial processes, measurement and control; graphical symbols, part 2 (symbols for control equipment and protective devices)
- ADR-0001 (Integration Approach), ADR-0003 (Symbol Library Format and Naming)
- Spike S1 and Phase 2 Stage 2.1: code-defined symbol library, ezdxf backend, golden DXF test
- Vault notes (not in repo): PV Electrical Symbology, Block-Based Symbol Libraries, SLD Drafting Conventions, CAD Output Testing Strategies

---

**Last updated:** 2026-10-07 (kickoff)

**Next step:** Owner decision on ADR-0005 acceptance; triggers Phase 4 Stage 4.2 (build CFE symbol set).
