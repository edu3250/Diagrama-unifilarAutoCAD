# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

### Changed
- `IMPLEMENTATION_PLAN.md`: Stages 1.1–1.6 marked Complete and Stage 1.7 In Progress. Phase 2 is refined into tentative stages 2.1–2.5 (spikes S1–S4 from ADR-0001 plus a review), still to be confirmed by the owner
- `README.md`: status, roadmap and documentation links updated
- `docs/README.md`: directory tree lists `docs/research/`

### Status
- Phase 1 (Documentation & Regulatory Research): Stages 1.1–1.6 complete; Stage 1.7 (vault lint, Phase 1 review, release `v0.1.0-docs`) in progress

---

## Version Numbering Convention

- **`v0.1.0-docs`** — Phase 1 complete; documentation and research published
- **`v0.2.0-spike`** — Phase 2 complete; MCP connectivity prototype validated
- **`v0.3.0-engine`** — Phase 3 complete; parametric PV sizing engine
- **`v1.0.0`** — Phase 5 complete; full product release with Mexican regulatory compliance

---

**Repository:** https://github.com/edu3250/Diagrama-unifilarAutoCAD  
**Maintainer:** edu3250 (edu3250@gmail.com)  
**Last updated:** 2026-10-05
