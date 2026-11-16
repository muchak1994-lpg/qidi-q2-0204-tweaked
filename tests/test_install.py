#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""Install / uninstall against a pretend printer (no network, no QIDI files).

Run:  python tests/test_install.py
"""
import json
import time
import hashlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import build  # noqa: E402
import firmware  # noqa: E402
import install  # noqa: E402

sha = lambda b: hashlib.sha256(b).hexdigest()
STOCK = {
    "/home/qidi/klipper/klippy/extras/fan.py": b"speed = 1\r\nlimit = 2\r\n",
    "/home/qidi/printer_data/config/printer.cfg": b"[idle_timeout]\r\ntimeout: 43200\r\n\r\n[x]\r\n",
}


class FakePrinter:
    def __init__(self, files, state="standby"):
        self.files = {p: [d, "qidi", "netdev", "644"] for p, d in files.items()}
        self.state, self.actions, self.restarts = state, [], []
        self.firmware_0204 = True
        self.db = {}
        self.tz = "Etc/UTC"

    def sha(self, path):
        if path == "/home/qidi/update/firmware_manifest.json":
            return firmware.MANIFEST_SHA256 if self.firmware_0204 else "0" * 64
        return sha(self.files[path][0]) if path in self.files else None

    def read(self, path):
        return self.files[path][0] if path in self.files else None

    def stat(self, path):
        return self.files[path][1:] if path in self.files else None

    def install(self, data, path, owner, group, mode):
        self.files[path] = [data, owner, group, mode]

    def remove(self, path):
        self.files.pop(path, None)

    def action(self, argv, check=True):
        self.actions.append(argv)
        if argv[0] == "moonraker-db":
            self.db[(argv[1], argv[2])] = argv[3]
        if argv[0] == "moonraker-db-delete":
            self.db.pop((argv[1], argv[2]), None)
        if argv[0] == "timezone":
            self.tz = argv[1]

    def timezone(self):
        return self.tz

    def db_value(self, namespace, key):
        return self.db.get((namespace, key))

    def restart(self, name):
        self.restarts.append(name)

    def needs(self, argv):
        if argv[0] == "timezone":
            return self.tz != argv[1]
        if argv[0] == "moonraker-db":
            return self.db.get((argv[1], argv[2])) != argv[3]
        return argv not in self.actions

    def http_json(self, url):
        return {"result": {"status": {"print_stats": {"state": self.state},
                                      "extruder": {"target": 0}, "heater_bed": {"target": 0}}}}


MODS = [
    {"id": "fan", "order": 1, "restart": ["klipper"],
     "files": {"/home/qidi/klipper/klippy/extras/fan.py": {"edits": [["limit = 2\r\n", "limit = 3\r\n"]]}}},
    {"id": "idle", "order": 2, "restart": ["klipper"],
     "files": {"/home/qidi/printer_data/config/printer.cfg": {"base": "printer",
                                                              "edits": [["timeout: 43200\n", "timeout: 300\n"]]}}},
    {"id": "guard", "order": 3, "actions": [["chattr", "+i", "/home/qidi/download"]], "files": {}},
]


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.saved = (firmware.load_index, firmware.extract, firmware.extract_many)
        firmware.load_index = lambda: {"files": {p: {"sha256": sha(d)} for p, d in STOCK.items()}}
        firmware.extract = lambda p: STOCK[p]
        firmware.extract_many = lambda paths: {p: STOCK[p] for p in paths}
        self.built = build.build(MODS, stock_reader=lambda p: STOCK[p])
        # the owner's printer.cfg: LF line ends and a calibration block after SAVE_CONFIG
        mine = dict(STOCK)
        mine["/home/qidi/printer_data/config/printer.cfg"] = b"[idle_timeout]\ntimeout: 43200\n\n[x]\n#*# mesh = 1\n"
        self.p = FakePrinter(mine)
        self.p.files["/root/uuid"] = [b"abc\n", "root", "root", "644"]

    def tearDown(self):
        firmware.load_index, firmware.extract, firmware.extract_many = self.saved
        shutil.rmtree(self.tmp)

    def test_install_then_uninstall(self):
        install.check_printer(self.p)
        changes = install.plan(self.p, MODS, built=self.built)
        self.assertEqual(sorted(c[2] for c in changes), ["config", "replace"])
        backup = install.do_install(self.p, MODS, changes, "1.2.3.4", backups=self.tmp)
        cfg = self.p.read("/home/qidi/printer_data/config/printer.cfg")
        self.assertEqual(cfg, b"[idle_timeout]\ntimeout: 300\n\n[x]\n#*# mesh = 1\n")  # calibration kept
        self.assertEqual(self.p.read("/home/qidi/klipper/klippy/extras/fan.py"), b"speed = 1\r\nlimit = 3\r\n")
        self.assertEqual(self.p.actions, [["chattr", "+i", "/home/qidi/download"]])
        self.assertEqual(self.p.restarts, ["klipper"])
        self.assertEqual(install.plan(self.p, MODS, built=self.built), [])  # second run: nothing to do
        # the owner saves a new calibration after the install
        self.p.files["/home/qidi/printer_data/config/printer.cfg"][0] += b"#*# shaper = 9\n"
        install.do_uninstall(self.p, backup)
        self.assertEqual(self.p.read("/home/qidi/klipper/klippy/extras/fan.py"), STOCK[
            "/home/qidi/klipper/klippy/extras/fan.py"])
        self.assertEqual(self.p.read("/home/qidi/printer_data/config/printer.cfg"),
                         b"[idle_timeout]\ntimeout: 43200\n\n[x]\n#*# mesh = 1\n#*# shaper = 9\n")
        self.assertIn(["chattr", "-i", "/home/qidi/download"], self.p.actions)

    def test_uninstall_uses_every_backup(self):  # audit 16.11.2026: a later small run hid the first backup
        fan = "/home/qidi/klipper/klippy/extras/fan.py"
        install.do_install(self.p, MODS, install.plan(self.p, MODS, built=self.built), "h", backups=self.tmp)
        time.sleep(1.1)  # backups are named by the second
        # a later run that only has an action to do (e.g. a card the user switched off again)
        extra = MODS + [{"id": "db", "order": 9, "files": {},
                         "actions": [["moonraker-db", "fluidd", "k", "false"]]}]
        install.do_install(self.p, extra, [], "h", backups=self.tmp)
        time.sleep(1.1)
        # and an upgrade run: the backup of fan.py now holds OUR earlier version, not QIDI's
        mine = self.p.read(fan)
        self.p.files[fan][0] = mine.replace(b"limit = 3", b"limit = 4")
        found = install.host_backups("h", self.tmp)
        self.assertEqual(len(found), 2)
        install.do_uninstall(self.p, found)
        self.assertEqual(self.p.read(fan), b"speed = 1\r\nlimit = 4\r\n")  # changed by hand since: left alone
        self.p.files[fan][0] = mine
        install.do_uninstall(self.p, found)
        self.assertEqual(self.p.read(fan), STOCK[fan])
        self.assertEqual(self.p.read("/home/qidi/printer_data/config/printer.cfg"),
                         b"[idle_timeout]\ntimeout: 43200\n\n[x]\n#*# mesh = 1\n")
        self.assertNotIn(("fluidd", "k"), self.p.db)  # was not there before: removed

    def test_backups_from_before_a_reflash_are_ignored(self):
        fan = "/home/qidi/klipper/klippy/extras/fan.py"
        install.do_install(self.p, MODS, install.plan(self.p, MODS, built=self.built), "h", backups=self.tmp)
        time.sleep(1.1)
        # reflash: QIDI's files again (an old-looking file of ours is NOT on the printer any more)
        self.p.files[fan][0] = STOCK[fan]
        self.p.files["/home/qidi/printer_data/config/printer.cfg"][0] = b"[idle_timeout]\ntimeout: 43200\n"
        self.p.actions.clear()
        install.do_install(self.p, MODS, install.plan(self.p, MODS, built=self.built), "h", backups=self.tmp)
        files, actions, complete = install.merged_record(install.host_backups("h", self.tmp))
        self.assertTrue(complete)
        self.assertEqual({e["_backup"] for e in files.values()}, {install.host_backups("h", self.tmp)[-1]})
        self.assertEqual(actions, [["chattr", "+i", "/home/qidi/download"]])  # only the run after the reflash
        install.do_uninstall(self.p, install.host_backups("h", self.tmp))
        self.assertEqual(self.p.read(fan), STOCK[fan])

    def test_stopped_install_is_finished_by_the_next_run(self):  # audit 16.11.2026
        changes = install.plan(self.p, MODS, built=self.built)
        real = self.p.action

        def fail(argv, check=True):
            raise install.InstallError("boom")
        self.p.action = fail
        with self.assertRaises(install.InstallError):
            install.do_install(self.p, MODS, changes, "h", backups=self.tmp)
        self.assertEqual(self.p.restarts, [])
        self.p.action = real
        time.sleep(1.1)
        self.assertEqual(install.unfinished_modules("h", self.tmp), {"fan", "idle"})
        install.do_install(self.p, MODS, install.plan(self.p, MODS, built=self.built), "h", backups=self.tmp)
        self.assertEqual(self.p.restarts, ["klipper"])
        self.assertEqual(install.unfinished_modules("h", self.tmp), set())

    def test_time_zone_problem_does_not_stop_the_install(self):  # audit 16.11.2026
        mods = MODS + [{"id": "tz", "order": 9, "files": {}, "actions": [["pc-timezone"]]}]
        saved = install.pc_timezone
        install.pc_timezone = lambda: "Europe/Kyiv"
        real = self.p.action

        def no_such_zone(argv, check=True):
            if argv[0] == "timezone":
                raise install.InstallError("printer command failed (1): timedatectl")
            real(argv, check)
        self.p.action = no_such_zone
        try:
            install.do_install(self.p, mods, install.plan(self.p, mods, built=self.built), "h", backups=self.tmp)
        finally:
            install.pc_timezone = saved
        self.assertEqual(self.p.restarts, ["klipper"])
        self.assertEqual(self.p.tz, "Etc/UTC")

    def test_zone_unknown_to_the_printer_is_skipped(self):
        saved = install.pc_timezone
        install.pc_timezone = lambda: "Europe/Kyiv"
        self.p.has_timezone = lambda zone: False
        try:
            self.assertIsNone(install.resolve_action(self.p, ["pc-timezone"]))
        finally:
            install.pc_timezone = saved

    def test_pc_zone_names_cleaned(self):
        for raw, zone in ((":Europe/Warsaw", "Europe/Warsaw"), ("/usr/share/zoneinfo/Europe/Warsaw", "Europe/Warsaw"),
                          ("CET-1CEST,M3.5.0,M10.5.0/3", None), (":/etc/localtime", None), ("", None)):
            self.assertEqual(install.clean_timezone(raw), zone, raw)

    def test_collapsed_mesh_card_is_left_alone(self):
        layouts = {"dashboard": {"c": [{"id": "bed-mesh-card", "enabled": True, "collapsed": True}]}}
        self.assertIsNone(install.fluidd_layouts_with_card(json.dumps(layouts), "bed-mesh-card"))

    def test_actions_only_when_needed(self):
        mods = MODS + [{"id": "svc", "order": 4, "files": {"/home/qidi/klipper/klippy/extras/fan.py": {}},
                        "actions": [["systemctl", "daemon-reload"]]}]
        changes = install.plan(self.p, MODS, built=self.built)
        acts = install.pending_actions(self.p, MODS, changes)
        self.assertEqual(acts, [("guard", ["chattr", "+i", "/home/qidi/download"])])
        install.do_install(self.p, MODS, changes, "1.2.3.4", backups=self.tmp)
        # second run: files in place, lock already set -> nothing at all
        changes = install.plan(self.p, MODS, built=self.built)
        self.assertEqual((changes, install.pending_actions(self.p, MODS, changes)), ([], []))
        # a non-state action runs only for a module whose files change
        self.assertEqual(install.pending_actions(self.p, mods, []), [])

    def test_moonraker_db_entry_is_a_state_action(self):
        act = ["moonraker-db", "fluidd", "uiSettings.general.axis.z.inverted", "false"]
        mods = [{"id": "fz", "order": 5, "files": {}, "actions": [act]}]
        self.assertTrue(install.is_state_action(act))
        self.assertEqual(install.pending_actions(self.p, mods, []), [("fz", act)])  # no file change needed
        self.p.action(act)
        self.assertEqual(install.pending_actions(self.p, mods, []), [])  # already set -> skipped
        self.assertIsNone(install.undo_action(act))  # no value to put back -> left alone
        factory = act + ["true"]  # a module may name QIDI's factory value (used by uninstall --from-stock)
        self.assertEqual(install.undo_action(factory), act[:3] + ["true"])

    def test_moonraker_db_entry_comes_back_on_uninstall(self):
        key = ("fluidd", "uiSettings.general.axis.z.inverted")
        act = ["moonraker-db", key[0], key[1], "false", "true"]  # "true": QIDI's factory value
        mods = [{"id": "fz", "order": 5, "files": {}, "actions": [act]}]
        self.p.db[key] = '"mine"'  # whatever the user had before the install
        backup = install.do_install(self.p, mods, [], "1.2.3.4", backups=self.tmp)
        self.assertEqual(self.p.db[key], "false")
        install.do_uninstall(self.p, backup)
        self.assertEqual(self.p.db[key], '"mine"')  # exactly the earlier value, not the factory one

    def test_upgrade_from_an_earlier_version_of_ours(self):
        fan = "/home/qidi/klipper/klippy/extras/fan.py"
        cfg = "/home/qidi/printer_data/config/printer.cfg"
        old_fan = b"speed = 1\r\nlimit = 2.5\r\n"  # what an earlier release installed
        self.p.files[fan][0] = old_fan
        self.p.files[cfg][0] = b"[idle_timeout]\ntimeout: 600\n\n[x]\n#*# mesh = 1\n"
        mods = [dict(m) for m in MODS]
        mods[1] = {"id": "idle", "order": 2, "restart": ["klipper"], "files": {cfg: {
            "base": "printer", "edits": [["timeout: 43200\n", "timeout: 300\n"]],
            "previous": [[["timeout: 43200\n", "timeout: 600\n"]]]}}}
        built = build.build(mods, stock_reader=lambda p: STOCK[p])
        saved = install.load_history
        install.load_history = lambda: {fan: [hashlib.sha256(old_fan).hexdigest()]}
        try:
            changes = {c[0]: c for c in install.plan(self.p, mods, built=built)}
        finally:
            install.load_history = saved
        self.assertEqual(changes[fan][2], "upgrade")
        self.assertEqual(changes[cfg][1], b"[idle_timeout]\ntimeout: 300\n\n[x]\n#*# mesh = 1\n")

    def test_uninstall_from_stock_without_backup(self):
        changes = install.plan(self.p, MODS, built=self.built)
        install.do_install(self.p, MODS, changes, "1.2.3.4", backups=self.tmp)
        self.p.files["/home/qidi/klipper/klippy/extras/fan.py"]  # installed
        saved = install.build.build
        install.build.build = lambda sel: self.built
        try:
            install.do_uninstall_stock(self.p, MODS)
        finally:
            install.build.build = saved
        self.assertEqual(self.p.read("/home/qidi/klipper/klippy/extras/fan.py"),
                         STOCK["/home/qidi/klipper/klippy/extras/fan.py"])
        self.assertEqual(self.p.read("/home/qidi/printer_data/config/printer.cfg"),
                         b"[idle_timeout]\ntimeout: 43200\n\n[x]\n#*# mesh = 1\n")
        self.assertIn(["chattr", "-i", "/home/qidi/download"], self.p.actions)

    def test_unknown_file_state_stops_before_any_change(self):
        self.p.files["/home/qidi/klipper/klippy/extras/fan.py"][0] = b"someone else's version\r\n"
        with self.assertRaises(install.InstallError):
            install.plan(self.p, MODS, built=self.built)

    def test_busy_printer_is_refused(self):
        install.check_printer(self.p)
        for state in ("printing", "paused"):
            self.p.state = state
            with self.assertRaisesRegex(install.InstallError, state):
                install.check_printer(self.p)
            install.check_printer(self.p, require_idle=False)  # "plan" only reads

    def test_other_firmware_is_refused(self):
        self.p.firmware_0204 = False
        with self.assertRaisesRegex(install.InstallError, "01.01.02.04"):
            install.check_printer(self.p)

    def test_optional_modules_need_with(self):
        mods = [{"id": "a", "files": {}}, {"id": "b", "default": False, "files": {}}]
        saved = install.build.load_modules
        install.build.load_modules = lambda: mods
        try:
            self.assertEqual([m["id"] for m in install.select([])], ["a"])
            self.assertEqual([m["id"] for m in install.select([], ["b"])], ["a", "b"])
            self.assertEqual([m["id"] for m in install.select(["a"], ["b"])], ["b"])
        finally:
            install.build.load_modules = saved

    def test_dns_fallback_hook_changes_one_line_and_comes_back(self):
        hook = b"#!/bin/sh\nA=1\n    " + install.DNS_QIDI + b"\nB=2\n"
        self.p.files["/etc/dhcpcd.exit-hook"] = [hook, "root", "root", "755"]
        mods = [{"id": "dns", "order": 9, "files": {},
                 "generate": {"path": "/etc/dhcpcd.exit-hook", "kind": "dns-fallback"}}]
        built = build.build(mods, stock_reader=lambda p: STOCK[p])
        changes = install.plan(self.p, mods, built=built)
        self.assertEqual([(c[0], c[2]) for c in changes], [("/etc/dhcpcd.exit-hook", "generated")])
        backup = install.do_install(self.p, mods, changes, "1.2.3.4", backups=self.tmp)
        new = self.p.read("/etc/dhcpcd.exit-hook")
        self.assertEqual(new, hook.replace(install.DNS_QIDI, install.DNS_OURS))
        self.assertEqual(self.p.files["/etc/dhcpcd.exit-hook"][1:], ["root", "root", "755"])
        self.assertEqual(install.plan(self.p, mods, built=built), [])  # second run: nothing
        install.do_uninstall(self.p, backup)
        self.assertEqual(self.p.read("/etc/dhcpcd.exit-hook"), hook)
        # without a PC backup: QIDI's line is put back, the file is never removed
        install.do_install(self.p, mods, install.plan(self.p, mods, built=built), "1.2.3.4", backups=self.tmp / "b2")
        saved = install.build.build
        install.build.build = lambda sel: built
        try:
            install.do_uninstall_stock(self.p, mods)
        finally:
            install.build.build = saved
        self.assertEqual(self.p.read("/etc/dhcpcd.exit-hook"), hook)
        # a hook this installer does not know is left alone
        self.p.files["/etc/dhcpcd.exit-hook"][0] = b"#!/bin/sh\nmy own\n"
        self.assertEqual(install.plan(self.p, mods, built=built), [])

    def test_ethernet_mac_matches_qidi_script(self):
        data = install.ethernet_mac_file(self.p)
        digest = hashlib.md5(b"abc\n").hexdigest()
        self.assertIn(("MACAddress=02:%s:%s:%s:%s:%s" % tuple(digest[i:i + 2] for i in range(0, 10, 2))).encode(),
                      data)


class NewActionsTest(unittest.TestCase):
    """Time zone from the PC and Fluidd's bed mesh card (16.11.2026)."""
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.saved = (firmware.load_index, install.pc_timezone)
        firmware.load_index = lambda: {"files": {}}
        install.pc_timezone = lambda: "Europe/Warsaw"
        self.mods = [{"id": "tz", "order": 1, "files": {}, "actions": [["pc-timezone"]]},
                     {"id": "mesh", "order": 2, "files": {}, "actions": [["fluidd-card", "bed-mesh-card"]]}]

    def tearDown(self):
        firmware.load_index, install.pc_timezone = self.saved

    def cards(self, p):
        layouts = json.loads(p.db[("fluidd", "layout.layouts")])
        return {c["id"]: c["enabled"] for col in layouts["dashboard"].values() for c in col}

    def test_install_and_uninstall_fresh_printer(self):
        p = FakePrinter({})
        backup = install.do_install(p, self.mods, [], "h", backups=self.tmp)
        self.assertEqual(p.tz, "Europe/Warsaw")
        cards = self.cards(p)
        self.assertTrue(cards["bed-mesh-card"])
        self.assertTrue(cards["camera-card"])  # the rest of Fluidd's default layout is kept
        self.assertFalse(cards["macros-card"])
        self.assertEqual(install.pending_actions(p, self.mods, []), [])  # second run: nothing to do
        install.do_uninstall(p, backup)
        self.assertEqual(p.tz, "Etc/UTC")
        self.assertNotIn(("fluidd", "layout.layouts"), p.db)  # there was none: removed again

    def test_own_layout_kept(self):
        p = FakePrinter({})
        own = {"dashboard": {"container1": [{"id": "camera-card", "enabled": False, "collapsed": True}],
                             "container2": [{"id": "bed-mesh-card", "enabled": False, "collapsed": True}]},
               "diagnostics": {"x": 1}}
        p.db[("fluidd", "layout.layouts")] = json.dumps(own)
        backup = install.do_install(p, self.mods, [], "h", backups=self.tmp)
        new = json.loads(p.db[("fluidd", "layout.layouts")])
        self.assertEqual(new["dashboard"]["container2"][0], {"id": "bed-mesh-card", "enabled": True, "collapsed": False})
        self.assertEqual(new["dashboard"]["container1"], own["dashboard"]["container1"])
        self.assertEqual(new["diagnostics"], {"x": 1})
        install.do_uninstall(p, backup)
        self.assertEqual(json.loads(p.db[("fluidd", "layout.layouts")]), own)

    def test_unknown_pc_zone_changes_nothing(self):
        install.pc_timezone = lambda: None
        p = FakePrinter({})
        self.assertEqual([a for _, a in install.pending_actions(p, self.mods[:1], [])], [])

    def test_windows_zone_map(self):
        from windows_zones import WINDOWS_TO_IANA
        self.assertEqual(WINDOWS_TO_IANA["Central European Standard Time"], "Europe/Warsaw")


class SSHActionTest(unittest.TestCase):
    """Commands the real printer gets for module actions."""
    def run_action(self, argv):
        p = install.SSHPrinter.__new__(install.SSHPrinter)
        sent = []
        p._run = lambda command, sudo=False, check=True: sent.append((command, sudo))
        p.action(argv)
        return sent

    def test_lock_makes_the_folder_first(self):  # fresh 02.04 has no /home/qidi/download (14.11.2026)
        self.assertEqual(self.run_action(["chattr", "+i", "/home/qidi/download"]),
                         [("mkdir -p /home/qidi/download && chattr +i /home/qidi/download", True)])

    def test_other_actions_unchanged(self):
        self.assertEqual(self.run_action(["systemctl", "disable", "--now", "frpc.service"]),
                         [("systemctl disable --now frpc.service", True)])

    def needs_for(self, reply):
        p = install.SSHPrinter.__new__(install.SSHPrinter)
        p._run = lambda command, sudo=False, check=True: reply.encode()
        return p.needs(["systemctl", "disable", "--now", "usbdevice.service"])

    def test_disable_skipped_when_service_missing(self):  # e.g. no ADB service on this printer
        self.assertFalse(self.needs_for("missing\ninactive\n"))

    def test_disable_needed_when_enabled(self):
        self.assertTrue(self.needs_for("present\nenabled\nactive\n"))

    def test_disable_skipped_when_already_off(self):
        self.assertFalse(self.needs_for("present\ndisabled\ninactive\n"))

if __name__ == "__main__":
    unittest.main(verbosity=2)
