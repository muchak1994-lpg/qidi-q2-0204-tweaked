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


MOONRAKER = (b"[server]\nhost: 0.0.0.0\n\n[authorization]\ntrusted_clients:\n    10.0.0.0/8\n"
             b"    192.168.0.0/16\ncors_domains:\n    *.local\n")


def server(tamper=False):
    def get(url, timeout=60):
        return TGZ + (b"x" if tamper else b"")
    return get


class Printer:
    def __init__(self, installed=False, ours=False, state=None, tun="tun", version=None, running=None):
        self.files = {ts.MOONRAKER_CONF: MOONRAKER}
        if ours:
            self.files[ts.DEFAULTS] = ts.defaults_file(False)
        self.commands = []
        self.installed, self.state, self.tun = installed, state, tun
        self.version = version or (ts.VERSION if installed else None)
        self.running = installed if running is None else running

    def read(self, path):
        return self.files.get(path)

    def stat(self, path):
        return ["qidi", "netdev", "644"] if path in self.files else None

    def _run(self, command, sudo=False, check=True):
        self.commands.append(command)
        if command.startswith("command -v tailscale"):
            ours = ts.MARKER.encode() in self.files.get(ts.DEFAULTS, b"")
            st = '{"Version": "x", "BackendState": "%s", "Self": {}}' % self.state if self.installed else ""
            return ("%s\n%s\n%s\n%s\n%s" % ("yes" if self.installed else "no", "ours" if ours else "theirs",
                                            "active" if self.running else "inactive",
                                            (self.version + "\n  tailscale commit: abc") if self.installed else "",
                                            st)).encode()
        if command == "uname -m":
            return b"aarch64\n"
        if "/dev/net/tun" in command:
            return (self.tun + "\n").encode()
        if "systemctl restart tailscaled" in command:
            self.installed, self.running, self.version = True, True, ts.VERSION
            self.state = self.state or "NeedsLogin"
        if "tailscale up" in command:
            return b"To authenticate, visit:\n\n\thttps://login.tailscale.com/a/abc123\n\n"
        if "disable --now tailscaled" in command:
            self.installed = self.running = False
            for f in list(ts.BINARIES.values()) + [ts.UNIT, ts.DEFAULTS, ts.MODULES_LOAD]:
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
        self.saved = ts.DOWNLOADS, dict(ts.SHA256)
        ts.DOWNLOADS = self.downloads
        ts.SHA256["arm64"] = hashlib.sha256(TGZ).hexdigest()

    def tearDown(self):
        ts.DOWNLOADS, saved = self.saved
        ts.SHA256.clear()
        ts.SHA256.update(saved)

    def offer(self, p, *replies, mode="ask", get=None):
        return ts.offer(p, mode, read=answers(*replies), get=get or server())

    def test_yes_yes_installs_trusts_and_shows_link(self):
        p = Printer()
        self.offer(p, "", "")  # Enter = yes, Enter = yes
        self.assertEqual(p.files[ts.BINARIES["tailscaled"]], b"DAEMON")
        self.assertEqual(p.files[ts.BINARIES["tailscale"]], b"CLI")
        self.assertIn(ts.MARKER.encode(), p.files[ts.DEFAULTS])
        self.assertIn(b'FLAGS=""', p.files[ts.DEFAULTS])
        conf = p.files[ts.MOONRAKER_CONF].decode()
        self.assertIn("trusted_clients:\n    100.64.0.0/10  " + ts.TRUST_TAG, conf)  # else 401 over Tailscale
        self.assertIn("fd7a:115c:a1e0::/48", conf)
        self.assertIn("systemctl restart moonraker", p.commands)
        self.assertTrue(any(ts.UP in c for c in p.commands))

    def test_link_not_in_log(self):
        import io as _io
        p = Printer()
        log, window = _io.StringIO(), _io.StringIO()

        class Tee:
            stream, log_ = window, log

            def write(self, t):
                window.write(t)
                log.write(t)

            def flush(self):
                pass
        tee = Tee()
        tee.log = log
        saved = sys.stdout
        sys.stdout = tee
        try:
            self.offer(p, "", "")
        finally:
            sys.stdout = saved
        self.assertIn("login.tailscale.com", window.getvalue())
        self.assertNotIn("login.tailscale.com", log.getvalue())

    def test_no_installs_nothing(self):
        p = Printer()
        self.offer(p, "n")
        self.assertEqual(p.files, {ts.MOONRAKER_CONF: MOONRAKER})

    def test_install_but_log_in_later(self):
        p = Printer()
        self.offer(p, "y", "n")
        self.assertIn(ts.BINARIES["tailscaled"], p.files)
        self.assertFalse(any("tailscale up" in c for c in p.commands))

    def test_no_tun_uses_userspace(self):
        p = Printer(tun="none")
        self.offer(p, "", "n")
        self.assertIn(b'FLAGS="--tun=userspace-networking"', p.files[ts.DEFAULTS])
        self.assertNotIn(ts.MODULES_LOAD, p.files)

    def test_tun_after_modprobe_loaded_at_boot(self):
        p = Printer(tun="loaded")
        self.offer(p, "", "n")
        self.assertEqual(p.files[ts.MODULES_LOAD], b"tun\n")

    def test_bad_download_refused(self):
        p = Printer()
        with self.assertRaises(ValueError):
            self.offer(p, "", "", get=server(tamper=True))
        self.assertNotIn(ts.BINARIES["tailscaled"], p.files)

    def test_already_logged_in_asks_nothing(self):
        p = Printer(installed=True, ours=True, state="Running")
        self.offer(p)  # no answers available: would raise StopIteration if it asked
        self.assertFalse(any("tailscale up" in c for c in p.commands))
        self.assertIn(ts.TRUST_TAG, p.files[ts.MOONRAKER_CONF].decode())  # 1.0-era install gets the trust too

    def test_users_own_tailscale_left_alone(self):
        p = Printer(installed=True, ours=False, state="Running", version="1.50.0")
        self.offer(p)
        self.assertNotIn(ts.BINARIES["tailscaled"], p.files)
        self.assertFalse(ts.uninstall(p))
        self.assertFalse(any("disable --now" in c for c in p.commands))

    def test_half_finished_install_is_completed(self):
        # stopped after the marker was written, service never started
        p = Printer(installed=True, ours=True, running=False, state=None)
        self.offer(p, "n")
        self.assertEqual(p.files[ts.BINARIES["tailscaled"]], b"DAEMON")
        self.assertTrue(p.running)

    def test_older_version_offered_update(self):
        p = Printer(installed=True, ours=True, state="Running", version="1.90.0")
        self.offer(p, "")
        self.assertEqual(p.files[ts.BINARIES["tailscaled"]], b"DAEMON")

    def test_ctrl_c_at_question(self):
        p = Printer()

        def interrupt(prompt):
            raise KeyboardInterrupt
        ts.offer(p, "ask", read=interrupt, get=server())  # no traceback
        self.assertNotIn(ts.DEFAULTS, p.files)

    def test_mode_no(self):
        p = Printer()
        ts.offer(p, "no", read=answers(), get=server())
        self.assertEqual(p.commands, [])

    def test_uninstall_ours_logs_out_and_untrusts(self):
        p = Printer()
        self.offer(p, "", "n")
        self.assertTrue(ts.uninstall(p))
        self.assertEqual(p.files[ts.MOONRAKER_CONF], MOONRAKER)
        self.assertTrue(any("tailscale logout" in c for c in p.commands))
        self.assertEqual(set(p.files), {ts.MOONRAKER_CONF})

    def test_status_with_many_peers(self):
        p = Printer(installed=True, ours=True, state="Running")
        self.assertEqual(ts.status(p)["state"], "Running")
        self.assertTrue(any("--peers=false" in c for c in p.commands))

    def test_login_link_parsed(self):
        self.assertEqual(ts.login(Printer(installed=True)), "https://login.tailscale.com/a/abc123")


if __name__ == "__main__":
    unittest.main()
