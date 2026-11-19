#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""Offline tests for tools/orca_filaments.py and the generated orca-profiles/filament/ (no OrcaSlicer needed).

Run:  python tests/test_orca_filaments.py
"""
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import orca_filaments as of  # noqa: E402


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class GeneratedFilesTest(unittest.TestCase):
    """The files in the repository match the index and the fan table."""

    def setUp(self):
        index = (of.OUT / of.INDEX_NAME).read_text(encoding="utf-8").splitlines()
        self.rows = [line.split("\t") for line in index if line and not line.startswith("#")]

    def test_index_and_files_agree(self):
        listed = {row[0] for row in self.rows}
        on_disk = {p.relative_to(of.OUT).as_posix() for p in of.OUT.rglob("*.json")}
        self.assertTrue(listed)
        self.assertEqual(listed, on_disk)

    def test_every_preset(self):
        names = set()
        for rel, inherits, ftype, fan, after in self.rows:
            data = json.loads((of.OUT / rel).read_text(encoding="utf-8"))
            self.assertEqual(int(fan), of.FAN[ftype], rel)
            self.assertEqual(int(after), of.AFTER_PRINT, rel)
            self.assertEqual(data, of.preset({"name": data["name"], "inherits": inherits, "fan": int(fan)}), rel)
            self.assertEqual(Path(rel).name, of.file_name(data["name"]) + ".json")
            self.assertTrue(data["name"].endswith(of.SUFFIX))
            self.assertNotIn(data["name"], names)
            names.add(data["name"])
            self.assertTrue(set(Path(rel).name).isdisjoint(of.BAD_FILENAME_CHARS), rel)

    def test_owner_decision(self):
        # 2026-11-19: PLA family 100, PETG 75, TPU 100, PA 25, ABS/ASA/PC 0; after the print 0.
        for ftype, speed in (("PLA", 100), ("PLA-CF", 100), ("PETG", 75), ("TPU", 100), ("PA", 25),
                             ("PA-CF", 25), ("ABS", 0), ("ASA", 0), ("PC", 0)):
            self.assertEqual(of.FAN[ftype], speed, ftype)
        self.assertEqual(of.AFTER_PRINT, 0)

    def test_owner_filaments_are_there(self):
        inherits = {row[1] for row in self.rows}
        for name in ("SUNLU PLA+ 2.0 @System", "eSUN PLA+ @System", "SUNLU PETG @System"):
            self.assertIn(name, inherits)


class PlanTest(unittest.TestCase):
    """plan() on a small made-up library."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        lib = self.tmp / "filament"
        write_json(lib / "base" / "fdm_filament_pla.json",
                   {"name": "fdm_filament_pla", "instantiation": "false", "filament_type": ["PLA"]})
        write_json(lib / "base" / "fdm_filament_pp.json",
                   {"name": "fdm_filament_pp", "instantiation": "false", "filament_type": ["PP"]})
        write_json(lib / "Brand" / "Brand PLA @base.json",
                   {"name": "Brand PLA @base", "inherits": "fdm_filament_pla", "instantiation": "false"})
        write_json(lib / "Brand" / "Brand PLA @System.json",
                   {"name": "Brand PLA @System", "inherits": "Brand PLA @base", "instantiation": "true",
                    "compatible_printers": []})
        write_json(lib / "Brand" / "Brand PLA @BBL A1.json",
                   {"name": "Brand PLA @BBL A1", "inherits": "Brand PLA @base", "instantiation": "true",
                    "compatible_printers": ["Bambu Lab A1 0.4 nozzle"]})
        write_json(lib / "Brand" / "Brand Support For PLA-PETG @System.json",
                   {"name": "Brand Support For PLA/PETG @System", "inherits": "Brand PLA @base",
                    "instantiation": "true", "filament_start_gcode": [
                        "{if bed_temperature[0] > 55}M106 P3 S200{endif}\n"
                        "{if activate_air_filtration[0] && support_air_filtration}\n"
                        "M106 P3 S{during_print_exhaust_fan_speed_num[current_extruder]}\n{endif}"]})
        write_json(lib / "Brand" / "Brand PP @System.json",
                   {"name": "Brand PP @System", "inherits": "fdm_filament_pp", "instantiation": "true"})
        write_json(lib / "Generic PETG @System.json",
                   {"name": "Generic PETG @System", "filament_type": ["PETG"], "instantiation": "true"})
        self.lib = lib

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_plan(self):
        entries, skipped = of.plan(self.lib)
        got = {e["name"]: (e["inherits"], e["type"], e["fan"], e["brand"], e["file"]) for e in entries}
        self.assertEqual(got, {
            "Brand PLA (Tweaked)": ("Brand PLA @System", "PLA", 100, "Brand", "Brand PLA (Tweaked).json"),
            "Brand Support For PLA/PETG (Tweaked)": ("Brand Support For PLA/PETG @System", "PLA", 100, "Brand",
                                                     "Brand Support For PLA-PETG (Tweaked).json"),
            "Generic PETG (Tweaked)": ("Generic PETG @System", "PETG", 75, "Generic", "Generic PETG (Tweaked).json"),
        })
        self.assertEqual(skipped, {"PP": 1})

    def test_start_gcode_that_overrides_the_fan_stops(self):
        write_json(self.lib / "Brand" / "Brand ABS @System.json",
                   {"name": "Brand ABS @System", "filament_type": ["ABS"], "instantiation": "true",
                    "filament_start_gcode": ["M106 P3 S255\n"]})
        with self.assertRaises(SystemExit):
            of.plan(self.lib)

    def test_write_replaces_old_files(self):
        out = self.tmp / "out"
        write_json(out / "Old" / "Gone (Tweaked).json", {})
        (out / "README.md").parent.mkdir(exist_ok=True)
        (out / "README.md").write_text("kept", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            of.main(["--library", str(self.lib), "--source", "test", "--out", str(out)])
        self.assertFalse((out / "Old").exists())
        self.assertEqual((out / "README.md").read_text(encoding="utf-8"), "kept")
        data = json.loads((out / "Generic" / "Generic PETG (Tweaked).json").read_text(encoding="utf-8"))
        self.assertEqual(data["during_print_exhaust_fan_speed"], ["75"])
        self.assertEqual(data["filament_settings_id"], ["Generic PETG (Tweaked)"])
        self.assertIn("Generic/Generic PETG (Tweaked).json", (out / of.INDEX_NAME).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
