#!/usr/bin/env python3
"""QIDI Q2 02.04 Tweaked - OrcaSlicer profiles (add-only).

Adds the project's printer and process profiles to OrcaSlicer's user folder.
It never overwrites or deletes a file it did not add itself:

* a file with the same name that already exists is skipped and reported;
* every added file is recorded (with its SHA-256) in a manifest kept in the
  Orca user folder, so `uninstall` removes only those files, and only if they
  are unchanged (a profile you edited afterwards is left alone);
* before any change, the current machine/ and process/ folders are zipped to
  backups/ next to this repository.

Without --apply every command only shows what it would do.

Usage:
    python tools/orca_profiles.py status
    python tools/orca_profiles.py install            (dry run)
    python tools/orca_profiles.py install --apply
    python tools/orca_profiles.py uninstall --apply

OrcaSlicer must be closed while installing or uninstalling.
Standard library only, Python 3.8+.
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

PROJECT = "qidi-q2-0204-tweaked"
MANIFEST_NAME = "." + PROJECT + "-orca-manifest.json"
REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "orca-profiles"
BACKUPS = REPO / "backups"
KINDS = ("machine", "process")
FORBIDDEN_KEYS = ("print_host", "printhost_apikey", "print_host_webui")


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
            out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True,
                                 text=True, timeout=30).stdout.lower()
        else:
            out = subprocess.run(["ps", "-A", "-o", "comm="], capture_output=True,
                                 text=True, timeout=30).stdout.lower()
    except Exception:
        return None
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
        if data.get("name") != stem:
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
    print("OrcaSlicer has several user folders (\"default\" or an account number):")
    for i, d in enumerate(dirs, 1):
        print("  %d) %s" % (i, d.name))
    if not sys.stdin.isatty():
        sys.exit("Choose one with --user-dir NAME.")
    answer = input("Which one? [1-%d]: " % len(dirs)).strip()
    if not answer.isdigit() or not 1 <= int(answer) <= len(dirs):
        sys.exit("No folder chosen, nothing changed.")
    return dirs[int(answer) - 1]


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
        for kind in KINDS:
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


def cmd_install(args, user_dir, files):
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
    print("Done. Start OrcaSlicer: printers \"... (Tweaked)\" and processes \"[TL] ...\" are in the lists.")


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


def main(argv=None):
    parser = argparse.ArgumentParser(description="Add (never overwrite) the QIDI Q2 02.04 Tweaked OrcaSlicer profiles.")
    parser.add_argument("command", choices=("status", "install", "uninstall"))
    parser.add_argument("--apply", action="store_true", help="really change files (default: dry run)")
    parser.add_argument("--orca-dir", help="OrcaSlicer data folder (default: auto-detect)")
    parser.add_argument("--user-dir", help='user profile folder inside user/ ("default" or an account number)')
    parser.add_argument("--skip-running-check", action="store_true", help="do not check that OrcaSlicer is closed")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    files = source_files()
    problems = check_sources(files)
    if problems or not files:
        sys.exit("Profile files in this repository are not valid:\n  " + "\n  ".join(problems or ["none found"]))
    root = Path(args.orca_dir) if args.orca_dir else default_orca_root()
    user_dir = pick_user_dir(root, args.user_dir)
    {"status": cmd_status, "install": cmd_install, "uninstall": cmd_uninstall}[args.command](args, user_dir, files)


if __name__ == "__main__":
    main()
