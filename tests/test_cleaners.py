"""Tests for cleaners, the item contract, and output parsing.

Nothing here deletes anything: cleaners are only asked to report.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from zarchcleaner import config, procs, safety
from zarchcleaner.cleaners import CLEANERS
from zarchcleaner.cleaners.app_cache import BROWSER_CACHE_DIRS, _browser_cache_paths, _glob_paths
from zarchcleaner.cleaners.system_junk import _VACUUM_RE, _stale_entries
from zarchcleaner.models import Kind, Risk

PACCACHE_OUTPUT = """==> Candidate packages:
bpf-7.2.6-1-x86_64.pkg.tar.zst
bpf-7.2.6-1-x86_64.pkg.tar.zst.sig
cpupower-7.2.6-1-x86_64.pkg.tar.zst

==> finished dry run: 3 candidates (disk space saved: 4.47 GiB)
"""

PACCACHE_EMPTY = "==> no candidate packages found for pruning\n"


class ParseSizeTests(unittest.TestCase):
    def test_binary_units(self):
        self.assertEqual(procs.parse_size("4.47 GiB"), int(4.47 * 1024**3))
        self.assertEqual(procs.parse_size("27.85 MiB"), int(27.85 * 1024**2))
        self.assertEqual(procs.parse_size("10.09 MiB"), int(10.09 * 1024**2))

    def test_bare_letters_are_binary(self):
        # systemd prints journal usage without a B suffix.
        self.assertEqual(procs.parse_size("take up 49.3M in the file system"), int(49.3 * 1024**2))

    def test_decimal_units(self):
        self.assertEqual(procs.parse_size("2 MB"), 2_000_000)

    def test_comma_decimals(self):
        self.assertEqual(procs.parse_size("1,5 GB"), int(1.5 * 1000**3))

    def test_garbage(self):
        self.assertEqual(procs.parse_size(""), 0)
        self.assertEqual(procs.parse_size("no numbers here"), 0)


class PacmanOutputTests(unittest.TestCase):
    def test_parses_candidates_and_total(self):
        candidates, saved = procs.parse_paccache_output(PACCACHE_OUTPUT)
        self.assertEqual(len(candidates), 3)
        self.assertEqual(candidates[0].name, "bpf-7.2.6-1-x86_64.pkg.tar.zst")
        self.assertEqual(saved, int(4.47 * 1024**3))

    def test_empty_run(self):
        candidates, saved = procs.parse_paccache_output(PACCACHE_EMPTY)
        self.assertEqual(candidates, [])
        self.assertEqual(saved, 0)


class BrowserCacheDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="zarchcleaner-browser-"))

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_chrome_layout(self):
        (self.tmp / "Default" / "Cache").mkdir(parents=True)
        (self.tmp / "Default" / "Code Cache").mkdir()
        found = [p.name for p in _browser_cache_paths(self.tmp)]
        self.assertEqual(sorted(found), ["Cache", "Code Cache"])

    def test_brave_nested_layout(self):
        (self.tmp / "Brave-Browser" / "Default" / "Cache").mkdir(parents=True)
        (self.tmp / "Brave-Browser" / "Profile 2" / "Code Cache").mkdir(parents=True)
        found = _browser_cache_paths(self.tmp)
        self.assertEqual(len(found), 2)

    def test_never_returns_profile_data(self):
        (self.tmp / "Default" / "Local Storage").mkdir(parents=True)
        (self.tmp / "Default" / "Cache").mkdir()
        (self.tmp / "Default" / "indexed_db").mkdir()
        found = {p.name for p in _browser_cache_paths(self.tmp)}
        self.assertEqual(found, {"Cache"})
        self.assertFalse(found & {"Local Storage", "indexed_db"})

    def test_does_not_descend_into_a_found_cache(self):
        nested = self.tmp / "Default" / "Cache" / "Cache_Data"
        nested.mkdir(parents=True)
        (nested / "Cache").mkdir()
        found = _browser_cache_paths(self.tmp)
        self.assertEqual([p.name for p in found], ["Cache"])
        self.assertTrue(all(p.parent.name == "Default" for p in found))

    def test_glob_paths_matches_wildcards(self):
        (self.tmp / "qtshadercache-one").mkdir()
        (self.tmp / "qtshadercache-two").mkdir()
        matches = _glob_paths((str(self.tmp / "qtshadercache-*"),))
        self.assertEqual([p.name for p in matches], ["qtshadercache-one", "qtshadercache-two"])


class StaleTempEntryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="zarchcleaner-tmp-"))

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _touch_old(self, relative: str) -> Path:
        path = self.tmp / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("junk")
        stale_time = 40 * 86400
        os.utime(path, (os.path.getmtime(path) - stale_time,) * 2)
        return path

    def test_finds_old_files(self):
        old = self._touch_old("old.log")
        fresh = self.tmp / "fresh.log"
        fresh.write_text("still in use")
        found = _stale_entries(self.tmp, 10)
        self.assertIn(old, found)
        self.assertNotIn(fresh, found)

    def test_skips_sockets_and_session_dirs(self):
        self._touch_old("keep-me.sock")
        self._touch_old("systemd-private-abc/tmp")
        self._touch_old(".X11-unix/X0")
        self.assertEqual(_stale_entries(self.tmp, 10), [])

    def test_stale_roots_stay_within_the_allowlist(self):
        # Whatever the cleaner proposes, deleting it must be allowed.
        for entry in _stale_entries(Path("/tmp"), 10):
            self.assertTrue(safety.is_safe_path(entry))


class CleanerContractTests(unittest.TestCase):
    def test_registry_is_not_empty_and_ids_are_unique(self):
        self.assertTrue(CLEANERS)
        ids = [cleaner.id for cleaner in CLEANERS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_cleaner_scans_without_raising(self):
        for cleaner in CLEANERS:
            with self.subTest(cleaner=cleaner.id):
                items = cleaner.scan()
                self.assertTrue(items, f"{cleaner.id} returned no items")

    def test_item_ids_are_globally_unique(self):
        seen: dict[str, str] = {}
        for cleaner in CLEANERS:
            for item in cleaner.scan():
                self.assertNotIn(item.id, seen, f"duplicate item id {item.id}")
                seen[item.id] = cleaner.id

    def test_deletion_targets_are_inside_the_allowlist(self):
        """The core safety contract: reports may propose nothing forbidden."""
        for cleaner in CLEANERS:
            for item in cleaner.scan():
                roots = safety.ALL_ROOTS
                if item.kind is Kind.TRUNCATE:
                    roots = safety.FILE_ROOTS
                for target in item.targets():
                    with self.subTest(item=item.id, target=str(target)):
                        self.assertTrue(
                            safety.is_safe_path(
                                target,
                                roots,
                                allow_root_itself=item.kind is Kind.TRUNCATE,
                            ),
                            f"{item.id} proposes a path outside the allowlist: {target}",
                        )

    def test_command_items_have_a_real_command(self):
        for cleaner in CLEANERS:
            for item in cleaner.scan():
                if item.kind is not Kind.COMMAND:
                    continue
                with self.subTest(item=item.id):
                    self.assertTrue(item.command)
                    self.assertTrue(all(isinstance(arg, str) and arg for arg in item.command))

    def test_root_items_never_target_the_home_directory(self):
        for cleaner in CLEANERS:
            for item in cleaner.scan():
                if not item.needs_root:
                    continue
                for target in item.targets():
                    with self.subTest(item=item.id, target=str(target)):
                        self.assertFalse(str(target).startswith(str(Path.home())))

    def test_risk_is_always_set(self):
        for cleaner in CLEANERS:
            for item in cleaner.scan():
                with self.subTest(item=item.id):
                    self.assertIsInstance(item.risk, Risk)

    def test_dangerous_items_are_off_by_default(self):
        for cleaner in CLEANERS:
            for item in cleaner.scan():
                if item.risk is Risk.DANGEROUS:
                    with self.subTest(item=item.id):
                        self.assertFalse(item.enabled_default)

    def test_available_items_have_a_measurable_size_or_a_note(self):
        for cleaner in CLEANERS:
            for item in cleaner.scan():
                if not item.available:
                    continue
                if item.kind in (Kind.PATHS, Kind.CONTENTS, Kind.TRUNCATE):
                    with self.subTest(item=item.id):
                        self.assertGreater(item.size, 0)


class ConfigTests(unittest.TestCase):
    def test_defaults_are_conservative(self):
        cfg = config.Config()
        self.assertTrue(cfg.dry_run, "dry-run must be the default")
        self.assertEqual(cfg.keep_cached_versions, 1)

    def test_unknown_keys_are_ignored(self):
        cfg = config.Config.from_dict({"dry_run": False, "evil": "rm -rf /"})
        self.assertFalse(cfg.dry_run)
        self.assertFalse(hasattr(cfg, "evil"))

    def test_journal_vacuum_is_validated(self):
        self.assertTrue(_VACUUM_RE.match("time=2weeks"))
        self.assertTrue(_VACUUM_RE.match("size=200M"))
        self.assertTrue(_VACUUM_RE.match("time=7d"))
        for bad in ("time=2weeks; rm -rf /", "--rotate", "time=", "$(id)", "time=1w extra"):
            with self.subTest(value=bad):
                self.assertIsNone(_VACUUM_RE.match(bad))


class BrowserCacheDirListTests(unittest.TestCase):
    def test_profile_data_is_not_in_the_cleanable_list(self):
        for name in ("Cookies", "Login Data", "History", "Local Storage", "IndexedDB"):
            with self.subTest(name=name):
                self.assertNotIn(name, BROWSER_CACHE_DIRS)


if __name__ == "__main__":
    unittest.main()
