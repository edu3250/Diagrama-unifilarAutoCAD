# Claude ↔ AutoCAD Unifilar Diagram Generator

## Project Vision

**Diagrama-unifilarAutoCAD** is an experimental system that combines Claude AI with Autodesk AutoCAD via the Model Context Protocol (MCP) to **automatically generate photovoltaic (PV) single-line electrical diagrams** compliant with Mexican regulatory standards.

The input is a set of solar installation parameters: capacity, inverters, strings, disconnects and protections. As decided in [ADR-0001](docs/decisions/ADR-0001-claude-autocad-integration.md), the system will:

- **Collect the parameters.** Claude, through MCP, elicits missing inputs, checks the design and explains any problems. It never draws geometry itself.
- **Compute and validate.** Deterministic code computes the engineering values and validates them against a versioned Mexican rule pack (NOM-001-SEDE-2012, CRE/CNE, CFE, UVIE) before anything is drawn.
- **Render.** The diagram is produced headlessly as DXF with a PNG preview. When the user's own AutoCAD 2027 is available, it can also be produced as native DWG and AutoCAD-plotted PDF.

## Current Status

**Phase 4: Symbol library:** Complete, released as `v0.4.0-symbols` (2026-10-08).
- 57 symbol blocks with ports and per-symbol sources, in `symbols/pvsld-symbols.dxf` and `.dwg`.
- The generator draws with them, on the owner's A3 sheet template (`a3_plantilla_v1`).

**Phase 3: Parametric sizing engine:** In progress.
- Done: the component catalogue (reviewed datasheet records), the sizing engine v1 (`pvsld size`) and, in Stage 3.5, the MCP tools that let Claude size and draw a system in one conversation.
- Next: completing the balance of system (Stage 3.4b) and the Claude Code plugin (Stage 3.6).

**Phase 2: MCP Server Prototype & Connectivity Spike:** Complete, released as `v0.2.0-spike` (2026-10-06). The spikes S1–S4 confirmed [ADR-0001](docs/decisions/ADR-0001-claude-autocad-integration.md): the exit gate passed and no reversal trigger fired. See the [Phase 2 spike review](docs/spikes/phase-2-review.md).

Phase 2 delivered:
- **S1:** an ezdxf DXF R2018 single-line diagram of a 7.70 kWp residential sample. It is byte-identical on Windows and Linux and audits 0/0 in ezdxf and in AutoCAD 2027.
- **S2:** an AutoCAD 2027 .NET 10 plug-in on a current-user named pipe, 186× faster than COM for drawing work.
- **S3:** a stdio MCP server that Claude Code drives (validate → generate in 2 tool calls).
- **S4:** a Core Console finisher for TrustedDWG 2018 and an AutoCAD-plotted PDF in ≤ 15 s per sheet.

**Phase 1: Documentation & Research:** Complete, released as `v0.1.0-docs` (2026-10-05).

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
| 2 | MCP Server Prototype & Connectivity Spike | Complete | v0.2.0-spike |
| 3 | Parametric PV Sizing Engine (complete rule pack, sizing engine) | To be defined (tentative scope in the plan) | v0.3.0-engine |
| 4 | Diagram Generation & Symbol Library | To be defined (tentative scope in the plan) | — |
| 5 | Validation & Packaging | To be defined (tentative scope in the plan) | v1.0.0 |

## Claude Code plugin (PvUnifilar)

The plugin [`pv-unifilar`](plugins/pv-unifilar/README.md) (shown as PvUnifilar) packages the MCP server with three Spanish skills: quick mode (`/pv-unifilar:diagrama`), professional mode with the Excel project sheet (`/pv-unifilar:pro`) and the local catalogue (`/pv-unifilar:catalogo`). It needs [uv](https://docs.astral.sh/uv/); AutoCAD is optional. Install it in Claude Code with:

```
/plugin install pv-unifilar --marketplace edu3250/Diagrama-unifilarAutoCAD
```

The marketplace (`pvsld`) is `.claude-plugin/marketplace.json`; the server runs with `uvx` from the release tag pinned in `plugins/pv-unifilar/.mcp.json`.

## Getting Started

### Prerequisites

The project is a Phase 2 prototype. The `pvsld` package validates a PV design, renders it to DXF with a PNG preview, and serves both steps to Claude over MCP. No package has been published yet.

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
pvsld validate examples/residential_7p7kwp.yaml
pvsld generate examples/residential_7p7kwp.yaml -o out/residential.dxf --png
pvsld size examples/sizing_jinko_growatt.yaml --include-unreviewed -o out/sized.yaml
```

**MCP server for Claude Code.** The repository's `.mcp.json` registers the stdio server `pvsld` (`pvsld-mcp`). Start Claude Code in the repository root and approve the project server once; `claude mcp list` should show `pvsld ... Connected`. The committed command only finds `pvsld-mcp` when the virtual environment is active in the shell that starts Claude Code. Otherwise, point the `PVSLD_MCP_COMMAND` variable at the venv executable before starting it:

```powershell
$env:PVSLD_MCP_COMMAND = "$PWD\.venv\Scripts\pvsld-mcp.exe"   # Linux/macOS: export PVSLD_MCP_COMMAND="$PWD/.venv/bin/pvsld-mcp"
claude
```

| Tool | What it does |
|---|---|
| `list_components` | Lists the reviewed catalogue: PV modules, string and hybrid inverters, DC breakers (filter by type or manufacturer) |
| `get_component` | Shows every datasheet value of one component, with its provenance (file, SHA-256, pages, reviewer) |
| `size_pv_system` | Sizes the strings, protection and conductors from the catalogue. Returns the selected design as a complete spec, ranked alternatives and the rejected configurations grouped by rule |
| `validate_pv_design` | Checks a spec against the rule pack `mx-gd-2026.10` |
| `generate_single_line_diagram` | Draws the validated spec as DXF on the A3 sheet, verifies it by reading it back and returns a PNG preview |

The server also publishes four resources:
- `pvsld://schema/pv-system-spec`: the spec JSON Schema.
- `pvsld://rulepack/mx-gd-2026.10`: the rule pack.
- `pvsld://symbols`: the symbol library.
- `pvsld://examples/sizing-template`: an example of the site, service and title-block sections a sizing request needs.

Environment variables:
- `PVSLD_OUTPUT_DIR`: where drawings go (default `out/`).
- `PVSLD_CATALOGUE_DIR`: the component records (default `datasheets/records`).

**Example: size a 10 kWp system in Guadalajara.** Ask Claude in Spanish, for example:

> Dimensiona un sistema de unos 10 kWp en Guadalajara con módulos ET Solar de 550 W y el inversor que mejor convenga del catálogo, y genera el diagrama.

Claude works through the tools in this order:
1. Calls `list_components` to find `ETSOLAR-ET-M672BH550`.
2. Reads `pvsld://examples/sizing-template` and asks for the site and service data it lacks.
3. Calls `size_pv_system` with `inverters: "auto"` and `target_dc_power_w: 10000`.

With the current catalogue the engine selects `GROWATT-MIN-6000TL-X2` 2 × 8 (8.80 kWp, DC/AC 1.47). The larger inverters are not in the catalogue yet, and every bigger configuration breaks STR-007 or VOLT-001. The engine reports the STR-007 warning and lists the alternatives (Huawei SUN2000-6KTL-L1 2 × 8, then 2 × 7). After the user accepts, Claude calls `validate_pv_design` and `generate_single_line_diagram` with the returned spec. The result is the DXF on the A3 sheet plus a preview. A sizing result stays around 3k tokens, well under the 25k cap of a Claude Code tool result.

Claude Desktop set-up and details: [`docs/spikes/s3-mcp-round-trip.md`](docs/spikes/s3-mcp-round-trip.md).

**DWG and PDF (optional, licensed AutoCAD 2027 on Windows).** `pvsld finish out/residential.dxf` converts a DXF to DWG 2018 and an A3 PDF through the AutoCAD Core Console ([`docs/spikes/s4-core-console.md`](docs/spikes/s4-core-console.md)). Output paths must be ASCII for now. A DWG records the Windows login as "last saved by", so check it before sharing.

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
- **[`docs/spikes/`](docs/spikes/)** — Phase 2 spike reports (S2–S4) and the [Phase 2 spike review](docs/spikes/phase-2-review.md)
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

**Last updated:** 2026-10-06
