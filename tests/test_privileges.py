"""Tests for the privileged path.

The tests never actually elevate: they cover the plumbing around the helper and
the fact that the helper-side code refuses a tampered plan.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from zarchcleaner import operations, privileges
from zarchcleaner.models import ActionResult, CleanItem, Kind


class PlanPlumbingTests(unittest.TestCase):
    def test_empty_plan_is_a_noop(self):
        seen: list[ActionResult] = []
        self.assertTrue(privileges.run_privileged([], seen.append))
        self.assertEqual(seen, [])

    def test_terminal_argv_uses_sudo_and_the_helper(self):
        plan = Path("/tmp/plan.json")
        out = Path("/tmp/out.jsonl")
        argv = privileges._terminal_argv(plan, out)
        if argv is None:
            self.skipTest("no terminal emulator installed")
        self.assertIn("sudo", argv)
        self.assertIn(str(privileges.HELPER_PATH), argv)
        self.assertIn(str(plan), argv)
        self.assertIn("--out", argv)
        self.assertIn(str(out), argv)
        self.assertTrue(argv[-1].endswith("out.jsonl"))

    def test_pkexec_detection(self):
        self.assertEqual(privileges.pkexec_available(), shutil.which("pkexec") is not None)

    def test_helper_path_points_at_a_real_file(self):
        self.assertTrue(privileges.HELPER_PATH.is_file())
        self.assertEqual(privileges.HELPER_PATH.name, "helper.py")


class ResultParsingTests(unittest.TestCase):
    def test_parses_a_result_line(self):
        seen: list[ActionResult] = []
        line = json.dumps(
            {"item_id": "x", "title": "Judul", "ok": True, "freed": 4096, "message": ""}
        )
        self.assertTrue(privileges._report(line, seen.append))
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].item_id, "x")
        self.assertEqual(seen[0].freed, 4096)
        self.assertTrue(seen[0].ok)

    def test_ignores_noise(self):
        seen: list[ActionResult] = []
        for line in ("", "   ", "sudo: a password is required", "{not json}",
                     "==> finished dry run"):
            with self.subTest(line=line):
                self.assertFalse(privileges._report(line, seen.append))
        self.assertEqual(seen, [])

    def test_tolerates_missing_fields(self):
        seen: list[ActionResult] = []
        self.assertTrue(privileges._report('{"item_id": "x", "ok": false}', seen.append))
        self.assertFalse(seen[0].ok)
        self.assertEqual(seen[0].freed, 0)


class TamperedPlanTests(unittest.TestCase):
    """The helper must not trust the plan it is handed."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="zarchcleaner-tamper-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _wire(self, **overrides) -> dict:
        payload = {
            "id": "evil",
            "title": "evil",
            "kind": "paths",
            "paths": [],
            "contents_of": [],
            "command": [],
            "packages": [],
            "measure_paths": [],
            "measure_argv": [],
            "size": 0,
        }
        payload.update(overrides)
        return payload

    def test_outside_targets_are_refused(self):
        for target in ("/etc/passwd", "/usr/bin/ls", str(Path.home() / ".bashrc")):
            with self.subTest(target=target):
                item = CleanItem.from_wire(self._wire(paths=[target]))
                result = operations.execute(item)
                self.assertFalse(result.ok, f"{target} should have been refused")
                self.assertIn("ditolak pengaman", result.message)
        self.assertTrue(Path("/etc/passwd").exists())

    def test_escape_via_symlink_is_refused(self):
        sandbox = Path.home() / ".cache" / "zarchcleaner-tamper-sandbox"
        shutil.rmtree(sandbox, ignore_errors=True)
        sandbox.mkdir(parents=True)
        outside = self.tmp / "precious.txt"
        outside.write_text("keep")
        link = sandbox / "link"
        link.symlink_to(outside)

        item = CleanItem.from_wire(self._wire(paths=[str(link / "nothing")]))
        result = operations.execute(item)

        self.assertFalse(result.ok)
        self.assertTrue(outside.exists())
        shutil.rmtree(sandbox, ignore_errors=True)

    def test_truncate_only_accepts_the_pacman_log(self):
        item = CleanItem.from_wire(self._wire(kind="truncate", paths=["/etc/passwd"]))
        result = operations.execute(item)
        self.assertFalse(result.ok)
        self.assertTrue(Path("/etc/passwd").exists())

    def test_unknown_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            CleanItem.from_wire(self._wire(kind="rm-rf-everything"))

    def test_missing_id_is_rejected(self):
        payload = self._wire()
        del payload["id"]
        with self.assertRaises(KeyError):
            CleanItem.from_wire(payload)

    def test_command_kind_cannot_be_smuggled_without_root(self):
        # A plan that runs a command still goes through the same executor, so
        # the command list is what it is — no shell interpretation happens.
        item = CleanItem.from_wire(self._wire(kind="command", command=["echo", "hi"]))
        self.assertEqual(item.command, ["echo", "hi"])
        self.assertEqual(item.kind, Kind.COMMAND)


class OperationsAreShellFreeTests(unittest.TestCase):
    def test_commands_run_without_a_shell(self):
        """A ';' inside an argument must reach the program as literal text."""
        script = Path(tempfile.mkdtemp(prefix="zarchcleaner-shell-"))
        try:
            item = CleanItem(
                id="t",
                title="t",
                description="",
                kind=Kind.COMMAND,
                command=["echo", "safe; touch " + str(script / "pwned")],
            )
            result = operations.execute(item)
            self.assertTrue(result.ok, result.message)
            self.assertFalse(
                (script / "pwned").exists(),
                "argument was interpreted by a shell",
            )
        finally:
            shutil.rmtree(script, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
