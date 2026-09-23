"""The bar at the bottom of the window: progress, dry-run switch, action."""

from __future__ import annotations

from ..gilib import Adw, GObject, Gtk, Pango
from ..usage import human_size


class SummaryBar(Gtk.Box):
    __gsignals__ = {
        "delete-requested": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "dry-run-changed": (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
    }

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(12)
        self.set_margin_end(12)

        self._status_box = self._build_status()
        self.append(self._status_box)

        self._progress = Gtk.ProgressBar()
        self._progress.set_visible(False)
        self.append(self._progress)

        self.append(self._build_actions())

        self._busy = False
        self._selected_count = 0
        self.set_busy(False, "")
        self.set_selected(0, 0)

    # -- construction --------------------------------------------------

    def _build_status(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._spinner = Adw.Spinner()
        self._spinner.set_visible(False)
        box.append(self._spinner)

        self._status = Gtk.Label(xalign=0.0)
        self._status.add_css_class("status-label")
        self._status.add_css_class("dim-label")
        self._status.set_ellipsize(Pango.EllipsizeMode.END)
        self._status.set_hexpand(True)
        box.append(self._status)
        return box

    def _build_actions(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        self._dry_switch = Gtk.Switch()
        self._dry_switch.set_active(True)
        self._dry_switch.set_valign(Gtk.Align.CENTER)
        self._dry_switch.connect("state-set", self._on_dry_run_switch)

        dry_label = Gtk.Label(label="Dry-run (jangan hapus)")
        dry_label.set_mnemonic_widget(self._dry_switch)

        dry_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        dry_box.append(self._dry_switch)
        dry_box.append(dry_label)
        box.append(dry_box)

        self._selected = Gtk.Label(xalign=1.0)
        self._selected.add_css_class("size-label")
        self._selected.set_hexpand(True)
        box.append(self._selected)

        self._button = Gtk.Button(label="Pratinjau…")
        self._button.add_css_class("suggested-action")
        self._button.connect("clicked", lambda *_: self.emit("delete-requested"))
        box.append(self._button)

        return box

    # -- state ---------------------------------------------------------

    @property
    def dry_run(self) -> bool:
        return self._dry_switch.get_active()

    def set_dry_run(self, value: bool) -> None:
        self._dry_switch.set_active(bool(value))
        self._refresh_button()

    def set_busy(self, busy: bool, label: str = "") -> None:
        self._busy = busy
        self._spinner.set_visible(busy)
        self._progress.set_visible(busy)
        if not busy:
            self._progress.set_fraction(0.0)
        self._status.set_label(label)
        self._refresh_button()

    def set_progress(self, fraction: float) -> None:
        self._progress.set_fraction(max(0.0, min(1.0, fraction)))

    def set_selected(self, count: int, size: int) -> None:
        self._selected_count = count
        if count:
            self._selected.set_label(f"Dipilih: {count} item · {human_size(size)}")
        else:
            self._selected.set_label("Belum ada item dipilih")
        self._refresh_button()

    # -- internals -----------------------------------------------------

    def _on_dry_run_switch(self, _switch: Gtk.Switch, state: bool) -> bool:
        self.emit("dry-run-changed", bool(state))
        self._refresh_button()
        return False

    def _refresh_button(self) -> None:
        dry = self._dry_switch.get_active()
        self._button.set_label("Pratinjau…" if dry else f"Hapus {self._selected_count} item")
        if dry:
            self._button.remove_css_class("destructive-action")
            self._button.add_css_class("suggested-action")
        else:
            self._button.remove_css_class("suggested-action")
            self._button.add_css_class("destructive-action")
        self._button.set_sensitive(not self._busy and self._selected_count > 0)
