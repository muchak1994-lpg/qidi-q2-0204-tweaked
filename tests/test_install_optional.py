#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""The installer's optional extras at the end: question -> yes -> installed right away; no -> next question.

Run:  python tests/test_install_optional.py
"""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import build  # noqa: E402
import install  # noqa: E402

OPTIONAL = [m["id"] for m in build.load_modules() if not m.get("default", True)]


class DefaultSetTests(unittest.TestCase):
    def test_only_what_needs_a_choice_of_the_user_stays_optional(self):
        self.assertEqual(sorted(OPTIONAL), ["phone-notifications", "start-keep-xy"])

    def test_the_screen_window_the_ai_service_modules_and_the_log_come_with_every_install(self):
        selected = {m["id"] for m in install.select([])}
        for mid in ("printer-screen-view", "printer-screen-touch", "algo-app-gate", "algo-app-malloc",
                    "algo-app-stream-decrypt", "journal-retention"):
            self.assertIn(mid, selected)


class Recorder:
    def __init__(self, answers=None, notify=False, nothing_to_do=()):
        self.answers = answers or {}
        self.notify = notify
        self.nothing_to_do = set(nothing_to_do)
        self.log = []

    def ask(self, question):
        mid = max((i for i in OPTIONAL if i in question), key=len)  # longest id: one id can be the start of another
        self.log.append(("ask", mid))
        return self.answers.get(mid, False)

    def round(self, selected):
        added = sorted(m["id"] for m in selected if not m.get("default", True))
        self.log.append(("round", added))
        return not (self.nothing_to_do and added and added[-1] in self.nothing_to_do)

    def notify_fn(self):
        self.log.append(("configure", None))

    def wanted(self, mode):
        self.log.append(("wanted", mode))
        return self.notify and mode != "no"


def run(rec, interactive=True, skip=(), notify="ask", extra=()):
    args = SimpleNamespace(skip=list(skip), notify=notify)
    selected = install.select(list(skip), list(extra))
    return install.optional_modules(selected, args, interactive, rec.ask, rec.round, rec.notify_fn, rec.wanted)


class OptionalStepTest(unittest.TestCase):
    def test_there_are_optional_modules_including_phone_notifications(self):
        self.assertIn("phone-notifications", OPTIONAL)
        self.assertGreaterEqual(len(OPTIONAL), 2)

    def test_each_module_is_asked_in_turn_and_no_goes_to_the_next_question(self):
        rec = Recorder()
        run(rec)
        asked = [x for kind, x in rec.log if kind == "ask"]
        self.assertEqual(asked, [m for m in OPTIONAL if m != "phone-notifications"])
        self.assertNotIn("round", [k for k, _ in rec.log])

    def test_yes_installs_right_away_before_the_next_question(self):
        first = [m for m in OPTIONAL if m != "phone-notifications"][0]
        rec = Recorder(answers={first: True})
        run(rec)
        kinds = [k for k, _ in rec.log]
        i = kinds.index("round")
        self.assertEqual(rec.log[i - 1], ("ask", first))        # the question came first ...
        self.assertEqual(rec.log[i][1], [first])               # ... then its install, with only that module added
        self.assertGreater(len(rec.log), i + 1)                 # ... and only then the next question

    def test_modules_installed_earlier_in_the_run_stay_in_the_selection(self):
        first = [m for m in OPTIONAL if m != "phone-notifications"][0]
        rec = Recorder(answers={first: True}, notify=True)
        run(rec)
        rounds = [x for k, x in rec.log if k == "round"]
        self.assertEqual(rounds[0], [first])
        self.assertEqual(rounds[1], sorted([first, "phone-notifications"]))

    def test_phone_notifications_are_configured_right_after_their_install(self):
        rec = Recorder(notify=True)
        run(rec)
        kinds = [k for k, _ in rec.log]
        i = kinds.index("configure")
        self.assertEqual(kinds[i - 1], "round")
        self.assertIn("phone-notifications", rec.log[i - 1][1])

    def test_phone_notifications_declined_installs_nothing(self):
        rec = Recorder(notify=False)
        run(rec)
        self.assertNotIn("configure", [k for k, _ in rec.log])

    def test_no_questions_without_a_window_to_ask_in(self):
        rec = Recorder(answers={m: True for m in OPTIONAL}, notify=True)
        run(rec, interactive=False)
        self.assertEqual([k for k, _ in rec.log if k in ("ask", "round", "configure")], [])
        self.assertIn(("wanted", "no"), rec.log)                   # --notify ask without a window means no

    def test_notify_yes_without_a_window_is_honoured(self):
        rec = Recorder(notify=True)
        run(rec, interactive=False, notify="yes")
        self.assertIn(("wanted", "yes"), rec.log)

    def test_skipped_and_already_selected_modules_are_not_asked(self):
        first = [m for m in OPTIONAL if m != "phone-notifications"][0]
        rec = Recorder()
        run(rec, skip=[first])
        self.assertNotIn(first, [x for k, x in rec.log if k == "ask"])
        rec = Recorder()
        run(rec, extra=[first])
        self.assertNotIn(first, [x for k, x in rec.log if k == "ask"])
        rec = Recorder()
        run(rec, extra=["phone-notifications"])
        self.assertNotIn("wanted", [k for k, _ in rec.log])

    def test_already_installed_says_so_and_goes_on(self):
        first = [m for m in OPTIONAL if m != "phone-notifications"][0]
        rec = Recorder(answers={first: True}, nothing_to_do=[first])
        run(rec)
        self.assertIn("wanted", [k for k, _ in rec.log])     # went on to the next question


if __name__ == "__main__":
    unittest.main()
