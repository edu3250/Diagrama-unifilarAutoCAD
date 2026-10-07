"""``pvsld size``: a YAML request in, a readable report (or JSON) and an optional spec out."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from pvsld.cli import main
from pvsld.service import load_spec_file
from pvsld.sizing import load_request
from s1_helpers import EXAMPLE, ROOT
from sizing_helpers import (
    FIXTURE_RECORDS,
    HUAWEI_5K,
    JINKO_650,
    SAMPLE_INVERTER,
    SAMPLE_MODULE,
)


def _request(tmp_path: Path, **fields: Any) -> Path:
    data: dict[str, Any] = {
        "module": SAMPLE_MODULE,
        "inverters": [SAMPLE_INVERTER],
        "target_dc_power_w": 13200,
        "template_file": str(EXAMPLE),
    }
    data.update(fields)
    path = tmp_path / "request.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def _size(*args: str | Path) -> int:
    return main(["size", *map(str, args), "--catalogue", str(FIXTURE_RECORDS)])


def test_size_prints_the_selection_the_rejections_and_the_todo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _size(_request(tmp_path)) == 0
    out = capsys.readouterr().out
    assert "SELECTED: YI-6000 2×8" in out
    assert "REJECTED:" in out
    assert "VOLT-001" in out
    assert "STR-007" in out
    assert "TODO 3.4b" in out


def test_size_writes_a_specification_that_validate_accepts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    spec_path = tmp_path / "sized.yaml"
    assert _size(_request(tmp_path), "-o", spec_path) == 0
    assert f"wrote {spec_path}" in capsys.readouterr().out
    assert spec_path.exists()
    assert main(["validate", str(spec_path)]) == 0


def test_size_can_write_the_specification_as_json(tmp_path: Path) -> None:
    spec_path = tmp_path / "sized.json"
    assert _size(_request(tmp_path), "-o", spec_path) == 0
    assert json.loads(spec_path.read_text(encoding="utf-8"))["schema_version"] == "0.1.0"
    assert main(["validate", str(spec_path)]) == 0


def test_size_json_prints_the_result(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _size(_request(tmp_path), "--json") == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is True
    assert data["selected"]["config"]["label"] == "2×8"
    assert data["selected"]["spec"]["schema_version"] == "0.1.0"


def test_size_fails_when_every_configuration_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request = _request(tmp_path, module=JINKO_650, inverters=[HUAWEI_5K], target_dc_power_w=12000)
    spec_path = tmp_path / "none.yaml"
    assert _size(request, "-o", spec_path) == 1
    captured = capsys.readouterr()
    assert "NO CANDIDATE" in captured.err
    assert "STR-004" in captured.err
    assert not spec_path.exists()


def test_size_applies_the_dc_ac_thresholds_of_the_request(tmp_path: Path) -> None:
    request = _request(tmp_path, dc_ac_policy={"warn_above": 1.3, "error_above": 1.4})
    spec_path = tmp_path / "sized.yaml"
    assert _size(request, "-o", spec_path) == 0
    sized = load_spec_file(spec_path)
    assert [s["n_series"] for s in sized["strings"]] == [7, 7]  # 2 x 8 is now above 1.40
    assert main(["validate", str(spec_path), "--dc-ac-warn", "1.3", "--dc-ac-error", "1.4"]) == 0


def test_size_reports_an_unknown_component(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _size(_request(tmp_path, module="JINKO-JKM650N-66HL4M-BD")) == 1
    err = capsys.readouterr().err
    assert err.startswith("error:")
    assert "did you mean JINKO-JKM650N-66HL4M-BDV" in err


def test_size_reports_a_bad_request_by_field(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _size(_request(tmp_path, max_candidates=0)) == 1
    assert "max_candidates" in capsys.readouterr().err


def test_size_reports_a_missing_request_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _size(tmp_path / "nope.yaml") == 1
    assert "not found" in capsys.readouterr().err


def test_size_reports_a_missing_catalogue(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["size", str(_request(tmp_path)), "--catalogue", str(tmp_path / "none")]) == 1
    assert "no such records folder" in capsys.readouterr().err


def test_size_needs_reviewed_records_unless_asked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    unreviewed = tmp_path / "records" / "modules"
    unreviewed.mkdir(parents=True)
    source = (FIXTURE_RECORDS / "modules" / "xm-550.yaml").read_text(encoding="utf-8")
    text = source.replace('reviewed_by: "test fixture"', "reviewed_by: null").replace(
        "review_date: 2026-10-07", "review_date: null"
    )
    (unreviewed / "xm-550.yaml").write_text(text, encoding="utf-8")
    inverters = tmp_path / "records" / "inverters"
    inverters.mkdir()
    (inverters / "yi-6000.yaml").write_text(
        (FIXTURE_RECORDS / "inverters" / "yi-6000.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    request = _request(tmp_path)
    records = tmp_path / "records"
    assert main(["size", str(request), "--catalogue", str(records)]) == 1
    assert "unknown component_id 'XM-550'" in capsys.readouterr().err
    args = ["size", str(request), "--catalogue", str(records), "--include-unreviewed"]
    assert main(args) == 0
    assert "unreviewed" in capsys.readouterr().out


def test_load_request_resolves_the_template_file_next_to_the_request(tmp_path: Path) -> None:
    (tmp_path / "base.yaml").write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    path = _request(tmp_path, template_file="base.yaml")
    request = load_request(path)
    assert request.site.t_min_c == -3
    assert request.utility.nominal_voltage_v == 220


def test_size_help_documents_the_request_fields(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["size", "--help"])
    assert exit_info.value.code == 0
    assert "--include-unreviewed" in capsys.readouterr().out


def test_the_committed_catalogue_sizes_the_owner_combination(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Jinko 650 W + Growatt MIN 5000TL-X2 straight from datasheets/records and the documented
    # example request (the records may still be unreviewed in develop: --include-unreviewed).
    spec_path = tmp_path / "sized.yaml"
    code = main(
        [
            "size",
            str(ROOT / "examples" / "sizing_jinko_growatt.yaml"),
            "--catalogue",
            str(ROOT / "datasheets" / "records"),
            "--include-unreviewed",
            "-o",
            str(spec_path),
        ]
    )
    assert code == 0
    assert "SELECTED: GROWATT-MIN-5000TL-X2 2×5" in capsys.readouterr().out
    assert main(["validate", str(spec_path)]) == 0
