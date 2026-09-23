"""Registry of every cleaner, in the order the UI should present them."""

from __future__ import annotations

from .app_cache import AppCacheCleaner
from .aur import AurBuildCacheCleaner
from .base import Cleaner
from .dev_cache import DevCacheCleaner
from .pacman import PacmanCleaner
from .system_junk import SystemJunkCleaner

CLEANERS: tuple[Cleaner, ...] = (
    PacmanCleaner(),
    AurBuildCacheCleaner(),
    SystemJunkCleaner(),
    AppCacheCleaner(),
    DevCacheCleaner(),
)

__all__ = ["CLEANERS", "Cleaner"]
