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

**Status:** In Progress

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

**Status:** Not Started

---

### Stage 2.4: S4, Core Console Finisher

**Goal:** Convert the S1 DXF to DWG 2018 and plot a PDF headlessly with `accoreconsole.exe` on the licensed workstation.

**Success Criteria:**
- The DWG opens in AutoCAD 2027 without the "not saved by Autodesk" notice; a PDF is produced
- ≤ 15 s per sheet
- Running outside a licensed session produces a reported error, never a silent success

**Tests:**
- Scripted finisher run (marked `autocad`) that checks the exit code, the existence of the output files and a timeout

**Status:** Not Started

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

**Status:** Not Started

---

## Phase 3: Parametric PV Sizing Engine

**Tentative Intent:** Implement a Python module (per ADR-0001) that accepts solar installation parameters (location, roof/site specs, load, inverter models) and computes optimal string/inverter configuration.

**Status:** To be defined

**Estimated Stages:** 3.1–3.4

---

## Phase 4: Diagram Generation & Symbol Library

**Tentative Intent:** Develop the Claude reasoning engine that translates parametric configuration into single-line diagram topology, and render AutoCAD .dwg files with proper symbology and labeling.

**Note (ADR-0001):** Topology and layout are assigned to deterministic code, not to Claude; Claude elicits, validates and explains parameters. Rendering is DXF-first (ezdxf), with DWG coming from the AutoCAD backend or a finisher. Revise this description when Phase 4 is planned.

**Status:** To be defined

**Estimated Stages:** 4.1–4.5

---

## Phase 5: Validation & Production Release

**Tentative Intent:** Validate diagrams against Mexican electrical standards (NOM-001-SEDE, CRE/CNE, CFE, UVIE), create integration test suite, package as standalone tool, and release `v1.0.0`.

**Status:** To be defined

**Estimated Stages:** 5.1–5.4

---

**Last updated:** 2026-10-05 (Phase 2 kickoff)
**Repository:** https://github.com/edu3250/Diagrama-unifilarAutoCAD
