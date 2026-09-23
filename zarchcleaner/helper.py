"""Privileged half of a cleaning plan.

This script is never run directly by a user: the application starts it through
``pkexec`` (or ``sudo`` in a terminal as a fallback). It revalidates every
target against :mod:`zarchcleaner.safety` before touching anything, so a
tampered plan file cannot make it delete something outside the allowlist.

Results are written as one JSON object per line, both to stdout and, when
``--out`` is given, to that file.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zarchcleaner import operations  # noqa: E402
from zarchcleaner.models import CleanItem  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Zarch Cleaner privileged helper")
    parser.add_argument("plan", help="path to the JSON plan file")
    parser.add_argument("--out", help="also append JSON results to this file")
    args = parser.parse_args(argv)

    if os.geteuid() != 0:
        print(
            json.dumps({"id": "-", "ok": False, "freed": 0, "message": "helper harus dijalankan sebagai root"}),
            flush=True,
        )
        return 1

    try:
        plan = json.loads(Path(args.plan).read_text())
        actions = plan["actions"]
    except (OSError, ValueError, KeyError) as exc:
        print(
            json.dumps({"id": "-", "ok": False, "freed": 0, "message": f"rencana tidak bisa dibaca: {exc}"}),
            flush=True,
        )
        return 1

    sink = None
    if args.out:
        try:
            sink = open(args.out, "a", encoding="utf-8")
        except OSError:
            sink = None

    failures = 0
    try:
        for raw in actions:
            try:
                item = CleanItem.from_wire(raw)
            except (KeyError, ValueError) as exc:
                line = json.dumps(
                    {"id": str(raw.get("id", "-")), "ok": False, "freed": 0, "message": f"item tidak valid: {exc}"},
                    ensure_ascii=False,
                )
                _emit(line, sink)
                failures += 1
                continue

            result = operations.execute(item)
            if not result.ok:
                failures += 1
            _emit(json.dumps(vars(result), ensure_ascii=False), sink)
    finally:
        if sink is not None:
            sink.close()

    return 1 if failures else 0


def _emit(line: str, sink) -> None:
    print(line, flush=True)
    if sink is not None:
        sink.write(line + "\n")
        sink.flush()


if __name__ == "__main__":
    raise SystemExit(main())
