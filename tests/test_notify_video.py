#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""Phone notifications: sending the timelapse video (sh), run against a stand-in sender script.

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

    def run_video(self, name, timeout=1, **extra):
        env = dict(os.environ, Q2_NOTIFY_SEND="python3 %s" % (self.dir / "send.py"), Q2_TIMELAPSE_DIR=str(self.tl),
                   Q2_VIDEO_POLL="1", Q2_VIDEO_TIMEOUT=str(timeout), FAKE_LOG=str(self.log), **extra)
        r = subprocess.run(["sh", str(VIDEO), name], env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return [json.loads(l) for l in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_ready_video_is_attached(self):
        mp4 = self.make("timelapse_hdd500.gcode.3mf_20261120_1010.mp4")
        (call,) = self.run_video("hdd500.gcode.3mf")
        self.assertEqual(call[0], "Timelapse")
        self.assertIn("hdd500.gcode.3mf", call[1])
        self.assertEqual(call[call.index("--attach") + 1], str(mp4))

    def test_picks_newest_matching_file_and_ignores_other_prints(self):
        self.make("timelapse_a.gcode_20261119_1256.mp4")
        new = self.make("timelapse_a.gcode_20261120_0900.mp4")
        self.make("timelapse_a.gcode_b_20261121_0900.mp4")           # another print whose name starts the same
        self.make("timelapse_a.gcode_20261121_0900.jpg")             # a picture, not the video
        (call,) = self.run_video("a.gcode")
        self.assertEqual(call[call.index("--attach") + 1], str(new))

    def test_name_with_space_and_polish_letters(self):
        mp4 = self.make("timelapse_Wieża 12mm (v2).gcode.3mf_20261120_1010.mp4")
        (call,) = self.run_video("Wieża 12mm (v2).gcode.3mf")
        self.assertEqual(call[call.index("--attach") + 1], str(mp4))

    def test_waits_then_sends_when_file_appears(self):
        target = self.tl / "timelapse_a.gcode_20261120_1010.mp4"
        calls = self.run_video("a.gcode", timeout=10, FAKE_APPEAR_AFTER_RENDERING=str(target))
        self.assertEqual(len(calls), 2)
        self.assertIn("rendering", calls[0][1].lower())
        self.assertEqual(calls[1][calls[1].index("--attach") + 1], str(target))

    def test_timeout_sends_not_ready(self):
        calls = self.run_video("a.gcode", timeout=1)
        self.assertEqual(len(calls), 2)
        self.assertIn("rendering", calls[0][1].lower())
        self.assertIn("not ready", calls[1][1].lower())
        self.assertNotIn("--attach", calls[1])

    def test_too_large_video_is_not_uploaded(self):
        self.make("timelapse_a.gcode_20261120_1010.mp4", size=50)
        (call,) = self.run_video("a.gcode", Q2_VIDEO_MAX_BYTES="10")
        self.assertNotIn("--attach", call)
        self.assertIn("too large", call[1].lower())


if __name__ == "__main__":
    unittest.main()
