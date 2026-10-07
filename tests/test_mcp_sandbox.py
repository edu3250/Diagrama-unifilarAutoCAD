"""The output sandbox: names are validated, nothing leaves the root, staging is private."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pvsld.mcp.sandbox import (
    DEFAULT_NAME,
    MAX_NAME_LENGTH,
    OUTPUT_DIR_ENV,
    STAGING_PREFIX,
    OutputSandbox,
    SandboxError,
    sha256_of_file,
    validate_name,
)


@pytest.mark.parametrize(
    "name",
    ["PV-2026-0001", "plano_1", "A", "x" * MAX_NAME_LENGTH, "abc123"],
)
def test_safe_names_are_accepted_unchanged(name: str) -> None:
    assert validate_name(name) == name


@pytest.mark.parametrize(
    "name",
    [
        "",
        "x" * (MAX_NAME_LENGTH + 1),
        "../evil",
        "..\\evil",
        "..",
        ".",
        "a/b",
        "a\\b",
        "/etc/passwd",
        "C:\\Windows\\win",
        "C:evil",
        "\\\\server\\share\\x",
        "name.dxf",
        ".hidden",
        "a b",
        "a\x00b",
        "ñandú",
        "name\n",
    ],
)
def test_names_that_can_address_another_place_are_refused(name: str) -> None:
    with pytest.raises(SandboxError, match="invalid name"):
        validate_name(name)


@pytest.mark.parametrize("name", ["CON", "con", "NUL", "Aux", "PRN", "COM1", "lpt9"])
def test_windows_device_names_are_refused_on_every_platform(name: str) -> None:
    with pytest.raises(SandboxError, match="reserved Windows device name"):
        validate_name(name)


def test_the_default_root_is_out_under_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(OUTPUT_DIR_ENV, raising=False)
    assert OutputSandbox.from_environment().root == (tmp_path / "out").resolve()


def test_the_environment_variable_sets_the_root(tmp_path: Path) -> None:
    sandbox = OutputSandbox.from_environment({OUTPUT_DIR_ENV: str(tmp_path / "elsewhere")})
    assert sandbox.root == (tmp_path / "elsewhere").resolve()


def test_a_blank_environment_variable_falls_back_to_the_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert (
        OutputSandbox.from_environment({OUTPUT_DIR_ENV: "  "}).root == (tmp_path / "out").resolve()
    )


def test_an_explicit_name_is_validated(tmp_path: Path) -> None:
    sandbox = OutputSandbox.at(tmp_path)
    assert sandbox.drawing_name("plano-1", {}) == "plano-1"
    with pytest.raises(SandboxError):
        sandbox.drawing_name("../plano", {})


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ({"project": {"id": "PV-2026-0001"}}, "PV-2026-0001"),
        ({"project": {"id": "PV 2026/0001"}}, "PV_2026_0001"),
        ({"project": {"id": "../../etc"}}, "etc"),
        ({"project": {"id": "x" * 100}}, "x" * MAX_NAME_LENGTH),
        ({"project": {"id": "///"}}, DEFAULT_NAME),
        ({"project": {"id": "CON"}}, DEFAULT_NAME),
        ({"project": {"id": 7}}, DEFAULT_NAME),
        ({"project": "not a mapping"}, DEFAULT_NAME),
        ({}, DEFAULT_NAME),
    ],
)
def test_the_default_name_is_derived_from_the_project_id(
    tmp_path: Path, spec: dict[str, object], expected: str
) -> None:
    assert OutputSandbox.at(tmp_path).drawing_name(None, spec) == expected


def test_the_dxf_path_is_a_direct_child_of_the_root(tmp_path: Path) -> None:
    sandbox = OutputSandbox.at(tmp_path)
    assert sandbox.dxf_path("plano") == sandbox.root / "plano.dxf"


def test_a_link_planted_at_the_target_cannot_redirect_the_write(tmp_path: Path) -> None:
    sandbox = OutputSandbox.at(tmp_path / "root")
    sandbox.root.mkdir()
    outside = tmp_path / "outside.dxf"
    outside.write_text("secret", encoding="utf-8")
    try:
        (sandbox.root / "plano.dxf").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("this account cannot create symbolic links")
    with pytest.raises(SandboxError, match="outside the output directory"):
        sandbox.dxf_path("plano")


def test_a_target_that_resolves_elsewhere_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = OutputSandbox.at(tmp_path / "root")
    real_resolve = Path.resolve

    def resolve_to_outside(self: Path, strict: bool = False) -> Path:
        if self.suffix == ".dxf":
            return tmp_path / "outside.dxf"
        return real_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "resolve", resolve_to_outside)
    with pytest.raises(SandboxError, match="outside the output directory"):
        sandbox.dxf_path("plano")


def test_staging_is_private_and_removed_on_exit(tmp_path: Path) -> None:
    sandbox = OutputSandbox.at(tmp_path / "root")
    with sandbox.staging() as first, sandbox.staging() as second:
        assert first != second
        assert first.parent == sandbox.root
        assert first.name.startswith(STAGING_PREFIX)
        (first / "partial.dxf").write_text("x", encoding="utf-8")
    assert list(sandbox.root.iterdir()) == []


def test_staging_is_removed_when_the_body_raises(tmp_path: Path) -> None:
    sandbox = OutputSandbox.at(tmp_path / "root")
    with pytest.raises(RuntimeError), sandbox.staging():
        raise RuntimeError("boom")
    assert list(sandbox.root.iterdir()) == []


def test_staging_reports_a_root_that_cannot_be_created(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("not a folder", encoding="utf-8")
    with (
        pytest.raises(SandboxError, match="cannot create the output directory"),
        OutputSandbox.at(blocker / "inside").staging(),
    ):
        pytest.fail("the body must not run")


def test_publish_moves_the_file_and_replaces_an_existing_one(tmp_path: Path) -> None:
    sandbox = OutputSandbox.at(tmp_path)
    target = sandbox.dxf_path("plano")
    target.write_text("old", encoding="utf-8")
    with sandbox.staging() as stage:
        staged = stage / "plano.dxf"
        staged.write_text("new", encoding="utf-8")
        sandbox.publish(staged, target)
    assert target.read_text(encoding="utf-8") == "new"


def test_publish_explains_a_file_that_cannot_be_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def locked(self: Path, target: Path) -> Path:
        raise PermissionError(13, "Permiso denegado")

    monkeypatch.setattr(Path, "replace", locked)
    sandbox = OutputSandbox.at(tmp_path)
    with pytest.raises(SandboxError, match="open in AutoCAD"):
        sandbox.publish(tmp_path / "a.dxf", sandbox.dxf_path("plano"))


def test_sha256_of_file_matches_hashlib(tmp_path: Path) -> None:
    data = b"abc" * 1_000_000
    path = tmp_path / "blob"
    path.write_bytes(data)
    assert sha256_of_file(path) == hashlib.sha256(data).hexdigest()
