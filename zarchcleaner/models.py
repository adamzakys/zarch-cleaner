"""Data model shared by cleaners, scanner, executor and the UI."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path

from .usage import display_path


class Risk(enum.Enum):
    SAFE = "safe"
    CAUTION = "caution"
    DANGEROUS = "dangerous"

    @property
    def label(self) -> str:
        return _RISK_LABELS[self]


_RISK_LABELS = {
    Risk.SAFE: "Aman",
    Risk.CAUTION: "Hati-hati",
    Risk.DANGEROUS: "Berisiko",
}


class Kind(enum.Enum):
    """How an item is cleaned."""

    PATHS = "paths"
    CONTENTS = "contents"
    COMMAND = "command"
    PACMAN_REMOVE = "pacman-remove"
    TRUNCATE = "truncate"


@dataclass
class CleanItem:
    """A single cleanable thing.

    Items are always constructed from static definitions inside
    ``zarchcleaner.cleaners`` — never from user input or from an arbitrarily
    listed directory.
    """

    id: str
    title: str
    description: str
    kind: Kind
    risk: Risk = Risk.SAFE
    needs_root: bool = False
    enabled_default: bool = False

    paths: list[Path] = field(default_factory=list)
    contents_of: list[Path] = field(default_factory=list)
    command: list[str] = field(default_factory=list)
    packages: list[str] = field(default_factory=list)

    #: Measured before and after a run to report how much was really freed.
    #: Measurement never deletes anything, so these paths do not need to be
    #: inside the deletion allowlist.
    measure_paths: list[Path] = field(default_factory=list)
    measure_argv: list[str] = field(default_factory=list)

    size: int = 0
    available: bool = True
    note: str = ""

    def targets(self) -> list[Path]:
        return [*self.paths, *self.contents_of]

    def summary_target(self) -> str:
        """Short, human-readable hint for the row subtitle."""
        if self.kind is Kind.PACMAN_REMOVE:
            return f"{len(self.packages)} paket"
        if self.kind is Kind.COMMAND:
            if not self.command:
                return self.note
            binary = Path(self.command[0]).name
            return f"{binary} · {self.note}" if self.note else binary
        if self.kind is Kind.TRUNCATE:
            return " · ".join(display_path(path) for path in self.paths)
        listed = [*self.paths, *self.contents_of]
        if not listed:
            return self.note
        first = display_path(listed[0])
        if len(listed) == 1:
            return first
        return f"{first}  (+{len(listed) - 1} lainnya)"

    def to_wire(self) -> dict:
        """Serialise for the privileged helper."""
        return {
            "id": self.id,
            "title": self.title,
            "kind": self.kind.value,
            "paths": [str(path) for path in self.paths],
            "contents_of": [str(path) for path in self.contents_of],
            "command": list(self.command),
            "packages": list(self.packages),
            "measure_paths": [str(path) for path in self.measure_paths],
            "measure_argv": list(self.measure_argv),
            "size": self.size,
        }

    @classmethod
    def from_wire(cls, data: dict) -> "CleanItem":
        """Rebuild an item from :meth:`to_wire`.

        Only the fields needed to perform the work are read back; the helper
        deliberately does not inherit anything about presentation.
        """
        return cls(
            id=str(data["id"]),
            title=str(data.get("title") or data["id"]),
            description="",
            kind=Kind(data["kind"]),
            paths=[Path(p) for p in data.get("paths", ())],
            contents_of=[Path(p) for p in data.get("contents_of", ())],
            command=[str(a) for a in data.get("command", ())],
            packages=[str(p) for p in data.get("packages", ())],
            measure_paths=[Path(p) for p in data.get("measure_paths", ())],
            measure_argv=[str(a) for a in data.get("measure_argv", ())],
            size=int(data.get("size", 0)),
        )


@dataclass
class ActionResult:
    item_id: str
    title: str
    ok: bool
    freed: int = 0
    message: str = ""


@dataclass
class RunReport:
    """What a run actually did, persisted for the user to review later."""

    started_at: str
    dry_run: bool = False
    finished_at: str = ""
    results: list[ActionResult] = field(default_factory=list)

    @property
    def freed(self) -> int:
        return sum(r.freed for r in self.results)

    @property
    def failures(self) -> list[ActionResult]:
        return [r for r in self.results if not r.ok]

    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "dry_run": self.dry_run,
            "freed": self.freed,
            "results": [vars(r) for r in self.results],
        }
