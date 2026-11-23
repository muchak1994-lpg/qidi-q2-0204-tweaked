#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""QIDI Q2 02.04 Tweaked - the chamber-fan hook in the OrcaSlicer printer profiles.

QIDI's own Q2 filament profiles switch the chamber (exhaust) fan, M106 P3, on or off per material. The
filament library bundled with OrcaSlicer (SUNLU, eSUN, Polymaker, ... "@System") leaves it off for every
material. Instead of one "(Tweaked)" copy of every filament (OrcaSlicer lists user presets flat, not grouped
by brand), the printer profiles `Qidi Q2 ... (Tweaked)` set the fan from the filament type in
before_layer_change_gcode, once, before the first layer.

Usage (maintainer, after changing the table below):
    python tools/orca_machine_hook.py

Standard library only, Python 3.9+.
"""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MACHINES = REPO / "orca-profiles" / "machine"

# Chamber fan (M106 P3) during the print, in %, per OrcaSlicer filament_type. Owner's decision 2026-11-19.
# QIDI's Q2 profiles as reference: PLA/PETG/TPU/PA 100, ABS/ASA/PC 0 (those heat the chamber instead).
# PETG 75 and PA 25 are the owner's choice (PA: a little air exchange, the chamber stays warm).
# Types not listed here get no fan line (the end G-code switches the fan off after the print).
FAN_GROUPS = {
    100: ("PLA", "PLA+", "PLA-CF", "PLA-AERO", "PLA Silk", "TPU", "TPU-AMS"),
    75: ("PETG", "PETG-CF", "PETG HF", "PET-CF", "PCTG", "PCTG-CF", "PCTG-GF"),
    25: ("PA", "PA6", "PA-CF", "PA-GF", "PA6-CF", "PPA-CF", "PPA-GF"),
    0: ("ABS", "ABS-GF", "ASA", "ASA-AERO", "ASA-CF", "PC"),
}
FAN = {ftype: speed for speed, types in FAN_GROUPS.items() for ftype in types}


def machine_fan_gcode():
    """before_layer_change_gcode: sets the chamber fan before the first layer from the filament type.
    Checked by slicing with OrcaSlicer 2.5.2: PLA -> S255, PETG -> S191, PA -> S64, ABS/ASA/PC -> nothing."""
    lines = ["{if layer_num == 0}"]
    for i, pct in enumerate(sorted({s for s in FAN.values() if s}, reverse=True)):
        cond = " or ".join('filament_type[initial_tool] == "%s"' % t for t, s in FAN.items() if s == pct)
        lines.append("{%s %s}" % ("if" if i == 0 else "elsif", cond))
        lines.append("M106 P3 S%d" % round(pct * 2.55))
    return "\n".join(lines + ["{endif}", "{endif}"])


def write_machine_hook(folder=None):
    """Put machine_fan_gcode() into the project's printer profiles (orca-profiles/machine/*.json)."""
    for path in sorted(Path(folder or MACHINES).glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        data["before_layer_change_gcode"] = machine_fan_gcode()
        path.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    write_machine_hook()
    print("Written to", MACHINES)
