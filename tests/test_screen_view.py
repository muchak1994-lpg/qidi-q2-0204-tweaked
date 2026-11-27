#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic)
"""printer-screen-view: the PNG made from a frame buffer, the HTTP answers, the module file."""
import json
import struct
import sys
import threading
import unittest
import urllib.error
import urllib.request
import zlib
from http.server import HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOD = ROOT / "modules" / "printer-screen-view"
sys.path.insert(0, str(MOD / "files"))
import q2_screen  # noqa: E402


def decode(png):
    """Minimal PNG reader for what q2_screen writes: 8 bit RGB, filter 0. Returns (w, h, rows of bytes)."""
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    w = h = 0
    pos, idat = 8, b""
    while pos < len(png):
        n, kind = struct.unpack(">I4s", png[pos:pos + 8])
        data = png[pos + 8:pos + 8 + n]
        assert struct.unpack(">I", png[pos + 8 + n:pos + 12 + n])[0] == zlib.crc32(kind + data) & 0xFFFFFFFF
        if kind == b"IHDR":
            w, h, depth, ctype = struct.unpack(">IIBB", data[:10])
            assert (depth, ctype) == (8, 2)
        elif kind == b"IDAT":
            idat += data
        pos += 12 + n
    raw = zlib.decompress(idat)
    rows = [raw[y * (w * 3 + 1):(y + 1) * (w * 3 + 1)] for y in range(h)]
    assert all(r[0] == 0 for r in rows)
    return w, h, [r[1:] for r in rows]


class PngTests(unittest.TestCase):
    def test_colours_and_padding(self):
        # 2x2 picture, 12 bytes per row (4 bytes padding after the 8 of pixels), B,G,R,A
        row1 = bytes([1, 2, 3, 255, 10, 20, 30, 255]) + b"\xee" * 4
        row2 = bytes([4, 5, 6, 0, 40, 50, 60, 0]) + b"\xee" * 4
        w, h, rows = decode(q2_screen.bgra_to_png(row1 + row2, 2, 2, 12))
        self.assertEqual((w, h), (2, 2))
        self.assertEqual(rows[0], bytes([3, 2, 1, 30, 20, 10]))   # R,G,B
        self.assertEqual(rows[1], bytes([6, 5, 4, 60, 50, 40]))   # alpha is ignored

    def test_full_size_frame(self):
        raw = bytes([0x24, 0x24, 0x24, 255]) * (480 * 272)
        w, h, rows = decode(q2_screen.bgra_to_png(raw, 480, 272, 1920))
        self.assertEqual((w, h, len(rows)), (480, 272, 272))
        self.assertEqual(rows[100][:3], bytes([0x24] * 3))


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.frames = 0

        def fake_png():
            self.frames += 1
            if self.fail:
                raise OSError("no screen")
            return b"PNGDATA"
        self.fail = False
        self.orig = q2_screen.screen_png
        q2_screen.screen_png = fake_png
        self.server = HTTPServer(("127.0.0.1", 0), q2_screen.Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = "http://127.0.0.1:%d" % self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        q2_screen.screen_png = self.orig

    def test_snapshot(self):
        r = urllib.request.urlopen(self.base + "/?action=snapshot")
        self.assertEqual((r.status, r.headers["Content-Type"], r.read()), (200, "image/png", b"PNGDATA"))

    def test_other_paths_and_failures(self):
        for path, code in (("/", 404), ("/?action=stream", 404), ("/x", 404)):
            with self.assertRaises(urllib.error.HTTPError) as c:
                urllib.request.urlopen(self.base + path)
            self.assertEqual(c.exception.code, code)
        self.fail = True
        with self.assertRaises(urllib.error.HTTPError) as c:
            urllib.request.urlopen(self.base + "/?action=snapshot")
        self.assertEqual(c.exception.code, 503)


class ModuleTests(unittest.TestCase):
    def test_module_file(self):
        m = json.loads((MOD / "module.json").read_text(encoding="utf-8"))
        self.assertEqual(m["id"], "printer-screen-view")
        self.assertTrue(m.get("default", True))      # installed unless --skip
        self.assertFalse([a for a in m["actions"] if a[0] == "moonraker-db"])   # no camera entry: own window
        js = (MOD / "files" / "q2-screen-view.js").read_text(encoding="utf-8")
        self.assertIn("/webcam4/?action=snapshot", js)
        self.assertNotIn("/printer/gcode", js)                                # nothing is sent to the printer
        self.assertNotIn("POST", js)
        edit = m["files"]["/home/qidi/fluidd/index.html"]["edits"][0]
        self.assertIn("q2-screen-view.js", edit[1])
        drying = json.loads((ROOT / "modules" / "fluidd-drying-button" / "module.json").read_text(encoding="utf-8"))
        self.assertEqual(edit[0], drying["files"]["/home/qidi/fluidd/index.html"]["edits"][0][0])   # same anchor: both can be installed
        for dest, f in m["files"].items():
            if "source" in f:
                self.assertTrue((MOD / f["source"]).is_file(), dest)

    def test_service_is_local_and_look_only(self):
        text = (MOD / "files" / "q2_screen.py").read_text(encoding="utf-8")
        self.assertIn('("127.0.0.1", PORT)', text)
        self.assertNotIn("event0", text)             # no touch
        self.assertNotIn('"wb"', text)               # never writes to the screen


if __name__ == "__main__":
    unittest.main()
