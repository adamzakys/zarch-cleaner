"""A row representing one cleanable item."""

from __future__ import annotations

from collections.abc import Callable

from ..gilib import Adw, GLib, GObject, Gtk
from ..models import CleanItem
from ..usage import human_size


def _safe(text: str) -> str:
    """ActionRow titles and subtitles are parsed as Pango markup."""
    return GLib.markup_escape_text(text)


class CleanerRow(Adw.ActionRow):
    """Checkbox + title + risk badge + size for a single :class:`CleanItem`."""

    __gsignals__ = {
        "selection-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, item: CleanItem, on_details: Callable[[CleanItem], None]) -> None:
        super().__init__()
        self.item = item
        self._check: Gtk.CheckButton | None = None

        self.set_title(_safe(item.title))
        self.set_subtitle_lines(2)
        self.add_css_class("cleaner-row")

        if item.available:
            self._build_available(on_details)
        else:
            self._build_unavailable()

    # -- state ---------------------------------------------------------

    @property
    def selected(self) -> bool:
        return bool(self._check and self._check.get_active())

    def set_selected(self, value: bool) -> None:
        if self._check is not None:
            self._check.set_active(bool(value))

    # -- building ------------------------------------------------------

    def _build_available(self, on_details: Callable[[CleanItem], None]) -> None:
        self._check = Gtk.CheckButton()
        self._check.set_valign(Gtk.Align.CENTER)
        self._check.set_active(self.item.enabled_default)
        self._check.connect("toggled", lambda *_: self.emit("selection-changed"))
        self.add_prefix(self._check)
        self.set_activatable_widget(self._check)

        self.set_subtitle(_safe(self.item.summary_target()))

        self.add_suffix(self._risk_badge())

        size = Gtk.Label(label=human_size(self.item.size))
        size.add_css_class("size-label")
        size.set_valign(Gtk.Align.CENTER)
        size.set_tooltip_text(f"{self.item.size:,} byte".replace(",", "."))
        self.add_suffix(size)

        details = Gtk.Button(icon_name="dialog-information-symbolic")
        details.add_css_class("flat")
        details.set_valign(Gtk.Align.CENTER)
        details.set_tooltip_text("Lihat apa yang akan dihapus")
        details.connect("clicked", lambda *_: on_details(self.item))
        self.add_suffix(details)

    def _build_unavailable(self) -> None:
        self.set_sensitive(False)
        self.set_subtitle(_safe(self.item.note or "Tidak ada yang perlu dibersihkan."))
        self.add_suffix(self._risk_badge())
        placeholder = Gtk.Label(label="—")
        placeholder.add_css_class("size-label")
        placeholder.add_css_class("dim-label")
        self.add_suffix(placeholder)

    def _risk_badge(self) -> Gtk.Label:
        badge = Gtk.Label(label=self.item.risk.label)
        badge.add_css_class("risk-badge")
        badge.add_css_class(f"risk-{self.item.risk.value}")
        badge.set_valign(Gtk.Align.CENTER)
        badge.set_tooltip_text(
            f"Tingkat risiko: {self.item.risk.label}"
            + (" — butuh hak akses root" if self.item.needs_root else "")
        )
        return badge
