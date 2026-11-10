#!/usr/bin/env python3
"""Offline tests for tools/orca_profiles.py (no OrcaSlicer needed).

Run:  python tests/test_orca_profiles.py
"""
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import orca_profiles as op  # noqa: E402


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        op.main(list(argv))
    return out.getvalue()


class OrcaProfilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "OrcaSlicer"
        self.user = self.root / "user" / "default"
        (self.user / "process").mkdir(parents=True)
        (self.user / "machine").mkdir(parents=True)
        self.files = op.source_files()
        # the user's own profiles: one unrelated, one with the same name as ours
        self.mine = self.user / "process" / "My own profile.json"
        self.mine.write_text('{"name": "My own profile"}', encoding="utf-8")
        kind, name, _ = next(f for f in self.files if f[1].endswith(".json") and f[0] == "process")
        self.clash = self.user / kind / name
        self.clash.write_text('{"name": "users version"}', encoding="utf-8")
        self.backups_before = set(op.BACKUPS.glob("*.zip")) if op.BACKUPS.is_dir() else set()
        self.common = ("--orca-dir", str(self.root), "--skip-running-check")

    def tearDown(self):
        shutil.rmtree(self.tmp)
        if op.BACKUPS.is_dir():
            for z in set(op.BACKUPS.glob("*.zip")) - self.backups_before:
                z.unlink()
            if not any(op.BACKUPS.iterdir()):
                op.BACKUPS.rmdir()

    def test_sources_are_valid_and_private_data_free(self):
        self.assertTrue(self.files)
        self.assertEqual(op.check_sources(self.files), [])
        for kind, name, path in self.files:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("192.168.", text, name)
            self.assertNotIn("makerbase", text, name)

    def test_dry_run_changes_nothing(self):
        before = sorted(p.name for p in self.user.rglob("*"))
        out = run("install", *self.common)
        self.assertIn("Dry run", out)
        self.assertEqual(before, sorted(p.name for p in self.user.rglob("*")))

    def test_install_adds_only_and_uninstall_removes_only_ours(self):
        out = run("install", "--apply", *self.common)
        self.assertIn("skip (exists, not ours, left untouched)", out)
        # user's files untouched
        self.assertEqual(self.mine.read_text(encoding="utf-8"), '{"name": "My own profile"}')
        self.assertEqual(self.clash.read_text(encoding="utf-8"), '{"name": "users version"}')
        manifest = json.loads((self.user / op.MANIFEST_NAME).read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["files"]), len(self.files) - 1)
        for kind, name, path in self.files:
            dest = self.user / kind / name
            if dest != self.clash:
                self.assertEqual(dest.read_bytes(), path.read_bytes())
        # a backup was made
        self.assertTrue(set(op.BACKUPS.glob("*.zip")) - self.backups_before)
        # second install: nothing to add
        self.assertIn("Nothing to add", run("install", "--apply", *self.common))
        # the user edits one of our profiles -> uninstall keeps it
        edited_rel = sorted(manifest["files"])[0]
        (self.user / edited_rel).write_text('{"edited": true}', encoding="utf-8")
        out = run("uninstall", "--apply", *self.common)
        self.assertIn("keep (you edited it)", out)
        self.assertTrue((self.user / edited_rel).exists())
        self.assertTrue(self.mine.exists())
        self.assertEqual(self.clash.read_text(encoding="utf-8"), '{"name": "users version"}')
        left = json.loads((self.user / op.MANIFEST_NAME).read_text(encoding="utf-8"))
        self.assertEqual(list(left["files"]), [edited_rel])
        for rel in manifest["files"]:
            if rel != edited_rel:
                self.assertFalse((self.user / rel).exists(), rel)

    def test_several_user_folders_need_a_choice(self):
        (self.root / "user" / "123456").mkdir()
        with self.assertRaises(SystemExit):
            run("status", *self.common)
        self.assertIn("Added by this project", run("status", "--user-dir", "default", *self.common))


if __name__ == "__main__":
    unittest.main(verbosity=2)
