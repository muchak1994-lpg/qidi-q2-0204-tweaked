#!/usr/bin/env python3
"""QIDI Q2 02.04 Tweaked - build the patched printer files on the PC.

Every module in modules/<id>/module.json lists, per printer file, text edits
([old, new] pairs), or a new file of this project ("source").

Files marked "base": "printer" (configuration files that also hold your own
calibration, e.g. printer.cfg) are built here from the original for checking
only; the installer applies the same edits to the file on your printer, so
your calibration stays. The build starts from the ORIGINAL file taken from the
official 01.01.02.04 package (tools/firmware.py), applies the edits of every
selected module in module order, and writes the result to work/build/.

Each "old" text must occur exactly once at the moment it is applied, so an
edit can never land in the wrong place; otherwise the build stops. Python
files are compiled as a check. Nothing is sent to the printer here.

    python tools/build.py                 build all modules
    python tools/build.py --only 23-hotend-fan-hysteresis
    python tools/build.py --list
Standard library only, Python 3.8+.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import firmware  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
MODULES = REPO / "modules"
BUILD = REPO / "work" / "build"
LOCK = MODULES / "LOCK.json"


class BuildError(Exception):
    pass


def load_modules():
    mods = []
    for path in sorted(MODULES.glob("*/module.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        data["_dir"] = path.parent
        if data.get("id") != path.parent.name:
            raise BuildError("%s: id %r differs from folder name" % (path, data.get("id")))
        mods.append(data)
    mods.sort(key=lambda m: (m.get("order", 1000), m["id"]))
    return mods


def apply_edits(data, edits, label, any_eol=False):
    """Apply [old, new] edits; each old must occur exactly once.

    any_eol: the edits are stored with LF line ends and follow the file's own
    line ends (configuration files are CRLF from QIDI but LF once Klipper's
    SAVE_CONFIG rewrote them)."""
    text = data.decode("utf-8")
    crlf = any_eol and text.count("\r\n") * 2 > text.count("\n")
    for i, (old, new) in enumerate(edits, 1):
        if any_eol:
            old, new = old.replace("\r\n", "\n"), new.replace("\r\n", "\n")
            if crlf:
                old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
        count = text.count(old)
        if count != 1:
            raise BuildError("%s, edit %d: the original text was found %d times (must be exactly 1)"
                             % (label, i, count))
        text = text.replace(old, new, 1)
    return text.encode("utf-8")


def apply_byte_edits(data, edits, label):
    """[offset, old_hex, new_hex] edits for binary files; old must match exactly."""
    buf = bytearray(data)
    for i, (offset, old_hex, new_hex) in enumerate(edits, 1):
        old, new = bytes.fromhex(old_hex), bytes.fromhex(new_hex)
        if len(old) != len(new) or bytes(buf[offset:offset + len(old)]) != old:
            raise BuildError("%s, byte edit %d: original bytes not found at %d" % (label, i, offset))
        buf[offset:offset + len(old)] = new
    return bytes(buf)


def build(selected, stock_reader=None, out_dir=None, with_sources=True):
    """Return {printer_path: bytes} for the selected modules (in module order)."""
    if stock_reader is None:
        paths = sorted({p for m in selected for p, spec in m.get("files", {}).items()
                        if "source" not in spec and "generator" not in spec})
        cache = firmware.extract_many(paths) if paths else {}
        stock_reader = cache.__getitem__
    files = {}
    owners = {}
    for mod in selected:
        for path, spec in mod.get("files", {}).items():
            if "source" in spec:  # a new file that belongs to this project
                if path in files:
                    raise BuildError("%s: %s is already built by %s" % (mod["id"], path, owners[path]))
                files[path] = (mod["_dir"] / spec["source"]).read_bytes()
                owners[path] = [mod["id"]]
                continue
            if "generator" in spec:  # rebuilt from official packages by a tool (the screen program)
                if path in files:
                    raise BuildError("%s: %s is already built by %s" % (mod["id"], path, owners[path]))
                if spec["generator"] != "screen":
                    raise BuildError("%s: unknown generator %s" % (mod["id"], spec["generator"]))
                import screen
                files[path] = screen.build()
                owners[path] = [mod["id"]]
                continue
            if path not in files:
                original = stock_reader(path)
                if "stock_sha256" in spec and hashlib.sha256(original).hexdigest() != spec["stock_sha256"]:
                    raise BuildError("%s: original %s is not the 02.04 file" % (mod["id"], path))
                files[path] = original
            if spec.get("edits"):
                files[path] = apply_edits(files[path], spec["edits"], "%s: %s" % (mod["id"], path),
                                          any_eol=spec.get("base") == "printer")
            if spec.get("byte_edits"):
                files[path] = apply_byte_edits(files[path], spec["byte_edits"], "%s: %s" % (mod["id"], path))
            if "result_sha256" in spec and hashlib.sha256(files[path]).hexdigest() != spec["result_sha256"]:
                raise BuildError("%s: %s has an unexpected result" % (mod["id"], path))
            owners.setdefault(path, []).append(mod["id"])
    third_party = set()  # library files from sources.json: checked by hash, not compiled here
    for mod in selected:
        if with_sources and mod.get("sources"):
            import sources
            for path, data in sources.fetch(mod["_dir"] / mod["sources"]).items():
                if path in files:
                    raise BuildError("%s: %s is already built by %s" % (mod["id"], path, owners[path]))
                files[path] = data
                owners[path] = [mod["id"]]
                third_party.add(path)
    for path, data in files.items():
        if path.endswith(".py") and path not in third_party:
            try:
                compile(data, path, "exec")
            except SyntaxError as exc:
                raise BuildError("%s does not compile after %s: %s" % (path, ", ".join(owners[path]), exc))
    if out_dir is not None:
        manifest = {}
        for path, data in files.items():
            target = Path(out_dir) / path.lstrip("/")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            manifest[path] = {"sha256": hashlib.sha256(data).hexdigest(), "modules": owners[path]}
        Path(out_dir, "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n",
                                                  encoding="utf-8")
    return files, owners


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build the patched 02.04 files on the PC.")
    parser.add_argument("--only", action="append", help="build only this module (repeatable)")
    parser.add_argument("--list", action="store_true", help="list modules and exit")
    parser.add_argument("--update-lock", action="store_true", help="(developers) record the result in modules/LOCK.json")
    args = parser.parse_args(argv)
    try:
        mods = load_modules()
        if args.list:
            for m in mods:
                print("%-36s %s" % (m["id"], m.get("title", "")))
            return 0
        selected = [m for m in mods if not args.only or m["id"] in args.only]
        missing = set(args.only or []) - {m["id"] for m in mods}
        if missing:
            raise BuildError("unknown module(s): " + ", ".join(sorted(missing)))
        files, owners = build(selected, out_dir=BUILD)
    except BuildError as exc:
        print("BUILD FAILED:", exc)
        return 1
    result = {p: hashlib.sha256(d).hexdigest() for p, d in files.items()}
    for path in sorted(result):
        print("  %s  %s  (%s)" % (result[path][:12], path, ", ".join(owners[path])))
    if not args.only:
        if args.update_lock:
            LOCK.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
            print("LOCK.json updated")
        elif LOCK.is_file():
            lock = json.loads(LOCK.read_text(encoding="utf-8"))
            if lock != result:
                print("BUILD FAILED: result differs from modules/LOCK.json")
                return 1
            print("Matches modules/LOCK.json")
    print("Built %d file(s) from %d module(s) into %s" % (len(files), len(selected), BUILD))
    return 0


if __name__ == "__main__":
    sys.exit(main())
