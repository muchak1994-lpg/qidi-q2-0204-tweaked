#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""Optional Tailscale step of the installer, against a stand-in printer and a stand-in download server.

Run:  python tests/test_tailscale.py
"""
import hashlib
import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import tailscale_setup as ts  # noqa: E402


def tarball():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, data in (("tailscale", b"CLI"), ("tailscaled", b"DAEMON"),
                           ("systemd/tailscaled.service", b"[Unit]\n")):
            info = tarfile.TarInfo("tailscale_1.2.3_arm64/" + name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


TGZ = tarball()


def server(tamper=False):
    def get(url, timeout=60):
        if url == ts.INDEX_URL:
            return json.dumps({"TarballsVersion": "1.2.3", "Tarballs": {"arm64": "t_arm64.tgz"}}).encode()
        if url.endswith(".sha256"):
            return (hashlib.sha256(TGZ).hexdigest() + "\n").encode()
        return TGZ + (b"x" if tamper else b"")
    return get


class Printer:
    def __init__(self, installed=False, state=None, tun=True):
        self.files, self.commands = {}, []
        self.installed, self.state, self.tun = installed, state, tun

    def _run(self, command, sudo=False, check=True):
        self.commands.append(command)
        if command.startswith("command -v tailscale"):
            ours = ts.MARKER.encode() in self.files.get(ts.DEFAULTS, b"")
            st = json.dumps({"BackendState": self.state}) if self.installed else ""
            return ("%s\n%s\n%s" % ("yes" if self.installed else "no", "ours" if ours else "theirs", st)).encode()
        if command == "uname -m":
            return b"aarch64\n"
        if "/dev/net/tun" in command:
            return b"tun\n" if self.tun else b"none\n"
        if "enable --now tailscaled" in command:
            self.installed, self.state = True, "NeedsLogin"
        if "tailscale up" in command:
            return b"To authenticate, visit:\n\n\thttps://login.tailscale.com/a/abc123\n\n"
        if "disable --now tailscaled" in command:
            self.installed = False
            for f in list(ts.BINARIES.values()) + [ts.UNIT, ts.DEFAULTS]:
                self.files.pop(f, None)
        return b""

    def install(self, data, path, owner, group, mode):
        self.files[path] = data


def answers(*seq):
    it = iter(seq)
    return lambda prompt: next(it)


class TailscaleTest(unittest.TestCase):
    def setUp(self):
        self.downloads = Path(tempfile.mkdtemp())
        self.saved = ts.DOWNLOADS
        ts.DOWNLOADS = self.downloads

    def tearDown(self):
        ts.DOWNLOADS = self.saved

    def offer(self, p, *replies, mode="ask", get=None):
        return ts.offer(p, mode, read=answers(*replies), get=get or server())

    def test_yes_yes_installs_and_shows_link(self):
        p = Printer()
        self.offer(p, "", "")  # Enter = yes, Enter = yes
        self.assertEqual(p.files[ts.BINARIES["tailscaled"]], b"DAEMON")
        self.assertEqual(p.files[ts.BINARIES["tailscale"]], b"CLI")
        self.assertIn(ts.MARKER.encode(), p.files[ts.DEFAULTS])
        self.assertIn(b'FLAGS=""', p.files[ts.DEFAULTS])
        self.assertTrue(any("tailscale up --accept-dns=false" in c for c in p.commands))

    def test_no_installs_nothing(self):
        p = Printer()
        self.offer(p, "n")
        self.assertEqual(p.files, {})

    def test_install_but_log_in_later(self):
        p = Printer()
        self.offer(p, "y", "n")
        self.assertIn(ts.BINARIES["tailscaled"], p.files)
        self.assertFalse(any("tailscale up" in c for c in p.commands))

    def test_no_tun_uses_userspace(self):
        p = Printer(tun=False)
        self.offer(p, "", "n")
        self.assertIn(b'FLAGS="--tun=userspace-networking"', p.files[ts.DEFAULTS])

    def test_bad_download_refused(self):
        p = Printer()
        with self.assertRaises(ValueError):
            self.offer(p, "", "", get=server(tamper=True))
        self.assertEqual(p.files, {})

    def test_already_logged_in_asks_nothing(self):
        p = Printer(installed=True, state="Running")
        self.offer(p)  # no answers available: would raise StopIteration if it asked
        self.assertFalse(any("tailscale up" in c for c in p.commands))

    def test_mode_no(self):
        p = Printer()
        ts.offer(p, "no", read=answers(), get=server())
        self.assertEqual(p.commands, [])

    def test_uninstall_only_ours(self):
        p = Printer()
        self.offer(p, "", "n")
        self.assertTrue(ts.uninstall(p))
        self.assertEqual(p.files, {})
        theirs = Printer(installed=True, state="Running")
        self.assertFalse(ts.uninstall(theirs))
        self.assertFalse(any("disable --now" in c for c in theirs.commands))

    def test_login_link_parsed(self):
        self.assertEqual(ts.login(Printer(installed=True)), "https://login.tailscale.com/a/abc123")


if __name__ == "__main__":
    unittest.main()
