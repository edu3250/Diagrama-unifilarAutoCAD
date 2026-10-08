"""Mutated records fail with a message that names the file, the field and the offending value."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from catalogue_helpers import BREAKER, INVERTER, MODULE, Mutation, raw, write
from pvsld.catalogue import CatalogueError, load_records, read_record


def _variant(data: dict[str, Any], index: int = 3) -> dict[str, Any]:
    variant: dict[str, Any] = data["variants"][index]
    return variant


def _vmp_above_voc(data: dict[str, Any]) -> None:
    _variant(data)["vmp_v"] = 52.0


def _imp_above_isc(data: dict[str, Any]) -> None:
    _variant(data)["imp_a"] = 16.5


def _power_mismatch(data: dict[str, Any]) -> None:
    _variant(data)["pmax_w"] = 600.0


def _efficiency_off(data: dict[str, Any]) -> None:
    _variant(data)["efficiency_pct"] = 21.0


def _positive_pmax_coefficient(data: dict[str, Any]) -> None:
    data["temp_coef_pmax_pct_per_c"] = 0.29


def _negative_isc_coefficient(data: dict[str, Any]) -> None:
    data["temp_coef_isc_pct_per_c"] = -0.045


def _coefficient_in_wrong_unit(data: dict[str, Any]) -> None:
    data["temp_coef_voc_pct_per_c"] = -25.0


def _bnpi_vmp_above_voc(data: dict[str, Any]) -> None:
    _variant(data)["bnpi"]["vmp_v"] = 60.0


def _duplicate_variant_id(data: dict[str, Any]) -> None:
    data["variants"][1]["component_id"] = data["variants"][0]["component_id"]


def _voc_above_system_voltage(data: dict[str, Any]) -> None:
    data["max_system_voltage_v"] = 49.0


def _bifacial_without_ratios(data: dict[str, Any]) -> None:
    del data["bifaciality_pct"]


def _unknown_field(data: dict[str, Any]) -> None:
    data["colour"] = "black"


def _missing_required_field(data: dict[str, Any]) -> None:
    del data["cells"]


def _bad_checksum(data: dict[str, Any]) -> None:
    data["source"]["sha256"] = "abc"


def _review_without_date(data: dict[str, Any]) -> None:
    data["source"]["reviewed_by"] = "Someone"
    data["source"]["review_date"] = None


def _mppt_window_above_max_input(data: dict[str, Any]) -> None:
    data["mppt_voltage_range_v"] = [90, 650]


def _operating_current_above_isc(data: dict[str, Any]) -> None:
    data["max_input_current_per_mppt_a"] = 20


def _rated_above_apparent(data: dict[str, Any]) -> None:
    _variant(data, 5)["rated_ac_power_w"] = 6000


def _ac_current_off(data: dict[str, Any]) -> None:
    _variant(data, 5)["max_ac_output_current_a"] = 15.0


def _hybrid_without_battery(data: dict[str, Any]) -> None:
    del data["battery"]


def _ambiguity_without_value(data: dict[str, Any]) -> None:
    _variant(data, 5)["max_pv_power_with_optimizers_ambiguous"] = True


def _optimizer_power_below_recommended(data: dict[str, Any]) -> None:
    _variant(data, 6)["max_pv_power_with_optimizers_wp"] = 8000


def _icu_rises_with_voltage(data: dict[str, Any]) -> None:
    data["breaking_capacity_dc"][1]["icu_ka"] = 6.0


def _capacity_above_rated_voltage(data: dict[str, Any]) -> None:
    data["breaking_capacity_dc"][1]["voltage_v"] = 1000


def _unsupported_type(data: dict[str, Any]) -> None:
    data["component_type"] = "fuse"


# (record, mutation, text the message must contain). Messages always start with the file name.
CASES: list[tuple[str, Mutation, str]] = [
    (
        MODULE,
        _vmp_above_voc,
        "variant JINKO-JKM640N-66HL4M-BDV: vmp_v (52) must be lower than voc_v",
    ),
    (MODULE, _imp_above_isc, "imp_a (16.5) must be lower than isc_a (16.32)"),
    (MODULE, _power_mismatch, "vmp_v x imp_a = 640.1 W differs 6.7% from pmax_w (600)"),
    (MODULE, _efficiency_off, "efficiency_pct (21) differs from pmax_w / area"),
    (MODULE, _positive_pmax_coefficient, "temp_coef_pmax_pct_per_c (0.29 %/degC) must be negative"),
    (MODULE, _negative_isc_coefficient, "temp_coef_isc_pct_per_c (-0.045 %/degC) must be positive"),
    (MODULE, _coefficient_in_wrong_unit, "temp_coef_voc_pct_per_c (-25 %/degC) is implausible"),
    (MODULE, _bnpi_vmp_above_voc, "bnpi: vmp_v (60) must be lower than voc_v"),
    (MODULE, _duplicate_variant_id, "duplicate variant component_id 'JINKO-JKM625N-66HL4M-BDV'"),
    (MODULE, _voc_above_system_voltage, "voc_v (49.88) exceeds max_system_voltage_v (49)"),
    (MODULE, _bifacial_without_ratios, "bifaciality_pct is required when bifacial is true"),
    (MODULE, _unknown_field, "colour: Extra inputs are not permitted"),
    (MODULE, _missing_required_field, "cells: Field required"),
    (MODULE, _bad_checksum, "source.sha256: String should match pattern"),
    (MODULE, _review_without_date, "reviewed_by and review_date must be both set or both null"),
    (INVERTER, _mppt_window_above_max_input, "mppt_voltage_range_v upper limit (650) exceeds"),
    (INVERTER, _operating_current_above_isc, "max_input_current_per_mppt_a (20) exceeds"),
    (INVERTER, _rated_above_apparent, "rated_ac_power_w (6000) exceeds max_apparent_power_va"),
    (
        INVERTER,
        _ac_current_off,
        "max_ac_output_current_a (15) does not match max_apparent_power_va",
    ),
    (INVERTER, _hybrid_without_battery, "a hybrid_inverter needs a battery port"),
    (INVERTER, _ambiguity_without_value, "max_pv_power_with_optimizers_ambiguous is set but"),
    (
        INVERTER,
        _optimizer_power_below_recommended,
        "max_pv_power_with_optimizers_wp (8000) is below",
    ),
    (
        BREAKER,
        _icu_rises_with_voltage,
        "Icu cannot rise with voltage (3 kA at 650 V, 6 kA at 800 V)",
    ),
    (
        BREAKER,
        _capacity_above_rated_voltage,
        "1000 V is above every rated voltage offered for any poles",
    ),
    (BREAKER, _unsupported_type, "component_type: 'fuse' is not supported"),
]


@pytest.mark.parametrize(
    ("relative", "mutate", "expected"), CASES, ids=[case[1].__name__.lstrip("_") for case in CASES]
)
def test_mutated_record_fails_with_file_field_and_value(
    tmp_path: Path, relative: str, mutate: Mutation, expected: str
) -> None:
    data = raw(relative)
    mutate(data)
    path = write(tmp_path, relative, data)

    with pytest.raises(CatalogueError) as excinfo:
        read_record(path)

    assert expected in str(excinfo.value)
    assert all(problem.startswith(f"{path}: ") for problem in excinfo.value.problems)


def test_unmutated_records_pass_the_same_path(tmp_path: Path) -> None:
    for relative in (MODULE, INVERTER, BREAKER):
        read_record(write(tmp_path, relative, raw(relative)))


def test_a_folder_load_reports_every_problem_of_every_file(tmp_path: Path) -> None:
    module = raw(MODULE)
    _vmp_above_voc(module)
    inverter = raw(INVERTER)
    _hybrid_without_battery(inverter)
    write(tmp_path, MODULE, module)
    write(tmp_path, INVERTER, inverter)

    with pytest.raises(CatalogueError) as excinfo:
        load_records(tmp_path)

    assert len(excinfo.value.problems) == 2
    assert "huawei-sun2000-ktl-l1.yaml" in excinfo.value.problems[0]
    assert "jinko-jkm-66hl4m-bdv.yaml" in excinfo.value.problems[1]


def test_duplicate_component_id_across_files_is_rejected(tmp_path: Path) -> None:
    write(tmp_path, MODULE, raw(MODULE))
    twin = raw(MODULE)
    twin["family_id"] = "JINKO-TWIN"
    write(tmp_path, "modules/jinko-twin.yaml", twin)

    with pytest.raises(CatalogueError, match="duplicate 'JINKO-JKM625N-66HL4M-BDV'") as excinfo:
        load_records(tmp_path)

    assert "also in" in str(excinfo.value)


def test_record_in_the_wrong_folder_is_rejected(tmp_path: Path) -> None:
    write(tmp_path, "inverters/jinko-jkm-66hl4m-bdv.yaml", raw(MODULE))
    with pytest.raises(CatalogueError, match="belongs in a folder named 'modules'"):
        load_records(tmp_path)


def test_file_name_must_match_the_family_id(tmp_path: Path) -> None:
    write(tmp_path, "modules/jinko.yaml", raw(MODULE))
    with pytest.raises(CatalogueError, match=r"file name must be jinko-jkm-66hl4m-bdv\.yaml"):
        load_records(tmp_path)


def test_a_single_file_is_not_subject_to_the_layout_rules(tmp_path: Path) -> None:
    """A draft can be validated wherever it sits, before it moves to datasheets/records/."""
    path = write(tmp_path, "draft.yaml", raw(MODULE))
    (record,) = load_records(path)
    assert record.family.family_id == "JINKO-JKM-66HL4M-BDV"


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("component_type: [unclosed", "invalid YAML"),
        ("- just\n- a list\n", "must be a YAML mapping, not list"),
        ("family_id: X\n", "component_type: None is not supported"),
    ],
)
def test_unreadable_or_untyped_files_are_reported(
    tmp_path: Path, content: str, expected: str
) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(CatalogueError, match=expected):
        read_record(path)


def test_missing_path_is_reported(tmp_path: Path) -> None:
    with pytest.raises(CatalogueError, match="no such records folder or file"):
        load_records(tmp_path / "nowhere")


def test_unreadable_file_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "latin1.yaml"
    path.write_bytes(b"title: caf\xe9\n")
    with pytest.raises(CatalogueError, match="cannot read the file"):
        read_record(path)


def test_catalogue_error_needs_a_problem() -> None:
    with pytest.raises(ValueError, match="at least one problem"):
        CatalogueError([])
