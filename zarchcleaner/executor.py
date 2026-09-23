"""Turning a selection of items into a completed run.

Dry-run is handled here as well: it produces the same report shape a real run
would, but no operation is ever performed.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable
from datetime import datetime, timezone

from gi.repository import GLib, GObject

from . import config, operations, privileges
from .models import ActionResult, CleanItem, RunReport

DRY_RUN_NOTE = "Pratinjau: tidak ada yang dihapus."


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class Executor(GObject.Object):
    __gsignals__ = {
        "status": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "result": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "finished": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }

    def __init__(self) -> None:
        super().__init__()
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, items: Iterable[CleanItem], dry_run: bool) -> None:
        if self.running:
            return
        selected = [item for item in items if item.available]
        if not selected:
            return
        self._cancel.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(selected, dry_run),
            name="zarchcleaner-run",
            daemon=True,
        )
        self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()

    def _run(self, items: list[CleanItem], dry_run: bool) -> None:
        report = RunReport(started_at=_now(), dry_run=dry_run)

        if dry_run:
            for item in items:
                self._record(report, ActionResult(item.id, item.title, True, item.size, DRY_RUN_NOTE))
        else:
            self._run_items(report, [item for item in items if not item.needs_root])
            self._run_root_items(report, [item for item in items if item.needs_root])

        report.finished_at = _now()
        config.save_report(report)
        self._emit("finished", report)

    def _run_items(self, report: RunReport, items: list[CleanItem]) -> None:
        for item in items:
            if self._cancel.is_set():
                return
            self._emit("status", f"Membersihkan {item.title}…")
            self._record(report, operations.execute(item))

    def _run_root_items(self, report: RunReport, items: list[CleanItem]) -> None:
        if not items or self._cancel.is_set():
            return

        self._emit("status", "Menunggu otorisasi untuk operasi yang butuh root…")
        reported: set[str] = set()

        def collect(result: ActionResult) -> None:
            reported.add(result.item_id)
            self._record(report, result)

        ran = privileges.run_privileged(items, collect)

        for item in items:
            if item.id in reported:
                continue
            message = (
                "Tidak dijalankan: otorisasi root dibatalkan."
                if not ran
                else "Helper root tidak melaporkan hasil untuk item ini."
            )
            self._record(report, ActionResult(item.id, item.title, False, 0, message))

    def _record(self, report: RunReport, result: ActionResult) -> None:
        report.results.append(result)
        self._emit("result", result)

    def _emit(self, signal: str, *args) -> None:
        GLib.idle_add(self.emit, signal, *args)
