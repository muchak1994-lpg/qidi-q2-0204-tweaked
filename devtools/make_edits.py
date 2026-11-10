#!/usr/bin/env python3
"""(Developers) Turn "original file -> changed file" into [old, new] edits.

    python devtools/make_edits.py ORIGINAL CHANGED > edits.json

Each changed block gets just enough surrounding lines to be unique in the
original, so build.py can place it exactly. Line endings are kept as they are.
"""
import difflib
import json
import sys


def make_edits(a_text, b_text, min_context=1):
    a = a_text.splitlines(keepends=True)
    b = b_text.splitlines(keepends=True)
    ops = [op[1:] for op in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if op[0] != "equal"]
    groups = [[i1, i2, j1, j2] for i1, i2, j1, j2 in ops]

    def window(g):
        ctx = min_context
        while True:
            lo, hi = max(0, g[0] - ctx), min(len(a), g[1] + ctx)
            old = "".join(a[lo:hi])
            if old and a_text.count(old) == 1:
                return lo, hi
            if lo == 0 and hi == len(a):
                raise ValueError("cannot make a unique edit")
            ctx += 1

    while True:  # merge changes whose unique windows touch or overlap
        wins = [window(g) for g in groups]
        for k in range(1, len(groups)):
            if wins[k][0] <= wins[k - 1][1]:
                g0, g1 = groups[k - 1], groups[k]
                groups[k - 1:k + 1] = [[g0[0], g1[1], g0[2], g1[3]]]
                break
        else:
            break
    edits = []
    for (i1, i2, j1, j2), (lo, hi) in zip(groups, wins):
        old = "".join(a[lo:hi])
        new = "".join(a[lo:i1]) + "".join(b[j1:j2]) + "".join(a[i2:hi])
        edits.append([old, new])
    return edits


def main():
    a = open(sys.argv[1], encoding="utf-8", newline="").read()
    b = open(sys.argv[2], encoding="utf-8", newline="").read()
    edits = make_edits(a, b)
    text = a
    for old, new in edits:
        assert text.count(old) == 1
        text = text.replace(old, new, 1)
    assert text == b, "edits do not reproduce the changed file"
    json.dump(edits, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()


def make_edits_tokens(a_text, b_text, pattern=r"(?<=[;}])"):
    """Same as make_edits, for minified files with few line breaks: the text
    is cut into tokens after ';' and '}' instead of into lines."""
    import re
    sep = "\x00"
    a = sep.join(re.split(pattern, a_text))
    b = sep.join(re.split(pattern, b_text))
    if sep in a_text or sep in b_text:
        raise ValueError("unexpected NUL in text")
    lines_a = a.replace("\n", "\x01").replace(sep, "\n")
    lines_b = b.replace("\n", "\x01").replace(sep, "\n")
    out = []
    for old, new in make_edits(lines_a + "\n", lines_b + "\n"):
        old = old.replace("\n", "").replace("\x01", "\n")
        new = new.replace("\n", "").replace("\x01", "\n")
        out.append([old, new])
    return out
