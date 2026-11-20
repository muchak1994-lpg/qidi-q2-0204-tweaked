#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic)
"""Offline tests for the installer's SSH login: SSH key and passwordless sudo when the printer allows both,
otherwise the password, as before (tools/install.py SSHPrinter, tools/printer.py connect_with_key).

Run:  python tests/test_ssh_login.py
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import install  # noqa: E402
import printer  # noqa: E402


class _Channel:
    def __init__(self, code):
        self.code = code

    def recv_exit_status(self):
        return self.code


class _Stream:
    def __init__(self, data=b"", code=0):
        self.data = data
        self.channel = _Channel(code)
        self.written = ""

    def read(self):
        return self.data

    def write(self, text):
        self.written += text

    def flush(self):
        pass


class _Client:
    """Records commands; 'sudo -n true' exits with sudo_n_code."""

    def __init__(self, sudo_n_code=0, sudo_check_codes=()):
        self.sudo_n_code = sudo_n_code
        self.sudo_check_codes = list(sudo_check_codes)  # exit codes of the password checks, in turn
        self.commands = []
        self.stdins = []

    def exec_command(self, command, timeout=None):
        self.commands.append(command)
        stdin = _Stream()
        self.stdins.append(stdin)
        code = self.sudo_n_code if command == "sudo -n true" else 0
        if command == "sudo -S -p '' true" and self.sudo_check_codes:
            code = self.sudo_check_codes.pop(0)
        return stdin, _Stream(b"ok", code), _Stream()

    def open_sftp(self):
        return None


class OpenTest(unittest.TestCase):
    def test_key_and_passwordless_sudo_ask_nothing(self):
        client = _Client(sudo_n_code=0)
        with mock.patch.object(printer, "connect_with_key", return_value=client), \
                mock.patch.object(install.getpass, "getpass", side_effect=AssertionError("asked")):
            p = install.SSHPrinter.open("printer", "mks")
        self.assertIsNone(p.password)
        p._run("systemctl restart klipper", sudo=True)
        self.assertEqual(client.commands[-1], "sudo -n sh -c 'systemctl restart klipper'")
        self.assertEqual(client.stdins[-1].written, "")  # no password sent anywhere

    def test_key_but_sudo_needs_password_asks_for_it(self):
        client = _Client(sudo_n_code=1)
        with mock.patch.object(printer, "connect_with_key", return_value=client), \
                mock.patch.object(install.getpass, "getpass", return_value="secret") as ask:
            p = install.SSHPrinter.open("printer", "mks")
        self.assertEqual(ask.call_count, 1)
        p._run("true", sudo=True)
        self.assertEqual(client.commands[-1], "sudo -S -p '' sh -c true")
        self.assertEqual(client.stdins[-1].written, "secret\n")

    def test_wrong_sudo_password_is_asked_again(self):  # audit 20.11.2026
        client = _Client(sudo_n_code=1, sudo_check_codes=[1, 0])
        with mock.patch.object(printer, "connect_with_key", return_value=client), \
                mock.patch.object(install.getpass, "getpass", side_effect=["typo", "secret"]) as ask:
            p = install.SSHPrinter.open("printer", "mks")
        self.assertEqual(ask.call_count, 2)
        self.assertEqual(p.password, "secret")
        self.assertNotIn("secret", " ".join(client.commands))  # only on stdin

    def test_wrong_sudo_password_three_times_stops(self):
        client = _Client(sudo_n_code=1, sudo_check_codes=[1, 1, 1])
        with mock.patch.object(printer, "connect_with_key", return_value=client), \
                mock.patch.object(install.getpass, "getpass", return_value="typo"):
            with self.assertRaises(install.InstallError):
                install.SSHPrinter.open("printer", "mks")

    def test_no_key_is_the_old_password_login(self):
        client = _Client()
        with mock.patch.object(printer, "connect_with_key", return_value=None), \
                mock.patch.object(printer, "connect", return_value=client) as conn, \
                mock.patch.object(install.getpass, "getpass", return_value="secret") as ask:
            p = install.SSHPrinter.open("printer", "mks")
        self.assertEqual(ask.call_count, 1)
        self.assertEqual(conn.call_args.kwargs["password"], "secret")
        p._run("true", sudo=True)
        self.assertEqual(client.commands[-1], "sudo -S -p '' sh -c true")
        self.assertEqual(client.stdins[-1].written, "secret\n")


try:
    import paramiko  # noqa: F401
    HAVE_PARAMIKO = True
except ImportError:
    HAVE_PARAMIKO = False


@unittest.skipUnless(HAVE_PARAMIKO, "paramiko not installed")
class KeyLoginTest(unittest.TestCase):
    def fake(self, exc):
        class Fake:
            def connect(self, *a, **k):
                raise exc

            def close(self):
                self.closed = True
        return Fake()

    def test_rejected_key_or_no_key_falls_back(self):
        import paramiko
        for exc in (paramiko.AuthenticationException("no"),
                    paramiko.SSHException("No authentication methods available")):
            with mock.patch.object(printer, "_client", return_value=self.fake(exc)):
                self.assertIsNone(printer.connect_with_key("printer", "mks"))

    def test_other_ssh_errors_are_not_hidden(self):
        import paramiko
        with mock.patch.object(printer, "_client", return_value=self.fake(paramiko.SSHException("host key not accepted"))):
            with self.assertRaises(paramiko.SSHException):
                printer.connect_with_key("printer", "mks")


if __name__ == "__main__":
    unittest.main(verbosity=2)
