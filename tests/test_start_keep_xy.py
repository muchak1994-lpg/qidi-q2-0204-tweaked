#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""start-keep-xy: the first homing of a print does not home X and Y again when they are already homed.

The two edits are taken from the module (QIDI's file is never needed): the homing part is rendered with jinja2 using
Klipper's delimiters, once as QIDI wrote it and once as the module writes it, and the G-code lines are compared.
The rendering tests are skipped when jinja2 is not installed (the printer has it; on Windows: pip install jinja2).
"""
import json
import re
import unittest
from pathlib import Path

try:
    import jinja2
except ImportError:  # pragma: no cover
    jinja2 = None

ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / "modules" / "start-keep-xy" / "module.json"
TARGET = "/home/qidi/printer_data/config/klipper-macros-qd/gcode_macro.cfg"
KEYWORD = "TWEAKED_KEEP_XY"
XY_LINES = ["SET_KINEMATIC_POSITION X=100", "SET_KINEMATIC_POSITION Y=100", "_HOME_XY"]
Z_ONLY = ["SET_KINEMATIC_POSITION Z=132.5", "G91", "G1 Z5 F600", "G4 P2000", "G90"]
MACRO = "_TWEAKED_START_HOME"
USED = "SET_GCODE_VARIABLE MACRO=_TWEAKED_START_HOME VARIABLE=xy_fresh VALUE=0"


def module():
    return json.loads(MODULE.read_text(encoding="utf-8"))


def edit(marker):
    found = [(old, new) for old, new in module()["files"][TARGET]["edits"] if marker in old]
    assert len(found) == 1, marker
    return found[0]


def klipper_params(line):
    """Klipper's reading of a G-code line (gcode.py, _process_commands): the words become parameter names."""
    parts = re.split("([A-Z_]+|[A-Z*/])", line.upper())
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts), 2)}


def render(text, **context):
    env = jinja2.Environment(block_start_string="{%", block_end_string="%}", variable_start_string="{",
                             variable_end_string="}")
    out = env.from_string(text).render(**context)
    return [line.strip() for line in out.split("\n") if line.strip() and not line.strip().startswith("#")]


def commands(text, homed, params, fresh=1, saved=None):
    printer = {"toolhead": {"homed_axes": homed, "axis_maximum": {"z": 265}}, "gcode_macro " + MACRO: {"xy_fresh": fresh},
               "save_variables": {"variables": saved or {}}}
    return render(text + "{% endif %}", printer=printer, params=params)


class MacroError(Exception):
    pass


def switch(params, saved=None):
    """The G-code of the user macro TWEAKED_START_XY."""
    new = edit("[homing_override]")[1]
    body = new.split("[gcode_macro TWEAKED_START_XY]\n")[1].split("gcode:\n")[1].split("\n[homing_override]")[0]
    body = body.split("\n[")[0]

    def stop(message):
        raise MacroError(message)

    return render(body, params=params, action_raise_error=stop, printer={"save_variables": {"variables": saved or {}}})


class ModuleTests(unittest.TestCase):
    def test_the_module_is_optional(self):
        self.assertIs(module()["default"], False)

    def test_only_the_first_homing_of_a_print_asks_to_keep_x_and_y(self):
        old, new = edit("SUB_STATUS=tool_head_reset")
        old_lines, new_lines = old.split("\n"), new.split("\n")
        self.assertEqual(len(old_lines), len(new_lines))
        changed = [(a, b) for a, b in zip(old_lines, new_lines) if a != b]
        self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0][0].strip(), "G28")
        self.assertEqual(changed[0][1].split("#")[0].strip(), "G28 " + KEYWORD)
        self.assertNotIn(";", changed[0][1])

    def test_the_mark_is_a_hidden_macro_that_starts_empty(self):
        old, new = edit("[homing_override]")
        self.assertTrue(new.endswith(old))
        self.assertIn("[gcode_macro " + MACRO + "]\nvariable_xy_fresh: 0\ngcode:\n    ", new)

    def test_klipper_reads_the_new_line_as_a_homing_of_all_axes(self):
        params = klipper_params("G28 " + KEYWORD)
        self.assertIn(KEYWORD, params)
        self.assertFalse([axis for axis in "XYZ" if axis in params])   # so homing_override runs its Home All part


@unittest.skipIf(jinja2 is None, "jinja2 not installed")
class HomingTests(unittest.TestCase):
    def setUp(self):
        self.old, self.new = edit("_HOME_XY")
        self.asked = klipper_params("G28 " + KEYWORD)
        self.plain = klipper_params("G28")

    def test_with_x_and_y_just_homed_by_the_check_only_the_z_part_is_left(self):
        for homed in ("xy", "xyz"):
            got = commands(self.new, homed, self.asked)
            self.assertEqual(got, [USED] + Z_ONLY, homed)
            self.assertEqual(got[1:], [c for c in commands(self.old, homed, self.asked) if c not in XY_LINES], homed)

    def test_x_and_y_homed_by_anything_else_are_homed_again(self):
        for homed in ("xy", "xyz"):
            got = commands(self.new, homed, self.asked, fresh=0)
            self.assertEqual(got, [USED] + commands(self.old, homed, self.asked), homed)

    def test_with_x_or_y_not_homed_it_is_the_homing_of_qidi(self):
        for homed in ("", "x", "y", "z", "xz", "yz"):
            got = commands(self.new, homed, self.asked)
            self.assertEqual(got, [USED] + commands(self.old, homed, self.asked), homed)
            self.assertTrue(all(c in got for c in XY_LINES), homed)

    def test_home_all_from_the_screen_or_fluidd_always_homes_everything(self):
        for homed in ("", "xy", "xyz"):
            got = commands(self.new, homed, self.plain)
            self.assertEqual(got, commands(self.old, homed, self.plain), homed)
            self.assertTrue(all(c in got for c in XY_LINES), homed)

@unittest.skipIf(jinja2 is None, "jinja2 not installed")
class AnyHomingTests(unittest.TestCase):
    """The wider mode the owner asked about on 27.11.2026: X and Y homed by anything are kept (chosen with a command)."""

    ANY = {"q2_start_keep_any": 1}

    def setUp(self):
        self.old, self.new = edit("_HOME_XY")
        self.asked = klipper_params("G28 " + KEYWORD)

    def test_x_and_y_homed_by_anything_are_kept(self):
        for homed in ("xy", "xyz"):
            self.assertEqual(commands(self.new, homed, self.asked, fresh=0, saved=self.ANY), [USED] + Z_ONLY, homed)

    def test_axes_that_are_not_homed_are_homed(self):
        for homed in ("", "x", "y", "yz"):
            got = commands(self.new, homed, self.asked, fresh=0, saved=self.ANY)
            self.assertTrue(all(c in got for c in XY_LINES), homed)

    def test_home_all_still_homes_everything(self):
        got = commands(self.new, "xyz", klipper_params("G28"), fresh=0, saved=self.ANY)
        self.assertTrue(all(c in got for c in XY_LINES))

    def test_the_careful_mode_is_the_default(self):
        for saved in ({}, {"q2_start_keep_any": 0}):
            got = commands(self.new, "xyz", self.asked, fresh=0, saved=saved)
            self.assertTrue(all(c in got for c in XY_LINES), saved)

    def test_the_command_chooses_and_remembers_the_mode(self):
        self.assertIn("SAVE_VARIABLE VARIABLE=q2_start_keep_any VALUE=1", switch({"MODE": "ANY"}))
        self.assertIn("SAVE_VARIABLE VARIABLE=q2_start_keep_any VALUE=0", switch({"MODE": "check"}, self.ANY))

    def test_the_command_without_a_mode_only_says_which_one_is_on(self):
        for saved, name in (({}, "CHECK"), (self.ANY, "ANY")):
            got = switch({}, saved)
            self.assertEqual(len(got), 1, got)
            self.assertTrue(got[0].startswith("M118 ") and name in got[0], got)

    def test_a_wrong_mode_changes_nothing(self):
        with self.assertRaises(MacroError):
            switch({"MODE": "ALL"})


if __name__ == "__main__":
    unittest.main()
