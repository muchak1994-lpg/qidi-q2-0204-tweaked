#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""The tools must run on Python 3.9 (the CI's oldest version), also when the tests run on a newer one.

Path.write_text() and Path.read_text() got a `newline` argument only in Python 3.10 (release 1.3.0 shipped
`orca_profiles.py hook` with it and failed on 3.9 in CI, while the local runs used 3.14).

Run:  python tests/test_py39_compat.py
"""
import ast
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# method name -> keyword arguments that do not exist on Python 3.9
TOO_NEW = {"write_text": {"newline"}, "read_text": {"newline"}}


def too_new_calls(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in TOO_NEW:
            used = {k.arg for k in node.keywords} & TOO_NEW[node.func.attr]
            if used:
                bad.append("%s:%d %s(%s=...)" % (path.relative_to(REPO), node.lineno, node.func.attr, ", ".join(sorted(used))))
    return bad


class Py39Test(unittest.TestCase):
    def test_no_keyword_arguments_newer_than_python_3_9(self):
        files = sorted((REPO / "tools").glob("*.py")) + sorted((REPO / "tests").glob("*.py")) \
            + sorted((REPO / "modules").glob("*/files/**/*.py"))
        bad = [line for f in files for line in too_new_calls(f)]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
