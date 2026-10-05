# Phase 1 Research Summary

**Scope:** Phase 1 (Documentation & Regulatory Research), Stages 1.2–1.6
**Research dates:** 2026-10-04/05 (facts are "as of 2026-10" unless stated)
**Decision taken from this research:** [ADR-0001: Claude ↔ AutoCAD Integration Approach](../decisions/ADR-0001-claude-autocad-integration.md)

> [!NOTE]
> This page condenses the research. The full knowledge base is the author's local Obsidian research vault (not part of this repository). It holds 252 research notes: 129 source notes, 78 entity notes, 37 concept notes and 8 comparisons. Every claim there cites a source note that records the URL, access date and confidence. Note names below in *italics* refer to vault notes.

## At a glance

1. **Nothing official to plug Claude into.** Autodesk's AutoCAD MCP server serves only Autodesk Assistant and cannot draw. The project needs its own MCP server.
2. **No community project generates PV single-line diagrams (SLDs) or targets Mexican rules.** The useful community patterns are dual engines (live + headless), attributed symbol blocks with ports, and in-process .NET plug-ins on a local pipe.
3. **Headless DXF generation with ezdxf works.** It is deterministic, licence-free and fast, so the whole pipeline can be tested in CI without AutoCAD.
4. **Mexican regulation prescribes SLD *content*, not a format or template.** 77 checklist items were consolidated, and 71 of them (92 %) can be checked by machine.
5. **Claude's job is to elicit, validate and explain; deterministic code does the engineering and the drawing.** All six research streams agree on this.

## 1. Autodesk official integration surface (Stage 1.2)

- **Current release.** AutoCAD 2027 (R26.0) was released on 2026-03-25 and updated by 2027.1 on 2026-08-04. COM ProgID: `AutoCAD.Application.26`.
- **.NET runtimes.**
  - 2027 runs **.NET 10**.
  - 2025 and 2026 shipped on .NET 8 (their base runtime); 2024 runs .NET Framework 4.8.
  - Microsoft support for .NET 8 ends on 2026-11-10, and the 2025.1.4 / 2026.1.2 updates move product dependencies to .NET 10. Whether unchanged net8.0 plug-ins still load on those updates is unverified.
  *(AutoCAD .NET API; AutoCAD 2027 Managed .NET and ObjectARX Compatibility Tables; Autodesk Support - .NET 10 Transition for AutoCAD Products)*
- **The official "AutoCAD and Civil 3D MCP Server"** is a Tech Preview inside AutoCAD 2027 (Windows).
  - Its only documented client is Autodesk Assistant.
  - It documents 7 tools, but in AutoCAD only the read, analysis, navigation and compliance tools are enabled (object-update and style tools are Civil 3D only); layer and system-variable management were added in 2026-09.
  - It **cannot draw geometry, insert blocks, fill attributes or plot.** *(Autodesk MCP Servers)*
- **Official servers Claude can use today:**
  - Product Help MCP: public, no authentication.
  - Fusion MCP: GA, local.
  - Revit Public MCP: Tech Preview, Revit 2027.2. It is a stdio executable plus an in-app add-in, which is the reference pattern for a desktop bridge.
  - No official MCP exists for external AutoCAD control, Design Automation, DWG files or AutoCAD Electrical. *(Autodesk MCP Servers; Revit Public MCP Server Documentation)*
- **API landscape.**
  - External processes reach AutoCAD only through COM, or through a channel that an in-process plug-in opens. The .NET API is in-process only.
  - AutoCAD LT has no COM and no .NET; it has AutoLISP since LT 2024 (Windows). *(AutoCAD API Landscape; AutoCAD 2027 Developer Help - Supported Programming Interfaces)*
- **Licensing** (published terms as of 2026-09-17; not legal advice):
  - A named-user (Single User) licence carves batch/background activity out of the concurrency count.
  - Service-bureau use is prohibited.
  - A hosted generation service would have to use the APS Automation API. *(AutoCAD Licensing for Automation)*
- **AutoCAD Electrical.** Its API is AutoLISP only. It ships IEC 60617 / IEEE 315 / NFPA libraries with one-line symbols, but no PV-specific symbols were found. *(AutoCAD Electrical Schematic Automation)*

## 2. Model Context Protocol and Claude (Stage 1.2)

- **Specification.** The current MCP revision is **2026-07-28**. It is stateless: no initialize handshake and no protocol sessions. `server/discover` is mandatory, and Roots, Sampling and Logging are deprecated. Earlier milestones:
  - 2025-03-26: Streamable HTTP and OAuth 2.1.
  - 2025-06-18: structured output and elicitation.
  - 2025-11-25: experimental tasks.

  *(MCP Spec 2026-07-28 Key Changes Page; MCP Spec 2025 Revision Changelogs)*
- **SDKs.**
  - MCP Python SDK v2: latest 2.3.0 (2026-10-02). It renames `FastMCP` to `MCPServer` and runs sync tools on worker threads, which is a trap for COM.
  - C# SDK: stable 2.2.0 (2026-08-13).

  *(MCP Python SDK; MCP CSharp SDK)*
- **Host limits.**
  - Claude Desktop: about 150,000 characters per tool result and 240 s per call; elicitation was not supported as of 2026-04.
  - Claude Code: 25,000-token output cap (`MAX_MCP_OUTPUT_TOKENS`), 30 s startup timeout, calls auto-backgrounded after 2 min, elicitation supported.

  *(Claude Connector Building Docs; Claude Code MCP Documentation)*
- **Tool design** (Anthropic guidance):
  - Prefer a few workflow-shaped tools over API mirrors.
  - Return concise structured results.
  - Make errors actionable, so the model knows what to fix.
  - Use opaque handles for state.

  For this project: make the parameter spec the API, and keep geometry in code. *(MCP Server Design Patterns)*
- **Bridge pattern.** Keep the MCP server out of process on stdio. Reach a running app through a small in-app plug-in on a **current-user named pipe**. Never host MCP inside the app. *(Bridging MCP to Desktop Applications)*

## 3. Community AutoCAD ↔ LLM integrations (Stage 1.3)

- **Scale and discovery.**
  - More than 100 AutoCAD MCP repositories exist; fewer than 10 have more than 25 stars, and most copy three upstreams.
  - Stars do not track quality: daobataotie has ≈579 stars and no tests; U-C4N has ≈118 stars and ≈4,990 tests.
  - Discovery is poor: the largest awesome-list has one AutoCAD entry, and the official MCP Registry has four. *(Community AutoCAD MCP Servers Comparison)*
- **Seven bridge mechanisms** were observed: COM, AutoLISP file-IPC, in-process .NET + IPC, ObjectARX + socket, headless ezdxf, Core Console, and a DWG library.
  - The most rigorous servers (beiming183, bimwright, debug23win) use an in-process .NET plug-in with DocumentLock + Transaction on a current-user pipe or a token-protected loopback.
  - COM has no transactions and cannot reach LT. *(AutoCAD MCP Integration Architectures)*
- **No server produces PV SLDs** or targets CFE/NOM. The nearest analogue is U-C4N's P&ID pack: attributed blocks with named ports, read back as a graph.
- **Security.**
  - Two C# plug-ins listen on all interfaces without auth.
  - Arbitrary-code escape hatches (`execute_lisp`, `send_code`) are common.
  - Five notable repositories have no licence.
- **Lessons.**
  - Verify results by measuring the drawing, not by trusting "OK".
  - Batching cut about 200 tool calls to 22 on one benchmark.
  - Running object snaps silently move `(command …)` points.
- **Shortlist to learn from** (all MIT):
  - U-C4N-Autocad-MCP: drawing semantics.
  - beiming183-cloud-AutoCAD-MCP: transport and safety.
  - puran-water-autocad-mcp: minimal baseline.

## 4. Programmatic DWG/DXF generation (Stage 1.2)

- **ezdxf 1.4.4** (2026-05-14, MIT) covers a 2D SLD: blocks with attribute definitions, XDATA ports, layers, MTEXT, paperspace sheets, audit, and SVG/PNG/PDF rendering.
- **Hands-on probe results:**
  - 0 audit errors.
  - Byte-identical output with fixed metadata, which enables golden-file tests.
  - ≈43 ms for a small sheet.
  - ≈0.29 s for 300 attributed inserts.
  - Rendering needs Pillow.

  *(ezdxf; R6 ezdxf Probe Experiment 2026-10-04)*
- **DWG format.** DWG 2018 (AC1032) is the format of AutoCAD 2018–2027. There is no free, commercially clean, non-Autodesk writer for it:
  - The ODA File Converter is free but non-commercial for non-members. ODA membership costs USD 3,000 in the first year (USD 2,250/yr recurring) or more.
  - LibreDWG 0.14 is GPLv3 and reliable only up to R2004.

  *(Programmatic DWG-DXF Generation Paths; ODA Pricing and MCP Servers Pages (2026-10))*
- **Core Console** (`accoreconsole.exe`) runs scripts, LISP and Core-safe .NET headlessly. It needs a licensed full AutoCAD, and with named-user licensing it fails silently outside the licensed user's session. *(AutoCAD Core Console)*
- **APS Automation API** (the cloud Core Console):
  - Pricing since 2025-12-08: 5 free AutoCAD processing hours/month, then 1 Flex token or USD 3 per 12 minutes (≈ USD 15/h).
  - US-East only; engines up to `Autodesk.AutoCAD+26_0`; no AutoCAD Electrical.

  *(Design Automation API for AutoCAD)*
- **Rejected tools.** pyautocad is abandoned (last release 2015). schemdraw has no DXF export and no inverter or SPD symbols. *(Programmatic DWG-DXF Generation Paths)*

## 5. Mexican regulation (Stage 1.5)

- **Installation code.** **NOM-001-SEDE-2012** remains in force as of 2026-10.
  - It is based on NEC 2011: it includes DC arc-fault protection (690-11) but no rapid shutdown.
  - It sets 25 Ω maximum grounding-electrode resistance (250-50) and the 120 % busbar rule (705-12(d)(2)).
  - PROY-NOM-001-SEDE-2018 was never finalized. The Programa Nacional de Infraestructura de la Calidad 2026 (DOF 2026-02-24) schedules a modification during 2026.

  *(NOM-001-SEDE-2012)*
- **2025 energy reform.**
  - The Ley del Sector Eléctrico (DOF 2025-03-18) raised the distributed-generation (GD) limit from < 0.5 MW to **< 0.7 MW** of installed capacity, and created an autoconsumo category (0.7–20 MW simplified permit).
  - The CNE replaced the CRE. The 2016 Manual de Interconexión and RES/142/2017 remain applicable.
  - A GD-specific DACG was still pending in 2026-09.

  *(Mexican Energy Reform 2025)*
- **CFE interconnection.**
  - CFE requires an SLD of the plant **and all load centres sharing the interconnection point**.
  - There is no official template, sheet size, file format or signer rule for BT. The Manual's scheme figures (MF, MCE, I1, I2, CCF, PI) act as the de-facto template.
  - Maximum processing time: 13 business days without a study, 18 with one.

  *(CFE Interconnection Procedure; Mexican SLD Submission Requirements)*
- **UVIE.** The PEC is the most explicit official SLD content specification. It requires:
  - Spanish legends, NOM-008 units and NMX-J-136 symbols (or a legend explaining any other symbol);
  - at ≥ 100 kW: feeder sizes, lengths and currents; device interrupting capacity and setting ranges; and the responsible engineer's name, cédula profesional and signature.

  UVIE review depends on the premises' installed load, not on PV capacity:
  - listed public places: any load;
  - other listed places: > 10 kW;
  - commerce/industry: > 20 kW;
  - any supply above 1000 V.

  *(UVIE Verification Process; Mexican SLD Submission Requirements)*
- **Inverters.** UL 1741 + IEEE 1547 certification or test evidence is required. Sello FIDE also accepts IEC 62109 / NMX-J-656 + IEEE 1547. *(Mexican PV Equipment Certification)*
- **Checklist.** The machine-checkable checklist **MX-A01…MX-I07** (about 75 items) is the key for the validation rule pack. The default detail level is UVIE ≥ 100 kW, which also satisfies CFE and the inspection units.

## 6. PV single-line diagram engineering (Stage 1.6)

- **Parameter model v0.1.0.** Typed components connected by circuits (graph edges), plus site, utility, title-block and layout data. All engineering values are *derived* by the engine and never typed by the user. *(PV SLD Parameter Model)*
- **Validation rules.** 98 rules in 13 families: GEN, VOLT, STR, CUR/CON, VD, OCP, DIS, PCC, MET, PCE, SPD, GND, TOP/DRW. They are mapped to the MX checklist and planned as a versioned rule pack `mx-gd-2026.10`. *(PV SLD Validation Rules)*
- **Symbols.**
  - NMX-J-136-ANCE-2019 (DOF 2020-01-30) is the current Mexican symbol standard and pairs each symbol with IEC 60617.
  - IEEE 315 was inactivated on 2019-11-07.
  - Proposed default: IEC 60617 shapes, Spanish abbreviations, and an always-generated symbol legend.

  *(PV Electrical Symbology; Symbol Standards Comparison)*
- **Calculation rules that drive designs:**
  - **Voltage correction.** NOM 690-7 requires the manufacturer's Voc temperature coefficient when given. Dwellings are limited to 600 V. In the worked example this gives a maximum of 11 modules per string.
  - **Small-conductor rule.** NOM 240-4(d) limits 10 AWG to a 30 A breaker, so a 6 kW / 220 V inverter on a 35 A breaker needs 8 AWG.
  - **Surge protection.** NOM has no SPD selection method, so IEC 60364-7-712 applies (Ucpv ≥ Uoc,max; In ≥ 5 kA; Lcrit = 115/Ng). Edition 3 was published on 2025-10-21.
  - **Voltage drop.** Limits are policy: NOM's 3 %/5 % values are informative, CFE G0100-04 uses 1 % DC, GIZ about 1 % DC + 1 % AC, and Enphase < 2 % AC. Proposed project defaults are 1.5 % DC and 2 % AC, as warnings.
- **Worked example.** 7.70 kWp residential system: 2 strings × 7 × 550 W modules on a 6 kW, 220 V inverter. *(PV String Sizing)*
- **Public examples.** No public example SLD is complete. Solar ABCs has the best tables and title block, and the CFE/CRE scheme figures give the element set. *(PV SLD Examples Catalog)*

## What this means for the architecture

[ADR-0001](../decisions/ADR-0001-claude-autocad-integration.md) adopts a **layered hybrid**:
- a Python MCP server on stdio;
- a deterministic core: parameter model → calculations → rule pack → backend-neutral diagram model;
- pluggable render backends: **ezdxf DXF first**, an **AutoCAD 2027 .NET 10 plug-in on a current-user named pipe second**, and Core Console / APS as optional finishers.

Phase 2 (tentative) proves this with four spikes: S1 ezdxf SLD, S2 AutoCAD connectivity vs COM, S3 MCP round trip, S4 Core Console finisher.

## Open questions

- **AutoCAD and tooling**
  - Named-pipe vs COM latency and reliability on AutoCAD 2027: not yet measured.
  - Generated DXF not yet opened and audited inside AutoCAD 2027.
  - Core Console behaviour with named-user licensing, and with AutoCAD LT (conflicting reports).
  - Whether .NET 8 plug-ins keep working in the .NET-10-aligned 2025/2026 updates.
  - Whether Autodesk will open its AutoCAD MCP server to third-party clients.
- **Claude hosts**
  - Whether Desktop's 240 s / 150k-character limits apply to local stdio servers.
  - Whether Desktop has shipped elicitation since 2026-04.
- **Regulation**
  - How CFE handles GD requests between 0.5 and 0.7 MW: the Manual's tiers stop at 500 kW.
  - Content and timing of the pending GD DACG and of a NOM-001-SEDE revision draft.
  - Current CFE request-form fields.
  - Whether the PEC and the public-places agreement are reissued under the 2025 regulations.
- **Submission practice**
  - Whether CFE/UVIE accept an ezdxf-made PDF, or prefer AutoCAD-plotted output or DWG.
  - Expected sheet size (A3 vs A1 is a house proposal).
  - Obtaining 3–5 real approved Mexican vector SLDs, the biggest evidence gap.
- **Data sources**
  - NMX-J-136-ANCE figure numbers and inverter-symbol coverage (needs the purchased standard).
  - Accepted minimum-temperature dataset (ASHRAE vs SMN) and lightning ground-flash-density (Ng) source.
  - IEC 60364-7-712:2025 numeric values (2017 values used so far).

## Where to find the details (vault)

| Domain | Start with |
|---|---|
| AutoCAD automation | *AutoCAD API Landscape*, *Programmatic DWG-DXF Generation Paths*, *AutoCAD Licensing for Automation*, *Autodesk MCP Servers* |
| MCP and Claude | *MCP Server Design Patterns*, *Bridging MCP to Desktop Applications*, *Configuring MCP Servers in Claude*, *MCP Security* |
| Community integrations | *Community AutoCAD MCP Servers Comparison*, *AutoCAD MCP Integration Architectures* |
| Mexican regulation | *Mexican SLD Submission Requirements*, *Mexican Energy Reform 2025*, *NOM-001-SEDE-2012*, *CFE Interconnection Procedure*, *UVIE Verification Process* |
| PV SLD engineering | *PV SLD Parameter Model*, *PV SLD Validation Rules*, *PV Single-Line Diagram Anatomy*, *PV Electrical Symbology*, *SLD Drafting Conventions* |
| Decision | *ADR-0001 Integration Approach* (`wiki/decisions/`) |

---

**Last updated:** 2026-10-05
