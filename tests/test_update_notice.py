#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""update-notice: the printer tells the owner once per release that a newer Tweaked version exists.

The script runs on the printer (Python 3.9, standard library only). The tests run it against two small local web
servers: a fake GitHub ("latest release") and a fake Moonraker (print state, objects list, gcode script).
Run:  python tests/test_update_notice.py
"""
import importlib.util
import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOD = ROOT / "modules" / "update-notice"
SCRIPT = MOD / "files" / "q2_update_notice.py"


def load():
    spec = importlib.util.spec_from_file_location("q2_update_notice", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Fake:
    """GitHub + Moonraker on 127.0.0.1; every request is recorded."""

    def __init__(self):
        self.release = {"tag_name": "v1.4.0", "draft": False, "prerelease": False}
        self.release_status = 200
        self.print_state = "standby"
        self.objects = ["print_stats", "gcode_macro _TWEAKED_NOTIFY"]
        self.scripts = []
        self.hits = []
        self.gcode_status = 200
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                fake.hits.append(("GET", self.path, self.headers.get("User-Agent", "")))
                if self.path.startswith("/release"):
                    return self._send(fake.release_status, fake.release)
                if self.path.startswith("/printer/objects/list"):
                    return self._send(200, {"result": {"objects": fake.objects}})
                if self.path.startswith("/printer/objects/query"):
                    return self._send(200, {"result": {"status": {"print_stats": {"state": fake.print_state}}}})
                self._send(404, {})

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
                fake.hits.append(("POST", self.path, ""))
                if self.path.startswith("/printer/gcode/script"):
                    if fake.gcode_status == 200:
                        fake.scripts.append(body["script"])
                    return self._send(fake.gcode_status, {"result": "ok"})
                self._send(404, {})

        self.server = HTTPServer(("127.0.0.1", 0), H)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def release_url(self):
        return "http://127.0.0.1:%d/release" % self.port

    @property
    def moonraker(self):
        return "http://127.0.0.1:%d" % self.port

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


class Case(unittest.TestCase):
    def setUp(self):
        self.m = load()
        self.fake = Fake()
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "VERSION").write_text("1.3.1\n", encoding="utf-8")

    def tearDown(self):
        self.fake.stop()
        self.tmp.cleanup()

    def notice(self):
        return self.m.Notice(self.fake.release_url, self.fake.moonraker, self.dir)

    def due(self, n):
        return n.step(n.next_fetch + 1)


class VersionTest(Case):
    def test_parse(self):
        p = self.m.parse_version
        self.assertEqual(p("1.3.1"), (1, 3, 1))
        self.assertEqual(p("v1.4.0\n"), (1, 4, 0))
        for bad in ("", "1.3", "1.3.1-beta", "v1.3.1; M112", "1.3.1\nM112", "x", "1.3.1.2", None):
            self.assertIsNone(p(bad), repr(bad))

    def test_numeric_not_text_order(self):
        self.assertGreater(self.m.parse_version("1.10.0"), self.m.parse_version("1.9.9"))

    def test_message_is_the_owners_text(self):
        self.assertEqual(self.m.message((1, 4, 0), (1, 3, 1)),
                         "New TWEAKED version 1.4.0 (currently 1.3.1). Download and install with the help of a computer.")


class AnnounceTest(Case):
    def test_newer_release_is_announced_to_screen_and_phone(self):
        n = self.notice()
        self.assertEqual(self.due(n), "announced")
        self.assertEqual(len(self.fake.scripts), 2)
        self.assertIn("RESPOND TYPE=error", self.fake.scripts[0])
        self.assertIn("New TWEAKED version 1.4.0 (currently 1.3.1)", self.fake.scripts[0])
        self.assertIn("RUN_SHELL_COMMAND CMD=q2_notify", self.fake.scripts[1])
        self.assertIn("New TWEAKED version 1.4.0", self.fake.scripts[1])

    def test_no_phone_message_without_the_phone_module(self):
        self.fake.objects = ["print_stats"]
        self.assertEqual(self.due(self.notice()), "announced")
        self.assertEqual(len(self.fake.scripts), 1)

    def test_once_per_version_even_after_a_restart_of_the_service(self):
        self.assertEqual(self.due(self.notice()), "announced")
        self.fake.scripts.clear()
        again = self.notice()  # a new process: only the files remember
        self.assertEqual(self.due(again), "up-to-date")
        self.assertEqual(self.fake.scripts, [])
        self.fake.release["tag_name"] = "v1.4.1"  # but the next release is news again
        again.next_fetch = 0
        self.assertEqual(again.step(10 ** 9), "announced")

    def test_same_or_older_version_is_silent(self):
        for tag in ("v1.3.1", "v1.3.0", "v0.9.9"):
            self.fake.release["tag_name"] = tag
            self.assertEqual(self.due(self.notice()), "up-to-date", tag)
        self.assertEqual(self.fake.scripts, [])

    def test_drafts_prereleases_and_odd_tags_are_ignored(self):
        for rel in ({"tag_name": "v2.0.0", "draft": True}, {"tag_name": "v2.0.0", "prerelease": True},
                    {"tag_name": "v2.0.0; M112"}, {"tag_name": "nightly"}, {}):
            self.fake.release = rel
            self.assertEqual(self.due(self.notice()), "up-to-date", rel)
        self.assertEqual(self.fake.scripts, [])


class SafetyTest(Case):
    def test_never_while_a_print_runs_or_is_paused_then_later(self):
        n = self.notice()
        for state in ("printing", "paused"):
            self.fake.print_state = state
            self.assertEqual(self.due(n), "busy", state)
            self.assertEqual(self.fake.scripts, [])
        self.fake.print_state = "complete"
        self.assertEqual(n.step(n.next_busy + 1), "announced")  # nothing was lost

    def test_unreadable_print_state_counts_as_busy(self):
        n = self.notice()
        n.moonraker = "http://127.0.0.1:1"  # nothing listens: Moonraker is down
        self.assertEqual(self.due(n), "busy")

    def test_github_down_retries_later_and_stays_quiet(self):
        self.fake.release_status = 500
        n = self.notice()
        self.assertEqual(self.due(n), "fetch-failed")
        self.assertEqual(self.fake.scripts, [])
        self.fake.release_status = 200
        self.assertEqual(n.step(n.next_fetch + 1), "announced")

    def test_one_request_per_day_not_more(self):
        n = self.notice()
        self.assertEqual(self.due(n), "announced")
        gets = [h for h in self.fake.hits if h[1].startswith("/release")]
        self.assertEqual(len(gets), 1)
        t = n.next_fetch
        self.assertEqual(n.step(t - 1), "waiting")
        self.assertEqual(len([h for h in self.fake.hits if h[1].startswith("/release")]), 1)
        self.assertGreaterEqual(n.next_fetch - (t - self.m.CHECK_EVERY), 0)
        self.assertGreaterEqual(self.m.CHECK_EVERY, 20 * 3600)

    def test_request_carries_nothing_about_the_owner(self):
        self.due(self.notice())
        ua = [h[2] for h in self.fake.hits if h[1].startswith("/release")][0]
        self.assertEqual(ua, "q2-update-notice")

    def test_off_switch_file_and_missing_version_file(self):
        (self.dir / "disabled").write_text("", encoding="utf-8")
        self.assertEqual(self.due(self.notice()), "off")
        self.assertEqual(self.fake.hits, [])
        (self.dir / "disabled").unlink()
        (self.dir / "VERSION").unlink()
        self.assertEqual(self.due(self.notice()), "no-version")
        self.assertEqual(self.fake.hits, [])

    def test_failed_announcement_is_retried_and_not_marked_done(self):
        self.fake.gcode_status = 500
        n = self.notice()
        self.assertEqual(self.due(n), "announce-failed")
        self.assertFalse((self.dir / "announced").exists())
        self.fake.gcode_status = 200
        self.assertEqual(n.step(n.next_busy + 1), "announced")
        self.assertEqual((self.dir / "announced").read_text(encoding="utf-8").strip(), "1.4.0")

    def test_upgrade_in_between_cancels_a_pending_message(self):
        self.fake.print_state = "printing"
        n = self.notice()
        self.assertEqual(self.due(n), "busy")
        (self.dir / "VERSION").write_text("1.4.0\n", encoding="utf-8")  # the owner installed it meanwhile
        self.fake.print_state = "standby"
        self.assertEqual(n.step(n.next_busy + 1), "up-to-date")
        self.assertEqual(self.fake.scripts, [])


class ModuleTest(unittest.TestCase):
    def test_version_file_matches_the_release(self):
        shipped = (MOD / "files" / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(shipped, (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
                         "bump modules/update-notice/files/VERSION together with VERSION")

    def test_module_json_and_files(self):
        m = json.loads((MOD / "module.json").read_text(encoding="utf-8"))
        self.assertTrue(m["default"])  # on for everyone; --skip update-notice leaves it out
        self.assertEqual(set(m["files"]), {
            "/usr/local/lib/q2-update-notice/q2_update_notice.py",
            "/usr/local/lib/q2-update-notice/VERSION",
            "/etc/systemd/system/q2-update-notice.service"})
        for spec in m["files"].values():
            self.assertTrue((MOD / spec["source"]).is_file(), spec["source"])
        service = (MOD / "files" / "q2-update-notice.service").read_text(encoding="utf-8")
        self.assertIn("q2_update_notice.py", service)
        self.assertNotIn("\r", service)

    def test_script_is_python39_clean_and_has_no_secrets(self):
        src = SCRIPT.read_text(encoding="utf-8")
        compile(src, str(SCRIPT), "exec", dont_inherit=True)
        self.assertNotIn("\r", src)
        for word in ("password", "token", "apikey", "192.168", "100.73"):
            self.assertNotIn(word, src.lower())


if __name__ == "__main__":
    unittest.main()
