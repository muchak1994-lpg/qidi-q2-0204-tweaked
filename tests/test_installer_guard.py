#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""Three faults found by the installer audit of 27.11.2026, against a pretend printer (no network, no QIDI files):
a print started while the installer runs, an update that dropped the optional modules, and the camera AI service
left switched off after an uninstall.

Run:  python tests/test_installer_guard.py
"""
import contextlib
import io
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import build  # noqa: E402
import firmware  # noqa: E402
import install  # noqa: E402
from test_install import MODS, STOCK, FakePrinter, sha  # noqa: E402

FAN = "/home/qidi/klipper/klippy/extras/fan.py"
CFG = "/home/qidi/printer_data/config/printer.cfg"


class Printer(FakePrinter):
    target = 0  # nozzle target temperature

    def http_json(self, url):
        answer = super().http_json(url)
        answer["result"]["status"]["extruder"]["target"] = self.target
        return answer


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.saved = (firmware.load_index, firmware.extract, firmware.extract_many, install.build.load_modules,
                      install.load_history)
        firmware.load_index = lambda: {"files": {p: {"sha256": sha(d)} for p, d in STOCK.items()}}
        firmware.extract = lambda p: STOCK[p]
        firmware.extract_many = lambda paths: {p: STOCK[p] for p in paths}
        self.built = build.build(MODS, stock_reader=lambda p: STOCK[p])
        self.p = Printer(STOCK)
        self.out = io.StringIO()

    def tearDown(self):
        (firmware.load_index, firmware.extract, firmware.extract_many, install.build.load_modules,
         install.load_history) = self.saved
        shutil.rmtree(self.tmp)

    def quiet(self, fn, *args, **kw):
        with contextlib.redirect_stdout(self.out):
            return fn(*args, **kw)

    def install_all(self, host="h"):
        changes = install.plan(self.p, MODS, built=self.built)
        return self.quiet(install.do_install, self.p, MODS, changes, host, backups=self.tmp)

    def print_starts_after_the_files_are_written(self):
        """The printer is idle until the first file is written, then a print runs."""
        real = self.p.install

        def install_then_print(*args):
            real(*args)
            self.p.state = "printing"

        self.p.install = install_then_print


# ------------------------------------------------------------------ 1: never restart a printer that prints
class BusyPrinterTest(Base):
    def test_print_started_while_the_installer_waited_for_yes_stops_before_any_write(self):
        changes = install.plan(self.p, MODS, built=self.built)
        self.p.state = "printing"  # started on the screen while the question was open
        with self.assertRaisesRegex(install.InstallError, "printing"):
            self.quiet(install.do_install, self.p, MODS, changes, "h", backups=self.tmp)
        self.assertEqual(self.p.read(FAN), STOCK[FAN])
        self.assertEqual((self.p.actions, self.p.restarts), ([], []))

    def test_print_started_during_the_copy_gets_no_action_and_no_restart(self):
        changes = install.plan(self.p, MODS, built=self.built)
        self.print_starts_after_the_files_are_written()
        with self.assertRaisesRegex(install.InstallError, "printing"):
            self.quiet(install.do_install, self.p, MODS, changes, "h", backups=self.tmp)
        self.assertEqual((self.p.actions, self.p.restarts), ([], []))
        text = self.out.getvalue()
        self.assertIn("NOT FINISHED", text)
        self.assertNotIn("turn the\nprinter off", text)  # that advice would kill the running print
        # after the print: the next run does the actions and restarts that are still owed
        self.p.state = "standby"
        del self.p.install
        time.sleep(1.1)  # backup folders are named to the second
        self.install_all()
        self.assertEqual(self.p.restarts, ["klipper"])
        self.assertIn(["chattr", "+i", "/home/qidi/download"], self.p.actions)

    def test_heater_switched_on_during_the_copy_also_stops_the_restart(self):
        changes = install.plan(self.p, MODS, built=self.built)
        real = self.p.install

        def install_then_heat(*args):
            real(*args)
            self.p.target = 210

        self.p.install = install_then_heat
        with self.assertRaisesRegex(install.InstallError, "heater"):
            self.quiet(install.do_install, self.p, MODS, changes, "h", backups=self.tmp)
        self.assertEqual(self.p.restarts, [])

    def test_uninstall_does_not_start_while_printing(self):
        backup = self.install_all()
        installed = self.p.read(FAN)
        self.p.actions, self.p.restarts, self.p.state = [], [], "paused"
        with self.assertRaisesRegex(install.InstallError, "paused"):
            self.quiet(install.do_uninstall, self.p, backup)
        self.assertEqual(self.p.read(FAN), installed)
        self.assertEqual((self.p.actions, self.p.restarts), ([], []))

    def test_uninstall_gets_no_restart_when_a_print_starts_during_it(self):
        backup = self.install_all()
        self.p.actions, self.p.restarts = [], []
        self.print_starts_after_the_files_are_written()
        with self.assertRaisesRegex(install.InstallError, "printing"):
            self.quiet(install.do_uninstall, self.p, backup)
        self.assertEqual((self.p.actions, self.p.restarts), ([], []))

    def test_uninstall_from_stock_gets_no_restart_when_a_print_starts_during_it(self):
        self.install_all()
        self.p.actions, self.p.restarts = [], []
        self.print_starts_after_the_files_are_written()
        saved = install.build.build
        install.build.build = lambda sel: self.built
        try:
            with self.assertRaisesRegex(install.InstallError, "printing"):
                self.quiet(install.do_uninstall_stock, self.p, MODS)
        finally:
            install.build.build = saved
        self.assertEqual((self.p.actions, self.p.restarts), ([], []))

    def klipper_is_starting(self, answers):
        """The next `answers` status queries fail the way they do while Klipper or Moonraker restart."""
        real, left = self.p.http_json, [answers]

        def http_json(url):
            if left[0] > 0:
                left[0] -= 1
                if left[0] % 2:
                    raise install.InstallError("curl failed")  # Moonraker not listening yet
                return {"error": {"message": "Klippy Disconnected"}}
            return real(url)

        self.p.http_json = http_json
        self.waited = []
        saved = install.time.sleep
        install.time.sleep = self.waited.append
        self.addCleanup(setattr, install.time, "sleep", saved)

    def test_a_klipper_that_is_still_starting_is_waited_for(self):
        """An optional module installed right after the main install: Klipper is restarting at that moment."""
        self.klipper_is_starting(5)
        self.quiet(install.check_idle, self.p)
        self.assertEqual(len(self.waited), 5)
        self.assertIn("Waiting", self.out.getvalue())

    def test_a_klipper_that_never_answers_ends_with_a_plain_message(self):
        self.klipper_is_starting(10 ** 6)
        with self.assertRaisesRegex(install.InstallError, "could not read"):
            self.quiet(install.check_idle, self.p)
        self.assertGreaterEqual(sum(self.waited), 120)  # QIDI's Klipper needed about 90 s on 27.11.2026

    def test_toolhead_check_sends_no_gcode_to_a_printing_printer(self):
        sent = []
        self.p.state = "printing"
        self.p.gcode = sent.append
        status = self.p.http_json
        self.p.http_json = lambda url: (
            {"result": {"state": "ready"}} if url == "/printer/info" else
            {"result": {"objects": ["q2_thr_check"]}} if url == "/printer/objects/list" else status(url))
        self.assertIsNone(self.quiet(install.toolhead_check, self.p, self.tmp, 3, lambda s: None))
        self.assertEqual(sent, [])
        self.assertIn("printing", self.out.getvalue())


# ------------------------------------------------------------------ 2: an update keeps the optional modules
class KeepInstalledTest(Base):
    OWN = "/home/qidi/extra/tool.py"

    def setUp(self):
        super().setUp()
        (self.tmp / "mod" / "files").mkdir(parents=True)
        (self.tmp / "mod" / "files" / "tool.py").write_bytes(b"version = 2\n")
        self.mods = [
            {"id": "base", "order": 1, "files": {}},
            {"id": "tool", "order": 2, "default": False, "_dir": self.tmp / "mod",
             "files": {self.OWN: {"source": "files/tool.py"}}},
            {"id": "macro", "order": 3, "default": False, "files": {CFG: {
                "base": "printer", "edits": [["timeout: 43200\n", "timeout: 300\n"]],
                "previous": [[["timeout: 43200\n", "timeout: 600\n"]]]}}},
        ]
        install.build.load_modules = lambda: self.mods
        install.load_history = lambda: {self.OWN: [sha(b"version = 1\n"), sha(b"version = 2\n")]}

    def keep(self, skip=(), extra=()):
        selected = install.select(list(skip), list(extra))
        return [m["id"] for m in self.quiet(install.keep_installed, self.p, selected, list(skip))]

    def test_a_printer_without_optional_modules_stays_without_them(self):
        self.assertEqual(self.keep(), ["base"])

    def test_an_installed_module_is_kept_also_when_it_is_an_older_version(self):
        self.p.files[self.OWN] = [b"version = 1\n", "qidi", "qidi", "644"]
        self.assertEqual(self.keep(), ["base", "tool"])
        self.assertIn("tool", self.out.getvalue())
        self.assertIn("--skip", self.out.getvalue())

    def test_a_module_that_only_edits_a_config_file_is_recognised_now_and_in_its_earlier_form(self):
        for value in (b"300", b"600"):
            self.p.files[CFG][0] = STOCK[CFG].replace(b"43200", value)
            self.assertEqual(self.keep(), ["base", "macro"])

    def test_skip_leaves_it_out(self):
        self.p.files[self.OWN] = [b"version = 2\n", "qidi", "qidi", "644"]
        self.assertEqual(self.keep(skip=["tool"]), ["base"])

    def test_a_changed_file_is_not_taken_over_and_is_reported(self):
        self.p.files[self.OWN] = [b"my own script\n", "qidi", "qidi", "644"]
        self.assertEqual(self.keep(), ["base"])
        self.assertIn(self.OWN, self.out.getvalue())

    def test_asked_for_modules_are_not_listed_twice(self):
        self.p.files[self.OWN] = [b"version = 2\n", "qidi", "qidi", "644"]
        self.assertEqual(self.keep(extra=["tool"]), ["base", "tool"])

    def test_the_update_command_keeps_the_module(self):
        """plan without --with (what install.bat runs) on a printer that has the optional module."""
        self.p.files[self.OWN] = [b"version = 1\n", "qidi", "qidi", "644"]
        seen = []
        saved = (install.SSHPrinter.open, install.show_plan)
        install.SSHPrinter.open = classmethod(lambda cls, *a: self.p)
        install.show_plan = lambda p, selected, host: seen.append([m["id"] for m in selected]) or ([], set(), [])
        self.p.close = lambda: None
        try:
            self.assertEqual(self.quiet(install.main, ["plan", "--host", "h"]), 0)
        finally:
            install.SSHPrinter.open, install.show_plan = saved
        self.assertEqual(seen, [["base", "tool"]])


class NotificationsOnUpdateTest(Base):
    """Keeping the module must not set the notifications up again (and send a test message) on every update."""
    OWN = "/home/qidi/q2-notify/send.sh"

    def run_install(self, *more):
        (self.tmp / "mod").mkdir(exist_ok=True)
        (self.tmp / "mod" / "send.sh").write_bytes(b"#!/bin/sh\n")
        mods = [{"id": "phone-notifications", "order": 1, "default": False, "_dir": self.tmp / "mod",
                 "files": {self.OWN: {"source": "send.sh"}}}]
        install.build.load_modules = lambda: mods
        install.load_history = lambda: {}
        self.p.files[self.OWN] = [b"#!/bin/sh\n", "qidi", "qidi", "755"]
        self.p.close = lambda: None
        configured = []
        saved = (install.SSHPrinter.open, install.show_plan, install.configure_notify)
        install.SSHPrinter.open = classmethod(lambda cls, *a: self.p)
        install.show_plan = lambda p, selected, host: ([], set(), [])
        install.configure_notify = lambda p, host: configured.append(host)
        try:
            argv = ["install", "--host", "h", "--toolhead", "no", "--tailscale", "no", "--orca", "no"]
            self.assertEqual(self.quiet(install.main, argv + list(more)), 0)
        finally:
            install.SSHPrinter.open, install.show_plan, install.configure_notify = saved
        return configured

    def test_a_plain_update_leaves_the_notification_settings_alone(self):
        self.assertEqual(self.run_install(), [])

    def test_asking_for_them_sets_them_up(self):
        self.assertEqual(self.run_install("--with", "phone-notifications"), ["h"])
        self.assertEqual(self.run_install("--notify", "yes"), ["h"])


class RealModulesTest(unittest.TestCase):
    def test_every_optional_module_can_be_recognised_on_a_printer(self):
        for m in build.load_modules():
            if m.get("default", True):
                continue
            files = m.get("files", {})
            self.assertTrue(any("source" in s or s.get("base") == "printer" and s.get("edits") for s in files.values()),
                            m["id"] + " has neither an own file nor a config edit: keep_installed cannot see it")


# ------------------------------------------------------------------ 3: the camera AI service is QIDI's
class FactoryServiceTest(Base):
    AI = [{"id": "ai", "order": 1, "files": {},
           "actions": [["systemctl", "enable", "--now", "algo_app.service"]]},
          {"id": "ours", "order": 2, "files": {},
           "actions": [["systemctl", "enable", "--now", "q2-ours.service"]]}]

    def check(self):
        self.assertIn(["systemctl", "enable", "algo_app.service"], self.p.actions)
        self.assertEqual([a for a in self.p.actions if "disable" in a],
                         [["systemctl", "disable", "--now", "q2-ours.service"]])
        self.assertIn("algo_app", self.p.restarts)  # the restart at the end starts it

    def test_uninstall_leaves_the_ai_service_switched_on(self):
        backup = self.quiet(install.do_install, self.p, self.AI, [], "h", backups=self.tmp)
        self.p.actions, self.p.restarts = [], []
        self.quiet(install.do_uninstall, self.p, backup)
        self.check()

    def test_uninstall_from_stock_leaves_the_ai_service_switched_on(self):
        saved = install.build.build
        install.build.build = lambda sel: ({}, {})
        try:
            self.quiet(install.do_uninstall_stock, self.p, self.AI)
        finally:
            install.build.build = saved
        self.check()


# ------------------------------------------------------------------ a module that left the project is taken off
class RetiredModuleTest(Base):
    """algo-app-recycle left the project in 1.4.1, but an update left it running on the printer (27.11.2026)."""
    UNIT = "/etc/systemd/system/q2-algo-recycle.service"
    SCRIPT = "/usr/local/lib/q2-algo-recycle/q2_algo_recycle.sh"
    DISABLE = ["systemctl", "disable", "--now", "q2-algo-recycle.service"]

    def setUp(self):
        super().setUp()
        install.build.load_modules = lambda: [{"id": "base", "order": 1, "files": {}}]
        install.load_history = lambda: {self.UNIT: [sha(b"unit\n")], self.SCRIPT: [sha(b"script\n")]}
        self.p.close = lambda: None
        self.asked = []

    def put_it_on_the_printer(self, script=b"script\n"):
        self.p.files[self.UNIT] = [b"unit\n", "root", "root", "644"]
        self.p.files[self.SCRIPT] = [script, "root", "root", "755"]

    def left(self):
        return [path for path in (self.UNIT, self.SCRIPT) if path in self.p.files]

    def run_main(self, command="install", answer="yes"):
        saved = (install.SSHPrinter.open, install.show_plan)
        install.SSHPrinter.open = classmethod(lambda cls, *a: self.p)
        install.show_plan = lambda p, selected, host: ([], set(), [])
        install.input = lambda question: self.asked.append(question) or answer
        try:
            argv = [command, "--host", "h", "--toolhead", "no", "--tailscale", "no", "--orca", "no"]
            return self.quiet(install.main, argv)
        finally:
            install.SSHPrinter.open, install.show_plan = saved
            del install.input

    def test_an_update_stops_the_service_and_removes_its_files(self):
        self.put_it_on_the_printer()
        stopped_while_present = []
        real = self.p.action

        def action(argv, check=True):
            if argv == self.DISABLE:
                stopped_while_present.append(self.left())
            return real(argv, check)

        self.p.action = action
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(len(self.asked), 1)  # nothing else to change, still asked first
        self.assertEqual(stopped_while_present, [[self.UNIT, self.SCRIPT]])
        self.assertEqual(self.left(), [])
        self.assertIn(["systemctl", "daemon-reload"], self.p.actions)
        self.assertIn(["rmdir", "/usr/local/lib/q2-algo-recycle"], self.p.actions)
        self.assertIn("algo-app-recycle", self.out.getvalue())

    def test_a_printer_without_it_is_not_asked_and_nothing_runs(self):
        self.assertEqual(self.run_main(), 0)
        self.assertEqual((self.asked, self.p.actions), ([], []))
        self.assertNotIn("algo-app-recycle", self.out.getvalue())

    def test_plan_names_it_and_changes_nothing(self):
        self.put_it_on_the_printer()
        self.assertEqual(self.run_main("plan"), 0)
        self.assertIn(self.SCRIPT, self.out.getvalue())
        self.assertEqual((self.left(), self.p.actions), ([self.UNIT, self.SCRIPT], []))

    def test_answering_no_keeps_it(self):
        self.put_it_on_the_printer()
        self.assertEqual(self.run_main(answer="no"), 0)
        self.assertEqual((self.left(), self.p.actions), ([self.UNIT, self.SCRIPT], []))

    def test_a_script_changed_by_the_owner_is_left_alone_and_reported(self):
        self.put_it_on_the_printer(script=b"my own version\n")
        self.assertEqual(self.run_main(), 0)
        self.assertEqual((self.left(), self.p.actions, self.asked), ([self.UNIT, self.SCRIPT], [], []))
        self.assertIn("left alone", self.out.getvalue())

    def test_a_print_started_before_yes_keeps_it(self):
        self.put_it_on_the_printer()
        saved = install.find_retired

        def then_print(p):
            found = saved(p)
            self.p.state = "printing"
            return found

        install.find_retired = then_print
        self.addCleanup(setattr, install, "find_retired", saved)
        self.assertEqual(self.run_main(), 1)
        self.assertEqual((self.left(), self.p.actions), ([self.UNIT, self.SCRIPT], []))

    def test_both_uninstalls_remove_it_even_without_a_record_of_its_install(self):
        backup = self.quiet(install.do_install, self.p, [], [], "h", backups=self.tmp)
        self.put_it_on_the_printer()
        self.quiet(install.do_uninstall, self.p, backup)
        self.assertEqual(self.left(), [])
        self.put_it_on_the_printer()
        saved = install.build.build
        install.build.build = lambda sel: ({}, {})
        try:
            self.quiet(install.do_uninstall_stock, self.p, [])
        finally:
            install.build.build = saved
        self.assertEqual(self.left(), [])
        self.assertEqual(self.p.actions.count(self.DISABLE), 2)


class RetiredHistoryTest(unittest.TestCase):
    def test_the_released_files_of_every_retired_module_are_still_known(self):
        history = install.load_history()
        for m in install.RETIRED:
            for path in m["files"]:
                self.assertTrue(history.get(path), "%s: no known version of %s" % (m["id"], path))


if __name__ == "__main__":
    unittest.main()
