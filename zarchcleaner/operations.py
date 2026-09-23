"""The only place that actually deletes anything.

Both the unprivileged executor and the privileged helper call
:func:`execute`, so a deletion can never happen without passing the same
allowlist checks.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from . import procs, safety, usage
from .models import ActionResult, CleanItem, Kind

COMMAND_TIMEOUT = 900
PACMAN_TIMEOUT = 1800


class OperationError(Exception):
    """A cleaning step failed."""


def execute(item: CleanItem) -> ActionResult:
    """Perform *item* and report what happened.

    Measurements are taken before and after so the reported figure is space
    that really went away rather than an estimate.
    """
    before = measure(item)
    try:
        _perform(item)
    except safety.PathGuardError as exc:
        return _result(item, False, before, note=f"ditolak pengaman: {exc}")
    except (OSError, subprocess.SubprocessError, OperationError) as exc:
        return _result(item, False, before, note=str(exc))
    return _result(item, True, before)


def measure(item: CleanItem) -> int | None:
    """Current size of whatever *item* would free, or None if unmeasurable."""
    if item.measure_argv:
        _ok, output = procs.run_ok(item.measure_argv)
        return procs.parse_size(output)
    if item.measure_paths:
        return sum(usage.path_bytes(path) for path in item.measure_paths)
    if item.kind in (Kind.PATHS, Kind.CONTENTS, Kind.TRUNCATE):
        targets = item.contents_of if item.kind is Kind.CONTENTS else item.paths
        return sum(usage.path_bytes(target) for target in targets)
    return None


def _result(item: CleanItem, ok: bool, before: int | None, note: str = "") -> ActionResult:
    after = measure(item)
    if before is not None and after is not None:
        freed = max(0, before - after)
    else:
        freed = item.size
    return ActionResult(item_id=item.id, title=item.title, ok=ok, freed=freed, message=note)


def _perform(item: CleanItem) -> None:
    if item.kind is Kind.PATHS:
        for path in item.paths:
            _delete(path)
    elif item.kind is Kind.CONTENTS:
        for directory in item.contents_of:
            _clear(directory)
    elif item.kind is Kind.TRUNCATE:
        for path in item.paths:
            _truncate(path)
    elif item.kind is Kind.COMMAND:
        _run(item.command)
    elif item.kind is Kind.PACMAN_REMOVE:
        if not item.packages:
            return
        _run(["pacman", "-Rns", "--noconfirm", "--", *item.packages], timeout=PACMAN_TIMEOUT)
    else:
        raise OperationError(f"jenis operasi tidak dikenal: {item.kind}")


def _delete(path: Path) -> None:
    target = safety.require_safe(path)
    _remove(target)


def _clear(directory: Path) -> None:
    root = safety.require_safe(directory)
    if not root.is_dir() or root.is_symlink():
        return
    for child in list(root.iterdir()):
        # Anything the allowlist does not cover is left strictly alone.
        if not safety.is_safe_path(child):
            continue
        _remove(child)


def _remove(target: Path) -> None:
    if target.is_symlink() or not target.is_dir():
        target.unlink(missing_ok=True)
    else:
        shutil.rmtree(target, ignore_errors=False)


def _truncate(path: Path) -> None:
    target = safety.require_safe(path, safety.FILE_ROOTS, allow_root_itself=True)
    try:
        with open(target, "wb"):
            pass
    except IsADirectoryError as exc:
        raise OperationError(f"{target} bukan berkas biasa") from exc


def _run(argv: list[str], *, timeout: int = COMMAND_TIMEOUT) -> str:
    if not argv:
        raise OperationError("perintah kosong")
    try:
        proc = procs.run(argv, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise OperationError(f"perintah melebihi batas waktu: {' '.join(argv)}") from exc
    except OSError as exc:
        raise OperationError(str(exc)) from exc

    output = f"{proc.stdout or ''}{proc.stderr or ''}".strip()
    if proc.returncode != 0:
        detail = output.splitlines()[-1] if output else f"kode keluar {proc.returncode}"
        raise OperationError(detail)
    return output
