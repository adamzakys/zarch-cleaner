"""Measuring how much disk space things actually occupy."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

ProgressCallback = Callable[[int], None]


def _entry_bytes(entry: os.DirEntry[str]) -> int:
    try:
        stat = entry.stat(follow_symlinks=False)
    except OSError:
        return 0
    blocks = getattr(stat, "st_blocks", None)
    if blocks is not None:
        return blocks * 512
    return stat.st_size


def path_bytes(path: str | os.PathLike[str], on_scanned: ProgressCallback | None = None) -> int:
    """Real disk usage of *path* in bytes.

    Directories are walked without following symlinks, so a link out of a cache
    directory contributes only the link itself and can never lead us astray.
    """
    root = Path(path)
    try:
        root_stat = root.stat(follow_symlinks=False)
    except OSError:
        return 0

    if not os.path.isdir(root) or root.is_symlink():
        blocks = getattr(root_stat, "st_blocks", None)
        return blocks * 512 if blocks is not None else root_stat.st_size

    total = 0
    stack = [str(root)]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    size = _entry_bytes(entry)
                    total += size
                    if on_scanned is not None:
                        on_scanned(1)
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def contents_bytes(path: str | os.PathLike[str], on_scanned: ProgressCallback | None = None) -> int:
    """Total disk usage of everything *inside* a directory."""
    total = 0
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                total += path_bytes(entry.path, on_scanned)
    except OSError:
        return 0
    return total


def human_size(size: int) -> str:
    """Format a byte count using IEC units, e.g. ``4,5 GB``."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}".replace(".", ",")
        value /= 1024
    return f"{value:.1f} TB"


def display_path(path: str | os.PathLike[str]) -> str:
    """Shorten a path for display by collapsing the home directory to ``~``."""
    text = str(path)
    home = os.path.expanduser("~")
    if text == home:
        return "~"
    if text.startswith(home + os.sep):
        return "~" + text[len(home) :]
    return text
