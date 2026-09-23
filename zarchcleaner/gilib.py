"""Pins the GTK and libadwaita versions before anything imports them.

Every UI module imports its GTK bindings from here so the ``require_version``
calls always run first.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Pango", "1.0")

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, Pango  # noqa: E402,F401

__all__ = ["Adw", "Gdk", "Gio", "GLib", "GObject", "Gtk", "Pango"]
