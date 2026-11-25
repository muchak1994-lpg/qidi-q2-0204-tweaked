#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""ai-fixes: the pre-print foreign-object check (M4050) does not judge the first seconds.

Why (22.11.2026, lab on real frames of an EMPTY plate): the printer switches the case light on when the print starts and the
check reads the camera at once; the first frame after the light comes on is badly exposed and was the only frame that gave a
false "foreign object" (0.57, threshold 0.5; the 14:46 alarm came from one frame 4 s after the start). So the results of the
first seconds are not judged: the counters are re-read as the new baseline, a positive counts only when it comes after that.
The test takes the method's source from the module's edit (the file QIDI's is never needed) and runs it with a pretend
camera service, clock and printer.
"""
import json
import logging
import time as real_time
import types
import unittest
from enum import Enum
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / "modules" / "ai-fixes" / "module.json"
NOTHING = "PEI foreign object check: nothing found."
FOUND = "PEI foreign object check: object found on the plate; waiting for Stop/Continue."
TARGET = "/home/qidi/klipper/klippy/extras/ai_func_manager.py"


class AIErrorType(Enum):
    NONE = ""
    FOREIGN = "foreign"
    NOODLE = "noodle"


def stats_source():
    edits = json.loads(MODULE.read_text(encoding="utf-8"))["files"][TARGET]["edits"]
    new = next(n for _old, n in edits if "def _handle_stats_changed" in n)
    return new.replace("\r\n", "\n")


def method_source():
    edits = json.loads(MODULE.read_text(encoding="utf-8"))["files"][TARGET]["edits"]
    new = next(n for _old, n in edits if "def m4050" in n)
    return new.replace("\r\n", "\n")


class Reply:
    def __init__(self, data):
        self.status_code, self._data = 200, data

    def json(self):
        return self._data


class Rig:
    """The pretend world: a clock, a camera service whose counters follow the scripted positive frames (one frame per second)."""

    def __init__(self, positives, reset_at=None, down_until=0.0, status=200, stored=None):
        self.t, self.positives, self.messages, self.notices, self.posts = 0.0, positives, [], [], []
        self.stored = stored                                         # what qdc_ai_error_code holds when the print starts
        self.reset_at = reset_at                                     # second at which the AI zeroes its counters
        self.down_until, self.status, self.calls = down_until, status, 0   # the AI does not answer before this second
        self.sd = types.SimpleNamespace(current_file=object(), file_position=0, has_run_m4050=False, must_pause_work=False,
                                        work_timer=None, do_resume=lambda: None, do_cancel=lambda: None)
        pause = types.SimpleNamespace(is_paused=False, sd_paused=False, pause_command_sent=False)
        save = types.SimpleNamespace(cmd_SAVE_VARIABLE=lambda cmd: self.notices.append(cmd))
        objects = {"virtual_sdcard": self.sd, "pause_resume": pause, "save_variables": save}
        self.printer = types.SimpleNamespace(lookup_object=lambda n, *a: objects[n],
                                             get_reactor=lambda: types.SimpleNamespace(monotonic=lambda: self.t, pause=self.pause))
        self.gcode = types.SimpleNamespace(respond_info=self.messages.append, create_gcode_command=lambda *a: a)
        self.requests = types.SimpleNamespace(get=self.get, post=self.post)

    def pause(self, until):
        self.t = max(self.t, until)

    def unanswered(self):
        # A real request that gets no answer blocks for its timeout (0.2 s) and then raises (requests' errors are OSErrors).
        self.calls += 1
        if self.t < self.down_until:
            self.t += 0.2
            raise TimeoutError("Read timed out. (read timeout=0.2)")

    def get(self, url, **kw):
        self.unanswered()
        if self.status != 200:
            reply = Reply({})
            reply.status_code = self.status
            return reply
        if self.reset_at is not None and self.t >= self.reset_at:
            return Reply({"frame_detect_pos_count": 0, "foreign_count": 0})
        frames = int(self.t)                                         # one frame per second since the start
        return Reply({"frame_detect_pos_count": 10 + frames,
                      "foreign_count": sum(1 for p in self.positives if int(p) < frames)})

    def post(self, url, json=None, **kw):
        self.unanswered()
        self.posts.append((url, json))
        return Reply({"status": "success", "homing_state": bool(json["state"])})

    def build(self, extra=""):
        ns = {"requests": self.requests, "time": types.SimpleNamespace(time=lambda: 1_000_000, strftime=real_time.strftime, localtime=real_time.localtime),
              "logging": logging,
              "AIErrorType": AIErrorType}
        exec("class M:\n" + method_source().lstrip("\n") + extra, ns)
        m = ns["M"]()
        m.printer, m.gcode, m._foreign_preflight, m.ai_error_type = self.printer, self.gcode, None, None
        m.save_variables = types.SimpleNamespace(qdc_ai_error_code=self.stored)
        m.ai_configs = {AIErrorType.FOREIGN: {"enabled": 1, "count": 0}}
        return m

    def run(self):
        m = self.build()
        m.m4050()
        return m


class SettleTests(unittest.TestCase):
    def test_a_positive_in_the_first_seconds_is_ignored(self):
        rig = Rig(positives=[2.0])                                   # the badly exposed first frame
        m = rig.run()
        self.assertIn(NOTHING, rig.messages)
        self.assertFalse(rig.sd.must_pause_work)
        self.assertEqual(rig.notices, [])
        self.assertIsNone(m._foreign_preflight)

    def test_a_positive_after_the_first_seconds_still_stops_the_print(self):
        rig = Rig(positives=[9.0])
        m = rig.run()
        self.assertIn(FOUND, rig.messages)
        self.assertTrue(rig.sd.must_pause_work)
        self.assertEqual(len(rig.notices), 1)
        self.assertEqual(m._foreign_preflight["phase"], "held")

    def test_the_first_seconds_do_not_hide_a_later_positive(self):
        rig = Rig(positives=[2.0, 10.0])                             # early one ignored, the real one counts
        rig.run()
        self.assertIn(FOUND, rig.messages)

    def test_a_positive_straight_after_the_settle_time_counts(self):
        rig = Rig(positives=[7.0])
        rig.run()
        self.assertIn(FOUND, rig.messages)

    def test_the_whole_check_does_not_take_longer_than_before(self):
        rig = Rig(positives=[])
        rig.run()
        self.assertLessEqual(rig.t, 20.0 + 0.8)                      # the same 20 s window as before the change
        self.assertEqual(rig.posts[0][1], {"state": True})
        self.assertEqual(rig.posts[-1][1], {"state": False})         # the AI worker is always switched back off

    def test_the_ai_is_switched_off_again_after_an_ignored_positive(self):
        rig = Rig(positives=[1.0])
        rig.run()
        self.assertEqual(rig.posts[-1][1], {"state": False})

    def test_the_user_never_sees_the_internal_command_name(self):
        for rig in (Rig(positives=[]), Rig(positives=[9.0]), Rig(positives=[], reset_at=15.0)):
            rig.run()
            self.assertTrue(rig.messages)
            self.assertFalse([m for m in rig.messages if "M4050" in m], rig.messages)
            self.assertTrue(all(m.startswith("PEI foreign object check:") for m in rig.messages), rig.messages)

    def test_a_clean_check_says_plainly_that_nothing_was_found(self):
        rig = Rig(positives=[])
        rig.run()
        self.assertIn(NOTHING, rig.messages)
        self.assertFalse([m for m in rig.messages if "not proof" in m])   # no hedging: the line states what the AI reported

    def test_the_result_is_also_given_when_the_ai_ends_its_own_window_and_zeroes_its_counters(self):
        # Real print 23.11.2026: the AI's own 15 s window ended ("pei and foreign check flag off: over time") before our 20 s
        # did, and the console showed only "inspecting" and then nothing.
        rig = Rig(positives=[], reset_at=15.0)
        rig.run()
        self.assertIn(NOTHING, rig.messages)
        self.assertEqual(rig.posts[-1][1], {"state": False})

    def test_a_positive_before_the_reset_is_still_a_positive(self):
        rig = Rig(positives=[9.0], reset_at=15.0)
        rig.run()
        self.assertIn(FOUND, rig.messages)
        self.assertNotIn(NOTHING, rig.messages)


UNAVAILABLE = "PEI foreign object check: unavailable; continuing without popup."


class SlowAiTests(unittest.TestCase):
    """25.11.2026, first print on the zram kernel: the AI service had been swapped out overnight, did not answer the first
    request within 0.2 s and the whole check was skipped. A slow first answer is tried again, a service that is really not
    there still lets the print go on."""

    def test_an_ai_that_answers_late_is_still_asked(self):
        rig = Rig(positives=[], down_until=2.0)                      # swapped out: silent for the first 2 s
        rig.run()
        self.assertIn(NOTHING, rig.messages)
        self.assertNotIn(UNAVAILABLE, rig.messages)
        self.assertEqual(rig.posts[0][1], {"state": True})
        self.assertEqual(rig.posts[-1][1], {"state": False})

    def test_a_late_ai_still_finds_an_object(self):
        rig = Rig(positives=[12.0], down_until=2.0)                  # a positive well after the late start
        rig.run()
        self.assertIn(FOUND, rig.messages)

    def test_an_ai_that_never_answers_does_not_hold_the_print(self):
        rig = Rig(positives=[], down_until=1e9)
        m = rig.run()
        self.assertIn(UNAVAILABLE, rig.messages)
        self.assertFalse(rig.sd.must_pause_work)
        self.assertIsNone(m._foreign_preflight)
        self.assertLessEqual(rig.t, 6.0)                             # a few tries, not a long wait
        self.assertLessEqual(rig.calls, 6)

    def test_a_refusal_is_not_tried_again(self):
        rig = Rig(positives=[], status=500)                          # the service answers, with an error: nothing to wait for
        rig.run()
        self.assertIn(UNAVAILABLE, rig.messages)
        self.assertEqual(rig.calls, 1)


def clock(moment):
    return real_time.strftime("%Y-%m-%d %H:%M:%S", real_time.localtime(moment))


class TimeStampTests(unittest.TestCase):
    """25.11.2026: the printer screen showed an AI "foreign object" window through two whole prints while the console and the
    log said "nothing found". Now the log says when the AI reported it and what was already stored at the start."""

    def test_a_positive_in_the_first_seconds_is_written_down_with_the_time(self):
        rig = Rig(positives=[2.0])
        rig.run()
        said = [m for m in rig.messages if "the AI reported an object at" in m]
        self.assertEqual(len(said), 1)
        self.assertIn(clock(1_000_000), said[0])
        self.assertIn("NOT paused", said[0])
        self.assertIn(NOTHING, rig.messages)                         # the verdict itself is unchanged

    def test_nothing_is_said_when_the_ai_reports_nothing(self):
        rig = Rig(positives=[])
        rig.run()
        self.assertFalse([m for m in rig.messages if "AI reported" in m or "already stored" in m])

    def test_a_stored_alarm_from_an_earlier_print_is_written_down_with_both_times(self):
        rig = Rig(positives=[], stored="foreign=1 status=1 time=999000")
        rig.run()
        said = [m for m in rig.messages if "already stored" in m]
        self.assertEqual(len(said), 1)
        self.assertIn(clock(999_000), said[0])                       # when it was raised
        self.assertIn(clock(1_000_000), said[0])                     # when this print started
        self.assertIn("this print did not raise it", said[0])

    def test_a_stored_alarm_that_is_zero_or_not_about_foreign_objects_is_not_reported(self):
        for stored in ("foreign=0 status=0 time=5", "noodle=3 status=1 time=5", "", None):
            rig = Rig(positives=[], stored=stored)
            rig.run()
            self.assertFalse([m for m in rig.messages if "already stored" in m], stored)

    def test_an_unreadable_stored_alarm_does_not_stop_the_check(self):
        rig = Rig(positives=[], stored="foreign=abc time=")
        rig.run()
        self.assertIn(NOTHING, rig.messages)


class ClearTheStoredAlarmTests(unittest.TestCase):
    """The alarm text that the screen reads stayed stored after a print and opened the window again at the start of the next
    one. The pre-print check of QIDI cleared it before it started; ours does that now, and the end of every print does too."""

    def cleared(self, rig):
        return [n for n in rig.notices if n[2]["VALUE"] == "''"]

    def test_a_stored_alarm_is_cleared_when_the_check_starts_and_the_log_says_so(self):
        rig = Rig(positives=[], stored="foreign=1 status=1 time=999000")
        rig.run()
        self.assertEqual(len(self.cleared(rig)), 1)
        self.assertEqual(self.cleared(rig)[0][2]["VARIABLE"], "qdc_ai_error_code")
        self.assertTrue([m for m in rig.messages if "was cleared" in m and "status=1" in m])
        self.assertIn(NOTHING, rig.messages)

    def test_nothing_is_written_when_no_alarm_is_active(self):
        for stored in ("foreign=0 status=0 time=5", "noodle=0 status=0 time=5", "", None):
            rig = Rig(positives=[], stored=stored)
            rig.run()
            self.assertEqual(rig.notices, [], stored)

    def test_the_end_of_a_print_clears_an_active_alarm(self):
        for new_status in ("complete", "cancelled", "standby", "error"):
            rig = Rig(positives=[], stored="foreign=1 status=1 time=999000")
            m = rig.build(stats_source())
            m.ai_error_type = AIErrorType.FOREIGN
            m.ai_configs[AIErrorType.FOREIGN]["count"] = 1
            m._handle_stats_changed("printing", new_status)
            self.assertEqual(len(self.cleared(rig)), 1, new_status)
            self.assertTrue([x for x in rig.messages if "cleared at the end of the print" in x], new_status)
            self.assertEqual(m.ai_configs[AIErrorType.FOREIGN]["count"], 0)       # what the stock method did stays
            self.assertEqual(m.ai_error_type, AIErrorType.NONE)

    def test_a_pause_does_not_clear_the_alarm(self):
        rig = Rig(positives=[], stored="foreign=1 status=1 time=999000")
        m = rig.build(stats_source())
        m._handle_stats_changed("printing", "paused")
        m._handle_stats_changed("paused", "printing")
        self.assertEqual(rig.notices, [])

    def test_the_end_of_a_print_without_an_alarm_writes_nothing(self):
        rig = Rig(positives=[], stored="noodle=0 status=0 time=5")
        m = rig.build(stats_source())
        m._handle_stats_changed("printing", "complete")
        self.assertEqual(rig.notices, [])


if __name__ == "__main__":
    unittest.main()
