"""ComponentRegistry: review gate, lookup, filters, duplicates and load time."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from catalogue_helpers import ALL_RECORDS, MODULE, RECORDS, copy_records, mark_reviewed, raw, write
from pvsld.catalogue import (
    CatalogueError,
    ComponentRegistry,
    DcBreaker,
    Inverter,
    PVModule,
    UnknownComponentError,
)


def test_unreviewed_records_are_excluded_by_default(tmp_path: Path) -> None:
    copy_records(tmp_path, reviewed=False)

    registry = ComponentRegistry.load(tmp_path)

    assert len(registry) == 0
    assert set(registry.skipped_unreviewed) == {
        "JINKO-JKM-66HL4M-BDV",
        "ETSOLAR-ET-M672BH",
        "HUAWEI-SUN2000-KTL-L1",
        "GROWATT-MIN-TL-X2",
        "SCHNEIDER-ACTI9-C60PV-DC",
        "SUNTREE-SL7N-63",
    }


def test_include_unreviewed_loads_everything(tmp_path: Path) -> None:
    copy_records(tmp_path, reviewed=False)

    registry = ComponentRegistry.load(tmp_path, include_unreviewed=True)

    assert len(registry) == 34
    assert registry.skipped_unreviewed == ()
    assert not any(component.reviewed for component in registry)


def test_only_the_reviewed_record_is_loaded_when_one_is_approved(tmp_path: Path) -> None:
    copy_records(tmp_path, reviewed=False)
    write(tmp_path, MODULE, mark_reviewed(raw(MODULE), owner="edu3250"))

    registry = ComponentRegistry.load(tmp_path)

    assert [type(c) for c in registry] == [PVModule] * 6
    assert all(c.reviewed and c.source.reviewed_by == "edu3250" for c in registry)
    assert "JINKO-JKM-66HL4M-BDV" not in registry.skipped_unreviewed
    assert len(registry.skipped_unreviewed) == 5


def test_an_invalid_unreviewed_record_still_fails_the_load(tmp_path: Path) -> None:
    copy_records(tmp_path, reviewed=True)
    broken = raw(MODULE)
    broken["cells"] = 0
    write(tmp_path, MODULE, broken)

    with pytest.raises(CatalogueError, match="cells"):
        ComponentRegistry.load(tmp_path)


def test_get_is_a_dictionary_lookup_with_suggestions(tmp_path: Path) -> None:
    registry = ComponentRegistry.load(copy_records(tmp_path), include_unreviewed=True)

    assert isinstance(registry.get("SCHNEIDER-A9N61652"), DcBreaker)
    assert "HUAWEI-SUN2000-6KTL-L1" in registry
    assert "NOPE" not in registry
    with pytest.raises(UnknownComponentError) as excinfo:
        registry.get("huawei-sun2000-6ktl-l")
    assert "HUAWEI-SUN2000-6KTL-L1" in excinfo.value.suggestions
    assert "did you mean" in str(excinfo.value)
    with pytest.raises(KeyError):
        registry.get("NOPE")


def test_find_filters_by_type_and_manufacturer() -> None:
    registry = ComponentRegistry.load(RECORDS, include_unreviewed=True)

    assert len(registry.find()) == 34
    assert len(registry.find(component_type="pv_module")) == 10
    assert len(registry.find(component_type="hybrid_inverter")) == 7
    assert len(registry.find(component_type="string_inverter")) == 7
    assert len(registry.find(manufacturer="huawei")) == 7
    assert len(registry.find(component_type="dc_breaker", manufacturer="Suntree")) == 9
    assert registry.find(component_type="pv_module", manufacturer="Huawei") == []
    ids = [c.component_id for c in registry]
    assert ids == sorted(ids)


def test_typed_accessors() -> None:
    registry = ComponentRegistry.load(RECORDS, include_unreviewed=True)
    assert all(isinstance(m, PVModule) for m in registry.modules())
    assert all(isinstance(i, Inverter) for i in registry.inverters())
    assert all(isinstance(b, DcBreaker) for b in registry.dc_breakers())


def test_registry_rejects_duplicate_component_ids() -> None:
    registry = ComponentRegistry.load(RECORDS, include_unreviewed=True)
    module = registry.modules()[0]
    with pytest.raises(CatalogueError, match="duplicate component_id"):
        ComponentRegistry([module, module])


def test_empty_records_folder_gives_an_empty_registry(tmp_path: Path) -> None:
    (tmp_path / "modules").mkdir()
    assert len(ComponentRegistry.load(tmp_path)) == 0


def test_load_from_one_file(tmp_path: Path) -> None:
    path = write(tmp_path, MODULE, mark_reviewed(raw(MODULE)))
    assert len(ComponentRegistry.load(path)) == 6


def test_catalogue_loads_in_under_100_ms() -> None:
    ComponentRegistry.load(RECORDS, include_unreviewed=True)  # warm the imports and caches
    timings = []
    for _ in range(5):
        start = time.perf_counter()
        registry = ComponentRegistry.load(RECORDS, include_unreviewed=True)
        timings.append(time.perf_counter() - start)
    assert len(registry) == 34
    assert min(timings) < 0.100, f"best of 5 loads took {min(timings) * 1000:.0f} ms"


def test_every_committed_record_is_listed_in_the_helpers() -> None:
    on_disk = {path.relative_to(RECORDS).as_posix() for path in RECORDS.rglob("*.yaml")}
    assert on_disk == set(ALL_RECORDS)
