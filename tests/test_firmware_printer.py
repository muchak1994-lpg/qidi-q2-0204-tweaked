#!/usr/bin/env python3
"""Offline tests for tools/firmware.py and tools/printer.py (no download, no printer).

Run:  python tests/test_firmware_printer.py
"""
import hashlib
import io
import shutil
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import firmware as fw  # noqa: E402
import printer  # noqa: E402


def ar_archive(members):
    out = io.BytesIO()
    out.write(b"!<arch>\n")
    for name, data in members:
        header = ("%-16s%-12s%-6s%-6s%-8s%-10s" % (name + "/", "0", "0", "0", "100644", len(data))).encode()
        out.write(header + b"`\n" + data)
        if len(data) & 1:
            out.write(b"\n")
    return out.getvalue()


def fake_package(files):
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w:xz") as tf:
        for path, data in files.items():
            info = tarfile.TarInfo("." + path)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    deb = ar_archive([("debian-binary", b"2.0\n"), ("control.tar.xz", b"x" * 7),
                      ("data.tar.xz", tar_buf.getvalue())])
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(fw.SOC_NAME, deb)
        zf.writestr("firmware_manifest.json", "{}")
    return zbuf.getvalue()


class FirmwareTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.saved = (fw.STOCK, fw.DATA, fw.INDEX)
        fw.STOCK = self.tmp / "stock"
        fw.DATA = fw.STOCK / "data.tar.xz"
        fw.INDEX = fw.STOCK / "index.json"
        self.saved_files = fw.FILES
        fw.FILES = fw.STOCK / "files"
        self.files = {"/home/qidi/klipper/klippy/extras/fan.py": b"print('fan')\r\n",
                      "/home/qidi/QIDI_Client/bin/start.sh": b"#!/bin/sh\n"}
        self.zip = self.tmp / "pkg.zip"
        self.zip.write_bytes(fake_package(self.files))

    def tearDown(self):
        fw.STOCK, fw.DATA, fw.INDEX = self.saved
        fw.FILES = self.saved_files
        shutil.rmtree(self.tmp)

    def test_unpack_index_extract(self):
        fw.STOCK.mkdir(parents=True)
        fw.unpack_data(self.zip)
        index = fw.build_index()
        self.assertEqual(set(index["files"]), set(self.files))
        for path, data in self.files.items():
            self.assertEqual(index["files"][path]["sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual(fw.extract(path), data)
        with self.assertRaises(KeyError):
            fw.extract("/etc/passwd")

    def test_wrong_package_is_refused(self):
        saved = fw.ZIP_SHA256
        try:
            with self.assertRaises(SystemExit):
                fw.main(["fetch", "--zip", str(self.zip)])
        finally:
            fw.ZIP_SHA256 = saved
        self.assertFalse(fw.INDEX.exists())


class ClassifyTest(unittest.TestCase):
    def test_classify(self):
        index = {"/r/a.py": {"sha256": "1" * 64}, "/r/b.py": {"sha256": "2" * 64},
                 "/r/c.py": {"sha256": "3" * 64}, "/other/x": {"sha256": "4" * 64}}
        on_printer = {"/r/a.py": "1" * 64, "/r/b.py": "9" * 64, "/r/new.py": "5" * 64,
                      "/r/__pycache__/a.cpython-39.pyc": "6" * 64}
        rep = printer.classify(index, on_printer, ("/r",))
        self.assertEqual(rep["original"], ["/r/a.py"])
        self.assertEqual(rep["changed"], ["/r/b.py"])
        self.assertEqual(rep["missing"], ["/r/c.py"])
        self.assertEqual(rep["extra"], ["/r/new.py"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
