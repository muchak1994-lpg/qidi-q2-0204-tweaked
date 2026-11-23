#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""Phone notifications: the timelapse message with links to the video (sh), run against a stand-in sender script.

The video itself is not uploaded: the public ntfy.sh refuses a video of a few MB (413, 23.11.2026). The message carries buttons that
open the file from the printer's own web server, one per address the printer has (home network, Tailscale).

Skipped on Windows (the script is for the printer's sh); run it in WSL/Linux:  python3 tests/test_notify_video.py
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIDEO = ROOT / "modules" / "phone-notifications" / "files" / "q2_notify_video.sh"

# Stand-in for q2_notify_send.sh: logs its arguments; a message that says "rendering" makes the video appear
# (FAKE_APPEAR_AFTER_RENDERING = the file to create), like the timelapse render finishing a moment later.
FAKE_SEND = """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
late = os.environ.get("FAKE_APPEAR_AFTER_RENDERING")
if late and "rendering" in sys.argv[1].lower() + sys.argv[2].lower():
    open(late, "wb").write(b"mp4")
"""

HOME, TAIL = "192.168.10.119", "100.73.132.37"
PATH = "/server/files/timelapse/"


def views(call):
    return [call[i + 1] for i, a in enumerate(call) if a == "--view"]


def labels(call):
    return [v.split("=")[0] for v in views(call)]


@unittest.skipIf(sys.platform == "win32", "shell script for the printer; run in WSL/Linux")
class VideoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.tl = self.dir / "timelapse"
        self.tl.mkdir()
        self.log = self.dir / "log.jsonl"
        (self.dir / "send.py").write_text(FAKE_SEND)

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, name, size=3):
        p = self.tl / name
        p.write_bytes(b"x" * size)
        return p

    def run_video(self, name, timeout=1, addrs="%s %s" % (HOME, TAIL), **extra):
        env = dict(os.environ, Q2_NOTIFY_SEND="python3 %s" % (self.dir / "send.py"), Q2_TIMELAPSE_DIR=str(self.tl),
                   Q2_VIDEO_POLL="1", Q2_VIDEO_TIMEOUT=str(timeout), FAKE_LOG=str(self.log), **extra)
        if addrs is not None:                                        # None = let the script ask its two commands
            env["Q2_NOTIFY_ADDRS"] = addrs
        r = subprocess.run(["sh", str(VIDEO), name], env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return [json.loads(l) for l in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_ready_video_gives_one_link_button_per_network_and_no_upload(self):
        self.make("timelapse_hdd500.gcode.3mf_20261120_1010.mp4")
        (call,) = self.run_video("hdd500.gcode.3mf")
        self.assertEqual(call[0], "Timelapse")
        self.assertIn("hdd500.gcode.3mf", call[1])
        f = "timelapse_hdd500.gcode.3mf_20261120_1010.mp4"
        self.assertEqual(views(call), ["Home network=http://%s%s%s" % (HOME, PATH, f), "Tailscale=http://%s%s%s" % (TAIL, PATH, f)])
        self.assertNotIn("--attach", call)

    def test_picks_newest_matching_file_and_ignores_other_prints(self):
        self.make("timelapse_a.gcode_20261119_1256.mp4")
        self.make("timelapse_a.gcode_20261120_0900.mp4")
        self.make("timelapse_a.gcode_b_20261121_0900.mp4")           # another print whose name starts the same
        self.make("timelapse_a.gcode_20261121_0900.jpg")             # a picture, not the video
        (call,) = self.run_video("a.gcode")
        self.assertTrue(views(call))
        self.assertTrue(all(v.endswith("timelapse_a.gcode_20261120_0900.mp4") for v in views(call)), views(call))

    def test_name_with_space_polish_letters_and_brackets_is_percent_encoded(self):
        self.make("timelapse_Wieża 12mm (v2).gcode.3mf_20261120_1010.mp4")
        (call,) = self.run_video("Wieża 12mm (v2).gcode.3mf")
        self.assertEqual(views(call)[0], "Home network=http://%s%stimelapse_Wie%%C5%%BCa%%2012mm%%20%%28v2%%29.gcode.3mf_20261120_1010.mp4"
                         % (HOME, PATH))

    def test_only_the_networks_a_phone_can_use_get_a_button(self):
        self.make("timelapse_a.gcode_20261120_1010.mp4")
        (call,) = self.run_video("a.gcode", addrs="127.0.0.1 169.254.3.4 8.8.8.8 172.17.0.1 %s %s" % (HOME, TAIL))
        self.assertEqual(labels(call), ["Home network", "Tailscale"])
        self.assertFalse([v for v in views(call) if "8.8.8.8" in v or "127.0.0.1" in v or "169.254" in v])

    def test_the_tailscale_address_is_asked_from_tailscale_when_the_interface_list_lacks_it(self):
        # 23.11.2026, the real printer: Tailscale runs without its own network interface, so `ip addr` shows only the Wi-Fi address
        # and the Tailscale address comes from `tailscale ip -4`
        self.make("timelapse_a.gcode_20261120_1010.mp4")
        env = dict(Q2_NOTIFY_IPCMD="echo 127.0.0.1; echo %s" % HOME, Q2_NOTIFY_TSCMD="echo %s" % TAIL)
        (call,) = self.run_video("a.gcode", addrs=None, **env)
        self.assertEqual(labels(call), ["Home network", "Tailscale"])

    def test_a_missing_or_failing_tailscale_command_only_drops_that_button(self):
        self.make("timelapse_a.gcode_20261120_1010.mp4")
        env = dict(Q2_NOTIFY_IPCMD="echo %s" % HOME, Q2_NOTIFY_TSCMD="exit 3")
        (call,) = self.run_video("a.gcode", addrs=None, **env)
        self.assertEqual(labels(call), ["Home network"])

    def test_without_tailscale_there_is_only_the_home_button(self):
        self.make("timelapse_a.gcode_20261120_1010.mp4")
        (call,) = self.run_video("a.gcode", addrs=HOME)
        self.assertEqual(labels(call), ["Home network"])

    def test_at_most_three_buttons_and_tailscale_always_among_them(self):
        self.make("timelapse_a.gcode_20261120_1010.mp4")
        (call,) = self.run_video("a.gcode", addrs="192.168.1.2 10.0.0.2 192.168.2.2 %s" % TAIL)
        self.assertLessEqual(len(views(call)), 3)
        self.assertIn("Tailscale", labels(call))

    def test_no_address_at_all_says_where_the_video_is(self):
        self.make("timelapse_a.gcode_20261120_1010.mp4")
        (call,) = self.run_video("a.gcode", addrs="127.0.0.1")
        self.assertEqual(views(call), [])
        self.assertIn("Fluidd", call[1])

    def test_the_message_names_the_fallback_in_fluidd_and_holds_no_address(self):
        self.make("timelapse_a.gcode_20261120_1010.mp4")
        (call,) = self.run_video("a.gcode")
        self.assertIn("Fluidd", call[1])
        self.assertNotIn(HOME, call[1])
        self.assertNotIn(TAIL, call[1])

    def test_waits_then_sends_when_file_appears(self):
        target = self.tl / "timelapse_a.gcode_20261120_1010.mp4"
        calls = self.run_video("a.gcode", timeout=10, FAKE_APPEAR_AFTER_RENDERING=str(target))
        self.assertEqual(len(calls), 2)
        self.assertIn("rendering", calls[0][1].lower())
        self.assertTrue(views(calls[1]))

    def test_timeout_sends_not_ready(self):
        calls = self.run_video("a.gcode", timeout=1)
        self.assertEqual(len(calls), 2)
        self.assertIn("rendering", calls[0][1].lower())
        self.assertIn("not ready", calls[1][1].lower())
        self.assertEqual(views(calls[1]), [])


if __name__ == "__main__":
    unittest.main()
