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
import types
import unittest
from enum import Enum
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / "modules" / "ai-fixes" / "module.json"
TARGET = "/home/qidi/klipper/klippy/extras/ai_func_manager.py"


class AIErrorType(Enum):
    NONE = ""
    FOREIGN = "foreign"
    NOODLE = "noodle"


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

    def __init__(self, positives):
        self.t, self.positives, self.messages, self.notices, self.posts = 0.0, positives, [], [], []
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

    def get(self, url, **kw):
        frames = int(self.t)                                         # one frame per second since the start
        return Reply({"frame_detect_pos_count": 10 + frames,
                      "foreign_count": sum(1 for p in self.positives if int(p) < frames)})

    def post(self, url, json=None, **kw):
        self.posts.append((url, json))
        return Reply({"status": "success", "homing_state": bool(json["state"])})

    def run(self):
        ns = {"requests": self.requests, "time": types.SimpleNamespace(time=lambda: 1_000_000), "logging": logging,
              "AIErrorType": AIErrorType}
        exec("class M:\n" + method_source().lstrip("\n"), ns)
        m = ns["M"]()
        m.printer, m.gcode, m._foreign_preflight, m.save_variables, m.ai_error_type = self.printer, self.gcode, None, None, None
        m.ai_configs = {AIErrorType.FOREIGN: {"enabled": 1, "count": 0}}
        m.m4050()
        return m


class SettleTests(unittest.TestCase):
    def test_a_positive_in_the_first_seconds_is_ignored(self):
        rig = Rig(positives=[2.0])                                   # the badly exposed first frame
        m = rig.run()
        self.assertIn("M4050: no positive detection; continuing (not proof of an empty bed).", rig.messages)
        self.assertFalse(rig.sd.must_pause_work)
        self.assertEqual(rig.notices, [])
        self.assertIsNone(m._foreign_preflight)

    def test_a_positive_after_the_first_seconds_still_stops_the_print(self):
        rig = Rig(positives=[9.0])
        m = rig.run()
        self.assertIn("M4050: foreign object detected; waiting for Stop/Continue.", rig.messages)
        self.assertTrue(rig.sd.must_pause_work)
        self.assertEqual(len(rig.notices), 1)
        self.assertEqual(m._foreign_preflight["phase"], "held")

    def test_the_first_seconds_do_not_hide_a_later_positive(self):
        rig = Rig(positives=[2.0, 10.0])                             # early one ignored, the real one counts
        rig.run()
        self.assertIn("M4050: foreign object detected; waiting for Stop/Continue.", rig.messages)

    def test_a_positive_straight_after_the_settle_time_counts(self):
        rig = Rig(positives=[7.0])
        rig.run()
        self.assertIn("M4050: foreign object detected; waiting for Stop/Continue.", rig.messages)

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


if __name__ == "__main__":
    unittest.main()
