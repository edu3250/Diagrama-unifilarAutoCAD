# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0-symbols] - 2026-10-08

Symbol library, the generator drawing with it, and the owner's sheet template. Also ships the first part of Phase 3 (component catalogue and the sizing engine v1).

### Added
- Symbol library (Phase 4, ADR-0005): 57 blocks `PVSLD_<FUNCTION>` (library 0.6.0) redrawn as vector geometry, each with its ports (DC, AC, PE, SIG, ANY) in XDATA, its attributes and the standard it comes from (hidden `SOURCE_STANDARD` and the *Fuente* column of the legend). `symbols/pvsld-symbols.dxf` (R2018, byte-reproducible) holds them with three `Legend` layouts grouped by family; `symbols/pvsld-symbols.dwg` is the same library as a TrustedDWG 2018 (AUDIT 0/0). `pvsld symbols build|list|validate|dwg`, `scripts/build_symbol_library.py`
- Parametric blocks defined on demand: the combiner box for 1 to 24 strings (`PVSLD_COMBINER_<n>S`) and a PV string with every module drawn (`PVSLD_PV_STRING_<n>M_UP|DN`, up to 30 modules); AC fuse `PVSLD_FUSE_AC`
- Layout template `a3_plantilla_v1`: the schematic on the owner's A3 sheet. `pvsld sheet import TEMPLATE.dwg|dxf` writes the neutral template `sheet_templates/a3_plantilla_v1.dxf` (published); the layout fills the heading, capacity, service, calculation summary, notes, circuit boxes, module and inverter data, symbology of the blocks drawn, protection schedule, drawing number and date. Personal data stays blank and the title block reads "COMPAÑÍA INSTALADORA". `pvsld size` produces designs on this sheet by default
- Component catalogue (Phase 3, ADR-0004): reviewed datasheet records under `datasheets/records/`, `pvsld catalogue validate|list|show`, review gate in CI
- Sizing engine v1 (Phase 3, Stage 3.4): `pvsld size REQUEST.yaml` enumerates string configurations per catalogue inverter, rejects those that break a rule, ranks the rest and writes a full specification; rule STR-007 and the DC/AC ratio policy (Stage 3.3)
- Diagram model: text styles and centred text, circles, scaled symbol samples; tables with a cell style and a centred title

### Changed
- The generator imports the blocks a diagram uses from the library DXF (port XDATA included) instead of defining symbols in code; instances carry `SOURCE_STANDARD`, the inverter has no `CERT` attribute (certifications are out of scope); the symbology table cites each symbol's source; the golden DXF was regenerated
- The thermomagnetic breaker of the diagrams is `PVSLD_CB` (owner decision); `PVSLD_CB_IEC` stays as an alternative
- `pvsld.core.rules`: `Severity` lives in `pvsld.core.severity`; `calc.max_ocpd_for_ampacity_a` is shared by CON-003 and the conductor sizing

### Removed
- `pvsld.symbols.catalogue` (the Phase 2 code-defined symbols) and `pvsld.backends.dxf.render_symbol_library`

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
