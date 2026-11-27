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
import atexit
import base64
import logging
import os
import shutil
import tempfile
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


class GcodeError(Exception):
    """What Klipper raises for a command that fails (gcode.error)."""


CONFIGURED = {"stepper_x": 1.07, "stepper_y": 1.07}
HOMING = 0.9


class Machine:
    """The pretend toolhead: position, homed axes and Klipper's refusal to move an axis that is not homed."""

    def __init__(self, rig, homed, position, report):
        self.rig, self.homed, self.pos, self.report = rig, homed, list(position) + [0.0], report
        self.z_move_fails = False
        self.broken = set()                                           # names of methods that fail like a bug in our code or in the fork
        self.current = dict(CONFIGURED)                               # motor current of X and Y
        self.absolute = True                                          # G90 / G91

    def get_status(self, eventtime):
        if self.report is None:
            raise KeyError("no status")
        return self.report

    def get_position(self):
        return list(self.pos)

    def set_position(self, newpos, homing_axes=()):
        assert self.rig.locked, "the toolhead is moved without the G-code mutex"
        self.fail_if_broken("set_position_before")
        self.pos = list(newpos)
        self.homed = "".join(a for k, a in enumerate("xyz") if a in self.homed or k in homing_axes)
        self.rig.events.append(("set_position", (self.pos[2], list(homing_axes)), self.rig.t))
        self.fail_if_broken("set_position_after")

    def fail_if_broken(self, name):
        if name in self.broken:
            raise AttributeError("broken: " + name)

    def motor_off(self):
        self.homed = ""
        self.rig.events.append(("motor_off", None, self.rig.t))

    def manual_move(self, coord, speed):
        assert self.rig.locked, "the toolhead is moved without the G-code mutex"
        for k, value in enumerate(coord):
            if value is not None and "xyz"[k] not in self.homed:
                raise GcodeError("Must home axis first")
        if self.z_move_fails:
            raise GcodeError("the bed did not move")
        before = self.pos[2]
        for k, value in enumerate(coord):
            if value is not None:
                self.pos[k] = value
        self.rig.events.append(("z_move", (before, self.pos[2], speed), self.rig.t))
        self.rig.spend(self.rig.durations.get("z", 0.0))

    def wait_moves(self):
        pass

    def get_kinematics(self):
        return types.SimpleNamespace(get_status=lambda eventtime: {"homed_axes": self.homed}, note_z_not_homed=self.note_z_not_homed)

    def note_z_not_homed(self):
        self.fail_if_broken("note_z_not_homed")
        self.homed = self.homed.replace("z", "")
        self.rig.events.append(("z_forgotten", None, self.rig.t))


class Mutex:
    def __init__(self, rig):
        self.rig = rig

    def __enter__(self):
        assert not self.rig.locked, "the G-code mutex is taken twice: Klipper would hang"
        self.rig.deliver()                                            # Klipper's mutex is a queue: who waits goes first
        self.rig.locked = True

    def __exit__(self, *error):
        self.rig.locked = False


SET_START_HOME = "SET_GCODE_VARIABLE MACRO=_TWEAKED_START_HOME VARIABLE=xy_fresh VALUE="


class Rig:
    """The pretend world: a clock, a camera service whose counters follow the scripted positive frames (one frame per second)."""

    def __init__(self, positives, reset_at=None, down_until=0.0, status=200, stored=None, light=None, history=None, capture=None, toolhead=None,
                 script_fails=False, homed="xyz", position=(260.0, 260.0, 50.0), home_fails=False, durations=None):
        self.t, self.positives, self.messages, self.notices, self.posts = 0.0, positives, [], [], []
        self.events, self.scripts, self.timers = [], [], []          # (kind, what, second) in order; G-code the check ran; (second, action) the user does meanwhile
        self.ai_at, self.first_call, self.script_fails = None, None, script_fails   # second the AI was switched on; second of the first request
        self.history, self.capture = history, capture               # pictures of the AI (base64 text) for /history_frames and /capture
        self.light = light                                           # value of output_pin caselight (None: no such pin)
        self.stored = stored                                         # what qdc_ai_error_code holds when the print starts
        self.reset_at = reset_at                                     # seconds after its start at which the AI zeroes its counters
        self.down_until, self.status, self.calls = down_until, status, 0   # the AI does not answer for this many seconds after the first request
        self.sd = types.SimpleNamespace(current_file=object(), file_position=0, has_run_m4050=False, must_pause_work=False,
                                        work_timer=None, do_resume=lambda: None, do_cancel=lambda: None)
        pause = types.SimpleNamespace(is_paused=False, sd_paused=False, pause_command_sent=False)
        save = types.SimpleNamespace(cmd_SAVE_VARIABLE=self.save)
        objects = {"virtual_sdcard": self.sd, "pause_resume": pause, "save_variables": save}
        self.locked, self.home_fails, self.durations = False, home_fails, durations or {}
        self.machine = Machine(self, homed, position, toolhead)
        objects["toolhead"] = objects["stepper_enable"] = self.machine
        self.abort_epoch, self.restore_fails, self.home_breaks_late = 0, False, False
        self.queue, self.errors, self.resets, self.after_homing = [], [], [], None
        self.xy_fresh, self.park_fails = None, False                 # xy_fresh: None = the module start-keep-xy is not installed
        self.sd.do_cancel, self.sd._reset_file, self.sd.cmd_from_sd = self.do_cancel, self.reset_file, False
        settings = {"tmc2240 " + name: {"run_current": value} for name, value in CONFIGURED.items()}
        objects["configfile"] = types.SimpleNamespace(get_status=lambda eventtime: {"settings": settings})
        if light is not None:
            objects["output_pin caselight"] = types.SimpleNamespace(get_status=lambda eventtime: {"value": self.light})
        self.objects = objects
        self.printer = types.SimpleNamespace(lookup_object=lambda n, *a: objects.get(n, a[0]) if a else objects[n],
                                             get_reactor=lambda: types.SimpleNamespace(monotonic=lambda: self.t, pause=self.pause))
        self.gcode = types.SimpleNamespace(respond_info=self.messages.append, create_gcode_command=lambda *a: a,
                                           run_script_from_command=self.run_script, run_script=self.run_queued,
                                           get_mutex=lambda: Mutex(self), error=GcodeError)
        self.requests = types.SimpleNamespace(get=self.get, post=self.post)

    def spend(self, seconds):
        self.pause(self.t + seconds)

    def abort_waits(self):
        # QIDI: a cancel makes Klipper drop the rest of every G-code script that is running (gcode.abort_waits).
        self.abort_epoch += 1

    def do_cancel(self):
        # QIDI's virtual_sdcard.do_cancel: drop what is running, close the file.
        self.abort_waits()
        self.sd.current_file = None

    def reset_file(self):
        self.sd.current_file, self.sd.has_run_m4050 = None, False
        self.resets.append(self.t)

    def send_reset(self, m):
        """SDCARD_RESET_FILE arrives (QIDI's Moonraker sends it after every cancel); it waits for the G-code mutex."""
        self.queue.append(m)
        self.deliver()

    def deliver(self):
        while self.queue and not self.locked:
            m = self.queue.pop(0)
            if not m.foreign_preflight_command("SDCARD_RESET_FILE"):  # Klipper's own command, as in virtual_sdcard.py
                if self.sd.cmd_from_sd:
                    self.errors.append("SDCARD_RESET_FILE cannot be run from the sdcard")
                else:
                    self.sd._reset_file()

    def work(self, m):
        """QIDI's SD worker around the check: "command from the file" until it returns; then the waiting commands run."""
        self.sd.cmd_from_sd = True
        try:
            m.m4050()
            self.sd.has_run_m4050 = True
        finally:
            self.sd.cmd_from_sd = False
            self.deliver()

    def run_queued(self, text):
        # gcode.run_script takes the G-code mutex itself: calling it while the mutex is held would hang Klipper.
        assert not self.locked, "run_script while the G-code mutex is held: Klipper would hang"
        self.deliver()                                                # who already waits for the mutex goes first
        self.locked = True
        try:
            self.execute(text)
        finally:
            self.locked = False                                       # the waiting command gets it when the check yields
        if text == "G28 X Y" and self.after_homing:
            hook, self.after_homing = self.after_homing, None
            hook()

    def execute(self, text):
        self.events.append(("gcode", text, self.t))
        for line in text.split("\n"):
            if line.startswith("SET_TMC_CURRENT "):
                if self.restore_fails:
                    raise GcodeError("the driver does not answer")
                words = dict(w.split("=") for w in line.split()[1:])
                self.machine.current[words["STEPPER"]] = float(words["CURRENT"])
            elif line == "G90":
                self.machine.absolute = True
            elif line.startswith("G28"):
                if self.home_fails:
                    raise GcodeError("homing failed")
                axes = line.split()[1:] or ["X", "Y", "Z"]
                # QIDI's homing macro: lower the motor current, home, back off in relative mode, put current and mode back.
                self.machine.current = {name: HOMING for name in CONFIGURED}
                self.machine.absolute = False
                if self.home_breaks_late:
                    raise GcodeError("homing failed half way")
                epoch = self.abort_epoch
                self.spend(self.durations.get("home", 0.0))
                if self.abort_epoch != epoch:
                    self.machine.homed = "y"                          # the first axis was done, the rest of the macro is dropped
                    continue
                self.machine.homed = "".join(a for a in "xyz" if a in self.machine.homed or a.upper() in axes)
                self.machine.current = dict(CONFIGURED)
                self.machine.absolute = True
            elif line.startswith("G1 "):
                if self.park_fails:
                    raise GcodeError("the head did not move")
                words = {w[0]: float(w[1:]) for w in line.split()[1:]}
                for k, axis in enumerate("XYZ"):
                    if axis in words:
                        if axis.lower() not in self.machine.homed:
                            raise GcodeError("Must home axis first")
                        self.machine.pos[k] = words[axis]
                self.spend(self.durations.get("park", 0.0))

    def pause(self, until):
        self.t = max(self.t, until)
        for timer in [x for x in self.timers if self.t >= x[0]]:    # what the user does while the check waits
            self.timers.remove(timer)
            timer[1]()
        self.deliver()

    def save(self, cmd):
        self.notices.append(cmd)
        self.events.append(("notice", cmd[2]["VALUE"], self.t))

    def run_script(self, text):
        if self.script_fails:
            raise RuntimeError("the pin is not there")
        self.scripts.append(text)
        self.events.append(("script", text, self.t))
        if text.startswith(SET_START_HOME):
            if self.xy_fresh is None:
                raise GcodeError("Unknown gcode_macro")
            self.xy_fresh = int(text[len(SET_START_HOME):])
        if self.light is not None and "caselight VALUE=1" in text:
            self.light = 1.0

    def unanswered(self):
        # A real request that gets no answer blocks for its timeout (0.2 s) and then raises (requests' errors are OSErrors).
        self.calls += 1
        if self.first_call is None:
            self.first_call = self.t
        if self.t < self.first_call + self.down_until:
            self.t += 0.2
            raise TimeoutError("Read timed out. (read timeout=0.2)")

    def get(self, url, **kw):
        self.unanswered()
        if url.endswith("/history_frames?type=foreign"):
            return Reply([] if self.history is None else self.history)
        if url.endswith("/capture"):
            return Reply({"image": self.capture} if self.capture else {})
        if self.status != 200:
            reply = Reply({})
            reply.status_code = self.status
            return reply
        since = 0.0 if self.ai_at is None else self.t - self.ai_at   # the AI looks at the plate from the moment it is switched on
        if self.reset_at is not None and self.ai_at is not None and since >= self.reset_at:
            return Reply({"frame_detect_pos_count": 0, "foreign_count": 0})
        frames = int(since)                                          # one frame per second since the AI was switched on
        return Reply({"frame_detect_pos_count": 10 + frames,
                      "foreign_count": sum(1 for p in self.positives if int(p) < frames)})

    def post(self, url, json=None, **kw):
        self.unanswered()
        self.posts.append((url, json))
        self.events.append(("post", json["state"], self.t))
        if json["state"] and self.ai_at is None:
            self.ai_at = self.t
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
        self.frames_dir = tempfile.mkdtemp(prefix="q2frames")        # never the printer's folder: the test must not create it on the PC
        atexit.register(shutil.rmtree, self.frames_dir, True)
        m._alarm_frames_dir = self.frames_dir
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
        self.assertLessEqual(rig.t, WAIT + 20.0 + 0.8)               # the same 20 s window as before, after the wait for the camera
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
        self.assertLessEqual(rig.t, WAIT + 6.0)                      # the wait for the camera, then a few tries, not a long wait
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


class CaseLightTests(unittest.TestCase):
    """The log says what the case light does when the AI looks at the plate (25.11.2026: the screen showed an alarm and nothing
    in the log said whether the light had come on before the first frame)."""

    def light_lines(self, rig):
        return [m for m in rig.messages if "the case light is" in m]

    def test_the_light_state_is_written_down_when_the_ai_starts_to_look(self):
        # a light that was off is switched on by the check (see CameraSettleTests), so the AI starts with the light on
        for value, word in ((1.0, "on"), (0.0, "on")):
            rig = Rig(positives=[], light=value)
            rig.run()
            lines = self.light_lines(rig)
            self.assertEqual(len(lines), 1, word)
            self.assertIn("light is " + word + " at ", lines[0])
            self.assertIn(clock(1_000_000), lines[0])

    def test_a_missing_light_pin_does_not_stop_the_check(self):
        rig = Rig(positives=[])
        rig.run()
        self.assertIn("light is unknown", self.light_lines(rig)[0])
        self.assertIn(NOTHING, rig.messages)

    def test_the_light_state_is_in_the_line_about_an_early_positive(self):
        rig = Rig(positives=[2.0], light=1.0)
        rig.run()
        said = [m for m in rig.messages if "the AI reported an object at" in m]
        self.assertEqual(len(said), 1)
        self.assertIn("the case light is on", said[0])


class SavedPicturesTests(unittest.TestCase):
    """25.11.2026: the screen showed an alarm on an empty plate and not one picture of what the AI had looked at existed."""

    def files(self, rig):
        return sorted(os.listdir(rig.frames_dir))

    def test_the_pictures_of_the_ai_are_saved_when_it_reports_an_object(self):
        jpeg = base64.b64encode(b"\xff\xd8picture\xff\xd9").decode()
        rig = Rig(positives=[2.0], history=[jpeg, jpeg], capture=jpeg)
        rig.run()
        names = self.files(rig)
        self.assertEqual(len(names), 3)
        self.assertEqual(sorted(n.split("_", 2)[2] for n in names), ["ai0.jpg", "ai1.jpg", "now0.jpg"])
        self.assertTrue(all("_early_" in n for n in names))
        with open(os.path.join(rig.frames_dir, names[0]), "rb") as f:
            self.assertEqual(f.read(), b"\xff\xd8picture\xff\xd9")
        self.assertTrue([m for m in rig.messages if "pictures of the AI were saved" in m])
        self.assertIn(NOTHING, rig.messages)

    def test_a_positive_after_the_first_seconds_saves_pictures_too(self):
        jpeg = base64.b64encode(b"x").decode()
        rig = Rig(positives=[9.0], history=[jpeg], capture=jpeg)
        rig.run()
        self.assertTrue([n for n in self.files(rig) if "_found_" in n])
        self.assertIn(FOUND, rig.messages)

    def test_nothing_is_saved_when_the_ai_reports_nothing(self):
        rig = Rig(positives=[], history=[base64.b64encode(b"x").decode()], capture=base64.b64encode(b"x").decode())
        rig.run()
        self.assertEqual(self.files(rig), [])

    def test_a_service_without_pictures_or_with_odd_answers_does_not_stop_the_check(self):
        for history, capture in ((None, None), (["", 5, None], ""), (["not base64 !!"], "###")):
            rig = Rig(positives=[2.0], history=history, capture=capture)
            rig.run()
            self.assertIn(NOTHING, rig.messages)
            self.assertEqual(rig.posts[-1][1], {"state": False})

    def test_only_the_newest_files_are_kept(self):
        rig = Rig(positives=[2.0], history=[base64.b64encode(b"x").decode()] * 2, capture=base64.b64encode(b"x").decode())
        m = rig.build()
        for k in range(20):
            open(os.path.join(rig.frames_dir, "2000010%d-000000_old_ai0.jpg" % (k % 10) + str(k)), "wb").close()
        m.m4050()
        self.assertEqual(len(self.files(rig)), 12)


class ToolheadPositionTests(unittest.TestCase):
    """25.11.2026: the alarms on an empty plate may depend on where the toolhead and the bed stand; the log says where."""

    def lines(self, rig):
        return [m for m in rig.messages if "the toolhead is at" in m]

    def test_the_position_and_the_homed_axes_are_written_down(self):
        rig = Rig(positives=[], toolhead={"position": [260.0, 260.0, 50.0, 0.0], "homed_axes": "xyz"})
        rig.run()
        self.assertEqual(len(self.lines(rig)), 1)
        self.assertIn('X260.0 Y260.0 Z50.0, homed axes "xyz"', self.lines(rig)[0])

    def test_axes_that_are_not_homed_are_said_so(self):
        rig = Rig(positives=[], toolhead={"position": [0.0, 0.0, 0.0, 0.0], "homed_axes": ""})
        rig.run()
        self.assertIn('homed axes ""', self.lines(rig)[0])

    def test_an_unreadable_or_odd_toolhead_report_does_not_stop_the_check(self):
        for toolhead in (None, {}, {"position": "bad"}):
            rig = Rig(positives=[], toolhead=toolhead)
            rig.run()
            self.assertIn("the toolhead is at unknown", self.lines(rig)[0])
            self.assertIn(NOTHING, rig.messages)


WAIT = 5.0                                                           # seconds the camera gets after the light before the AI is started
SWITCH_ON = "SET_PIN PIN=caselight VALUE=1"


class CameraSettleTests(unittest.TestCase):
    """26.11.2026, test on the printer without a print: the AI started at once with the light wrote a "foreign object" alarm within
    four seconds from badly exposed, completely white frames of an EMPTY plate (2 of 2 runs); started 5 s after the light it wrote
    none (0 of 2). So the check switches the light on itself and starts the AI only when the camera has had time to settle."""

    def ai_started(self, rig):
        return next(t for kind, what, t in rig.events if kind == "post" and what is True)

    def test_the_ai_is_started_only_after_the_camera_had_time_to_settle(self):
        rig = Rig(positives=[], light=1.0)
        rig.run()
        self.assertGreaterEqual(self.ai_started(rig), WAIT)
        self.assertLess(self.ai_started(rig), WAIT + 1.5)             # a wait, not a long delay of the print

    def test_a_light_that_is_off_is_switched_on_at_the_start_and_the_log_says_so(self):
        rig = Rig(positives=[], light=0.0)
        rig.run()
        scripts = [e for e in rig.events if e[0] == "script"]
        self.assertEqual([e[1] for e in scripts], [SWITCH_ON])
        self.assertLess(scripts[0][2], 1.0)                           # at the start, so the camera has the whole wait
        self.assertGreaterEqual(self.ai_started(rig) - scripts[0][2], WAIT - 0.5)
        self.assertTrue([m for m in rig.messages if "the case light was off" in m and "switched on" in m], rig.messages)

    def test_a_light_that_is_already_on_is_left_alone_and_the_wait_stays(self):
        rig = Rig(positives=[], light=1.0)                            # nobody knows since when it is on
        rig.run()
        self.assertEqual(rig.scripts, [])
        self.assertGreaterEqual(self.ai_started(rig), WAIT)

    def test_a_missing_light_pin_switches_nothing_and_does_not_stop_the_check(self):
        rig = Rig(positives=[])
        rig.run()
        self.assertEqual(rig.scripts, [])
        self.assertGreaterEqual(self.ai_started(rig), WAIT)
        self.assertIn(NOTHING, rig.messages)

    def test_a_light_that_cannot_be_switched_on_does_not_stop_the_check(self):
        rig = Rig(positives=[], light=0.0, script_fails=True)
        rig.run()
        self.assertGreaterEqual(self.ai_started(rig), WAIT)
        self.assertIn(NOTHING, rig.messages)
        self.assertEqual(rig.posts[-1][1], {"state": False})

    def test_the_wait_is_written_down(self):
        rig = Rig(positives=[], light=1.0)
        rig.run()
        self.assertIn("PEI foreign object check: waiting 5 s for the camera to settle after the light.", rig.messages)
        self.assertTrue(all(m.startswith("PEI foreign object check:") for m in rig.messages), rig.messages)

    def test_a_cancel_during_the_wait_starts_no_ai_and_leaves_nothing_behind(self):
        rig = Rig(positives=[], light=1.0)
        rig.timers.append((2.0, lambda: setattr(rig.sd, "current_file", None)))
        m = rig.run()
        self.assertEqual(rig.posts, [])
        self.assertIsNone(m._foreign_preflight)
        self.assertNotIn(NOTHING, rig.messages)

    def test_a_pause_during_the_wait_ends_the_check_without_starting_the_ai(self):
        rig = Rig(positives=[], light=1.0)
        rig.timers.append((3.0, lambda: setattr(rig.sd, "must_pause_work", True)))
        rig.run()
        self.assertEqual(rig.posts, [])
        self.assertNotIn(NOTHING, rig.messages)

    def test_the_ai_still_gets_its_whole_twenty_seconds(self):
        rig = Rig(positives=[], light=1.0)
        rig.run()
        self.assertGreaterEqual(rig.t - self.ai_started(rig), 19.0)
        self.assertLessEqual(rig.t - self.ai_started(rig), 20.0 + 0.8)

    def test_an_object_that_is_really_there_is_still_found_after_the_wait(self):
        rig = Rig(positives=[9.0], light=1.0)                         # nine seconds after the AI started
        m = rig.run()
        self.assertIn(FOUND, rig.messages)
        self.assertTrue(rig.sd.must_pause_work)
        self.assertEqual(m._foreign_preflight["phase"], "held")

    def test_a_stored_alarm_is_cleared_before_the_wait_not_after_it(self):
        rig = Rig(positives=[], light=1.0, stored="foreign=1 status=1 time=999000")
        rig.run()
        cleared = [e for e in rig.events if e[0] == "notice" and e[1] == "\'\'"]
        self.assertEqual(len(cleared), 1)
        self.assertLess(cleared[0][2], 1.0)                           # at the start, before the wait for the camera

PARK = "G90\nG1 X260 Y260 F3000\nM400"
MOVING = "PEI foreign object check: moving the head to the rear right corner, away from the camera's view of the plate."


class ParkForTheCameraTests(unittest.TestCase):
    """26.11.2026: with the toolhead in the middle of the picture the AI reported an object on an empty plate (after a Home); at
    the rear right corner it did not (2 of 2). So before the AI looks, X and Y are homed (never Z: homing Z presses the nozzle
    on a plate nobody has looked at yet) and the head is driven to that corner. The owner decides what the warning means."""

    def events(self, rig, *kinds):
        return [e for e in rig.events if e[0] in kinds]

    def gcodes(self, rig):
        return [e[1] for e in self.events(rig, "gcode")]

    def ai_started(self, rig):
        return next(t for kind, what, t in rig.events if kind == "post" and what is True)

    def test_after_the_motors_were_off_the_bed_drops_then_x_and_y_home_then_the_head_parks(self):
        rig = Rig(positives=[], light=1.0, homed="", position=(0.0, 0.0, 0.0))
        rig.run()
        moves = [(e[0], e[1]) for e in self.events(rig, "set_position", "z_move", "z_forgotten", "gcode", "post")]
        self.assertEqual(moves[:6], [("set_position", (0.0, [2])), ("z_move", (0.0, 5.0, 10.0)), ("z_forgotten", None),
                                     ("gcode", "G28 X Y"), ("gcode", PARK), ("post", True)])
        self.assertEqual(rig.machine.pos[:2], [260.0, 260.0])
        self.assertIn(NOTHING, rig.messages)

    def test_the_printer_never_keeps_believing_that_it_knows_the_bed_height(self):
        rig = Rig(positives=[], homed="")
        rig.run()
        self.assertEqual(rig.machine.homed, "xy")                     # the print file homes everything again

    def test_z_is_never_homed_by_the_check(self):
        for homed in ("", "xy", "xyz", "z"):
            rig = Rig(positives=[], homed=homed)
            rig.run()
            homing = [g for g in self.gcodes(rig) if "G28" in g]
            self.assertTrue(all(g == "G28 X Y" for g in homing), (homed, homing))

    def test_homed_axes_are_not_homed_again_and_a_low_enough_bed_is_not_moved(self):
        for z in (50.0, 138.0, 265.0):
            rig = Rig(positives=[], homed="xyz", position=(100.0, 100.0, z))
            rig.run()
            self.assertEqual(self.gcodes(rig), [PARK], z)
            self.assertEqual(self.events(rig, "set_position", "z_move"), [], z)
            self.assertEqual(rig.machine.homed, "xyz")

    def test_a_bed_close_to_the_nozzle_is_only_ever_moved_away_from_it(self):
        # 50 mm is the lowest bed height at which the AI was tried with the head in this corner
        for z in (-1.0, 0.0, 20.0, 49.9):
            rig = Rig(positives=[], homed="xyz", position=(100.0, 100.0, z))
            rig.run()
            self.assertEqual([e[1] for e in self.events(rig, "z_move")], [(z, 50.0, 10.0)], z)
            self.assertEqual(self.events(rig, "set_position", "z_forgotten"), [], z)
            self.assertEqual(rig.machine.homed, "xyz")                # the height was really known: it stays known

    def test_only_a_missing_x_or_y_is_homed(self):
        for homed, expected in (("xy", [PARK]), ("x", ["G28 X Y", PARK]), ("yz", ["G28 X Y", PARK])):
            rig = Rig(positives=[], homed=homed)
            rig.run()
            self.assertEqual(self.gcodes(rig), expected, homed)

    def test_the_ai_looks_only_after_the_head_has_arrived_and_the_camera_has_settled(self):
        rig = Rig(positives=[], light=1.0, homed="", durations={"home": 9.0, "park": 4.0})
        rig.run()
        self.assertGreaterEqual(self.ai_started(rig), 9.0 + 4.0 + WAIT)
        self.assertGreaterEqual(rig.t - self.ai_started(rig), 19.0)   # still its whole window

    def test_the_user_is_told_that_the_head_moves(self):
        rig = Rig(positives=[], homed="")
        rig.run()
        self.assertEqual(rig.messages.count(MOVING), 1)
        self.assertTrue(all(m.startswith("PEI foreign object check:") for m in rig.messages), rig.messages)
        self.assertFalse([m for m in rig.messages if "without movement" in m])

    def test_a_bed_that_does_not_move_stops_the_print_with_that_error(self):
        rig = Rig(positives=[], homed="")
        rig.machine.z_move_fails = True
        m = rig.build()
        with self.assertRaises(GcodeError):
            m.m4050()
        self.assertEqual(rig.machine.homed, "")                       # the made-up height is forgotten even then
        self.assertEqual((rig.posts, self.gcodes(rig)), ([], []))
        self.assertIsNone(m._foreign_preflight)
        self.assertFalse(rig.locked)

    def test_a_homing_that_fails_stops_the_print_with_that_error(self):
        rig = Rig(positives=[], homed="", home_fails=True)
        m = rig.build()
        with self.assertRaises(GcodeError):
            m.m4050()
        self.assertEqual(rig.posts, [])                               # the AI does not look at a head that did not move
        self.assertNotIn("z", rig.machine.homed)
        self.assertIsNone(m._foreign_preflight)
        self.assertNotIn(UNAVAILABLE, rig.messages)

    def test_a_cancel_while_the_bed_drops_stops_before_the_homing(self):
        rig = Rig(positives=[], homed="", durations={"z": 1.0})
        m = rig.build()
        rig.timers.append((0.5, lambda: m.foreign_preflight_command("CANCEL_PRINT")))
        m.m4050()
        self.assertEqual((self.gcodes(rig), rig.posts), ([], []))
        self.assertNotIn("z", rig.machine.homed)
        self.assertIsNone(m._foreign_preflight)

    def test_a_cancel_while_x_and_y_home_stops_before_the_park(self):
        rig = Rig(positives=[], homed="", durations={"home": 8.0})
        m = rig.build()
        rig.timers.append((3.0, lambda: m.foreign_preflight_command("CANCEL_PRINT")))
        m.m4050()
        self.assertEqual(self.gcodes(rig), ["G28 X Y", RESTORE])
        self.assertEqual(rig.posts, [])
        self.assertIsNone(m._foreign_preflight)

    def test_a_pause_while_x_and_y_home_holds_the_print_without_further_moves(self):
        rig = Rig(positives=[], homed="", durations={"home": 8.0})
        m = rig.build()
        rig.timers.append((3.0, lambda: m.foreign_preflight_command("PAUSE")))
        m.m4050()
        self.assertEqual(self.gcodes(rig), ["G28 X Y"])
        self.assertEqual(rig.posts, [])
        self.assertTrue(rig.sd.must_pause_work)
        self.assertEqual(m._foreign_preflight["phase"], "held")      # Continue still finds the waiting print

    def test_a_cancel_while_the_head_drives_to_the_corner_starts_no_ai(self):
        rig = Rig(positives=[], homed="xyz", durations={"park": 4.0})
        m = rig.build()
        rig.timers.append((1.0, lambda: m.foreign_preflight_command("CANCEL_PRINT")))
        m.m4050()
        self.assertEqual(rig.posts, [])
        self.assertNotIn(NOTHING, rig.messages)

    def test_nothing_moves_when_the_check_is_switched_off(self):
        rig = Rig(positives=[], homed="")
        m = rig.build()
        m.ai_configs[AIErrorType.FOREIGN]["enabled"] = 0
        m.m4050()
        self.assertEqual(rig.events, [])

    def test_nothing_moves_for_a_resumed_print(self):
        for change in ({"has_run_m4050": True}, {"file_position": 1000}, {"current_file": None}):
            rig = Rig(positives=[], homed="")
            for name, value in change.items():
                setattr(rig.sd, name, value)
            rig.run()
            self.assertEqual(rig.events, [], change)

SKIPPED = ("PEI foreign object check: the head could not be moved to the corner (see the log); the check is skipped "
           "and the print goes on.")


class ParkThatBreaksTests(unittest.TestCase):
    """Review by the 03.02 agent (26.11.2026): only a movement that the printer refuses may stop a print. A mistake in our code,
    or a Klipper that differs from what we read, must not block every print - and must never leave a made-up bed height behind."""

    def broken(self, name):
        rig = Rig(positives=[], homed="")
        rig.machine.broken.add(name)
        m = rig.run()                                                 # no exception: the print goes on
        self.assertIn(SKIPPED, rig.messages, name)
        self.assertNotIn(UNAVAILABLE, rig.messages, name)
        self.assertNotIn(NOTHING, rig.messages, name)
        self.assertEqual(rig.posts, [], name)                         # the AI does not look at a head that may be anywhere
        self.assertNotIn("z", rig.machine.homed, name)
        self.assertFalse(rig.sd.must_pause_work, name)
        self.assertIsNone(m._foreign_preflight, name)
        self.assertFalse(rig.locked, name)
        return rig

    def test_a_toolhead_that_does_not_take_the_new_position_does_not_block_the_print(self):
        self.broken("set_position_before")

    def test_a_failure_after_the_position_was_taken_still_forgets_the_height(self):
        rig = self.broken("set_position_after")
        self.assertIn("z_forgotten", [e[0] for e in rig.events])

    def test_when_the_height_cannot_be_forgotten_the_motors_are_switched_off(self):
        rig = self.broken("note_z_not_homed")
        self.assertIn("motor_off", [e[0] for e in rig.events])        # Klipper then knows no axis any more
        self.assertEqual([e for e in rig.events if e[0] == "gcode"], [])

    def test_the_motors_are_left_on_in_a_normal_run(self):
        rig = Rig(positives=[], homed="")
        rig.run()
        self.assertNotIn("motor_off", [e[0] for e in rig.events])

RESTORE = ("SET_TMC_CURRENT STEPPER=stepper_x CURRENT=1.07\nSET_TMC_CURRENT STEPPER=stepper_y CURRENT=1.07\nG90")
RESTORED = "PEI foreign object check: the homing was cut short; the motor current of X and Y was put back."


class CutHomingTests(unittest.TestCase):
    """26.11.2026, third test on the printer: a cancel during "G28 X Y" made QIDI drop the rest of the homing macro, and the X
    and Y motors stayed at the homing current (0.9 A instead of 1.07 A) until the next homing."""

    def gcodes(self, rig):
        return [e[1] for e in rig.events if e[0] == "gcode"]

    def cancelled(self):
        rig = Rig(positives=[], homed="", durations={"home": 8.0})
        m = rig.build()
        rig.timers.append((3.0, lambda: m.foreign_preflight_command("CANCEL_PRINT")))
        return rig, m

    def test_a_cancel_during_the_homing_puts_the_motor_current_and_the_mode_back(self):
        rig, m = self.cancelled()
        m.m4050()
        self.assertEqual(rig.machine.current, CONFIGURED)
        self.assertTrue(rig.machine.absolute)
        self.assertEqual(rig.messages.count(RESTORED), 1)
        self.assertEqual(rig.posts, [])

    def test_a_homing_that_fails_half_way_puts_the_current_back_and_still_stops_the_print(self):
        rig = Rig(positives=[], homed="")
        rig.home_breaks_late = True
        with self.assertRaisesRegex(GcodeError, "homing failed half way"):
            rig.run()
        self.assertEqual(rig.machine.current, CONFIGURED)
        self.assertTrue(rig.machine.absolute)

    def test_a_current_that_cannot_be_put_back_hides_neither_the_error_nor_the_cancel(self):
        rig, m = self.cancelled()
        rig.restore_fails = True
        m.m4050()                                                     # no exception
        self.assertNotIn(RESTORED, rig.messages)
        self.assertIsNone(m._foreign_preflight)
        rig = Rig(positives=[], homed="")
        rig.restore_fails, rig.home_breaks_late = True, True
        with self.assertRaisesRegex(GcodeError, "homing failed half way"):
            rig.run()

    def test_nothing_extra_is_sent_when_the_homing_ends_normally_or_the_print_is_paused(self):
        rig = Rig(positives=[], homed="")
        rig.run()
        self.assertFalse([g for g in self.gcodes(rig) if "SET_TMC_CURRENT" in g])
        rig = Rig(positives=[], homed="", durations={"home": 8.0})
        m = rig.build()
        rig.timers.append((3.0, lambda: m.foreign_preflight_command("PAUSE")))
        m.m4050()
        self.assertEqual(self.gcodes(rig), ["G28 X Y"])               # a pause does not cut the macro
        self.assertEqual(rig.machine.current, CONFIGURED)

REFUSED = "SDCARD_RESET_FILE cannot be run from the sdcard"


class ResetAfterCancelTests(unittest.TestCase):
    """26.11.2026, 19:07 on the printer: after a cancel during "G28 X Y" the screen showed "SDCARD_RESET_FILE cannot be run
    from the sdcard". QIDI's Moonraker sends that command after every cancel; the check had not returned yet, so Klipper
    still counted it as a command from the file and refused the reset."""

    def cancel(self, rig, m, at, reset_after=0.3):
        rig.timers.append((at, lambda: m.foreign_preflight_command("CANCEL_PRINT")))
        rig.timers.append((at + reset_after, lambda: rig.send_reset(m)))

    def quiet(self, rig, m):
        rig.work(m)
        self.assertEqual(rig.errors, [])
        self.assertEqual(len(rig.resets), 1)                          # the file and the print state are reset, as QIDI wants
        self.assertEqual(rig.queue, [])
        self.assertIsNone(m._foreign_preflight)
        self.assertIsNone(m._foreign_check_sd)

    def test_a_cancel_while_x_and_y_home_shows_no_error(self):
        rig = Rig(positives=[], homed="", durations={"home": 8.0})
        m = rig.build()
        self.cancel(rig, m, 3.0)
        self.quiet(rig, m)
        self.assertEqual(rig.machine.current, CONFIGURED)

    def test_a_reset_between_the_cut_homing_and_the_current_going_back_shows_no_error(self):
        rig = Rig(positives=[], homed="", durations={"home": 8.0})
        m = rig.build()
        rig.timers.append((3.0, lambda: m.foreign_preflight_command("CANCEL_PRINT")))
        rig.after_homing = lambda: rig.send_reset(m)
        self.quiet(rig, m)
        self.assertEqual(rig.machine.current, CONFIGURED)

    def test_a_cancel_while_the_camera_settles_shows_no_error(self):
        rig = Rig(positives=[], light=1.0)
        m = rig.build()
        self.cancel(rig, m, 2.1)                                      # both arrive before the check looks again
        self.quiet(rig, m)
        self.assertEqual(rig.posts, [])

    def test_a_cancel_while_the_ai_looks_shows_no_error(self):
        rig = Rig(positives=[], light=1.0)
        m = rig.build()
        self.cancel(rig, m, 10.1, reset_after=0.1)
        self.quiet(rig, m)
        self.assertEqual(rig.posts[-1][1], {"state": False})

    def test_a_cancel_while_the_head_drives_shows_no_error(self):
        rig = Rig(positives=[], homed="xyz", durations={"park": 4.0})
        m = rig.build()
        self.cancel(rig, m, 1.0)
        self.quiet(rig, m)

    def test_a_cancel_while_the_bed_drops_shows_no_error(self):
        rig = Rig(positives=[], homed="", durations={"z": 1.0})
        m = rig.build()
        self.cancel(rig, m, 0.3)
        self.quiet(rig, m)

    def test_a_reset_that_is_itself_the_cancel_still_cancels(self):
        rig = Rig(positives=[], light=1.0)
        m = rig.build()
        rig.timers.append((2.1, lambda: rig.send_reset(m)))          # the user's own reset, the file still open
        rig.timers.append((2.4, lambda: rig.send_reset(m)))          # Moonraker's, after it saw "cancelled"
        self.quiet(rig, m)
        self.assertEqual(rig.posts, [])

    def test_after_the_check_the_command_is_klippers_again(self):
        rig = Rig(positives=[], light=1.0)
        m = rig.build()
        rig.work(m)
        rig.sd.current_file = None
        self.assertFalse(m.foreign_preflight_command("SDCARD_RESET_FILE"))

    def test_a_reset_inside_a_print_file_is_still_refused(self):
        rig = Rig(positives=[], light=1.0)
        m = rig.build()
        rig.work(m)
        rig.sd.cmd_from_sd = True                                     # a line of the file is running
        rig.send_reset(m)
        self.assertEqual(rig.errors, [REFUSED])

    def test_a_found_object_still_lets_the_reset_cancel_the_held_print(self):
        rig = Rig(positives=[9.0], light=1.0)
        m = rig.build()
        rig.work(m)
        self.assertIsNone(m._foreign_check_sd)
        rig.send_reset(m)
        self.assertEqual(rig.errors, [])
        self.assertIsNone(rig.sd.current_file)
        self.assertIsNone(m._foreign_preflight)

    def test_a_check_that_stops_the_print_with_an_error_hands_the_command_back(self):
        rig = Rig(positives=[], homed="", home_fails=True)
        m = rig.build()
        with self.assertRaises(GcodeError):
            rig.work(m)
        self.assertIsNone(m._foreign_check_sd)

class StartKeepsXyTests(unittest.TestCase):
    """Module start-keep-xy: the first homing of a print may keep X and Y only when this check has just homed them itself
    and nobody was asked to do anything since (03.02 agent and owner, 26.11.2026)."""

    def rig(self, stale=0, **kw):
        rig = Rig(**dict({"positives": [], "homed": ""}, **kw))
        rig.xy_fresh = stale
        rig.objects["gcode_macro _TWEAKED_START_HOME"] = object()
        return rig

    def test_a_check_that_homed_x_and_y_itself_lets_the_start_keep_them(self):
        rig = self.rig()
        rig.work(rig.build())
        self.assertIn(NOTHING, rig.messages)
        self.assertEqual(rig.xy_fresh, 1)

    def test_axes_that_were_homed_before_the_check_are_homed_again_by_the_print_start(self):
        for homed in ("xy", "xyz"):                                   # e.g. Home on the screen, or a cancel a minute ago
            rig = self.rig(homed=homed)
            rig.run()
            self.assertEqual(rig.xy_fresh, 0, homed)

    def test_an_old_mark_never_survives_a_new_start(self):
        rig = self.rig(stale=1, homed="xyz")
        rig.run()
        self.assertEqual(rig.xy_fresh, 0)
        rig = self.rig(stale=1)
        m = rig.build()
        m.ai_configs[AIErrorType.FOREIGN]["enabled"] = 0             # check switched off: nothing is homed by it
        m.m4050()
        self.assertEqual(rig.xy_fresh, 0)

    def test_a_found_object_means_the_user_may_touch_the_printer_so_everything_is_homed(self):
        rig = self.rig(positives=[9.0])
        rig.run()
        self.assertIn(FOUND, rig.messages)
        self.assertEqual(rig.xy_fresh, 0)

    def test_an_object_reported_in_the_first_seconds_also_means_full_homing(self):
        rig = self.rig(positives=[2.0])
        rig.run()
        self.assertIn(NOTHING, rig.messages)
        self.assertEqual(rig.xy_fresh, 0)

    def test_a_cancel_or_a_pause_or_a_continue_leaves_no_mark(self):
        for command in ("CANCEL_PRINT", "PAUSE", "RESUME"):
            for second in (3.0, 10.0, 22.0):                          # homing, camera wait, AI window
                rig = self.rig(durations={"home": 8.0})
                m = rig.build()
                rig.timers.append((second, lambda: m.foreign_preflight_command(command)))
                rig.work(m)
                self.assertEqual(rig.xy_fresh, 0, (command, second))

    def test_without_an_answer_of_the_ai_the_mark_is_set_the_print_goes_on_untouched(self):
        rig = self.rig(status=500)
        rig.run()
        self.assertIn(UNAVAILABLE, rig.messages)
        self.assertEqual(rig.xy_fresh, 1)

    def test_a_head_that_could_not_be_parked_leaves_no_mark(self):
        rig = self.rig()
        rig.park_fails = True
        with self.assertRaises(GcodeError):
            rig.run()
        self.assertEqual(rig.xy_fresh, 0)
        rig = self.rig()
        rig.machine.broken.add("set_position_before")
        rig.run()
        self.assertEqual(rig.xy_fresh, 0)

    def test_without_the_module_nothing_is_sent(self):
        rig = Rig(positives=[], homed="")
        rig.run()
        self.assertFalse([s for s in rig.scripts if "START_HOME" in s])
        self.assertIn(NOTHING, rig.messages)

    def test_a_mark_that_cannot_be_written_stops_nothing(self):
        rig = self.rig(light=1.0)
        rig.script_fails = True
        rig.run()
        self.assertIn(NOTHING, rig.messages)


if __name__ == "__main__":
    unittest.main()
