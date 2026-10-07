"""Invariants of the committed catalogue that hold whatever products it contains.

No counts and no file names here: adding a datasheet record must never require editing a test.
"""

from __future__ import annotations

import time

import pytest

from catalogue_helpers import REAL_RECORDS
from pvsld.catalogue import ComponentRegistry, LoadedRecord, load_records


@pytest.fixture(scope="module")
def records() -> list[LoadedRecord]:
    return load_records(REAL_RECORDS)


def test_every_record_file_validates_and_is_discovered(records: list[LoadedRecord]) -> None:
    on_disk = sorted(REAL_RECORDS.rglob("*.yaml"))
    assert on_disk, "datasheets/records has no record at all"
    assert sorted(record.path for record in records) == on_disk


def test_component_ids_are_unique_across_the_catalogue(records: list[LoadedRecord]) -> None:
    ids = [v.component_id for record in records for v in record.family.variants]
    assert len(ids) == len(set(ids))


def test_each_family_expands_to_one_component_per_variant(records: list[LoadedRecord]) -> None:
    for record in records:
        components = record.family.expand()
        assert [c.component_id for c in components] == [
            v.component_id for v in record.family.variants
        ], record.path
        assert {c.family_id for c in components} == {record.family.family_id}


def test_registry_holds_every_variant_of_every_record(records: list[LoadedRecord]) -> None:
    registry = ComponentRegistry.from_records(records, include_unreviewed=True)
    assert len(registry) == sum(len(record.family.variants) for record in records)
    assert all(component.component_id in registry for component in registry)


def test_catalogue_loads_in_under_100_ms() -> None:
    ComponentRegistry.load(REAL_RECORDS, include_unreviewed=True)  # warm the imports and caches
    timings = []
    for _ in range(5):
        start = time.perf_counter()
        ComponentRegistry.load(REAL_RECORDS, include_unreviewed=True)
        timings.append(time.perf_counter() - start)
    assert min(timings) < 0.100, f"best of 5 loads took {min(timings) * 1000:.0f} ms"
