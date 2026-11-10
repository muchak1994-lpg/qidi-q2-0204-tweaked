#!/usr/bin/env python3
"""Install / uninstall against a pretend printer (no network, no QIDI files).

Run:  python tests/test_install.py
"""
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

    def restart(self, name):
        self.restarts.append(name)

    def needs(self, argv):
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
        self.saved = (firmware.load_index, firmware.extract)
        firmware.load_index = lambda: {"files": {p: {"sha256": sha(d)} for p, d in STOCK.items()}}
        firmware.extract = lambda p: STOCK[p]
        self.built = build.build(MODS, stock_reader=lambda p: STOCK[p])
        # the owner's printer.cfg: LF line ends and a calibration block after SAVE_CONFIG
        mine = dict(STOCK)
        mine["/home/qidi/printer_data/config/printer.cfg"] = b"[idle_timeout]\ntimeout: 43200\n\n[x]\n#*# mesh = 1\n"
        self.p = FakePrinter(mine)
        self.p.files["/root/uuid"] = [b"abc\n", "root", "root", "644"]

    def tearDown(self):
        firmware.load_index, firmware.extract = self.saved
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

    def test_ethernet_mac_matches_qidi_script(self):
        data = install.ethernet_mac_file(self.p)
        digest = hashlib.md5(b"abc\n").hexdigest()
        self.assertIn(("MACAddress=02:%s:%s:%s:%s:%s" % tuple(digest[i:i + 2] for i in range(0, 10, 2))).encode(),
                      data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
