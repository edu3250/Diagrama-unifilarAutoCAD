# ADR-0004: Component Catalogue Storage Format & Datasheet Ingestion Workflow

| Field | Value |
|---|---|
| Status | **Proposed** |
| Decision date | proposed 2026-10-06 |
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

**YAML per component** (`datasheets/records/<type>/<model>.yaml`), loaded at Python startup into an in-memory `ComponentRegistry` (dict-based indexing).

### Storage structure

```
datasheets/
├── inbox/                          # git-ignored: raw PDFs from manufacturers
│   ├── modules/
│   │   ├── SunPower-SPR-M440.pdf
│   │   └── CanadianSolar-CS7-630.pdf
│   ├── inverters/
│   │   └── SMA-STP-25000-10-US.pdf
│   ├── conductors/
│   └── protection/
│
├── cache/                          # git-ignored: markitdown markdown caches
│   ├── modules/
│   │   ├── SunPower-SPR-M440.md
│   │   └── ...
│   └── ...
│
└── records/                        # committed: extracted component specs
    ├── modules/
    │   ├── sunpower-spr-m440.yaml
    │   └── canadian-solar-cs7-630.yaml
    ├── inverters/
    │   └── sma-stp-25000-10-us.yaml
    ├── conductors/
    │   ├── copper-thwn-2-10awg.yaml
    │   └── ...
    └── protection/
        ├── breaker-2p-63a-acti9.yaml
        └── ...
```

### Record schema (Pydantic)

```python
class ComponentMetadata(BaseModel):
    """Provenance and review tracking."""
    source_datasheet_filename: str  # e.g., "SunPower-SPR-M440.pdf"
    source_datasheet_sha256: str    # SHA-256 of the original PDF for integrity
    page_references: list[int]      # pages from which facts were extracted
    extraction_date: date           # when Claude extracted the facts
    reviewed_by: str                # owner's name or email (e.g., "edu3250")
    review_date: date               # when the owner approved the record
    notes: Optional[str]            # any caveats or non-standard aspects

class PVModuleSpec(BaseModel):
    """Photovoltaic module specifications."""
    component_type: str = "pv_module"
    component_id: str               # e.g., "SUNPOWER-SPR-M440"
    manufacturer: str
    model: str
    rated_power_stc_w: float        # P_STC at STC (1000 W/m², 25 °C)
    voc_v: float                    # V_oc at STC
    vmp_v: float                    # V_mp at STC
    isc_a: float                    # I_sc at STC
    imp_a: float                    # I_mp at STC
    temp_coef_voc_v_per_k: float   # ΔV_oc/ΔT, typically negative
    temp_coef_pmp_pct_per_k: float # ΔP_mp/ΔT / P_mp, typically negative
    temp_coef_isc_pct_per_k: float # ΔI_sc/ΔT / I_sc, typically positive
    dimensions_mm: tuple[float, float, float]  # length, width, thickness
    weight_kg: float
    frame_type: str                 # e.g., "aluminum", "none"
    certifications: list[str]       # e.g., ["IEC-61215", "IEC-61730", "UL-1703"]
    metadata: ComponentMetadata

class StringInverterSpec(BaseModel):
    """String or hybrid inverter specifications."""
    component_type: str = "string_inverter"
    component_id: str
    manufacturer: str
    model: str
    pdc_max_w: float                # Maximum DC input power
    vdc_max_v: float                # Maximum DC input voltage
    vdc_min_v: float                # Minimum DC input voltage
    mppt_count: int                 # Number of MPPT inputs
    mppt_vmax_v: list[float]        # Per-MPPT max voltage (if different)
    mppt_isc_max_a: list[float]     # Per-MPPT max SC current
    vmp_window_v: tuple[float, float]  # Recommended V_mp window (e.g., 400-600 V)
    pac_nominal_w: float            # Nominal AC power
    pac_max_w: float                # Maximum AC power
    pf_range: tuple[float, float]   # Power factor range (e.g., 0.8 to 1.0)
    thd_max_pct: Optional[float]    # Total harmonic distortion limit
    certifications: list[str]       # e.g., ["UL-1741-SB", "IEEE-1547", "NMX"]
    metadata: ComponentMetadata

class ConductorSpec(BaseModel):
    """Electrical conductor (wire, cable)."""
    component_type: str = "conductor"
    component_id: str
    material: str                   # "copper" or "aluminum"
    core_cross_section_mm2: float   # or AWG equivalent
    awg_equivalent: Optional[str]   # for reference
    insulation_type: str            # "THWN-2", "USE-2", "PV"
    rated_voltage_v: int            # e.g., 600
    ampacity_25c_a: float           # Ampacity at 25 °C
    ampacity_table: dict[float, float]  # Temperature -> ampacity (for derating)
    dc_voltage_drop_mv_per_a_per_100m: float  # Ohm's law: (rho * L / A) per 100 m
    metadata: ComponentMetadata

class OvercurrentDeviceSpec(BaseModel):
    """Fuse, breaker, or SPD."""
    component_type: str             # "breaker", "fuse", "spd"
    component_id: str
    manufacturer: str
    model: str
    rated_current_a: float
    rated_voltage_v: int
    interrupting_rating_ka: float   # or KAIC (kA)
    certifications: list[str]       # e.g., ["UL-1498", "UL-1699", "NMX"]
    metadata: ComponentMetadata
```

### Ingestion workflow (Stage 3.2)

1. **Owner supplies PDF** → `datasheets/inbox/<type>/<model>.pdf`
2. **Markitdown conversion** → `datasheets/cache/<type>/<model>.md` (git-ignored)
3. **Claude reading** (interactive, not in CI): reads markdown, answers schema extraction questions
4. **Template generation** → JSON form of the schema with blanks for the owner to fill
5. **Owner review & approval** → Edits the JSON template if any extraction was wrong
6. **Python validation** (`src/pvsld/ingest.py`):
   - Pydantic schema validation (correct types, units, ranges)
   - Plausibility checks: Vmp < Voc, Imp < Isc, temp coefficients have correct sign, conductor ampacity decreases with temperature, etc.
   - Returns `(valid: bool, warnings: list[str], errors: list[str])`
7. **Convert to YAML** → `datasheets/records/<type>/<model>.yaml`
8. **Commit to git** with a message like "feat(catalogue): add PV module SunPower SPR-M440 (datasheet rev 2024-03, reviewed by edu3250)"

### Runtime loading

```python
from src.pvsld.catalogue import ComponentRegistry

registry = ComponentRegistry.load_from_yaml("datasheets/records/")
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

**Status:** Proposed (awaiting owner confirmation at the start of Phase 3, Stage 3.1). If approved, this ADR is referenced in the commit that adds Stage 3.1 to `IMPLEMENTATION_PLAN.md` and the first datasheet record to `datasheets/records/`.
