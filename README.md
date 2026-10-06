# Claude ↔ AutoCAD Unifilar Diagram Generator

## Project Vision

**Diagrama-unifilarAutoCAD** is an experimental system that combines Claude AI with Autodesk AutoCAD via the Model Context Protocol (MCP) to **automatically generate photovoltaic (PV) single-line electrical diagrams** compliant with Mexican regulatory standards.

The input is a set of solar installation parameters: capacity, inverters, strings, disconnects and protections. As decided in [ADR-0001](docs/decisions/ADR-0001-claude-autocad-integration.md), the system will:

- **Collect the parameters.** Claude, through MCP, elicits missing inputs, checks the design and explains any problems. It never draws geometry itself.
- **Compute and validate.** Deterministic code computes the engineering values and validates them against a versioned Mexican rule pack (NOM-001-SEDE-2012, CRE/CNE, CFE, UVIE) before anything is drawn.
- **Render.** The diagram is produced headlessly as DXF with a PNG preview. When the user's own AutoCAD 2027 is available, it can also be produced as native DWG and AutoCAD-plotted PDF.

## Current Status

**Phase 1: Documentation & Research:** Complete, released as `v0.1.0-docs` (2026-10-05). Phase 2 (trial-and-error spikes S1–S4 from ADR-0001) is drafted and awaits the owner's confirmation.

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
| 1 | Documentation & Regulatory Research | Complete | v0.1.0-docs |
| 2 | MCP Server Prototype & Connectivity Spike | Tentative: spikes S1–S4 from ADR-0001, to be confirmed | v0.2.0-spike |
| 3 | Parametric PV Sizing Engine | To be defined | — |
| 4 | Diagram Generation & Symbol Library | To be defined | — |
| 5 | Validation & Packaging | To be defined | — |

## Getting Started

### Prerequisites

The project is in its Phase 2 prototype: a Python package scaffold exists (`pvsld`), but no release has been published yet.

- Python 3.11+ (for the MCP server and the deterministic core)
- Optional: AutoCAD 2027 on Windows, needed only for native DWG output, AutoCAD PDF plotting and live editing
- Git (GitFlow compatible)

### Development setup

```bash
# Clone and start from the integration branch
git clone https://github.com/edu3250/Diagrama-unifilarAutoCAD.git
cd Diagrama-unifilarAutoCAD
git checkout develop

# Create a feature branch for your work
git flow feature start <name>
# or manually: git checkout -b feature/<name>
```

Create a virtual environment in the repository and activate it:

```bash
python -m venv .venv
```

| Shell | Activate |
|-------|----------|
| Windows PowerShell | `.venv\Scripts\Activate.ps1` |
| Windows cmd | `.venv\Scripts\activate.bat` |
| Git Bash on Windows | `source .venv/Scripts/activate` |
| Linux / macOS | `source .venv/bin/activate` |

> If PowerShell refuses to run `Activate.ps1`, allow scripts for the current session only: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned`.

Install the package in editable mode with the development tools, then run the checks that CI runs:

```bash
pip install -e ".[dev]"

ruff check .             # lint
ruff format --check .    # formatting (run `ruff format .` to fix)
pytest --cov             # tests with coverage (floor: 60 %)

pvsld --version
pvsld validate-example examples/residential_7p7kwp.yaml
```

**AutoCAD tests.** Tests marked `autocad` drive a licensed local AutoCAD 2027 and only run on Windows. A plain `pytest` (and CI) reports them as *skipped*, with the reason shown. On the licensed workstation, with AutoCAD 2027 installed, run them explicitly and add the optional `autocad` extra (`pywin32`):

```bash
pip install -e ".[dev,autocad]"
pytest --run-autocad -m autocad
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
