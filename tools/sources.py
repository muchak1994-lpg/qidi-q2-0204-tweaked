#!/usr/bin/env python3
"""QIDI Q2 02.04 Tweaked - third-party files from their public origin.

Some modules need files that are not in QIDI's package (the camera AI is
missing Python libraries). They are not stored in this repository either:
modules/<id>/sources.json lists, for every file, the public package it comes
from (a PyPI wheel or a Debian .deb), that package's SHA-256, the member inside
it and the SHA-256 of the member. This tool downloads each package once into
downloads/, checks both hashes and returns the files.

    python tools/sources.py fetch modules/ai-libraries/sources.json
Standard library only, Python 3.9+.
"""
import hashlib
import io
import json
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOWNLOADS = REPO / "downloads" / "sources"
PYPI_JSON = "https://pypi.org/pypi/%s/%s/json"


def _get(url, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": "qidi-q2-0204-tweaked"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def wheel_url(filename):
    name, version = filename.split("-")[:2]
    info = json.loads(_get(PYPI_JSON % (name, version), timeout=60))
    for entry in info["urls"]:
        if entry["filename"] == filename:
            return entry["url"]
    raise LookupError("%s is not on PyPI" % filename)


def package(entry):
    """Path of the downloaded package file, checked against its SHA-256."""
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    path = DOWNLOADS / entry["file"]
    if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == entry["file_sha256"]:
        return path
    url = entry.get("url") or wheel_url(entry["file"])
    print("  downloading", entry["file"])
    data = _get(url)
    digest = hashlib.sha256(data).hexdigest()
    if digest != entry["file_sha256"]:
        raise ValueError("%s: SHA-256 %s, expected %s" % (entry["file"], digest, entry["file_sha256"]))
    path.write_bytes(data)
    return path


def deb_data(path):
    """The data.tar.* member of a .deb as an open tarfile."""
    raw = path.read_bytes()
    if raw[:8] != b"!<arch>\n":
        raise ValueError("%s is not a .deb" % path.name)
    pos = 8
    while pos + 60 <= len(raw):
        header = raw[pos:pos + 60]
        name = header[:16].decode("ascii").strip().rstrip("/")
        size = int(header[48:58].decode("ascii").strip())
        start = pos + 60
        if name.startswith("data.tar"):
            return tarfile.open(fileobj=io.BytesIO(raw[start:start + size]))
        pos = start + size + (size & 1)
    raise ValueError("%s: no data.tar member" % path.name)


def fetch(sources_path):
    """Return {printer_path: bytes} for every entry of a sources.json."""
    entries = json.loads(Path(sources_path).read_text(encoding="utf-8"))
    by_file = {}
    for entry in entries:
        by_file.setdefault(entry["file"], []).append(entry)
    out = {}
    for filename, items in sorted(by_file.items()):
        path = package(items[0])
        if items[0]["kind"] == "pypi-wheel":
            with zipfile.ZipFile(path) as zf:
                read = {e["member"]: zf.read(e["member"]) for e in items}
        elif items[0]["kind"] == "debian-deb":
            with deb_data(path) as tf:
                read = {}
                for e in items:
                    for name in (e["member"], "./" + e["member"]):
                        try:
                            read[e["member"]] = tf.extractfile(name).read()
                            break
                        except KeyError:
                            continue
        else:
            raise ValueError("unknown kind " + items[0]["kind"])
        for e in items:
            data = read.get(e["member"])
            if data is None or hashlib.sha256(data).hexdigest() != e["sha256"]:
                raise ValueError("%s: member %s does not match" % (filename, e["member"]))
            out[e["target"]] = data
    return out


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 2 or argv[0] != "fetch":
        sys.exit(__doc__)
    files = fetch(argv[1])
    print("OK: %d files, all SHA-256 checked" % len(files))


if __name__ == "__main__":
    main()
