#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""Phone notifications: the sender script (sh + curl), run against a stand-in curl.

Skipped on Windows (the script is for the printer's sh); run it in WSL/Linux:  python3 tests/test_notify_send.py
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEND = ROOT / "modules" / "phone-notifications" / "files" / "q2_notify_send.sh"

FAKE_CURL = """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["FAKE_CURL_OUT"], "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
if "-o" in sys.argv and not os.environ.get("FAKE_CURL_NO_DOWNLOAD"):
    with open(sys.argv[sys.argv.index("-o") + 1], "wb") as f:
        f.write(b"jpg")
"""


@unittest.skipIf(sys.platform == "win32", "shell script for the printer; run in WSL/Linux")
class SendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.out = self.dir / "curl_calls.jsonl"
        self.fake = self.dir / "fake_curl.py"
        self.fake.write_text(FAKE_CURL)
        self.conf = self.dir / "q2_notify.conf"
        self.write_conf("ENABLED=1\nNTFY_SERVER=https://ntfy.example\nEVENTS_TOPIC=evtopic\nCMD_TOPIC=cmdtopic\n")

    def tearDown(self):
        self.tmp.cleanup()

    def write_conf(self, text):
        self.conf.write_text(text)

    def run_send(self, *args, **extra_env):
        env = dict(os.environ, Q2_NOTIFY_CONF=str(self.conf), Q2_NOTIFY_CURL="python3 %s" % self.fake,
                   FAKE_CURL_OUT=str(self.out), Q2_NOTIFY_TMP=str(self.dir), **extra_env)
        r = subprocess.run(["sh", str(SEND), *args], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return [json.loads(l) for l in self.out.read_text().splitlines()] if self.out.exists() else []

    @staticmethod
    def body(call):
        return json.loads(call[call.index("-d") + 1])

    def test_publishes_json_to_server_root(self):
        (call,) = self.run_send("Print started", "hdd500 started", "--prio", "3", "--tags", "printer,rocket")
        self.assertEqual(call[-1], "https://ntfy.example")
        b = self.body(call)
        self.assertEqual((b["topic"], b["title"], b["message"], b["priority"]), ("evtopic", "Print started", "hdd500 started", 3))
        self.assertEqual(b["tags"], ["printer", "rocket"])

    def test_action_buttons(self):
        (call,) = self.run_send("Paused", "filament runout", "--action", "Resume=resume", "--action", "Cancel=cancel")
        acts = self.body(call)["actions"]
        self.assertEqual([a["label"] for a in acts], ["Resume", "Cancel"])
        self.assertEqual([a["body"] for a in acts], ["resume", "cancel"])
        for a in acts:
            self.assertEqual((a["action"], a["method"], a["url"], a["clear"]),
                             ("http", "POST", "https://ntfy.example/cmdtopic", True))

    def test_attach_uses_put_with_filename(self):
        pic = self.dir / "snap.jpg"
        pic.write_bytes(b"jpg")
        (call,) = self.run_send("Paused", "look", "--attach", str(pic))
        self.assertIn("-T", call)
        self.assertEqual(call[call.index("-T") + 1], str(pic))
        self.assertEqual(call[-1], "https://ntfy.example/evtopic")
        self.assertIn("Filename: snap.jpg", call)
        self.assertIn("Title: Paused", call)
        self.assertIn("Message: look", call)

    def test_attach_non_ascii_title_is_rfc2047_encoded(self):
        pic = self.dir / "snap.jpg"
        pic.write_bytes(b"jpg")
        (call,) = self.run_send("Wieża gotowa", "ok", "--attach", str(pic))
        titles = [a for a in call if a.startswith("Title: ")]
        self.assertEqual(len(titles), 1)
        self.assertTrue(titles[0].startswith("Title: =?UTF-8?B?"), titles[0])
        self.assertTrue(titles[0].isascii())

    def test_title_with_quotes_pipe_and_unicode_is_passed_intact(self):
        name = 'Wieża 12mm "v2" | a\\b.gcode.3mf'
        (call,) = self.run_send("Print finished", name)
        self.assertEqual(self.body(call)["message"], name)

    def test_multiline_message(self):
        (call,) = self.run_send("T", "line one\nline two")
        self.assertEqual(self.body(call)["message"], "line one\nline two")

    def test_tsv_mode_matches_positional_mode(self):
        pos = self.run_send("Print paused: manual", "hdd 500|x", "--prio", "4", "--tags", "pause",
                            "--click", "http://p/x", "--action", "Resume=resume")
        self.out.unlink()
        tsv = self.run_send("--tsv", "\t".join(["Print paused: manual", "hdd 500|x", "4", "pause", "http://p/x", "", "Resume=resume"]))
        self.assertEqual(self.body(pos[0]), self.body(tsv[0]))

    def test_attach_url_is_downloaded_then_uploaded_and_removed(self):
        dl, up = self.run_send("Paused", "look", "--attach", "http://127.0.0.1/webcam/?action=snapshot")
        self.assertEqual(dl[dl.index("-o") + 1].rsplit("/", 1)[0], str(self.dir))
        self.assertEqual(dl[-1], "http://127.0.0.1/webcam/?action=snapshot")
        self.assertEqual(dl[dl.index("--max-time") + 1], "8")
        self.assertEqual(up[up.index("-T") + 1], dl[dl.index("-o") + 1])
        self.assertEqual(up[-1], "https://ntfy.example/evtopic")
        self.assertEqual(list(self.dir.glob("q2_notify_snap*")), [])

    def test_failed_download_still_sends_the_message_without_picture(self):
        calls = self.run_send("Paused", "look", "--attach", "http://127.0.0.1/webcam/?action=snapshot",
                              FAKE_CURL_NO_DOWNLOAD="1")
        self.assertEqual(len(calls), 2)
        self.assertNotIn("-T", calls[1])
        self.assertEqual(self.body(calls[1])["title"], "Paused")

    def test_clock_token_becomes_the_finish_time(self):
        (call,) = self.run_send("Print 50%", "left 30 min, done at @@+1836@@", TZ="UTC", Q2_NOTIFY_NOW="1000000000")
        self.assertEqual(self.body(call)["message"], "left 30 min, done at 02:17")   # 01:46:40 + 30:36

    def test_disabled_or_missing_conf_sends_nothing(self):
        self.write_conf("ENABLED=0\nNTFY_SERVER=https://ntfy.example\nEVENTS_TOPIC=e\nCMD_TOPIC=c\n")
        self.assertEqual(self.run_send("T", "m"), [])
        self.conf.unlink()
        self.assertEqual(self.run_send("T", "m"), [])

    def test_curl_has_max_time(self):
        (call,) = self.run_send("T", "m")
        self.assertEqual(call[call.index("--max-time") + 1], "15")


if __name__ == "__main__":
    unittest.main()
