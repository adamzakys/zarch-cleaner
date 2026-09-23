"""Tests for the code that actually deletes things.

Everything runs inside a sandbox created under ~/.cache, which is inside the
real allowlist, so these tests exercise the genuine code path without touching
anything that matters. The sandbox is always removed afterwards.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from zarchcleaner import operations
from zarchcleaner.models import CleanItem, Kind


def _sandbox() -> Path:
    root = Path(os.path.expanduser("~/.cache/zarchcleaner-selftest"))
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    return root


class ContentsTests(unittest.TestCase):
    def setUp(self):
        self.root = _sandbox()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_clears_contents_but_keeps_the_directory(self):
        nested = self.root / "nested"
        nested.mkdir()
        (self.root / "a.bin").write_bytes(b"x" * 4096)
        (nested / "b.bin").write_bytes(b"y" * 8192)

        item = CleanItem(
            id="test-contents",
            title="test",
            description="",
            kind=Kind.CONTENTS,
            contents_of=[self.root],
        )
        result = operations.execute(item)

        self.assertTrue(result.ok, result.message)
        self.assertTrue(self.root.is_dir(), "the directory itself must survive")
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertGreater(result.freed, 0)

    def test_symlink_to_outside_is_unlinked_but_target_survives(self):
        outside = self.root.parent / "zarchcleaner-selftest-outside"
        shutil.rmtree(outside, ignore_errors=True)
        outside.mkdir()
        precious = outside / "precious.txt"
        precious.write_text("keep me")
        link = self.root / "escape"
        link.symlink_to(precious)

        result = operations.execute(
            CleanItem(id="t", title="t", description="", kind=Kind.CONTENTS, contents_of=[self.root])
        )

        self.assertTrue(result.ok, result.message)
        self.assertFalse(link.exists())
        self.assertTrue(precious.exists(), "content outside the sandbox was destroyed")
        shutil.rmtree(outside, ignore_errors=True)

    def test_files_outside_the_allowlist_are_skipped(self):
        link_dir = self.root / "linked"
        link_dir.mkdir()
        (link_dir / "inside.txt").write_bytes(b"z" * 1024)
        # A directory symlink pointing at /etc: its contents must not be walked.
        (self.root / "etc-link").symlink_to("/etc", target_is_directory=True)

        result = operations.execute(
            CleanItem(id="t", title="t", description="", kind=Kind.CONTENTS, contents_of=[self.root])
        )

        self.assertTrue(result.ok, result.message)
        self.assertTrue(Path("/etc/passwd").exists())


class PathsTests(unittest.TestCase):
    def setUp(self):
        self.root = _sandbox()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_deletes_a_single_file(self):
        target = self.root / "file.bin"
        target.write_bytes(b"a" * 2048)

        result = operations.execute(
            CleanItem(id="t", title="t", description="", kind=Kind.PATHS, paths=[target])
        )

        self.assertTrue(result.ok, result.message)
        self.assertFalse(target.exists())
        self.assertGreater(result.freed, 0)

    def test_deletes_a_directory_tree(self):
        tree = self.root / "tree"
        (tree / "deep").mkdir(parents=True)
        (tree / "deep" / "file.bin").write_bytes(b"b" * 1024)

        result = operations.execute(
            CleanItem(id="t", title="t", description="", kind=Kind.PATHS, paths=[tree])
        )

        self.assertTrue(result.ok, result.message)
        self.assertFalse(tree.exists())

    def test_refuses_a_path_outside_the_allowlist(self):
        result = operations.execute(
            CleanItem(
                id="t",
                title="t",
                description="",
                kind=Kind.PATHS,
                paths=[Path("/etc/passwd"), Path(os.path.expanduser("~/.bashrc"))],
            )
        )

        self.assertFalse(result.ok)
        self.assertIn("ditolak pengaman", result.message)
        self.assertTrue(Path("/etc/passwd").exists())
        self.assertTrue(Path(os.path.expanduser("~/.bashrc")).exists())

    def test_refuses_traversal_out_of_the_root(self):
        sneaky = self.root / ".." / ".." / ".ssh" / "id_ed25519"
        result = operations.execute(
            CleanItem(id="t", title="t", description="", kind=Kind.PATHS, paths=[sneaky])
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.freed, 0)


class TruncateTests(unittest.TestCase):
    def test_refuses_anything_but_the_allowed_log(self):
        for path in (Path("/etc/passwd"), Path("/tmp/x"), Path("/var/log/syslog")):
            with self.subTest(path=path):
                result = operations.execute(
                    CleanItem(id="t", title="t", description="", kind=Kind.TRUNCATE, paths=[path])
                )
                self.assertFalse(result.ok)
                self.assertIn("ditolak pengaman", result.message)


class CommandTests(unittest.TestCase):
    def test_success(self):
        result = operations.execute(
            CleanItem(id="t", title="t", description="", kind=Kind.COMMAND, command=["true"])
        )
        self.assertTrue(result.ok, result.message)

    def test_failure_is_reported(self):
        result = operations.execute(
            CleanItem(id="t", title="t", description="", kind=Kind.COMMAND, command=["false"])
        )
        self.assertFalse(result.ok)

    def test_missing_command_is_reported_not_raised(self):
        result = operations.execute(
            CleanItem(
                id="t",
                title="t",
                description="",
                kind=Kind.COMMAND,
                command=["zarchcleaner-does-not-exist"],
            )
        )
        self.assertFalse(result.ok)

    def test_empty_command_is_rejected(self):
        result = operations.execute(
            CleanItem(id="t", title="t", description="", kind=Kind.COMMAND, command=[])
        )
        self.assertFalse(result.ok)

    def test_pacman_remove_without_packages_is_a_noop(self):
        result = operations.execute(
            CleanItem(id="t", title="t", description="", kind=Kind.PACMAN_REMOVE, packages=[])
        )
        self.assertTrue(result.ok, result.message)


class MeasurementTests(unittest.TestCase):
    def test_measure_paths_sums_directories(self):
        root = _sandbox()
        try:
            (root / "a").write_bytes(b"x" * 4096)
            item = CleanItem(
                id="t", title="t", description="", kind=Kind.CONTENTS,
                contents_of=[root], measure_paths=[root],
            )
            self.assertGreaterEqual(operations.measure(item), 4096)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_measure_argv_parses_its_output(self):
        item = CleanItem(
            id="t", title="t", description="", kind=Kind.COMMAND,
            command=["true"], measure_argv=["echo", "2.00 GiB"],
        )
        self.assertEqual(operations.measure(item), int(2 * 1024**3))

    def test_measure_is_none_when_nothing_can_be_measured(self):
        item = CleanItem(id="t", title="t", description="", kind=Kind.COMMAND, command=["true"])
        self.assertIsNone(operations.measure(item))

    def test_freed_falls_back_to_the_reported_size(self):
        result = operations.execute(
            CleanItem(id="t", title="t", description="", kind=Kind.COMMAND, command=["true"], size=1234)
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.freed, 1234)


class WireFormatTests(unittest.TestCase):
    def test_round_trip(self):
        original = CleanItem(
            id="x",
            title="Judul",
            description="",
            kind=Kind.CONTENTS,
            contents_of=[Path("/tmp/a")],
            measure_paths=[Path("/tmp/b")],
            size=99,
        )
        restored = CleanItem.from_wire(original.to_wire())
        self.assertEqual(restored.id, original.id)
        self.assertEqual(restored.kind, original.kind)
        self.assertEqual(restored.contents_of, original.contents_of)
        self.assertEqual(restored.measure_paths, original.measure_paths)
        self.assertEqual(restored.size, 99)

    def test_wire_payload_is_json_serialisable(self):
        original = CleanItem(
            id="x", title="t", description="", kind=Kind.PATHS, paths=[Path("/tmp/a")]
        )
        json.dumps({"actions": [original.to_wire()]})


class HelperTests(unittest.TestCase):
    def test_helper_refuses_to_run_unprivileged(self):
        if os.geteuid() == 0:
            self.skipTest("running as root already")
        plan = Path("/tmp/zarchcleaner-helper-test.json")
        plan.write_text(json.dumps({"actions": []}))
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "zarchcleaner.helper", str(plan)],
                capture_output=True,
                text=True,
                cwd=str(Path(__file__).resolve().parent.parent),
                check=False,
            )
        finally:
            plan.unlink(missing_ok=True)

        self.assertEqual(proc.returncode, 1)
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertFalse(payload["ok"])
        self.assertIn("root", payload["message"])

    def test_helper_reports_a_missing_plan(self):
        if os.geteuid() == 0:
            self.skipTest("running as root already")
        proc = subprocess.run(
            [sys.executable, "-m", "zarchcleaner.helper", "/nonexistent/plan.json"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parent.parent),
            check=False,
        )
        self.assertEqual(proc.returncode, 1)


if __name__ == "__main__":
    unittest.main()
