"""Command-line behaviour of ``pvsld``: ``--version``, ``validate`` and ``generate``."""

from __future__ import annotations

import json
import shutil
import subprocess
import sysconfig
from pathlib import Path
from typing import Any

import pytest
import yaml

import pvsld
from pvsld.cli import main
from s1_helpers import EXAMPLE, load_example, mutated


def _write_spec(path: Path, spec: Any) -> Path:
    path.write_text(yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")
    return path


def _twelve_modules(spec: dict[str, Any]) -> None:
    for string in spec["strings"]:
        string["n_series"] = 12


# --- --version and usage ----------------------------------------------------------------------


def test_version_flag_prints_the_package_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == f"pvsld {pvsld.__version__}"


def test_missing_command_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main([])
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "validate" in err
    assert "generate" in err


def test_the_stage_2_0_smoke_command_is_gone(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["validate-example", str(EXAMPLE)])
    assert excinfo.value.code == 2


# --- validate ---------------------------------------------------------------------------------


def test_validate_accepts_the_sample(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", str(EXAMPLE)]) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("OK:")
    assert "mx-gd-2026.10" in captured.out
    assert "7.70 kWp" in captured.out
    assert captured.err == ""


def test_validate_reports_a_violated_rule_in_spanish_and_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_spec(tmp_path / "twelve.yaml", mutated(_twelve_modules))
    assert main(["validate", str(path)]) == 1
    err = capsys.readouterr().err
    assert err.startswith("FAILED:")
    assert "[E] VOLT-001 S1" in err
    assert "La rama S1 alcanza 640.2 V" in err
    assert "MX-C02" in err


def test_validate_dc_ac_thresholds_are_configurable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def eight(spec: dict[str, Any]) -> None:
        for string in spec["strings"]:
            string["n_series"] = 8

    path = _write_spec(tmp_path / "eight.yaml", mutated(eight))
    # default policy: 8.8 kWp / 6 kW = 1.47 -> warning only
    assert main(["validate", str(path)]) == 0
    assert "[W] STR-007 INV1" in capsys.readouterr().out
    assert main(["validate", str(path), "--dc-ac-warn", "1.3", "--dc-ac-error", "1.4"]) == 1
    assert "[E] STR-007 INV1" in capsys.readouterr().err
    assert main(["validate", str(path), "--dc-ac-warn", "1.6", "--dc-ac-error", "1.8"]) == 0
    assert "STR-007" not in capsys.readouterr().out


def test_validate_rejects_inconsistent_dc_ac_thresholds(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["validate", str(EXAMPLE), "--dc-ac-warn", "1.6", "--dc-ac-error", "1.4"]) == 1
    assert "warn_above <= error_above" in capsys.readouterr().err


def test_validate_json_prints_the_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_spec(tmp_path / "twelve.yaml", mutated(_twelve_modules))
    assert main(["validate", str(path), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is False
    assert report["findings"][0]["rule_id"] == "VOLT-001"
    assert main(["validate", str(EXAMPLE), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_validate_reports_every_schema_error_as_gen_001(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    spec = load_example()
    del spec["grounding"]
    del spec["utility"]
    assert main(["validate", str(_write_spec(tmp_path / "partial.yaml", spec))]) == 1
    err = capsys.readouterr().err
    assert err.count("GEN-001") == 2
    assert "grounding" in err
    assert "utility" in err


def test_validate_reads_json_files(tmp_path: Path) -> None:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(load_example(), default=str), encoding="utf-8")
    assert main(["validate", str(path)]) == 0


def test_validate_rejects_a_missing_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["validate", str(tmp_path / "nope.yaml")]) == 1
    assert "not found" in capsys.readouterr().err


def test_validate_reports_an_unreadable_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["validate", str(tmp_path)]) == 1  # a directory, not a file
    assert "cannot read" in capsys.readouterr().err


def test_validate_rejects_invalid_yaml(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    broken = tmp_path / "broken.yaml"
    broken.write_text("project: [unclosed\n", encoding="utf-8")
    assert main(["validate", str(broken)]) == 1
    assert "invalid" in capsys.readouterr().err


def test_validate_rejects_invalid_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert main(["validate", str(broken)]) == 1
    assert "invalid .json" in capsys.readouterr().err


@pytest.mark.parametrize("content", ["", "- just\n- a list\n", "42\n"])
def test_validate_rejects_a_non_mapping_document(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str
) -> None:
    spec_path = tmp_path / "not-a-mapping.yaml"
    spec_path.write_text(content, encoding="utf-8")
    assert main(["validate", str(spec_path)]) == 1
    assert "mapping" in capsys.readouterr().err


# --- generate ---------------------------------------------------------------------------------


def test_generate_writes_a_verified_dxf(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "nested" / "sld.dxf"
    assert main(["generate", str(EXAMPLE), "-o", str(output)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("OK: wrote")
    assert "attributes 157/157" in out
    assert "dangling ports 0" in out
    assert "entities on layer 0: 0" in out
    assert output.read_bytes().startswith(b"  0\nSECTION")
    assert not output.with_suffix(".png").exists()


def test_generate_with_png_also_writes_the_preview(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "sld.dxf"
    assert main(["generate", str(EXAMPLE), "-o", str(output), "--png"]) == 0
    assert "preview:" in capsys.readouterr().out
    assert output.with_suffix(".png").read_bytes().startswith(b"\x89PNG")


def test_generate_refuses_an_invalid_spec_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_spec(tmp_path / "twelve.yaml", mutated(_twelve_modules))
    output = tmp_path / "sld.dxf"
    assert main(["generate", str(path), "-o", str(output)]) == 1
    err = capsys.readouterr().err
    assert "nothing was written" in err
    assert "VOLT-001" in err
    assert not output.exists()


def test_generate_reports_a_missing_spec_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["generate", str(tmp_path / "nope.yaml"), "-o", str(tmp_path / "x.dxf")]) == 1
    assert "not found" in capsys.readouterr().err


def test_generate_reports_an_unwritable_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a folder", encoding="utf-8")
    assert main(["generate", str(EXAMPLE), "-o", str(blocker / "sld.dxf")]) == 1
    assert "cannot write" in capsys.readouterr().err


def test_generate_requires_an_output_path(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["generate", str(EXAMPLE)])
    assert excinfo.value.code == 2


def test_console_script_is_installed_and_runs() -> None:
    executable = shutil.which("pvsld", path=sysconfig.get_path("scripts"))
    assert executable is not None, "the 'pvsld' console script is not installed"
    completed = subprocess.run(
        [executable, "--version"], capture_output=True, text=True, check=True
    )
    assert completed.stdout.strip() == f"pvsld {pvsld.__version__}"


def test_console_script_validates_the_sample() -> None:
    executable = shutil.which("pvsld", path=sysconfig.get_path("scripts"))
    assert executable is not None
    completed = subprocess.run(
        [executable, "validate", str(EXAMPLE)], capture_output=True, text=True, check=True
    )
    assert completed.stdout.startswith("OK:")
