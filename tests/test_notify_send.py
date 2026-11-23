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
if "-T" in sys.argv and os.environ.get("FAKE_CURL_FAIL_UPLOAD"):
    sys.exit(28)                      # curl: operation timed out
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

    def test_photo_button_keeps_the_message(self):
        call = self.run_send("Print 25%", "x", "--action", "Photo=photo", "--action", "Resume=resume")[-1]
        self.out.unlink()
        acts = self.body(call)["actions"]
        self.assertEqual([(a["body"], a["clear"]) for a in acts], [("photo", False), ("resume", True)])
        pic = self.dir / "snap.jpg"
        pic.write_bytes(b"jpg")
        call = self.run_send("Print 25%", "x", "--attach", str(pic), "--action", "Photo=photo", "--action", "Resume=resume")[-1]
        header = [a for a in call if a.startswith("Actions: ")][0]
        self.assertIn("body=photo, clear=false", header)
        self.assertIn("body=resume, clear=true", header)

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

    def eta_script(self, seconds):                    # stands in for q2_notify_eta.py: the same answer for every argument
        p = self.dir / "eta.sh"
        p.write_text("#!/bin/sh\necho %s\n" % seconds)
        return p

    def test_est_token_gives_the_whole_estimate_and_the_finish_time(self):
        # the macros pass a line break as the two characters \n; the sender turns it into a real one
        (call,) = self.run_send("--tsv", "\t".join(["Print started", "hdd500.gcode\\n@@EST:900@@", "3"]),
                                Q2_NOTIFY_ETA="sh %s" % self.eta_script("11100"), TZ="UTC", Q2_NOTIFY_NOW="1000000000")
        self.assertEqual(self.body(call)["message"], "hdd500.gcode\nestimated 3h 05m, done at 04:51")

    def test_est_token_without_an_estimate_leaves_no_empty_line(self):
        (call,) = self.run_send("--tsv", "\t".join(["Print started", "hdd500.gcode\\n100 layers\\n@@EST:900@@", "3"]), Q2_NOTIFY_ETA="true", TZ="UTC")
        self.assertEqual(self.body(call)["message"], "hdd500.gcode\n100 layers")

    # ---- the end of a print: the macro cannot tell finished from cancelled (QIDI wipes print_stats), Moonraker's history can ----
    END_MESSAGE = "hdd500.gcode\\nprinted in 5h 07m, filament @@FIL:28000@@||hdd500.gcode\\nstopped at layer 98/120 after 5h 07m"

    def end_script(self, line):                       # stands in for `q2_notify_eta.py --end`: status, grams, millimetres (tab separated)
        p = self.dir / "end.sh"
        p.write_text("#!/bin/sh\n" + ("" if line is None else "printf '%s\\n'\n" % line.replace("\t", "\\t")))
        return p

    def send_end(self, line, button="Show timelapse=video hdd500.gcode"):
        self.out.unlink(missing_ok=True)                # one call per check, also inside a subTest loop
        (call,) = self.run_send("--tsv", "\t".join(["@@END@@", self.END_MESSAGE, "3", "", "", "", button, "", ""]),
                                Q2_NOTIFY_ETA="sh %s" % self.end_script(line), TZ="UTC")
        return self.body(call)

    def test_end_completed_is_a_finished_message_with_the_grams_and_the_timelapse_button(self):
        b = self.send_end("completed\t83\t28597")
        self.assertEqual((b["title"], b["message"]), ("Print finished", "hdd500.gcode\nprinted in 5h 07m, filament 83 g"))
        self.assertEqual([a["label"] for a in b["actions"]], ["Show timelapse"])

    def test_end_completed_without_grams_gives_metres_from_the_history(self):
        b = self.send_end("completed\t\t28597")
        self.assertEqual(b["message"], "hdd500.gcode\nprinted in 5h 07m, filament 28.5 m")

    def test_end_completed_without_any_history_numbers_keeps_the_macros_filament_token(self):
        b = self.send_end("completed\t\t")
        self.assertEqual(b["message"], "hdd500.gcode\nprinted in 5h 07m, filament 28.0 m")      # 28000 mm, from the macro's memory

    def test_end_cancelled_is_a_cancelled_message_without_buttons(self):
        b = self.send_end("cancelled\t7\t2442")
        self.assertEqual((b["title"], b["message"]), ("Print cancelled", "hdd500.gcode\nstopped at layer 98/120 after 5h 07m"))
        self.assertNotIn("actions", b)

    def test_end_with_another_status_is_a_stopped_message(self):
        for status in ("error", "klippy_shutdown", "interrupted"):
            with self.subTest(status):
                b = self.send_end(status + "\t\t")
                self.assertEqual(b["title"], "Print stopped")
                self.assertEqual(b["message"], "hdd500.gcode\nstopped at layer 98/120 after 5h 07m")
                self.assertNotIn("actions", b)

    def test_end_without_an_answer_from_moonraker_says_only_that_it_ended(self):
        b = self.send_end(None)
        self.assertEqual((b["title"], b["message"]), ("Print ended", "hdd500.gcode\nstopped at layer 98/120 after 5h 07m"))
        self.assertNotIn("actions", b)

    def test_end_message_without_the_separator_is_sent_whole(self):
        (call,) = self.run_send("--tsv", "\t".join(["@@END@@", "hdd500.gcode\\nended", "3"]),
                                Q2_NOTIFY_ETA="sh %s" % self.end_script("completed\t83\t28597"), TZ="UTC")
        b = self.body(call)
        self.assertEqual((b["title"], b["message"]), ("Print finished", "hdd500.gcode\nended"))

    def test_disabled_or_missing_conf_sends_nothing(self):
        self.write_conf("ENABLED=0\nNTFY_SERVER=https://ntfy.example\nEVENTS_TOPIC=e\nCMD_TOPIC=c\n")
        self.assertEqual(self.run_send("T", "m"), [])
        self.conf.unlink()
        self.assertEqual(self.run_send("T", "m"), [])

    def test_a_big_upload_is_not_cut_off_after_one_minute(self):
        # 23.11.2026: the 6.4 MB timelapse video needs more than 60 s from the printer's Wi-Fi; the old limit stopped it silently
        vid = self.dir / "t.mp4"
        vid.write_bytes(b"x" * 1000)
        (call,) = self.run_send("Timelapse", "name", "--attach", str(vid))
        self.assertGreaterEqual(int(call[call.index("--max-time") + 1]), 600)
        self.assertIn("--speed-time", call)                          # a stalled upload still ends, after 30 s of nothing
        self.assertIn("--speed-limit", call)

    def test_a_refusal_from_the_server_counts_as_a_failed_upload(self):
        # 23.11.2026: ntfy.sh answers 413 ("attachment too large, or bandwidth limit reached") to a 3 MB file; without --fail curl
        # would end with 0 and the message would be taken for delivered
        vid = self.dir / "t.mp4"
        vid.write_bytes(b"x" * 1000)
        (call,) = self.run_send("Timelapse", "name", "--attach", str(vid))
        self.assertIn("--fail", call)

    def test_a_failed_upload_still_sends_a_text_that_says_so(self):
        vid = self.dir / "t.mp4"
        vid.write_bytes(b"x" * 1000)
        up, text = self.run_send("Timelapse", "my print", "--attach", str(vid), FAKE_CURL_FAIL_UPLOAD="1")
        self.assertIn("-T", up)
        self.assertNotIn("-T", text)
        b = self.body(text)
        self.assertEqual(b["title"], "Timelapse")
        self.assertIn("my print", b["message"])
        self.assertIn("could not be sent", b["message"])

    def test_a_successful_upload_sends_no_extra_text(self):
        vid = self.dir / "t.mp4"
        vid.write_bytes(b"x" * 1000)
        self.assertEqual(len(self.run_send("Timelapse", "my print", "--attach", str(vid))), 1)

    def test_curl_has_max_time(self):
        (call,) = self.run_send("T", "m")
        self.assertEqual(call[call.index("--max-time") + 1], "15")


if __name__ == "__main__":
    unittest.main()
