"""Application entry point."""

from __future__ import annotations

from . import APP_ID, APP_NAME
from .gilib import Adw, Gio, GLib
from .ui import style


class ZarchCleanerApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        # GApplication takes its display name from the environment, not from a
        # constructor argument.
        GLib.set_application_name(APP_NAME)

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        style.install()

    def do_activate(self) -> None:
        from .window import MainWindow

        window = self.props.active_window
        if window is None:
            window = MainWindow(application=self)
        window.present()


def main(argv: list[str] | None = None) -> int:
    return ZarchCleanerApplication().run(argv if argv is not None else [])
