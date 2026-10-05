# Claude ↔ AutoCAD Unifilar Diagram Generator

## Project Vision

**Diagrama-unifilarAutoCAD** is an experimental system that combines Claude AI with Autodesk AutoCAD via the Model Context Protocol (MCP) to **automatically generate photovoltaic (PV) single-line electrical diagrams** compliant with Mexican regulatory standards.

The input is a set of solar installation parameters: capacity, inverters, strings, disconnects and protections. As decided in [ADR-0001](docs/decisions/ADR-0001-claude-autocad-integration.md), the system will:

- **Collect the parameters.** Claude, through MCP, elicits missing inputs, checks the design and explains any problems. It never draws geometry itself.
- **Compute and validate.** Deterministic code computes the engineering values and validates them against a versioned Mexican rule pack (NOM-001-SEDE-2012, CRE/CNE, CFE, UVIE) before anything is drawn.
- **Render.** The diagram is produced headlessly as DXF with a PNG preview. When the user's own AutoCAD 2027 is available, it can also be produced as native DWG and AutoCAD-plotted PDF.

## Current Status

**Phase 1: Documentation & Research:** Stages 1.1–1.6 are complete. Stage 1.7 (vault lint, Phase 1 review, release `v0.1.0-docs`) is in progress.

Phase 1 researched:
- Official Autodesk APIs and MCP connectivity patterns
- Existing open-source community integrations (GitHub survey)
- Mexican electrical regulatory requirements for distributed generation
- PV single-line diagram best practices, symbology and a parametric model

Key outputs:
- **[ADR-0001: Claude ↔ AutoCAD Integration Approach](docs/decisions/ADR-0001-claude-autocad-integration.md)** (accepted 2026-10-05). It adopts a layered hybrid: a Python stdio MCP server; a deterministic core (parameter model → calculations → rule pack → diagram model); an ezdxf DXF backend first and an AutoCAD 2027 .NET 10 plug-in backend second.
- **[Phase 1 research summary](docs/research/phase-1-summary.md):** key findings per domain, open questions and a map of the vault.

The full research (252 notes with cited sources) lives in the author's local Obsidian research vault (not part of this repository). Start at the vault's `wiki/index.md`. The vault holds the working original of each ADR (`wiki/decisions/`); `docs/decisions/` is the published mirror, regenerated from the vault when they differ.

## Roadmap

| Phase | Name | Status | Target |
|-------|------|--------|--------|
| 1 | Documentation & Regulatory Research | In Progress (Stages 1.1–1.6 complete; 1.7 in progress) | v0.1.0-docs |
| 2 | MCP Server Prototype & Connectivity Spike | Tentative: spikes S1–S4 from ADR-0001, to be confirmed | v0.2.0-spike |
| 3 | Parametric PV Sizing Engine | To be defined | — |
| 4 | Diagram Generation & Symbol Library | To be defined | — |
| 5 | Validation & Packaging | To be defined | — |

## Getting Started

### Prerequisites

Planned, per ADR-0001; no code has been released yet.

- Python 3.10+ (for the MCP server and the deterministic core)
- Optional: AutoCAD 2027 on Windows, needed only for native DWG output, AutoCAD PDF plotting and live editing
- Git (GitFlow compatible)

### Development

```bash
# Clone and set up
git clone https://github.com/edu3250/Diagrama-unifilarAutoCAD.git
cd Diagrama-unifilarAutoCAD
git checkout develop

# Create a feature branch for your work
git flow feature start <name>
# or manually: git checkout -b feature/<name>
```

See `CONTRIBUTING.md` for detailed GitFlow instructions and `IMPLEMENTATION_PLAN.md` for current stage details.

## Documentation

- **`IMPLEMENTATION_PLAN.md`** — Staged breakdown of work for each phase
- **[`docs/decisions/`](docs/decisions/)** — Architecture Decision Records, starting with [ADR-0001](docs/decisions/ADR-0001-claude-autocad-integration.md)
- **[`docs/research/`](docs/research/)** — Research summaries, starting with the [Phase 1 summary](docs/research/phase-1-summary.md)
- **`docs/README.md`** — Technical documentation structure
- **`CONTRIBUTING.md`** — GitFlow workflow and commit conventions
- **`CHANGELOG.md`** — Version history (Keep a Changelog format)
- **Obsidian vault** (the author's local Obsidian research vault (not part of this repository)) — Full knowledge base: cited research notes, comparisons, and the vault originals of the ADRs

## License

MIT License — see `LICENSE` file.

## Contact & Contributions

Maintainer: edu3250 (edu3250@gmail.com)

Contributions welcome! Please follow `CONTRIBUTING.md` before submitting pull requests.

---

**Last updated:** 2026-10-05
