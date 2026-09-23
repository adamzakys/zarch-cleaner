"""Running the privileged half of a plan.

``pkexec`` is the primary mechanism: it shows the desktop's polkit prompt and
runs the helper as root. If polkit is unavailable or the prompt is dismissed,
the plan is handed to ``sudo`` inside a terminal window instead, where the
helper writes its results to a file that we read back.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from .models import ActionResult, CleanItem

HELPER_PATH = Path(__file__).resolve().parent / "helper.py"
PYTHON = sys.executable or "/usr/bin/python3"
WINDOW_TITLE = "Zarch Cleaner — hak akses root"

#: pkexec exit codes that mean "we never got to run anything".
PKEXEC_AUTH_FAILED = frozenset({122, 126, 127})

TERMINALS: tuple[tuple[str, list[str]], ...] = (
    ("kitty", ["kitty", "--title", WINDOW_TITLE]),
    ("alacritty", ["alacritty", "--title", WINDOW_TITLE, "-e"]),
    ("foot", ["foot", "--title", WINDOW_TITLE]),
    ("konsole", ["konsole", "--title", WINDOW_TITLE, "-e"]),
    ("gnome-terminal", ["gnome-terminal", "--title", WINDOW_TITLE, "--"]),
)

ResultCallback = Callable[[ActionResult], None]


def pkexec_available() -> bool:
    return shutil.which("pkexec") is not None


def terminal_available() -> bool:
    return any(shutil.which(name) for name, _argv in TERMINALS)


def run_privileged(items: list[CleanItem], on_result: ResultCallback) -> bool:
    """Execute *items* as root. Returns True when the helper actually ran."""
    if not items:
        return True

    workdir = Path(tempfile.mkdtemp(prefix="zarchcleaner-plan-"))
    os.chmod(workdir, 0o700)
    plan_path = workdir / "plan.json"
    out_path = workdir / "results.jsonl"
    plan_path.write_text(
        json.dumps({"actions": [item.to_wire() for item in items]}, ensure_ascii=False),
        encoding="utf-8",
    )

    try:
        if pkexec_available():
            ran = _run_pkexec(plan_path, on_result)
            if ran is not None:
                return ran
        return _run_terminal_sudo(plan_path, out_path, on_result)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _helper_argv(plan_path: Path, out_path: Path | None) -> list[str]:
    argv = [PYTHON, str(HELPER_PATH), str(plan_path)]
    if out_path is not None:
        argv += ["--out", str(out_path)]
    return argv


def _run_pkexec(plan_path: Path, on_result: ResultCallback) -> bool | None:
    """Run through pkexec. None means "fall back to a terminal"."""
    argv = ["pkexec", *_helper_argv(plan_path, None)]
    try:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except OSError:
        return None

    received = 0
    assert proc.stdout is not None
    for line in proc.stdout:
        if _report(line, on_result):
            received += 1
    proc.wait()

    if received:
        return True
    if proc.returncode in PKEXEC_AUTH_FAILED:
        return None
    return True


def _run_terminal_sudo(plan_path: Path, out_path: Path, on_result: ResultCallback) -> bool:
    argv = _terminal_argv(plan_path, out_path)
    if argv is None:
        return False

    out_path.write_text("", encoding="utf-8")
    try:
        proc = subprocess.Popen(argv)
    except OSError:
        return False

    offset = 0
    while proc.poll() is None:
        offset = _drain_results(out_path, offset, on_result)
        time.sleep(0.25)
    _drain_results(out_path, offset, on_result)
    return True


def _terminal_argv(plan_path: Path, out_path: Path) -> list[str] | None:
    command = ["sudo", *_helper_argv(plan_path, out_path)]
    for name, prefix in TERMINALS:
        if shutil.which(name):
            return [*prefix, *command]
    return None


def _drain_results(path: Path, offset: int, on_result: ResultCallback) -> int:
    try:
        with open(path, encoding="utf-8") as handle:
            handle.seek(offset)
            for line in handle:
                _report(line, on_result)
            return handle.tell()
    except OSError:
        return offset


def _report(line: str, on_result: ResultCallback) -> bool:
    line = line.strip()
    if not line or not line.startswith("{"):
        return False
    try:
        payload = json.loads(line)
    except ValueError:
        return False
    on_result(
        ActionResult(
            item_id=str(payload.get("item_id", "-")),
            title=str(payload.get("title", "")),
            ok=bool(payload.get("ok")),
            freed=int(payload.get("freed", 0)),
            message=str(payload.get("message", "")),
        )
    )
    return True
