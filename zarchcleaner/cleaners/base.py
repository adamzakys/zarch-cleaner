"""Base class for cleaners.

A cleaner turns static knowledge about the system into a list of
:class:`~zarchcleaner.models.CleanItem` objects. Cleaners must not import GTK
and must never raise: anything unexpected is reported through the item's
``available`` and ``note`` fields.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from .. import usage
from ..models import CleanItem, Kind, Risk


class Cleaner(ABC):
    id: str = ""
    title: str = ""
    description: str = ""
    category: str = ""
    icon: str = "user-trash-symbolic"

    @abstractmethod
    def scan(self) -> list[CleanItem]:
        """Return this cleaner's items, measured and ready to display."""

    def contents_item(
        self,
        item_id: str,
        title: str,
        description: str,
        paths: list[Path],
        *,
        risk: Risk = Risk.SAFE,
        enabled_default: bool = False,
        needs_root: bool = False,
        measure_paths: list[Path] | None = None,
        empty_note: str = "Sudah kosong.",
    ) -> CleanItem:
        """Build an item that empties directories, or mark it unavailable."""
        existing = [path for path in paths if path.is_dir()]
        item = CleanItem(
            id=item_id,
            title=title,
            description=description,
            kind=Kind.CONTENTS,
            contents_of=existing,
            risk=risk,
            enabled_default=enabled_default,
            needs_root=needs_root,
            measure_paths=list(measure_paths) if measure_paths is not None else list(existing),
            size=sum(usage.contents_bytes(path) for path in existing),
        )
        if not existing or item.size == 0:
            item.available = False
            item.note = empty_note
        return item

    def unavailable(
        self,
        item_id: str,
        title: str,
        description: str,
        note: str,
        *,
        risk: Risk = Risk.SAFE,
    ) -> CleanItem:
        return CleanItem(
            id=item_id,
            title=title,
            description=description,
            kind=Kind.PATHS,
            risk=risk,
            available=False,
            note=note,
        )
