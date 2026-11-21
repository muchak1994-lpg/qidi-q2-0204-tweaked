#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""Phone notifications: time left up to 50 % = the slicer's estimate minus the print time (like the printer screen).

The helper q2_notify_eta.py asks Moonraker for the print file's estimated_time; the sender script turns the token
@@ETA:<elapsed>:<fallback>@@ into text. Run:  python tests/test_notify_eta.py   (the sender part needs sh: skipped on Windows)
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
FILES = ROOT / "modules" / "phone-notifications" / "files"
ETA = FILES / "q2_notify_eta.py"
SEND = FILES / "q2_notify_send.sh"


def serve(filename, estimated, **meta):
    """A stand-in Moonraker: print_stats says which file is printing, metadata gives its estimate."""
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/printer/objects/query":
                body = {"result": {"status": {"print_stats": {"filename": filename}}}}
            elif u.path == "/server/files/metadata" and parse_qs(u.query).get("filename") == [filename]:
                body = {"result": dict(estimated_time=estimated, **meta)}
            else:
                self.send_response(404)
                self.end_headers()
                return
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, "http://127.0.0.1:%d" % srv.server_address[1]


def run_eta(elapsed, url, *flags):
    r = subprocess.run([sys.executable, "-I", str(ETA), *flags, str(elapsed)], capture_output=True, text=True, timeout=30,
                       env=dict(os.environ, Q2_MOONRAKER=url))
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


class EtaHelperTests(unittest.TestCase):
    def test_estimate_minus_elapsed(self):
        srv, url = serve("hdd500-12mm_PLA_1h1m.gcode.3mf", 3644)
        self.addCleanup(srv.shutdown)
        self.assertEqual(run_eta(900, url), "2744")

    def test_name_with_space_and_polish_letters_and_folder(self):
        name = "dir/Wieża 12mm (v2).gcode.3mf"
        srv, url = serve(name, 7200)
        self.addCleanup(srv.shutdown)
        self.assertEqual(run_eta(3600, url), "3600")

    def test_never_negative(self):
        srv, url = serve("a.gcode", 600)
        self.addCleanup(srv.shutdown)
        self.assertEqual(run_eta(900, url), "0")

    def test_no_estimate_prints_nothing(self):
        for est in (0, None):
            srv, url = serve("a.gcode", est)
            self.addCleanup(srv.shutdown)
            self.assertEqual(run_eta(100, url), "")

    def test_weight_is_the_slicer_weight_in_proportion_to_the_filament_used(self):
        srv, url = serve("a.gcode", 3644, filament_total=7960.0, filament_weight_total=23.18)
        self.addCleanup(srv.shutdown)
        self.assertEqual(run_eta(7960, url, "--weight"), "23")          # all of it, whole grams
        self.assertEqual(run_eta(3980, url, "--weight"), "12")          # half of it (11.6)
        self.assertEqual(run_eta(9000, url, "--weight"), "23")          # purge lines: never more than the slicer's weight

    def test_weight_prints_nothing_without_the_slicer_numbers(self):
        for meta in ({}, {"filament_total": 0, "filament_weight_total": 5.0}, {"filament_total": 7960.0}):
            srv, url = serve("a.gcode", 3644, **meta)
            self.addCleanup(srv.shutdown)
            self.assertEqual(run_eta(7960, url, "--weight"), "")

    def test_moonraker_unreachable_prints_nothing_and_exits_0(self):
        self.assertEqual(run_eta(100, "http://127.0.0.1:9"), "")


@unittest.skipIf(sys.platform == "win32", "shell script for the printer; run in WSL/Linux")
class EtaTokenTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.out = self.dir / "curl.jsonl"
        (self.dir / "curl.py").write_text("import json,os,sys\nopen(os.environ['OUT'],'a').write(json.dumps(sys.argv[1:])+'\\n')\n")
        (self.dir / "eta.sh").write_text("#!/bin/sh\n[ -n \"$FAKE_ETA\" ] && echo \"$FAKE_ETA\"\nexit 0\n")
        (self.dir / "q2.conf").write_text("ENABLED=1\nNTFY_SERVER=https://n.example\nEVENTS_TOPIC=e\nCMD_TOPIC=c\n")

    def tearDown(self):
        self.tmp.cleanup()

    def message(self, text, **env):
        e = dict(os.environ, Q2_NOTIFY_CONF=str(self.dir / "q2.conf"), Q2_NOTIFY_CURL="python3 %s" % (self.dir / "curl.py"),
                 OUT=str(self.out), Q2_NOTIFY_ETA="sh %s" % (self.dir / "eta.sh"), TZ="UTC", Q2_NOTIFY_NOW="1000000000", **env)
        r = subprocess.run(["sh", str(SEND), "Print 25%", text], env=e, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        call = json.loads(self.out.read_text().splitlines()[-1])
        return json.loads(call[call.index("-d") + 1])["message"]

    def test_slicer_estimate_is_used(self):
        # 3644 s estimate, 900 s printed -> 2744 s = 45 min left, finishing 01:46:40 + 45:44 = 02:32
        self.assertEqual(self.message("elapsed 15 min, @@ETA:900:5400@@", FAKE_ETA="2744"),
                         "elapsed 15 min, 45 min left, done at 02:32")

    def test_over_an_hour(self):
        self.assertEqual(self.message("x @@ETA:900:60@@", FAKE_ETA="11100"), "x 3h 05m left, done at 04:51")

    def test_fallback_when_there_is_no_estimate(self):
        self.assertEqual(self.message("x @@ETA:900:1800@@"), "x 30 min left, done at 02:16")

    def test_filament_token_becomes_grams(self):
        self.assertEqual(self.message("done, filament @@FIL:7960@@", FAKE_ETA="23"), "done, filament 23 g")

    def test_filament_token_falls_back_to_metres(self):
        self.assertEqual(self.message("done, filament @@FIL:12345@@"), "done, filament 12.3 m")
        self.assertEqual(self.message("done, filament @@FIL:800@@"), "done, filament 0.8 m")

    def test_two_different_tokens_in_one_message_both_expand(self):
        self.assertEqual(self.message("x @@FIL:5@@ @@ETA:1:2@@ y", FAKE_ETA="9"), "x 9 g 0 min left, done at 01:46 y")

    def test_zero_left_is_shown_as_0_min(self):
        self.assertEqual(self.message("x @@ETA:900:1800@@", FAKE_ETA="0"), "x 0 min left, done at 01:46")


if __name__ == "__main__":
    unittest.main()
