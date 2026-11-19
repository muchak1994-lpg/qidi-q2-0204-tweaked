#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
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
import unittest.mock
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
        # No one to answer (stdin is not a terminal): it must stop, not wait. Set here,
        # because on Windows an empty input (NUL) reports itself as a terminal.
        with contextlib.redirect_stdout(io.StringIO()), \
                unittest.mock.patch.object(sys, "stdin", io.StringIO()), \
                self.assertRaises(SystemExit):
            op.main(["status", *self.common])
        self.assertIn("Added by this project", run("status", "--user-dir", "default", *self.common))


class FilamentTest(unittest.TestCase):
    """Filament profiles for the filaments enabled in OrcaSlicer, and the installer's OrcaSlicer step."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "OrcaSlicer"
        self.user = self.root / "user" / "default"
        self.user.mkdir(parents=True)
        conf = {"filaments": ["SUNLU PETG @System", "Not In Our List @System"], "models": []}
        (self.root / "OrcaSlicer.conf").write_text(json.dumps(conf, indent=1) + "\n# MD5 checksum 0123\n",
                                                   encoding="utf-8")
        self.backups_before = set(op.BACKUPS.glob("*.zip")) if op.BACKUPS.is_dir() else set()
        self.common = ("--orca-dir", str(self.root), "--skip-running-check")

    def tearDown(self):
        shutil.rmtree(self.tmp)
        if op.BACKUPS.is_dir():
            for z in set(op.BACKUPS.glob("*.zip")) - self.backups_before:
                z.unlink()
            if not any(op.BACKUPS.iterdir()):
                op.BACKUPS.rmdir()

    def petg(self):
        return self.user / "filament" / "SUNLU PETG (Tweaked).json"

    def test_enabled_filaments(self):
        self.assertEqual(op.enabled_filaments(self.root), ["SUNLU PETG @System", "Not In Our List @System"])
        self.assertEqual(op.enabled_filaments(self.tmp), [])  # no OrcaSlicer.conf
        (self.tmp / "OrcaSlicer.conf").write_text("not json", encoding="utf-8")
        self.assertEqual(op.enabled_filaments(self.tmp), [])
        names = [n for _, n, _ in op.filament_files(["SUNLU PETG @System", "Not In Our List @System"])]
        self.assertEqual(names, ["SUNLU PETG (Tweaked).json", "SUNLU PETG (Tweaked).info"])

    def test_install_adds_only_enabled_filaments_and_uninstall_removes_them(self):
        run("install", "--apply", *self.common)
        self.assertEqual(sorted(p.name for p in (self.user / "filament").iterdir()),
                         ["SUNLU PETG (Tweaked).info", "SUNLU PETG (Tweaked).json"])
        data = json.loads(self.petg().read_text(encoding="utf-8"))
        self.assertEqual(data["during_print_exhaust_fan_speed"], ["75"])
        self.assertTrue(self.user.joinpath("machine").is_dir())
        run("uninstall", "--apply", *self.common)
        self.assertEqual(list((self.user / "filament").iterdir()), [])

    def offer(self, answer, running=False):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), \
                unittest.mock.patch.object(op, "orca_running", return_value=running):
            op.offer("ask", read=lambda prompt: answer, root=self.root)
        return out.getvalue()

    def test_offer_no_changes_nothing(self):
        out = self.offer("n")
        self.assertIn("filaments you use, with the chamber fan set per material: 1", out)
        self.assertFalse(self.petg().exists())
        self.assertFalse((self.user / "machine").exists())

    def test_offer_while_orca_is_open_changes_nothing(self):
        self.assertIn("Close it", self.offer("", running=True))
        self.assertFalse(self.petg().exists())
        self.assertIn("Close it", self.offer("", running=None))

    def test_offer_yes_adds_then_has_nothing_left(self):
        self.offer("")
        self.assertTrue(self.petg().exists())
        self.assertIn("already there", self.offer(""))

    def test_offer_without_orca_or_with_mode_no(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            op.offer("ask", read=lambda prompt: self.fail("must not ask"), root=self.tmp / "none")
            op.offer("no", read=lambda prompt: self.fail("must not ask"), root=self.root)
        self.assertIn("no profiles folder", out.getvalue())
        self.assertFalse(self.petg().exists())


class OrcaRunningTest(unittest.TestCase):
    """tasklist output in the console code page (cp852 on Polish Windows, 0xFF = thousands separator)."""

    def check(self, stdout):
        result = unittest.mock.Mock(stdout=stdout)
        with unittest.mock.patch.object(op.subprocess, "run", return_value=result):
            return op.orca_running()

    def test_non_utf8_tasklist_is_read(self):
        line = b'"explorer.exe","1234","Console","1","123\xff456 K"\r\n'
        self.assertIs(self.check(line), False)
        self.assertIs(self.check(line + b'"orca-slicer.exe","99","Console","1","1\xff000 K"\r\n'), True)

    def test_command_failure_is_unknown(self):
        with unittest.mock.patch.object(op.subprocess, "run", side_effect=OSError("no tasklist")):
            self.assertIsNone(op.orca_running())


if __name__ == "__main__":
    unittest.main(verbosity=2)
