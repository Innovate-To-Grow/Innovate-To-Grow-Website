"""Regression checks for image package security requirements (no network needed)."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INSTALLER = ROOT / "src/security/install-debian-floors.sh"
FLOORS = ROOT / "src/security/debian"


class DebianSecurityFloorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.floors = self.root / "floors"
        self.floors.mkdir()
        self.log = self.root / "apt-arguments"
        self.env = os.environ | {
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "APT_LOG": str(self.log),
            "INSTALLED_VERSION": "5.40.1-6+deb13u1",
        }
        self.command("apt-get", 'printf "%s\\n" "$@" > "$APT_LOG"; exit "${APT_EXIT:-0}"')
        self.command("dpkg-query", 'printf "%s" "$INSTALLED_VERSION"; exit "${QUERY_EXIT:-0}"')
        # Most tests exercise fail-closed control flow independently of dpkg's
        # implementation. Linux-only tests below use the actual version engine.
        self.command("dpkg", 'exit "${COMPARE_EXIT:-0}"')

    def command(self, name, script):
        path = self.bin / name
        path.write_text(f"#!/bin/sh\n{script}\n")
        path.chmod(0o755)

    def requirement(self, content, name="alert-1.txt"):
        (self.floors / name).write_text(content)

    def run_installer(self):
        return subprocess.run(
            ["sh", str(INSTALLER), str(self.floors)], env=self.env, capture_output=True, text=True, check=False
        )

    def test_installs_current_candidates_and_verifies_each_alert(self):
        self.requirement("# first finding\nperl-base 5.40.1-6+deb13u1\n")
        self.requirement("perl-base 5.40.1-6+deb13u1\n", "alert-2.txt")
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log.read_text().splitlines(), ["install", "-y", "--no-install-recommends", "perl-base"])
        self.assertEqual(result.stdout.count("satisfies"), 2)

    def test_old_version_fails_even_when_apt_succeeds(self):
        self.requirement("perl-base 5.40.1-6+deb13u1\n")
        self.env.update(INSTALLED_VERSION="5.40.1-6", COMPARE_EXIT="1")
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("older than required", result.stderr)

    def test_apt_failure_is_not_masked(self):
        self.requirement("perl-base 5.40.1-6+deb13u1\n")
        self.env["APT_EXIT"] = "100"
        self.assertEqual(self.run_installer().returncode, 100)

    def test_missing_installed_package_fails(self):
        self.requirement("perl-base 5.40.1-6+deb13u1\n")
        self.env["QUERY_EXIT"] = "1"
        self.assertNotEqual(self.run_installer().returncode, 0)

    def test_empty_requirements_fail(self):
        self.requirement("# no package\n")
        self.assertNotEqual(self.run_installer().returncode, 0)
        self.assertFalse(self.log.exists())

    def test_invalid_requirements_never_reach_apt(self):
        for content in ["--allow-unauthenticated 1\n", "perl-base\n", "perl-base 1 extra\n", "perl-base x\n"]:
            with self.subTest(content=content):
                self.requirement(content)
                self.assertNotEqual(self.run_installer().returncode, 0)
                self.assertFalse(self.log.exists())

    @unittest.skipUnless(shutil.which("dpkg"), "Debian version comparison requires dpkg")
    def test_debian_security_revision_and_future_updates(self):
        (self.bin / "dpkg").unlink()
        self.requirement("perl-base 5.40.1-6+deb13u1\n")
        for version, accepted in [("5.40.1-6", False), ("5.40.1-6+deb13u1", True), ("5.40.1-6+deb13u2", True)]:
            with self.subTest(version=version):
                self.env["INSTALLED_VERSION"] = version
                self.assertEqual(self.run_installer().returncode == 0, accepted)

    @unittest.skipUnless(shutil.which("dpkg"), "Debian version comparison requires dpkg")
    def test_debian_tilde_and_epoch_versions(self):
        (self.bin / "dpkg").unlink()
        self.requirement("libpcre2-8-0 10.46-1~deb13u2\n")
        for version, accepted in [("10.46-1~deb13u1", False), ("10.46-1~deb13u2", True), ("1:10.46-1", True)]:
            with self.subTest(version=version):
                self.env["INSTALLED_VERSION"] = version
                self.assertEqual(self.run_installer().returncode == 0, accepted)

    def test_repository_floors_are_valid(self):
        self.floors = FLOORS
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("satisfies"), len(list(FLOORS.glob("*.txt"))))


if __name__ == "__main__":
    unittest.main()
