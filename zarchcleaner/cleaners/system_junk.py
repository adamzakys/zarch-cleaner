"""System junk: journald logs, stale temporary files, thumbnails, trash."""

from __future__ import annotations

import os
import re
import stat
import time
from pathlib import Path

from .. import config, procs, usage
from ..models import CleanItem, Kind, Risk
from .base import Cleaner

THUMBNAILS_DIR = Path(os.path.expanduser("~/.cache/thumbnails"))
FONTCONFIG_DIR = Path(os.path.expanduser("~/.cache/fontconfig"))
TRASH_DIR = Path(os.path.expanduser("~/.local/share/Trash"))
USER_FLATPAK_DIR = Path(os.path.expanduser("~/.local/share/flatpak"))

TMP_DIRS: tuple[Path, ...] = (Path("/tmp"), Path("/var/tmp"))

#: Never touched: sockets and lock files belonging to running processes, and
#: directories managed by systemd or desktop sessions.
TMP_PROTECTED_NAMES = frozenset(
    {
        ".X11-unix",
        ".XIM-unix",
        ".ICE-unix",
        ".font-unix",
        ".Test-unix",
        "tmpfiles.d",
    }
)
TMP_PROTECTED_PREFIXES = (".X11-unix", "systemd-private-", "snap-private-tmp", ".org.chromium")

#: Names that suggest a live process is using the entry. Removing a lock file
#: belonging to a running process is harmful, so these are left alone.
TMP_PROTECTED_SUFFIXES = (".sock", ".lock", ".pid")

_VACUUM_RE = re.compile(r"^(?:time=\S+|size=\d+[KMG]?)$")


class SystemJunkCleaner(Cleaner):
    id = "system"
    title = "Sampah sistem"
    description = "Log journal, berkas sementara lama, thumbnail, dan trash."
    category = "Sampah sistem"
    icon = "user-trash-symbolic"

    def scan(self) -> list[CleanItem]:
        return [
            self._journal_item(),
            self._tmp_item(),
            self._thumbnails_item(),
            self._trash_item(),
            self._flatpak_item(),
            self._fontconfig_item(),
        ]

    def _journal_item(self) -> CleanItem:
        if not procs.command_exists("journalctl"):
            return self.unavailable(
                "journal-vacuum",
                "Log systemd journal",
                "Memangkas entri journal yang lama.",
                "journalctl tidak ditemukan.",
            )

        vacuum = config.load().journal_vacuum
        if not _VACUUM_RE.match(vacuum):
            # The value comes from a user-writable file, so it is validated
            # before it is ever passed to journalctl.
            vacuum = "time=2weeks"

        size = procs.journal_disk_usage()
        item = CleanItem(
            id="journal-vacuum",
            title="Log systemd journal",
            description=(
                f"Menjalankan `journalctl --vacuum-{vacuum}` untuk membuang entri "
                "journal yang lebih lama dari batas tersebut. Log terbaru tetap ada."
            ),
            kind=Kind.COMMAND,
            command=["journalctl", f"--vacuum-{vacuum}"],
            needs_root=True,
            risk=Risk.SAFE,
            enabled_default=True,
            measure_argv=["journalctl", "--disk-usage"],
            size=size,
            note=f"journal saat ini {usage.human_size(size)}",
        )
        if size == 0:
            item.available = False
            item.note = "Journal tidak memakai ruang apa pun."
        return item

    def _tmp_item(self) -> CleanItem:
        max_age = max(1, config.load().tmp_max_age_days)
        stale: list[Path] = []
        for base in TMP_DIRS:
            stale.extend(_stale_entries(base, max_age))

        freed = sum(usage.path_bytes(path) for path in stale)
        item = CleanItem(
            id="tmp-stale",
            title="Berkas sementara lama",
            description=(
                "Menghapus berkas di /tmp dan /var/tmp yang tidak diakses maupun "
                "diubah selama periode tersebut. Socket, lock file, dan direktori "
                "sesi sistem dilewati. Hanya lapisan teratas yang diperiksa, tidak "
                "masuk ke dalam direktori. Catatan: /tmp di sistem ini adalah tmpfs, "
                "jadi membersihkannya mengembalikan RAM, bukan ruang disk."
            ),
            kind=Kind.PATHS,
            paths=stale,
            needs_root=True,
            risk=Risk.CAUTION,
            enabled_default=False,
            size=freed,
            note=f"{len(stale)} berkas lebih tua dari {max_age} hari",
        )
        if not stale:
            item.available = False
            item.note = f"Tidak ada berkas lebih tua dari {max_age} hari."
        return item

    def _thumbnails_item(self) -> CleanItem:
        return self.contents_item(
            "thumbnails",
            "Cache thumbnail",
            "Thumbnail berkas yang dibuat file manager. Dibuat ulang saat "
            "direktori dibuka kembali.",
            [THUMBNAILS_DIR],
            enabled_default=True,
        )

    def _trash_item(self) -> CleanItem:
        if not procs.command_exists("gio"):
            return self.contents_item(
                "trash",
                "Trash",
                "Mengosongkan trash pengguna di ~/.local/share/Trash.",
                [TRASH_DIR],
                enabled_default=True,
                empty_note="Trash kosong.",
            )
        item = CleanItem(
            id="trash",
            title="Trash",
            description=(
                "Mengosongkan trash pengguna dengan `gio trash --empty`. Berkas "
                "yang dikosongkan di sini tidak bisa dipulihkan."
            ),
            kind=Kind.COMMAND,
            command=["gio", "trash", "--empty"],
            risk=Risk.SAFE,
            enabled_default=True,
            measure_paths=[TRASH_DIR],
            size=usage.path_bytes(TRASH_DIR),
        )
        if item.size == 0:
            item.available = False
            item.note = "Trash kosong."
        return item

    def _flatpak_item(self) -> CleanItem:
        if not procs.command_exists("flatpak"):
            return self.unavailable(
                "flatpak-unused",
                "Runtime flatpak tak terpakai",
                "Menghapus runtime yang tidak lagi dipakai aplikasi.",
                "flatpak tidak terpasang.",
            )
        return CleanItem(
            id="flatpak-unused",
            title="Runtime flatpak tak terpakai",
            description=(
                "Menjalankan `flatpak uninstall --unused -y` untuk membuang runtime "
                "yang tidak lagi dipakai aplikasi apa pun. Ukurannya hanya diketahui "
                "setelah perintah dijalankan, karena flatpak tidak menyediakan mode "
                "pratinjau. Runtime milik instalasi sistem mungkin meminta hak akses "
                "tambahan."
            ),
            kind=Kind.COMMAND,
            command=["flatpak", "uninstall", "--unused", "-y"],
            risk=Risk.SAFE,
            enabled_default=False,
            measure_paths=[USER_FLATPAK_DIR],
            note="Ukuran baru diketahui setelah dijalankan",
        )

    def _fontconfig_item(self) -> CleanItem:
        return self.contents_item(
            "fontconfig-cache",
            "Cache fontconfig",
            "Indeks font milik pengguna. Dibuat ulang otomatis, atau paksa dengan "
            "`fc-cache -f` bila ada font yang tidak muncul.",
            [FONTCONFIG_DIR],
        )


def _stale_entries(base: Path, max_age_days: int) -> list[Path]:
    """Top-level entries in *base* untouched for more than *max_age_days*."""
    cutoff = time.time() - max_age_days * 86400
    stale: list[Path] = []
    try:
        entries = list(os.scandir(base))
    except OSError:
        return stale

    for entry in entries:
        name = entry.name
        if name in TMP_PROTECTED_NAMES or name.startswith(TMP_PROTECTED_PREFIXES):
            continue
        if name.endswith(TMP_PROTECTED_SUFFIXES):
            continue
        try:
            info = entry.stat(follow_symlinks=False)
        except OSError:
            continue
        if stat.S_ISSOCK(info.st_mode) or stat.S_ISFIFO(info.st_mode):
            continue
        # Both access and modification time must be old. st_ctime is deliberately
        # not used: it changes whenever metadata is touched and would keep
        # long-forgotten files out of reach forever.
        if info.st_atime > cutoff or info.st_mtime > cutoff:
            continue
        # Paths owned by another user stay out of reach by default.
        if info.st_uid != os.getuid() and info.st_uid != 0:
            continue
        stale.append(Path(entry.path))
    return stale
