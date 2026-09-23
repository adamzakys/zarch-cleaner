"""Facts about the running system, shown in the header and the overview."""

from __future__ import annotations

import os
from pathlib import Path

from . import procs

OS_RELEASE = Path("/etc/os-release")


def _parse_os_release() -> dict[str, str]:
    try:
        content = OS_RELEASE.read_text(errors="replace")
    except OSError:
        return {}

    values: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        values[key.strip()] = raw.strip().strip('"').strip("'")
    return values


def distro_name() -> str:
    """The distribution's human-readable name, e.g. ``Arch Linux``."""
    values = _parse_os_release()
    return values.get("PRETTY_NAME") or values.get("NAME") or "Linux"


def kernel_release() -> str:
    return os.uname().release


def pacman_version() -> str:
    """Installed pacman version, or an empty string when it is unavailable."""
    ok, output = procs.run_ok(["pacman", "-Q", "pacman"])
    if not ok:
        return ""
    parts = output.split()
    return parts[1] if len(parts) >= 2 else ""


def summary() -> str:
    """One line describing the system, for the overview group."""
    parts = [distro_name(), f"kernel {kernel_release()}"]
    version = pacman_version()
    if version:
        parts.append(f"pacman {version}")
    return " · ".join(parts)
