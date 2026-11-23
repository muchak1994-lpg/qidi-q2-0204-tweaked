#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""algo-app-stream-decrypt, second part: the AI service gives its noodle model back after a print (no restart).

QIDI's DetectionDeal loads the noodle model in a print's second layer and never releases it (its own detector_release()
is never called). q2stream starts one small watcher thread per DetectionDeal: when the printer has been idle (not
printing, not paused, not "beginning" a print) for 120 s in a row and a model is loaded, it calls QIDI's own
detector_release(), runs the garbage collector and asks glibc to give the memory back (malloc_trim). The next print
loads the model again, as it does after a restart of the service.

The tests use fake DetectionDeal / printer objects and a fake clock, so no thread has to sleep.
Run:  python tests/test_algo_stream_release.py
"""
import gc
import importlib
import logging
import os
import sys
import tempfile
import textwrap
import types
import unittest
from pathlib import Path

import test_algo_stream_decrypt as dec  # the sibling test file: its helpers load the package

ROOT = Path(__file__).resolve().parent.parent


class FakePrinter(object):
    def __init__(self, printing=False, begin=False, paused=False):
        self.is_printing = printing
        self.is_printing_begin = begin
        self._paused = paused

    def is_paused(self):
        return self._paused


class FakeDetector(object):
    pass


def make_deal_class(release_calls):
    class DetectionDeal(object):
        def __init__(self, config, vi, printer):
            self.config = config
            self.vi = vi
            self.printer = printer
            self.detector = None
            self.pei_detector = None
            self.stop_event = types.SimpleNamespace(is_set=lambda: False)

        def detector_release(self):
            release_calls.append(1)
            self.detector = None
            gc.collect()

    return DetectionDeal


class Base(unittest.TestCase):
    def setUp(self):
        self.q = dec.load_package()
        self.records = []
        handler = logging.Handler()
        handler.emit = self.records.append
        self.logger = logging.getLogger(self.q.LOGGER_NAME)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.DEBUG)
        self.addCleanup(self.logger.removeHandler, handler)
        self.trims = []
        self.q._malloc_trim = lambda: self.trims.append(1)  # no real glibc call in the tests
        self.releases = []
        self.Deal = make_deal_class(self.releases)

    def messages(self):
        return [r.getMessage() for r in self.records]

    def deal(self, **printer):
        obj = self.Deal(config=None, vi=None, printer=FakePrinter(**printer))
        obj.detector = FakeDetector()
        return obj


class ReleaserDecisions(Base):
    def releaser(self, idle=120):
        return self.q.Releaser(idle_seconds=idle)

    def test_idle_long_enough_releases_once(self):
        obj, rel = self.deal(), self.releaser()
        self.assertEqual(rel.step(obj, 1000), "waiting")
        self.assertEqual(rel.step(obj, 1119), "waiting")
        self.assertEqual(rel.step(obj, 1120), "released")
        self.assertEqual(len(self.releases), 1)
        self.assertIsNone(obj.detector)
        self.assertEqual(len(self.trims), 1)
        self.assertEqual(rel.step(obj, 1200), "nothing")  # nothing loaded any more: nothing to do
        self.assertEqual(len(self.releases), 1)
        self.assertTrue(any("released" in m for m in self.messages()), self.messages())

    def test_printing_beginning_or_paused_is_never_released(self):
        for kwargs in ({"printing": True}, {"begin": True}, {"paused": True}, {"printing": True, "begin": True}):
            obj, rel = self.deal(**kwargs), self.releaser()
            for now in (0, 500, 5000):
                self.assertEqual(rel.step(obj, now), "busy", kwargs)
            self.assertIsNotNone(obj.detector)
        self.assertEqual(self.releases, [])

    def test_busy_resets_the_idle_clock(self):
        obj, rel = self.deal(), self.releaser()
        rel.step(obj, 0)
        rel.step(obj, 100)
        obj.printer.is_printing = True
        self.assertEqual(rel.step(obj, 110), "busy")
        obj.printer.is_printing = False
        self.assertEqual(rel.step(obj, 115), "waiting")  # counting again from 115
        self.assertEqual(rel.step(obj, 200), "waiting")
        self.assertEqual(rel.step(obj, 235), "released")

    def test_a_print_starting_right_before_the_release_wins(self):
        obj, rel = self.deal(), self.releaser()
        rel.step(obj, 0)
        states = iter([False, True])  # idle on the first look, printing on the re-check

        class Flipping(FakePrinter):
            @property
            def is_printing(self):
                return next(states)

            @is_printing.setter
            def is_printing(self, value):
                pass

        obj.printer = Flipping()
        self.assertEqual(rel.step(obj, 500), "busy")
        self.assertEqual(self.releases, [])

    def test_nothing_loaded_does_nothing(self):
        obj, rel = self.deal(), self.releaser()
        obj.detector = None
        for now in (0, 500, 5000):
            self.assertEqual(rel.step(obj, now), "nothing")
        self.assertEqual(self.releases, [])

    def test_unknown_printer_object_counts_as_busy(self):
        rel = self.releaser()
        obj = self.deal()
        obj.printer = object()  # QIDI changed the printer class: we cannot tell, so we never release
        self.assertEqual(rel.step(obj, 0), "busy")
        self.assertEqual(rel.step(obj, 10000), "busy")
        obj.printer = None
        self.assertEqual(rel.step(obj, 20000), "busy")
        obj.printer = FakePrinter()
        del FakePrinter.is_paused  # a printer without is_paused()
        try:
            self.assertEqual(rel.step(obj, 30000), "busy")
        finally:
            FakePrinter.is_paused = lambda self: self._paused
        self.assertEqual(self.releases, [])

    def test_the_pei_detector_is_left_alone(self):
        obj, rel = self.deal(), self.releaser()
        pei = obj.pei_detector = FakeDetector()
        rel.step(obj, 0)
        rel.step(obj, 500)
        self.assertIs(obj.pei_detector, pei)

    def test_an_error_in_the_release_is_logged_and_never_raised(self):
        obj, rel = self.deal(), self.releaser()

        def boom():
            raise RuntimeError("release failed")

        obj.detector_release = boom
        rel.step(obj, 0)
        self.assertEqual(rel.step(obj, 500), "error")
        self.assertIsNotNone(obj.detector)
        self.assertTrue(any("release failed" in m for m in self.messages()), self.messages())

    def test_too_many_errors_switch_the_releaser_off(self):
        obj, rel = self.deal(), self.releaser()

        def boom():
            raise RuntimeError("x")

        obj.detector_release = boom
        for i in range(self.q.MAX_RELEASE_ERRORS + 3):
            rel.step(obj, i * 1000)
            rel.step(obj, i * 1000 + 500)
        self.assertEqual(rel.step(obj, 10 ** 7), "off")

    def test_the_trim_is_asked_for_after_the_release(self):
        order = []
        obj, rel = self.deal(), self.releaser()
        original = obj.detector_release
        obj.detector_release = lambda: (order.append("release"), original())
        self.q._malloc_trim = lambda: order.append("trim")
        rel.step(obj, 0)
        rel.step(obj, 500)
        self.assertEqual(order, ["release", "trim"])


class WatcherLoop(Base):
    def test_loop_steps_until_the_object_is_gone_or_stopped(self):
        import weakref
        obj = self.deal()
        rel = self.q.Releaser(idle_seconds=120)
        clock = {"t": 0.0}
        sleeps = []

        def sleep(seconds):
            sleeps.append(seconds)
            clock["t"] += seconds

        self.q.run_watcher(weakref.ref(obj), rel, clock=lambda: clock["t"], sleep=sleep, poll=5, max_loops=40)
        self.assertEqual(len(self.releases), 1)  # released after 120 idle seconds (24 polls of 5 s)
        self.assertEqual(set(sleeps), {5})
        # a stopped service ends the loop at once
        obj2 = self.deal()
        obj2.stop_event = types.SimpleNamespace(is_set=lambda: True)
        before = len(sleeps)
        self.q.run_watcher(weakref.ref(obj2), self.q.Releaser(120), clock=lambda: 0.0, sleep=sleep, poll=5, max_loops=40)
        self.assertEqual(len(sleeps), before)

    def test_a_deleted_object_ends_the_loop(self):
        import weakref
        obj = self.deal()
        ref = weakref.ref(obj)
        del obj
        gc.collect()
        self.q.run_watcher(ref, self.q.Releaser(120), clock=lambda: 0.0, sleep=lambda s: self.fail("no sleep"), poll=5, max_loops=5)

    def test_an_exception_in_a_step_does_not_kill_the_loop(self):
        import weakref
        obj = self.deal()

        class Exploding(object):
            calls = 0

            def step(self, inst, now):
                Exploding.calls += 1
                raise ValueError("odd")

        self.q.run_watcher(weakref.ref(obj), Exploding(), clock=lambda: 0.0, sleep=lambda s: None, poll=5, max_loops=3)
        self.assertEqual(Exploding.calls, 3)


class PatchingTheClass(Base):
    def module(self):
        m = types.ModuleType("src.detection_deal")
        m.DetectionDeal = self.Deal
        return m

    def test_init_is_wrapped_and_starts_one_watcher_per_object(self):
        started = []
        self.q.start_watcher = started.append
        m = self.module()
        self.assertTrue(self.q.patch_release(m))
        self.assertTrue(hasattr(m.DetectionDeal.__init__, "_q2stream_original"))
        a = m.DetectionDeal(None, None, FakePrinter())
        b = m.DetectionDeal(None, None, FakePrinter())
        self.assertEqual(started, [a, b])
        self.assertIsNone(a.detector)  # the original __init__ ran

    def test_patching_twice_does_nothing_the_second_time(self):
        self.q.start_watcher = lambda inst: None
        m = self.module()
        self.assertTrue(self.q.patch_release(m))
        first = m.DetectionDeal.__init__
        self.assertFalse(self.q.patch_release(m))
        self.assertIs(m.DetectionDeal.__init__, first)

    def test_a_class_that_is_not_the_one_expected_is_left_alone(self):
        m = types.ModuleType("src.detection_deal")
        m.DetectionDeal = type("DetectionDeal", (), {"__init__": lambda self, a, b: None})
        original = m.DetectionDeal.__init__
        self.assertFalse(self.q.patch_release(m))
        self.assertIs(m.DetectionDeal.__init__, original)
        m2 = types.ModuleType("src.detection_deal")

        class NoRelease(object):
            def __init__(self, config, vi, printer):
                pass

        m2.DetectionDeal = NoRelease
        self.assertFalse(self.q.patch_release(m2))
        self.assertFalse(self.q.patch_release(types.ModuleType("x")))
        self.assertFalse(self.q.patch_release(None))

    def test_a_failing_watcher_start_does_not_break_the_service(self):
        def boom(inst):
            raise RuntimeError("no threads")

        self.q.start_watcher = boom
        m = self.module()
        self.assertTrue(self.q.patch_release(m))
        obj = m.DetectionDeal(None, None, FakePrinter())  # must not raise
        self.assertIsNone(obj.detector)

    def test_start_watcher_makes_one_daemon_thread(self):
        import threading
        seen = {}

        class FakeThread(object):
            def __init__(self, target=None, args=(), kwargs=None, name=None, daemon=None):
                seen.update(target=target, daemon=daemon, name=name)

            def start(self):
                seen["started"] = True

        real = threading.Thread
        threading.Thread = FakeThread
        try:
            self.q.start_watcher(self.deal())
        finally:
            threading.Thread = real
        self.assertTrue(seen.get("started"))
        self.assertTrue(seen.get("daemon"))


class ThroughTheImportHook(Base):
    def setUp(self):
        Base.setUp(self)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        pkg = Path(self.tmp.name) / "fakeapp2"
        (pkg / "src").mkdir(parents=True)
        (pkg / "src" / "__init__.py").write_text("", encoding="utf-8")
        text = textwrap.dedent('''
            import tempfile
            from q2stream_fake_crypto2 import AES, unpad

            class DetectionDeal(object):
                def __init__(self, config, vi, printer):
                    self.printer = printer
                    self.detector = None
                    self.encryption_key = "k"

                def detector_release(self):
                    self.detector = None
            ''') + textwrap.indent(textwrap.dedent(dec.ORIGINAL_METHOD), "    ")
        (pkg / "src" / "detection_deal.py").write_text(text, encoding="utf-8")
        fake = types.ModuleType("q2stream_fake_crypto2")
        fake.AES = dec.ToyAES
        fake.unpad = dec.unpad
        sys.modules["q2stream_fake_crypto2"] = fake
        sys.path.insert(0, str(pkg))
        self.addCleanup(self.cleanup, str(pkg))
        self.drop()

    def drop(self):
        for name in [n for n in sys.modules if n == "src" or n.startswith("src.")]:
            del sys.modules[name]

    def cleanup(self, pkg):
        self.q.uninstall()
        sys.path.remove(pkg)
        sys.modules.pop("q2stream_fake_crypto2", None)
        self.drop()

    def test_both_patches_are_applied_on_import(self):
        started = []
        self.q.start_watcher = started.append
        self.assertTrue(self.q.install(environ={}))
        deal = importlib.import_module("src.detection_deal")
        self.assertTrue(hasattr(deal.DetectionDeal.decrypt_weight, "_q2stream_original"))
        self.assertTrue(hasattr(deal.DetectionDeal.__init__, "_q2stream_original"))
        obj = deal.DetectionDeal(None, None, FakePrinter())
        self.assertEqual(started, [obj])

    def test_the_release_can_be_switched_off_alone(self):
        self.assertTrue(self.q.install(environ={"Q2_STREAM_RELEASE": "off"}))
        deal = importlib.import_module("src.detection_deal")
        self.assertTrue(hasattr(deal.DetectionDeal.decrypt_weight, "_q2stream_original"))
        self.assertFalse(hasattr(deal.DetectionDeal.__init__, "_q2stream_original"))

    def test_the_decrypt_can_be_switched_off_alone(self):
        self.q.start_watcher = lambda inst: None
        self.assertTrue(self.q.install(environ={"Q2_STREAM_DECRYPT": "off"}))
        deal = importlib.import_module("src.detection_deal")
        self.assertFalse(hasattr(deal.DetectionDeal.decrypt_weight, "_q2stream_original"))
        self.assertTrue(hasattr(deal.DetectionDeal.__init__, "_q2stream_original"))

    def test_both_off_installs_nothing(self):
        self.assertFalse(self.q.install(environ={"Q2_STREAM_DECRYPT": "off", "Q2_STREAM_RELEASE": "off"}))


if __name__ == "__main__":
    unittest.main()
