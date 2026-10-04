# Claude ↔ AutoCAD Unifilar Diagram Generator

## Project Vision

**Diagrama-unifilarAutoCAD** is an experimental system that combines Claude AI with Autodesk AutoCAD via the Model Context Protocol (MCP) to **automatically generate photovoltaic (PV) single-line electrical diagrams** compliant with Mexican regulatory standards.

Given a set of solar installation parameters (capacity, inverters, strings, disconnects, protections), the system will:

- Translate electrical specifications into parametric diagram data
- Invoke Claude via MCP to reason about optimal single-line topology
- Render the diagram into AutoCAD format (.dwg)
- Validate compliance with Mexican norms (NOM-001-SEDE, CRE, CFE, UVIE)

## Current Status

**Phase 1: Documentation & Research** — In Progress

This phase focuses on exhaustive research into:
- Official Autodesk APIs and MCP connectivity patterns
- Existing open-source community integrations (GitHub survey)
- Mexican electrical regulatory requirements for distributed generation
- PV single-line diagram best practices and symbology

All research is documented in the **Obsidian vault** at:
```
D:\Obsidian\Claude-AutoCAD unifilar
```

See the vault's `wiki/index.md` for the current knowledge base status.

## Roadmap

| Phase | Name | Status | Target |
|-------|------|--------|--------|
| 1 | Documentation & Regulatory Research | In Progress | v0.1.0-docs |
| 2 | MCP Server Prototype & Connectivity Spike | To be defined | — |
| 3 | Parametric PV Sizing Engine | To be defined | — |
| 4 | Diagram Generation & Symbol Library | To be defined | — |
| 5 | Validation & Packaging | To be defined | — |

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+ (if using MCP server in TypeScript)
- AutoCAD 2020+ (or compatible .dwg processor)
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
- **`docs/README.md`** — Technical documentation structure
- **`CONTRIBUTING.md`** — GitFlow workflow and commit conventions
- **`CHANGELOG.md`** — Version history (Keep a Changelog format)
- **Obsidian Vault** — Knowledge base, research notes, and decisions

## License

MIT License — see `LICENSE` file.

## Contact & Contributions

Maintainer: edu3250 (edu3250@gmail.com)

Contributions welcome! Please follow `CONTRIBUTING.md` before submitting pull requests.

---

**Last updated:** 2026-10-04
