#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""Offline tests for tools/orca_profiles.py (no OrcaSlicer needed).

Run:  python tests/test_orca_profiles.py
"""
import contextlib
import hashlib
import io
import json
import shutil
import sys
import tempfile
import unittest
import unittest.mock
import zipfile
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

    def test_old_filament_copies_of_an_earlier_version_are_backed_up_before_uninstall_removes_them(self):
        # Versions up to 1.2.0 added "(Tweaked)" filament copies (chamber fan per material) and recorded them in the manifest;
        # now the printer profiles set the fan. Uninstall still removes those copies (when unchanged) - after zipping them.
        (self.user / "filament").mkdir()
        old = self.user / "filament" / "SUNLU PETG (Tweaked).json"
        old.write_text('{"name": "SUNLU PETG (Tweaked)"}', encoding="utf-8")
        edited = self.user / "filament" / "eSUN PLA+ (Tweaked).json"
        edited.write_text('{"name": "I changed this"}', encoding="utf-8")
        digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()  # noqa: E731
        manifest = {"project": op.PROJECT, "files": {"filament/SUNLU PETG (Tweaked).json": digest(old),
                                                     "filament/eSUN PLA+ (Tweaked).json": "0" * 64}}
        (self.user / op.MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
        out = run("uninstall", "--apply", *self.common)
        self.assertIn("keep (you edited it): filament/eSUN PLA+ (Tweaked).json", out)
        self.assertFalse(old.exists())
        self.assertTrue(edited.exists())
        zips = sorted(set(op.BACKUPS.glob("*.zip")) - self.backups_before)
        self.assertEqual(len(zips), 1)
        with zipfile.ZipFile(zips[0]) as zf:
            self.assertIn("filament/SUNLU PETG (Tweaked).json", zf.namelist())

    def test_several_user_folders_need_a_choice(self):
        (self.root / "user" / "123456").mkdir()
        # No one to answer (stdin is not a terminal): it must stop, not wait. Set here,
        # because on Windows an empty input (NUL) reports itself as a terminal.
        with contextlib.redirect_stdout(io.StringIO()), \
                unittest.mock.patch.object(sys, "stdin", io.StringIO()), \
                self.assertRaises(SystemExit):
            op.main(["status", *self.common])
        self.assertIn("Added by this project", run("status", "--user-dir", "default", *self.common))


class InstallStepTest(unittest.TestCase):
    """The OrcaSlicer step of the installer (and install/uninstall into an Orca user folder)."""

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

    def marker(self):
        return self.user / "machine" / "Qidi Q2 0.4 nozzle (Tweaked).json"

    def test_install_adds_printer_and_process_profiles_and_uninstall_removes_them(self):
        run("install", "--apply", *self.common)
        self.assertTrue(self.marker().exists())
        self.assertFalse((self.user / "filament").exists())  # no filament copies any more
        hooked = json.loads(self.marker().read_text(encoding="utf-8"))
        self.assertIn("M106 P3 S255", hooked["before_layer_change_gcode"])
        run("uninstall", "--apply", *self.common)
        self.assertFalse(self.marker().exists())

    def offer(self, answer, running=False):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), \
                unittest.mock.patch.object(op, "orca_running", return_value=running):
            op.offer("ask", read=lambda prompt: answer, root=self.root)
        return out.getvalue()

    def test_offer_no_changes_nothing(self):
        out = self.offer("n")
        self.assertIn("they also set the chamber fan from the filament type): 4", out)
        self.assertFalse(self.marker().exists())
        self.assertFalse((self.user / "machine").exists())

    def test_offer_while_orca_is_open_changes_nothing(self):
        self.assertIn("Close it", self.offer("", running=True))
        self.assertFalse(self.marker().exists())
        self.assertIn("Close it", self.offer("", running=None))

    def test_offer_yes_adds_then_has_nothing_left(self):
        self.offer("")
        self.assertTrue(self.marker().exists())
        self.assertIn("already there", self.offer(""))

    def test_offer_without_orca_or_with_mode_no(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            op.offer("ask", read=lambda prompt: self.fail("must not ask"), root=self.tmp / "none")
            op.offer("no", read=lambda prompt: self.fail("must not ask"), root=self.root)
        self.assertIn("no profiles folder", out.getvalue())
        self.assertFalse(self.marker().exists())


class UpgradeFrom120Test(unittest.TestCase):
    """Version 1.2.0 added printer profiles without the chamber-fan hook (the fan lived in 331 filament copies)."""

    NAME = "Qidi Q2 0.4 nozzle (Tweaked)"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "OrcaSlicer"
        self.user = self.root / "user" / "default"
        (self.user / "machine").mkdir(parents=True)
        self.conf = {"version": "2.4.0", "filaments": [], "models": []}
        self.write_conf()
        self.backups_before = set(op.BACKUPS.glob("*.zip")) if op.BACKUPS.is_dir() else set()
        self.common = ("--orca-dir", str(self.root), "--skip-running-check")
        self.json = self.user / "machine" / (self.NAME + ".json")
        self.info = self.user / "machine" / (self.NAME + ".info")

    def tearDown(self):
        shutil.rmtree(self.tmp)
        if op.BACKUPS.is_dir():
            for z in set(op.BACKUPS.glob("*.zip")) - self.backups_before:
                z.unlink()
            if not any(op.BACKUPS.iterdir()):
                op.BACKUPS.rmdir()

    def write_conf(self):
        (self.root / "OrcaSlicer.conf").write_text(json.dumps(self.conf, indent=1) + "\n# MD5 checksum 0123\n",
                                                   encoding="utf-8")

    def old_profile(self, gcode=None):
        """The profile as 1.2.0 left it, plus what the owner's Orca adds: the printer address."""
        data = json.loads((op.SRC / "machine" / (self.NAME + ".json")).read_text(encoding="utf-8"))
        data.pop("before_layer_change_gcode", None)
        if gcode is not None:
            data["before_layer_change_gcode"] = gcode
        data["print_host"] = "192.168.1.50"
        data["printhost_apikey"] = "secret"
        self.json.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")
        self.info.write_text("sync_info = \nuser_id = u1\nsetting_id = s1\nbase_id = b1\nupdated_time = 1000\n",
                             encoding="utf-8")

    def test_hook_dry_run_names_the_profile_and_changes_nothing(self):
        self.old_profile()
        before = self.json.read_bytes()
        out = run("hook", *self.common)
        self.assertIn(self.NAME, out)
        self.assertIn("Dry run", out)
        self.assertEqual(self.json.read_bytes(), before)

    def test_hook_adds_the_fan_code_and_keeps_everything_else(self):
        self.old_profile()
        out = run("hook", "--apply", *self.common)
        data = json.loads(self.json.read_text(encoding="utf-8"))
        self.assertIn("M106 P3 S255", data["before_layer_change_gcode"])
        self.assertEqual(data["print_host"], "192.168.1.50")      # the printer address and key stay
        self.assertEqual(data["printhost_apikey"], "secret")
        self.assertEqual(data["name"], self.NAME)
        self.assertIn("updated_time = ", self.info.read_text(encoding="utf-8"))
        self.assertNotIn("updated_time = 1000", self.info.read_text(encoding="utf-8"))  # Orca then sees it as newer
        self.assertIn("setting_id = s1", self.info.read_text(encoding="utf-8"))
        self.assertTrue(set(op.BACKUPS.glob("*.zip")) - self.backups_before)
        self.assertIn("Backup", out)
        self.assertIn("nothing to add", run("hook", "--apply", *self.common).lower())  # second time: nothing left

    def test_hook_leaves_a_profile_with_its_own_before_layer_code_alone(self):
        self.old_profile(gcode="M117 mine")
        run("hook", "--apply", *self.common)
        self.assertEqual(json.loads(self.json.read_text(encoding="utf-8"))["before_layer_change_gcode"], "M117 mine")

    def test_hook_leaves_other_printers_alone(self):
        other = self.user / "machine" / "Some Other Printer.json"
        other.write_text(json.dumps({"name": "Some Other Printer"}), encoding="utf-8")
        run("hook", "--apply", *self.common)
        self.assertEqual(json.loads(other.read_text(encoding="utf-8")), {"name": "Some Other Printer"})

    def test_hook_needs_orca_closed(self):
        self.old_profile()
        with unittest.mock.patch.object(op, "orca_running", return_value=True), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            op.main(["hook", "--apply", "--orca-dir", str(self.root)])
        self.assertNotIn("before_layer_change_gcode", json.loads(self.json.read_text(encoding="utf-8")))

    def offer(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), unittest.mock.patch.object(op, "orca_running", return_value=False):
            op.offer("ask", read=lambda prompt: "n", root=self.root)
        return out.getvalue()

    def test_installer_step_points_out_a_profile_without_the_fan_code(self):
        self.old_profile()
        for kind in ("machine", "process"):  # everything else of the project is there already
            for k, name, path in op.source_files():
                if k == kind and name != self.NAME + ".json" and name != self.NAME + ".info":
                    (self.user / k).mkdir(exist_ok=True)
                    (self.user / k / name).write_bytes(path.read_bytes())
        out = self.offer()
        self.assertIn("already there", out)
        self.assertIn(self.NAME, out)
        self.assertIn("py tools/orca_profiles.py hook --apply", out)
        self.assertIn("update OrcaSlicer", out)                  # 2.4.0 is older than the one the hook was checked with
        self.assertIn("2.4.0", out)

    def test_no_hint_when_the_profile_has_the_fan_code_and_orca_is_current(self):
        self.old_profile()
        run("hook", "--apply", *self.common)
        for k, name, path in op.source_files():
            (self.user / k).mkdir(exist_ok=True)
            if not (self.user / k / name).exists():
                (self.user / k / name).write_bytes(path.read_bytes())
        self.conf["version"] = op.CHECKED_WITH_ORCA
        self.write_conf()
        out = self.offer()
        self.assertIn("already there", out)
        self.assertNotIn("hook --apply", out)
        self.assertNotIn("update OrcaSlicer", out)

    def test_the_account_folder_orca_uses_is_chosen_without_asking(self):
        (self.root / "user" / "9acef6b1").mkdir()
        self.conf["preset_folder"] = "9acef6b1"
        self.write_conf()
        with unittest.mock.patch.object(sys, "stdin", io.StringIO()):
            self.assertEqual(op.pick_user_dir(self.root, None).name, "9acef6b1")
        self.conf["preset_folder"] = "gone"       # a folder that does not exist: back to asking
        self.write_conf()
        with unittest.mock.patch.object(sys, "stdin", io.StringIO()), self.assertRaises(SystemExit):
            op.pick_user_dir(self.root, None)


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
