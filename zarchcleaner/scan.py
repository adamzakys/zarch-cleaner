"""Background scanning.

Measuring caches touches thousands of files, so it runs off the main thread.
Signals are re-emitted on the main context via ``GLib.idle_add`` because GTK
must only be touched from the main thread.
"""

from __future__ import annotations

import threading

from gi.repository import GLib, GObject

from .cleaners import CLEANERS
from .models import CleanItem, Kind


class Scanner(GObject.Object):
    __gsignals__ = {
        # (item, cleaner_id)
        "item-found": (GObject.SignalFlags.RUN_FIRST, None, (object, str)),
        # (done, total, label)
        "progress": (GObject.SignalFlags.RUN_FIRST, None, (int, int, str)),
        "finished": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self) -> None:
        super().__init__()
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._generation = 0

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._cancel.clear()
        self._generation += 1
        generation = self._generation
        self._thread = threading.Thread(
            target=self._run,
            args=(generation,),
            name="zarchcleaner-scan",
            daemon=True,
        )
        self._thread.start()

    def cancel(self) -> None:
        """Stop emitting results from the current scan."""
        self._cancel.set()

    def _run(self, generation: int) -> None:
        total = len(CLEANERS)
        for index, cleaner in enumerate(CLEANERS, start=1):
            if self._cancelled(generation):
                return
            self._emit("progress", index - 1, total, cleaner.title)
            for item in self._scan_one(cleaner):
                if self._cancelled(generation):
                    return
                self._emit("item-found", item, cleaner.id)
            self._emit("progress", index, total, cleaner.title)
        if not self._cancelled(generation):
            self._emit("finished")

    def _scan_one(self, cleaner) -> list[CleanItem]:
        try:
            return cleaner.scan()
        except Exception as exc:  # one broken cleaner must not stop the rest
            return [
                CleanItem(
                    id=f"{cleaner.id}-error",
                    title=cleaner.title,
                    description=f"Pemindaian gagal: {exc}",
                    kind=Kind.PATHS,
                    available=False,
                    note="Gagal memindai.",
                )
            ]

    def _cancelled(self, generation: int) -> bool:
        return self._cancel.is_set() or generation != self._generation

    def _emit(self, signal: str, *args) -> None:
        GLib.idle_add(self.emit, signal, *args)
