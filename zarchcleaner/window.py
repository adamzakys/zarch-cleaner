"""Main application window."""

from __future__ import annotations

import shutil

from . import config, system_info
from .cleaners import CLEANERS
from .executor import Executor
from .gilib import Adw, Gio, GLib, Gtk
from .models import ActionResult, CleanItem, RunReport
from .scan import Scanner
from .ui.cleaner_row import CleanerRow
from .ui.confirm_dialog import ConfirmDialog
from .ui.details_dialog import DetailsDialog
from .ui.summary_bar import SummaryBar
from .usage import human_size


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.set_title("Zarch Cleaner")
        self.set_default_size(880, 760)

        self._category_of = {cleaner.id: cleaner.category for cleaner in CLEANERS}
        self._groups: dict[str, Adw.PreferencesGroup] = {}
        self._rows: dict[str, CleanerRow] = {}
        self._items: dict[str, CleanItem] = {}
        self._wanted_selection: set[str] = set()
        self._active_plan: list[CleanItem] = []
        self._run_freed = 0
        self._run_failures = 0

        self._scanner = Scanner()
        self._scanner.connect("item-found", self._on_item_found)
        self._scanner.connect("progress", self._on_scan_progress)
        self._scanner.connect("finished", self._on_scan_finished)

        self._executor = Executor()
        self._executor.connect("status", self._on_run_status)
        self._executor.connect("result", self._on_run_result)
        self._executor.connect("finished", self._on_run_finished)

        self._toasts = Adw.ToastOverlay()
        self._toasts.set_child(self._build_toolbar())
        self.set_content(self._toasts)

        self._install_actions()
        self._apply_config(config.load())
        self._start_scan()

    # -- construction --------------------------------------------------

    def _build_toolbar(self) -> Adw.ToolbarView:
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(self._build_header())

        self._page = Adw.PreferencesPage()
        self._build_overview()
        self._build_category_groups()
        toolbar.set_content(self._page)

        self._summary = SummaryBar()
        self._summary.connect("delete-requested", lambda *_: self._on_delete_requested())
        self._summary.connect("dry-run-changed", self._on_dry_run_changed)
        toolbar.add_bottom_bar(self._summary)
        return toolbar

    def _build_header(self) -> Adw.HeaderBar:
        header = Adw.HeaderBar()

        # The running distribution sits under the title, so it is obvious which
        # Arch installation is being cleaned.
        self._title = Adw.WindowTitle(title="Zarch Cleaner", subtitle=system_info.distro_name())
        header.set_title_widget(self._title)

        self._refresh_button = Gtk.Button(icon_name="view-refresh-symbolic")
        self._refresh_button.set_tooltip_text("Pindai ulang (Ctrl+R)")
        self._refresh_button.set_action_name("win.refresh")
        header.pack_start(self._refresh_button)

        menu = Gio.Menu()
        menu.append("Laporan terakhir", "win.last-report")
        menu.append("Buka folder konfigurasi", "win.open-config")
        menu.append("Tentang Zarch Cleaner", "win.about")

        button = Gtk.MenuButton(icon_name="open-menu-symbolic")
        button.set_menu_model(menu)
        button.set_tooltip_text("Menu")
        header.pack_end(button)
        return header

    def _build_overview(self) -> None:
        self._overview = Adw.PreferencesGroup(title="Ringkasan")
        self._system = Adw.ActionRow(title="Sistem", subtitle=system_info.summary())
        self._reclaimable = Adw.ActionRow(title="Bisa dibebaskan", subtitle="Menunggu pemindaian…")
        self._disk = Adw.ActionRow(title="Ruang disk (/)")
        self._overview.add(self._system)
        self._overview.add(self._reclaimable)
        self._overview.add(self._disk)
        self._page.add(self._overview)

    def _build_category_groups(self) -> None:
        for cleaner in CLEANERS:
            if cleaner.category in self._groups:
                continue
            group = Adw.PreferencesGroup(title=GLib.markup_escape_text(cleaner.category))
            group.set_visible(False)
            self._groups[cleaner.category] = group
            self._page.add(group)

    def _install_actions(self) -> None:
        actions = {
            "refresh": (self._on_refresh_action, None),
            "about": (self._on_about_action, None),
            "open-config": (self._on_open_config_action, None),
            "last-report": (self._on_last_report_action, None),
        }
        for name, (handler, param_type) in actions.items():
            action = Gio.SimpleAction.new(name, param_type)
            action.connect("activate", handler)
            self.add_action(action)

        app = self.get_application()
        if app is not None:
            app.set_accels_for_action("win.refresh", ["<Control>r"])

    # -- configuration -------------------------------------------------

    def _apply_config(self, cfg: config.Config) -> None:
        self._summary.set_dry_run(cfg.dry_run)
        self._wanted_selection = set(cfg.selected_items)

    def _collect_config(self) -> config.Config:
        cfg = config.load()
        cfg.dry_run = self._summary.dry_run
        cfg.selected_items = sorted(self._selected_ids())
        return cfg

    # -- scanning ------------------------------------------------------

    def _start_scan(self) -> None:
        if self._scanner.running:
            return
        self._clear_rows()
        self._summary.set_busy(True, "Memindai…")
        self._refresh_button.set_sensitive(False)
        self._scanner.start()

    def _clear_rows(self) -> None:
        for group in self._groups.values():
            group.set_visible(False)
        for row in self._rows.values():
            parent = row.get_parent()
            if parent is not None:
                parent.remove(row)
        self._rows.clear()
        self._items.clear()

    def _on_item_found(self, _scanner: Scanner, item: CleanItem, cleaner_id: str) -> None:
        category = self._category_of.get(cleaner_id)
        group = self._groups.get(category)
        if group is None:
            return

        row = CleanerRow(item, self._on_details_requested)
        if item.available and item.id in self._wanted_selection:
            row.set_selected(True)
        row.connect("selection-changed", lambda *_: self._update_selection())

        group.set_visible(True)
        group.add(row)
        self._rows[item.id] = row
        self._items[item.id] = item
        self._update_selection()

    def _on_scan_progress(self, _scanner: Scanner, done: int, total: int, label: str) -> None:
        if not label:
            return
        self._summary.set_busy(True, f"Memindai: {label}…")
        self._summary.set_progress(done / max(1, total))

    def _on_scan_finished(self, _scanner: Scanner) -> None:
        self._summary.set_busy(False, "")
        self._refresh_button.set_sensitive(True)
        self._update_overview()
        self._update_selection()

    def _update_overview(self) -> None:
        total = sum(item.size for item in self._items.values() if item.available)
        count = sum(1 for item in self._items.values() if item.available)
        self._reclaimable.set_subtitle(
            GLib.markup_escape_text(
                f"{human_size(total)} dari {count} item" if count else "Tidak ada yang perlu dibersihkan"
            )
        )

        try:
            usage = shutil.disk_usage("/")
        except OSError:
            return
        percent = usage.used / usage.total * 100 if usage.total else 0
        self._disk.set_subtitle(
            GLib.markup_escape_text(
                f"{human_size(usage.used)} terpakai dari {human_size(usage.total)} "
                f"({percent:.0f}%) · {human_size(usage.free)} kosong"
            )
        )

    # -- selection -----------------------------------------------------

    def _selected_ids(self) -> list[str]:
        return [item_id for item_id, row in self._rows.items() if row.selected]

    def _selected_items(self) -> list[CleanItem]:
        return [self._items[item_id] for item_id in self._selected_ids()]

    def _update_selection(self) -> None:
        selected = self._selected_items()
        self._summary.set_selected(len(selected), sum(item.size for item in selected))

    # -- running -------------------------------------------------------

    def _on_delete_requested(self) -> None:
        if self._executor.running or self._scanner.running:
            return
        items = self._selected_items()
        if not items:
            return

        self._active_plan = items
        dry_run = self._summary.dry_run
        dialog = ConfirmDialog(items, dry_run, on_confirm=lambda: self._run(items, dry_run))
        dialog.present(self)

    def _run(self, items: list[CleanItem], dry_run: bool) -> None:
        self._run_freed = 0
        self._run_failures = 0
        self._summary.set_busy(True, "Menyiapkan…")
        self._executor.start(items, dry_run)

    def _on_run_status(self, _executor: Executor, status: str) -> None:
        self._summary.set_busy(True, status)

    def _on_run_result(self, _executor: Executor, result: ActionResult) -> None:
        self._run_freed += result.freed
        if not result.ok:
            self._run_failures += 1

    def _on_run_finished(self, _executor: Executor, report: RunReport) -> None:
        self._summary.set_busy(False, "")
        self._toast(self._run_summary(report))

        if report.failures:
            details = "\n".join(
                f"• {result.title}: {result.message or 'gagal'}" for result in report.failures[:6]
            )
            dialog = Adw.AlertDialog(
                heading=f"{len(report.failures)} item gagal dibersihkan",
                body=details,
            )
            dialog.add_response("close", "Tutup")
            dialog.present(self)

        if not report.dry_run:
            self._start_scan()
        else:
            self._summary.set_selected(
                len(self._selected_items()), sum(item.size for item in self._selected_items())
            )

    def _run_summary(self, report: RunReport) -> str:
        freed = human_size(report.freed)
        if report.dry_run:
            return f"Pratinjau: {freed} bisa dibebaskan (tidak ada yang dihapus)."
        if report.freed:
            return f"Membebaskan {freed}."
        return "Selesai. Tidak ada ruang yang bisa dibebaskan."

    def _toast(self, message: str) -> None:
        self._toasts.add_toast(Adw.Toast(title=message, timeout=6))

    # -- actions -------------------------------------------------------

    def _on_refresh_action(self, _action: Gio.SimpleAction, _param) -> None:
        config.save(self._collect_config())
        self._start_scan()

    def _on_details_requested(self, item: CleanItem) -> None:
        DetailsDialog(item).present(self)

    def _on_dry_run_changed(self, _bar: SummaryBar, dry_run: bool) -> None:
        cfg = self._collect_config()
        cfg.dry_run = dry_run
        config.save(cfg)

    def _on_about_action(self, _action: Gio.SimpleAction, _param) -> None:
        from . import APP_ID, APP_NAME, __version__

        dialog = Adw.AboutDialog(
            application_name=APP_NAME,
            application_icon=APP_ID,
            version=__version__,
            developer_name="adamzakys",
            comments=(
                "Pembersih sistem untuk Arch Linux dan turunannya.\n"
                "Setiap penghapusan melewati allowlist di zarchcleaner/safety.py."
            ),
            license_type=Gtk.License.MIT_X11,
        )
        dialog.present(self)

    def _on_open_config_action(self, _action: Gio.SimpleAction, _param) -> None:
        config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._open_uri(f"file://{config.CONFIG_DIR}")

    def _on_last_report_action(self, _action: Gio.SimpleAction, _param) -> None:
        data = config.load_report()
        if not data:
            self._toast("Belum ada laporan.")
            return

        results = data.get("results", [])
        lines = [
            f"{'PRATINJAU' if data.get('dry_run') else 'EKSEKUSI'} · {data.get('started_at', '?')}",
            f"Total dibebaskan: {human_size(int(data.get('freed', 0)))}",
            "",
        ]
        for entry in results[:25]:
            mark = "ok" if entry.get("ok") else "GAGAL"
            freed = human_size(int(entry.get("freed", 0)))
            lines.append(f"[{mark}] {entry.get('title')} — {freed}")
            if not entry.get("ok") and entry.get("message"):
                lines.append(f"        {entry['message']}")
        if len(results) > 25:
            lines.append(f"… dan {len(results) - 25} lainnya")

        dialog = Adw.AlertDialog(heading="Laporan terakhir", body="\n".join(lines))
        dialog.add_response("close", "Tutup")
        dialog.present(self)

    def _open_uri(self, uri: str) -> None:
        try:
            Gio.AppInfo.launch_default_for_uri(uri, None)
        except GLib.Error as exc:
            self._toast(f"Tidak bisa membuka: {exc.message}")
