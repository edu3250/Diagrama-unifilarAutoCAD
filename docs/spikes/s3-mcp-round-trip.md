# Spike S3: MCP Round Trip from Claude Code

| Field | Value |
|---|---|
| Stage | Phase 2, Stage 2.3 (spike S3 of [ADR-0001](../decisions/ADR-0001-claude-autocad-integration.md)) |
| Date | 2026-10-06 |
| Branch | `feature/s3-mcp-server`, built on S1 (`feature/s1-ezdxf-minimal`, PR #3) |
| Code | `src/pvsld/mcp/`, `.mcp.json`, console script `pvsld-mcp` |
| Tests | `tests/test_mcp_*.py` (135 cases: in-memory client, real stdio subprocess, sandbox, preview) |
| Vault note | `wiki/sources/Spike S3 Results 2026-10.md` (author's local vault) |

> **Update (2026-10-06, Stage 2.5).** The owner closed the model-in-the-loop check with a manual Claude Code run (2.1.291). Validate → generate took 2 calls, and the VOLT-001 self-correction took 4, so both criteria are met. The MCP Inspector session is still not run (no Node.js). Pillow is now a declared dependency (`5fdddb4`). See [`phase-2-review.md`](phase-2-review.md).

## Result in one paragraph

A stdio MCP server on the official Python SDK (`mcp` 2.3.0) exposes the two workflow tools of ADR-0001, `validate_pv_design` and `generate_single_line_diagram`, and three resources (parameter JSON Schema, rule-pack catalogue, symbol catalogue). Claude Code 2.1.150 registers it from the repo `.mcp.json` and reports it connected. The server starts and lists its tools in 2.0 to 2.6 s (the criterion is under 5 s). A spec with 12 modules per string comes back from both tools with VOLT-001 findings that name the limit ("máximo 11 módulos"); the generator turns it into a tool error and writes nothing. **Two criteria could not be measured and are marked pending: the model-in-the-loop run (the `claude` CLI on this workstation has an expired login, so a headless run is not possible without an interactive sign-in) and the MCP Inspector session (no Node.js).** Exact instructions to close both are in [Manual checks](#manual-checks-pending-owner).

## Results against the Stage 2.3 criteria

| Criterion | Measured | Result |
|---|---|---|
| Server starts and lists tools in < 5 s | 10 runs of a real `python -m pvsld.mcp` subprocess driven by the SDK stdio client (spawn, initialize, `tools/list`): min 2.01 s, median 2.12 s, max 2.59 s. `claude mcp list` (Claude Code's own health check, includes its start-up) took 4.1 s wall and reports "Connected" | met |
| Claude Code registers the server from `.mcp.json` | `claude mcp get pvsld`: scope "Project config (shared via .mcp.json)", stdio, "Connected" | met |
| Claude completes validate → generate on the sample in ≤ 4 tool calls | Scripted client over real stdio: 2 calls (validate, generate). Model-in-the-loop run not possible | **pending: manual check by the owner** |
| Result (drawing_id, DXF path, PNG preview) stays under the 25k-token cap | Generate with preview: 83,670 characters serialised, about 20.9k tokens at the conservative 4 characters per token (the PNG is 81,224 of them as base64). Without preview: 1,849 characters (about 460 tokens). Validate: 2,258 characters | met by the chars/4 estimate; host counting of base64 to be confirmed in the manual check |
| A 12-module spec returns VOLT-001 and Claude corrects it | Validate returns two `error` findings (VOLT-001, S1 and S2) with the Spanish message, MX-C02 and the NOM 690-7(a) citation; generate refuses with `is_error` and the same findings and writes nothing. A scripted fix (7 modules) then validates and generates the golden file: 3 calls (validate, validate, generate). The model correcting it is not measured | tool error met; Claude correcting it **pending: manual check** |
| In-memory MCP client tests in CI | 135 test cases in `tests/test_mcp_*.py`; whole suite 469 passed, 2 skipped, coverage 97 % (floor 60 %), ruff clean | met |
| MCP Inspector session | Needs Node.js 22.19+, not installed | **pending: manual check** |
| Optional: same flow in Claude Desktop within 240 s | Not run (generate takes 0.2 s without and 1 to 2 s with the preview, so the budget is not a concern) | not run |

Sample numbers behind the table (this workstation, Windows 11, Python 3.11.9, warm process):

| Call | Server time | Result characters | About tokens (chars / 4) |
|---|---|---|---|
| `validate_pv_design`, sample (ok) | 5 ms | 2,258 | 564 |
| `validate_pv_design`, 12 modules (2 errors) | 99 ms first call | 3,445 | 861 |
| `generate_single_line_diagram`, 12 modules (refused) | 7 ms | 2,079 | 520 |
| `generate_single_line_diagram`, sample, no preview | 186 ms | 1,849 | 462 |
| `generate_single_line_diagram`, sample, with preview | 1.1 to 1.9 s (PNG about 0.65 s warm; the first call also imports matplotlib) | 83,670 | 20,918 |

The DXF written through the server is byte-identical to the golden file of S1 (SHA-256 `05717887de0ea4cef518b635345bed6b996d0481fcaacb6803b1bf12792bdc91`).

## What the server exposes

Tools (workflow level; there is no primitive drawing tool and no code execution):

| Tool | Annotations | Input | Output |
|---|---|---|---|
| `validate_pv_design` | read-only, idempotent, closed world | `spec` (the whole parameter object) | `ok`, `summary`, `findings[]` (`rule_id`, `severity`, `subject`, `message_es`, `mx_ids`, `cites`; errors first, at most 50), `derived` (kWp, kWac, string Voc at T_min, voltage drop and ampacity per circuit), `next_step` |
| `generate_single_line_diagram` | not read-only, not destructive, idempotent, closed world | `spec`; optional `name`, `overwrite` (default false), `preview` (default true) | `drawing_id`, `dxf_path`, `png_path`, `sha256`, `size_bytes`, `unchanged`, `readback` (audit, INSERT counts, attribute round trip, dangling ports, layer 0), `timings_ms`, `next_step`, plus a PNG image block |

Resources: `pvsld://schema/pv-system-spec` (JSON Schema 2020-12, about 25 kB), `pvsld://rulepack/mx-gd-2026.10`, `pvsld://symbols`. Server `instructions` carry the workflow ("validate first", "never invent equipment data", "explain in Spanish").

How the contract keeps Claude on the rails:

- **Findings are a normal result, not an error, in `validate_pv_design`;** an invalid spec in `generate_single_line_diagram` is a tool error (`is_error`) whose text and structured content carry the same findings, so the model can fix the spec. Both put the findings in the text content too, for hosts that show only text.
- **The sandbox.** A call carries a *name*, never a path. Files go to `PVSLD_OUTPUT_DIR` (or `--output-dir`, default `./out` of the server's working directory). Names must match `[A-Za-z0-9_-]{1,64}` and must not be a Windows device name (`CON`, `NUL`, ...); a name that does not is refused, not rewritten. Output is staged in a private folder inside the root and moved into place, so a crash or a failed read-back never leaves a half-written or unverified drawing. Replacing a file that has different content needs `overwrite=true`; identical content is reported as `unchanged`.
- **`drawing_id`** is `<name>-<first 8 hex of the DXF SHA-256>`: stateless, names the file, and changes when the content does.
- **Preview.** The 100 dpi A3 PNG (401 kB) stays on disk next to the DXF. The copy attached to the result is shrunk to at most 62,000 bytes (900 x 636 px, 8 colours, 59 KiB for the sample) so the whole result stays below 25k tokens by the 4 characters per token estimate. `PVSLD_PREVIEW_MAX_BYTES` lowers or raises that budget without a code change.
- **Logging** goes to stderr only, one line per call with the tool name, duration and outcome; the spec (names, phone, RPU) and the findings are never logged.

## Registering the server

### Claude Code (committed `.mcp.json`)

```json
{
  "mcpServers": {
    "pvsld": {
      "type": "stdio",
      "command": "${PVSLD_MCP_COMMAND:-pvsld-mcp}",
      "args": [],
      "env": {
        "PYTHONUTF8": "1",
        "PVSLD_OUTPUT_DIR": "${PVSLD_OUTPUT_DIR:-out}"
      }
    }
  }
}
```

From a fresh clone:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1          # puts pvsld-mcp.exe on PATH
pip install -e ".[dev]"
claude                              # start Claude Code in the repo root, approve the project server once
claude mcp list                     # pvsld: pvsld-mcp - Connected
```

**The venv-absolute-path caveat.** `pvsld-mcp` is found through `PATH`, so Claude Code must be started from a shell where the environment that holds `pvsld` is active (or where `pvsld` is installed globally). Without that, Claude Code reports "Failed to connect" (verified: `pvsld: pvsld-mcp - ✗ Failed to connect`). A committed file cannot hold the absolute path of one machine's venv, so the command is an environment expansion with a default (`${VAR:-default}` works in `command` and `env` in Claude Code 2.1.150, verified with `claude mcp get`). To use an absolute path without editing the file, set the variable before starting Claude Code:

```powershell
$env:PVSLD_MCP_COMMAND = "D:\path\to\repo\.venv\Scripts\pvsld-mcp.exe"   # verified: "Connected"
```

or register it privately instead of using the shared file: `claude mcp add --scope user pvsld -e PYTHONUTF8=1 -e PVSLD_OUTPUT_DIR=C:\Users\me\Documents\pvsld -- D:\path\to\repo\.venv\Scripts\pvsld-mcp.exe`.

Verified facts about Claude Code 2.1.150 on this workstation: it starts the stdio server with the **project directory as working directory** (a probe server recorded `D:\DataScience\pvsld-s3`), so the default `out` is the repo's git-ignored `out/`; and it expands `${PVSLD_OUTPUT_DIR:-out}` from its own environment, which lets a run point at a fresh folder.

### Claude Desktop

Edit `%APPDATA%\Claude\claude_desktop_config.json` (Settings > Developer > Edit Config; a Microsoft Store install may use `%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json`) and restart Desktop completely:

```json
{
  "mcpServers": {
    "pvsld": {
      "command": "D:\\path\\to\\repo\\.venv\\Scripts\\pvsld-mcp.exe",
      "args": [],
      "env": {
        "PYTHONUTF8": "1",
        "PVSLD_OUTPUT_DIR": "C:\\Users\\me\\Documents\\pvsld"
      }
    }
  }
}
```

Use absolute paths for both. Desktop does not start the server in a project folder, so a relative `PVSLD_OUTPUT_DIR` would land in an arbitrary directory. Logs are in `%APPDATA%\Claude\logs\mcp-server-pvsld.log`. Not tested in this spike (no Claude Desktop run).

## Manual checks pending (owner)

### 1. Model in the loop (criteria: at most 4 tool calls, VOLT-001 self-correction, 25k-token cap)

The `claude` CLI is on PATH (2.1.150) but its login has expired: a headless run ended with `API Error: 401 OAuth access token has expired. Re-authenticate to continue.` Signing in is interactive and was not attempted.

```powershell
claude                                  # once, /login if asked, then /exit
cd D:\path\to\repo ; .venv\Scripts\Activate.ps1
New-Item -ItemType Directory -Force out\check | Out-Null
(Get-Content examples\residential_7p7kwp.yaml) -replace 'n_series: 7', 'n_series: 12' |
  Set-Content out\check\bad_12_modules.yaml

$tools = "mcp__pvsld__validate_pv_design,mcp__pvsld__generate_single_line_diagram"

# Run A: valid sample. Expect 2 pvsld calls (validate, generate).
$env:PVSLD_OUTPUT_DIR = "$PWD\out\check\a"
claude -p "Use the pvsld MCP server to validate the PV design in examples/residential_7p7kwp.yaml. If it is invalid, fix the design and validate again. Then generate the single-line diagram and tell me where the files are." `
  --mcp-config .mcp.json --strict-mcp-config --allowedTools $tools --output-format stream-json --verbose > out\check\a.jsonl

# Run B: 12 modules per string. Expect validate (VOLT-001), validate (ok), generate = 3 calls.
$env:PVSLD_OUTPUT_DIR = "$PWD\out\check\b"
claude -p "Use the pvsld MCP server to validate the PV design in out/check/bad_12_modules.yaml. If it is invalid, fix the design and validate again. Then generate the single-line diagram and tell me where the files are." `
  --mcp-config .mcp.json --strict-mcp-config --allowedTools $tools --output-format stream-json --verbose > out\check\b.jsonl

# Count tool calls by name (pvsld calls are what the criterion counts; Read and ToolSearch are Claude Code's own)
python -c "import json,sys,collections; c=collections.Counter(b['name'] for l in open(sys.argv[1],encoding='utf-8') for m in [json.loads(l)] if m.get('type')=='assistant' for b in m['message']['content'] if b.get('type')=='tool_use'); print(dict(c))" out\check\a.jsonl
```

Pass: at most 4 `mcp__pvsld__*` calls in each run, the last `generate_single_line_diagram` has no error, `out\check\a\PV-2026-0001.dxf` exists, and no "MCP tool output exceeds" message appears. Expect Claude Code to add a `ToolSearch` call (it defers MCP tool definitions) and a `Read` call; record those separately. If the output-size message appears, lower the preview budget (`PVSLD_PREVIEW_MAX_BYTES`, for example `30000`, in the `env` block) or call with `preview` false and report the result here.

### 2. MCP Inspector

```powershell
npx @modelcontextprotocol/inspector .venv\Scripts\pvsld-mcp.exe      # needs Node.js 22.19+
```

Check that both tools list with their schemas, that `validate_pv_design` accepts the sample (paste it as JSON), and that the three resources read.

### 3. Optional: Claude Desktop

Register the snippet above, restart Desktop, ask for the same two runs and confirm each call finishes well inside 240 s.

## Findings

1. **`mcp` 2.3.0 matches the vault's notes, with details that matter.** `from mcp.server import MCPServer`; `Client(server)` is the in-memory client (`client.instructions` is a property, not a coroutine). A tool annotated `Annotated[CallToolResult, Model]` gets an `outputSchema` from `Model` *and* may return `CallToolResult(is_error=True, structured_content=...)`: output validation is skipped for errors, which is how the generator returns findings in a tool error. A bare `ToolError` carries text only, prefixed with "Error executing tool <name>:". Arguments that fail the input schema come back as `is_error` results, not protocol errors.
2. **`MCPServer.__init__` calls `logging.basicConfig` with a Rich handler on stderr.** `main()` configures logging with `force=True` first so the audit format wins, and `ezdxf` is set to WARNING because its drawing add-on logs one INFO line per hidden attribute (hundreds per preview).
3. **The core is not re-entrant.** `fixed_metadata` pins a process-global ezdxf option, and the SDK runs sync tools on worker threads, so generation is serialised with a lock (tested with three concurrent calls).
4. **The sandbox needs to handle Windows.** `Path.replace` onto a DXF that is open in AutoCAD fails with `PermissionError`; the server returns an actionable tool error ("close it in AutoCAD") and leaves nothing behind. A failure to save only the full-resolution PNG does not fail the drawing.
5. **The preview does not fit a result as it is.** The 100 dpi PNG is 401 kB (about 535k base64 characters). Pillow (already installed as a hard dependency of matplotlib) downsizes it to a palette PNG: 1000 px is 82 kB, 900 px at 16 colours 69 kB, 900 px at 8 colours 61 kB. The ladder keeps the widest candidate that fits the budget. Legibility at 900 px is good enough for a layout check; small table text is borderline.
6. **The wire is UTF-8 without help.** A raw subprocess test without `PYTHONUTF8` shows "máximo 11 módulos" intact in a `tools/call` response, and every stdout line is a JSON-RPC frame. `.mcp.json` still sets `PYTHONUTF8=1` as the vault checklist advises.
7. **The server is cheap to start.** Import of the MCP SDK takes about 1.6 s and ezdxf about 0.5 s of the 2.0 to 2.6 s; matplotlib and Pillow are imported only when a preview is made.
8. **Claude Code spawns the configured MCP servers before it calls the model.** With the expired login, `claude -p --mcp-config` still started a probe server (it wrote its working directory) before the 401, which made the working-directory and expansion checks possible without a model.

## Open items

- Close the two pending manual checks above; then update the Stage 2.3 status and the spike S3 line of the ADR-0001 exit gate.
- Confirm how Claude Code counts the base64 image against the 25k-token cap; the budget knob is `PVSLD_PREVIEW_MAX_BYTES`.
- Every call carries the whole spec (about 6 to 8 kB of JSON), twice per session. A `spec_id` handle returned by validate and accepted by generate would cut that, at the price of server state that the stateless MCP spec of 2026-07-28 discourages. Deferred.
- A `pvsld://examples/...` resource with a complete valid spec would help Claude build one from datasheets. `examples/` is not part of the wheel, so this needs a packaging decision (S1 owner).
- The server calls Pillow through matplotlib's hard dependency; declaring `pillow` in `pyproject.toml` would be cleaner but `tests/test_project_metadata.py` pins the exact dependency set.
- Index this page from `docs/README.md` and add the changelog and README entries (not touched here).
- Later surface of ADR-0001: `export_drawing`, `get_diagram_summary` (`drawing_id` already encodes the file name).

## Reproduce

```powershell
python -m venv .venv ; .venv\Scripts\Activate.ps1 ; pip install -e ".[dev]"
ruff check . ; ruff format --check . ; pytest --cov
pvsld-mcp --version ; pvsld-mcp --help
claude mcp list
```
