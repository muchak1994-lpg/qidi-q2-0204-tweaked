#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""QIDI Q2 02.04 Tweaked - generate the OrcaSlicer filament profiles with the chamber fan set per material.

QIDI's own Q2 filament profiles switch the chamber (exhaust) fan, M106 P3, on or off per material. The
generic filament library bundled with OrcaSlicer (SUNLU, eSUN, Polymaker, ... "@System") leaves it off
for every material. This script writes one OrcaSlicer user preset per library filament usable on the Q2.
Each preset inherits everything from the library filament and only sets the chamber fan (FAN below)
and limits the preset to the QIDI Q2 printer.

The files go to orca-profiles/filament/<brand>/ (a .json and the .info OrcaSlicer keeps next to it).
They are imported by the user in OrcaSlicer (File > Import > Import Configs..., picking only the
filaments they want), or added by tools/orca_profiles.py for the filaments enabled in OrcaSlicer.

Usage (maintainer, after updating the OrcaSlicer library):
    python tools/orca_filaments.py --library <OrcaSlicer>/resources/profiles/OrcaFilamentLibrary/filament \
        --source "OrcaSlicer main abc1234 (YYYY-MM-DD)"

Standard library only, Python 3.9+.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "orca-profiles" / "filament"
INDEX_NAME = "index.tsv"
SUFFIX = " (Tweaked)"
PRESET_VERSION = "2.4.0.19"
Q2_CONDITION = 'printer_model == "Qidi Q2"'

# Chamber fan (M106 P3) during the print, in %, per OrcaSlicer filament_type. After the print: 0 for all.
# Owner's decision 2026-11-19. QIDI's Q2 profiles as reference: PLA/PETG/TPU/PA 100, ABS/ASA/PC 0
# (those heat the chamber instead). PETG 75 and PA 25 are the owner's choice (PA: a little air
# exchange, the chamber stays warm). Types not listed here get no profile.
FAN_GROUPS = {
    100: ("PLA", "PLA+", "PLA-CF", "PLA-AERO", "PLA Silk", "TPU", "TPU-AMS"),
    75: ("PETG", "PETG-CF", "PETG HF", "PET-CF", "PCTG", "PCTG-CF", "PCTG-GF"),
    25: ("PA", "PA6", "PA-CF", "PA-GF", "PA6-CF", "PPA-CF", "PPA-GF"),
    0: ("ABS", "ABS-GF", "ASA", "ASA-AERO", "ASA-CF", "PC"),
}
FAN = {ftype: speed for speed, types in FAN_GROUPS.items() for ftype in types}
AFTER_PRINT = 0
FAN_KEYS = ("activate_air_filtration", "during_print_exhaust_fan_speed", "complete_print_exhaust_fan_speed")
BAD_FILENAME_CHARS = '<>:"/\\|?*'


def first(value):
    return value[0] if isinstance(value, list) and value else value


def load_library(folder):
    """{name: (json, path)} of every profile in the OrcaSlicer filament library folder."""
    profiles = {}
    for path in sorted(Path(folder).rglob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if "name" in data:
            profiles[data["name"]] = (data, path)
    return profiles


def resolve(profiles, name, key, depth=0):
    """Value of key for a profile, following "inherits"; None when not set anywhere."""
    if name not in profiles or depth > 20:
        return None
    data = profiles[name][0]
    if key in data:
        return data[key]
    parent = data.get("inherits")
    return resolve(profiles, parent, key, depth + 1) if parent else None


def preset_name(library_name):
    stem = library_name[:-len(" @System")] if library_name.endswith(" @System") else library_name
    return stem + SUFFIX


def file_name(name):
    """The preset name with characters Windows does not allow in file names replaced (Orca reads "name")."""
    return "".join("-" if c in BAD_FILENAME_CHARS else c for c in name)


def start_gcode_keeps_our_fan(gcode):
    """True when the filament start G-code leaves the chamber fan to our setting: no M106 P3 at all, or
    its last M106 P3 is OrcaSlicer's own "M106 P3 S{during_print_exhaust_fan_speed_num[...]}" line."""
    tail = gcode.rsplit("M106 P3", 1)
    return len(tail) == 1 or tail[1].lstrip().startswith("S{during_print_exhaust_fan_speed_num")


def brand_folder(library_root, path):
    rel = path.relative_to(library_root).parts
    return rel[0] if len(rel) > 1 else "Generic"


def plan(library_root):
    """(entries, skipped). entries: dicts for the presets to write; skipped: {filament_type: count}."""
    library_root = Path(library_root)
    profiles = load_library(library_root)
    entries, skipped, names = [], {}, set()
    for name, (data, path) in sorted(profiles.items()):
        if str(first(resolve(profiles, name, "instantiation"))).lower() == "false":
            continue
        printers = resolve(profiles, name, "compatible_printers") or []
        if printers and not any(p.startswith("Qidi Q2 ") for p in printers):
            continue  # made for other printers only (e.g. one Bambu model)
        ftype = first(resolve(profiles, name, "filament_type"))
        if ftype not in FAN:
            skipped[ftype] = skipped.get(ftype, 0) + 1
            continue
        if not start_gcode_keeps_our_fan(str(first(resolve(profiles, name, "filament_start_gcode")) or "")):
            raise SystemExit("%s switches the chamber fan in its start G-code; check it by hand" % name)
        new = preset_name(name)
        if new in names:
            raise SystemExit("two library filaments give the same name: " + new)
        names.add(new)
        entries.append({"name": new, "inherits": name, "type": ftype, "fan": FAN[ftype],
                        "brand": brand_folder(library_root, path), "file": file_name(new) + ".json",
                        "base_id": data.get("setting_id", "")})
    files = [(e["brand"], e["file"].lower()) for e in entries]
    if len(set(files)) != len(files):
        raise SystemExit("two presets give the same file name")
    return entries, skipped


def preset(entry):
    """The OrcaSlicer user preset (JSON object) for one entry."""
    return {
        "activate_air_filtration": ["1"],
        "compatible_printers": [],
        "compatible_printers_condition": Q2_CONDITION,
        "complete_print_exhaust_fan_speed": [str(AFTER_PRINT)],
        "during_print_exhaust_fan_speed": [str(entry["fan"])],
        "filament_settings_id": [entry["name"]],
        "from": "User",
        "inherits": entry["inherits"],
        "name": entry["name"],
        "version": PRESET_VERSION,
    }


def info(entry):
    """The .info file OrcaSlicer keeps next to a user preset (as it writes one on import)."""
    return "sync_info = \nuser_id = \nsetting_id = \nbase_id = %s\nupdated_time = 0\n" % entry.get("base_id", "")


def write(entries, out, source):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for child in out.iterdir():  # the brand folders are ours and fully regenerated
        if child.is_dir():
            shutil.rmtree(child)
    lines = ["# Generated by tools/orca_filaments.py from " + source,
             "# file\tinherits (OrcaSlicer library)\tfilament_type\tchamber fan during print %\tafter print %"]
    for e in sorted(entries, key=lambda e: (e["brand"].lower(), e["name"].lower())):
        rel = "%s/%s" % (e["brand"], e["file"])
        target = out / rel
        target.parent.mkdir(exist_ok=True)
        target.write_text(json.dumps(preset(e), indent=4, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        target.with_suffix(".info").write_text(info(e), encoding="utf-8")
        lines.append("\t".join((rel, e["inherits"], e["type"], str(e["fan"]), str(AFTER_PRINT))))
    (out / INDEX_NAME).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--library", required=True, help="OrcaSlicer resources/profiles/OrcaFilamentLibrary/filament")
    parser.add_argument("--source", required=True, help='where the library came from, e.g. "OrcaSlicer main 5cf5ef8 (2026-11-19)"')
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args(argv)
    entries, skipped = plan(args.library)
    if not entries:
        sys.exit("No filaments found in " + args.library)
    write(entries, args.out, args.source)
    by_fan = {}
    for e in entries:
        by_fan[e["fan"]] = by_fan.get(e["fan"], 0) + 1
    print("Written: %d presets to %s" % (len(entries), args.out))
    for speed in sorted(by_fan, reverse=True):
        print("  chamber fan %3d%%: %d" % (speed, by_fan[speed]))
    print("Skipped (material without a decided fan speed): " +
          ", ".join("%s %d" % (t, n) for t, n in sorted(skipped.items(), key=lambda x: str(x[0]))))


if __name__ == "__main__":
    main()
