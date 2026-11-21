#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""Maintenance reminders (q2_maint.cfg), rendered the way Klipper renders macros (jinja2, Klipper's delimiters).

A tiny fake Klipper runs the G-code the macros print: SET_GCODE_VARIABLE / SAVE_VARIABLE change state, macro calls are
rendered in turn, UPDATE_DELAYED_GCODE for the reminder is collected, RESPOND and RUN_SHELL_COMMAND are recorded.
Skipped when jinja2 is not installed.
"""
import ast
import re
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
        self.reminds = 0

    def printer(self):
        p = {"print_stats": self.stats, "gcode_macro _TWEAKED_MAINT": self.macro, "save_variables": {"variables": self.vars}}
        if self.notify:
            p["gcode_macro _TWEAKED_NOTIFY"] = {}
        return p

    def render(self, name, key="gcode", **params):
        tpl = self.env.from_string(dedent(self.cfg[name][key]))
        text = tpl.render(printer=self.printer(), params=params)
        for line in [l.strip() for l in text.split("\n") if l.strip()]:
            self.execute(line)

    def execute(self, line):
        word = line.split()[0]
        if word == "SET_GCODE_VARIABLE":
            p = dict(a.split("=", 1) for a in shlex.split(line)[1:])
            self.macro[p["VARIABLE"]] = ast.literal_eval(p["VALUE"])
        elif word == "SAVE_VARIABLE":
            p = dict(a.split("=", 1) for a in shlex.split(line)[1:])
            self.vars[p["VARIABLE"].lower()] = ast.literal_eval(p["VALUE"])
        elif word == "UPDATE_DELAYED_GCODE":
            if "_TWEAKED_MAINT_REMIND" in line:
                self.reminds += 1
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
        elif word in ("M118",):
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

    def done(self, task):
        self.render("gcode_macro TWEAKED_MAINT_DONE", TASK=task)

    def remind(self):
        self.render("delayed_gcode _TWEAKED_MAINT_REMIND")

    def test_a_finished_print_adds_its_time(self):
        self.print_for(2 * H)
        self.print_for(30 * 60, end="cancelled")
        self.assertEqual(self.vars["q2_maint_total"], 2 * H + 1800)

    def test_nothing_is_counted_while_the_print_runs_or_at_restart(self):
        self.stats.update(state="printing", print_duration=5000.0)
        self.tick()
        self.assertNotIn("q2_maint_total", self.vars)
        self.tick()
        self.assertNotIn("q2_maint_total", self.vars)

    def test_no_reminder_below_every_interval(self):
        self.print_for(99 * H)
        self.assertEqual(self.reminds, 0)

    def test_the_rails_are_due_at_100_hours_and_the_others_are_not(self):
        self.print_for(100 * H)
        self.assertEqual(self.reminds, 1)
        self.remind()
        self.assertEqual(len(self.responds), 1)
        self.assertIn("X/Y linear rails", self.responds[0])
        self.assertNotIn("Z lead screws", self.responds[0])
        self.assertNotIn("fans", self.responds[0])
        self.assertEqual(self.shells[0][6], "X/Y rails done=maintdone rails")
        self.assertEqual(self.shells[0][7:], ["", ""])

    def test_all_three_due_at_300_hours(self):
        self.print_for(300 * H)
        self.remind()
        for part in ("X/Y linear rails", "Z lead screws", "fans"):
            self.assertIn(part, self.responds[0])
        self.assertEqual(self.shells[0][6:], ["X/Y rails done=maintdone rails", "Z screws done=maintdone zscrews",
                                             "Fans done=maintdone fans"])

    def test_done_resets_only_that_task_and_the_reminder_stops(self):
        self.print_for(100 * H)
        self.done("rails")
        self.assertEqual(self.vars["q2_maint_rails_at"], 100 * H)
        self.assertNotIn("q2_maint_zscrews_at", self.vars)
        self.responds.clear()
        self.print_for(10 * H)                                 # 10 h after the service: not due again
        self.assertEqual(self.reminds, 1)
        self.print_for(90 * H)                                 # 100 h after it: due again
        self.assertEqual(self.reminds, 2)

    def test_it_reminds_again_after_every_print_until_done(self):
        self.print_for(100 * H)
        self.print_for(1 * H)
        self.assertEqual(self.reminds, 2)

    def test_done_all_and_unknown_task(self):
        self.print_for(300 * H)
        self.done("all")
        self.assertEqual([self.vars[k] for k in ("q2_maint_rails_at", "q2_maint_zscrews_at", "q2_maint_fans_at")],
                         [300 * H] * 3)
        self.responds.clear()
        self.done("bogus")
        self.assertIn("TYPE=error", self.responds[0])

    def test_no_reminder_window_while_a_new_print_has_started(self):
        self.print_for(100 * H)
        self.stats["state"] = "printing"
        self.remind()
        self.assertEqual(self.responds, [])

    def test_works_without_the_phone_module(self):
        self.notify = False
        self.print_for(100 * H)
        self.remind()
        self.assertEqual(len(self.responds), 1)
        self.assertEqual(self.shells, [])

    def test_status_lists_the_hours(self):
        self.print_for(50 * H)
        self.responds.clear()
        self.render("gcode_macro TWEAKED_MAINT_STATUS")
        text = "\n".join(self.responds)
        self.assertIn("50.0 of 100 h", text)
        self.assertIn("50.0 of 300 h", text)


if __name__ == "__main__":
    unittest.main()
