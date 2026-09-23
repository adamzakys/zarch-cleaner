"""Caches owned by desktop applications: browsers, GPU shaders, indexers."""

from __future__ import annotations

import os
from pathlib import Path

from ..models import CleanItem, Risk
from .base import Cleaner

BROWSERS: tuple[tuple[str, str], ...] = (
    ("Brave", "~/.cache/BraveSoftware"),
    ("Thorium", "~/.cache/thorium"),
    ("Chromium", "~/.cache/chromium"),
    ("Google Chrome", "~/.cache/google-chrome"),
    ("Vivaldi", "~/.cache/vivaldi"),
    ("Microsoft Edge", "~/.cache/microsoft-edge"),
)

#: Only these directory names are ever cleaned. Profile data such as cookies,
#: logins, history, and local storage lives elsewhere and is never touched.
BROWSER_CACHE_DIRS = frozenset(
    {
        "Cache",
        "Code Cache",
        "GPUCache",
        "GrShaderCache",
        "ShaderCache",
        "DawnCache",
        "DawnGraphiteCache",
        "DawnWebGPUCache",
        "Media Cache",
    }
)

PROFILE_SEARCH_DEPTH = 3

SHADER_CACHE_GLOBS = (
    "~/.cache/mesa_shader_cache",
    "~/.cache/mesa_shader_cache_db",
    "~/.cache/qtshadercache-*",
    "~/.cache/nvidia/GLCache",
)

TRACKER_DIR = Path(os.path.expanduser("~/.cache/tracker3"))
GSTREAMER_DIR = Path(os.path.expanduser("~/.cache/gstreamer-1.0"))
ZED_DIR = Path(os.path.expanduser("~/.cache/zed"))


class AppCacheCleaner(Cleaner):
    id = "apps"
    title = "Cache aplikasi"
    description = "Cache browser, shader GPU, dan indeks aplikasi desktop."
    category = "Cache aplikasi"
    icon = "applications-graphics-symbolic"

    def scan(self) -> list[CleanItem]:
        items: list[CleanItem] = []
        items.extend(self._browser_items())
        items.append(self._shader_item())
        items.append(self._gstreamer_item())
        items.append(self._zed_item())
        items.append(self._tracker_item())
        return items

    def _browser_items(self) -> list[CleanItem]:
        items: list[CleanItem] = []
        for name, raw_root in BROWSERS:
            root = Path(os.path.expanduser(raw_root))
            caches = _browser_cache_paths(root)
            if not caches:
                continue
            items.append(
                self.contents_item(
                    f"browser-{name.lower().replace(' ', '-')}",
                    f"Cache {name}",
                    (
                        "Mengosongkan cache HTTP dan cache kode halaman web. Cookie, "
                        "login, riwayat, dan pengaturan profil tidak disentuh. Tutup "
                        "browser lebih dulu agar hasilnya maksimal."
                    ),
                    caches,
                    enabled_default=True,
                )
            )

        if not items:
            items.append(
                self.unavailable(
                    "browser-cache",
                    "Cache browser",
                    "Cache HTTP dan kode dari browser berbasis Chromium.",
                    "Tidak ada cache browser yang ditemukan.",
                )
            )
        return items

    def _shader_item(self) -> CleanItem:
        return self.contents_item(
            "gpu-shader-cache",
            "Cache shader GPU",
            "Cache kompilasi shader Mesa, Qt, dan NVIDIA. Dibuat ulang saat "
            "aplikasi dijalankan; aplikasi pertama kali dibuka mungkin terasa "
            "sedikit lebih lambat.",
            _glob_paths(SHADER_CACHE_GLOBS),
            enabled_default=True,
        )

    def _gstreamer_item(self) -> CleanItem:
        return self.contents_item(
            "gstreamer-cache",
            "Cache GStreamer",
            "Registry plugin GStreamer. Dibuat ulang saat pemutaran berikutnya.",
            [GSTREAMER_DIR],
        )

    def _zed_item(self) -> CleanItem:
        return self.contents_item(
            "zed-cache",
            "Cache Zed",
            "Cache editor Zed: indeks bahasa dan data sementara lainnya.",
            [ZED_DIR],
        )

    def _tracker_item(self) -> CleanItem:
        return self.contents_item(
            "tracker-index",
            "Indeks pencarian Tracker",
            "Basis data indeks pencarian berkas GNOME. Setelah dibersihkan Tracker "
            "akan mengindeks ulang, yang sementara waktu memakai CPU dan I/O.",
            [TRACKER_DIR],
            risk=Risk.CAUTION,
        )


def _child_dirs(path: Path) -> list[Path]:
    try:
        with os.scandir(path) as entries:
            return [
                Path(entry.path)
                for entry in entries
                if entry.is_dir(follow_symlinks=False)
            ]
    except OSError:
        return []


def _browser_cache_paths(root: Path) -> list[Path]:
    """Cache directories of every profile under a browser's cache root.

    Layouts differ between browsers (Brave nests one level deeper than Chrome),
    so the search walks a bounded number of levels looking for known cache
    directory names and never descends into a cache it already found.
    """
    found: list[Path] = []
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack:
        current, depth = stack.pop()
        if depth >= PROFILE_SEARCH_DEPTH:
            continue
        for child in _child_dirs(current):
            if child.name in BROWSER_CACHE_DIRS:
                found.append(child)
                continue
            stack.append((child, depth + 1))
    return sorted(found)


def _glob_paths(patterns: tuple[str, ...]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        expanded = Path(os.path.expanduser(pattern))
        if any(char in str(expanded) for char in "*?["):
            paths.extend(sorted(expanded.parent.glob(expanded.name)))
        elif expanded.is_dir():
            paths.append(expanded)
    return paths
