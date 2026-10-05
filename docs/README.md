# Technical Documentation

This directory contains technical documentation for the Diagrama-unifilarAutoCAD project.

## Structure

```
docs/
├── README.md                    (this file)
├── decisions/                   (Architecture Decision Records)
│   └── ADR-0001-claude-autocad-integration.md
├── research/                    (Condensed research summaries; full notes in the vault)
│   └── phase-1-summary.md
└── [other docs as needed]
```

## Knowledge Base: Obsidian Vault

**The primary knowledge base and research documentation lives in the author's local Obsidian research vault (not part of this repository).** A condensed, public summary is in [`research/phase-1-summary.md`](research/phase-1-summary.md).

The vault contains:
- **Research sources** — Autodesk API docs, MCP specs, GitHub surveys
- **Regulatory research** — Mexican electrical standards (NOM-001-SEDE, CRE/CNE, CFE, UVIE)
- **Best practices** — PV single-line diagram conventions and symbology
- **Domain knowledge** — AutoCAD, MCP, electrical engineering concepts
- **Comparisons** — Integration approach evaluation matrices
- **Decisions** — Architecture Decision Records and design rationale

### Accessing the Vault

1. Open the vault in Obsidian (desktop app)
2. Start at `wiki/index.md` for the master catalog
3. Use `wiki/hot.md` for recent activity and key facts
4. Search wikilinks (`[[Page Name]]`) for cross-references

### Vault Conventions

- All pages use YAML frontmatter with standardized fields (see `CLAUDE.md` in the vault)
- Sources are immutable in `.raw/` and referenced with metadata
- The synthesis team (stages 1.4, 1.7) owns `wiki/index.md`, `wiki/log.md`, `wiki/hot.md`, `wiki/overview.md`
- Research team members own their domain-specific pages and entity definitions

## Architecture Decision Records (ADRs)

The working original of each ADR lives in the vault at `wiki/decisions/`. `docs/decisions/` holds the published mirror; if the two differ, the vault wins and the mirror is regenerated.

### ADR-0001: Claude ↔ AutoCAD Integration Approach

**Location:** `docs/decisions/ADR-0001-claude-autocad-integration.md` (vault original: `wiki/decisions/ADR-0001 Integration Approach.md`)

**Status:** Accepted 2026-10-05. The decision is a layered hybrid: an ezdxf DXF backend first, then an AutoCAD 2027 .NET 10 plug-in backend over a current-user named pipe.

Synthesized during Phase 1, Stage 1.4. Documents the recommended integration pattern for connecting Claude (via MCP) to AutoCAD, considering:
- Autodesk's official APIs (.NET SDK, COM, RealDWG, AutoLISP)
- Design Automation API and cloud-based alternatives
- File-based approaches (DXF, DWG generation libraries)
- Real-time vs. batch processing trade-offs
- Licensing and maintainability constraints

---

## Phase 1 Deliverables

- **Research vault** — Exhaustive documentation of official and community AutoCAD integration patterns
- **Regulatory vault** — Mexican electrical standards and compliance requirements
- **Architecture decision** — ADR-0001 recommending the optimal integration approach
- **Parametric model** — JSON/YAML schema for PV system input parameters and diagram generation data
- **v0.1.0-docs release** — Git tag on main branch with the ADR mirror and the Phase 1 research summary (the vault itself is not published)

---

## Contributing Documentation

When adding new documentation:

1. **For vault research:** Add pages to the Obsidian vault following `CLAUDE.md` conventions
2. **For architecture decisions:** Create a numbered ADR in `docs/decisions/`
3. **For API/code docs:** Use docstrings in code; major APIs should have supplementary `.md` guides
4. **Update `wiki/index.md`** after vault changes (or let the synthesis stage handle it)

See `CONTRIBUTING.md` for detailed workflow.

---

**Last updated:** 2026-10-05  
**Vault:** author's local Obsidian vault (not published)  
**Maintainer:** edu3250 (edu3250@gmail.com)
