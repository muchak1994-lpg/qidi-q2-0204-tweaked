#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic)
"""Printer screen touch: presses the printer's touch screen when the Fluidd 'Printer screen' window is clicked.

OPTIONAL and separate from the look-only picture service. Listens on 127.0.0.1 only (nginx shows it as /webcam3/).
One POST /?action=tap with JSON {"x": 0..1, "y": 0..1} (the place in the picture) writes one short touch (press and
release) to the Goodix touch panel, exactly like a finger. The event sequence is the one proved on 06.11.2026.
One POST /?action=swipe with {"x1","y1","x2","y2","ms"} drags from one place to another (scrolling lists on the screen):
the same press and release, with the position moved in steps in between (the moving part is not proven on the real panel).
Standard library only.

The service itself is OFF until the Fluidd window "arms" it (POST /?action=arm, valid ARM_SECONDS, the window renews it
while its Touch button is on; POST /?action=disarm turns it off). Every POST must carry the header X-Q2-Touch: 1: a page of
another site cannot send a custom header without a CORS preflight, and this service never answers one.
"""
import json
import math
import os
import signal
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
MIN_GAP_SECONDS = 0.25                 # taps closer together than this are refused (a swipe counts as a tap here)
SWIPE_STEPS = 10                       # a drag is played back in this many steps
SWIPE_MIN_SECONDS, SWIPE_MAX_SECONDS = 0.15, 0.8   # the drag takes as long as the user's, held between these
MAX_BODY = 200
ARM_SECONDS = 60                       # one arming lasts this long; the window renews it every ~20 s while touch is on
HEADER = "X-Q2-Touch"
EV = struct.Struct("llHHi")            # struct input_event on 64 bit Linux

last_tap = [0.0]
armed_until = [0.0]                      # off after every start
now = time.monotonic


def to_touch(fx, fy):
    """Place in the picture (0..1 each) -> touch panel numbers. ValueError when it is not a number from 0 to 1."""
    for v in (fx, fy):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 or v > 1:
            raise ValueError("position outside the picture")
    px = min(int(fx * SCREEN_W + 0.5), SCREEN_W - 1)
    py = min(int(fy * SCREEN_H + 0.5), SCREEN_H - 1)
    return min(int(px * SCALE_X), TOUCH_MAX_X), min(int(py * SCALE_Y), TOUCH_MAX_Y)


EV_SYN, EV_KEY, EV_ABS = 0, 1, 3


def to_swipe(x1, y1, x2, y2, ms):
    """Two places in the picture (0..1 each) and the time of the drag in milliseconds -> (start, end, seconds) for the touch
    panel. ValueError for anything that is not a number (the places: 0 to 1). The time is held between SWIPE_MIN_SECONDS and
    SWIPE_MAX_SECONDS."""
    if isinstance(ms, bool) or not isinstance(ms, (int, float)) or not math.isfinite(ms):
        raise ValueError("bad time")
    seconds = min(max(ms / 1000.0, SWIPE_MIN_SECONDS), SWIPE_MAX_SECONDS)
    return to_touch(x1, y1), to_touch(x2, y2), seconds


def _events(f, items):
    for t, c, v in items:
        s = time.time()
        f.write(EV.pack(int(s), int((s % 1) * 1e6), t, c, v))


def _press(x, y):
    return ((EV_ABS, 0x2f, 0), (EV_ABS, 0x39, 4242), (EV_ABS, 0x35, x), (EV_ABS, 0x36, y), (EV_ABS, 0x30, 10),
            (EV_KEY, 0x14a, 1), (EV_ABS, 0, x), (EV_ABS, 1, y), (EV_SYN, 0, 0))


_RELEASE = ((EV_ABS, 0x2f, 0), (EV_ABS, 0x39, -1), (EV_KEY, 0x14a, 0), (EV_SYN, 0, 0))


def write_tap(f, x, y, sleep=time.sleep):
    """One touch (press, short wait, release) as input events - the sequence of the 06.11.2026 test.

    The release is sent whatever happens in between (a failed write, the wait cut short by SIGTERM/Ctrl-C), so the
    panel is never left "pressed"."""
    try:
        _events(f, _press(x, y))
        sleep(PRESS_SECONDS)
    finally:
        _events(f, _RELEASE)


def write_swipe(f, start, end, seconds, steps=SWIPE_STEPS, sleep=time.sleep):
    """A drag: press at start, move to end in even steps over `seconds` (the finger moves, the screen's list scrolls), release.
    The press and the release are the tap's; the moves update the same position numbers. Not proven on the real panel yet
    (only the tap was: 06.11.2026). The release is sent whatever happens in between, like the tap's."""
    (x1, y1), (x2, y2) = start, end
    try:
        _events(f, _press(x1, y1))
        for i in range(1, steps + 1):
            sleep(seconds / steps)
            x, y = x1 + (x2 - x1) * i // steps, y1 + (y2 - y1) * i // steps
            _events(f, ((EV_ABS, 0x35, x), (EV_ABS, 0x36, y), (EV_ABS, 0, x), (EV_ABS, 1, y), (EV_SYN, 0, 0)))
    finally:
        _events(f, _RELEASE)


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


def inject_swipe(start, end, seconds):
    path = find_device()
    if not path:
        raise OSError("touch panel not found")
    with open(path, "wb", buffering=0) as f:
        write_swipe(f, start, end, seconds)


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
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self.reply(400, "bad length")
        body = self.rfile.read(min(max(length, 0), 65536))   # always read what was sent, so the answer is not lost
        action = {"/?action=tap": "tap", "/?action=swipe": "swipe", "/?action=arm": "arm",
                  "/?action=disarm": "disarm"}.get(self.path)
        if action is None:
            return self.reply(404)
        # A page from another site may not use this. (Origin cannot be compared with Host here: Fluidd's web
        # server passes its own upstream name as Host. Browsers send Sec-Fetch-Site on their own - on plain http they
        # often do not, so its absence is allowed.) The custom header makes any cross-site request need a CORS
        # preflight, which this service never allows; the arming below keeps a stray request from touching the screen.
        site = self.headers.get("Sec-Fetch-Site")
        if site and site != "same-origin":
            return self.reply(403, "another site")
        if self.headers.get(HEADER) != "1":
            return self.reply(403, "header missing")
        if (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
            return self.reply(415, "JSON only")
        if length > MAX_BODY:
            return self.reply(413, "too big")
        if action == "arm":
            armed_until[0] = now() + ARM_SECONDS
            return self.reply(200, "ok")
        if action == "disarm":
            armed_until[0] = 0.0
            return self.reply(200, "ok")
        t = now()
        if t >= armed_until[0]:
            return self.reply(403, "touch is off")
        try:
            data = json.loads(body)
            if action == "swipe":
                swipe = to_swipe(data["x1"], data["y1"], data["x2"], data["y2"], data["ms"])
            else:
                x, y = to_touch(data["x"], data["y"])
        except (ValueError, KeyError, TypeError):
            return self.reply(400, "bad position")
        if t - last_tap[0] < MIN_GAP_SECONDS:
            return self.reply(429, "too fast")
        last_tap[0] = t
        try:
            if action == "swipe":
                inject_swipe(*swipe)
            else:
                inject(x, y)
        except OSError as e:
            return self.reply(503, str(e))
        self.reply(200, "ok")

    def log_message(self, *args):
        pass


def on_term(signum, frame):
    """SIGTERM (systemctl stop) -> SystemExit, so that a tap in progress still sends its release."""
    raise SystemExit(0)


def main():
    signal.signal(signal.SIGTERM, on_term)
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    sys.exit(main())
