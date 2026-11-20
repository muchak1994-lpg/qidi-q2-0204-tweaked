#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic)
"""Every G-code command and macro the modules add must reach its own handler in Klipper.

Klipper reads a command like "Q2_ADAPTIVE_MESH" as the traditional G-code "Q2" (a letter and a
number), and QIDI's Klipper drops unknown commands without a message - the command silently does
nothing. This test runs every command name from the modules through the same parsing as QIDI's
klippy/gcode.py.

Run:  python tests/test_command_names.py
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARGS_R = re.compile('([A-Z_]+|[A-Z*/])')  # klippy/gcode.py (QIDI 02.04), GCodeDispatch.args_r

# Macros only used as variable stores (SET_GCODE_VARIABLE / printer['gcode_macro ...']), never run
# as a command. Anything added here must really never be called.
VARIABLES_ONLY = {"_Q2_DRY_IDLE"}


def klipper_command(line):
    """The handler name Klipper looks up for a line (GCodeDispatch._process_commands)."""
    parts = ARGS_R.split(line.upper())
    if len(parts) >= 3 and parts[1] != 'N':
        return parts[1] + parts[2].strip()
    if len(parts) >= 5 and parts[1] == 'N':
        return parts[3] + parts[4].strip()
    return ""


def module_names():
    """(name, where) for every command a module registers or every macro it defines."""
    found = []
    for path in sorted((ROOT / "modules").rglob("*")):
        if path.suffix not in (".py", ".cfg", ".json") or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix == ".json":
            try:  # config edits live inside module.json as strings
                text = "\n".join(json.dumps(json.loads(text)).encode().decode("unicode_escape").splitlines())
            except ValueError:
                pass
        for m in re.finditer(r"register_command\(\s*['\"]([A-Za-z0-9_]+)['\"]", text):
            found.append((m.group(1), path.relative_to(ROOT)))
        for m in re.finditer(r"\[gcode_macro\s+([A-Za-z0-9_]+)\s*\]", text):
            found.append((m.group(1), path.relative_to(ROOT)))
    return found


class CommandNamesTest(unittest.TestCase):
    def test_parser_matches_klipper(self):
        self.assertEqual(klipper_command("Q2_ADAPTIVE_MESH PROFILE=kamp"), "Q2")  # the bug
        self.assertEqual(klipper_command("TWEAKED_ADAPTIVE_MESH PROFILE=kamp"), "TWEAKED_ADAPTIVE_MESH")
        self.assertEqual(klipper_command("G1 X10"), "G1")
        self.assertEqual(klipper_command("M118 hello"), "M118")

    def test_every_module_command_reaches_its_handler(self):
        names = module_names()
        self.assertTrue(any(n == "TWEAKED_THR_CHECK" for n, _ in names))
        bad = []
        for name, where in names:
            if name in VARIABLES_ONLY:
                continue
            if klipper_command(name + " X=1") != name.upper():
                bad.append("%s (%s) is read by Klipper as %r" % (name, where, klipper_command(name)))
        self.assertEqual(bad, [], "\n".join(bad))

    def test_variable_only_macros_are_never_run(self):
        for name in VARIABLES_ONLY:
            for path in (ROOT / "modules").rglob("*.cfg"):
                for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                    code = line.split("#", 1)[0].strip()
                    self.assertFalse(code.upper().startswith(name.upper() + " ") or code.upper() == name.upper(),
                                     "%s is run as a command in %s" % (name, path))


if __name__ == "__main__":
    unittest.main(verbosity=2)
