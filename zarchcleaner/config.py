"""User preferences and run reports."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .models import RunReport

CONFIG_DIR = Path(os.path.expanduser("~/.config/zarch-cleaner"))
CONFIG_PATH = CONFIG_DIR / "config.json"
STATE_DIR = Path(os.path.expanduser("~/.local/state/zarch-cleaner"))
LAST_RUN_PATH = STATE_DIR / "last-run.json"


@dataclass
class Config:
    """Preferences. Notably not a place to store deletion targets."""

    dry_run: bool = True
    keep_cached_versions: int = 1
    tmp_max_age_days: int = 10
    journal_vacuum: str = "time=2weeks"
    selected_items: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


def load() -> Config:
    try:
        raw = CONFIG_PATH.read_text()
        data = json.loads(raw)
    except (OSError, ValueError):
        return Config()
    if not isinstance(data, dict):
        return Config()
    try:
        return Config.from_dict(data)
    except (TypeError, ValueError):
        return Config()


def save(config: Config) -> None:
    _write_json(CONFIG_PATH, asdict(config))


def save_report(report: RunReport) -> None:
    _write_json(LAST_RUN_PATH, report.to_dict())


def load_report() -> dict | None:
    try:
        data = json.loads(LAST_RUN_PATH.read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_json(path: Path, payload: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        tmp.replace(path)
    except OSError:
        pass
