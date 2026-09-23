"""Integration tests for the executor.

These drive the real Executor (including its background thread and GLib main
loop) but only ever touch a sandbox under ~/.cache, plus one dry run over the
real items to prove a preview changes nothing.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gi.repository import GLib

from zarchcleaner import config, executor, usage
from zarchcleaner.cleaners import CLEANERS
from zarchcleaner.models import CleanItem, Kind, RunReport

SANDBOX = Path.home() / ".cache" / "zarchcleaner-executor-test"
TIMEOUT_SECONDS = 180


def _run_executor(items: list[CleanItem], dry_run: bool) -> RunReport:
    """Run the executor to completion on a main loop and return the report."""
    loop = GLib.MainLoop()
    outcome: dict[str, RunReport] = {}

    def on_finished(_exec: executor.Executor, report: RunReport) -> None:
        outcome["report"] = report
        loop.quit()

    exec_ = executor.Executor()
    exec_.connect("finished", on_finished)
    exec_.start(items, dry_run)

    def bail() -> bool:
        loop.quit()
        return False

    GLib.timeout_add_seconds(TIMEOUT_SECONDS, bail)
    loop.run()

    if "report" not in outcome:
        raise AssertionError("executor never finished")
    return outcome["report"]


def _sandbox_item() -> CleanItem:
    """A CONTENTS item shaped the way a cleaner would hand it over."""
    return CleanItem(
        id="sandbox",
        title="sandbox",
        description="",
        kind=Kind.CONTENTS,
        contents_of=[SANDBOX],
        measure_paths=[SANDBOX],
        size=usage.contents_bytes(SANDBOX),
    )


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(SANDBOX, ignore_errors=True)
        SANDBOX.mkdir(parents=True)
        (SANDBOX / "payload.bin").write_bytes(b"x" * 65536)

        self.state_dir = Path(tempfile.mkdtemp(prefix="zarchcleaner-state-"))
        self.state = self.state_dir / "last-run.json"
        self._patcher = mock.patch.object(config, "LAST_RUN_PATH", self.state)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        shutil.rmtree(SANDBOX, ignore_errors=True)
        shutil.rmtree(self.state_dir, ignore_errors=True)

    def test_dry_run_touches_nothing(self):
        before = usage.contents_bytes(SANDBOX)
        self.assertGreater(before, 0)

        report = _run_executor([_sandbox_item()], dry_run=True)

        self.assertTrue(report.dry_run)
        self.assertTrue((SANDBOX / "payload.bin").exists(), "dry run deleted a file")
        self.assertEqual(usage.contents_bytes(SANDBOX), before)
        self.assertEqual(report.freed, before)
        self.assertTrue(all(result.ok for result in report.results))
        self.assertTrue(all("Pratinjau" in result.message for result in report.results))

    def test_real_run_clears_the_sandbox(self):
        before = usage.contents_bytes(SANDBOX)

        report = _run_executor([_sandbox_item()], dry_run=False)

        self.assertFalse(report.dry_run)
        self.assertTrue(SANDBOX.is_dir(), "the directory itself must survive")
        self.assertEqual(list(SANDBOX.iterdir()), [])
        self.assertGreater(report.freed, 0)
        self.assertLessEqual(report.freed, before)

    def test_report_is_written_to_disk(self):
        _run_executor([_sandbox_item()], dry_run=False)

        self.assertTrue(self.state.is_file())
        data = json.loads(self.state.read_text())
        self.assertIn("results", data)
        self.assertFalse(data["dry_run"])
        self.assertEqual(data["results"][0]["item_id"], "sandbox")

    def test_a_failing_item_does_not_stop_the_others(self):
        bad = CleanItem(
            id="bad",
            title="bad",
            description="",
            kind=Kind.COMMAND,
            command=["zarchcleaner-does-not-exist"],
        )
        report = _run_executor([bad, _sandbox_item()], dry_run=False)

        by_id = {result.item_id: result for result in report.results}
        self.assertFalse(by_id["bad"].ok)
        self.assertTrue(by_id["sandbox"].ok)
        self.assertEqual(list(SANDBOX.iterdir()), [])
        self.assertEqual(len(report.failures), 1)

    def test_unavailable_items_are_skipped(self):
        item = _sandbox_item()
        item.available = False

        exec_ = executor.Executor()
        finished: list[object] = []
        exec_.connect("finished", lambda *args: finished.append(args))
        exec_.start([item], dry_run=False)

        self.assertFalse(exec_.running)
        self.assertEqual(finished, [])
        self.assertTrue((SANDBOX / "payload.bin").exists())

    def test_dry_run_over_every_real_item_changes_nothing(self):
        """The promise the UI makes: a preview never removes anything.

        Byte-for-byte equality cannot be asserted here because applications
        that are actually running (a browser, for one) keep writing to their own
        caches, and background timers may prune the package cache. That the dry
        run performs no operation at all is proven exactly by
        ``test_dry_run_touches_nothing`` on a sandbox we control; what this test
        adds is that a preview across every real item is harmless and complete.
        """
        items = [item for cleaner in CLEANERS for item in cleaner.scan() if item.available]
        self.assertTrue(items)
        watched = [path for item in items for path in item.measure_paths]
        self.assertTrue(watched)

        report = _run_executor(items, dry_run=True)

        self.assertTrue(report.dry_run)
        self.assertEqual(len(report.results), len(items))
        self.assertTrue(all(result.ok for result in report.results))
        self.assertTrue(all("Pratinjau" in result.message for result in report.results))

        missing = [str(path) for path in watched if not path.exists()]
        self.assertEqual(missing, [], "a dry run removed something")


if __name__ == "__main__":
    unittest.main()
