#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""QIDI Q2 02.04 Tweaked - OrcaSlicer profiles (add-only).

Adds the project's printer and process profiles to OrcaSlicer's user folder. The printer profiles also set
the chamber fan from the filament type, so the ordinary OrcaSlicer filaments need no copy of their own.
It never overwrites or deletes a file it did not add itself:

* a file with the same name that already exists is skipped and reported;
* every added file is recorded (with its SHA-256) in a manifest kept in the
  Orca user folder, so `uninstall` removes only those files, and only if they
  are unchanged (a profile you edited afterwards is left alone);
* before any change, the current machine/, process/ and filament/ folders are zipped to
  backups/ next to this repository.

Without --apply every command only shows what it would do.

Usage:
    python tools/orca_profiles.py status
    python tools/orca_profiles.py install            (dry run)
    python tools/orca_profiles.py install --apply
    python tools/orca_profiles.py uninstall --apply
    python tools/orca_profiles.py hook --apply       (chamber-fan code into printer profiles from version 1.2.0 or older)

OrcaSlicer must be closed while installing or uninstalling.
Standard library only, Python 3.9+.
"""
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from orca_machine_hook import machine_fan_gcode  # noqa: E402

# The 03.02 project uses the same manifest name: the printer and process profiles are identical, so either project
# can see and remove what the other added.
PROJECT = "qidi-q2-0204-tweaked"
MANIFEST_NAME = "." + PROJECT + "-orca-manifest.json"
REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "orca-profiles"
BACKUPS = REPO / "backups"
KINDS = ("machine", "process")
# "filament" is only zipped, never written to: versions up to 1.2.0 added "(Tweaked)" filament copies, and uninstall still removes
# the unchanged ones recorded in the manifest.
BACKUP_KINDS = KINDS + ("filament",)
BAD_FILENAME_CHARS = '<>:"/\\|?*'
HOW_TO_ADD = "py tools/orca_profiles.py install --apply"
FORBIDDEN_KEYS = ("print_host", "printhost_apikey", "print_host_webui")
HOOK_KEY = "before_layer_change_gcode"
HOW_TO_HOOK = "py tools/orca_profiles.py hook --apply"
CHECKED_WITH_ORCA = "2.5.2"    # the OrcaSlicer version the fan code was checked with (sliced, M106 P3 lines read)
ORCA_RELEASES = "https://github.com/OrcaSlicer/OrcaSlicer/releases"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def default_orca_root():
    system = platform.system()
    home = Path.home()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming")))
        return base / "OrcaSlicer"
    if system == "Darwin":
        return home / "Library" / "Application Support" / "OrcaSlicer"
    flatpak = home / ".var" / "app" / "io.github.softfever.OrcaSlicer" / "config" / "OrcaSlicer"
    if flatpak.is_dir():
        return flatpak
    return Path(os.environ.get("XDG_CONFIG_HOME", str(home / ".config"))) / "OrcaSlicer"


def orca_running():
    """True / False, or None when it cannot be determined."""
    try:
        if platform.system() == "Windows":
            cmd = ["tasklist", "/FO", "CSV", "/NH"]
        else:
            cmd = ["ps", "-A", "-o", "comm="]
        raw = subprocess.run(cmd, capture_output=True, timeout=30).stdout
    except Exception:
        return None
    # Bytes, decoded leniently: tasklist writes in the console code page (e.g. cp852 on Polish
    # Windows, with 0xFF as the thousands separator), which UTF-8 mode (Python 3.15+) cannot read.
    # The process names we look for are plain ASCII either way.
    out = raw.decode("ascii", errors="replace").lower()
    return any(name in out for name in ("orca-slicer", "orcaslicer"))


def source_files():
    """[(kind, filename, path)] of the profiles shipped with the project."""
    files = []
    for kind in KINDS:
        folder = SRC / kind
        if not folder.is_dir():
            continue
        for path in sorted(folder.iterdir()):
            if path.is_file() and path.suffix in (".json", ".info"):
                files.append((kind, path.name, path))
    return files


def file_name(name):
    """The preset name with characters Windows does not allow in file names replaced (Orca reads "name")."""
    return "".join("-" if c in BAD_FILENAME_CHARS else c for c in name)


def check_sources(files):
    """Refuse to ship a broken or private profile."""
    problems = []
    names = {(k, n) for k, n, _ in files}
    for kind, name, path in files:
        if path.suffix != ".json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            problems.append("%s/%s: invalid JSON (%s)" % (kind, name, exc))
            continue
        stem = name[:-5]
        if file_name(str(data.get("name"))) != stem:
            problems.append("%s/%s: name field %r differs from file name" % (kind, name, data.get("name")))
        for key in FORBIDDEN_KEYS:
            if key in data:
                problems.append("%s/%s: contains %s (printer address/key must not ship)" % (kind, name, key))
        if (kind, stem + ".info") not in names:
            problems.append("%s/%s: missing .info file" % (kind, name))
    return problems


def pick_user_dir(root, wanted):
    user = root / "user"
    dirs = sorted(d for d in user.iterdir() if d.is_dir()) if user.is_dir() else []
    if wanted:
        target = user / wanted
        if not target.is_dir():
            sys.exit("Orca user folder not found: %s" % target)
        return target
    if not dirs:
        sys.exit("No OrcaSlicer user folder in %s.\nStart OrcaSlicer once, add a QIDI Q2 printer, "
                 "close it and run this again (or pass --orca-dir)." % user)
    if len(dirs) == 1:
        return dirs[0]
    active = orca_conf(root).get("preset_folder")  # the folder OrcaSlicer itself is using (an account number when signed in)
    for d in dirs:
        if active and d.name == active:
            return d
    print("OrcaSlicer has several user folders (\"default\" or an account number):")
    for i, d in enumerate(dirs, 1):
        print("  %d) %s" % (i, d.name))
    if not sys.stdin.isatty():
        sys.exit("Choose one with --user-dir NAME.")
    answer = input("Which one? [1-%d]: " % len(dirs)).strip()
    if not answer.isdigit() or not 1 <= int(answer) <= len(dirs):
        sys.exit("No folder chosen, nothing changed.")
    return dirs[int(answer) - 1]


def orca_conf(root):
    """OrcaSlicer.conf as a dict ({} when missing or unreadable). The file is JSON followed by a '# MD5 checksum' line."""
    try:
        text = (Path(root) / "OrcaSlicer.conf").read_text(encoding="utf-8")
        data = json.JSONDecoder().raw_decode(text.lstrip())[0]
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def version_tuple(text):
    try:
        return tuple(int(part) for part in str(text).split(".")[:3])
    except ValueError:
        return None


def profiles_without_hook(user_dir, files):
    """The project's printer profiles that are in the Orca user folder but have no before-layer code ([Path])."""
    found = []
    for kind, name, _ in files:
        dest = user_dir / kind / name
        if kind != "machine" or not name.endswith(".json") or not dest.is_file():
            continue
        try:
            data = json.loads(dest.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if isinstance(data, dict) and not str(data.get(HOOK_KEY, "")).strip():
            found.append(dest)
    return found


def load_manifest(user_dir):
    path = user_dir / MANIFEST_NAME
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"project": PROJECT, "files": {}}


def save_manifest(user_dir, manifest):
    path = user_dir / MANIFEST_NAME
    if manifest["files"]:
        manifest["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        path.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    elif path.exists():
        path.unlink()


def backup(user_dir):
    BACKUPS.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = BACKUPS / ("orca-%s-%s.zip" % (user_dir.name, stamp))
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for kind in BACKUP_KINDS:
            folder = user_dir / kind
            if folder.is_dir():
                for path in sorted(folder.rglob("*")):
                    if path.is_file():
                        zf.write(path, path.relative_to(user_dir).as_posix())
        manifest = user_dir / MANIFEST_NAME
        if manifest.is_file():
            zf.write(manifest, MANIFEST_NAME)
    return target


def require_closed(args):
    if args.skip_running_check:
        return
    running = orca_running()
    if running:
        sys.exit("OrcaSlicer is running. Close it and run this again.")
    if running is None:
        sys.exit("Could not check whether OrcaSlicer is running. Close it and add --skip-running-check.")


def cmd_status(args, user_dir, files):
    manifest = load_manifest(user_dir)
    print("Orca user folder:", user_dir)
    counts = {"ours": 0, "missing": 0, "other": 0, "edited": 0, "same": 0}
    for kind, name, path in files:
        rel = kind + "/" + name
        dest = user_dir / kind / name
        if not dest.exists():
            state = "missing"
        elif rel in manifest["files"]:
            state = "ours" if sha256(dest) == manifest["files"][rel] else "edited"
        elif sha256(dest) == sha256(path):
            state = "same"
        else:
            state = "other"
        counts[state] += 1
        if args.verbose or state in ("other", "edited"):
            print("  %-8s %s" % (state, rel))
    print("Added by this project: %(ours)d, edited since: %(edited)d, not added yet: %(missing)d, "
          "identical copy already there: %(same)d, same name owned by someone else (left alone): %(other)d" % counts)


def install_plan(user_dir, files):
    """(to add [(rel, source, dest)], already there [rel], skipped [rel])."""
    manifest = load_manifest(user_dir)
    plan_add, plan_skip, plan_same = [], [], []
    for kind, name, path in files:
        rel = kind + "/" + name
        dest = user_dir / kind / name
        if not dest.exists():
            plan_add.append((rel, path, dest))
        elif rel in manifest["files"] or sha256(dest) == sha256(path):
            plan_same.append(rel)
        else:
            plan_skip.append(rel)
    return plan_add, plan_same, plan_skip


def cmd_install(args, user_dir, files):
    manifest = load_manifest(user_dir)
    plan_add, plan_same, plan_skip = install_plan(user_dir, files)
    print("Orca user folder:", user_dir)
    print("To add: %d   already present: %d   skipped, a file of that name exists: %d"
          % (len(plan_add), len(plan_same), len(plan_skip)))
    for rel in plan_skip:
        print("  skip (exists, not ours, left untouched):", rel)
    if not args.apply:
        for rel, _, _ in plan_add:
            print("  would add:", rel)
        print("Dry run - nothing changed. Add --apply to install.")
        return
    if not plan_add:
        print("Nothing to add.")
        return
    require_closed(args)
    print("Backup:", backup(user_dir))
    for rel, path, dest in plan_add:
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = path.read_bytes()
        with open(dest, "xb") as fh:  # "x": never overwrite, even in a race
            fh.write(data)
        manifest["files"][rel] = hashlib.sha256(data).hexdigest()
        print("  added:", rel)
    save_manifest(user_dir, manifest)
    print("Done. Start OrcaSlicer: printers \"... (Tweaked)\", processes \"[TL] ...\".")


def cmd_hook(args, user_dir, files):
    """Chamber-fan code into the project's printer profiles that lack it (profiles added by version 1.2.0 or older).
    Only the one key is added; the printer address, the API key and every other setting stay. A profile that already has
    its own before-layer code is left alone."""
    todo = profiles_without_hook(user_dir, files)
    print("Orca user folder:", user_dir)
    print("Printer profiles without the chamber-fan code: %d" % len(todo))
    for path in todo:
        print("  would add it to:" if not args.apply else "  to change:", path.stem)
    if not args.apply:
        print("Dry run - nothing changed. Add --apply to do it (OrcaSlicer must be closed)." if todo
              else "Nothing to add.")
        return
    if not todo:
        print("Nothing to add.")
        return
    require_closed(args)
    print("Backup:", backup(user_dir))
    code = machine_fan_gcode()
    for path in todo:
        data = json.loads(path.read_text(encoding="utf-8"))
        data[HOOK_KEY] = code
        path.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        info = path.with_suffix(".info")
        if info.is_file():  # a newer update time, so OrcaSlicer (and its cloud sync) keeps this version
            lines = info.read_text(encoding="utf-8").splitlines()
            stamp = "updated_time = %d" % int(time.time())
            lines = [stamp if line.startswith("updated_time") else line for line in lines]
            if stamp not in lines:
                lines.append(stamp)
            info.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        print("  added the fan code:", path.stem)
    print("Done. Start OrcaSlicer; the code is in the printer profile under Printer settings > Machine G-code > "
          "Before layer change G-code.")


def cmd_uninstall(args, user_dir, files):
    manifest = load_manifest(user_dir)
    if not manifest["files"]:
        print("Nothing recorded as added by this project in", user_dir)
        return
    remove, keep, gone = [], [], []
    for rel, digest in sorted(manifest["files"].items()):
        dest = user_dir / rel
        if not dest.exists():
            gone.append(rel)
        elif sha256(dest) == digest:
            remove.append(rel)
        else:
            keep.append(rel)
    print("Orca user folder:", user_dir)
    print("To remove: %d   edited since install (kept): %d   already gone: %d"
          % (len(remove), len(keep), len(gone)))
    for rel in keep:
        print("  keep (you edited it):", rel)
    if not args.apply:
        print("Dry run - nothing changed. Add --apply to uninstall.")
        return
    require_closed(args)
    print("Backup:", backup(user_dir))
    for rel in remove:
        (user_dir / rel).unlink()
        del manifest["files"][rel]
        print("  removed:", rel)
    for rel in gone:
        del manifest["files"][rel]
    save_manifest(user_dir, manifest)
    print("Done.")


def ask(question, default=True, read=input):
    answer = read("%s [%s] " % (question, "Y/n" if default else "y/N")).strip().lower()
    return default if not answer else answer in ("y", "yes", "t", "tak")


def offer(mode="ask", read=input, root=None):
    """The installer's OrcaSlicer step, on this computer. mode: ask / yes / no. Never stops the installer."""
    if mode == "no":
        return
    try:
        _offer(mode, read, Path(root) if root else default_orca_root())
    except (KeyboardInterrupt, EOFError):
        print("\nOrcaSlicer profiles left out. Add them any time:", HOW_TO_ADD)
    except SystemExit as exc:
        print("OrcaSlicer profiles not added: %s\nAdd them any time: %s" % (exc.code, HOW_TO_ADD))


def _offer(mode, read, root):
    if not (root / "user").is_dir():
        print("\nOrcaSlicer: no profiles folder on this computer - step skipped "
              "(after installing OrcaSlicer: %s)." % HOW_TO_ADD)
        return
    files = source_files()
    problems = check_sources(files)
    if problems:
        print("OrcaSlicer profiles skipped, the project files are not valid:\n  " + "\n  ".join(problems))
        return
    print()
    user_dir = pick_user_dir(root, None)
    try:
        _offer_add(mode, read, user_dir, files)
    finally:
        _hints(root, user_dir, files)


def _hints(root, user_dir, files):
    """After the step: profiles from version 1.2.0 or older without the fan code, and an OrcaSlicer older than the one checked."""
    todo = profiles_without_hook(user_dir, files)
    if todo:
        print("OrcaSlicer: these printer profiles have no chamber-fan code (versions up to 1.2.0 did not add it):\n  "
              + "\n  ".join(p.stem for p in todo)
              + "\n  Add it (your printer address and other settings stay; close OrcaSlicer first): " + HOW_TO_HOOK)
    version = orca_conf(root).get("version")
    if version and version_tuple(version) and version_tuple(version) < version_tuple(CHECKED_WITH_ORCA):
        print("OrcaSlicer %s is installed; the profiles were checked with %s. It is worth it to update OrcaSlicer: %s"
              % (version, CHECKED_WITH_ORCA, ORCA_RELEASES))


def _offer_add(mode, read, user_dir, files):
    plan_add = install_plan(user_dir, files)[0]
    if not plan_add:
        print("OrcaSlicer: the project's profiles are already there.")
        return
    count = {}
    for rel, _, _ in plan_add:
        if rel.endswith(".json"):
            kind = rel.split("/")[0]
            count[kind] = count.get(kind, 0) + 1
    print("OrcaSlicer profiles from this project (only added, nothing of yours is changed):\n"
          "  printers \"Qidi Q2 ... (Tweaked)\" (they also set the chamber fan from the filament type): %d,\n"
          "  timelapse processes \"[TL] ...\": %d"
          % (count.get("machine", 0), count.get("process", 0)))
    if mode == "ask" and not ask("Add them to OrcaSlicer?", True, read):
        print("Not added. Any time later:", HOW_TO_ADD)
        return
    if orca_running() is not False:
        print("OrcaSlicer is open (or that could not be checked). Close it and run:", HOW_TO_ADD)
        return
    cmd_install(argparse.Namespace(apply=True, skip_running_check=True), user_dir, files)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Add (never overwrite) the QIDI Q2 02.04 Tweaked OrcaSlicer profiles.")
    parser.add_argument("command", choices=("status", "install", "uninstall", "hook"))
    parser.add_argument("--apply", action="store_true", help="really change files (default: dry run)")
    parser.add_argument("--orca-dir", help="OrcaSlicer data folder (default: auto-detect)")
    parser.add_argument("--user-dir", help='user profile folder inside user/ ("default" or an account number)')
    parser.add_argument("--skip-running-check", action="store_true", help="do not check that OrcaSlicer is closed")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.orca_dir) if args.orca_dir else default_orca_root()
    files = source_files()
    problems = check_sources(files)
    if problems or not files:
        sys.exit("Profile files in this repository are not valid:\n  " + "\n  ".join(problems or ["none found"]))
    user_dir = pick_user_dir(root, args.user_dir)
    {"status": cmd_status, "install": cmd_install, "uninstall": cmd_uninstall,
     "hook": cmd_hook}[args.command](args, user_dir, files)


if __name__ == "__main__":
    main()
