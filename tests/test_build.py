#!/usr/bin/env python3
"""Offline tests for tools/build.py (no QIDI files needed).

Run:  python tests/test_build.py
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "devtools"))
import build  # noqa: E402
from make_edits import make_edits  # noqa: E402

STOCK = {"/k/a.py": "x = 1\r\ny = 2\r\nz = 3\r\n".encode()}


def reader(path):
    return STOCK[path]


def mod(mid, order, edits):
    return {"id": mid, "order": order, "files": {"/k/a.py": {"edits": edits}}}


class BuildTest(unittest.TestCase):
    def test_modules_apply_in_order_on_the_original(self):
        files, owners = build.build([mod("one", 1, [["y = 2\r\n", "y = 20\r\n"]]),
                                     mod("two", 2, [["y = 20\r\nz", "y = 20\r\nw = 0\r\nz"]])],
                                    stock_reader=reader)
        self.assertEqual(files["/k/a.py"], b"x = 1\r\ny = 20\r\nw = 0\r\nz = 3\r\n")
        self.assertEqual(owners["/k/a.py"], ["one", "two"])

    def test_edit_must_match_exactly_once(self):
        with self.assertRaises(build.BuildError):
            build.build([mod("bad", 1, [["not there", "x"]])], stock_reader=reader)
        with self.assertRaises(build.BuildError):
            build.build([mod("dup", 1, [[" = ", "="]])], stock_reader=reader)

    def test_python_must_compile(self):
        with self.assertRaises(build.BuildError):
            build.build([mod("syntax", 1, [["y = 2", "y = ("]])], stock_reader=reader)

    def test_wrong_original_is_refused(self):
        m = mod("pinned", 1, [])
        m["files"]["/k/a.py"]["stock_sha256"] = "0" * 64
        with self.assertRaises(build.BuildError):
            build.build([m], stock_reader=reader)

    def test_config_edits_follow_file_line_ends(self):
        for data in (b"[a]\r\nx: 1\r\n", b"[a]\nx: 1\n"):
            out = build.apply_edits(data, [["x: 1\n", "x: 2\n"]], "t", any_eol=True)
            self.assertEqual(out, data.replace(b"1", b"2"))

    def test_new_file_from_module(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        (d / "new.cfg").write_bytes(b"[x]\n")
        m = {"id": "n", "order": 1, "_dir": d, "files": {"/k/new.cfg": {"source": "new.cfg"}}}
        files, owners = build.build([m], stock_reader=reader)
        self.assertEqual(files["/k/new.cfg"], b"[x]\n")

    def test_byte_edits(self):
        out = build.apply_byte_edits(b"\x00\x01\x02\x03", [[1, "0102", "aabb"]], "t")
        self.assertEqual(out, b"\x00\xaa\xbb\x03")
        with self.assertRaises(build.BuildError):
            build.apply_byte_edits(b"\x00\x01", [[0, "ff", "00"]], "t")

    def test_make_edits_reproduces_target(self):
        a = "".join("line %d\r\n" % i for i in range(50))
        b = a.replace("line 10\r\n", "line 10\r\nnew\r\n").replace("line 40\r\n", "")
        text = a
        for old, new in make_edits(a, b):
            self.assertEqual(text.count(old), 1)
            text = text.replace(old, new, 1)
        self.assertEqual(text, b)


if __name__ == "__main__":
    unittest.main(verbosity=2)
