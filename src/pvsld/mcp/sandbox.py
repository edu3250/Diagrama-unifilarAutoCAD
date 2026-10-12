"""Output sandbox of the MCP server: the only place it ever writes (ADR-0001, risk "local attack
surface").

A tool call never carries a path. It carries a *name*, and the sandbox turns that name into
``<root>/<name>.dxf``. The name is validated, not sanitised: anything that could address another
directory, drive or Windows device (separators, ``..``, ``C:``, ``CON``) is refused with a message
Claude can act on, so an attempt is visible instead of silently rewritten.

Files are produced in a private staging folder inside the root and moved into place at the end, so
a crash never leaves a half-written drawing and a failed verification never publishes one.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "DEFAULT_OUTPUT_DIR",
    "OUTPUT_DIR_ENV",
    "OutputSandbox",
    "SandboxError",
    "validate_name",
]

OUTPUT_DIR_ENV = "PVSLD_OUTPUT_DIR"
DEFAULT_OUTPUT_DIR = "out"
MAX_NAME_LENGTH = 64
DEFAULT_NAME = "diagram"
STAGING_PREFIX = ".pvsld-staging-"

_NAME_PATTERN = re.compile(rf"[A-Za-z0-9_-]{{1,{MAX_NAME_LENGTH}}}")
_UNSAFE_CHARACTERS = re.compile(r"[^A-Za-z0-9_-]+")
# Names Windows treats as devices whatever the extension ("CON.dxf" opens the console).
_WINDOWS_DEVICES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)

NAME_RULE = (
    f"name must be 1 to {MAX_NAME_LENGTH} characters from A-Z, a-z, 0-9, '-' and '_' "
    "(no dots, spaces, path separators or drive letters) and must not be a Windows device name"
)


class SandboxError(ValueError):
    """A name or location is refused; the message says why and is safe to show to Claude."""


def validate_name(name: str) -> str:
    """Return ``name`` when it is a safe drawing name, else raise :class:`SandboxError`."""
    if not _NAME_PATTERN.fullmatch(name):
        raise SandboxError(f"invalid name {name!r}: {NAME_RULE}.")
    if name.upper() in _WINDOWS_DEVICES:
        raise SandboxError(f"invalid name {name!r}: it is a reserved Windows device name.")
    return name


def _default_name(spec: Mapping[str, Any]) -> str:
    """Derive a file name from ``project.id`` of an unvalidated spec; fall back to a constant."""
    project = spec.get("project")
    raw = project.get("id") if isinstance(project, Mapping) else None
    if not isinstance(raw, str):
        return DEFAULT_NAME
    cleaned = _UNSAFE_CHARACTERS.sub("_", raw).strip("_")[:MAX_NAME_LENGTH]
    try:
        return validate_name(cleaned) if cleaned else DEFAULT_NAME
    except SandboxError:
        return DEFAULT_NAME


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class OutputSandbox:
    """A resolved, absolute output root."""

    root: Path

    @classmethod
    def at(cls, directory: Path | str) -> OutputSandbox:
        """Sandbox rooted at ``directory`` (made absolute against the working directory)."""
        return cls(Path(directory).expanduser().resolve())

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> OutputSandbox:
        """``$PVSLD_OUTPUT_DIR`` when set and not blank, else ``./out`` of the working directory."""
        source = os.environ if environ is None else environ
        configured = source.get(OUTPUT_DIR_ENV, "").strip()
        return cls.at(configured or DEFAULT_OUTPUT_DIR)

    def drawing_name(self, requested: str | None, spec: Mapping[str, Any]) -> str:
        """The validated name asked for, or one derived from ``project.id`` of the spec."""
        return validate_name(requested) if requested is not None else _default_name(spec)

    def dxf_path(self, name: str) -> Path:
        """Where the drawing ``name`` is published; refuses anything that leaves the root."""
        target = self.root / f"{validate_name(name)}.dxf"
        # ``resolve`` follows a link planted at the target, so a symlink cannot redirect the write.
        if target.resolve().parent != self.root:
            raise SandboxError(f"{target.name} resolves outside the output directory.")
        return target

    def project_dir(self, name: str) -> Path:
        """The folder of the project ``name``; refuses anything outside the root."""
        target = self.root / validate_name(name)
        if target.resolve().parent != self.root:
            raise SandboxError(f"{target.name} resolves outside the output directory.")
        return target

    @contextmanager
    def staging(self) -> Iterator[Path]:
        """A private empty folder inside the root, removed on exit whatever happens."""
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise SandboxError(
                f"cannot create the output directory {self.root}: {error}"
            ) from error
        folder = self.root / f"{STAGING_PREFIX}{uuid.uuid4().hex[:8]}"
        folder.mkdir()
        try:
            yield folder
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def publish(self, staged: Path, target: Path) -> None:
        """Atomically move ``staged`` onto ``target`` (both inside the root).

        Raises:
            SandboxError: the target cannot be replaced, typically because the file is open in
                AutoCAD, which locks it on Windows.
        """
        try:
            staged.replace(target)
        except OSError as error:
            raise SandboxError(
                f"cannot write {target.name}: {error.strerror or error}. "
                "If the file is open in AutoCAD, close it and call the tool again."
            ) from error
