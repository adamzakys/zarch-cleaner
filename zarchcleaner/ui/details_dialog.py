"""Dialog showing exactly what an item will do."""

from __future__ import annotations

from ..gilib import Adw, GLib, Gtk, Pango
from ..models import CleanItem, Kind
from ..usage import human_size

MAX_LISTED = 200


def _safe(text: str) -> str:
    """Group and row titles/descriptions are parsed as Pango markup."""
    return GLib.markup_escape_text(text)


class DetailsDialog(Adw.Dialog):
    def __init__(self, item: CleanItem) -> None:
        super().__init__()
        self.set_title(item.title)
        self.set_content_width(640)
        self.set_content_height(580)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        toolbar.set_content(self._body(item))
        self.set_child(toolbar)

    def _body(self, item: CleanItem) -> Gtk.Widget:
        page = Adw.PreferencesPage()

        summary = Adw.PreferencesGroup(title="Ringkasan")
        summary.add(self._info_row("Risiko", item.risk.label))
        summary.add(
            self._info_row("Hak akses", "root (lewat pkexec)" if item.needs_root else "pengguna biasa")
        )
        summary.add(self._info_row("Ukuran terukur", human_size(item.size)))
        summary.add(self._info_row("Status", "Siap dibersihkan" if item.available else "Tidak tersedia"))
        if item.note:
            summary.add(self._info_row("Catatan", item.note))
        page.add(summary)

        page.add(self._text_group("Cara kerja", None, [item.description or "—"]))
        page.add(self._targets_group(item))
        return page

    def _targets_group(self, item: CleanItem) -> Adw.PreferencesGroup:
        if item.kind is Kind.COMMAND:
            return self._text_group("Yang akan dijalankan", "Perintahnya:", [" ".join(item.command)])

        if item.kind is Kind.PACMAN_REMOVE:
            lines = list(item.packages[:MAX_LISTED])
            return self._text_group(
                f"Paket orphan ({len(item.packages)})",
                "Dihapus dengan `pacman -Rns`. Periksa dulu: paket yang dipasang "
                "manual di luar pacman bisa ikut terhapus.",
                lines,
                total=len(item.packages),
            )

        if item.kind is Kind.TRUNCATE:
            return self._text_group(
                "Yang akan dikosongkan",
                "Isi berkas dikosongkan, berkasnya tetap ada:",
                [str(path) for path in item.paths],
            )

        if item.kind is Kind.CONTENTS:
            targets = item.contents_of
            description = "Isi direktori berikut dikosongkan, direktorinya tetap ada:"
        else:
            targets = item.paths
            description = "Berkas dan direktori berikut dihapus:"
        return self._text_group(
            f"Yang akan dihapus ({len(targets)})",
            description,
            [str(path) for path in targets[:MAX_LISTED]],
            total=len(targets),
        )

    def _text_group(
        self,
        title: str,
        description: str | None,
        lines: list[str],
        total: int | None = None,
    ) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title=_safe(title))
        if description:
            group.set_description(_safe(description))
        for line in lines:
            group.add(self._mono_row(line))
        if total is not None and total > len(lines):
            group.add(self._mono_row(f"… dan {total - len(lines)} lainnya"))
        if not lines:
            group.add(self._mono_row("—"))
        return group

    def _info_row(self, title: str, value: str) -> Adw.ActionRow:
        row = Adw.ActionRow(title=_safe(title), subtitle=_safe(value))
        row.add_css_class("property")
        return row

    def _mono_row(self, text: str) -> Adw.PreferencesRow:
        row = Adw.PreferencesRow()
        label = Gtk.Label(label=text)
        label.add_css_class("mono")
        label.set_wrap(True)
        label.set_wrap_mode(Pango.WrapMode.CHAR)
        label.set_xalign(0.0)
        label.set_selectable(True)
        label.set_margin_top(6)
        label.set_margin_bottom(6)
        label.set_margin_start(12)
        label.set_margin_end(12)
        row.set_child(label)
        return row
