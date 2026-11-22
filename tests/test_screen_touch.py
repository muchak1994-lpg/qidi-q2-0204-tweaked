#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic)
"""printer-screen-touch: coordinates, the touch events, what the service accepts and refuses, the module file."""
import io
import json
import struct
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOD = ROOT / "modules" / "printer-screen-touch"
sys.path.insert(0, str(MOD / "files"))
import q2_touch  # noqa: E402

EV = struct.Struct("llHHi")


def decode(data):
    return [EV.unpack_from(data, i)[2:] for i in range(0, len(data), EV.size)]


class CoordinateTests(unittest.TestCase):
    def test_picture_position_to_touch_point(self):
        # 06.11.2026 test (owner watched): touch point 160,200 pressed "Cancel", which sits at pixel 160,200 of the
        # 480x272 screen picture -> the touch panel's numbers are screen pixels (1:1), although it reports 0-799 x 0-479
        self.assertEqual(q2_touch.to_touch(160 / 480, 200 / 272), (160, 200))

    def test_corners_stay_inside(self):
        self.assertEqual(q2_touch.to_touch(0, 0), (0, 0))
        self.assertEqual(q2_touch.to_touch(1, 1), (479, 271))

    def test_scale_can_be_changed(self):          # if a later test shows another factor, only these numbers change
        old = q2_touch.SCALE_X, q2_touch.SCALE_Y
        q2_touch.SCALE_X, q2_touch.SCALE_Y = 800 / 480, 480 / 272
        try:
            self.assertEqual(q2_touch.to_touch(1, 1), (798, 478))      # last pixel, inside the panel range
            self.assertEqual(q2_touch.to_touch(0.5, 0.5), (400, 240))
        finally:
            q2_touch.SCALE_X, q2_touch.SCALE_Y = old

    def test_bad_numbers_refused(self):
        for bad in (-0.1, 1.1, float("nan"), float("inf"), "0.5", None, True):
            with self.assertRaises(ValueError):
                q2_touch.to_touch(bad, 0.5)


class EventTests(unittest.TestCase):
    def test_tap_events_like_the_proven_script(self):
        out, waits = io.BytesIO(), []
        q2_touch.write_tap(out, 160, 200, sleep=waits.append)
        evs = decode(out.getvalue())
        EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
        self.assertEqual(evs[:8], [(EV_ABS, 0x2f, 0), (EV_ABS, 0x39, 4242), (EV_ABS, 0x35, 160), (EV_ABS, 0x36, 200),
                                   (EV_ABS, 0x30, 10), (EV_KEY, 0x14a, 1), (EV_ABS, 0, 160), (EV_ABS, 1, 200)])
        self.assertEqual(evs[8], (EV_SYN, 0, 0))
        self.assertEqual(evs[9:], [(EV_ABS, 0x2f, 0), (EV_ABS, 0x39, -1), (EV_KEY, 0x14a, 0), (EV_SYN, 0, 0)])
        self.assertEqual(waits, [q2_touch.PRESS_SECONDS])


class DeviceTests(unittest.TestCase):
    def test_finds_the_goodix_panel_only(self):
        with tempfile.TemporaryDirectory() as d:
            for n, name in (("event0", "icspring camera"), ("event1", "Goodix Capacitive TouchScreen")):
                (Path(d) / n / "device").mkdir(parents=True)
                (Path(d) / n / "device" / "name").write_text(name + "\n")
            self.assertEqual(q2_touch.find_device(d, "/dev/input").replace("\\", "/"), "/dev/input/event1")
            (Path(d) / "event1" / "device" / "name").write_text("something else\n")
            self.assertIsNone(q2_touch.find_device(d, "/dev/input"))


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.taps, self.clock = [], [100.0]
        self.orig = (q2_touch.inject, q2_touch.now)
        q2_touch.inject = lambda x, y: self.taps.append((x, y))
        q2_touch.now = lambda: self.clock[0]
        q2_touch.last_tap[0] = 0.0
        self.server = HTTPServer(("127.0.0.1", 0), q2_touch.Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d/?action=tap" % self.server.server_port
        self.host = "127.0.0.1:%d" % self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        q2_touch.inject, q2_touch.now = self.orig

    def post(self, body, headers=None, url=None):
        h = {"Content-Type": "application/json"}
        h.update(headers or {})
        req = urllib.request.Request(url or self.url, data=body if isinstance(body, bytes) else json.dumps(body).encode(),
                                     headers=h, method="POST")
        try:
            with urllib.request.urlopen(req) as r:
                return r.status
        except urllib.error.HTTPError as e:
            e.close()
            return e.code

    def test_tap_is_injected(self):
        self.assertEqual(self.post({"x": 160 / 480, "y": 200 / 272}), 200)
        self.assertEqual(self.taps, [(160, 200)])

    def test_refusals(self):
        self.assertEqual(self.post({"x": 2, "y": 0.5}), 400)
        self.assertEqual(self.post(b"not json"), 400)
        self.assertEqual(self.post({"x": 0.5}), 400)
        self.assertEqual(self.post({"x": 0.5, "y": 0.5}, {"Content-Type": "text/plain"}), 415)   # a web page cannot send this quietly
        self.assertEqual(self.post({"x": 0.5, "y": 0.5}, {"Sec-Fetch-Site": "cross-site"}), 403)  # another site
        self.assertEqual(self.post({"x": 0.5, "y": 0.5}, url=self.url.replace("tap", "other")), 404)
        self.assertEqual(self.post(b"{" + b" " * 1000 + b"}"), 413)
        self.assertEqual(self.taps, [])

    def test_same_origin_is_fine(self):
        # behind Fluidd's web server Host is not the browser's address (22.11.2026: a Host check refused every real tap)
        self.assertEqual(self.post({"x": 0.5, "y": 0.5}, {"Origin": "http://100.73.132.37", "Host": "mjpgstreamer3",
                                                          "Sec-Fetch-Site": "same-origin"}), 200)

    def test_get_is_not_a_tap(self):
        with self.assertRaises(urllib.error.HTTPError) as c:
            urllib.request.urlopen(self.url)
        c.exception.close()
        self.assertEqual((c.exception.code, self.taps), (405, []))

    def test_taps_are_rate_limited(self):
        self.assertEqual(self.post({"x": 0.5, "y": 0.5}), 200)
        self.assertEqual(self.post({"x": 0.5, "y": 0.5}), 429)
        self.clock[0] += 1
        self.assertEqual(self.post({"x": 0.5, "y": 0.5}), 200)
        self.assertEqual(len(self.taps), 2)

    def test_no_panel_found(self):
        def none(x, y):
            raise OSError("no touch panel")
        q2_touch.inject = none
        self.assertEqual(self.post({"x": 0.5, "y": 0.5}), 503)


class ModuleTests(unittest.TestCase):
    def test_module_is_optional_and_local(self):
        m = json.loads((MOD / "module.json").read_text(encoding="utf-8"))
        self.assertEqual(m["id"], "printer-screen-touch")
        self.assertIs(m["default"], False)
        for dest, f in m["files"].items():
            if "source" in f:
                self.assertTrue((MOD / f["source"]).is_file(), dest)
        self.assertIn('("127.0.0.1", PORT)', (MOD / "files" / "q2_touch.py").read_text(encoding="utf-8"))

    def test_view_module_stays_look_only(self):
        view = ROOT / "modules" / "printer-screen-view" / "files"
        self.assertNotIn("/dev/input", (view / "q2_screen.py").read_text(encoding="utf-8"))

    def test_window_starts_with_touch_off(self):
        js = (MOD / "files" / "q2-screen-touch.js").read_text(encoding="utf-8")
        self.assertIn("var enabled = false", js)              # every time the window opens, touch is off
        self.assertIn("/webcam3/?action=tap", js)
        self.assertIn("q2-screen-open", (ROOT / "modules" / "printer-screen-view" / "files" / "q2-screen-view.js"
                                         ).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
