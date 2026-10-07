# Implementation Plan

All work is tracked in phases and stages. Each stage has specific deliverables, success criteria, verification tests, and a status tracker.

Update status after each merge. Completed phases are condensed into `CHANGELOG.md`; delete this file only when no planned phases remain in it.

---

## Phase 1: Documentation & Regulatory Research

**Goal:** Exhaustive research into AutoCAD connectivity patterns, MCP integration, Mexican electrical regulations, and PV single-line diagram standards. All knowledge captured in the Obsidian vault.

**Target Release:** `v0.1.0-docs`

---

### Stage 1.1: Vault Scaffold & Conventions

**Goal:** Establish the Obsidian vault structure, templates, and frontmatter conventions to standardize all research documentation.

**Success Criteria:**
- Vault directory tree created in the author's local Obsidian vault
- All template files in `_templates/` ready for researchers
- Five research domains initialized with stub pages
- Frontmatter conventions documented in vault `CLAUDE.md`
- First research entry logged in `wiki/log.md`

**Tests:**
- All directories exist and contain `.gitkeep` or initial files
- `wiki/index.md` renders without broken links
- All domain pages include required frontmatter fields
- `_templates/*.md` contain valid YAML frontmatter
- `.manifest.json` in `.raw/` is valid JSON

**Status:** Complete

---

### Stage 1.2: Official Autodesk APIs & MCP/Claude Documentation Research

**Goal:** Deep dive into official Autodesk AutoCAD APIs, Model Context Protocol (MCP) specifications, and Claude integration documentation.

**Success Criteria:**
- Comprehensive research of Autodesk's official AutoCAD API documentation (AutoCAD .NET SDK, COM, AutoLISP, RealDWG)
- MCP protocol specification fully documented with use cases
- Claude API integration patterns researched (tool use, agent mode, function calling)
- All sources saved to vault with citation metadata
- Decision factors identified for integration approach (latency, complexity, licensing)

**Tests:**
- Vault lint: no dead links in sourced materials
- All sources cited with `source_type`, `url`, `confidence`, and `key_claims`
- Entity pages created for Autodesk, Anthropic, AutoCAD products
- Concept pages for MCP, Claude tools, API patterns
- Coverage checklist: AutoCAD API documentation thoroughly ingested

**Status:** Complete

---

### Stage 1.3: Community GitHub AutoCAD↔LLM/MCP Implementations Survey

**Goal:** Systematic survey of existing open-source projects attempting to integrate AutoCAD with LLMs, Claude, or MCP.

**Success Criteria:**
- GitHub search across keywords: "AutoCAD API", "AutoCAD Claude", "AutoCAD LLM", "AutoCAD MCP", "DXF generation", "AutoLISP AI"
- Each relevant repository documented in vault with:
  - Project purpose and maturity level
  - Integration approach (API, COM, file-based, headless)
  - Source code language and dependencies
  - Licensing and viability for reference/reuse
  - Lessons learned and limitations
- Comparison matrix created (Stage 1.4)

**Tests:**
- Vault lint: all repository entities linked correctly
- Each repository has a dedicated entity page with contact info and known issues
- Source citations include GitHub URLs and commit hashes (reproducible)
- Coverage checklist: at least 15–20 relevant projects surveyed

**Status:** Complete

---

### Stage 1.4: Integration Approach Comparison & ADR-0001

**Goal:** Synthesize research from Stages 1.2 and 1.3 into an Architecture Decision Record (ADR) recommending the optimal integration approach.

**Success Criteria:**
- ADR-0001 document created at `docs/decisions/ADR-0001-claude-autocad-integration.md`
- Comparison of integration options:
  - AutoCAD .NET with MCP bridge
  - AutoLISP + external Claude API calls
  - Design Automation API + MCP
  - ODA (Open Design Alliance) file generation
  - Pure DXF/DWG file generation (ezdxf, libredwg, etc.)
- Decision rationale: cost, latency, complexity, compliance, maintainability
- Accepted approach clearly stated with trade-offs documented
- ADR written in the vault as `wiki/decisions/ADR-0001 Integration Approach` (original) and mirrored to `docs/decisions/`

**Tests:**
- ADR document is well-formed markdown
- All options compared with pros, cons and an explicit verdict
- Decision is defensible from user's architectural constraints
- References to Stage 1.2 and 1.3 research intact

> ADR-0001 accepted 2026-10-05: layered hybrid, ezdxf DXF backend first, AutoCAD 2027 .NET 10 plug-in backend second; see `docs/decisions/ADR-0001-claude-autocad-integration.md`.

**Status:** Complete

---

### Stage 1.5: Mexican Electrical Regulatory Research

**Goal:** Comprehensive research into Mexican electrical standards for distributed PV generation and interconnection.

**Success Criteria:**
- NOM-001-SEDE (Electrical installations) coverage:
  - Single-line diagram requirements
  - Labeling and symbology standards
  - Protection device specifications
- CRE (Comisión Reguladora de Energía, replaced by the CNE in 2025) interconnection rules researched
- CNE (Comisión Nacional de Energía) and CFE (Comisión Federal de Electricidad) guidelines documented
- UVIE (Unidad de Verificación de Instalaciones Eléctricas) inspection checklist understood
- Local utility requirements (e.g., CFE plant interconnection rules)
- Compliance checklist created for diagram validation (Stage 1.6)

**Tests:**
- Vault lint: all regulation entities have titles, sources, and key requirements
- Each standard page contains relevant excerpts and official references
- Concept pages for "distributed generation", "interconnection", "protection zones"
- Coverage checklist: all major Mexican regulations and their diagram implications documented

**Status:** Complete

---

### Stage 1.6: PV Single-Line Diagram Best Practices & Parametric Model

**Goal:** Research single-line diagram conventions for photovoltaic systems and define the parametric data model that will drive automatic diagram generation.

**Success Criteria:**
- Industry best practices for PV single-line diagrams researched (IEEE, IEC, regional variants)
- Mexican-compliant symbology standards documented (per NOM-001-SEDE)
- Typical PV system components identified:
  - DC side: arrays, strings, string combiners, DC disconnects, DC protections (breakers, fuses)
  - Inverters: string, central, hybrid configurations
  - AC side: inverter breakers, AC disconnects, transformers, grid interconnect points
  - Protections: overcurrent, overvoltage, grounding, islanding detection
- Example single-line diagrams for common configurations (5kW residential, 30kW commercial, 100kW utility)
- Parametric model defined:
  - Input parameters: array count, inverter type/count, string configuration, protection specs
  - Output diagram data model: symbol types, connections, labels, zones
- Symbol library requirements documented (vector format, attributes per symbol)

**Tests:**
- Vault lint: all example diagrams linked and sourced
- Concept pages for each diagram component with symbol descriptions
- Parametric model documented in machine-readable format (JSON/YAML schema stub)
- Coverage checklist: main PV topologies (radial, series-parallel, multi-inverter) covered

**Status:** Complete

---

### Stage 1.7: Vault Lint & Phase 1 Review; Release v0.1.0-docs

**Goal:** Validate vault completeness and health, perform phase review, and release Phase 1 as `v0.1.0-docs`.

**Success Criteria:**
- Vault lint pass:
  - No orphaned or dead-link pages
  - All wikilinks resolve correctly
  - All entity and concept pages have complete frontmatter
  - All sources cited with proper metadata
  - No duplicate entities or concept definitions
- Phase 1 review checklist:
  - All 6 prior stages marked Complete
  - `wiki/index.md` updated with final page count and source ingestion count
  - `wiki/hot.md` summarizes key findings and open questions
  - `wiki/overview.md` readable by newcomers
- Git release:
  - `release/0.1.0-docs` branch created from develop (git-flow, tag prefix `v`)
  - `CHANGELOG.md` updated with stage summaries
  - `IMPLEMENTATION_PLAN.md` updated (Phase 1 condensed; Phases 2–5 stay planned here)
  - Merge to main, tag `v0.1.0-docs`
  - Merge back to develop

**Tests:**
- Vault lint tool (provided by `claude-obsidian:wiki-lint`) passes with zero errors
- All files UTF-8 encoded, no broken image links
- GitHub release created for `v0.1.0-docs` with release notes (once the public repository is published)
- Tag `v0.1.0-docs` exists on main branch

> Closed 2026-10-05: vault lint 0 errors after fixes (`Lint Report 2026-10-05`), tag `v0.1.0-docs` on main. Public repository published the same day (https://github.com/edu3250/Diagrama-unifilarAutoCAD) with GitHub release `v0.1.0-docs`.

**Status:** Complete

---

## Phase 2: MCP Server Prototype & Connectivity Spike

**Goal:** Prove ADR-0001 before committing to production code. Five stages cover the Python project scaffold (2.0), the ezdxf rendering path (2.1), AutoCAD 2027 connectivity (.NET 10 plug-in vs COM, 2.2), the MCP round trip from Claude Code (2.3), the Core Console finisher (2.4), and spike review + ADR confirmation (2.5). All numeric thresholds are proposed targets from the ADR.

**Target Release:** `v0.2.0-spike`

**Status:** Complete (released as `v0.2.0-spike`, 2026-10-06)

---

### Stage 2.0: Foundation – Python Project Scaffold & CI

**Goal:** Establish the Python project structure, development environment, testing framework and continuous integration pipeline to support Stages 2.1–2.5.

**Success Criteria:**

- Project layout: `src/pvsld/` (package), `tests/`, `examples/`, `.github/workflows/`, `pyproject.toml`
- `pyproject.toml` with src layout, package name `pvsld`, runtime dependencies (ezdxf, mcp, pydantic, PyYAML), a `dev` extra (pytest, pytest-cov, ruff), an `autocad` extra (pywin32, Windows only), build backend (hatchling), and CLI entry point
- Tooling: ruff (lint + format), pytest (with `autocad` marker excluded by default in CI), coverage ≥60% for changed code
- CI matrix: `windows-latest` and `ubuntu-latest`, Python 3.11+
- `.mcp.json` is created in Stage 2.3 together with a working server (a placeholder would make Claude Code try to start a non-existent server)
- Sample input file `examples/residential_7p7kwp.yaml` from the vault's worked example (PV SLD Parameter Model)
- `venv` instructions in `README.md` and `CONTRIBUTING.md` updated

**Tests:**

- Verify `pyproject.toml` is valid, can be parsed and build succeeds
- Confirm toolchain (ruff, pytest) runs without errors on a clean checkout
- Check that AutoCAD-marked tests are skipped in CI (marked tests report "skipped", not failures)
- Verify sample parameter file is valid YAML and matches the schema stub
- GitHub Actions workflow passes on both Windows and Ubuntu for Python 3.11

> Merged 2026-10-06 (PR #1): CI green on Ubuntu and Windows, Python 3.11 and 3.12.

**Status:** Complete

---

### Stage 2.1: S1, ezdxf Minimal PV SLD

**Goal:** Render the 7.70 kWp residential sample parameter file to a DXF R2018 SLD through a backend-neutral diagram model. The sheet has an A3 layout, title block and string table, and uses a minimal symbol library.

**Success Criteria:**
- `doc.audit()` reports 0 errors and 0 fixes
- Output is byte-identical across two runs and across Windows and Linux CI runners (fixed metadata)
- INSERT count per block equals the model count; 100 % attribute round-trip by `COMP_ID`; 0 dangling ports; 0 entities on layer `0`
- Build + write ≤ 1 s; PNG preview ≤ 3 s
- The DXF opens in AutoCAD 2027 and AUDIT reports 0 errors (manual check)

**Tests:**
- Golden-file test against a committed DXF fixture
- Semantic ezdxf query tests (blocks, attributes, layers, port connectivity)
- Rule-subset tests (VOLT-001, STR-001, STR-004, CON-003, PCC-002, MET-001, DIS-003/004) pass on the sample and fail as expected on 3 mutated specs

> Merged 2026-10-06 (PR #3): audit 0/0; byte-identical output across runs, processes and the Windows/Linux CI matrix; 9 blocks / 11 inserts; 147/147 attributes round-trip by `COMP_ID`; 0 dangling ports; 0 entities on layer 0; build + write 97 ms; PNG preview ~1.1 s. The AutoCAD AUDIT check is measured headlessly in Stage 2.4. Symbol naming: ADR-0003 (accepted).

**Status:** Complete

---

### Stage 2.2: S2, AutoCAD 2027 Connectivity (.NET 10 Plug-in vs COM)

**Goal:** Prove the AutoCAD backend transport. A `net10.0` plug-in listens on a current-user named pipe (newline-delimited JSON-RPC plus a secret generated at each start). It answers a ping, inserts an attributed block and reads attributes back. A throwaway Python COM spike against `AutoCAD.Application.26` serves as the baseline.

> .NET 10 SDK 10.0.401 installed with the owner's approval on 2026-10-05. Attended run on AutoCAD 2027 (2026-10-06): 22/22 tests; ping p95 2.25 ms; 200 + 200 batch 47 ms (71 ms worst); 100/100 runs; busy errors in 0.001–1.89 s; 5/5 injected failures rolled back; unauthenticated client refused. COM was 37–186× slower for drawing work. See `docs/spikes/s2-autocad-connectivity.md` (PR #2).

**Success Criteria:**
- COM baseline: pywin32 spike against `AutoCAD.Application.26` with message-filter retries; operations (ping, insert attributed block, read attributes, batch of 200 inserts + 200 lines); reliability metrics and latency recorded
- .NET 10 plug-in: named pipe with newline JSON-RPC and secret; plug-in ping p95 < 50 ms; 200-insert batch < 2 s; COM/plug-in latency ratio recorded
- 100/100 consecutive runs without unhandled errors
- With a modal dialog or an active command, the plug-in returns an actionable "busy" error within 5 s, and AutoCAD never hangs
- An injected mid-transaction failure leaves the drawing unchanged
- A client without the secret is refused; the pipe ACL is current-user only

**Tests:**
- COM spike: pywin32 benchmark harness (marked `autocad`, run manually on the licensed workstation)
- .NET 10 plug-in benchmark: marked `autocad` and run manually
- Protocol tests of the pipe client against a fake server (CI, SDK-independent)
- Benchmark results recorded in the vault

**Status:** Complete

---

### Stage 2.3: S3, MCP Round Trip from Claude Code

**Goal:** Build a Python MCP server (`mcp` 2.x, stdio) registered through a repo `.mcp.json`. It exposes `validate_pv_design`, `generate_single_line_diagram` (ezdxf backend) and the parameter-schema resource.

**Success Criteria:**
- The server starts and lists tools in < 5 s (Claude Code's startup timeout is 30 s)
- Claude completes validate → generate on the sample in ≤ 4 tool calls; the result (drawing_id, DXF path, PNG preview) stays under the 25k-token output cap
- An invalid spec (12 modules per string) returns a VOLT-001 tool error that Claude then corrects

**Tests:**
- In-memory MCP client tests in CI
- MCP Inspector session
- Optional: the same flow in Claude Desktop within 240 s

> Merged 2026-10-06 (PR #5): `mcp` 2.3.0 stdio server with `validate_pv_design`, `generate_single_line_diagram` and three resources. It starts and lists tools in 2.0–2.6 s, and a result with the preview is about 20.9k tokens (estimate). In the owner's manual Claude Code run, validate → generate took 2 calls, and Claude corrected the 12-module VOLT-001 spec in 4. Claude also spotted an inverter DC overload that no implemented rule caught (STR-007, Phase 3). MCP Inspector was not run (no Node.js) and Claude Desktop was not tested. See `docs/spikes/s3-mcp-round-trip.md`.

**Status:** Complete

---

### Stage 2.4: S4, Core Console Finisher

**Goal:** Convert the S1 DXF to DWG 2018 and plot a PDF headlessly with `accoreconsole.exe` on the licensed workstation.

**Success Criteria:**
- The DWG opens in AutoCAD 2027 without the "not saved by Autodesk" notice; a PDF is produced
- ≤ 15 s per sheet
- Running outside a licensed session produces a reported error, never a silent success

**Tests:**
- Scripted finisher run (marked `autocad`) that checks the exit code, the existence of the output files and a timeout

> Merged 2026-10-06 (PR #6): `pvsld finish` gives DWG `AC1032` (TrustedDWG) and a 1-page A3 PDF in 4.2–10.8 s per sheet, and 4/4 failure modes are reported. It also found that AutoCAD AUDIT rejects the S1 overall paper-space viewport off layer 0; PR #7 fixed this, and AUDIT now reports 0/0 (12.2 s cold). See `docs/spikes/s4-core-console.md`.

**Status:** Complete

---

### Stage 2.5: Spike Review, ADR-0001 Confirmation and Release v0.2.0-spike

**Goal:** Review the S1–S4 results against ADR-0001's exit gate and reversal triggers. Either confirm the ADR or record a superseding ADR, then plan Phases 3–5 to match.

**Success Criteria:**
- S1 and S3 meet their criteria, and S2 shows the plug-in meets its reliability criteria; otherwise a superseding ADR is recorded
- Spike measurements and decisions are logged in the vault
- `CHANGELOG.md` is updated and `v0.2.0-spike` is tagged per GitFlow

**Tests:**
- All CI tests green on Windows and Linux
- Vault lint passes for the new notes

> Review 2026-10-06 (`docs/spikes/phase-2-review.md`): the exit gate is passed and ADR-0001 is confirmed, with no superseding ADR. Reversal triggers T1–T9 were not fired. A "Phase 2 validation" section is appended to ADR-0001 (repository mirror and vault original), and the vault note "Phase 2 Spike Review 2026-10" records the review. `CHANGELOG.md` is updated. Released as `v0.2.0-spike` (GitFlow release branch, tag on `main`, GitHub release).

**Status:** Complete

---

## Phase 3: Parametric PV Sizing Engine & Complete Rule Pack

**Goal:** Implement the deterministic PV system sizing engine, store component specifications from manufacturer datasheets, complete the validation rule pack to all 98 rules (including STR-007, the gap found in Phase 2), and expose sizing as an MCP tool to Claude. The owner supplies component datasheets; the team extracts specifications, validates them, and stores them in a versioned catalogue. The sizing engine proposes string configurations, inverter matching, and balance-of-system (BOS) sizing deterministically, while Claude elicits parameters and explains trade-offs.

**Target Release:** `v0.3.0-engine`

---

### Stage 3.1: Component Catalogue Data Model & Storage Format (ADR-0004)

**Goal:** Design and implement the component catalogue schema and storage backend. Define how equipment datasheets map to the parameter model, including PV module specs (Pstc, Voc, Vmp, Imp, temp coefficients), inverter specs (Pdc_max, Vdc_max, MPPT count and limits, AC power, certifications), and balance-of-system components (conductors, fuses, breakers, SPD ratings). Establish a workflow for datasheet ingestion: PDF → markitdown → human review → versioned catalogue.

**Success Criteria:**

- ADR-0004 (proposed) documents the chosen storage format (YAML per component, SQLite, or JSON), with rationale for cost-of-change, auditability, and version control
- Component schema defined and validated:
  - PV modules: `pstc_w`, `voc_v`, `vmp_v`, `imp_a`, `temp_coef_voc` (V/K), `temp_coef_pmp` (%/K), `temp_coef_imp` (A/K), `isc_a`, dimensions, weight, frame type, source (datasheet SHA-256, page ref, extraction date, reviewed flag)
  - String/hybrid inverters: `pdc_max_w`, `vdc_max_v`, `vdc_min_v`, `mppt_count`, per-MPPT `isc_max_a`, `vmp_window_v`, `pac_nominal_w`, `pf_range`, `thd_max`, certifications (UL-1741-SB, IEEE-1547, NMX), source fields
  - Conductors: rated ampacity vs. temperature, insulation type, core cross-section, voltage drop per meter at rated current
  - Overcurrent devices: interrupting rating (KAIC), voltage rating, current rating, certifications
- `src/pvsld/catalogue.py` module with typed schema (Pydantic) and a `ComponentRegistry` class
- Git-ignored `datasheets/inbox/` and `datasheets/cache/` directories (raw PDFs and markitdown); committed `datasheets/records/` with per-component JSON/YAML records including provenance
- Unit validation tests (e.g., Vmp < Voc, Imp < Isc, temperature coefficients in plausible ranges)
- Documentation in `CONTRIBUTING.md` on the datasheet ingestion workflow

**Tests:**

- Schema validation: 10+ fixtures pass Pydantic type checking and unit plausibility
- Three mutated specs fail expected validations (e.g., Voc < Vmp, negative temp coeff where positive expected)
- Roundtrip test: record → model → JSON serialization is lossless
- File integrity test: source SHA-256 and extraction metadata are present and immutable after commit
- Coverage: at least 3 PV modules, 3 inverters, 5 conductor types, 10 protection devices in the initial commit

**Status:** Not Started

---

### Stage 3.2: Datasheet Ingestion Pipeline & Validation Workflow

**Goal:** Create a semi-automated pipeline to extract component specifications from manufacturer PDFs using markitdown and Claude's reading ability, validate the extracted facts, and store them in the catalogue. Establish a human-review workflow so the owner can approve extracted records before they're committed.

**Success Criteria:**

- `docs/datasheet-ingestion-protocol.md` documents the workflow:
  1. Owner places PDF in `datasheets/inbox/<component_type>/<model>.pdf`
  2. markitdown converts to markdown, cached in `datasheets/cache/` (git-ignored)
  3. Claude reads the markdown and extracts structured facts into a JSON template
  4. Python validation script checks plausibility (units, ranges, cross-field consistency)
  5. Owner reviews the extracted record and either approves or flags for re-read
  6. Approved record is committed to `datasheets/records/<component_type>/<model>.yaml`
- `src/pvsld/ingest.py` script:
  - `ingest_datasheet(pdf_path: Path, component_type: str) → dict` (returns extraction template for human review)
  - `validate_component_record(record: dict, schema: Type[BaseModel]) → tuple[bool, list[str]]` (returns validity and any warnings)
  - Token budget for PDFs: estimate tokens with markitdown, then chunk if > 50k
- Example ingestion of 3 real datasheets (modules, inverter, protection device) in the repo history
- Validation catches at least 5 common datasheet mistakes (ambiguous specs, unit mismatches, out-of-range values)
- `src/pvsld/rules.py` extended with a datasheet-sourced fact check (rule DTS-001: every catalogue component has a source and extraction date)

**Tests:**

- Unit test: `test_validate_component_record` with 10+ fixture records (valid, under-spec'd, out-of-range, missing required fields)
- Integration test: `test_ingest_example_datasheet` reads a sample markdown (synthetic, no copyright), extracts to template, validates, and compares against expected fields (photosynthetic match, not byte match)
- Workflow test: a dry run of the full pipeline on one owner-supplied PDF (marked `datasheets`, skipped in CI because the PDF is not in the repository; only the reviewed record is committed)
- No full PDFs committed to the public repo; `.gitignore` enforces this

**Status:** Not Started

---

### Stage 3.3: Rule Pack Completion & STR-007 Priority

**Goal:** Implement all 98 validation rules in the Mexican PV SLD rule pack (`mx-gd-2026.10`), with immediate focus on STR-007 (inverter DC power and DC/AC ratio), which Phase 2 identified as a gap. Update the vault tables against the current NOM-001-SEDE-2012 and CRE regulations.

**Success Criteria:**

- Phase 2 baseline: 8 of 98 rules implemented; Phase 3 target: ≥ 80 of 98 (85 %)
- **STR-007 (inverter DC power)** implemented and tested:
  - Rule: Σ(P_STC of modules on each string × number of strings) ≤ inverter P_dc,max (error if violated)
  - DC/AC ratio check: ratio ≥ 1.0 and ≤ policy ceiling (e.g., 1.35 for warnings, 1.5+ as errors per owner policy; configurable)
  - Test case: the Phase 2 owner test (2 × 11 × 550 W = 12.1 kWp vs. inverter P_dc,max = 9 kW) correctly rejects as STR-007
- Vault note `PV SLD Validation Rules.md` re-read against NOM-001-SEDE-2012 (published text, not phase 2 memory); all 98 rules updated with:
  - Rule ID (`STR-NNN`, `VOLT-NNN`, `CON-NNN`, `PCC-NNN`, `MET-NNN`, `DIS-NNN`, `PROT-NNN`, `I-NNN`)
  - Mexican regulation reference (NOM, CRE/CNE table, CFE guideline, UVIE requirement)
  - Machine-checkable condition (formal or pseudo-code)
  - Severity (error vs. warning/info)
- Coverage test per MX-xx checklist item: 65 of 71 machine-checkable items (MX-A through MX-I) have a mapping in `src/pvsld/rules.py`
- `src/pvsld/rules.py`:
  - One rule class per catalogue rule (factory or registry pattern)
  - `RulePack` with a `check(spec: PVSystemSpec, catalogue: ComponentRegistry) → list[Finding]`
  - `Finding` dataclass with rule_id, severity, description, affected_component_ids, remediation hint
- Rule test suite:
  - Happy path: the residential_7p7kwp example passes all implemented rules
  - Sad paths: 30+ mutations of the example (bad string voltage, bad conductor size, too many modules, inverter overload, etc.) each fail the expected rule
  - Regression: the Phase 2 8-rule subset still passes

**Tests:**

- `test_rule_str_007_dc_power`: nominal, at limit, and over limit cases
- `test_rule_pack_coverage`: every MX-xx item has a mapping
- `test_residential_7p7kwp_passes`: golden spec passes all implemented rules
- `test_mutations_fail_expected_rules`: 30+ mutations each trigger exactly one expected rule
- Vault lint: all 98 rule IDs in the vault have a corresponding Python implementation or a deferred note
- CLI: `pvsld check examples/residential_7p7kwp.yaml` reports 0 findings

**Status:** Not Started

---

### Stage 3.4: Parametric Sizing Engine (Strings, Inverters, Conductors, OCPD)

**Goal:** Implement the deterministic sizing engine: given a site (min/max temperature, utility service voltage/frequency), a target system size (kWp), and a choice of components from the catalogue, compute viable string configurations, inverter matching, DC/AC ratio, conductor sizes, overcurrent protection, and voltage drop. Return a ranked list of candidate designs and recommend one. Explain why alternatives were rejected.

**Success Criteria:**

- `src/pvsld/sizing.py`:
  - `propose_string_configs(modules: list[PVModule], vdc_window: tuple[float, float], mppt_isc_max_a: float, site: SiteParams) → list[StringConfig]`
    - Input: module model, min/max counts per string (from voltage rules VOLT-NNN), MPPT current limit, temperature extremes
    - Output: ≥ 1 and ≤ 10 candidate configs with (modules_per_string, count, voc_min_hot, voc_max_cold, isc, pdc)
    - Compute temperature-corrected Voc at T_min (cold) and T_max (hot) using module temp coefficient
    - Reject configs where Voc_cold > MPPT V_max or Voc_hot < MPPT V_min (VOLT rules)
    - Reject configs where string Isc > MPPT I_max or total Pdc > inverter Pdc_max (STR-007)
  - `match_inverters(target_pdc_w: float, target_vdc_window: tuple, site: SiteParams, catalogue: ComponentRegistry) → list[InverterMatch]`
    - Propose ≥ 1 inverter from the catalogue that fits the DC power and voltage window
    - Compute DC/AC ratio and report as info/warning/error per policy
  - `size_conductors_and_ocpd(strings: list[StringConfig], pdc_total: float, vdc: float, circuit_type: str, max_voltage_drop_pct: float = 3.0) → BosSpec`
    - Input: DC current (Isc × safety factor), AC current (Pac / V_ac), conductor routing length, ambient temperature
    - Output: conductor AWG/mm², OCPD type and rating, voltage drop %, grounding requirements
    - Use NOM-001 tables from vault for copper conductor ampacity (temperature-derating and bundling)
    - Apply 125 % factor for continuous loads, 80 % factor for non-continuous; STR rules for string current limits
    - Reject sizing where voltage drop > max (3 % DC typical, 3 % AC typical per NOM)
  - `size_pv_system(site: SiteParams, target_pdc_w: float, module_model: str, inverter_choice: Optional[str], owner_constraints: dict) → SizingResult`
    - Orchestrator: call propose_string_configs, match_inverters, size_conductors, then validate full spec with rule pack
    - Return a `SizingResult` with a ranked list of candidate specs (best first), selected spec, and a human-readable report explaining trade-offs and rejections
  - All sizing is deterministic Python; no LLM calls
- Example (the Phase 2 owner test): with the sample 550 W module and the 6 kW inverter (P_dc,max 9 kW, V_dc,max 600 V) at T_min −3 °C, the engine rejects 2 × 12 (VOLT-001, 640 V) and 2 × 11 (STR-007, 12.1 kWp > 9 kW), and selects 2 × 8 (8.8 kWp, DC/AC 1.47, Voc 426.8 V), reporting why each alternative was rejected; its conductors, OCPD and voltage drop pass the rule pack
- Test harness: `test_size_residential_7p7kwp` passes known configurations
- Token budget: sizing result (candidate list + selected spec + explanations) stays under 10k tokens (leaves room for Claude's reasoning)

**Tests:**

- `test_string_config_temp_corrected_voc`: Voc at hot and cold temperatures is within voltage window
- `test_string_config_reject_overvoltage`: config with Voc_cold > MPPT_Vmax is rejected
- `test_string_config_reject_overpower`: config with Pdc > inverter Pdc_max is rejected (STR-007)
- `test_inverter_match`: only inverters with Vdc_min ≤ string_vmp ≤ Vdc_max are matched
- `test_conductor_size_voltage_drop`: 7.7 kWp system has ≤ 3 % drop on 50 m DC run with chosen conductor
- `test_ocpd_rating_continuous`: DC OCPD is sized at 125 % × Isc (continuous load rule)
- `test_sizing_result_passes_rule_pack`: proposed spec runs through full rule validation and reports 0 errors (warnings/info allowed)
- `test_residential_example`: end-to-end sizing of the Phase 2 7.7 kWp example returns ≥ 1 candidate, selected spec, no validation errors

**Status:** Not Started

---

### Stage 3.5: MCP Tool Surface & Token Budget Confirmation

**Goal:** Expose the sizing engine as an MCP tool (`size_pv_system`) and publish the component catalogue and rule pack as MCP resources. Confirm the preview token budget with real Claude runs and document the limits.

**Success Criteria:**

- `src/pvsld/mcp/server.py` extended with:
  - `size_pv_system` tool: input schema (site, target_pdc_w, preferred_components, owner_constraints), returns result JSON with candidates, selected spec, report text, and a visual diagram preview (SVG or small PNG, ≤ 5 kB)
  - `list_components` resource / tool: filter by type (module, inverter, conductor, ocpd), return brief catalogue
  - `get_component` tool: fetch full datasheet-sourced spec of one catalogue entry
  - `ingest_datasheet` tool (optional, early): upload a PDF and trigger the extraction pipeline (returns a template for owner review, not a committed record)
- `.mcp.json` updated to list the new tools
- Token budget test (real Claude Code run or estimate):
  - Sizing result (full candidate list + explanations): ≤ 8k tokens
  - Rule catalogue (all 98 rules + MX references): ≤ 15k tokens (published as a resource, not in every call)
  - Total per `size_pv_system` call: ≤ 20k tokens (margin for Claude's reasoning: 25k hard cap, so 5k buffer)
- Environment variable `PVSLD_MCP_COMMAND` documented in README and `.mcp.json` configured correctly
- Optional MCP Inspector session run (if Node.js is installed; confirm tools and schemas are listed)
- User-facing documentation: a worked example in the README ("Size a 10 kWp system for Guadalajara") that calls `size_pv_system`, shows the result and selected spec

**Tests:**

- `test_mcp_size_pv_system_schema`: tool input and output schemas are valid OpenAPI
- `test_size_pv_system_result_under_token_cap`: result JSON serialization is ≤ 20k tokens
- `test_mcp_list_components_by_type`: filter works and returns expected items
- `test_mcp_get_component_detail`: fetches full spec including datasheet provenance
- Integration test: `test_mcp_server_lists_tools`: the server starts, lists tools in < 5 s, and schemas match the code
- Optional: manual Claude Code session ("size a 15 kWp commercial system") within 240 s, no output-cap errors

**Status:** Not Started

---

### Stage 3.6: Minimum Installable Claude Code Plugin

**Goal:** The owner's short-term goal is a Claude Code plugin. Package the `pvsld` MCP server with the plugin layout Claude Code uses (`.claude-plugin/plugin.json`, a plugin-level MCP server definition, skills or slash commands), so that installing the plugin gives Claude the validate, size and generate tools plus guided workflows: design a PV single-line diagram end to end, and ingest a datasheet into the catalogue.

**Success Criteria:**
- Plugin layout follows the structure of plugins actually installed on the workstation (checked against an installed plugin, not memory)
- The plugin starts the MCP server without the `PVSLD_MCP_COMMAND` workaround (e.g., a launcher that finds or creates the Python environment, or a documented `pip install` step the plugin verifies)
- Skills or commands: `design` (elicit inputs → `size_pv_system` → `validate_pv_design` → `generate_single_line_diagram` → review the preview) and `ingest-datasheet` (markitdown → extraction → validation → owner review)
- Installed from a local marketplace/path by the owner in a fresh Claude Code session; the end-to-end design flow works on the owner's datasheet-based catalogue

**Tests:**
- CI: plugin manifest and MCP definition are valid JSON with the required fields; referenced files exist
- Manual (owner): install the plugin, run the design workflow for one real installation, and record the result in the vault

**Status:** Not Started

---

**Phase 3 Status Summary:** In progress (owner confirmed 2026-10-06: Claude Code plugin as the short-term goal; component catalogue from the owner's datasheets via markitdown; parametric sizing in Python)

---

## Phase 4: Diagram Generation & Symbol Library

**Tentative Intent:** Grow the symbol library to Mexican standards and develop layout templates for diverse PV topologies. Extend the B1 (ezdxf DXF) and B2 (AutoCAD .NET plug-in) diagram rendering, and implement the Core Console finisher for DWG and PDF export.

**Note (ADR-0001):** Topology and layout are deterministic; Claude elicits, validates and explains parameters. Rendering is DXF-first (ezdxf, B1), with native DWG and AutoCAD PDF coming from the plug-in (B2) or Core Console finisher (optional). 

**Proposed scope (Phase 2 review, tentative, pending Phase 3 completion):**

- **Symbol library expansion:** Grow beyond the Phase 2 minimal set to the NMX-J-136-ANCE figures (purchase the standard, P1) with approved Mexican SLDs as references and golden files (P12). Support ANSI variants (layout.symbol_style: ANSI) as a separate block set.
- **Layout templates:** Beyond `bt_string_residential_v1`, add templates for 2–4 strings, multiple MPPTs, several inverters, three-phase configurations, and later microinverters and optimizers.
- **B2 production methods:** `render_diagram`, `read_back`, `save_as_dwg`, `plot_pdf`, and `zoom_to` on the diagram model. B1/B2 parity test (golden ezdxf files). A signed `.bundle` for the .NET plug-in (removes the "Load once" prompt).
- **Core Console finisher:** `export_drawing` with batching (multiple sheets per session), non-ASCII path support, and DWGPROPS privacy (clear "last saved by" field). Validation that the output is TrustedDWG 2018 and error-free under AutoCAD AUDIT.
- **Diagram summary tool:** `get_diagram_summary` (name, kWp, inverter, string count, BOS details) for annotation.

**Status:** To be defined (depends on Phase 3; owner confirmation pending)

**Estimated Stages:** 4.1–4.4

---

## Phase 5: Validation, Plugin Packaging & Production Release

**Tentative Intent:** Validate diagram output against Mexican electrical standards and professional reviewers. Harden and distribute the Claude Code plugin started in Stage 3.6 (signed .NET plug-in if needed, public marketplace or GitHub Releases). Release `v1.0.0`.

**Proposed scope (Phase 2 review, tentative, pending Phase 3 and Phase 4 completion):**

- **Regulatory validation (trigger T3, open item Z1):** Gather feedback from UVIE inspection units and CFE on whether DXF and ezdxf PDFs are accepted, or if native DWG and AutoCAD PDFs are required. This feeds the plugin packaging decision.
- **Package validator:** Implement TOP and DRW rules (post-drawing checks), validator for MX-I01…I07, and end-to-end test suite that exercises all diagram types.
- **Claude Code plugin packaging:** Bundle the MCP server (`pvsld-mcp` executable), the configuration, and optional frontend skill/slash command into a `.claude-plugin` package compatible with the Claude Code plugin system. Decide whether to include the .NET plug-in (Phase 4 B2) in the distribution: if regulatory feedback requires native DWG, include it with a signed `.bundle` and installer; otherwise, distribute B1 (ezdxf) only. Host the plugin on a public registry or GitHub Releases.
- **Distribution variants:** 
  - **v1.0.0-core**: MCP server + ezdxf B1, no AutoCAD plug-in, works on any OS with Python 3.11+
  - **v1.0.0-plugin** (conditional): includes the signed .NET 10 plug-in + B2 backend (Windows only), requires AutoCAD 2027
  - Documentation in Spanish and English
- **Claude Desktop support (optional):** Test a full end-to-end run on Claude Desktop (150k character limit, 240 s timeout).

**Status:** To be defined (depends on Phase 4 and regulatory feedback; owner confirmation pending)

**Estimated Stages:** 5.1–5.4

---

**Last updated:** 2026-10-06 (Stage 2.5 spike review)
**Repository:** https://github.com/edu3250/Diagrama-unifilarAutoCAD
