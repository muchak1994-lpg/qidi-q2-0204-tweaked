#!/usr/bin/env python3
"""print-cache-protection: which print-start file names are taken (QIDI's screen sends full paths).

Run:  python tests/test_print_start_path.py
"""
import ast
import json
import os
import unittest
from pathlib import Path
from typing import Optional

MODULE = Path(__file__).resolve().parent.parent / "modules/print-cache-protection/module.json"
_source = next(iter(json.loads(MODULE.read_text())["files"].values()))["edits"][0][1]
_tree = ast.parse(_source)
_func = next(n for n in _tree.body if isinstance(n, ast.FunctionDef) and n.name == "_q2_print_location")
_ns = {"os": os, "Optional": Optional}
exec(compile(ast.Module(body=[_func], type_ignores=[]), str(MODULE), "exec"), _ns)
location = _ns["_q2_print_location"]

BASE = "/home/qidi/printer_data"


class PrintStartPath(unittest.TestCase):
    def test_relative_gcode_file(self):  # Orca, Fluidd, the screen's file list
        self.assertEqual(location("clip.gcode.3mf", BASE), "clip.gcode.3mf")
        self.assertEqual(location("sub/clip.gcode", BASE), "sub/clip.gcode")
        self.assertEqual(location("USB/clip.gcode", BASE), "USB/clip.gcode")

    def test_full_path_in_print_cache(self):  # the screen's "recently printed" entry
        self.assertEqual(location(BASE + "/.cache/clip.gcode.3mf", BASE), ".cache/clip.gcode.3mf")

    def test_full_path_in_gcodes(self):  # e.g. the screen's USB tab
        self.assertEqual(location(BASE + "/gcodes/USB/clip.gcode", BASE), "USB/clip.gcode")
        self.assertEqual(location(BASE + "/gcodes/clip.gcode.3mf", BASE), "clip.gcode.3mf")

    def test_relative_cache_path(self):  # QIDI's own ".cache/..." form
        self.assertEqual(location(".cache/clip.gcode.3mf", BASE), ".cache/clip.gcode.3mf")

    def test_outside_refused(self):
        for bad in ("/etc/passwd", "../config/printer.cfg", BASE + "/config/printer.cfg",
                    BASE + "/gcodes/../config/printer.cfg", ".cache/../config/printer.cfg",
                    BASE + "/gcodes", BASE + "/.cache", BASE + "/gcodesX/a.gcode",
                    BASE + "/.cache2/a.gcode", "/home/qidi/a.gcode"):
            self.assertIsNone(location(bad, BASE), bad)

    def test_screen_recently_printed_entry(self):  # what the screen sent on the printer, 13.11.2026
        self.assertEqual(location("/.cache/clip.gcode.3mf", BASE, False), ".cache/clip.gcode.3mf")

    def test_no_copy_takes_the_cache_name(self):  # Klipper prints .cache/<name> (QIDI's code)
        self.assertEqual(location("/root/printer_data/.cache/clip.gcode.3mf", BASE, False),
                         ".cache/clip.gcode.3mf")
        self.assertIsNone(location("/root/printer_data/.cache/clip.gcode.3mf", BASE, True))
        self.assertIsNone(location("/root/printer_data/.cache/", BASE, False))

    def test_linked_home(self):  # /home/mks -> /home/qidi on the printer
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            real = os.path.join(tmp, "qidi")
            os.makedirs(os.path.join(real, "printer_data", ".cache"))
            os.makedirs(os.path.join(real, "printer_data", "gcodes"))
            os.symlink(real, os.path.join(tmp, "mks"))
            base = os.path.join(real, "printer_data")
            self.assertEqual(location(os.path.join(tmp, "mks/printer_data/.cache/a.gcode"), base),
                             ".cache/a.gcode")
            self.assertEqual(location(os.path.join(tmp, "mks/printer_data/gcodes/a.gcode"), base),
                             "a.gcode")
            self.assertIsNone(location(os.path.join(tmp, "mks/printer_data/config/a.cfg"), base))

    def test_dot_dot_that_stays_inside(self):
        self.assertEqual(location("sub/../clip.gcode", BASE), "clip.gcode")


if __name__ == "__main__":
    unittest.main()
