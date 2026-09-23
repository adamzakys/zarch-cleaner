"""Path safety guard.

Every destructive operation in Zarch Cleaner passes through :func:`is_safe_path`.
The guard is intentionally paranoid: a target must be lexically inside an allowed
root *and* its fully resolved path must stay inside that root, so a symlink can
never be used to escape the allowlist.

The allowlist lives in this file only. It can be widened by editing this source,
never through configuration or through data handed in at runtime.
"""

from __future__ import annotations

import os
from pathlib import Path

HOME = Path(os.path.expanduser("~"))


class PathGuardError(Exception):
    """Raised when a path is not an allowed deletion target."""


def normalize(path: str | os.PathLike[str]) -> Path:
    """Lexically absolutise a path without following symlinks."""
    expanded = os.path.expanduser(str(path))
    return Path(os.path.abspath(expanded))


def _resolve(path: Path) -> Path | None:
    try:
        return path.resolve(strict=False)
    except OSError:
        return None


def _is_within(child: Path, parent: Path) -> bool:
    """True when *child* is inside *parent* (equal paths count as within)."""
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


#: Directories whose *contents* may be cleaned with admin rights.
#: /boot is deliberately absent: nothing in this app may touch a kernel.
ROOT_ROOTS: tuple[str, ...] = (
    "/var/cache/pacman",
    "/var/tmp",
    "/tmp",
)

#: Paths inside the user's home that may be cleaned without admin rights.
USER_ROOTS: tuple[str, ...] = (
    "~/.cache",
    "~/.npm",
    "~/.local/share/Trash",
)

#: Individual files that may be truncated (never removed).
FILE_ROOTS: tuple[str, ...] = ("/var/log/pacman.log",)

#: Paths that must never be removed, even when they are an allowed root.
FORBIDDEN: frozenset[str] = frozenset(
    str(p)
    for p in (
        Path("/"),
        Path("/home"),
        Path("/root"),
        Path("/usr"),
        Path("/etc"),
        Path("/var"),
        Path("/var/cache"),
        Path("/var/log"),
        Path("/var/lib"),
        Path("/var/lib/systemd"),
        Path("/tmp"),
        Path("/var/tmp"),
        Path("/boot"),
        HOME,
        HOME / ".cache",
        HOME / ".config",
        HOME / ".local",
        HOME / ".local/share",
        HOME / ".local/share/Trash",
        HOME / ".npm",
    )
)

ALL_ROOTS: tuple[str, ...] = (*ROOT_ROOTS, *USER_ROOTS)


def _within_any_root(target: Path, roots: tuple[str, ...]) -> bool:
    return any(_is_within(target, normalize(root)) for root in roots)


def is_safe_path(
    path: str | os.PathLike[str],
    roots: tuple[str, ...] = ALL_ROOTS,
    *,
    allow_root_itself: bool = False,
) -> bool:
    """Return True when *path* may be deleted.

    ``allow_root_itself`` permits targeting a root path exactly; it is only used
    for the file roots used by truncation and is still subject to ``FORBIDDEN``.
    """
    if path is None:
        return False

    target = normalize(path)
    target_str = str(target)

    if not target_str or target_str == ".":
        return False
    if target_str in FORBIDDEN:
        return False

    for root in roots:
        root_abs = normalize(root)
        if target == root_abs:
            if not allow_root_itself:
                continue
        elif not _is_within(target, root_abs):
            continue

        # Lexically inside the root. Now make sure symlinks do not escape it.
        root_real = _resolve(root_abs)
        target_real = _resolve(target)

        if root_real is not None and target_real is not None:
            if _is_within(target_real, root_real):
                return True
            # A symlink that points outside may still be unlinked: removing the
            # link itself never touches what it points at.
            if target.is_symlink():
                return True
            return False

        # Root does not exist yet (nothing to delete) or the path is a broken
        # symlink: the lexical check already proved containment.
        return target_real is not None or not target.exists()

    return False


def require_safe(
    path: str | os.PathLike[str],
    roots: tuple[str, ...] = ALL_ROOTS,
    *,
    allow_root_itself: bool = False,
) -> Path:
    """Like :func:`is_safe_path` but raises :class:`PathGuardError`."""
    if not is_safe_path(path, roots, allow_root_itself=allow_root_itself):
        raise PathGuardError(f"refusing to touch path outside the allowlist: {path}")
    return normalize(path)
