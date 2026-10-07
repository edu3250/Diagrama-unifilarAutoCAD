"""``pvsld catalogue validate | list | show``."""

from __future__ import annotations

from pathlib import Path

import pytest

from catalogue_helpers import MODULE, RECORDS, copy_records, mark_reviewed, raw, write
from pvsld.cli import main


def test_validate_accepts_the_committed_catalogue(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["catalogue", "validate", str(RECORDS)]) == 0
    out = capsys.readouterr().out
    assert "OK:" in out
    assert "6 record(s), 34 component(s)" in out
    assert "10 pv_module" in out
    assert "7 hybrid_inverter" in out


@pytest.fixture
def unreviewed(tmp_path: Path) -> Path:
    """A copy of the catalogue with every review field cleared."""
    return copy_records(tmp_path / "unreviewed", reviewed=False)


def test_the_committed_catalogue_is_fully_reviewed(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["catalogue", "validate", str(RECORDS), "--require-reviewed"]) == 0
    out = capsys.readouterr().out
    assert "34 component(s)" in out
    assert "0 unreviewed" in out


def test_validate_defaults_to_datasheets_records_of_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    copy_records(tmp_path / "datasheets" / "records", reviewed=True)
    monkeypatch.chdir(tmp_path)
    assert main(["catalogue", "validate"]) == 0
    assert "0 unreviewed" in capsys.readouterr().out


def test_validate_a_single_draft_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(tmp_path, "draft.yaml", raw(MODULE))
    assert main(["catalogue", "validate", str(path)]) == 0
    assert "1 record(s), 6 component(s)" in capsys.readouterr().out


def test_validate_names_file_variant_and_value_and_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = raw(MODULE)
    broken["variants"][0]["vmp_v"] = 60.0
    write(tmp_path, MODULE, broken)

    assert main(["catalogue", "validate", str(tmp_path)]) == 1

    err = capsys.readouterr().err
    assert "FAILED: 1 problem(s)" in err
    assert "jinko-jkm-66hl4m-bdv.yaml" in err
    assert "variant JINKO-JKM625N-66HL4M-BDV: vmp_v (60) must be lower than voc_v" in err


def test_validate_missing_folder_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["catalogue", "validate", str(tmp_path / "nowhere")]) == 1
    assert "no such records folder or file" in capsys.readouterr().err


def test_require_reviewed_fails_while_a_record_is_unreviewed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    copy_records(tmp_path, reviewed=False)
    assert main(["catalogue", "validate", str(tmp_path), "--require-reviewed"]) == 1
    assert "unreviewed:" in capsys.readouterr().err

    copy_records(tmp_path, reviewed=True)
    assert main(["catalogue", "validate", str(tmp_path), "--require-reviewed"]) == 0


def test_list_hides_unreviewed_records_by_default(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    copy_records(tmp_path, reviewed=False)
    write(tmp_path, MODULE, mark_reviewed(raw(MODULE)))  # only the Jinko record is approved

    assert main(["catalogue", "list", "--records", str(tmp_path)]) == 0

    captured = capsys.readouterr()
    assert "6 component(s)" in captured.out
    assert "JINKO-JKM640N-66HL4M-BDV" in captured.out
    assert "HUAWEI" not in captured.out
    assert "5 unreviewed record(s) skipped" in captured.err


def test_list_filters_by_type_and_manufacturer(
    unreviewed: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = ["catalogue", "list", "--records", str(unreviewed), "--include-unreviewed"]
    assert main([*args, "--type", "dc_breaker", "--manufacturer", "suntree"]) == 0
    out = capsys.readouterr().out
    assert "9 component(s)" in out
    assert "SUNTREE-SL7N-63-16A" in out
    assert "16 A" in out
    assert "UNREVIEWED" in out
    assert "SCHNEIDER" not in out


def test_list_describes_each_component_type(capsys: pytest.CaptureFixture[str]) -> None:
    args = ["catalogue", "list", "--records", str(RECORDS), "--include-unreviewed"]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "650 Wp" in out
    assert "6 kW AC, 9 kWp DC max" in out
    assert "34 component(s)" in out


def test_list_rejects_an_unknown_type() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["catalogue", "list", "--type", "toaster"])
    assert excinfo.value.code == 2


def test_list_reports_a_broken_catalogue(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "bad.yaml").write_text("- nope\n", encoding="utf-8")
    assert main(["catalogue", "list", "--records", str(tmp_path)]) == 1
    assert "must be a YAML mapping" in capsys.readouterr().err


def test_show_prints_the_expanded_component_as_yaml(
    unreviewed: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [
            "catalogue",
            "show",
            "HUAWEI-SUN2000-6KTL-L1",
            "--records",
            str(unreviewed),
            "--include-unreviewed",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert out.startswith("# HUAWEI-SUN2000-6KTL-L1 (hybrid_inverter, UNREVIEWED)")
    assert "max_pv_power_with_optimizers_wp: 10000.0" in out
    assert "max_input_voltage_v: 600.0" in out  # resolved from the family
    assert "reviewed_by" in out  # provenance travels with the component


def test_show_unknown_id_suggests_close_matches(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "catalogue",
            "show",
            "HUAWEI-SUN2000-6KTL",
            "--records",
            str(RECORDS),
            "--include-unreviewed",
        ]
    )
    assert code == 1
    err = capsys.readouterr().err
    assert "unknown component_id 'HUAWEI-SUN2000-6KTL'" in err
    assert "HUAWEI-SUN2000-6KTL-L1" in err


def test_show_prints_reviewed_status_and_reviewer(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["catalogue", "show", "SCHNEIDER-A9N61652", "--records", str(RECORDS)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# SCHNEIDER-A9N61652 (dc_breaker, reviewed)")
    assert "reviewed_by: edu3250" in out


def test_show_does_not_see_unreviewed_records_by_default(
    unreviewed: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["catalogue", "show", "SCHNEIDER-A9N61652", "--records", str(unreviewed)]) == 1
    assert "unknown component_id" in capsys.readouterr().err


def test_show_reports_a_broken_catalogue(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["catalogue", "show", "X", "--records", str(tmp_path / "nowhere")]) == 1
    assert "no such records folder" in capsys.readouterr().err
