#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Q2 tweaked - phone notifications: seconds left of the running print, from the slicer's estimate.
#
#   q2_notify_eta.py <print time so far in seconds>
#
# Prints (estimated_time of the print file from Moonraker) - (print time so far), never below 0 - the same number the
# printer screen shows up to 50 % progress. Prints nothing when there is no estimate or Moonraker does not answer;
# the caller then uses its own extrapolation. Never fails and never waits long (3 s per request).
import json
import os
import sys
import urllib.parse
import urllib.request

BASE = os.environ.get("Q2_MOONRAKER", "http://127.0.0.1:7125")


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=3) as r:
        return json.load(r)["result"]


def main():
    try:
        elapsed = int(float(sys.argv[1]))
        name = get("/printer/objects/query?print_stats")["status"]["print_stats"]["filename"]
        est = get("/server/files/metadata?filename=" + urllib.parse.quote(name))["estimated_time"]
        if name and est and float(est) > 0:
            print(max(0, int(float(est)) - elapsed))
    except Exception:
        pass


main()
