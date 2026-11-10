#!/usr/bin/env python3
"""QIDI Q2 02.04 Tweaked - the official 01.01.02.04 firmware package.

The project does not ship any QIDI file. Every module that changes a printer
file starts from the original, taken from QIDI's own public package:

    python tools/firmware.py fetch        download (or reuse) and verify the package
    python tools/firmware.py fetch --zip PATH   use a copy you already downloaded
    python tools/firmware.py status

`fetch` checks the SHA-256 of the whole package, unpacks the system part
(a Debian package), and writes work/stock/index.json: the SHA-256 of every
file in it. Single files are extracted on demand by the other modules
(`extract()` below), so nothing else is unpacked to your disk.

Standard library only, Python 3.8+.
"""
import argparse
import hashlib
import json
import lzma
import shutil
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

VERSION = "01.01.02.04"
URL = ("https://public-cdn.qidimaker.com/upgrade/3DPrinter/QD_Q2/01.01.02.04/"
       "nrpolyn8hx/QD_Q2_01.01.02.04_20260804_Release.zip")
ZIP_NAME = "QD_Q2_01.01.02.04_20260804_Release.zip"
ZIP_SHA256 = "92308ee19ddd49b3e8229118a4950d6f0dec993a5e99709e4c88f7e22b89092e"
ZIP_BYTES = 242880638
SOC_NAME = "QD_Q2_SOC_01.01.02.04_20260804_Release_NA"
# /home/qidi/update/firmware_manifest.json on a printer running 01.01.02.04
MANIFEST_SHA256 = "e1ed69645b01446733bbb19916d31d5f67d52c730dfe732470067b24376f45d1"

REPO = Path(__file__).resolve().parent.parent
DOWNLOADS = REPO / "downloads"
STOCK = REPO / "work" / "stock"
INDEX = STOCK / "index.json"
DATA = STOCK / "data.tar.xz"
FILES = STOCK / "files"


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def download(target):
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    print("Downloading the official package from QIDI (%d MB):" % (ZIP_BYTES // 1000000))
    print(" ", URL)
    req = urllib.request.Request(URL, headers={"User-Agent": "qidi-q2-0204-tweaked"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(part, "wb") as out:
        done, last = 0, 0.0
        while True:
            block = resp.read(1 << 20)
            if not block:
                break
            out.write(block)
            done += len(block)
            if time.time() - last > 2:
                last = time.time()
                print("  %3d%%" % (done * 100 // ZIP_BYTES), end="\r", flush=True)
    print("  100%")
    part.replace(target)


def ar_members(fh):
    """Yield (name, offset, size) of a Unix ar archive (a .deb)."""
    if fh.read(8) != b"!<arch>\n":
        raise ValueError("not an ar/deb archive")
    while True:
        header = fh.read(60)
        if len(header) < 60:
            return
        name = header[:16].decode("ascii").strip().rstrip("/")
        size = int(header[48:58].decode("ascii").strip())
        offset = fh.tell()
        yield name, offset, size
        fh.seek(offset + size + (size & 1))


def unpack_data(zip_path):
    """Copy data.tar.xz out of the SOC .deb inside the zip to work/stock/."""
    STOCK.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf, zf.open(SOC_NAME) as soc:
        raw = soc  # zipfile members can seek forward (Python 3.7+)
        for name, offset, size in ar_members(raw):
            if name == "data.tar.xz":
                raw.seek(offset)
                with open(DATA, "wb") as out:
                    left = size
                    while left:
                        block = raw.read(min(left, 1 << 20))
                        if not block:
                            raise ValueError("truncated data.tar.xz")
                        out.write(block)
                        left -= len(block)
                return
    raise ValueError("data.tar.xz not found in " + SOC_NAME)


def build_index():
    files = {}
    with tarfile.open(DATA, "r:xz") as tf:
        for member in tf:
            if member.isfile():
                path = "/" + member.name.lstrip("./")
                h = hashlib.sha256()
                fh = tf.extractfile(member)
                for block in iter(lambda: fh.read(1 << 20), b""):
                    h.update(block)
                files[path] = {"sha256": h.hexdigest(), "size": member.size, "mode": "%o" % member.mode}
    index = {"firmware": VERSION, "package_sha256": ZIP_SHA256, "files": files}
    INDEX.write_text(json.dumps(index, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return index


def load_index():
    if not INDEX.is_file():
        sys.exit("The official 02.04 package is not prepared yet. Run:  python tools/firmware.py fetch")
    return json.loads(INDEX.read_text(encoding="utf-8"))


def extract(printer_path):
    """Return the original bytes of one printer file, checked against the index.

    Files are cached in work/stock/files/ so the big archive is read once."""
    return extract_many([printer_path])[printer_path]


def extract_many(paths):
    index = load_index()
    result, missing = {}, []
    for path in paths:
        entry = index["files"].get(path)
        if entry is None:
            raise KeyError("not in the official 02.04 package: " + path)
        cached = FILES / path.lstrip("/")
        if cached.is_file():
            data = cached.read_bytes()
            if hashlib.sha256(data).hexdigest() == entry["sha256"]:
                result[path] = data
                continue
        missing.append(path)
    if missing:
        wanted = {"." + p: p for p in missing}
        with tarfile.open(DATA, "r:xz") as tf:
            for member in tf:
                if member.name in wanted:
                    path = wanted.pop(member.name)
                    data = tf.extractfile(member).read()
                    if hashlib.sha256(data).hexdigest() != index["files"][path]["sha256"]:
                        raise ValueError("work/stock is damaged; run: python tools/firmware.py fetch --force")
                    cached = FILES / path.lstrip("/")
                    cached.parent.mkdir(parents=True, exist_ok=True)
                    cached.write_bytes(data)
                    result[path] = data
                    if not wanted:
                        break
    return result


def cmd_fetch(args):
    if args.zip:
        zip_path = Path(args.zip)
    else:
        zip_path = DOWNLOADS / ZIP_NAME
        if not zip_path.is_file() or args.force:
            download(zip_path)
    print("Checking", zip_path)
    if not zip_path.is_file():
        sys.exit("File not found: %s" % zip_path)
    digest = sha256_file(zip_path)
    if digest != ZIP_SHA256:
        sys.exit("This is not the official 01.01.02.04 package (SHA-256 %s).\nExpected %s.\n"
                 "Delete it and run fetch again." % (digest, ZIP_SHA256))
    print("  SHA-256 OK - official QIDI Q2 01.01.02.04")
    if INDEX.is_file() and DATA.is_file() and not args.force:
        print("Already prepared:", INDEX)
        return
    print("Unpacking the system part (about a minute)...")
    if STOCK.exists():
        shutil.rmtree(STOCK)
    unpack_data(zip_path)
    index = build_index()
    print("Ready: %d original files indexed in %s" % (len(index["files"]), INDEX))


def cmd_status(args):
    zip_path = DOWNLOADS / ZIP_NAME
    print("Package:", zip_path if zip_path.is_file() else "not downloaded")
    if INDEX.is_file():
        index = json.loads(INDEX.read_text(encoding="utf-8"))
        print("Prepared: %d original files (firmware %s)" % (len(index["files"]), index["firmware"]))
    else:
        print("Prepared: no - run: python tools/firmware.py fetch")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Get and verify the official QIDI Q2 01.01.02.04 package.")
    parser.add_argument("command", choices=("fetch", "status"))
    parser.add_argument("--zip", help="use this already downloaded official package")
    parser.add_argument("--force", action="store_true", help="download/unpack again")
    args = parser.parse_args(argv)
    {"fetch": cmd_fetch, "status": cmd_status}[args.command](args)


if __name__ == "__main__":
    main()
