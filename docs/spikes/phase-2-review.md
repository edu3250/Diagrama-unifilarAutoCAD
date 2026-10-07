# Phase 2 Spike Review (Stage 2.5)

| Field | Value |
|---|---|
| Stage | Phase 2, Stage 2.5 ([`IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md)) |
| Decision under review | [ADR-0001](../decisions/ADR-0001-claude-autocad-integration.md): exit gate and reversal triggers T1–T9 |
| Date | 2026-10-06 |
| Evidence | Spike reports [S2](s2-autocad-connectivity.md), [S3](s3-mcp-round-trip.md), [S4](s4-core-console.md); S1 in PR #3 and the vault note "Spike S1 Results 2026-10"; PR #7 (AUDIT fix); the owner's manual Claude Code run of 2026-10-06 |
| Merged pull requests | #1 foundation (2.0), #3 S1 (2.1), #2 S2 (2.2), #4 ADR-0003, #5 S3 (2.3), #6 S4 (2.4), #7 AUDIT fix |
| Vault note | `wiki/sources/Phase 2 Spike Review 2026-10.md` (author's local vault) |

## Verdict

**ADR-0001 is confirmed.** S1 and S3 meet their criteria, and S2 shows that the .NET 10 plug-in meets every reliability criterion, with wide margins. S4, which is outside the gate, also passes. No reversal trigger fired. Two items deviate from the letter of the plan, and neither changes the decision:

- **The S1 AutoCAD AUDIT failed first.** It found 2 errors, because S1 had moved the overall paper-space viewport off layer `0`. PR #7 fixed this, and AUDIT now reports 0 errors and 0 fixes.
- **The S3 MCP Inspector session was not run,** because Node.js is not installed. Other checks cover what the session would show:
  - in-memory and real stdio client tests list the tools and their schemas and read all three resources;
  - Claude Code reports the server as connected;
  - the owner ran the server with a real model.

  The Inspector session stays an open item.

ADR-0001 keeps its status (accepted; vault status `active`). A "Phase 2 validation (2026-10-06)" section is appended to the ADR (repository mirror and vault original). The original decision text is unchanged.

## Results per stage against the criteria

| Stage / spike | Criterion | Measured | Result |
|---|---|---|---|
| 2.0 Foundation (#1) | Scaffold, tooling, CI on Windows and Ubuntu | CI green on Ubuntu and Windows with Python 3.11 and 3.12 | met |
| 2.1 S1 ezdxf (#3) | `doc.audit()` 0 errors, 0 fixes | 0 / 0, measured on the document re-read from the written bytes | met |
| | Byte-identical across runs and across Windows and Linux | Same SHA-256 across runs, 12 `PYTHONHASHSEED` values, Python 3.11 and 3.13, and the Windows/Linux CI matrix. The golden file changed once, by design, in #7 | met |
| | INSERT counts, attribute round trip by `COMP_ID`, ports, layer `0` | 9 blocks and 11 inserts; 147 of 147 attributes; 0 dangling ports of 18; 0 drawing entities on layer `0`. Since #7, the overall paper-space viewport is the one allowed exception (ADR-0003) | met |
| | Build + write ≤ 1 s; PNG preview ≤ 3 s | median 97 ms; about 1.1 s cold | met |
| | Rule subset passes on the sample and fails on 3 mutated specs | Sample: 0 findings. More than 10 mutations fail the expected rule, including 12 modules per string (VOLT-001) | met |
| | DXF opens in AutoCAD 2027 and AUDIT reports 0 errors | S4 (Core Console 2027) found **2 errors, 0 fixed**: `AcDbViewport(123) Paperspace vport layer Not "0"`. **After #7: 0 errors, 0 fixed** | met after fix |
| 2.2 S2 plug-in vs COM (#2) | ping p95 < 50 ms | 2.25 ms through AutoCAD's main thread | met |
| | 200 inserts + 200 lines < 2 s; COM ratio recorded | 47.3 ms p50, 71.4 ms max; COM 8.8 s (185.6×) | met |
| | 100/100 runs without unhandled errors | 100/100 | met |
| | "Busy" error within 5 s with a modal dialog or active command; AutoCAD never hangs | 0.001 s (modal dialog), 0.54 s (`DELAY`), 1.89 s (`LINE` waiting for input) | met |
| | Injected mid-transaction failure leaves the drawing unchanged | 5 of 5 rolled back | met |
| | Client without the secret refused; pipe ACL current user only | refused (-32001); DACL deny NETWORK, allow current user | met |
| 2.3 S3 MCP round trip (#5) | Server starts and lists tools in < 5 s | 2.01–2.59 s (median 2.12 s, 10 runs); `claude mcp list` 4.1 s | met |
| | Registered through the repo `.mcp.json` | Claude Code: project scope, stdio, "Connected" | met (needs `PVSLD_MCP_COMMAND` or an active venv; see findings) |
| | Claude completes validate → generate in ≤ 4 tool calls | **Owner's manual run** (Claude Code 2.1.291, server at `bd426a5`): 2 calls (validate, generate) | met |
| | Result stays under the 25k-token cap | 83,670 characters with the preview (about 20.9k tokens at 4 characters per token); 1,849 without it. In the owner's run, Claude received and read the preview PNG; no output-cap problem was recorded | met (by estimate; margin about 16 %) |
| | 12 modules per string returns VOLT-001 and Claude corrects it | Generate refused and wrote nothing (VOLT-001 on S1 and S2: 640.2 V at −3 °C against 600 V, "máximo 11 módulos"). Claude corrected the spec and generated in 4 calls | met |
| | In-memory client tests in CI | 135 MCP test cases; whole suite green | met |
| | MCP Inspector session | Not run: needs Node.js 22.19+ | **not run** (open item) |
| | Optional: Claude Desktop within 240 s | Not run | not run (optional) |
| 2.4 S4 Core Console (#6) | DWG 2018 without the "not saved by Autodesk" notice | `AC1032`; TrustedDWG sentence in the file; re-opens in Core Console without a notice. The GUI balloon was not checked | met |
| | PDF produced | 1 page, A3 landscape (420.2 × 297.0 mm), plotted by AutoCAD | met |
| | ≤ 15 s per sheet | 4.2–10.8 s (warm median 4.9 s); 12.2 s on the cold run after #7 | met |
| | Running outside a licensed session gives a reported error, never a silent success | 4 of 4 real failure modes were reported; the silent exit is covered by the CI fake. **A real unlicensed run was not reproduced** | met (unlicensed case simulated) |
| AUDIT fix (#7) | AutoCAD AUDIT of the S1 DXF reports 0 errors | Core Console 2027: **0 errors, 0 fixed**; DWG `AC1032` TrustedDWG; one-page A3 PDF; 12.2 s cold. Canonical paper `ISO_full_bleed_A3_(420.00_x_297.00_MM)`. 659 passed, 30 skipped (autocad) | met |
| Manual Claude test (owner) | Model in the loop, criteria of S3 | Test 1: 2 calls. Test 2: 4 calls with self-correction. Claude also noticed a DC-power overload that no implemented rule caught (finding 1) | met; found a rule-pack gap |

## ADR-0001 exit gate

The gate is: "The ADR stands if S1 and S3 meet their criteria and S2 shows the plug-in meets its reliability criteria."

| Gate part | Evaluation | Outcome |
|---|---|---|
| S1 meets its criteria | Every criterion met. The AutoCAD AUDIT met it after a backend fix (#7); the defect was our layer choice, not an ezdxf limitation | **pass** |
| S3 meets its criteria | Start-up, registration, call count, token cap, VOLT-001 correction and CI tests all met. MCP Inspector not run (tooling missing); its checks are covered by other tests | **pass**, with one recorded deviation |
| S2 plug-in reliability | Every criterion met by one to three orders of magnitude | **pass** |
| S4 (outside the gate) | Every Stage 2.4 criterion met | pass |

**Verdict: the gate is passed. ADR-0001 is confirmed, and no superseding ADR is needed.**

## Reversal triggers

| # | Trigger | Status | Evidence |
|---|---|---|---|
| T1 | Autodesk opens its AutoCAD MCP server to third-party clients and adds creation tools | **not fired** | As of the Phase 1 research (2026-10-04), the server is Assistant-only and cannot insert blocks or plot. Phase 2 did not re-check it; it stays a watch item (A1) |
| T2 | S1 fails: AutoCAD AUDIT rejects ezdxf DXF, or a required feature cannot be expressed | **not fired** | The first AUDIT reported 2 errors. Both came from one viewport placed on the wrong layer by our own code, and a one-line change fixed them (#7: 0/0). Every required SLD feature was expressible: attributed blocks, XDATA ports, layers, A3 layout and tables |
| T3 | CFE, UVIE or inspection units reject DXF or ezdxf PDF, or demand DWG | **not fired (untested)** | No reviewer has been asked yet (open item Z1). If it fires, S4 has already proven the response: the Core Console finisher gives TrustedDWG and an AutoCAD PDF in ≤ 15 s |
| T4 | Plug-in friction is prohibitive while COM coarse operations are equally reliable | **not fired** | COM is 37–186× slower for drawing work. It saw 119 `RPC_E_CALL_REJECTED` rejections and can only report "busy" after its 5 s retry budget. The plug-in's friction is the per-session "Load once" prompt for an unsigned DLL, which a signed `.bundle` removes; that is a deployment cost, not a blocker |
| T5 | Most target users run AutoCAD LT | **not fired (untested)** | No user data collected. LT users get DXF plus a preview from B1 |
| T6 | ODA MCP servers ship, or terms allow free commercial DWG writing | **not fired** | ODA MCP servers were not confirmed shipped as of 2026-10-04 (G5); not re-checked in Phase 2 |
| T7 | A hosted or SaaS variant is required | **not fired** | No such requirement; everything runs locally |
| T8 | ezdxf maintenance stops or a blocking defect appears | **not fired** | ezdxf 1.4.4 delivered everything. One non-blocking defect (CLASS-section order depends on `PYTHONHASHSEED`) is worked around on our document instance, and the dependency is capped `<1.5` |
| T9 | Live editing needs more than attribute edits | **not fired** | No live-editing requirement beyond attributes has appeared |

## Findings

1. **Rule-pack gap: inverter DC power.** In the owner's test 2, Claude corrected 12 modules per string to 11. The design then passed validation, although 2 × 11 × 550 W = 12.1 kWp exceeds the inverter's `pdc_max_w` of 9,000 W by 34 % (DC/AC 2.02). Claude noticed this without a finding and settled on 8 modules (8.8 kWp, DC/AC 1.47).
   - The vault rule catalogue already defines the check as **STR-007** (Σ P_STC ≤ P_dc,max as an error; DC/AC between 1.0 and 1.35 as info). The S1 subset implements only 8 of the 98 rules, and STR-007 is not one of them. The parameter model already carries `pdc_max_w`.
   - A tool that stays silent on a 34 % overload contradicts "validate first". Completing the rule pack is a Phase 3 priority. Implement STR-007 first, and consider raising its DC/AC band from info to a warning above a policy ceiling.
2. **Pillow.** The S3 preview imports PIL directly, but Pillow first arrived only through matplotlib. It is now a declared dependency (`pillow>=10,<13`, commit `5fdddb4` in #5). The S3 report's open item on this is resolved.
3. **Non-ASCII paths are refused by the finisher.** The Core Console script is written as ASCII, and paths such as `Diseño` are refused with a clear error, because the script encoding for them is unverified. Spanish-speaking users will hit this often (accented folder and user names). Verify how Core Console reads `.scr` files (ANSI code page or UTF-8 with BOM) and lift the limit before `export_drawing` ships.
4. **Unsigned plug-in.** With `SECURELOAD=1`, NETLOAD of the unsigned DLL asks for "Cargar una vez" (Load once) in every session, so unattended use is impossible. Real use needs a signed `.bundle` in a trusted `ApplicationPlugins` folder (code-signing certificate, installer).
5. **Education licence.** The workstation runs AutoCAD 2027 Education ("no comercial"). S4 found no educational marking in the PDF (text, metadata, visible page) or in the DWG's readable content. That contradicts S2's statement that the licence "stamps drawings". A flag in the DWG's compressed sections cannot be ruled out without opening the file in a commercial seat. Whatever the files contain, the licence terms forbid commercial use, so commercial submissions need a commercial licence.
6. **Privacy of DWG "last saved by".** The DWG's DWGPROPS record the Windows login name as "last saved by". Generated DWGs must not be committed to this public repository (`out/` is git-ignored), and users should know before sharing files. A way to override or clear the value is an open item. The Core Console working folder also receives `ErrorReports\...\cer.log` with a device id, which must stay out of version control.
7. **`.mcp.json` needs the venv executable.** The committed command `${PVSLD_MCP_COMMAND:-pvsld-mcp}` connects only if the venv's `Scripts` folder is on `PATH` when Claude Code starts. Otherwise Claude Code reports "Failed to connect" or "Connection closed"; the orchestrator's own Claude Code session showed exactly that. Set `PVSLD_MCP_COMMAND` to the absolute path of `.venv\Scripts\pvsld-mcp.exe` (now in the README quick start), or register the server at user scope. An MCPB bundle (planned distribution) removes the problem for end users.
8. **Never force-kill AutoCAD.** During S2, a force-kill of a starting AutoCAD truncated `AcLivePreviewContext.dll` in the user profile, and every later start failed with "Bad IL format" until the owner repaired the file. The harness now shuts down only with `Quit()` and never kills AutoCAD. The Core Console finisher kills only the process it started, and only on timeout.
9. **A command waiting for input cannot be cancelled from outside.** AutoCAD rejects COM `PostCommand` and ignores posted Esc keystrokes. Tools must report "busy" with the reason and let the user act, which the plug-in does.
10. **Core Console needs a timeout.** A script that falls out of step (for example, an unknown PC3) leaves Core Console waiting for input forever. Start-up, licence check and load take about 85 % of each sheet, so a batch of several sheets in one Core Console session would remove most of the ~4 s per sheet.
11. **The preview is near the token cap.** With the preview, a generate result is about 20.9k of the 25k tokens (by estimate). `PVSLD_PREVIEW_MAX_BYTES` lowers the budget without a code change. Claude Code's actual counting of base64 images is still unconfirmed.

### Inconsistencies found during the review

- `IMPLEMENTATION_PLAN.md` still listed Stages 2.3 and 2.4 as "Not Started" after #5 and #6 merged. Fixed in this review.
- The S3 report still lists the model-in-the-loop run as pending and Pillow as undeclared, and the S4 report still lists the S1 AUDIT as not met. Each report now carries a short update note that points here.
- S2 says the Education licence "stamps drawings"; S4 found no marking. S4 is the measured result, and the S2 report now carries a note.
- The vault's `index.md`, `log.md`, `hot.md` and `overview.md` did not list the four spike notes or ADR-0003. Fixed in the vault together with this review.
- `docs/README.md` did not list `docs/spikes/` or ADR-0003. Fixed in this review.
- The owner's manual test ran the server at `bd426a5`, before the #7 AUDIT fix. #7 changes only the DXF layout metadata, not the MCP contract, so the result still holds.
- The CI run for the #7 merge on `develop` was still in progress when this review was written. The PR's own checks passed.

## Open items

| Item | Owner / when |
|---|---|
| Run the MCP Inspector session (install Node.js 22.19+) | owner, before or early in Phase 3 |
| Optional Claude Desktop run (240 s, about 150k characters; M1) | owner, Phase 5 distribution |
| Open an S4 DWG in interactive AutoCAD 2027 (GUI TrustedDWG balloon) and in a **commercial** seat (hidden Education flag) | owner, when a commercial seat is available |
| Observe a real Core Console run outside the licensed session (another Windows account) | owner, when it can be arranged safely |
| Confirm how Claude Code counts the base64 preview against the 25k-token cap | Phase 3 |
| Non-ASCII paths in the Core Console finisher | Phase 4 (`export_drawing`) |
| Override or clear DWGPROPS "last saved by" before sharing | Phase 4 |
| Signed `.bundle` for the plug-in | Phase 4 |
| Ask two or three UVIEs and a CFE service centre whether DXF or ezdxf PDFs are accepted (Z1, trigger T3) | owner, before Phase 5 |
| Re-read the NOM table values in `core/tables.py` against the published text | Phase 3 |
| Re-check T1 (Autodesk AutoCAD MCP server) and T6 (ODA MCP servers) | at each phase review |
| Tag `v0.2.0-spike` after this review merges | orchestrator (GitFlow release) |

## Proposed scope for Phases 3–5 (tentative, owner to confirm)

These are proposals from the spike results. The owner confirms them when each phase is planned.

### Phase 3: Parametric PV sizing engine and complete rule pack (`v0.3.0-engine`)

- **3.1 Parameter model schema v1 (ADR-0002).** Add the fields that 7 catalogue rules still need: inverter THD, DC injection and PF range; service conductors; CCF element; grounding data; transformer evidence; storage export limit and polarity. Add equipment catalogue entries keyed by `id` from datasheets, and a schema version policy.
- **3.2 Complete rule pack `mx-gd-2026.10`.** Implement all 98 catalogue rules, starting with **STR-007 (inverter DC power, DC/AC ratio)**, the gap the owner's test exposed. Re-read the NOM tables against the published text. Add a coverage test per MX checklist item (65 of 71 machine-checkable items mapped).
- **3.3 Sizing engine.** Propose string configurations (series and parallel ranges from the voltage, MPPT, current and DC-power rules), inverter matching and DC/AC ratio, then conductor, OCPD and voltage-drop sizing. All of it is deterministic, so Claude proposes and explains, and the code decides.
- **3.4 MCP surface.** Add a sizing tool, publish the full rule catalogue resource, and confirm the preview token budget. Close the MCP Inspector item.

### Phase 4: Diagram generation and symbol library

- More layout templates beyond `bt_string_residential_v1`: more strings and MPPTs, several inverters, three-phase, microinverters and optimizers; later MT.
- Grow the symbol library to the NMX-J-136-ANCE figures (purchase the standard, P1), with approved Mexican SLDs as references and golden files (P12).
- B2 production methods (`render_diagram`, `read_back`, `save_as_dwg`, `plot_pdf`, `zoom_to`) on the S1 diagram model, the B1/B2 parity test, and the signed `.bundle`.
- `export_drawing` (Core Console finisher with batching, non-ASCII paths and DWGPROPS privacy) and `get_diagram_summary`.

### Phase 5: Validation, distribution and production release (`v1.0.0`)

- Reviewer acceptance of the output (UVIE and CFE feedback, trigger T3) and the package validator for MX-I01…I07.
- Post-drawing TOP and DRW rules on DXF and DWG, and end-to-end tests.
- Distribution: an MCPB bundle and a Claude Desktop run; documentation in Spanish and English.
- Release `v1.0.0`, with drawings marked as drafts until the responsible engineer signs them.
