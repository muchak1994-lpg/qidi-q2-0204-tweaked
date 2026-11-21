#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""send-and-print-guard: finds the Upload & Print bug in Fluidd's active bundle by its code, not by checksums.

Broken code found once -> repaired; already repaired -> nothing; anything else (unknown code, two matches, printer busy,
Moonraker silent) -> nothing is changed and the run still ends OK. Skipped on Windows (script for the printer).
Run in WSL/Linux:  python3 tests/test_send_print_guard.py
"""
import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

GUARD = Path(__file__).resolve().parent.parent / "modules" / "send-and-print-guard" / "files" / "fix-fluidd-upload-print.sh"

BROKEN = ('this.$store.getters["files/getCanPrint"]("gcodes",t)'
          '&&(this.FileSystemSelectLineDialogState={open:!0,filename:t})}}saveConfigAndRestart')
FIXED = ('this.$store.getters["files/getCanPrint"]("gcodes",t)'
         '&&(this.FileSystemSelectLineDialogState={open:!0,filename:t})}'
         'else this.uploadFile(e,"","gcodes",!0)}saveConfigAndRestart')


def bundle(core):
    return ("var a=1;function x(){return 2}" + core + "(){this.reload()};export{a as b};").encode()


def status(**over):
    s = {"webhooks": {"state": "ready"}, "print_stats": {"state": "standby"}, "pause_resume": {"is_paused": False},
         "virtual_sdcard": {"is_active": False}, "motion_report": {"live_velocity": 0.0, "live_extruder_velocity": 0.0},
         "heaters": {"available_heaters": ["heater_bed", "extruder"]},
         "heater_bed": {"target": 0.0}, "extruder": {"target": 0.0}}
    for k, v in over.items():
        s[k] = v
    return s


def serve(st):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            keys = [k for k, _ in parse_qsl(urlparse(self.path).query, keep_blank_values=True)]
            if not keys:                    # the query string is "webhooks&print_stats&..." (keys without values)
                keys = urlparse(self.path).query.split("&")
            body = json.dumps({"result": {"status": {k: st[k] for k in keys if k in st}}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, "http://127.0.0.1:%d" % srv.server_address[1]


@unittest.skipIf(sys.platform == "win32", "script for the printer; run in WSL/Linux")
class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "fluidd"
        (self.root / "assets").mkdir(parents=True)
        (self.root / "index.html").write_text('<script type="module" src="./assets/index-ABC123.js"></script>')
        self.js = self.root / "assets" / "index-ABC123.js"

    def tearDown(self):
        self.tmp.cleanup()

    def run_guard(self, st=None, url=None):
        srv = None
        if url is None:
            srv, url = serve(st or status())
            self.addCleanup(lambda: (srv.shutdown(), srv.server_close()))
        r = subprocess.run(["sh", str(GUARD)], capture_output=True, text=True, timeout=60,
                           env=dict(os.environ, Q2_FLUIDD_ROOT=str(self.root), Q2_MOONRAKER=url))
        return r

    def test_broken_code_is_repaired_whatever_the_rest_of_the_file_is(self):
        self.js.write_bytes(bundle(BROKEN))
        self.js.chmod(0o640)
        r = self.run_guard()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("fixed", r.stdout.lower())
        self.assertEqual(self.js.read_bytes(), bundle(FIXED))
        self.assertEqual(stat.S_IMODE(self.js.stat().st_mode), 0o640)
        self.assertEqual([p.name for p in (self.root / "assets").iterdir()], ["index-ABC123.js"])   # no temp file left

    def test_already_fixed_is_left_alone(self):
        self.js.write_bytes(bundle(FIXED))
        r = self.run_guard()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Already fixed", r.stdout)
        self.assertEqual(self.js.read_bytes(), bundle(FIXED))

    def test_unknown_code_is_left_alone_and_the_run_is_ok(self):
        self.js.write_bytes(bundle("function other(){return 3}"))
        r = self.run_guard()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("nothing changed", r.stdout.lower())
        self.assertEqual(self.js.read_bytes(), bundle("function other(){return 3}"))

    def test_two_matches_are_not_touched(self):
        self.js.write_bytes(bundle(BROKEN + BROKEN))
        r = self.run_guard()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.js.read_bytes(), bundle(BROKEN + BROKEN))

    def test_no_single_active_bundle_changes_nothing(self):
        (self.root / "index.html").write_text("<html>no script</html>")
        self.js.write_bytes(bundle(BROKEN))
        r = self.run_guard()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.js.read_bytes(), bundle(BROKEN))

    def test_busy_printer_defers_the_repair(self):
        busy = {
            "printing": status(print_stats={"state": "printing"}),
            "paused": status(pause_resume={"is_paused": True}),
            "sdcard active": status(virtual_sdcard={"is_active": True}),
            "not ready": status(webhooks={"state": "shutdown"}),
            "moving": status(motion_report={"live_velocity": 5.0, "live_extruder_velocity": 0.0}),
            "heating": status(heater_bed={"target": 60.0}),
        }
        for name, st in busy.items():
            with self.subTest(name):
                self.js.write_bytes(bundle(BROKEN))
                r = self.run_guard(st)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn("deferred", r.stdout.lower())
                self.assertEqual(self.js.read_bytes(), bundle(BROKEN))

    def test_moonraker_silent_defers_the_repair(self):
        self.js.write_bytes(bundle(BROKEN))
        r = self.run_guard(url="http://127.0.0.1:9")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.js.read_bytes(), bundle(BROKEN))

    def test_a_symlinked_bundle_is_not_touched(self):
        real = self.root / "real.js"
        real.write_bytes(bundle(BROKEN))
        self.js.symlink_to(real)
        r = self.run_guard()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(real.read_bytes(), bundle(BROKEN))

    def test_the_script_has_no_checksum_lists(self):
        text = GUARD.read_text()
        self.assertNotIn("APPROVED_CLIENTS", text)
        self.assertNotIn("ALREADY_FIXED", text)
        self.assertNotIn("hashlib", text)
        self.assertLess(len(text), 8000)


if __name__ == "__main__":
    unittest.main()
