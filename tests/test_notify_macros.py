#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""Phone notifications: the Klipper side (q2_notify.cfg), rendered the way Klipper renders a macro.

The tick (delayed_gcode) is rendered with jinja2 using Klipper's delimiters ({% %} blocks, { } variables) against a
fake `printer` object; the G-code it prints is read back: SET_GCODE_VARIABLE lines update the macro state (like Klipper
does) and RUN_SHELL_COMMAND lines are decoded the way Klipper and gcode_shell_command decode them (two rounds of shlex).
Skipped when jinja2 is not installed (the printer has it; on Windows: pip install jinja2).
"""
import ast
import copy
import re
import shlex
import unittest
from pathlib import Path

try:
    import jinja2
except ImportError:  # pragma: no cover
    jinja2 = None

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "modules" / "phone-notifications" / "files" / "q2_notify.cfg"
TAB = "\t"


def sections(text):
    """{'gcode_macro _X': {'variable_a': '1', 'gcode': '...'}}: Klipper config sections, continuation lines joined."""
    out, cur, key = {}, None, None
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.startswith("#") and not line.startswith(" "):
            continue
        m = re.match(r"^\[(.+)\]\s*$", line)
        if m:
            cur, key = out.setdefault(m.group(1), {}), None
            continue
        if cur is None:
            continue
        if line[:1] in (" ", "\t") and key:
            cur[key] += "\n" + line
            continue
        m = re.match(r"^([A-Za-z0-9_]+)\s*[:=]\s*(.*)$", line)
        if m:
            key = m.group(1)
            cur[key] = m.group(2)
    return out


def dedent(body):
    lines = [l for l in body.split("\n")]
    pad = min((len(l) - len(l.lstrip()) for l in lines[1:] if l.strip()), default=0)
    return "\n".join([lines[0]] + [l[pad:] for l in lines[1:]])


@unittest.skipIf(jinja2 is None, "jinja2 not installed")
class NotifyMacroTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = sections(CFG.read_text(encoding="utf-8"))
        cls.env = jinja2.Environment(block_start_string="{%", block_end_string="%}", variable_start_string="{",
                                     variable_end_string="}", extensions=["jinja2.ext.do"], undefined=jinja2.Undefined)
        cls.tick = cls.env.from_string(dedent(cls.cfg["delayed_gcode _TWEAKED_NOTIFY_TICK"]["gcode"]))
        cls.defaults = {k[len("variable_"):]: ast.literal_eval(v)
                        for k, v in cls.cfg["gcode_macro _TWEAKED_NOTIFY"].items() if k.startswith("variable_")}

    def setUp(self):
        self.state = copy.deepcopy(self.defaults)
        self.printer = {
            "print_stats": {"state": "standby", "filename": "hdd500.gcode", "print_duration": 0,
                            "info": {"current_layer": 0, "total_layer": 100}},
            "display_status": {"progress": 0.0},
            "save_variables": {"variables": {"qdc_ai_error_code": ""}},
            "filament_switch_sensor filament_switch_sensor": {"filament_detected": True},
        }
        self.sent = []   # decoded tsv field lists, one per RUN_SHELL_COMMAND
        self.all_gcode = []

    def run_tick(self):
        self.printer["gcode_macro _TWEAKED_NOTIFY"] = self.state
        text = self.tick.render(printer=self.printer)
        for line in [l.strip() for l in text.split("\n") if l.strip()]:
            self.all_gcode.append(line)
            if line.startswith("SET_GCODE_VARIABLE MACRO=_TWEAKED_NOTIFY"):
                p = dict(a.split("=", 1) for a in shlex.split(line)[1:])
                self.state[p["VARIABLE"]] = ast.literal_eval(p["VALUE"])
            elif line.startswith("RUN_SHELL_COMMAND"):
                p = dict(a.split("=", 1) for a in shlex.split(line)[1:])        # Klipper's own parsing of the line
                self.assertEqual(p["CMD"], "q2_notify")
                args = shlex.split(p["PARAMS"])                                    # gcode_shell_command's parsing
                self.assertEqual(args[0], "--tsv")
                self.assertEqual(len(args), 2, line)
                self.sent.append(args[1].split(TAB))
        return text

    def pause(self, **kw):
        self.printer["print_stats"].update(state="paused", info={"current_layer": 12, "total_layer": 100}, **kw)

    def test_pause_reason_each_of_five(self):
        cases = [
            ("AI spaghetti", lambda: self.printer["save_variables"]["variables"].update(
                qdc_ai_error_code="noodle=1 status=1 time=1763600000")),
            ("AI foreign object", lambda: self.printer["save_variables"]["variables"].update(
                qdc_ai_error_code="foreign=1 status=1 time=1763600000")),
            ("filament runout", lambda: self.printer["filament_switch_sensor filament_switch_sensor"].update(
                filament_detected=False)),
            ("M0/M25 in G-code", lambda: self.state.update(reason="M0")),
            ("manual", lambda: None),
        ]
        for expected, arrange in cases:
            with self.subTest(expected):
                self.setUp()
                arrange()
                self.pause()
                self.run_tick()
                self.assertEqual(len(self.sent), 1)
                self.assertEqual(self.sent[0][0], "Print paused: " + expected)

    def test_pause_message_has_picture_and_buttons_and_high_priority(self):
        self.pause()
        self.run_tick()
        f = self.sent[0]
        self.assertEqual(f[1], "hdd500.gcode\\nLayer 12/100")        # \n as two characters: the sender converts it
        self.assertEqual(f[2], "5")
        self.assertEqual(f[5], "http://127.0.0.1/webcam/?action=snapshot")
        self.assertEqual(f[6:9], ["Resume=resume", "Cancel=cancel"])

    def test_pause_sent_once_and_again_after_resume(self):
        self.pause()
        for _ in range(3):
            self.run_tick()
        self.assertEqual(len(self.sent), 1)
        self.printer["print_stats"]["state"] = "printing"
        self.run_tick()
        self.assertEqual(self.state["paused_sent"], 0)
        self.pause()
        self.run_tick()
        self.assertEqual(len(self.sent), 2)

    def test_pause_does_not_touch_heaters(self):
        for state in ("printing", "paused", "complete", "standby"):
            self.printer["print_stats"]["state"] = state
            self.run_tick()
        text = "\n".join(self.all_gcode)
        for forbidden in ("M104", "M109", "M140", "M190", "M141", "M191", "SET_HEATER_TEMPERATURE", "TEMPERATURE_WAIT"):
            self.assertNotIn(forbidden, text)

    def test_stale_ai_code_from_an_earlier_print_is_not_reported(self):
        self.printer["save_variables"]["variables"]["qdc_ai_error_code"] = "noodle=1 status=1 time=1"
        self.run_tick()                       # standby: the old code is taken as seen
        self.pause()
        self.run_tick()
        self.assertEqual(self.sent[0][0], "Print paused: manual")

    def test_reason_is_used_once(self):
        self.state["reason"] = "M25"
        self.pause()
        self.run_tick()
        self.assertEqual(self.sent[0][0], "Print paused: M0/M25 in G-code")
        self.assertEqual(self.state["reason"], "")

    def test_nasty_file_name_stays_one_argument(self):
        self.pause(filename='Wieża 12mm "v2" | a\\b #1; x*y\'s.gcode.3mf')
        self.run_tick()
        self.assertEqual(len(self.sent), 1)
        self.assertTrue(self.sent[0][1].startswith("Wieża 12mm v2 | ab 1 xys"), self.sent[0][1])
        for line in self.all_gcode:
            if line.startswith("RUN_SHELL_COMMAND"):
                self.assertFalse(re.search(r"[#;*]", line), line)   # Klipper would cut the line there

    def test_tick_reschedules_itself(self):
        text = self.run_tick()
        self.assertIn("UPDATE_DELAYED_GCODE ID=_TWEAKED_NOTIFY_TICK DURATION=15", text)

    def test_sender_is_a_shell_command_and_tick_starts_after_boot(self):
        self.assertEqual(self.cfg["gcode_shell_command q2_notify"]["command"], "sh /home/qidi/q2-notify/q2_notify_send.sh")
        self.assertEqual(self.cfg["delayed_gcode _TWEAKED_NOTIFY_TICK"]["initial_duration"], "15")


if __name__ == "__main__":
    unittest.main()
