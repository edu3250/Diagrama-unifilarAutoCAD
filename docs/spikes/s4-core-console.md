# Spike S4: AutoCAD Core Console Finisher

| Field | Value |
|---|---|
| Stage | Phase 2, Stage 2.4 ([`IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md)), plus the S1 criterion "the DXF opens in AutoCAD 2027 and AUDIT reports 0 errors" (Stage 2.1) |
| Decision under test | [ADR-0001](../decisions/ADR-0001-claude-autocad-integration.md): optional finishers, the Core Console route to TrustedDWG and an AutoCAD-plotted PDF |
| Date | 2026-10-06 (build and AutoCAD runs, 10:30-10:55 local time, UTC-6) |
| Workstation | Windows 11 Pro 26200; AutoCAD 2027 (R26.0, build 26.0.118, Spanish, **Education licence**), `accoreconsole.exe` 26.0.118; Python 3.11.9 |
| Status | **Stage 2.4 criteria met.** The S1 AUDIT criterion is **not met**: 2 errors, with a verified one-line fix for S1 (see [S1 AUDIT](#s1-audit-the-dxf-in-autocad-2027)) |

## Summary

`pvsld.finishers.core_console` turns one drawing into DWG 2018 and a PDF by running the AutoCAD Core Console:

```
accoreconsole.exe /i sld.dxf /s sld.finish.scr /isolate pvsld <out>\.accoreconsole-user
```

The generated script runs AUDIT (report only), `SAVEAS` 2018, `-PLOT` of layout `A3` with `DWG To PDF.pc3`, and `QUIT`. Stdout goes to a file, and a timeout stops only the process the finisher started. The result object carries:

- the paths, the exit code, the duration and the per-step timings;
- the AUDIT counts and the facts read from the drawing;
- the DWG and PDF inspection;
- a list of problems.

`ok` is true only when that list is empty. The CLI is `pvsld finish DRAWING [-d DIR] [--json]`.

**Outcome on the reference workstation:**

- **Speed:** the finisher produced DWG `AC1032` and a one-page A3 PDF in **4.2 to 10.8 s per sheet**. The cold first run took 10.8 s and the warm median was 4.9 s, against a 15 s limit.
- **TrustedDWG:** the DWG carries the "Trusted DWG last saved by an Autodesk application" text, and it re-opens and audits clean in Core Console.
- **Failures:** invalid input, a missing Core Console, a timeout and a missing PC3 are all reported as failures, never as a silent success.
- **S1 sheet:** AUDIT finds **2 errors**, both from S1 putting the overall paper-space viewport on a layer other than `0`. A copy with that one viewport on layer `0` audits **0 errors, 0 fixed**, both as DXF and as the DWG saved from it.
- **Education licence:** no educational or non-commercial marking was found in the DWG's readable content or in the PDF (text, metadata and a visual check). See [Education licence markings](#education-licence-markings).

## Results

Measured with `python scripts/s4_measure.py --runs 5 --timeout 60` and `pytest tests/finishers --run-autocad` (**6 passed** in 43 s; the missing-PC3 test waits for its 20 s timeout). Raw numbers are in the git-ignored `out/s4/measure/results.json`.

| Criterion | Measured | Result |
|---|---|---|
| DWG 2018 produced (Stage 2.4) | `AC1032` in the first six bytes on every run; 46-47 KB from a 137 KB DXF | **PASS** |
| DWG opens without the "not saved by Autodesk" notice (Stage 2.4) | The DWG contains the TrustedDWG sentence "Autodesk DWG. This file is a Trusted DWG last saved by an Autodesk application or Autodesk licensed application." (UTF-16LE, in AppInfo and its history copy). Re-opening it in Core Console prints no notice, and AUDIT is clean on the layer-0 copy. Not checked: the interactive AutoCAD balloon itself (no GUI run) | **PASS** (file evidence and Core Console re-open) |
| PDF produced (Stage 2.4) | One page, MediaBox 1191 x 842 pt (420.2 x 297.0 mm, A3 landscape), 119 KB, PDF 1.7, Producer `pdfplot18.hdi 18.00.118.00000`, Creator `AutoCAD 2027 - Español (Spanish) 2027 (26.0)` | **PASS** |
| ≤ 15 s per sheet (Stage 2.4) | 5 runs: 10.78 (cold), 5.26, 4.55, 5.46, 4.23 s; median 5.26 s, warm median 4.91 s. Variants 4.4-5.6 s | **PASS** |
| Unlicensed or failed run is reported, never a silent success (Stage 2.4) | 4/4 failure modes reported (table below); a silent exit with no output and no files is covered by the CI fake | **PASS** (see [Licensing](#licensing-and-the-silent-failure-risk)) |
| Scripted run checks exit code, outputs and a timeout (Stage 2.4 test) | `tests/finishers/test_core_console_live.py`, 6 tests, marker `autocad` | **PASS** |
| S1: the DXF opens in AutoCAD 2027 and AUDIT reports 0 errors (Stage 2.1) | Opens (304 entities, layouts `A3`, `Model`); AUDIT **2 errors, 0 fixed**: `AcDbViewport(123) Paperspace vport layer Not "0"`, once in pass 1 and once in pass 2. With that viewport on layer `0`: **0 errors, 0 fixed** | **FAIL** as generated; fix verified |

### Timing

Step times come from AutoCAD's `MILLISECS`, printed by the script's markers. `outside_script` is the wall time minus the scripted part: process start, licence check, loading the DXF given with `/i`, and exit.

| Run | Wall (s) | AUDIT (ms) | SAVEAS (ms) | PLOT (ms) | outside_script (ms) |
|---|---|---|---|---|---|
| 1 (cold) | 10.78 | 31 | 156 | 1,188 | 9,408 |
| 2 | 5.26 | 31 | 94 | 563 | 4,569 |
| 3 | 4.55 | 31 | 78 | 469 | 3,976 |
| 4 | 5.46 | 31 | 219 | 734 | 4,478 |
| 5 | 4.23 | 47 | 63 | 469 | 3,647 |

About 85 % of a sheet is Core Console start-up, licence check and drawing load. The work itself (AUDIT, SAVEAS and PLOT) takes 0.5 to 1.4 s. A batch of many sheets should therefore run them in one Core Console session (one script, several drawings) rather than one process per sheet.

| Variant | Wall (s) | Outcome |
|---|---|---|
| Output folder with a space (quoted paths) | 4.53 | DWG and PDF produced; same 2 AUDIT errors |
| `DXFIN` into the start-up drawing instead of `/i` | 4.74 | Works as well (drawing named `Dibujo1.dwg`); `/i` stays the default |
| Detailed plot, paper `ISO full bleed A3 (420.00 x 297.00 MM)`, `monochrome.ctb` | 5.55 | The Spanish build accepts the English media name and the prompt order matches the script; same A3 page |
| Viewport on layer 0 (S1 fix) | 4.40 | **ok**: AUDIT 0/0, DWG and PDF |
| Re-open the DWG (AUDIT only) | 4.40 | Opens without notice; AUDIT 2/0 for the S1 output, 0/0 for the layer-0 copy |

### Failure modes

| Case | What happened | Reported as |
|---|---|---|
| Invalid DXF | Exit code **53**; log: "Error en el encabezamiento del dibujo en línea 5", "... no es un archivo DXF válido", "Entrada DXF no válida o incompleta -- dibujo descartado.", "ERROR: Something went wrong. ErrorStatus=53" | not ok: exit code, no markers, 4 console problems, DWG and PDF not produced |
| Core Console missing | Nothing started | `FinisherError: accoreconsole.exe not found (...); a full AutoCAD is required` |
| 1 s timeout | The process the finisher started (one PID) was killed after 1.04 s, and the PID was gone afterwards | not ok: "did not finish within 1 s; the process this finisher started (pid N) was stopped", no markers, outputs not produced |
| Missing PC3 (`NoSuch.pc3`) | `-PLOT` rejects the device ("<NoSuch.pc3> no encontrado."). Every later script line is then read as a device name, and **Core Console waits for input forever** after the script ends | not ok after the timeout (60 s): timeout, markers `plotted` and `end` missing, 5 "no encontrado" lines, PDF not produced |

## Education licence markings

The owner's AutoCAD runs on an Education licence ("EDUCACIÓN (NO COMERCIAL)" in the AutoCAD UI). S2 reported that this licence "stamps drawings". S4 checked the actual output:

| Where | Method | Finding |
|---|---|---|
| DWG, readable content | Scan of the whole file as Latin-1 and as UTF-16LE (both byte alignments) for `educational`, `education`, `educación`, `educativ`, `student`, `estudiant`, `academic`, `no comercial`, `non-commercial`, `not for commercial` | **None found** |
| DWG, provenance text | Uncompressed UTF-16LE strings | TrustedDWG sentence (above); `<ProductInformation name ="AutoCAD" build_version="X.118.0.0(x64)" registry_version="26.0" install_id_string="pvsld" registry_localeID="1034" git_commit_id="2c19eb97...">`, truncated by AutoCAD before `/>`. It has no edition or licence field. `install_id_string` is the `/isolate` key name, and `1034` is Spanish |
| DWG, DWGPROPS summary | `<prop_set>` (UTF-16LE) | Create date `2000-01-01T00:00:00` (from the deterministic DXF), last-save time in UTC, application `AutoCAD 2027`, version `X.118.0.0`, and **"last saved by" = the Windows login name** (prop 8). There is no edition field |
| DWG, compressed sections | Not decoded (no DWG library) | **Unknown.** A licence flag, if any, would sit in compressed data. The decisive test is opening the DWG in a commercial AutoCAD seat (open item) |
| PDF, text and metadata | Raw bytes and the 3 Flate streams that inflate, scanned for the same words; Info dictionary | **None found.** `/Title (A3)`, Producer `pdfplot18.hdi 18.00.118.00000`, Creator `AutoCAD 2027 - Español (Spanish) 2027 (26.0)`; no XMP metadata |
| PDF, visible content | The PDF page viewed as an image | **No stamp, banner or watermark.** The sheet content fills the A3 page (border, title block, tables) and nothing else is printed |
| Core Console log | Same word scan over every run's log | **None found.** The console prints no licence or edition text |

**Conclusion.** For AutoCAD 2027 Education, the Core Console output shows **no educational marking** in the PDF (text, metadata or visible content) or in the DWG's readable content. The DWG identifies its writer as "AutoCAD" with no edition. A marking hidden in the DWG's compressed sections cannot be ruled out without a commercial seat. Whatever is or is not in the files, the Education licence terms ("no comercial") still govern their use; this measurement says nothing about licensing.

## S1 AUDIT: the DXF in AutoCAD 2027

AutoCAD's AUDIT of the S1 golden DXF (`tests/golden/residential_7p7kwp.dxf`, identical to a fresh `pvsld generate`):

```
Fase 1 200     objetos revisadosAcDbViewport(123)
           Paperspace vport layer Not "0"               "0"
AcDbViewport(123)                 no se ha reparado.
...
Total de errores encontrados 2, corregidos 0
```

Handle `123` is the overall paper-space viewport (viewport id 1) of layout `A3`. S1 deliberately moved it from ezdxf's `VIEWPORTS` layer to `G-ANNO-NPLT` to keep "0 entities on layer 0" (S1 report, finding 3). AutoCAD requires this viewport on layer `0`, and AUDIT counts it in both passes. Changing only that entity's group code 8 to `0` gives **0 errors, 0 fixed** in AutoCAD 2027, as DXF and as DWG after `SAVEAS`. **Recommendation for S1:** leave the overall paper-space viewport on layer `0` and exempt it from the layer-0 rule in the read-back. The user-visible viewport (id 2) can stay on `G-ANNO-NPLT`. The live test `test_golden_dxf_becomes_dwg_2018_and_pdf_within_15_s` tolerates exactly these 2 errors until S1 changes; after that it expects 0.

## Licensing and the silent-failure risk

Running outside the licensed Windows session was not reproduced. It would need another Windows account or a disabled licence, and both would touch the owner's licensing set-up. The finisher therefore does not trust any single signal. A run is ok only if:

1. the process exits with code 0 inside the timeout;
2. the console printed something;
3. all five AutoLISP markers (`loaded`, `audited`, `saved`, `plotted`, `end`) were printed;
4. the drawing has entities and the layout;
5. the AUDIT summary is present with 0 errors;
6. no problem phrase is in the log;
7. every requested file was created by this run and has the right format (`AC1032`; `%PDF-` with pages).

The reported failure modes (silent exit, hang) are each caught by rules 1-3 and 7. The CI fake covers them (`FakeCoreConsole(silent=True)`, `timed_out=True`, `exit_code=...`), and the real runs above show the same rules firing on actual Core Console failures.

## What was built

| Piece | Path | Role |
|---|---|---|
| Finisher | `src/pvsld/finishers/core_console.py` | Locates `accoreconsole.exe` (argument, `$PVSLD_ACCORECONSOLE`, newest `%ProgramFiles%\Autodesk\AutoCAD 20xx`), writes the script, builds the command line, runs it with a timeout, assesses the result (`FinishResult.to_dict()` is JSON-ready for a later MCP `export_drawing`) |
| Log parser | `src/pvsld/finishers/console_log.py` | Decodes the UTF-16LE console output; reads markers, checks, the AUDIT summary (English and Spanish) and problem phrases |
| Output inspection | `src/pvsld/finishers/outputs.py` | DWG version, TrustedDWG sentence, product information, DWGPROPS; PDF pages, MediaBox, producer, creator; marking scan |
| Fake | `src/pvsld/finishers/fake.py` | `FakeCoreConsole`, a runner for CI with one knob per failure |
| CLI | `src/pvsld/cli.py` | `pvsld finish` |
| Tests | `tests/test_finisher_*.py` (CI), `tests/finishers/test_core_console_live.py` (`autocad`) | 96 CI tests; finisher modules 99-100 % covered; 6 live tests |
| Harness | `scripts/s4_measure.py` | The measurements in this report |

The generated script (`out\sld.finish.scr`, CRLF, ASCII) for the default options:

```
(progn (princ (strcat "\nPVSLD" ":STEP:loaded:" (itoa (getvar "MILLISECS")) "\n")) (princ))
(progn (princ (strcat "\nPVSLD" ":CHECK:entities:" (itoa (if (setq pvsld_ss (ssget "_X")) (sslength pvsld_ss) 0)) "\n")) (princ))
... (acadver, locale, dwgname, layouts)
_.AUDIT
_N
(... :STEP:audited: ...)
_.SAVEAS
_2018
D:\...\sld.dwg
(... :STEP:saved: ...)
_.-PLOT
_N
A3

DWG To PDF.pc3
D:\...\sld.pdf
_N
_Y
(... :STEP:plotted: ...)
(... :STEP:end: ...)
_.QUIT
_Y
```

## Findings worth keeping

1. **`/i` opens a DXF directly** in Core Console 2027, and `DXFIN` into the start-up drawing works too. No intermediate DWG is needed.
2. **`/isolate` protects the owner's profile and needs no set-up.** The first run creates an 11 MB private profile in the output folder (159 files, with the default PC3s and CTBs, in 0.2 s). `DWG To PDF.pc3` and `monochrome.ctb` are then found there. The owner's recent-file list was unchanged, and no `pvsld` key appeared under `HKCU\Software\Autodesk`.
3. **Core Console lacks `(layoutlist)`** (`; error: no function definition: LAYOUTLIST`). The script reads the `ACAD_LAYOUT` dictionary instead.
4. **`DATE` advances only in whole seconds in Core Console**, so step timings use `MILLISECS`.
5. **Redirected output is UTF-16LE without a BOM** (8.8 KB raw for 4.4 KB of text). The first line names a temporary redirect file in the user's `%TEMP%`.
6. **Language-neutral script input works in the Spanish build:** `_.` commands, `_N`/`_Y`/`_2018`/`_M`/`_L` keywords, and an English media name for the detailed plot. The prompts and messages are Spanish, so the log parser matches both languages.
7. **A script out of step never ends on its own.** A rejected answer is retried with the next lines, and after the last line Core Console waits for input even with stdin closed. The timeout (default 60 s, about 13 times a sheet) is the only guard, and the "<...> no encontrado" lines identify the cause.
8. **The working folder receives `ErrorReports\<hash>\cer.log`.** This is the crash reporter's start-up log (no crash), and it contains a device ID, so it must never be committed. `out/` is git-ignored.
9. **`QUIT` asks to discard changes** after a plot, even though nothing was edited; the script answers `_Y`. AUDIT without fixing reports "no se ha reparado" for each error.
10. **The S1 page setup names the paper `ISO_A3_(420.00_x_297.00_MM)_(420.00_x_297.00_MM)`.** That name is not a `DWG To PDF.pc3` media name, yet AutoCAD plots the 420 x 297 mm area onto an A3 page. S1 should still write the canonical name (open item).
11. **Privacy:** the DWG records the Windows login as "last saved by". Generated DWGs committed to this public repository would publish it.

## Safety record

- Every file was written under `D:\DataScience\pvsld-s4\out` (git-ignored). Each run used its own `/isolate` folder, so the owner's drawings and AutoCAD profile were not used.
- Core Console was started only by the finisher. A timeout stopped only the process it started; this happened twice (the 1 s and 60 s cases), and each PID was gone afterwards. No other AutoCAD process was running or touched.
- Machine and user names are left out of this report. The DWG's "last saved by" value is described, not quoted.

## How to run

```powershell
.venv\Scripts\pvsld generate examples\residential_7p7kwp.yaml -o out\sld.dxf
.venv\Scripts\pvsld finish out\sld.dxf --overwrite          # DWG + PDF next to the DXF
.venv\Scripts\python scripts\s4_measure.py --runs 5          # this report's measurements
.venv\Scripts\python -m pytest tests\finishers --run-autocad  # live tests (about 45 s)
```

## Open items

- **S1 fix:** keep the overall paper-space viewport on layer `0` (exempt it from the read-back's layer-0 rule) and write a canonical paper name. Then regenerate the golden file; the live test will expect 0 errors.
- **TrustedDWG in the GUI and the Education flag:** open an S4 DWG in interactive AutoCAD 2027 to confirm no notice appears. Open it in a **commercial** AutoCAD seat to rule out a hidden Education flag.
- **Unlicensed run:** observe a real run outside the licensed session (another Windows account) once the owner can arrange one safely.
- **Batching:** one Core Console session for several sheets would cut the ~4 s start-up per sheet.
- **Non-ASCII paths** (e.g. `Diseño`) are refused, because the script encoding for them is unverified.
- **Privacy:** consider clearing or overriding the DWGPROPS "last saved by" value before sharing DWGs.
