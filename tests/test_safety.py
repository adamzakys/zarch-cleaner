"""Tests for the deletion allowlist. This is the most safety-critical module."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from zarchcleaner import safety
from zarchcleaner.safety import PathGuardError, is_safe_path, require_safe

HOME = Path(os.path.expanduser("~"))


class AllowlistTests(unittest.TestCase):
    def test_rejects_system_paths(self):
        for path in ("/etc/passwd", "/usr/bin/ls", "/usr", "/etc", "/", "/root", "/home"):
            with self.subTest(path=path):
                self.assertFalse(is_safe_path(path))

    def test_rejects_home_secrets(self):
        for path in (
            HOME / ".ssh/id_ed25519",
            HOME / ".bashrc",
            HOME / ".gnupg/secring.gpg",
            HOME / "Documents/arch-cleaner-btw/models.py",
        ):
            with self.subTest(path=path):
                self.assertFalse(is_safe_path(path))

    def test_rejects_roots_themselves(self):
        for path in ("/tmp", "/var/tmp", "/boot", HOME / ".cache", HOME / ".npm", HOME):
            with self.subTest(path=path):
                self.assertFalse(is_safe_path(path))
                self.assertFalse(is_safe_path(path, allow_root_itself=True))

    def test_rejects_traversal_out_of_root(self):
        escaped = HOME / ".cache" / ".." / ".." / ".ssh" / "id_ed25519"
        self.assertFalse(is_safe_path(escaped))
        self.assertFalse(is_safe_path("/tmp/../etc/passwd"))
        self.assertFalse(is_safe_path("/var/tmp/../../etc/shadow"))

    def test_prefix_confusion_is_not_containment(self):
        # /var/tmp-something must not count as being inside /var/tmp
        self.assertFalse(is_safe_path("/var/tmp-evil/payload"))
        self.assertFalse(is_safe_path("/var/cache/pacman-other/pkg"))

    def test_accepts_cache_children(self):
        for path in (
            HOME / ".cache/thumbnails/abc.png",
            HOME / ".cache/mesa_shader_cache/1a/2b",
            HOME / ".npm/_cacache/content-v2/sha512/de/ad",
            HOME / ".local/share/Trash/files/old.txt",
            "/var/cache/pacman/pkg/linux-7.2.6-1-x86_64.pkg.tar.zst",
            "/tmp/old-session-file",
            "/var/tmp/build-stamp",
        ):
            with self.subTest(path=path):
                self.assertTrue(is_safe_path(path))

    def test_boot_and_kernels_are_never_touchable(self):
        # No cleaner targets /boot: kernel and initramfs files stay off limits.
        for path in (
            "/boot",
            "/boot/vmlinuz-linux",
            "/boot/vmlinuz-linux-lts",
            "/boot/initramfs-linux.img",
            "/boot/initramfs-linux-fallback.img",
            "/boot/grub/grub.cfg",
            "/boot/efi/EFI/BOOT/BOOTX64.EFI",
        ):
            with self.subTest(path=path):
                self.assertFalse(is_safe_path(path))
                self.assertFalse(is_safe_path(path, safety.FILE_ROOTS, allow_root_itself=True))

    def test_none_and_empty_are_rejected(self):
        self.assertFalse(is_safe_path(None))
        self.assertFalse(is_safe_path(""))

    def test_file_roots_for_truncation(self):
        self.assertFalse(is_safe_path("/var/log/pacman.log"))
        self.assertTrue(
            is_safe_path("/var/log/pacman.log", safety.FILE_ROOTS, allow_root_itself=True)
        )
        self.assertFalse(
            is_safe_path("/var/log/journal", safety.FILE_ROOTS, allow_root_itself=True)
        )
        self.assertFalse(
            is_safe_path("/etc/passwd", safety.FILE_ROOTS, allow_root_itself=True)
        )

    def test_require_safe_raises(self):
        with self.assertRaises(PathGuardError):
            require_safe("/etc/passwd")
        self.assertEqual(require_safe("/tmp/x"), Path("/tmp/x"))


class SymlinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="zarchcleaner-test-"))
        self.root = self.tmp / "root"
        self.outside = self.tmp / "outside"
        self.root.mkdir()
        self.outside.mkdir()
        (self.outside / "precious.txt").write_text("do not delete")
        self.roots = (str(self.root),)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_symlink_escape_is_rejected(self):
        link = self.root / "escape"
        link.symlink_to(self.outside, target_is_directory=True)
        self.assertFalse(is_safe_path(link / "precious.txt", self.roots))
        self.assertFalse(is_safe_path(self.outside / "precious.txt", self.roots))

    def test_symlink_itself_may_be_unlinked(self):
        link = self.root / "escape"
        link.symlink_to(self.outside, target_is_directory=True)
        self.assertTrue(is_safe_path(link, self.roots))

    def test_plain_children_are_accepted(self):
        (self.root / "junk").mkdir()
        (self.root / "junk" / "file.bin").write_bytes(b"x" * 32)
        self.assertTrue(is_safe_path(self.root / "junk", self.roots))
        self.assertTrue(is_safe_path(self.root / "junk" / "file.bin", self.roots))

    def test_root_itself_needs_explicit_permission(self):
        self.assertFalse(is_safe_path(self.root, self.roots))
        self.assertTrue(is_safe_path(self.root, self.roots, allow_root_itself=True))


if __name__ == "__main__":
    unittest.main()
