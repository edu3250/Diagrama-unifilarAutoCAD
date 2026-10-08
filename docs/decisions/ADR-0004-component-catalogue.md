# ADR-0004: Component Catalogue Storage Format & Datasheet Ingestion Workflow

| Field | Value |
|---|---|
| Status | **Accepted** |
| Decision date | proposed 2026-10-06, accepted 2026-10-07 |
| Phase / stage | Phase 3, Stage 3.1 |
| Deciders | edu3250 (project owner) |
| Supersedes | none |
| Vault original | none yet |

> [!NOTE]
> **Decision in one paragraph.**
> Store component specifications as **one YAML file per component** in `datasheets/records/<type>/<model>.yaml`, with a Pydantic schema validation in Python and a human-in-the-loop review step before commit. Copyrighted PDFs go into git-ignored `datasheets/inbox/`; markitdown caches go into git-ignored `datasheets/cache/`. Each committed record carries provenance: datasheet filename, SHA-256, page references, extraction date, and a reviewed flag. The catalogue is loaded at runtime as a `ComponentRegistry` and indexed in memory; CLIs and the MCP server query it directly. This design keeps the version control history clean (one file per model), enables code review of extracted facts (owner diffs), and avoids a database migration burden.

## Context

**Problem.** How should equipment specifications extracted from copyrighted manufacturer datasheets be stored, versioned, and validated? The system needs component data (PV modules, inverters, conductors, overcurrent devices) to parameterize the sizing engine and the diagram template engine.

**Facts (as of 2026-10):**

- **Datasheet sources are copyrighted.** PDFs from manufacturers (SunPower, Canadian Solar, SMA, Victron, IEC, Mexican standards bodies) cannot be committed to the public repository. The owner will supply them; Claude will read the markitdown version; facts (numbers and specs) will be extracted and stored.
- **Facts must be reviewable.** The owner approves extracted specifications before they are committed, ensuring accuracy and giving an audit trail of who reviewed what and when.
- **Specifications change.** A manufacturer releases a datasheet rev; the owner supplies a new PDF; the extracted facts are a new version of the component record.
- **Related specs must stay in sync.** If a module record is updated, the sizing rules and any sizing tests that reference it must be checked (soft coupling via `model_id`, not foreign keys).
- **Initial volume is modest.** Phase 3 targets ≥ 15 components (3 modules, 3 inverters, 5 conductors, 4 protection devices); Phase 4 and later may expand to 50–200 (microinverters, optimizers, batteries, transformers, etc.).
- **CI/CD must not require licensed software.** Datasheet reading happens in Claude (interactive), not in CI. Python validation runs in CI (no LLM).
- **Distribution as a Claude Code plugin.** The final plugin (Phase 5) bundles the catalogue so offline users and end-users have it without re-reading datasheets.

## Decision drivers

| ID | Driver | Evidence |
|---|---|---|
| D1 | Copyrighted PDFs cannot be committed; extracted facts (numbers) can be | Intellectual property law, repository public license (MIT) |
| D2 | Owner approval of extracted specs is a safety gate | Safety: a misread spec (e.g., Vmp 400 V instead of 40 V) breaks the sizing engine. Phase 2 manual test already caught STR-007 as a missing rule |
| D3 | Version control history must be human-readable and mergeable | Collaborative work: if two team members extract different components in parallel, the branches must merge cleanly |
| D4 | No additional infrastructure (database server, migrations) | Constraints: single-person operation initially; keep the barrier to contribution low |
| D5 | Specifications must carry provenance | Auditability: know which datasheet revision, which page, when extracted, who approved |
| D6 | At runtime, fast lookup by model ID and type | Performance: the sizing engine queries the catalogue during validation; must be O(1) or O(log n) |
| D7 | Initial volume is modest; no schema stability yet | Phase 3 will discover missing fields (e.g., inverter THD range, service conductor type). Schema is not yet frozen |

## Options considered

| # | Option | Pros | Cons | Verdict |
|---|---|---|---|---|
| O1 | **YAML per component: `datasheets/records/<type>/<model>.yaml`** (chosen) | 1. Version control: one file per model, diffs are readable by the owner. 2. Mergeable: parallel extraction work (different models) does not conflict. 3. Schema validation: Pydantic reads the YAML at load time and rejects invalid specs at Python startup, fast feedback. 4. Self-documenting: YAML comments explain field meanings and units. 5. No infrastructure: no database, no migration scripts. 6. Natural for Python: one model = one `Component` dataclass instance. 7. Provenance: metadata fields (`_source`, `_datasheet_sha256`, `_page_refs`, `_extraction_date`, `_reviewed_by`) travel with the data. | Scaling: at 200+ components, file-based indexing is slower than a database. However, runtime indexing into a dict is O(1), so the catalogue is in-memory after load. Schema migrations are manual YAML edits, not SQL scripts, but schema is not yet stable. | **Adopted** |
| O2 | **SQLite database: `datasheets/records.db`** | Schema-flexible (table with EAV, JSON columns). ACID transactions if concurrent writes ever needed. Query language (SQL) is familiar. Tools (sqlite3, DBeaver) for inspection. | 1. Binary file: diffs are opaque; owner cannot review extracted facts by reading a diff. 2. Migration burden: if a new field is added (e.g., inverter THD), all rows must be updated; YAML files get a new line and a default. 3. Not mergeable: a single `records.db` file will conflict in parallel extraction. 4. Runtime startup cost: reading and parsing the database is slower than loading a Python dict. 5. Plugin distribution: bundling a `.db` file in the package is possible but unconventional; unclear how to check schema version without Python startup. | **Rejected** in favour of O1 (version control and review matter more than query flexibility at current scale) |
| O3 | **JSON with a manifest: `datasheets/records/<type>/<model>.json` + `datasheets/manifest.json`** | Similar to O1: one file per model, mergeable, versionable. JSON is ubiquitous. Schema can be expressed as JSON Schema. | No advantage over YAML for this use case; YAML is more human-readable. Manifest file is an extra file to keep in sync. | **Rejected** in favour of O1 (YAML is more concise for metadata-heavy records) |
| O4 | **Hybrid: YAML per component + SQLite index** | Best of both: human-readable source (YAML), fast runtime lookup (SQL index). | Added complexity: two data sources to keep in sync. The Python loader must regenerate the index if any YAML has changed (expensive at startup). | **Rejected** (D4: no additional infrastructure; revisit if scaling becomes a problem) |
| O5 | **Cloud-hosted catalogue (Firebase, MongoDB, Airtable)** | Multi-user collaboration. Real-time sync. | 1. Requires internet and authentication credentials. 2. Cannot be packaged in the plugin (end-user offline use). 3. Licensing/cost. 4. Out-of-scope for Phase 3 (solo development). | **Deferred** (trigger T7: if a SaaS variant is built later) |

## Decision

**One YAML file per datasheet family** (`datasheets/records/<type>/<family-id>.yaml`). Shared facts are written once. **Every power level or model gets its own complete variant entry with its own `component_id`** (owner decision, 2026-10-07). At load time the `ComponentRegistry` expands each variant into a standalone, fully-typed component (family fields + variant fields), so Claude and the sizing engine select e.g. `JINKO-JKM640N-66HL4M-BDV` or `HUAWEI-SUN2000-6KTL-L1` directly.

The schema was checked against the first three real datasheets supplied by the owner on 2026-10-07 (Jinko JKM625-650N-66HL4M-BDV, Huawei SUN2000-2…6KTL-L1, Schneider Acti9 C60PV-DC A9N61652). Those datasheets showed fields the first draft lacked: per-variant values, bifacial (BNPI) values, module max system voltage and max series fuse, the two different per-MPPT inverter currents, the inverter's recommended max PV power, the AC max output current, and voltage-dependent DC breaking capacity.

### Storage structure

```
datasheets/
├── inbox/        # git-ignored: the owner's PDFs, any file name
├── cache/        # git-ignored: markitdown text, rendered page images, draft records
└── records/      # committed: reviewed facts only (no datasheet text)
    ├── modules/      jinko-jkm-66hl4m-bdv.yaml        (6 variants: 625…650 W)
    ├── inverters/    huawei-sun2000-ktl-l1.yaml       (7 variants: 2…6 kW)
    ├── protection/   schneider-acti9-c60pv-dc.yaml    (variants by rating)
    └── conductors/
```

### Record schema (Pydantic, family + variants)

```python
class Provenance(BaseModel):
    filename: str
    sha256: str  # of the owner's PDF; the PDF itself is never committed
    title: str  # datasheet title, revision/version and date as printed
    pages: list[int]
    extraction_method: Literal["markitdown", "rendered_page"]
    extraction_date: date
    reviewed_by: str | None  # None until the owner approves; only reviewed records are committed
    review_date: date | None
    notes: str | None = None


class ModuleVariant(BaseModel):  # one per power level, all values at STC
    component_id: str  # e.g. "JINKO-JKM650N-66HL4M-BDV"
    pmax_w: float
    vmp_v: float
    imp_a: float
    voc_v: float
    isc_a: float
    efficiency_pct: float
    bnpi: ElectricalPoint | None  # bifacial nameplate irradiance values (Pmax, Vmp, Imp, Voc, Isc)


class PVModuleFamily(BaseModel):
    component_type: Literal["pv_module"]
    family_id: str
    manufacturer: str
    model_family: str
    cell_type: str
    cells: int
    bifacial: bool
    bifaciality_pct: dict[str, float] | None
    dimensions_mm: tuple[float, float, float]
    weight_kg: float
    max_system_voltage_v: float  # e.g. 1500 (IEC)
    max_series_fuse_a: float  # bounds the string OCPD
    temp_coef_pmax_pct_per_c: float
    temp_coef_voc_pct_per_c: float
    temp_coef_isc_pct_per_c: float
    operating_temp_c: tuple[float, float]
    certifications: list[str]
    variants: list[ModuleVariant]
    source: Provenance


class InverterVariant(BaseModel):  # one per model of the family
    component_id: str  # e.g. "HUAWEI-SUN2000-5KTL-L1"
    recommended_max_pv_power_wp: float  # what datasheets publish; STR-007 uses it as P_dc,max
    max_pv_power_with_optimizers_wp: float | None
    rated_ac_power_w: float
    max_apparent_power_va: float
    max_ac_output_current_a: float  # sizes the AC OCPD and conductors
    max_efficiency_pct: float
    euro_efficiency_pct: float | None


class InverterFamily(BaseModel):  # values common to all models
    component_type: Literal["string_inverter", "hybrid_inverter"]
    family_id: str
    manufacturer: str
    model_family: str
    max_input_voltage_v: float | None  # family or variant level, exactly one
    startup_voltage_v: float
    rated_input_voltage_v: float
    mppt_voltage_range_v: tuple[float, float] | None  # family or variant level, exactly one
    mppt_count: int
    inputs_per_mppt: int
    max_input_current_per_mppt_a: float  # operating limit (current above it is clipped)
    max_short_circuit_current_per_mppt_a: float  # hard limit for array Isc (incl. bifacial gain)
    grid: Literal["single_phase", "split_phase", "three_phase"]
    rated_ac_voltage_v: list[float]
    max_ac_current_reference_voltage_v: (
        float | None
    )  # voltage at which the max AC current is specified
    frequency_hz: list[float]
    power_factor_range: tuple[float, float]
    thd_max_pct: float | None
    battery: BatteryPort | None
    variants: list[InverterVariant]
    source: Provenance


class DcBreakerVariant(BaseModel):
    component_id: str  # catalogue reference, e.g. "SCHNEIDER-A9N61652"
    rated_current_a: float
    breaking_capacity_dc: list[
        tuple[float, float]
    ]  # (voltage V, Icu kA) pairs, e.g. [(650, 3.0), (800, 1.5)]


class ProtectionFamily(BaseModel):  # DC/AC breakers, fuses, SPDs, disconnects
    component_type: Literal["dc_breaker", "ac_breaker", "fuse", "spd", "disconnect"]
    family_id: str
    manufacturer: str
    range_name: str
    poles: int
    rated_voltage_v: float
    trip_curve: str | None
    polarity_sensitive: bool | None
    standard: str
    operating_temp_c: tuple[float, float]
    variants: list[DcBreakerVariant]
    source: Provenance
```

Units are stored as printed on the datasheet (temperature coefficients in %/°C), and the engine converts them where needed. Plausibility validators run on load: per variant Vmp < Voc, Imp < Isc, |Vmp·Imp − Pmax| ≤ 2 %, efficiency consistent with module area ±0.3 points; coefficient signs (Pmax and Voc negative, Isc positive); inverter MPPT window inside the max input voltage, operating current ≤ short-circuit current, rated AC power ≤ apparent power. These rules caught no errors on the three test datasheets.

### Ingestion workflow (Stage 3.2), tested on 2026-10-07

1. The owner drops PDFs in `datasheets/inbox/` (any name).
2. **markitdown** converts each to text in `datasheets/cache/` (≈1.3–1.6 k tokens per datasheet tested).
3. **Fallback:** when markitdown returns no text (datasheets exported with fonts as outlines, e.g. Adobe Illustrator, as with the Jinko sheet), the pages are rendered to PNG with `pypdfium2` (already a markitdown dependency; no poppler/OCR install) and Claude reads the images.
4. Claude extracts a draft record (family + one variant per power level/model) into `datasheets/cache/drafts/`, with provenance (SHA-256, pages, method).
5. Python validation (`pvsld.catalogue`): Pydantic types + the plausibility validators above.
6. **Owner review** → `reviewed_by`/`review_date` filled → the record moves to `datasheets/records/` and is committed (`feat(catalogue): add … (datasheet rev …, reviewed by …)`).

### Runtime loading

```python
from src.pvsld.catalogue import ComponentRegistry

registry = ComponentRegistry.load_from_yaml("datasheets/records/")  # one component per variant
# registry.modules: dict[str, PVModuleSpec]
# registry.inverters: dict[str, StringInverterSpec]
# registry.conductors: dict[str, ConductorSpec]
# registry.protections: dict[str, OvercurrentDeviceSpec]

module_spec = registry.get("SUNPOWER-SPR-M440")  # O(1) lookup
```

### Schema versioning

If a new field is added (e.g., `series_fuse_rating_a` for inverters), the schema version is incremented in a comment at the top of each YAML file. The Python loader checks and issues a warning or error if a file is from an old schema. Schema migration (adding default values) is done once in Python, not in SQL migrations.

## Consequences

### Positive

- **Version control:** Diffs are human-readable; the owner can review extracted facts with `git diff datasheets/records/modules/`. 
- **Mergeable:** Parallel extraction of different components has no conflicts.
- **Reviewable:** The owner's approval is recorded in the `metadata.reviewed_by` and `metadata.review_date` fields.
- **Auditable:** Source SHA-256 links to the original PDF (integrity check); page refs and extraction date are explicit.
- **No schema lock-in:** Changing a field name or adding a new field requires updating a few YAML files, not a database migration.
- **Plugin distribution:** The `datasheets/records/` directory is bundled in the plugin's `.claude-plugin` package; offline users have the catalogue.
- **Performant:** In-memory dict indexing is O(1).

### Negative / risks

- **Scaling:** At 500+ components, a file-per-model approach may become unwieldy (directory browsing, loading time). A hybrid approach (YAML source + SQL index) can be adopted later without losing version control.
- **Concurrent writes:** If multiple Claude processes are extracting simultaneously, file conflicts are possible. Mitigation: component_id naming convention ensures no two people extract the same model; branch and merge via git.
- **Schema stability:** The schema is not yet frozen. Adding a required field will break old YAML files unless a default is provided in the Python loader.

## Open questions

1. Who has the authority to approve and commit a datasheet extraction? (Answer: the owner initially; may expand as the team grows.)
2. What is the canonical format for `component_id` (kebab-case, UPPERCASE, snake_case)? (Recommendation: UPPERCASE, e.g., `SUNPOWER-SPR-M440`, for URL safety and consistency with the symbol naming in ADR-0003.)
3. Should the markitdown cache (`datasheets/cache/`) be versioned at all, or is it always regenerated? (Recommendation: never commit; rely on the PDF and re-run markitdown if needed.)
4. Will the catalogue ever be edited by end-users (e.g., to add a local component)? (Out of scope for Phase 3; addressed in Phase 5 if the use case emerges.)

---

**Status:** Accepted by the project owner on 2026-10-07, together with two decisions: every power level or model keeps its own variant record, and an inverter's optimizer-only PV power (e.g. Huawei's 10,000 Wp footnote) is stored only on the model the datasheet attaches it to, flagged as ambiguous, and used by the engine only when the design declares optimizers on every module; every other model is limited to its recommended max PV power.

**Owner decisions 2026-10-07 (PR #11):** inverter maximum AC currents are checked at the datasheet's reference voltage when it differs from the nominal one (Growatt: 220 V); module power tolerance carries its unit in the field name (`power_tolerance_pct`, `power_tolerance_w`); the 2 kA fallback breaking capacity of the Suntree breaker is accepted (it matters mainly for battery circuits); inverter certifications are not tracked, so `certifications_safety` and `certifications_grid` were removed.
