#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic)
"""Installer speed: hash cache, batched probes, one-command install check (docs/superpowers/specs/2026-11-23-installer-speed-design.md).

The printer is a small stand-in that understands the few shell commands SSHPrinter sends; it counts them.

Run:  python tests/test_install_speed.py
"""
import hashlib
import io
import json
import shlex
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import install  # noqa: E402


def digest(data):
    return hashlib.sha256(data).hexdigest()


class Remote:
    """A pretend printer: files, their identity (size, ctime, inode) and the units' states."""

    def __init__(self, files):
        self.files = dict(files)
        self.ctime = {p: "1000.000000001" for p in files}
        self.inode = {p: 100 + i for i, p in enumerate(files)}
        self.owner = {p: ("qidi", "netdev", "644") for p in files}
        self.units = {}
        self.commands = []
        self.uploads = {}
        self.lock = threading.Lock()
        self.clock = 1000

    # -- helpers the tests use
    def touch(self, path, data=None):
        """Another program changed the file."""
        if data is not None:
            self.files[path] = data
        self.clock += 1
        self.ctime[path] = "%d.000000001" % self.clock

    def count(self, word):
        return sum(1 for c in self.commands if c.startswith(word))

    # -- the shell
    def ident(self, path):
        return "%s|%d|%s|%d" % (path, len(self.files[path]), self.ctime[path], self.inode[path])

    def run(self, command, sudo=False, check=True, raw=False):
        with self.lock:
            self.commands.append(command)
        if command.startswith("mktemp"):
            return b"/tmp/q2t.test\n"
        if command.startswith("find "):
            paths = [t for t in shlex.split(command.split(" -maxdepth")[0])[1:] if t != "-L"]
            return "".join(self.ident(p) + "\n" for p in paths if p in self.files).encode()
        if command.startswith("sha256sum "):
            paths = shlex.split(command.split(" 2>/dev/null")[0])[1:]
            return "".join("%s  %s\n" % (digest(self.files[p]), p) for p in paths if p in self.files).encode()
        if command.startswith("stat -c "):
            paths = shlex.split(command.split(" 2>/dev/null")[0])[3:]
            return "".join("%s|%s|%s|%s\n" % ((p,) + self.owner[p]) for p in paths if p in self.files).encode()
        if command.startswith("for u in "):
            units = shlex.split(command.split(";")[0])[3:]
            return "".join("%s|%s\n" % (u, "|".join(self.units.get(u, ("missing", "", "")))) for u in units).encode()
        if command.startswith("for f in "):
            paths = shlex.split(command.split(";")[0])[3:]
            out = b""
            for p in paths:
                out += b"@@" + p.encode() + b"\n"
                out += (__import__("base64").b64encode(self.files[p]) if p in self.files else b"MISSING") + b"\n"
            return out
        if "install -o" in command:
            parts = shlex.split(command.split(" && ")[1])
            owner, group, mode, tmp, path = parts[2], parts[4], parts[6], parts[7], parts[8]
            self.touch(path, self.uploads[tmp])
            self.inode.setdefault(path, 900 + len(self.inode))
            self.owner[path] = (owner, group, mode)
            return ("%s  %s\n%s\n" % (digest(self.files[path]), path, self.ident(path))).encode()
        raise AssertionError("unexpected command: " + command)


class Sftp:
    def __init__(self, remote):
        self.remote = remote

    def putfo(self, fh, path):
        self.remote.uploads[path] = fh.read()


def make(files, cache=None, rehash=False):
    remote = Remote(files)
    p = install.SSHPrinter.__new__(install.SSHPrinter)
    p.client, p.password, p.sftp, p.staging = None, None, Sftp(remote), None
    p._run = remote.run
    p.use_hash_cache(cache if cache is not None else install.HashCache(None), rehash=rehash)
    return p, remote


FILES = {"/a/one": b"1" * 10, "/a/two": b"2" * 20, "/a/three": b"3" * 30}


class HashCacheTests(unittest.TestCase):
    def test_first_run_hashes_every_file_and_a_missing_file_is_none(self):
        p, r = make(FILES)
        got = p.sha_many(list(FILES) + ["/a/missing"])
        self.assertEqual(got, dict({k: digest(v) for k, v in FILES.items()}, **{"/a/missing": None}))
        self.assertGreaterEqual(r.count("sha256sum"), 1)

    def test_second_run_asks_only_for_the_identity_and_hashes_nothing(self):
        p, r = make(FILES)
        first = p.sha_many(list(FILES))
        before = r.count("sha256sum")
        second = p.sha_many(list(FILES))
        self.assertEqual(first, second)
        self.assertEqual(r.count("sha256sum"), before)
        self.assertEqual(r.count("find"), 2)

    def test_a_changed_file_is_hashed_again_and_the_others_are_not(self):
        p, r = make(FILES)
        p.sha_many(list(FILES))
        r.commands.clear()
        r.touch("/a/two", b"changed-content!!!!!!")
        got = p.sha_many(list(FILES))
        self.assertEqual(got["/a/two"], digest(b"changed-content!!!!!!"))
        hashed = [t for c in r.commands if c.startswith("sha256sum") for t in shlex.split(c.split(" 2>")[0])[1:]]
        self.assertEqual(hashed, ["/a/two"])

    def test_same_size_but_newer_ctime_is_hashed_again(self):
        p, r = make(FILES)
        p.sha_many(list(FILES))
        r.touch("/a/one", b"9" * 10)  # same length, different content, newer ctime
        self.assertEqual(p.sha_many(["/a/one"])["/a/one"], digest(b"9" * 10))

    def test_a_file_that_is_gone_is_none(self):
        p, r = make(FILES)
        p.sha_many(list(FILES))
        del r.files["/a/one"]
        self.assertIsNone(p.sha_many(["/a/one"])["/a/one"])

    def test_rehash_ignores_the_cache(self):
        cache = install.HashCache(None)
        p, r = make(FILES, cache)
        p.sha_many(list(FILES))
        r.commands.clear()
        p2, _ = make(FILES, cache, rehash=True)
        p2._run = r.run
        p2.sha_many(list(FILES))
        self.assertGreaterEqual(r.count("sha256sum"), 1)

    def test_cache_survives_in_a_file_and_a_broken_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json"
            cache = install.HashCache(path)
            p, r = make(FILES, cache)
            p.sha_many(list(FILES))
            cache.save()
            again = install.HashCache(path)
            p2, r2 = make(FILES, again)
            r2.ctime, r2.inode = dict(r.ctime), dict(r.inode)
            p2.sha_many(list(FILES))
            self.assertEqual(r2.count("sha256sum"), 0)
            path.write_text("{not json", encoding="utf-8")
            self.assertEqual(install.HashCache(path).data, {})
            path.write_text(json.dumps([1, 2]), encoding="utf-8")
            self.assertEqual(install.HashCache(path).data, {})

    def test_many_files_are_hashed_in_chunks_with_every_answer_kept(self):
        many = {"/m/f%03d" % i: bytes([i]) * (i + 1) for i in range(130)}
        p, r = make(many)
        got = p.sha_many(list(many))
        self.assertEqual(got, {k: digest(v) for k, v in many.items()})
        self.assertGreater(r.count("sha256sum"), 1)
        for c in r.commands:
            if c.startswith("sha256sum"):
                self.assertLessEqual(len(shlex.split(c.split(" 2>")[0])) - 1, install.HASH_CHUNK)

    def test_without_a_cache_the_old_way_still_works(self):
        remote = Remote(FILES)
        p = install.SSHPrinter.__new__(install.SSHPrinter)
        p.client, p.password, p.sftp, p.staging = None, None, Sftp(remote), None
        p._run = remote.run
        self.assertEqual(p.sha_many(list(FILES)), {k: digest(v) for k, v in FILES.items()})
        self.assertEqual(remote.count("find"), 0)


class InstallOneCommandTests(unittest.TestCase):
    def test_write_is_verified_in_the_same_command_and_the_cache_learns_it(self):
        p, r = make(FILES)
        p.sha_many(list(FILES))
        r.commands.clear()
        p.install(b"new-content", "/a/one", "qidi", "netdev", "644")
        self.assertEqual(r.count("sha256sum"), 0)      # no separate check
        self.assertEqual(r.count("mktemp"), 1)
        self.assertEqual(sum(1 for c in r.commands if "install -o" in c), 1)
        r.commands.clear()
        self.assertEqual(p.sha_many(["/a/one"])["/a/one"], digest(b"new-content"))
        self.assertEqual(r.count("sha256sum"), 0)      # known from the write itself

    def test_wrong_digest_after_write_is_an_error(self):
        p, r = make(FILES)
        real = r.run

        def liar(command, **kw):
            out = real(command, **kw)
            if "install -o" in command:
                return b"0" * 64 + b"  /a/one\n" + out.split(b"\n", 1)[1]
            return out
        p._run = liar
        with self.assertRaises(install.InstallError):
            p.install(b"x", "/a/one", "qidi", "netdev", "644")

    def test_remove_forgets_the_file(self):
        p, r = make(FILES)
        p.sha_many(list(FILES))
        p._run = lambda command, **kw: (r.files.pop("/a/one", None), b"")[1] if command.startswith("rm ") else r.run(command, **kw)
        p.remove("/a/one")
        self.assertNotIn("/a/one", p.hash_cache.data)


class BatchedProbeTests(unittest.TestCase):
    def test_all_units_are_asked_in_one_command_and_needs_uses_the_answer(self):
        p, r = make({})
        r.units = {"a.service": ("present", "enabled", "active"), "b.service": ("present", "disabled", "inactive")}
        p.prefetch_units(["a.service", "b.service", "c.service"])
        self.assertEqual(r.count("for u in"), 1)
        self.assertFalse(p.needs(["systemctl", "enable", "--now", "a.service"]))
        self.assertTrue(p.needs(["systemctl", "enable", "--now", "b.service"]))
        self.assertFalse(p.needs(["systemctl", "enable", "--now", "c.service"]))   # not on this printer: nothing to do
        self.assertTrue(p.needs(["systemctl", "disable", "--now", "a.service"]))
        self.assertEqual(r.count("for u in"), 1)

    def test_a_write_makes_the_next_answer_fresh(self):
        p, r = make({"/x": b"1"})
        r.units = {"a.service": ("present", "disabled", "inactive")}
        p.prefetch_units(["a.service"])
        self.assertTrue(p.needs(["systemctl", "enable", "--now", "a.service"]))
        r.units["a.service"] = ("present", "enabled", "active")
        p.install(b"2", "/x", "qidi", "netdev", "644")      # anything written drops the remembered states
        p.prefetch_units(["a.service"])
        self.assertFalse(p.needs(["systemctl", "enable", "--now", "a.service"]))


class ReadAndStatManyTests(unittest.TestCase):
    def test_read_many_returns_bytes_or_none_in_one_command(self):
        files = {"/c/one.cfg": b"a\r\nb\x00c", "/c/two.cfg": b"zz"}
        p, r = make(files)
        got = p.read_many(["/c/one.cfg", "/c/two.cfg", "/c/none.cfg"])
        self.assertEqual(got, {"/c/one.cfg": files["/c/one.cfg"], "/c/two.cfg": b"zz", "/c/none.cfg": None})
        self.assertEqual(r.count("for f in"), 1)

    def test_stat_many_matches_stat_for_each(self):
        p, r = make(FILES)
        r.owner["/a/two"] = ("root", "root", "755")
        got = p.stat_many(list(FILES) + ["/a/none"])
        self.assertEqual(got["/a/two"], ["root", "root", "755"])
        self.assertEqual(got["/a/one"], ["qidi", "netdev", "644"])
        self.assertIsNone(got["/a/none"])
        self.assertEqual(r.count("stat -c"), 1)


class UsedByThePlanTests(unittest.TestCase):
    def test_pending_actions_prefetches_the_units_once(self):
        class P:
            def __init__(self):
                self.prefetched, self.asked = [], []

            def prefetch_units(self, units):
                self.prefetched.append(sorted(units))

            def needs(self, action):
                self.asked.append(action)
                return True
        mods = [{"id": "m1", "actions": [["systemctl", "enable", "--now", "x.service"], ["daemon-reload"]]},
                {"id": "m2", "actions": [["systemctl", "disable", "--now", "y.service"]]}]
        p = P()
        install.pending_actions(p, mods, [])
        self.assertEqual(p.prefetched, [["x.service", "y.service"]])


if __name__ == "__main__":
    unittest.main()
