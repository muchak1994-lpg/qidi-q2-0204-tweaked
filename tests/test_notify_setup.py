#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""Optional phone-notifications step of the installer, against a stand-in printer.

Run:  python tests/test_notify_setup.py
"""
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import notify_setup as ns  # noqa: E402

MOONRAKER = b"[server]\nhost: 0.0.0.0\n\n[authorization]\ntrusted_clients:\n    10.0.0.0/8\n\n[timelapse]\noutput_path: ~/x/\n"


class Printer:
    def __init__(self, moonraker=MOONRAKER):
        self.files = {ns.MOONRAKER_CONF: moonraker}
        self.commands = []

    def read(self, path):
        return self.files.get(path)

    def stat(self, path):
        return ["qidi", "qidi", "644"] if path in self.files else None

    def install(self, data, path, owner, group, mode):
        self.files[path] = data
        self.modes = getattr(self, "modes", {})
        self.modes[path] = (owner, group, mode)

    def remove(self, path):
        self.files.pop(path, None)

    def _run(self, command, sudo=False, check=True):
        self.commands.append(command)
        return b""


class Window:
    """stdout stand-in like the installer's tee: `stream` is the window, `log` the file that must stay clean."""
    def __init__(self):
        self.stream, self.log = io.StringIO(), io.StringIO()

    def write(self, text):
        self.stream.write(text)
        self.log.write(text)
        return len(text)

    def flush(self):
        pass


def counter():
    n = iter(range(1, 100))
    return lambda size=16: "TOPIC%02d" % next(n)


def answers(*seq):
    it = iter(seq)
    return lambda prompt: next(it)


class NotifySetupTest(unittest.TestCase):
    def setUp(self):
        self.backups = Path(tempfile.mkdtemp())
        self.p = Printer()

    def configure(self, *replies, p=None, mode="yes"):
        return ns.configure(p or self.p, mode, read=answers(*replies), secrets_fn=counter(),
                            backups=self.backups, host="printer.example")

    # --- the question
    def test_mode_no_does_nothing(self):
        def boom(prompt):
            raise AssertionError("must not ask")
        self.assertFalse(ns.wanted("no", read=boom))
        self.assertFalse(ns.configure(self.p, "no", read=boom, backups=self.backups, host="h"))
        self.assertEqual(self.p.commands, [])
        self.assertEqual(self.p.files, {ns.MOONRAKER_CONF: MOONRAKER})

    def test_ask_default_is_no_and_yes_is_yes(self):
        self.assertFalse(ns.wanted("ask", read=lambda prompt: ""))
        self.assertTrue(ns.wanted("ask", read=lambda prompt: "y"))
        self.assertTrue(ns.wanted("yes", read=lambda prompt: ""))

    # --- what is written
    def test_config_written_with_mode_600_and_two_different_topics(self):
        self.assertTrue(self.configure(""))      # Enter = the default server
        text = self.p.files[ns.CONF].decode()
        self.assertEqual(self.p.modes[ns.CONF], ("qidi", "qidi", "600"))
        lines = dict(l.split("=", 1) for l in text.splitlines())
        self.assertEqual(lines["ENABLED"], "1")
        self.assertEqual(lines["NTFY_SERVER"], "https://ntfy.sh")
        self.assertNotEqual(lines["EVENTS_TOPIC"], lines["CMD_TOPIC"])
        self.assertTrue(lines["EVENTS_TOPIC"].startswith("TOPIC"))

    def test_topics_are_random_and_not_in_log_output(self):
        win, saved = Window(), sys.stdout
        sys.stdout = win
        try:
            self.configure("")
        finally:
            sys.stdout = saved
        lines = dict(l.split("=", 1) for l in self.p.files[ns.CONF].decode().splitlines())
        self.assertIn(lines["EVENTS_TOPIC"], win.stream.getvalue())      # the window shows the channel to subscribe to
        for secret in (lines["EVENTS_TOPIC"], lines["CMD_TOPIC"]):
            self.assertNotIn(secret, win.log.getvalue())
        self.assertNotIn(lines["CMD_TOPIC"], win.stream.getvalue())      # the command channel is never shown

    def test_notifier_file_has_the_apprise_address_not_the_placeholder(self):
        self.configure("")
        lines = dict(l.split("=", 1) for l in self.p.files[ns.CONF].decode().splitlines())
        conf = self.p.files[ns.MOONRAKER_NOTIFIER].decode()
        self.assertIn("url: ntfys://ntfy.sh/%s?priority=high" % lines["EVENTS_TOPIC"], conf)
        self.assertNotIn("__NTFY_URL__", conf)
        self.assertIn("[notifier q2_ntfy]", conf)
        self.assertEqual(self.p.modes[ns.MOONRAKER_NOTIFIER], ("qidi", "qidi", "600"))

    def test_custom_server_is_used(self):
        self.configure("http://ntfy.lan:8080")
        self.assertIn("NTFY_SERVER=http://ntfy.lan:8080\n", self.p.files[ns.CONF].decode())
        self.assertIn("url: ntfy://ntfy.lan:8080/", self.p.files[ns.MOONRAKER_NOTIFIER].decode())
        p2 = Printer()
        self.configure("https://ntfy.example.org/", p=p2)
        self.assertIn("NTFY_SERVER=https://ntfy.example.org\n", p2.files[ns.CONF].decode())
        self.assertIn("url: ntfys://ntfy.example.org/", p2.files[ns.MOONRAKER_NOTIFIER].decode())

    def test_include_line_added_once_and_topics_kept_on_a_second_run(self):
        self.configure("")
        first = self.p.files[ns.CONF]
        self.configure("")
        conf = self.p.files[ns.MOONRAKER_CONF].decode()
        self.assertEqual(conf.count(ns.INCLUDE_LINE), 1)
        self.assertEqual(self.p.files[ns.CONF], first)
        self.assertTrue(conf.startswith(MOONRAKER.decode()))              # nothing else in the file was touched

    def test_crlf_moonraker_conf_keeps_its_line_ends(self):
        p = Printer(MOONRAKER.replace(b"\n", b"\r\n"))
        self.configure("", p=p)
        conf = p.files[ns.MOONRAKER_CONF]
        self.assertNotIn(b"\n", conf.replace(b"\r\n", b""))

    def test_services_are_restarted_and_a_test_message_is_sent(self):
        self.configure("")
        joined = "\n".join(self.p.commands)
        self.assertIn("systemctl restart q2-notify-listen.service", joined)
        self.assertIn("systemctl restart moonraker", joined)
        self.assertIn("q2_notify_send.sh", joined)

    def test_copy_of_the_config_is_kept_on_the_pc(self):
        self.configure("")
        copies = list(self.backups.glob("notify-printer.example-*/q2_notify.conf"))
        self.assertEqual(len(copies), 1)
        self.assertEqual(copies[0].read_bytes(), self.p.files[ns.CONF])

    # --- uninstall
    def test_uninstall_removes_everything_it_added(self):
        self.configure("")
        self.assertTrue(ns.remove(self.p))
        self.assertEqual(self.p.files, {ns.MOONRAKER_CONF: MOONRAKER})
        self.assertIn("systemctl disable --now q2-notify-listen.service", "\n".join(self.p.commands))
        self.assertIn("systemctl restart moonraker", "\n".join(self.p.commands))

    def test_uninstall_without_setup_changes_nothing(self):
        self.assertFalse(ns.remove(self.p))
        self.assertEqual(self.p.files, {ns.MOONRAKER_CONF: MOONRAKER})


if __name__ == "__main__":
    unittest.main()
