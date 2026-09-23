"""Confirmation before anything is removed."""

from __future__ import annotations

from collections.abc import Callable

from ..gilib import Adw, GLib, Gtk
from ..models import CleanItem, Risk
from ..usage import human_size

#: Typed by the user when a dangerous item is selected and dry-run is off.
CONFIRM_PHRASE = "HAPUS"
MAX_LISTED = 40


class ConfirmDialog(Adw.AlertDialog):
    """Summary of the plan plus an explicit, hard-to-misfire confirmation."""

    def __init__(
        self,
        items: list[CleanItem],
        dry_run: bool,
        on_confirm: Callable[[], None],
    ) -> None:
        super().__init__()
        self._items = items
        self._dry_run = dry_run
        self._on_confirm = on_confirm
        self._dangerous = [item for item in items if item.risk is Risk.DANGEROUS]
        needs_typing = bool(self._dangerous) and not dry_run

        total = sum(item.size for item in items)
        self.set_heading("Pratinjau pembersihan" if dry_run else f"Hapus {len(items)} item?")
        self.set_body_use_markup(True)
        self.set_body(self._body_markup(items, total, dry_run))

        self._entry: Gtk.Entry | None = None
        self._action = self._build_action_button(needs_typing)
        self.set_extra_child(self._extra_child(needs_typing, total))

        self.add_response("cancel", "Batal")
        self.set_close_response("cancel")
        self.set_default_response("cancel")
        self._update_action()

    # -- content -------------------------------------------------------

    def _body_markup(self, items: list[CleanItem], total: int, dry_run: bool) -> str:
        escape = GLib.markup_escape_text
        size = escape(human_size(total))
        if dry_run:
            lines = [
                f"Perkiraan <b>{size}</b> akan dibebaskan dari {len(items)} item.",
                "",
                "<b>Tidak ada yang benar-benar dihapus</b> selama dry-run aktif.",
                "",
            ]
        else:
            lines = [f"Total <b>{size}</b> dari {len(items)} item akan dihapus.", ""]

        for item in items[:MAX_LISTED]:
            lines.append(f"• {escape(item.title)} — {escape(human_size(item.size))}")
        if len(items) > MAX_LISTED:
            lines.append(f"• … dan {len(items) - MAX_LISTED} item lainnya")
        return "\n".join(lines)

    def _extra_child(self, needs_typing: bool, total: int) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        root_items = [item for item in self._items if item.needs_root]
        if root_items and not self._dry_run:
            note = Gtk.Label(
                label=(
                    f"{len(root_items)} item butuh hak akses root. Kamu akan diminta "
                    "mengautentikasi lewat polkit (atau sudo di terminal)."
                )
            )
            note.set_wrap(True)
            note.set_xalign(0.0)
            note.add_css_class("dim-label")
            box.append(note)

        if self._dangerous:
            warning = Gtk.Label(
                label=(
                    f"Perhatian: {len(self._dangerous)} item berisiko tinggi "
                    f"({', '.join(item.title for item in self._dangerous[:3])}). "
                    "Baca bagian detailnya sebelum melanjutkan."
                )
            )
            warning.set_wrap(True)
            warning.set_xalign(0.0)
            warning.add_css_class("error")
            box.append(warning)

        if needs_typing:
            self._entry = Gtk.Entry()
            self._entry.set_placeholder_text(f"Ketik {CONFIRM_PHRASE} untuk mengaktifkan tombol")
            self._entry.connect("changed", lambda *_: self._update_action())
            box.append(self._entry)

        box.append(self._action)
        return box

    def _build_action_button(self, needs_typing: bool) -> Gtk.Button:
        if self._dry_run:
            button = Gtk.Button(label="Tampilkan pratinjau")
            button.add_css_class("suggested-action")
        else:
            button = Gtk.Button(label=f"Hapus {len(self._items)} item")
            button.add_css_class("destructive-action")
        button.connect("clicked", lambda *_: self._confirmed())
        return button

    # -- behaviour -----------------------------------------------------

    def _update_action(self) -> None:
        if self._entry is None:
            self._action.set_sensitive(True)
            return
        typed = self._entry.get_text().strip()
        self._action.set_sensitive(typed == CONFIRM_PHRASE)

    def _confirmed(self) -> None:
        self._on_confirm()
        self.close()
