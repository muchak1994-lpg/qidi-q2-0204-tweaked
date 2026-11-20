# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic)
"""Bed mesh before a print measured only where the first layer is printed.

q2-0204-tweaked, module adaptive-bed-mesh.

QIDI's G29 (called by PRINT_START) measures the whole plate before every
print. TWEAKED_ADAPTIVE_MESH reads the first layer of the file being printed and
measures only the area of everything printed on it - the models and also the
wipe (prime) tower, brim and skirt, which the slicer's object outlines do not
include - plus a margin. The number of probe points shrinks with the area,
keeping the configured point spacing (at least 3 x 3).

The command name must not start with a letter followed by a digit ("Q2_..."):
Klipper would read that as the traditional G-code "Q2" and QIDI's Klipper drops
unknown commands without a message.

The whole plate is measured, as before, when no file is printing (a G29 from
the screen or the console), when the file has no layer markers, when the first
layer cannot be read within the limits below, when it covers most of the
plate anyway, or when the file is printed object by object (the first layer of
the first object is all that comes before its second layer).

    TWEAKED_ADAPTIVE_MESH PROFILE=kamp
"""
import logging
import math
import re

MARGIN = 10.            # mm around the first layer (nozzle presses near the edge, brim growth)
MAX_BYTES = 32 << 20    # read at most this much of the file looking for the first layer
FULL_RATIO = 0.9        # area this close to the whole plate: just measure the whole plate
LAYER_MARKERS = (";LAYER_CHANGE", "; CHANGE_LAYER", ";LAYER:")
TAIL_BYTES = 256 << 10  # the slicer's settings are at the end of the file
BY_OBJECT = re.compile(r"^;\s*(print_sequence\s*=\s*by.object|complete_objects\s*=\s*1)\s*$", re.M)
WORD = re.compile(r"([XYZEIJF])\s*(-?\d*\.?\d+)")


def first_layer_bbox(lines, pause=None):
    """(min_x, min_y, max_x, max_y) of the extruding moves of the first layer, or None.

    lines: an iterable of G-code lines. The first layer is what lies between the
    first and the second layer marker; the start G-code before it (QIDI's purge
    line at the front edge) is not part of it."""
    x = y = 0.
    e_last = 0.
    absolute = True        # G90
    e_relative = None      # M83 True, M82 False; None = not set in the file
    layer = 0
    box = None
    for n, raw in enumerate(lines):
        if pause is not None and n % 20000 == 19999:
            pause()
        line = raw.strip()
        if not line:
            continue
        if line[0] == ";":
            if line.startswith(LAYER_MARKERS):
                layer += 1
                if layer == 2:
                    return box
            continue
        code = line.split(";", 1)[0].split(None, 1)
        cmd = code[0].upper()
        if cmd == "G90":
            absolute = True
        elif cmd == "G91":
            absolute = False
        elif cmd == "M82":
            e_relative = False
        elif cmd == "M83":
            e_relative = True
        elif cmd == "G92":
            words = dict(WORD.findall(code[1].upper())) if len(code) > 1 else {}
            if "E" in words:
                e_last = float(words["E"])
        elif cmd in ("G0", "G1", "G2", "G3"):
            words = dict(WORD.findall(code[1].upper())) if len(code) > 1 else {}
            nx, ny = x, y
            if "X" in words:
                nx = float(words["X"]) if absolute else x + float(words["X"])
            if "Y" in words:
                ny = float(words["Y"]) if absolute else y + float(words["Y"])
            extrudes = False
            if "E" in words:
                e = float(words["E"])
                if e_relative or not absolute:  # in Klipper G91 makes E relative too
                    extrudes = e > 0.
                elif e_relative is False:
                    extrudes = e > e_last
                else:  # mode not stated in the file: count it as extruding either way (a larger area is safe)
                    extrudes = e > 0. or e > e_last
                if e_relative is not True and absolute:
                    e_last = e
            if extrudes and layer == 1:
                points = [(x, y), (nx, ny)]
                if cmd in ("G2", "G3") and ("I" in words or "J" in words):
                    cx, cy = x + float(words.get("I", 0.)), y + float(words.get("J", 0.))
                    r = math.hypot(x - cx, y - cy)
                    points += [(cx - r, cy - r), (cx + r, cy + r)]  # whole circle: never too small
                for px, py in points:
                    if box is None:
                        box = [px, py, px, py]
                    else:
                        box[0] = min(box[0], px)
                        box[1] = min(box[1], py)
                        box[2] = max(box[2], px)
                        box[3] = max(box[3], py)
            x, y = nx, ny
    return None  # no second layer marker within what was read: not trusted


def printed_by_object(tail):
    """True when the slicer's settings at the end of the file say "one object after another"."""
    return BY_OBJECT.search(tail) is not None


def mesh_area(bbox, mesh_min, mesh_max, probe_count, margin=MARGIN):
    """(MESH_MIN, MESH_MAX, PROBE_COUNT) for the area, or None for the whole plate.

    Same rules as Klipper's own adaptive mesh: the probe count shrinks in
    proportion to the area (rounded up, at least 3; 4 when the other axis needs
    more than 6, a Klipper requirement)."""
    if bbox is None:
        return None
    lo = [max(bbox[0] - margin, mesh_min[0]), max(bbox[1] - margin, mesh_min[1])]
    hi = [min(bbox[2] + margin, mesh_max[0]), min(bbox[3] + margin, mesh_max[1])]
    full = (mesh_max[0] - mesh_min[0], mesh_max[1] - mesh_min[1])
    size = [hi[0] - lo[0], hi[1] - lo[1]]
    if size[0] <= 0 or size[1] <= 0:
        return None  # the first layer is outside the probed area: be safe
    ratio = (size[0] / full[0], size[1] / full[1])
    if ratio[0] * ratio[1] >= FULL_RATIO:
        return None
    count = [int(math.ceil(probe_count[0] * ratio[0])), int(math.ceil(probe_count[1] * ratio[1]))]
    least = 4 if max(count) > 6 and min(count) < 4 else 3
    count = [max(least, c) for c in count]
    # a tiny area: keep at least 1 mm between points
    for axis in (0, 1):
        need = count[axis] - 1
        if size[axis] < need:
            grow = (need - size[axis]) / 2.
            lo[axis] = max(mesh_min[axis], lo[axis] - grow)
            hi[axis] = min(mesh_max[axis], lo[axis] + need)
            lo[axis] = hi[axis] - need
    return (lo[0], lo[1]), (hi[0], hi[1]), (count[0], count[1])


class Q2MeshArea:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.margin = config.getfloat('margin', MARGIN, minval=0.)
        gcode = self.printer.lookup_object('gcode')
        gcode.register_command('TWEAKED_ADAPTIVE_MESH', self.cmd_TWEAKED_ADAPTIVE_MESH,
                               desc="Bed mesh only where the first layer of the printing file is")

    def _mesh_settings(self):
        eventtime = self.printer.get_reactor().monotonic()
        settings = self.printer.lookup_object('configfile').get_status(eventtime)['settings']['bed_mesh']

        def pair(value):
            if isinstance(value, str):
                value = [float(v) for v in value.split(',')]
            return (float(value[0]), float(value[1]))
        count = settings.get('probe_count', (3, 3))
        if isinstance(count, (int, float)):
            count = (count, count)
        return pair(settings['mesh_min']), pair(settings['mesh_max']), \
            (int(pair(count)[0]), int(pair(count)[1]))

    def _first_layer(self):
        sdcard = self.printer.lookup_object('virtual_sdcard', None)
        path = sdcard.file_path() if sdcard is not None else None
        if not path:
            return None, "no file is printing"
        reactor = self.printer.get_reactor()
        pause = lambda: reactor.pause(reactor.monotonic() + 0.001)  # let heaters and comms run

        def lines(f):
            read = 0
            for line in f:
                read += len(line)
                if read > MAX_BYTES:
                    return
                yield line
        try:
            with open(path, 'rb') as f:
                f.seek(0, 2)
                f.seek(max(0, f.tell() - TAIL_BYTES))
                tail = f.read().decode('utf-8', 'replace')
            if printed_by_object(tail):
                return None, "printed object by object"
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                bbox = first_layer_bbox(lines(f), pause)
        except OSError as exc:
            return None, "file not readable (%s)" % exc
        if bbox is None:
            return None, "first layer not found in the file"
        return bbox, None

    def cmd_TWEAKED_ADAPTIVE_MESH(self, gcmd):
        profile = gcmd.get('PROFILE', 'default')
        base = "BED_MESH_CALIBRATE PROFILE=%s" % profile
        try:
            mesh_min, mesh_max, count = self._mesh_settings()
            bbox, why = self._first_layer()
            area = mesh_area(bbox, mesh_min, mesh_max, count, self.margin) if bbox else None
            if bbox is not None and area is None:
                why = "the first layer covers most of the plate"
        except Exception as exc:  # never stop a print start because of this: measure everything
            logging.exception("q2_mesh_area")
            area, why = None, "error (%s)" % exc
        if area is None:
            gcmd.respond_info("Bed mesh: whole plate (%s)" % why)
            self.printer.lookup_object('gcode').run_script_from_command(base)
            return
        lo, hi, cnt = area
        gcmd.respond_info("Bed mesh: only under the first layer (models, wipe tower, brim, skirt + %.0f mm): "
                          "X%.1f-%.1f Y%.1f-%.1f, %d x %d points"
                          % (self.margin, lo[0], hi[0], lo[1], hi[1], cnt[0], cnt[1]))
        self.printer.lookup_object('gcode').run_script_from_command(
            "%s MESH_MIN=%.3f,%.3f MESH_MAX=%.3f,%.3f PROBE_COUNT=%d,%d"
            % (base, lo[0], lo[1], hi[0], hi[1], cnt[0], cnt[1]))


def load_config(config):
    return Q2MeshArea(config)
