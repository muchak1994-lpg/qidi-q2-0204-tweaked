#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Q2 tweaked - phone notifications: seconds left of the running print, from the slicer's estimate.
#
#   q2_notify_eta.py <print time so far in seconds>
#   q2_notify_eta.py --weight <filament used so far in mm>
#
# Time left: prints (estimated_time of the print file from Moonraker) - (print time so far), never below 0 - the same number the
# printer screen shows up to 50 % progress. Prints nothing when there is no estimate or Moonraker does not answer;
# the caller then uses its own extrapolation.
# Weight: prints the whole grams of filament used = the slicer's weight of the print file (filament_weight_total) in
# proportion to the length used (filament_total), never more than the slicer's weight (purge lines); nothing without those
# numbers. Never fails and never waits long (3 s per request).
import json
import os
import sys
import urllib.parse
import urllib.request

BASE = os.environ.get("Q2_MOONRAKER", "http://127.0.0.1:7125")


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=3) as r:
        return json.load(r)["result"]


def metadata():
    name = get("/printer/objects/query?print_stats")["status"]["print_stats"]["filename"]
    return name, get("/server/files/metadata?filename=" + urllib.parse.quote(name))


def main():
    try:
        weight = sys.argv[1] == "--weight"
        value = float(sys.argv[-1])
        name, meta = metadata()
        if weight:
            total, grams = float(meta["filament_total"]), float(meta["filament_weight_total"])
            if name and total > 0 and grams > 0:
                print("%d" % round(grams * min(value / total, 1.0)))
        elif name and meta["estimated_time"] and float(meta["estimated_time"]) > 0:
            print(max(0, int(float(meta["estimated_time"])) - int(value)))
    except Exception:
        pass


main()
