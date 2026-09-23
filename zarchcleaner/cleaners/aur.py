"""Build caches left behind by AUR helpers."""

from __future__ import annotations

import os
from pathlib import Path

from ..models import CleanItem
from .base import Cleaner

HELPER_CACHES: tuple[tuple[str, str], ...] = (
    ("yay", "~/.cache/yay"),
    ("paru", "~/.cache/paru"),
    ("pikaur", "~/.cache/pikaur"),
    ("trizen", "~/.cache/trizen"),
)


class AurBuildCacheCleaner(Cleaner):
    id = "aur"
    title = "Build cache AUR"
    description = "Sumber dan direktori build yang ditinggalkan AUR helper."
    category = "Paket dan repositori"
    icon = "package-x-generic-symbolic"

    def scan(self) -> list[CleanItem]:
        items: list[CleanItem] = []
        for helper, raw_path in HELPER_CACHES:
            cache = Path(os.path.expanduser(raw_path))
            item = self.contents_item(
                f"aur-{helper}",
                f"Build cache {helper}",
                (
                    f"Mengosongkan isi {cache}: sumber paket, direktori build, dan "
                    f"cache internal {helper}. Paket yang sudah terinstall tidak "
                    "terpengaruh; berkas akan diunduh ulang saat dibutuhkan."
                ),
                [cache],
                enabled_default=True,
            )
            if item.available:
                items.append(item)

        if not items:
            items.append(
                self.unavailable(
                    "aur-cache",
                    "Build cache AUR",
                    "Cache milik yay, paru, pikaur, dan trizen.",
                    "Tidak ada build cache AUR helper yang ditemukan.",
                )
            )
        return items
