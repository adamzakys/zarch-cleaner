"""Thin wrappers around the external commands we rely on.

Every command runs with a C locale so parsing its output never depends on the
user's language settings.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

DEFAULT_TIMEOUT = 120

_ENV = {**os.environ, "LC_ALL": "C", "LANG": "C"}

_SIZE_RE = re.compile(r"([0-9][0-9.,]*)\s*([KMGTPE]?i?B?)\b", re.IGNORECASE)

# Bare single letters are treated as binary: that is what systemd and du use.
_SIZE_UNITS = {
    "": 1,
    "b": 1,
    "k": 1024,
    "kib": 1024,
    "kb": 1000,
    "m": 1024**2,
    "mib": 1024**2,
    "mb": 1000**2,
    "g": 1024**3,
    "gib": 1024**3,
    "gb": 1000**3,
    "t": 1024**4,
    "tib": 1024**4,
    "tb": 1000**4,
    "p": 1024**5,
    "pib": 1024**5,
    "pb": 1000**5,
}


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def run(
    argv: list[str],
    *,
    timeout: int = DEFAULT_TIMEOUT,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(arg) for arg in argv],
        capture_output=True,
        text=True,
        timeout=timeout,
        input=input_text,
        check=False,
        env=_ENV,
    )


def run_ok(argv: list[str], *, timeout: int = DEFAULT_TIMEOUT) -> tuple[bool, str]:
    """Run a command and return ``(succeeded, combined output)``."""
    try:
        proc = run(argv, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    output = f"{proc.stdout or ''}{proc.stderr or ''}".strip()
    return proc.returncode == 0, output


def parse_size(text: str) -> int:
    """Turn ``'4.47 GiB'`` / ``'49.3M'`` / ``'10.09 MiB'`` into bytes."""
    match = _SIZE_RE.search(text or "")
    if not match:
        return 0
    try:
        value = float(match.group(1).replace(",", "."))
    except ValueError:
        return 0
    unit = _SIZE_UNITS.get(match.group(2).lower())
    if unit is None:
        return 0
    return int(value * unit)


def pacman_cache_dirs() -> list[Path]:
    """CacheDir entries from pacman.conf, falling back to the built-in default."""
    dirs: list[Path] = []
    conf = Path("/etc/pacman.conf")
    try:
        content = conf.read_text(errors="replace")
    except OSError:
        content = ""
    for line in content.splitlines():
        match = re.match(r"\s*CacheDir\s*=\s*(.+?)\s*$", line)
        if match:
            dirs.append(Path(match.group(1)))
    return dirs or [Path("/var/cache/pacman/pkg")]


def paccache_argv(
    *,
    remove: bool,
    keep: int | None = None,
    uninstalled: bool = False,
    verbose: bool = False,
) -> list[str]:
    argv = ["paccache", "-r" if remove else "-d", "--nocolor"]
    if verbose:
        argv.append("-v")
    if keep is not None:
        argv.append(f"-k{keep}")
    if uninstalled:
        argv.append("-u")
    for cachedir in pacman_cache_dirs():
        argv += ["-c", str(cachedir)]
    return argv


def parse_paccache_output(output: str) -> tuple[list[Path], int]:
    """Parse a ``paccache -d -v`` run into ``(candidate files, reclaimable bytes)``."""
    candidates: list[Path] = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("==>") or line.startswith("warning:"):
            continue
        if ".pkg.tar" in line or line.endswith(".sig"):
            candidates.append(Path(line))

    saved = 0
    match = re.search(r"disk space saved:\s*(.+?)\)?\s*$", output, re.MULTILINE)
    if match:
        saved = parse_size(match.group(1))
    return candidates, saved


def paccache_scan(argv: list[str]) -> tuple[list[Path], int]:
    """Run a paccache dry run and report what it would remove."""
    _ok, output = run_ok(argv)
    return parse_paccache_output(output)


def pacman_orphans() -> tuple[list[str], int]:
    """Orphaned packages and their combined installed size."""
    _ok, output = run_ok(["pacman", "-Qtdq"])
    packages = [line.strip() for line in output.splitlines() if line.strip()]
    if not packages:
        return [], 0

    size = 0
    for start in range(0, len(packages), 200):
        chunk = packages[start : start + 200]
        _ok, info = run_ok(["pacman", "-Qi", *chunk])
        for line in info.splitlines():
            if line.startswith("Installed Size"):
                size += parse_size(line.partition(":")[2])
    return packages, size


def journal_disk_usage() -> int:
    _ok, output = run_ok(["journalctl", "--disk-usage"])
    match = re.search(r"take up\s+(.+?)\s+in the file system", output)
    return parse_size(match.group(1)) if match else 0
