# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Removed
- `pvsld.symbols.catalogue` (the Phase 2 code-defined symbols) and `pvsld.backends.dxf.render_symbol_library`; the library DXF of ADR-0005 replaces both

### Added
- Phase 4, Stage 4.4: the symbol library as DWG 2018, `symbols/pvsld-symbols.dwg` (TrustedDWG, AUDIT 0/0), exported from the library DXF with `pvsld symbols dwg` (Core Console). `pvsld symbols dwg --check` and a test compare it with the DXF through `symbols/pvsld-symbols.dwg.json` (DXF SHA-256 and library version)
- Layout template `a3_plantilla_v1` (owner request): the schematic on the owner's A3 sheet template. `pvsld sheet import TEMPLATE.dwg|dxf` (DWG through the Core Console) checks the template against its definition (`pvsld.sheets.a3_plantilla_v1`: 76 field anchors, cleared symbology box, layer map) and writes a neutral DXF (fields as placeholders, house layers, no metadata, Open Sans mapped to Arial); `pvsld.core.layout_sheet` places the schematic in the free area, numbers the circuits with the template markers and fills the heading, capacity, service, calculation summary, notes, circuit boxes (with the DC disconnect and SPDs), module and inverter data, the symbology of the blocks drawn (scaled samples) and the drawing number and date. Personal data stays blank and the title block reads "COMPAÑÍA INSTALADORA". `layout_diagram` in the service picks the builder from `layout.template`
- The neutral sheet template `sheet_templates/a3_plantilla_v1.dxf` is published (owner approval) and `pvsld size` draws on it by default (`layout_template`, default `a3_plantilla_v1`)
- Sheet template, owner review: the protection schedule in the style of the template boxes (lower right of the schematic area), and every PV module drawn: `pv_string(n, extend)` builds `PVSLD_PV_STRING_<n>M_UP|DN` (CFE modules 5 x 10 mm, six to a row, rows joined in series, output on the right edge), defined on demand by `loader.ensure_symbol`; each string runs straight into its MPPT input. Template v1 keeps the two-module convention
- Diagram model: `TextItem.style` and centred alignment, `CircleItem`, `SymbolSample` (scaled block insert without identity) and sheet text styles; the DXF backend renders them
- Phase 3, Stage 3.3: rule STR-007 (`pvsld.core.rules`): array STC power per inverter against the inverter PV power limit (`pdc_max_w`, error) and a DC/AC ratio policy (`pvsld.core.policy`: warning above 1.35, error above 1.50, information below 1.0; project policy, owner decision pending). `validate_pv_design(..., dc_ac_policy=...)` and `pvsld validate --dc-ac-warn/--dc-ac-error` configure it. The Phase 2 owner test (2 x 11 x 550 W = 12.1 kWp on a 9 kW inverter) is now rejected
- Phase 3, Stage 3.4 (v1): `pvsld.sizing`, the deterministic sizing engine. It enumerates string configurations per catalogue inverter, rejects each one that breaks VOLT-001/002/003, STR-001/002/004/007 (rule and numbers in Spanish), warns on STR-003/STR-005 (clipping estimate), ranks by deliverable power against the target, sizes the string breaker (catalogue, only where NOM 690-9(a) needs it or on request), the inverter-output breaker and the copper conductors with voltage drop, builds a full parameter specification and runs the rule pack on it before returning it. Bifacial modules use the BNPI short-circuit current. `pvsld size REQUEST.yaml [--catalogue DIR] [--include-unreviewed] [-o SPEC] [--json]` and `examples/sizing_jinko_growatt.yaml`
- Tests: fixture catalogue `tests/fixtures/sizing/` (copies of the owner's datasheet records and the sample 550 W / 6 kW pair) and scenario tests for the Jinko 650 W, ET Solar 550 W, Huawei SUN2000 L1, Growatt MIN TL-X2, Schneider and Suntree components
- Phase 4, Stage 4.2 (ADR-0005): the CFE G0100-04 symbol set as a block library. `src/pvsld/symbols/cfe/` defines 57 blocks (v0.6.0): the 13 Appendix C symbols and the Appendix D usage redrawn as vector geometry, 34 more from the symbol map (NMX-J-136-ANCE-2019 figures, DGE/UNE-EN 60617 forms, compositions where no official symbol exists, the IEC thermomagnetic breaker `PVSLD_CB_IEC`, the residual-current device `PVSLD_RCD`, the DC disconnect `PVSLD_DC_DISCONNECT` with a `LOAD_BREAK` attribute), with ports (kinds DC, AC, PE, SIG, ANY), attributes (inverter `CERT` dropped, hidden `SOURCE_STANDARD` added) and a source with clause or code per block; `symbols/pvsld-symbols-cfe.dxf` (R2018, byte-reproducible) holds them with three `Legend` layouts grouped by family (Símbolo | Designación | Fuente). `pvsld symbols build|list|validate` and `scripts/build_symbol_library.py`; `pvsld.symbols.cfe.loader.import_blocks` copies blocks with their port XDATA (ezdxf's `Importer` does not)
- Symbol library 0.6.0 (owner review of 0.5.0): AC fuse `PVSLD_FUSE_AC` (the DC fuse is now described as `Fusible (CD)`); the combiner box is parametric in the number of strings (`combiner_box(n)`, 1 to 24, block `PVSLD_COMBINER_<n>S` defined on demand by `loader.ensure_combiner`); the generator will use the CFE breaker `PVSLD_CB`

### Changed
- Phase 4, Stage 4.3: the generator draws with the CFE symbol library. The DXF backend imports the blocks a diagram uses from `symbols/pvsld-symbols-cfe.dxf` (`loader.library_document`, with port XDATA) and defines `PVSLD_COMBINER_<n>S` for the exact string count; `pvsld.symbols` is the interface over the CFE definitions and the `pvsld://symbols` resource lists all 57 blocks. Instances carry `SOURCE_STANDARD`, the inverter has no `CERT`, the symbology table cites the CFE/NMX source, and the golden DXF was regenerated
- `pvsld.core.rules`: the `Severity` enum lives in `pvsld.core.severity` (still importable from `pvsld.core.rules`); `calc.max_ocpd_for_ampacity_a` is shared by CON-003 and the conductor sizing
- A specification of 12 modules per string now also reports STR-007 (13.2 kWp > 9 kW); the sample (2 x 7) and the golden DXF are unchanged
- `IMPLEMENTATION_PLAN.md`: Stage 3.3 and Stage 3.4 In Progress

## [0.2.0-spike] - 2026-10-06

Phase 2 (MCP Server Prototype & Connectivity Spike) complete; ADR-0001 confirmed.

### Added
- Phase 2, Stage 2.5: `docs/spikes/phase-2-review.md`, the spike review. It holds the per-stage results against the criteria, the ADR-0001 exit-gate evaluation (passed), the status of reversal triggers T1–T9 (none fired), the findings, the open items and the proposed (tentative) scope for Phases 3–5
- Phase 2, Stage 2.4 (S4, PR #6): Core Console finisher `pvsld.finishers.core_console` and `pvsld finish`: DXF → DWG 2018 (TrustedDWG) plus an AutoCAD-plotted A3 PDF through `accoreconsole.exe /isolate`, in 4.2–10.8 s per sheet. A run is ok only on several independent signals (exit code, progress markers, AUDIT summary, output formats), so failures are never silent. It also adds a CI fake runner, live `autocad` tests and the `scripts/s4_measure.py` harness; report `docs/spikes/s4-core-console.md`
- Phase 2, Stage 2.3 (S3, PR #5): stdio MCP server `pvsld-mcp` (`mcp` 2.3) with `validate_pv_design` and `generate_single_line_diagram`, plus the resources `pvsld://schema/pv-system-spec`, `pvsld://rulepack/mx-gd-2026.10` and `pvsld://symbols`. It writes into an output sandbox and returns a size-bounded PNG preview (`PVSLD_PREVIEW_MAX_BYTES`). The repo `.mcp.json` uses `${PVSLD_MCP_COMMAND:-pvsld-mcp}`. Pillow is a declared dependency, and specs over 256 KiB are refused. Report `docs/spikes/s3-mcp-round-trip.md`
- Phase 2, Stage 2.1 (S1, PR #3): deterministic core (`pvsld.core`: Pydantic parameter model, calculations, rule-pack subset VOLT-001, STR-001, STR-004, CON-003, PCC-002, MET-001, DIS-003, DIS-004), code-defined symbol catalogue (`pvsld.symbols`), backend-neutral diagram model and ezdxf DXF R2018 backend with PNG preview; `pvsld validate` and `pvsld generate`; byte-identical golden DXF on Windows and Linux
- Phase 2, Stage 2.2 (S2, PR #2): AutoCAD 2027 .NET 10 plug-in (bridge, Core-safe render assembly, desktop host) on a current-user named pipe with per-start secret; Python pipe client, fake plug-in and COM baseline; CI job building the plug-in and running its bridge tests
- `docs/decisions/ADR-0003-symbol-library-format.md`: symbol library format and `PVSLD_*` naming (accepted 2026-10-06)
- Phase 2, Stage 2.0 (Foundation): Python project scaffold for the `pvsld` package
  - `pyproject.toml`: hatchling build, `src/` layout, version `0.2.0.dev0`, Python >= 3.11, MIT; runtime dependencies `ezdxf`, `mcp` 2.x, `pydantic` 2.x and `PyYAML`; extras `dev` (pytest, pytest-cov, ruff) and `autocad` (`pywin32`, Windows only); console script `pvsld`
  - `src/pvsld/`: `__version__` read from package metadata, `py.typed`, and empty `core/`, `backends/`, `transports/` and `finishers/` subpackages whose docstrings state their role in ADR-0001
  - `pvsld --version` (the Stage 2.0 `validate-example` smoke check was replaced by `pvsld validate` in Stage 2.1)
  - `examples/residential_7p7kwp.yaml`: the 7.70 kWp / 6 kW @ 220 V worked example from the vault's PV SLD Parameter Model, marked as an illustrative sample
  - `tests/`: package, CLI, `pyproject.toml` and example tests, and a `--run-autocad` option that skips `autocad`-marked tests (with a reason) unless it is given on Windows
  - Ruff lint and format configuration; pytest with strict markers; coverage floor of 60 % on `pvsld`
  - `.github/workflows/ci.yml`: ruff and pytest on Ubuntu and Windows with Python 3.11 and 3.12 (`contents: read` permissions)
  - "Development setup" sections in `README.md` and `CONTRIBUTING.md` (virtual environment, ruff, pytest, AutoCAD tests)

### Fixed
- Backend (PR #7): the overall paper-space viewport is on layer `0` and the layout names the canonical `ISO_full_bleed_A3_(420.00_x_297.00_MM)` paper. AutoCAD 2027 AUDIT of the S1 DXF goes from 2 errors to 0 errors, 0 fixed (Core Console). The read-back counts that viewport apart from drawing content; the golden DXF is regenerated, and ADR-0003 states the layer-0 exception

### Changed
- `docs/decisions/ADR-0001-claude-autocad-integration.md`: "Phase 2 validation (2026-10-06)" section appended. The ADR is confirmed by spikes S1–S4 and its status is unchanged
- `IMPLEMENTATION_PLAN.md`: Stages 2.3 and 2.4 Complete; Stage 2.5 Complete except the `v0.2.0-spike` tag; Phase 2 Complete pending release; tentative scopes for Phases 3–5 refined from the review
- `README.md`: status (Phase 2 complete, pending `v0.2.0-spike`), roadmap, and quick-start notes for the MCP server and `PVSLD_MCP_COMMAND`
- `docs/README.md`: lists `docs/spikes/` and ADR-0003; update notes on the S2, S3 and S4 reports point to the review
- `IMPLEMENTATION_PLAN.md`: Stage 1.7 records the public GitHub repository and the `v0.1.0-docs` GitHub release
- `IMPLEMENTATION_PLAN.md`: Stages 2.0–2.2 Complete; the `.mcp.json` placeholder is replaced by creating `.mcp.json` in Stage 2.3 together with a working server
- `.gitignore`: ignore `.venv/` and `.ruff_cache/`
- `CONTRIBUTING.md`: the Python checks are now ruff and pytest (previously black and flake8)

## [0.1.0-docs] - 2026-10-05

Phase 1 (Documentation & Regulatory Research) complete.

### Added
- Initial repository scaffold with GitFlow structure (main, develop, feature/* branches)
- `README.md` with project vision, current status, and roadmap
- `CONTRIBUTING.md` with detailed GitFlow workflow and Conventional Commits guidelines
- `LICENSE` (MIT, Copyright 2026 edu3250)
- `.gitignore` covering Python, Node.js, AutoCAD, IDE, and OS temporary files
- `CHANGELOG.md` (this file) following Keep a Changelog format
- `IMPLEMENTATION_PLAN.md` with seven detailed stages for Phase 1 (Documentation & Research)
- `docs/README.md` explaining technical documentation structure
- Obsidian research vault scaffold (author's local vault, not part of this repository) with research domains
- Phase 1 research corpus in the Obsidian vault (Stages 1.2, 1.3, 1.5, 1.6): 252 research notes (129 sources, 78 entities, 37 concepts, 8 comparisons). It covers:
  - Autodesk APIs and MCP servers;
  - MCP and Claude integration;
  - a survey of community AutoCAD MCP servers;
  - programmatic DWG/DXF generation, including a hands-on ezdxf probe;
  - Mexican regulation, including the machine-checkable SLD checklist MX-A01…MX-I07;
  - PV single-line-diagram engineering: parameter model v0.1.0 and validation rules.
- `docs/decisions/ADR-0001-claude-autocad-integration.md`: ADR-0001 accepted (Stage 1.4). It adopts a layered hybrid: a Python stdio MCP server, a deterministic core (parameter model → calculations → `mx-gd-2026.10` rule pack → diagram model), an ezdxf DXF backend first and an AutoCAD 2027 .NET 10 plug-in backend second. Vault original: `wiki/decisions/ADR-0001 Integration Approach.md`
- `docs/research/phase-1-summary.md`: condensed English summary of the Phase 1 findings, open questions and a map of the vault
- `.gitattributes`: LF normalization for text; DXF/DWG/PDF/PNG kept byte-exact for golden-file tests
- Stage 1.7 vault lint (`Lint Report 2026-10-05` in the vault): 0 dead links, 0 orphans, 0 frontmatter failures; 2 errors and 10 warnings fixed (8 uncovered MX checklist items received rules, rule pack now 98 rules; pre-ADR notes aligned with ADR-0001)

### Changed
- `IMPLEMENTATION_PLAN.md`: Stages 1.1–1.7 marked Complete. Phase 2 is refined into tentative stages 2.1–2.5 (spikes S1–S4 from ADR-0001 plus a review), still to be confirmed by the owner
- `README.md`: status, roadmap and documentation links updated
- `docs/README.md`: directory tree lists `docs/research/`
- Checklist coverage figures corrected after the vault lint: 77 MX items, 71 machine-checkable (92 %)

---

## Version Numbering Convention

- **`v0.1.0-docs`** — Phase 1 complete; documentation and research published
- **`v0.2.0-spike`** — Phase 2 complete; MCP connectivity prototype validated
- **`v0.3.0-engine`** — Phase 3 complete; parametric PV sizing engine
- **`v1.0.0`** — Phase 5 complete; full product release with Mexican regulatory compliance

---

**Repository:** https://github.com/edu3250/Diagrama-unifilarAutoCAD  
**Maintainer:** edu3250 (edu3250@gmail.com)  
**Last updated:** 2026-10-06
