#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""Maintenance reminders (q2_maint.cfg), rendered the way Klipper renders macros (jinja2, Klipper's delimiters).

A tiny fake Klipper runs the G-code the macros print: SET_GCODE_VARIABLE / SAVE_VARIABLE change state, macro calls are
rendered in turn, the delayed reminders are collected and run on request, RESPOND and RUN_SHELL_COMMAND are recorded.
Skipped when jinja2 is not installed.
"""
import ast
import shlex
import sys
import unittest
from pathlib import Path

try:
    import jinja2
except ImportError:  # pragma: no cover
    jinja2 = None

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_notify_macros import sections, dedent  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "modules" / "maintenance-reminders" / "files" / "q2_maint.cfg"
H = 3600


@unittest.skipIf(jinja2 is None, "jinja2 not installed")
class MaintenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = sections(CFG.read_text(encoding="utf-8"))
        cls.env = jinja2.Environment(block_start_string="{%", block_end_string="%}", variable_start_string="{",
                                     variable_end_string="}", extensions=["jinja2.ext.do"], undefined=jinja2.Undefined)
        cls.defaults = {k[len("variable_"):]: ast.literal_eval(v)
                        for k, v in cls.cfg["gcode_macro _TWEAKED_MAINT"].items() if k.startswith("variable_")}

    def setUp(self):
        self.macro = dict(self.defaults)
        self.vars = {}                      # saved_variables
        self.stats = {"state": "standby", "print_duration": 0.0}
        self.notify = True                  # is the phone-notifications macro there?
        self.responds, self.shells = [], []
        self.scheduled = {}                 # delayed reminder -> seconds

    def printer(self):
        p = {"print_stats": self.stats, "gcode_macro _TWEAKED_MAINT": self.macro, "save_variables": {"variables": self.vars}}
        if self.notify:
            p["gcode_macro _TWEAKED_NOTIFY"] = {}
        return p

    def render(self, name, **params):
        text = self.env.from_string(dedent(self.cfg[name]["gcode"])).render(printer=self.printer(), params=params)
        for line in [l.strip() for l in text.split("\n") if l.strip()]:
            self.execute(line)

    def execute(self, line):
        word = line.split()[0]
        if word in ("SET_GCODE_VARIABLE", "SAVE_VARIABLE"):
            p = dict(a.split("=", 1) for a in shlex.split(line)[1:])
            if word == "SAVE_VARIABLE":
                self.vars[p["VARIABLE"].lower()] = ast.literal_eval(p["VALUE"])
            else:
                self.macro[p["VARIABLE"]] = ast.literal_eval(p["VALUE"])
        elif word == "UPDATE_DELAYED_GCODE":
            p = dict(a.split("=", 1) for a in shlex.split(line)[1:])
            if p["ID"] != "_TWEAKED_MAINT_TICK":
                self.scheduled[p["ID"]] = int(p["DURATION"])
        elif word == "RESPOND":
            self.responds.append(line)
        elif word == "RUN_SHELL_COMMAND":
            p = dict(a.split("=", 1) for a in shlex.split(line)[1:])
            self.assertEqual(p["CMD"], "q2_notify")
            args = shlex.split(p["PARAMS"])
            self.assertEqual(len(args), 2, line)
            self.shells.append(args[1].split("\t"))
        elif word == "_TWEAKED_MAINT_FINISH":
            self.render("gcode_macro _TWEAKED_MAINT_FINISH")
        elif word == "M118":
            pass
        else:
            self.fail("unexpected G-code: " + line)

    def tick(self):
        self.render("delayed_gcode _TWEAKED_MAINT_TICK")

    def print_for(self, seconds, end="complete"):
        self.stats.update(state="printing", print_duration=float(seconds))
        self.tick()
        self.stats["state"] = end
        self.tick()

    def fire(self):
        """Let the scheduled reminders run (in the order of their delays) and forget them."""
        for name in sorted(self.scheduled, key=self.scheduled.get):
            self.render("delayed_gcode " + name)
        self.scheduled = {}

    def test_a_finished_print_adds_its_time(self):
        self.print_for(2 * H)
        self.print_for(30 * 60, end="cancelled")
        self.assertEqual(self.vars["q2_maint_total"], 2 * H + 1800)

    def test_nothing_is_counted_while_the_print_runs_or_at_restart(self):
        self.stats.update(state="printing", print_duration=5000.0)
        self.tick()
        self.tick()
        self.assertNotIn("q2_maint_total", self.vars)

    def test_no_reminder_below_100_hours(self):
        self.print_for(99 * H)
        self.assertEqual(self.scheduled, {})

    def test_at_100_hours_only_the_rails_window_and_a_phone_message_without_buttons(self):
        self.print_for(100 * H)
        self.assertEqual(list(self.scheduled), ["_TWEAKED_MAINT_REMIND_SHORT"])
        self.fire()
        self.assertEqual(len(self.responds), 1)
        self.assertIn("X/Y rails", self.responds[0])
        self.assertIn("100 h", self.responds[0])
        self.assertNotIn("fans", self.responds[0])
        (msg,) = self.shells
        self.assertEqual(msg[0], "Maintenance: X/Y rails")
        self.assertEqual(msg[6:9], ["", "", ""])                      # no buttons

    def test_at_300_hours_both_reminders_come_as_two_separate_windows_and_messages(self):
        self.print_for(300 * H)
        self.fire()
        self.assertEqual(len(self.responds), 2)
        self.assertIn("X/Y rails", self.responds[0])
        self.assertIn("Z screws and dust the fans", self.responds[1])
        self.assertIn("300 h", self.responds[1])
        self.assertEqual([m[0] for m in self.shells], ["Maintenance: X/Y rails", "Maintenance: Z screws and fans"])
        self.assertTrue(all(m[6:9] == ["", "", ""] for m in self.shells))

    def test_the_second_window_comes_after_the_first(self):
        self.print_for(300 * H)
        self.assertLess(self.scheduled["_TWEAKED_MAINT_REMIND_SHORT"], self.scheduled["_TWEAKED_MAINT_REMIND_LONG"])

    def test_a_reminder_comes_once_per_interval_not_after_every_print(self):
        self.print_for(100 * H)
        self.fire()
        self.print_for(1 * H)                                     # 101 h: no new reminder
        self.assertEqual(self.scheduled, {})
        self.print_for(99 * H)                                    # 200 h: the next one
        self.assertEqual(list(self.scheduled), ["_TWEAKED_MAINT_REMIND_SHORT"])

    def test_one_long_print_over_several_intervals_gives_one_reminder(self):
        self.print_for(250 * H)
        self.fire()
        self.assertEqual(len(self.responds), 1)

    def test_no_window_while_a_new_print_has_started(self):
        self.print_for(100 * H)
        self.stats["state"] = "printing"
        self.fire()
        self.assertEqual(self.responds, [])

    def test_works_without_the_phone_module(self):
        self.notify = False
        self.print_for(100 * H)
        self.fire()
        self.assertEqual(len(self.responds), 1)
        self.assertEqual(self.shells, [])

    def test_status_says_when_the_next_reminders_come(self):
        self.print_for(130 * H)
        self.responds.clear()
        self.render("gcode_macro TWEAKED_MAINT_STATUS")
        text = "\n".join(self.responds)
        self.assertIn("printed 130.0 h", text)
        self.assertIn("rails: next reminder in 70.0 h", text)
        self.assertIn("fans: next reminder in 170.0 h", text)


if __name__ == "__main__":
    unittest.main()
