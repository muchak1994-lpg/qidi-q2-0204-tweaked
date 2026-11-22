#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic)
"""Printer screen view: serves what the printer's own touch screen shows (/dev/fb0) as one PNG picture.

Look only: no touch, nothing is ever written to the screen. Listens on 127.0.0.1 only; nginx shows it as
/webcam4/?action=snapshot, Fluidd shows that as a camera card. Standard library only (the printer has little free RAM).
"""
import struct
import sys
import time
import zlib
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

FB = "/dev/fb0"
SYS = "/sys/class/graphics/fb0/"
PORT = 8083
CACHE_SECONDS = 0.4          # many viewers or a fast refresh read the screen at most ~2.5 times a second

_cache = {"time": 0.0, "png": b""}


def chunk(kind, data):
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def bgra_to_png(raw, width, height, stride):
    """PNG (RGB) of a 32 bit B,G,R,A frame buffer with `stride` bytes per row."""
    rows = []
    for y in range(height):
        row = raw[y * stride:y * stride + width * 4]
        rgb = bytearray(width * 3)
        rgb[0::3] = row[2::4]
        rgb[1::3] = row[1::4]
        rgb[2::3] = row[0::4]
        rows.append(b"\x00" + bytes(rgb))            # filter type 0 (none)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 1)) + chunk(b"IEND", b""))


def read_int(name):
    with open(SYS + name) as f:
        return int(f.read().replace(",", " ").split()[0])


def screen_png():
    now = time.monotonic()
    if _cache["png"] and now - _cache["time"] < CACHE_SECONDS:
        return _cache["png"]
    with open(SYS + "virtual_size") as f:
        width, height = [int(v) for v in f.read().strip().split(",")]
    if read_int("bits_per_pixel") != 32:
        raise RuntimeError("the screen is not 32 bit")
    stride = read_int("stride")
    with open(FB, "rb") as f:
        raw = f.read(stride * height)
    if len(raw) < stride * height:
        raise RuntimeError("short read from the screen")
    _cache["png"], _cache["time"] = bgra_to_png(raw, width, height, stride), now
    return _cache["png"]


class Handler(BaseHTTPRequestHandler):
    timeout = 10
    server_version = "q2-screen"

    def do_GET(self):
        url = urlparse(self.path)
        if parse_qs(url.query).get("action") != ["snapshot"]:
            self.send_error(404)
            return
        try:
            png = screen_png()
        except (OSError, RuntimeError, ValueError) as e:
            self.send_error(503, str(e))
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(png)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(png)

    def log_message(self, *args):                     # no log lines: the card asks every second
        pass


def main():
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    sys.exit(main())
