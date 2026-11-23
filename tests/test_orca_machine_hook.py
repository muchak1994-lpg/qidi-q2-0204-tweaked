#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""The printer profiles set the chamber fan from the filament type (before_layer_change_gcode).

Run:  python tests/test_orca_machine_hook.py
"""
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import orca_machine_hook as hook  # noqa: E402


class MachineHookTest(unittest.TestCase):
    def test_every_printer_profile_carries_the_generated_hook(self):
        files = sorted((REPO / "orca-profiles" / "machine").glob("*.json"))
        self.assertEqual(len(files), 4)
        for path in files:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["before_layer_change_gcode"], hook.machine_fan_gcode(), path.name)

    def test_hook_values(self):
        g = hook.machine_fan_gcode()
        self.assertEqual(g.count("{if layer_num == 0}"), 1)  # once, before the first layer
        for fan, ftype in ((255, "PLA"), (191, "PETG"), (64, "PA")):
            block = g.split("M106 P3 S%d" % fan)[0].rsplit("{", 1)[1]
            self.assertIn('"%s"' % ftype, block)
        for ftype in ("ABS", "ASA", "PC"):  # these heat the chamber: no fan line
            self.assertNotIn('"%s"' % ftype, g)

    def test_no_filament_profiles_are_shipped(self):
        self.assertFalse((REPO / "orca-profiles" / "filament").exists())


if __name__ == "__main__":
    unittest.main()
