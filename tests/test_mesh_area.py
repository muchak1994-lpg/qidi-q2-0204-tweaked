#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic)
"""Offline tests for the adaptive-bed-mesh area (modules/adaptive-bed-mesh/files/q2_mesh_area.py).

Run:  python tests/test_mesh_area.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "modules" / "adaptive-bed-mesh" / "files"))
import q2_mesh_area as q  # noqa: E402

START = """PRINT_START BED=55 HOTEND=220
M83
G1 X108 Y1 F30000
G0 X128 E8
G0 X158 E.37
"""
LAYER1 = """;LAYER_CHANGE
;Z:0.2
G1 X120 Y120 F30000
G1 X150 Y120 E1.2
G1 X150 Y150 E1.2
G1 X120 Y150 E1.2
"""
TOWER = """;TYPE:Prime tower
G1 X200 Y220 F30000
G1 X235 Y220 E1.4
G1 X235 Y240 E.8
"""
LAYER2 = """;LAYER_CHANGE
;Z:0.4
G1 X10 Y10 F30000
G1 X260 Y260 E9
"""

MESH = ((10., 10.), (260., 260.), (6, 6))


def bbox(text):
    return q.first_layer_bbox(text.splitlines())


class FirstLayerTest(unittest.TestCase):
    def test_models_only_purge_line_left_out(self):
        self.assertEqual(bbox(START + LAYER1 + LAYER2), [120., 120., 150., 150.])

    def test_wipe_tower_is_part_of_the_area(self):
        self.assertEqual(bbox(START + LAYER1 + TOWER + LAYER2), [120., 120., 235., 240.])

    def test_travel_moves_do_not_count(self):
        self.assertEqual(bbox(LAYER1 + "G1 X5 Y5 F30000\n" + LAYER2), [120., 120., 150., 150.])

    def test_absolute_extrusion(self):
        text = "M82\nG92 E0\n;LAYER_CHANGE\nG1 X100 Y100\nG1 X110 Y100 E1\nG1 X120 Y100 E1\nG1 X130 Y130 E2\n" + LAYER2
        self.assertEqual(bbox(text), [100., 100., 130., 130.])  # the move with E1 -> E1 extrudes nothing

    def test_relative_positions(self):
        text = "M83\n;LAYER_CHANGE\nG90\nG1 X100 Y100\nG91\nG1 X10 Y5 E1\nG90\n" + LAYER2
        self.assertEqual(bbox(text), [100., 100., 110., 105.])

    def test_arc_counts_whole_circle(self):
        text = "M83\n;LAYER_CHANGE\nG1 X100 Y100\nG2 X120 Y100 I10 J0 E2\n" + LAYER2
        self.assertEqual(bbox(text), [100., 90., 120., 110.])

    def test_cura_markers(self):
        text = "M83\n;LAYER:0\nG1 X50 Y60\nG1 X70 Y80 E1\n;LAYER:1\nG1 X200 Y200 E1\n"
        self.assertEqual(bbox(text), [50., 60., 70., 80.])

    def test_no_markers_or_no_second_layer_is_not_trusted(self):
        self.assertIsNone(bbox(START + "G1 X120 Y120\nG1 X150 Y120 E1\n"))
        self.assertIsNone(bbox(START + LAYER1))  # cut off: the first layer may continue

    def test_extrusion_mode_not_stated_counts_both_ways(self):
        self.assertEqual(bbox(LAYER1 + LAYER2), [120., 120., 150., 150.])

    def test_comments_and_crlf(self):
        text = (LAYER1 + LAYER2).replace("\n", " ; note\r\n")
        self.assertEqual(bbox(text), [120., 120., 150., 150.])


class AreaTest(unittest.TestCase):
    def test_small_print(self):
        lo, hi, count = q.mesh_area([120., 120., 150., 150.], *MESH)
        self.assertEqual((lo, hi, count), ((110., 110.), (160., 160.), (3, 3)))

    def test_with_tower(self):
        lo, hi, count = q.mesh_area([120., 120., 235., 240.], *MESH)
        self.assertEqual((lo, hi), ((110., 110.), (245., 250.)))
        self.assertEqual(count, (4, 4))  # 6 * 135/250 and 6 * 140/250, rounded up

    def test_clamped_to_the_probe_area(self):
        lo, hi, _ = q.mesh_area([5., 5., 60., 60.], *MESH)
        self.assertEqual((lo, hi), ((10., 10.), (70., 70.)))

    def test_almost_whole_plate_is_whole_plate(self):
        self.assertIsNone(q.mesh_area([15., 15., 255., 255.], *MESH))

    def test_nothing_found_is_whole_plate(self):
        self.assertIsNone(q.mesh_area(None, *MESH))

    def test_outside_the_probe_area_is_whole_plate(self):
        self.assertIsNone(q.mesh_area([262., 262., 268., 268.], *MESH, margin=0.))

    def test_tiny_print_keeps_points_apart(self):
        lo, hi, count = q.mesh_area([135., 135., 135.5, 135.5], *MESH, margin=0.)
        self.assertEqual(count, (3, 3))
        self.assertGreaterEqual(hi[0] - lo[0], 2.)
        self.assertGreaterEqual(hi[1] - lo[1], 2.)


if __name__ == "__main__":
    unittest.main(verbosity=2)
