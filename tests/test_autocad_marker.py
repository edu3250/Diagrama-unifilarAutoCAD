"""The ``autocad`` marker is skipped unless ``--run-autocad`` is given on Windows."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

CONFTEST_SOURCE = Path(__file__).with_name("conftest.py").read_text(encoding="utf-8")

INNER_TESTS = """
import pytest

@pytest.mark.autocad
def test_needs_autocad():
    pass

def test_plain():
    pass
"""


@pytest.mark.autocad
def test_dummy_autocad_test_only_runs_when_enabled(request: pytest.FixtureRequest) -> None:
    """Placeholder for real AutoCAD tests: reaching this body proves the gate opened."""
    assert request.config.getoption("--run-autocad")
    assert sys.platform == "win32"


@pytest.fixture
def inner(pytester: pytest.Pytester) -> pytest.Pytester:
    """A throw-away project that reuses this suite's conftest with a pretend platform."""
    pytester.makeini("[pytest]\nmarkers =\n    autocad: needs AutoCAD\n")
    pytester.makepyfile(test_inner=INNER_TESTS)
    return pytester


def _use_conftest(inner: pytest.Pytester, platform: str) -> None:
    inner.makeconftest(f"{CONFTEST_SOURCE}\n_platform = lambda: {platform!r}\n")


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_autocad_tests_are_skipped_by_default(inner: pytest.Pytester, platform: str) -> None:
    _use_conftest(inner, platform)
    result = inner.runpytest("-rs")
    result.assert_outcomes(passed=1, skipped=1)
    result.stdout.fnmatch_lines(["SKIPPED*--run-autocad*"])


def test_autocad_tests_are_skipped_on_non_windows_even_with_the_flag(
    inner: pytest.Pytester,
) -> None:
    _use_conftest(inner, "linux")
    result = inner.runpytest("-rs", "--run-autocad")
    result.assert_outcomes(passed=1, skipped=1)
    result.stdout.fnmatch_lines(["SKIPPED*only run on Windows*"])


def test_autocad_tests_run_on_windows_with_the_flag(inner: pytest.Pytester) -> None:
    _use_conftest(inner, "win32")
    inner.runpytest("--run-autocad").assert_outcomes(passed=2)


def test_selecting_only_autocad_tests_without_the_flag_is_not_a_failure(
    inner: pytest.Pytester,
) -> None:
    _use_conftest(inner, "win32")
    result = inner.runpytest("-m", "autocad")
    result.assert_outcomes(skipped=1)
    assert result.ret == pytest.ExitCode.OK
