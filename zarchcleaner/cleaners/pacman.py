"""Pacman package cache, orphaned packages and the pacman log."""

from __future__ import annotations

from pathlib import Path

from .. import config, procs, usage
from ..models import CleanItem, Kind, Risk
from .base import Cleaner

PACMAN_LOG = Path("/var/log/pacman.log")


class PacmanCleaner(Cleaner):
    id = "pacman"
    title = "Paket dan cache pacman"
    description = "Cache paket terunduh, paket orphan, dan log pacman."
    category = "Paket dan repositori"
    icon = "package-x-generic-symbolic"

    def scan(self) -> list[CleanItem]:
        items: list[CleanItem] = []
        if procs.command_exists("paccache"):
            items.extend(self._cache_items())
        else:
            items.append(
                self.unavailable(
                    "pacman-cache",
                    "Cache paket pacman",
                    "Dibutuhkan paccache untuk mengukur dan membersihkan cache.",
                    "paccache tidak ditemukan — install paket pacman-contrib.",
                )
            )
        items.append(self._orphans_item())
        items.append(self._log_item())
        return items

    def _cache_items(self) -> list[CleanItem]:
        keep = max(0, config.load().keep_cached_versions)
        cache_dirs = procs.pacman_cache_dirs()

        old_candidates, old_size = procs.paccache_scan(
            procs.paccache_argv(remove=False, keep=keep, verbose=True)
        )
        uninstalled_candidates, uninstalled_size = procs.paccache_scan(
            procs.paccache_argv(remove=False, keep=0, uninstalled=True, verbose=True)
        )
        all_candidates, all_size = procs.paccache_scan(
            procs.paccache_argv(remove=False, keep=0, verbose=True)
        )

        items = [
            CleanItem(
                id="pacman-cache-old",
                title="Versi lama paket terunduh",
                description=(
                    "Menjalankan paccache untuk membuang versi lama paket di cache "
                    f"pacman, menyisakan {keep} versi terbaru setiap paket. Selama "
                    "versi terbaru masih ada, paket bisa dipasang ulang tanpa "
                    "mengunduh."
                ),
                kind=Kind.COMMAND,
                command=procs.paccache_argv(remove=True, keep=keep),
                needs_root=True,
                risk=Risk.SAFE,
                enabled_default=True,
                measure_paths=cache_dirs,
                size=old_size,
                note=f"{len(old_candidates)} berkas kandidat",
            ),
            CleanItem(
                id="pacman-cache-uninstalled",
                title="Cache paket yang tidak terinstall",
                description=(
                    "Membuang seluruh berkas cache milik paket yang sudah tidak "
                    "terinstall. Paket yang masih terinstall tidak disentuh."
                ),
                kind=Kind.COMMAND,
                command=procs.paccache_argv(remove=True, keep=0, uninstalled=True),
                needs_root=True,
                risk=Risk.SAFE,
                enabled_default=False,
                measure_paths=cache_dirs,
                size=uninstalled_size,
                note=f"{len(uninstalled_candidates)} berkas kandidat",
            ),
            CleanItem(
                id="pacman-cache-all",
                title="Seluruh cache paket",
                description=(
                    "Mengosongkan cache paket sepenuhnya. Setelah ini paket tidak "
                    "bisa dipasang ulang secara offline dan downgrade tidak mungkin "
                    "tanpa mengunduh ulang."
                ),
                kind=Kind.COMMAND,
                command=procs.paccache_argv(remove=True, keep=0),
                needs_root=True,
                risk=Risk.CAUTION,
                enabled_default=False,
                measure_paths=cache_dirs,
                size=all_size,
                note=f"{len(all_candidates)} berkas kandidat",
            ),
        ]

        for item in items:
            if item.size == 0:
                item.available = False
                item.note = "Tidak ada kandidat untuk dibersihkan."
        return items

    def _orphans_item(self) -> CleanItem:
        packages, size = procs.pacman_orphans()
        title = "Paket orphan"
        description = (
            "Paket yang tidak lagi dibutuhkan paket lain dan tidak dipasang secara "
            "eksplisit. Diperiksa dengan `pacman -Qtdq` dan dihapus dengan "
            "`pacman -Rns`, termasuk paket dependensi yang menjadi yatim."
        )
        if not packages:
            return self.unavailable(
                "pacman-orphans",
                title,
                description,
                "Tidak ada paket orphan.",
                risk=Risk.DANGEROUS,
            )
        return CleanItem(
            id="pacman-orphans",
            title=f"Paket orphan ({len(packages)})",
            description=description,
            kind=Kind.PACMAN_REMOVE,
            packages=packages,
            needs_root=True,
            risk=Risk.DANGEROUS,
            enabled_default=False,
            size=size,
        )

    def _log_item(self) -> CleanItem:
        return CleanItem(
            id="pacman-log",
            title="Log pacman",
            description=(
                "Mengosongkan /var/log/pacman.log. Berkasnya tetap ada, tapi "
                "riwayat transaksi dan pemasangan paket akan hilang."
            ),
            kind=Kind.TRUNCATE,
            paths=[PACMAN_LOG],
            needs_root=True,
            risk=Risk.CAUTION,
            enabled_default=False,
            size=usage.path_bytes(PACMAN_LOG),
        )
