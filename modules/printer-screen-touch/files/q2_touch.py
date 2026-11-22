#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic)
"""Printer screen touch: presses the printer's touch screen when the Fluidd 'Printer screen' window is clicked.

OPTIONAL and separate from the look-only picture service. Listens on 127.0.0.1 only (nginx shows it as /webcam3/).
One POST /?action=tap with JSON {"x": 0..1, "y": 0..1} (the place in the picture) writes one short touch (press and
release) to the Goodix touch panel, exactly like a finger. The event sequence is the one proved on 06.11.2026.
Standard library only.
"""
import json
import math
import os
import struct
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 8082
SCREEN_W, SCREEN_H = 480, 272          # the picture of the screen
TOUCH_MAX_X, TOUCH_MAX_Y = 799, 479    # what the Goodix panel reports as its range
# Touch numbers per screen pixel. 1:1 because on 06.11.2026 the touch point 160,200 pressed "Cancel", which is at
# pixel 160,200 of the 480x272 picture (scaling by 800/480 would have missed it). One test, so only these two numbers
# are to be changed if another factor is found.
SCALE_X, SCALE_Y = 1.0, 1.0
PRESS_SECONDS = 0.12
MIN_GAP_SECONDS = 0.25                 # taps closer together than this are refused
MAX_BODY = 200
EV = struct.Struct("llHHi")            # struct input_event on 64 bit Linux

last_tap = [0.0]
now = time.monotonic


def to_touch(fx, fy):
    """Place in the picture (0..1 each) -> touch panel numbers. ValueError when it is not a number from 0 to 1."""
    for v in (fx, fy):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 or v > 1:
            raise ValueError("position outside the picture")
    px = min(int(fx * SCREEN_W + 0.5), SCREEN_W - 1)
    py = min(int(fy * SCREEN_H + 0.5), SCREEN_H - 1)
    return min(int(px * SCALE_X), TOUCH_MAX_X), min(int(py * SCALE_Y), TOUCH_MAX_Y)


def write_tap(f, x, y, sleep=time.sleep):
    """One touch (press, short wait, release) as input events - the sequence of the 06.11.2026 test."""
    EV_SYN, EV_KEY, EV_ABS = 0, 1, 3

    def ev(t, c, v):
        s = time.time()
        f.write(EV.pack(int(s), int((s % 1) * 1e6), t, c, v))
    for t, c, v in ((EV_ABS, 0x2f, 0), (EV_ABS, 0x39, 4242), (EV_ABS, 0x35, x), (EV_ABS, 0x36, y), (EV_ABS, 0x30, 10),
                    (EV_KEY, 0x14a, 1), (EV_ABS, 0, x), (EV_ABS, 1, y), (EV_SYN, 0, 0)):
        ev(t, c, v)
    sleep(PRESS_SECONDS)
    for t, c, v in ((EV_ABS, 0x2f, 0), (EV_ABS, 0x39, -1), (EV_KEY, 0x14a, 0), (EV_SYN, 0, 0)):
        ev(t, c, v)


def find_device(sys_root="/sys/class/input", dev_root="/dev/input"):
    """The event file of the Goodix touch panel (looked up by name, not by number), or None."""
    try:
        names = sorted(os.listdir(sys_root))
    except OSError:
        return None
    for n in names:
        if not n.startswith("event"):
            continue
        try:
            with open(os.path.join(sys_root, n, "device", "name")) as f:
                if "goodix" in f.read().lower():
                    return os.path.join(dev_root, n)
        except OSError:
            continue
    return None


def inject(x, y):
    path = find_device()
    if not path:
        raise OSError("touch panel not found")
    with open(path, "wb", buffering=0) as f:
        write_tap(f, x, y)


class Handler(BaseHTTPRequestHandler):
    timeout = 10
    server_version = "q2-touch"

    def reply(self, code, text=""):
        body = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.reply(405, "taps are sent with POST")

    def do_POST(self):
        if self.path != "/?action=tap":
            return self.reply(404)
        origin = self.headers.get("Origin")
        if origin and origin.split("://", 1)[-1] != self.headers.get("Host"):
            return self.reply(403, "another site")              # a page from elsewhere may not press the screen
        if (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
            return self.reply(415, "JSON only")
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self.reply(400, "bad length")
        if length < 1 or length > MAX_BODY:
            return self.reply(413 if length > MAX_BODY else 400, "bad size")
        try:
            data = json.loads(self.rfile.read(length))
            x, y = to_touch(data["x"], data["y"])
        except (ValueError, KeyError, TypeError):
            return self.reply(400, "bad position")
        t = now()
        if t - last_tap[0] < MIN_GAP_SECONDS:
            return self.reply(429, "too fast")
        last_tap[0] = t
        try:
            inject(x, y)
        except OSError as e:
            return self.reply(503, str(e))
        self.reply(200, "ok %d,%d" % (x, y))

    def log_message(self, *args):
        pass


def main():
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    sys.exit(main())
