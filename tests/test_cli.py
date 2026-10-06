"""Command-line behaviour of ``pvsld`` (``--version`` and ``validate-example``)."""

from __future__ import annotations

import shutil
import subprocess
import sysconfig
from pathlib import Path
from typing import Any

import pytest
import yaml

import pvsld
from pvsld.cli import REQUIRED_TOP_LEVEL_SECTIONS, main


def _write_spec(path: Path, spec: Any) -> Path:
    path.write_text(yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")
    return path


@pytest.fixture
def complete_spec() -> dict[str, Any]:
    spec: dict[str, Any] = {section: {} for section in REQUIRED_TOP_LEVEL_SECTIONS}
    spec["schema_version"] = "0.1.0"
    return spec


def test_version_flag_prints_the_package_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == f"pvsld {pvsld.__version__}"


def test_missing_command_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main([])
    assert excinfo.value.code == 2
    assert "validate-example" in capsys.readouterr().err


def test_validate_example_accepts_a_file_with_all_sections(
    tmp_path: Path, complete_spec: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    spec_path = _write_spec(tmp_path / "ok.yaml", complete_spec)
    assert main(["validate-example", str(spec_path)]) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("OK:")
    assert "0.1.0" in captured.out
    assert captured.err == ""


def test_validate_example_tolerates_extra_sections(
    tmp_path: Path, complete_spec: dict[str, Any]
) -> None:
    complete_spec["transformer"] = {}
    assert main(["validate-example", str(_write_spec(tmp_path / "mt.yaml", complete_spec))]) == 0


def test_validate_example_lists_every_missing_section(
    tmp_path: Path, complete_spec: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    del complete_spec["grounding"]
    del complete_spec["utility"]
    spec_path = _write_spec(tmp_path / "partial.yaml", complete_spec)
    assert main(["validate-example", str(spec_path)]) == 1
    err = capsys.readouterr().err
    assert err.startswith("error:")
    assert "grounding" in err
    assert "utility" in err


def test_validate_example_rejects_a_missing_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["validate-example", str(tmp_path / "nope.yaml")]) == 1
    assert "not found" in capsys.readouterr().err


def test_validate_example_reports_an_unreadable_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["validate-example", str(tmp_path)]) == 1  # a directory, not a file
    assert "cannot read" in capsys.readouterr().err


def test_validate_example_rejects_invalid_yaml(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = tmp_path / "broken.yaml"
    broken.write_text("project: [unclosed\n", encoding="utf-8")
    assert main(["validate-example", str(broken)]) == 1
    assert "invalid YAML" in capsys.readouterr().err


@pytest.mark.parametrize("content", ["", "- just\n- a list\n", "42\n"])
def test_validate_example_rejects_a_non_mapping_document(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str
) -> None:
    spec_path = tmp_path / "not-a-mapping.yaml"
    spec_path.write_text(content, encoding="utf-8")
    assert main(["validate-example", str(spec_path)]) == 1
    assert "mapping" in capsys.readouterr().err


def test_console_script_is_installed_and_runs() -> None:
    executable = shutil.which("pvsld", path=sysconfig.get_path("scripts"))
    assert executable is not None, "the 'pvsld' console script is not installed"
    completed = subprocess.run(
        [executable, "--version"], capture_output=True, text=True, check=True
    )
    assert completed.stdout.strip() == f"pvsld {pvsld.__version__}"
