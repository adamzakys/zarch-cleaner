"""Widget-level tests.

They need a display, so they are skipped when there is none. Building the
dialogs matters: without these, a broken detail or confirmation dialog would
only show up when a user clicked it.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

HAVE_DISPLAY = bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"))

if HAVE_DISPLAY:
    from zarchcleaner.gilib import Adw, Gtk

    from zarchcleaner.models import CleanItem, Kind, Risk
    from zarchcleaner.ui.cleaner_row import CleanerRow
    from zarchcleaner.ui.confirm_dialog import CONFIRM_PHRASE, ConfirmDialog
    from zarchcleaner.ui.details_dialog import DetailsDialog
    from zarchcleaner.ui.summary_bar import SummaryBar


def _item(**overrides) -> CleanItem:
    base = {
        "id": "item",
        "title": "Judul item",
        "description": "Penjelasan.",
        "kind": Kind.CONTENTS,
        "contents_of": [Path("/tmp/example")],
        "measure_paths": [Path("/tmp/example")],
        "size": 1024,
    }
    base.update(overrides)
    return CleanItem(**base)


@unittest.skipUnless(HAVE_DISPLAY, "butuh display untuk membuat widget GTK")
class WidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Gtk.init()
        try:
            Adw.init()
        except Exception:
            pass

    def test_row_defaults_follow_enabled_default(self):
        on = CleanerRow(_item(enabled_default=True), lambda _item: None)
        off = CleanerRow(_item(enabled_default=False), lambda _item: None)
        self.assertTrue(on.selected)
        self.assertFalse(off.selected)

    def test_row_selection_is_writable(self):
        row = CleanerRow(_item(), lambda _item: None)
        self.assertFalse(row.selected)
        row.set_selected(True)
        self.assertTrue(row.selected)

    def test_row_emits_selection_changed(self):
        row = CleanerRow(_item(), lambda _item: None)
        calls: list[int] = []
        row.connect("selection-changed", lambda *_: calls.append(1))
        row.set_selected(True)
        self.assertEqual(len(calls), 1)

    def test_unavailable_row_has_no_checkbox(self):
        row = CleanerRow(_item(available=False, note="Kosong."), lambda _item: None)
        self.assertIsNone(row._check)
        self.assertFalse(row.selected)
        self.assertFalse(row.get_sensitive())

    def test_row_title_with_ampersand_does_not_break_markup(self):
        # ActionRow titles are parsed as Pango markup; escaping must hold.
        row = CleanerRow(_item(title="Paket & repositori <x>"), lambda _item: None)
        self.assertIn("&", row.get_title())

    def test_details_dialog_builds_for_every_kind(self):
        items = [
            _item(),
            _item(id="paths", kind=Kind.PATHS, paths=[Path("/tmp/a")]),
            _item(
                id="cmd",
                kind=Kind.COMMAND,
                command=["journalctl", "--vacuum-time=2weeks"],
                needs_root=True,
            ),
            _item(id="trunc", kind=Kind.TRUNCATE, paths=[Path("/var/log/pacman.log")]),
            _item(
                id="orphans",
                kind=Kind.PACMAN_REMOVE,
                packages=["libfoo", "libbar"],
                risk=Risk.DANGEROUS,
            ),
        ]
        for item in items:
            with self.subTest(item=item.id):
                dialog = DetailsDialog(item)
                self.assertIsNotNone(dialog.get_child())

    def test_details_dialog_handles_a_long_package_list(self):
        packages = [f"pkg-{index}" for index in range(500)]
        dialog = DetailsDialog(
            _item(id="big", kind=Kind.PACMAN_REMOVE, packages=packages, risk=Risk.DANGEROUS)
        )
        self.assertIsNotNone(dialog.get_child())

    def test_confirm_dialog_blocks_until_the_phrase_is_typed(self):
        dangerous = _item(id="danger", risk=Risk.DANGEROUS, needs_root=True)
        confirmed: list[bool] = []
        dialog = ConfirmDialog([dangerous], dry_run=False, on_confirm=lambda: confirmed.append(True))
        closed: list[bool] = []
        dialog.close = lambda: closed.append(True)

        self.assertIsNotNone(dialog._entry)
        self.assertFalse(dialog._action.get_sensitive(), "button must start disabled")

        dialog._entry.set_text("salah")
        self.assertFalse(dialog._action.get_sensitive())

        dialog._entry.set_text(CONFIRM_PHRASE)
        self.assertTrue(dialog._action.get_sensitive())

        dialog._action.emit("clicked")
        self.assertEqual(confirmed, [True])
        self.assertEqual(closed, [True], "the dialog should close itself after confirming")

    def test_confirm_dialog_is_not_blocked_when_nothing_is_dangerous(self):
        safe = _item()
        dialog = ConfirmDialog([safe], dry_run=False, on_confirm=lambda: None)
        self.assertIsNone(dialog._entry)
        self.assertTrue(dialog._action.get_sensitive())

    def test_confirm_dialog_in_dry_run_is_a_preview(self):
        dangerous = _item(id="danger", risk=Risk.DANGEROUS)
        dialog = ConfirmDialog([dangerous], dry_run=True, on_confirm=lambda: None)
        self.assertIsNone(dialog._entry, "a preview deletes nothing, so no typing is required")
        self.assertIn("pratinjau", dialog._action.get_label().lower())
        self.assertFalse(dialog._action.has_css_class("destructive-action"))

    def test_summary_bar_button_reflects_selection_and_mode(self):
        bar = SummaryBar()
        self.assertFalse(bar._button.get_sensitive(), "nothing selected yet")
        self.assertIn("Pratinjau", bar._button.get_label())

        bar.set_selected(3, 5 * 1024**3)
        self.assertTrue(bar._button.get_sensitive())
        self.assertIn("3", bar._selected.get_label())

        bar.set_dry_run(False)
        self.assertIn("Hapus", bar._button.get_label())
        self.assertTrue(bar._button.has_css_class("destructive-action"))

        bar.set_busy(True, "bekerja")
        self.assertFalse(bar._button.get_sensitive())
        bar.set_busy(False, "")
        self.assertTrue(bar._button.get_sensitive())

    def test_summary_bar_emits_dry_run_changes(self):
        bar = SummaryBar()
        seen: list[bool] = []
        bar.connect("dry-run-changed", lambda _bar, value: seen.append(value))
        bar.set_dry_run(False)
        self.assertEqual(seen, [False])

    def test_summary_bar_emits_delete_request(self):
        bar = SummaryBar()
        bar.set_selected(1, 100)
        seen: list[int] = []
        bar.connect("delete-requested", lambda *_: seen.append(1))
        bar._button.emit("clicked")
        self.assertEqual(seen, [1])


if __name__ == "__main__":
    unittest.main()
