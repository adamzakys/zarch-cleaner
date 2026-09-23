"""Stylesheet: Arch Linux blue, plus badges and a few numeric labels."""

from __future__ import annotations

from ..gilib import Gdk, Gtk

CSS = """
/* Arch Linux blue (#1793d1) as the accent, so the app sits comfortably next to
   the rest of an Arch desktop instead of the default GNOME blue. These are the
   names libadwaita's own widgets resolve against, so overriding them re-tints
   switches, suggested actions and selections across the whole window. */
@define-color accent_bg_color #1793d1;
@define-color accent_fg_color #ffffff;
@define-color accent_color #1793d1;

headerbar {
    box-shadow: inset 0 -2px 0 0 alpha(@accent_bg_color, 0.85);
}

.risk-badge {
    font-size: 0.72em;
    font-weight: 800;
    padding: 2px 9px;
    border-radius: 999px;
    letter-spacing: 0.03em;
}

.risk-safe {
    background-color: alpha(@accent_bg_color, 0.20);
    color: @accent_color;
}

.risk-caution {
    background-color: alpha(@warning_bg_color, 0.24);
    color: @warning_color;
}

.risk-dangerous {
    background-color: alpha(@error_bg_color, 0.24);
    color: @error_color;
}

.size-label {
    font-feature-settings: "tnum";
    font-weight: 600;
}

/* Arch is a terminal-first distribution; paths and commands read better in a
   monospaced face. */
.mono {
    font-family: monospace;
    font-size: 0.92em;
}

.status-label {
    font-size: 0.9em;
}

.distro-label {
    font-size: 0.85em;
    letter-spacing: 0.02em;
}
"""

_provider: Gtk.CssProvider | None = None


def install() -> None:
    """Attach the stylesheet to the default display, once."""
    global _provider
    if _provider is not None:
        return
    _provider = Gtk.CssProvider()
    _provider.load_from_string(CSS)
    display = Gdk.Display.get_default()
    if display is not None:
        Gtk.StyleContext.add_provider_for_display(
            display, _provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
