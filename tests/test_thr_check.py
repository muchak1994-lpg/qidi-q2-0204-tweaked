#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""thr-accel-check: the Klipper extra (pretend toolhead, synthetic firmware) and the installer's end step.

Run:  python tests/test_thr_check.py
"""
import hashlib
import importlib.util
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import install  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "q2_thr_check", REPO / "modules" / "thr-accel-check" / "files" / "q2_thr_check.py")
thr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(thr)

sha = lambda b: hashlib.sha256(b).hexdigest()
BOOT = bytes(range(256)) * 128                       # 32 KiB
APP = (b"\x12\x34\x56\x78" * 3000)[:11000]           # ends inside a page
BOOT_SHA, APP_SHA = sha(BOOT), sha(APP)


class Error(Exception):
    pass


def printer(rate, state="standby", save_dir=None, app=APP, read_ok=True):
    flash = bytearray(b"\xff" * 0x20000)
    flash[:len(BOOT)] = BOOT
    flash[0x8000:0x8000 + len(app)] = app
    calls = []

    class Query:
        def send(self, data):
            order, addr = data
            calls.append(addr)
            if not read_ok:
                raise Error("Unknown command: debug_read")
            if addr == thr.FLASH_SIZE_REG:
                return {"val": 128}
            return {"val": struct.unpack_from("<I", flash, addr - thr.FLASH)[0]}

    class Mcu:
        def lookup_query_command(self, *a):
            return Query()

        def get_status(self):
            return {"mcu_version": "02.02.01.08"}

    class Client:
        def finish_measurements(self):
            pass

        def get_samples(self):
            return [(i / rate, 0., 0., 0.) for i in range(int(2 * rate))]

    objs = {
        "mcu THR": Mcu(),
        "lis2dw": type("Chip", (), {"start_internal_client": lambda s: Client()})(),
        "toolhead": type("T", (), {"dwell": lambda s, t: None})(),
        "print_stats": type("PS", (), {"get_status": lambda s, e: {"state": state}})(),
        "gcode": type("G", (), {"register_command": lambda s, *a, **k: None})(),
    }

    class Printer:
        def lookup_object(self, name, default=None):
            return objs.get(name, default)

        def get_reactor(self):
            return type("R", (), {"monotonic": lambda s: 0.})()

    class Config:
        def get_printer(self):
            return Printer()

        def get(self, key, default):
            return save_dir if key == "save_dir" and save_dir else default

    return thr.Q2ThrCheck(Config()), calls


class Gcmd:
    def __init__(self, save=0):
        self.save, self.out = save, []

    def get_int(self, name, default, **kw):
        return self.save

    def respond_info(self, msg):
        self.out.append(msg)

    def error(self, msg):
        return Error(msg)


class ExtraTest(unittest.TestCase):
    def setUp(self):
        self.saved = dict(thr.KNOWN_BOOT), dict(thr.KNOWN_APP)
        thr.KNOWN_BOOT.clear()
        thr.KNOWN_APP.clear()
        thr.KNOWN_BOOT[BOOT_SHA] = "test bootloader"
        thr.KNOWN_APP[APP_SHA] = (len(APP), "test firmware", "stock")

    def tearDown(self):
        for live, old in zip((thr.KNOWN_BOOT, thr.KNOWN_APP), self.saved):
            live.clear()
            live.update(old)

    def test_bug_known_combination(self):
        check, calls = printer(387.)
        g = Gcmd()
        check.cmd_TWEAKED_THR_CHECK(g)
        r = check.last
        self.assertEqual((r["state"], r["bootloader_sha256"], r["application_sha256"]), ("bug", BOOT_SHA, APP_SHA))
        self.assertEqual(r["application_bytes"], len(APP))
        self.assertIn("manual, optional fix exists", "\n".join(r["lines"]))
        self.assertNotIn("saved", r)
        # reads stop at the first erased page after the firmware (11000 bytes -> 6 pages of 2 KiB)
        self.assertEqual(max(a for a in calls if a < thr.FLASH_SIZE_REG), thr.APP_START + 6 * thr.PAGE + thr.PAGE - 4)

    def test_ok_rate(self):
        check, _ = printer(1602.)
        check.cmd_TWEAKED_THR_CHECK(Gcmd())
        self.assertEqual(check.last["state"], "ok")
        self.assertEqual(check.last["rate_hz"], 1602.0)

    def test_unknown_firmware_no_flash_advice(self):
        check, _ = printer(390., app=b"\x01\x02\x03\x04" * 900)
        check.cmd_TWEAKED_THR_CHECK(Gcmd())
        r = check.last
        self.assertEqual(r["application_state"], "unknown")
        self.assertIn("do not flash", "\n".join(r["lines"]))

    def test_save(self):
        d = tempfile.mkdtemp()
        check, _ = printer(387., save_dir=d)
        check.cmd_TWEAKED_THR_CHECK(Gcmd(save=1))
        folder = Path(check.last["saved"])
        self.assertEqual(folder.parent, Path(d))
        self.assertEqual((folder / "bootloader.bin").read_bytes(), BOOT)
        self.assertEqual((folder / "application.bin").read_bytes(), APP)
        self.assertEqual(json.loads((folder / "report.json").read_text())["application_sha256"], APP_SHA)

    def test_refused_while_printing(self):
        check, calls = printer(387., state="printing")
        with self.assertRaises(Error):
            check.cmd_TWEAKED_THR_CHECK(Gcmd())
        self.assertEqual(calls, [])

    def test_read_failure_reported(self):
        check, _ = printer(387., read_ok=False)
        check.cmd_TWEAKED_THR_CHECK(Gcmd())
        self.assertTrue(check.last["done"])
        self.assertIn("could not be read", "\n".join(check.last["lines"]))

    def test_real_tables(self):
        self.tearDown()
        self.assertIn("31f8344db7b091df5429960bc9cd06065e2188c3b8092e43fb65eb3f2833723c", thr.KNOWN_BOOT)
        for digest, (size, _, state) in thr.KNOWN_APP.items():
            self.assertEqual(len(digest), 64)
            self.assertIn(state, ("stock", "fixed"))
        self.setUp()


class FakePrinter:
    def __init__(self, result, loaded=True):
        self.result, self.loaded = result, loaded
        self.files = {}
        self.removed, self.scripts = [], []
        if result.get("saved"):
            for name in install.THR_FILES:
                self.files[result["saved"] + "/" + name] = name.encode()

    def http_json(self, url):
        if url == "/printer/info":
            return {"result": {"state": "ready"}}
        if url == "/printer/objects/list":
            return {"result": {"objects": ["toolhead"] + (["q2_thr_check"] if self.loaded else [])}}
        return {"result": {"status": {"q2_thr_check": self.result, "print_stats": {"state": "standby"},
                                      "extruder": {"target": 0}, "heater_bed": {"target": 0}}}}

    def gcode(self, script):
        self.scripts.append(script)

    def read(self, path):
        return self.files.get(path)

    def remove_tree(self, path):
        self.removed.append(path)


class InstallerStepTest(unittest.TestCase):
    RESULT = {"done": True, "lines": ["Accelerometer: 387 samples/s"], "bootloader_sha256": "31f8344d" + "0" * 56,
              "application_sha256": "1d34b4b0" + "0" * 56, "saved": install.THR_SAVE_DIR + "/31f8344d-1d34b4b0"}

    def test_backup_copied_and_removed(self):
        backups = Path(tempfile.mkdtemp())
        p = FakePrinter(dict(self.RESULT))
        install.toolhead_check(p, backups, sleep=lambda s: None)
        target = backups / "toolhead-31f8344d-1d34b4b0"
        self.assertEqual((target / "bootloader.bin").read_bytes(), b"bootloader.bin")
        self.assertEqual(p.scripts, ["TWEAKED_THR_CHECK SAVE=1"])
        self.assertEqual(p.removed, [self.RESULT["saved"]])
        # second run: the same backup is already on the PC, the printer copy is still removed
        p2 = FakePrinter(dict(self.RESULT))
        install.toolhead_check(p2, backups, sleep=lambda s: None)
        self.assertEqual(p2.removed, [self.RESULT["saved"]])

    def offer(self, answer, mode="ask", state="bug"):
        import contextlib
        import io
        backups = Path(tempfile.mkdtemp())
        p = FakePrinter(dict(self.RESULT, state=state))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            install.toolhead_offer(p, mode, read=lambda prompt: answer, backups=backups)
        return p, out.getvalue(), backups

    def test_offer_says_what_the_bug_is_and_recommends(self):
        p, text, _ = self.offer("")
        self.assertIn("390 samples", text)
        self.assertEqual(p.scripts, ["TWEAKED_THR_CHECK SAVE=1"])

    def test_offer_n_does_nothing(self):
        p, text, _ = self.offer("n")
        self.assertEqual((p.scripts, p.removed), ([], []))
        self.assertIn("TWEAKED_THR_CHECK", text)

    def test_offer_mode_no_is_silent_and_yes_does_not_ask(self):
        p, text, _ = self.offer("n", mode="no")
        self.assertEqual((p.scripts, text), ([], ""))
        p, _, _ = self.offer("n", mode="yes")
        self.assertEqual(p.scripts, ["TWEAKED_THR_CHECK SAVE=1"])

    def test_skipped_when_not_loaded(self):
        p = FakePrinter(dict(self.RESULT), loaded=False)
        self.assertIsNone(install.toolhead_check(p, Path(tempfile.mkdtemp()), sleep=lambda s: None))
        self.assertEqual(p.scripts, [])

    def test_remove_tree_guard(self):
        sp = install.SSHPrinter.__new__(install.SSHPrinter)
        for bad in ("/home/qidi", "/home/qidi/printer_data/config", install.THR_SAVE_DIR + "/../x"):
            with self.assertRaises(install.InstallError):
                sp.remove_tree(bad)


if __name__ == "__main__":
    unittest.main()
