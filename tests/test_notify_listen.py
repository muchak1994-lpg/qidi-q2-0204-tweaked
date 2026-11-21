#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""Phone notifications: the command listener (sh + curl), run against a stand-in curl and a stand-in video script.

Skipped on Windows (the script is for the printer's sh); run it in WSL/Linux:  python3 tests/test_notify_listen.py
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LISTEN = ROOT / "modules" / "phone-notifications" / "files" / "q2_notify_listen.sh"

# Stand-in curl: the channel stream prints the lines of FAKE_STREAM on the first connection only (later ones are
# empty, so the listener's reconnect can be counted); Moonraker answers with the state in FAKE_STATE; a resume or
# cancel POST is logged and, for resume, changes the state to "printing" like the real printer would.
FAKE_CURL = r"""#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]
url = a[-1]
log = os.environ["FAKE_LOG"]
def note(**kw):
    with open(log, "a") as f:
        f.write(json.dumps(kw) + "\n")
if url.endswith("/raw"):
    n = int(open(log + ".conn").read()) if os.path.exists(log + ".conn") else 0
    open(log + ".conn", "w").write(str(n + 1))
    note(stream=url)
    if n == 0:
        sys.stdout.write(open(os.environ["FAKE_STREAM"]).read())
elif "/printer/objects/query" in url:
    print(json.dumps({"result": {"status": {"print_stats": {"filename": os.environ.get("FAKE_FILE", "hdd500.gcode"), "state": open(os.environ["FAKE_STATE"]).read().strip()}}}}))
elif "/printer/print/" in url:
    note(post=url.rsplit("/", 1)[1])
    if url.endswith("/resume"):
        open(os.environ["FAKE_STATE"], "w").write("printing")
"""

FAKE_SEND = """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(json.dumps({"send": sys.argv[1:]}) + "\\n")
"""

FAKE_VIDEO = """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(json.dumps({"video": sys.argv[1:]}) + "\\n")
"""


@unittest.skipIf(sys.platform == "win32", "shell script for the printer; run in WSL/Linux")
class ListenTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.log = self.dir / "log.jsonl"
        (self.dir / "curl.py").write_text(FAKE_CURL)
        (self.dir / "video.py").write_text(FAKE_VIDEO)
        (self.dir / "send.py").write_text(FAKE_SEND)
        self.conf = self.dir / "q2_notify.conf"
        self.conf.write_text("ENABLED=1\nNTFY_SERVER=https://ntfy.example\nEVENTS_TOPIC=ev\nCMD_TOPIC=cmd\n")

    def tearDown(self):
        self.tmp.cleanup()

    extra_env = {}

    def listen(self, lines, state="paused", loops=1):
        (self.dir / "stream").write_text("".join(l + "\n" for l in lines))
        (self.dir / "state").write_text(state)
        env = dict(os.environ, Q2_NOTIFY_CONF=str(self.conf), Q2_NOTIFY_CURL="python3 %s" % (self.dir / "curl.py"),
                   Q2_NOTIFY_VIDEO="python3 %s" % (self.dir / "video.py"), Q2_NOTIFY_RETRY="0",
                   Q2_NOTIFY_SEND="python3 %s" % (self.dir / "send.py"), **self.extra_env,
                   Q2_NOTIFY_LOOPS=str(loops), FAKE_LOG=str(self.log), FAKE_STREAM=str(self.dir / "stream"),
                   FAKE_STATE=str(self.dir / "state"))
        r = subprocess.run(["sh", str(LISTEN)], env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        import time
        time.sleep(0.3)                                  # the video script is started in the background
        return [json.loads(l) for l in self.log.read_text().splitlines()] if self.log.exists() else []

    @staticmethod
    def posts(calls):
        return [c["post"] for c in calls if "post" in c]

    @staticmethod
    def videos(calls):
        return [c["video"] for c in calls if "video" in c]

    def test_resume_only_when_paused(self):
        self.assertEqual(self.posts(self.listen(["resume"], state="paused")), ["resume"])
        self.log.unlink()
        self.assertEqual(self.posts(self.listen(["resume"], state="printing")), [])

    def test_cancel_only_when_paused(self):
        self.assertEqual(self.posts(self.listen(["cancel"], state="paused")), ["cancel"])
        self.log.unlink()
        self.assertEqual(self.posts(self.listen(["cancel"], state="printing")), [])

    def test_resume_twice_second_is_noop(self):
        self.assertEqual(self.posts(self.listen(["resume", "resume"], state="paused")), ["resume"])

    def test_unknown_and_malformed_lines_ignored(self):
        calls = self.listen(["", "reboot", "RESUME", "resume now", "resume;reboot", '{"title":"x"}', "cancel all",
                             "  ", "videos", "video"], state="paused")
        self.assertEqual(self.posts(calls), [])
        self.assertEqual(self.videos(calls), [])

    def test_video_rejects_path_tricks(self):
        bad = ["video ../../etc/passwd", "video /x", "video a.mp4;reboot", "video $(id)", "video `id`",
               "video a|b", "video a&b", "video -rf", "video .hidden", 'video a"b', "video a'b", "video a\\b"]
        self.assertEqual(self.videos(self.listen(bad, state="printing")), [])

    def test_video_passes_a_plain_name_as_one_argument(self):
        calls = self.listen(["video hdd500.gcode", "video Wieża 12mm (v2).gcode.3mf"], state="complete")
        self.assertEqual(self.videos(calls), [["hdd500.gcode"], ["Wieża 12mm (v2).gcode.3mf"]])

    @staticmethod
    def sends(calls):
        return [c["send"] for c in calls if "send" in c]

    def test_photo_sends_the_camera_picture_in_any_state(self):
        for state in ("printing", "paused", "standby"):
            with self.subTest(state):
                for f in (self.log, Path(str(self.log) + ".conn")):
                    if f.exists():
                        f.unlink()
                (call,) = self.sends(self.listen(["photo"], state=state))
                self.assertEqual(call[0], "Camera")
                self.assertIn("hdd500.gcode", call[1])
                self.assertEqual(call[call.index("--attach") + 1], "http://127.0.0.1/webcam/?action=snapshot")
                self.assertEqual(self.posts([]), [])

    def test_photo_without_a_print_file_says_so(self):
        self.extra_env = {"FAKE_FILE": ""}
        (call,) = self.sends(self.listen(["photo"], state="standby"))
        self.assertIn("no print", call[1].lower())

    def test_photo_with_a_special_file_name_is_one_argument(self):
        self.extra_env = {"FAKE_FILE": "a b;$(id) 'c'.gcode"}
        (call,) = self.sends(self.listen(["photo"], state="printing"))
        self.assertIn("a b;$(id) 'c'.gcode", call[1])

    def test_photo_with_extra_words_is_ignored(self):
        self.assertEqual(self.sends(self.listen(["photo now", "photos", "PHOTO"], state="printing")), [])

    def test_reconnects_after_stream_ends(self):
        calls = self.listen([], loops=3)
        self.assertEqual(len([c for c in calls if "stream" in c]), 3)
        self.assertEqual([c["stream"] for c in calls if "stream" in c][0], "https://ntfy.example/cmd/raw")

    def test_disabled_does_nothing(self):
        self.conf.write_text("ENABLED=0\nNTFY_SERVER=https://ntfy.example\nEVENTS_TOPIC=ev\nCMD_TOPIC=cmd\n")
        self.assertEqual(self.listen(["resume"]), [])


if __name__ == "__main__":
    unittest.main()
