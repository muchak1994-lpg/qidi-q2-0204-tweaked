#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""algo-app-gate: the brightness gate that runs inside the AI service (path 2: no change to QIDI's `main`).

The package modules/algo-app-gate/files/q2gate/ is installed as _internal/cv2/q2gate/. OpenCV's own loader imports every
sub-folder of the cv2 package at the end of `import cv2`; our code then wraps cv2.VideoCapture.read(): a frame whose
mean grey value is below 22 (case light off) comes back as a uniform grey frame, every other frame is returned as it is.

The tests use a fake `cv2` (a module with a fake VideoCapture class), so they run anywhere with numpy. One extra test
class runs OpenCV's real loader on a pip copy of cv2, when this machine has one (a Windows pip OpenCV does).
Run:  python tests/test_algo_gate.py        (or in WSL: python3 tests/test_algo_gate.py)
"""
import ast
import gc
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
import weakref
from pathlib import Path
from unittest import mock

try:
    import numpy as np
except ImportError:  # the gate needs numpy (the AI service has it); nothing to test without it
    np = None

ROOT = Path(__file__).resolve().parent.parent
MOD = ROOT / "modules" / "algo-app-gate"
GATE = MOD / "files" / "q2gate" / "__init__.py"
LOGGER = "app.q2gate"
SCRIPTED = []  # results (ret, frame) the next fake read()/retrieve() calls return


class FakeCapture:
    """What cv2.VideoCapture looks like to the AI service: open, set/get, read, release."""

    def __init__(self, *args, **kwargs):
        self.args = args
        self.released = False

    def isOpened(self):
        return True

    def set(self, prop, value):
        return True

    def get(self, prop):
        return 640.0

    def read(self, *args):
        return SCRIPTED.pop(0)

    def retrieve(self, *args):
        return SCRIPTED.pop(0)

    def release(self):
        self.released = True


class SealedCapture:
    """A class that cannot be subclassed (the gate then has to wrap it instead)."""

    def __init_subclass__(cls, **kwargs):
        raise TypeError("sealed")

    def __init__(self, *args):
        self.opened = True

    def isOpened(self):
        return self.opened

    def read(self, *args):
        return SCRIPTED.pop(0)

    def release(self):
        self.opened = False


def fake_cv2(capture=FakeCapture):
    module = types.ModuleType("cv2")
    module.VideoCapture = capture
    return module


def load_gate(name="q2gate_under_test", cv2_module=None, env=None, conf=None):
    """Import the gate source file the way OpenCV's loader does: as a module, with `cv2` already in sys.modules."""
    spec = importlib.util.spec_from_file_location(name, str(GATE))
    mod = importlib.util.module_from_spec(spec)
    patch_env = {"Q2_GATE_CONF": conf or os.path.join(tempfile.gettempdir(), "q2gate-no-such-config")}
    patch_env.update(env or {})
    with mock.patch.dict(sys.modules, {"cv2": cv2_module if cv2_module is not None else sys.modules["cv2"]}), \
            mock.patch.dict(os.environ, patch_env):
        spec.loader.exec_module(mod)
    return mod


def frame_of(value, shape=(480, 640, 3)):
    return np.full(shape, value, dtype=np.uint8)


def dark_frame():
    """A real dark frame of the case-light-off camera: neutral grey 19 plus a small bright green spot (the toolhead LEDs)."""
    f = frame_of(19)
    f[10:30, 300:340] = (0, 200, 0)
    return f


def light_frame():
    f = frame_of(50)
    f[100:200, 100:300] = (60, 120, 200)
    return f


@unittest.skipIf(np is None, "numpy is needed")
class GateBase(unittest.TestCase):
    def setUp(self):
        SCRIPTED.clear()
        self.cv2 = fake_cv2()
        self.mod = load_gate(cv2_module=self.cv2)
        self.cap = self.cv2.VideoCapture("http://127.0.0.1/webcam/?action=stream")

    def read(self, frame, ret=True):
        SCRIPTED.append((ret, frame))
        return self.cap.read()


class DarkAndLightFrames(GateBase):
    def test_dark_frame_comes_back_uniform_with_same_shape_and_dtype(self):
        original = dark_frame()
        before = original.copy()
        ret, out = self.read(original)
        self.assertTrue(ret)
        self.assertEqual(out.shape, original.shape)
        self.assertEqual(out.dtype, original.dtype)
        self.assertTrue((out == 19).all())
        self.assertTrue((original == before).all(), "the camera's own frame must not be modified")

    def test_light_frame_is_returned_as_the_same_object(self):
        original = light_frame()
        result = (True, original)
        SCRIPTED.append(result)
        got = self.cap.read()
        self.assertIs(got, result)
        self.assertIs(got[1], original)

    def test_threshold_boundary(self):
        f22 = frame_of(22)
        self.assertIs(self.read(f22)[1], f22)  # 22.0 is not below 22.0
        f21 = frame_of(21)
        out = self.read(f21)[1]
        self.assertIsNot(out, f21)
        self.assertTrue((out == 19).all())
        almost = frame_of(22)
        almost[0, 0] = (21, 21, 21)  # mean a hair below 22 (pixel 0,0 is always sampled)
        out = self.read(almost)[1]
        self.assertTrue((out == 19).all())

    def test_threshold_uses_grey_weights_not_a_plain_channel_mean(self):
        green = frame_of(0)
        green[...] = (0, 40, 0)  # BGR: grey = 0.587 * 40 = 23.5 -> light (a plain channel mean would say 13.3)
        self.assertIs(self.read(green)[1], green)
        red = frame_of(0)
        red[...] = (0, 0, 60)  # grey = 0.299 * 60 = 17.9 -> dark
        self.assertTrue((self.read(red)[1] == 19).all())

    def test_sampled_mean_is_close_to_the_full_frame_mean(self):
        rng = np.random.RandomState(1)
        smooth = (np.linspace(0, 255, 640)[None, :, None] * np.ones((480, 1, 3))).astype(np.uint8)
        noisy = rng.randint(0, 80, size=(480, 640, 3)).astype(np.uint8)
        for f in (smooth, noisy, dark_frame(), light_frame()):
            full = (0.114 * f[..., 0] + 0.587 * f[..., 1] + 0.299 * f[..., 2]).mean()
            self.assertLess(abs(self.mod.Gate.frame_mean(f) - full), 1.0)  # a 0..255 ramp is the worst case

    def test_retrieve_is_gated_like_read(self):
        SCRIPTED.append((True, dark_frame()))
        ret, out = self.cap.retrieve()
        self.assertTrue((out == 19).all())

    def test_other_methods_are_untouched(self):
        self.assertTrue(self.cap.isOpened())
        self.assertEqual(self.cap.get(3), 640.0)
        self.assertTrue(self.cap.set(38, 1))
        self.cap.release()
        self.assertTrue(self.cap.released)
        self.assertIsInstance(self.cap, self.cv2.VideoCapture)  # the replacement class (a wrapper, see NeverSubclassTheCapture)

    def test_failed_read_passes_through(self):
        result = (False, None)
        SCRIPTED.append(result)
        self.assertIs(self.cap.read(), result)
        with_frame = (False, dark_frame())
        SCRIPTED.append(with_frame)
        self.assertIs(self.cap.read(), with_frame)


class OddFrames(GateBase):
    def test_grey_two_dimensional_frame(self):
        out = self.read(np.full((48, 64), 10, np.uint8))[1]
        self.assertEqual(out.shape, (48, 64))
        self.assertTrue((out == 19).all())
        light = np.full((48, 64), 90, np.uint8)
        self.assertIs(self.read(light)[1], light)

    def test_four_channel_and_single_channel_frames(self):
        bgra = np.full((48, 64, 4), 10, np.uint8)
        self.assertTrue((self.read(bgra)[1] == 19).all())
        self.assertEqual(self.read(bgra)[1].shape, (48, 64, 4))
        one = np.full((48, 64, 1), 10, np.uint8)
        self.assertEqual(self.read(one)[1].shape, (48, 64, 1))
        bright = np.full((48, 64, 1), 100, np.uint8)
        self.assertIs(self.read(bright)[1], bright)

    def test_tiny_and_empty_frames(self):
        for shape in ((1, 1, 3), (3, 3, 3), (1, 640, 3)):
            self.assertEqual(self.read(frame_of(5, shape))[1].shape, shape)
        empty = np.zeros((0, 0, 3), np.uint8)
        self.assertIs(self.read(empty)[1], empty)

    def test_non_uint8_frames_are_left_alone(self):
        f = np.zeros((48, 64, 3), np.uint16)
        self.assertIs(self.read(f)[1], f)
        g = np.zeros((48, 64, 3), np.float32)
        self.assertIs(self.read(g)[1], g)

    def test_non_contiguous_and_big_frames(self):
        base = np.full((960, 1280, 3), 10, np.uint8)
        view = base[::2, ::2]
        self.assertTrue((self.read(view)[1] == 19).all())
        big = frame_of(10, (1080, 1920, 3))
        self.assertTrue((self.read(big)[1] == 19).all())

    def test_not_an_array_and_odd_results_pass_through(self):
        for odd in ((True, "not a frame"), (True, None)):
            SCRIPTED.append(odd)
            self.assertIs(self.cap.read(), odd)
        SCRIPTED.append(None)
        self.assertIsNone(self.cap.read())


class Failures(GateBase):
    def test_exception_inside_the_gate_returns_the_original_and_is_logged_once(self):
        def boom(frame):
            raise RuntimeError("boom")

        self.mod.Gate.frame_mean = staticmethod(boom)
        original = dark_frame()
        with self.assertLogs(LOGGER, level="DEBUG") as logs:
            for _ in range(3):
                result = (True, original)
                SCRIPTED.append(result)
                self.assertIs(self.cap.read(), result)
        warnings = [r for r in logs.records if r.levelname == "WARNING"]
        self.assertEqual(len(warnings), 1)

    def test_too_many_errors_switch_the_gate_off_for_good(self):
        def boom(frame):
            raise RuntimeError("boom")

        self.mod.Gate.frame_mean = staticmethod(boom)
        gate = self.cv2.VideoCapture._q2gate
        with self.assertLogs(LOGGER, level="DEBUG"):
            for _ in range(self.mod.MAX_ERRORS + 5):
                SCRIPTED.append((True, dark_frame()))
                self.cap.read()
        self.assertTrue(gate.broken)
        self.mod.Gate.frame_mean = staticmethod(lambda frame: 1.0)  # even a working gate stays off
        out = self.read(dark_frame())[1]
        self.assertFalse((out == 19).all())

    def test_underlying_exception_is_not_swallowed(self):
        class Raising(FakeCapture):
            def read(self, *args):
                raise OSError("camera gone")

        cv2 = fake_cv2(Raising)
        load_gate("q2gate_raising", cv2)
        with self.assertRaises(OSError):
            cv2.VideoCapture("x").read()

    def test_autostart_never_raises_when_the_install_fails(self):
        class BadCv2(types.ModuleType):
            @property
            def VideoCapture(self):
                raise ZeroDivisionError("broken cv2")

        bad = BadCv2("cv2")
        with self.assertLogs(LOGGER, "WARNING"):
            mod = load_gate("q2gate_failing", bad)  # importing the gate must not raise
            self.assertFalse(mod.install(bad))
        with mock.patch.object(mod, "Gate", side_effect=RuntimeError("no gate")), self.assertLogs(LOGGER, "WARNING"):
            self.assertFalse(mod.install(fake_cv2()))  # install() reports False instead of raising

    def test_no_cv2_at_all(self):
        spec = importlib.util.spec_from_file_location("q2gate_nocv2", str(GATE))
        mod = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, {"cv2": None}):  # `cv2` is not there: sys.modules.get gives None
            spec.loader.exec_module(mod)
            self.assertFalse(mod.install(None))
        self.assertFalse(mod.install(types.ModuleType("cv2")))  # a cv2 without VideoCapture

    def test_buffer_given_to_read_is_filled_in_place(self):
        buffer = dark_frame()
        SCRIPTED.append((True, buffer))
        ret, out = self.cap.read(buffer)
        self.assertIs(out, buffer)
        self.assertTrue((buffer == 19).all())


class ImportTwice(GateBase):
    def test_second_import_does_not_wrap_again(self):
        first = self.cv2.VideoCapture
        load_gate("q2gate_second", self.cv2)
        load_gate("q2gate_third", self.cv2)
        self.assertIs(self.cv2.VideoCapture, first)
        wrappers = [c for c in self.cv2.VideoCapture.__mro__ if c.__dict__.get("_q2gate_class")]
        self.assertEqual(len(wrappers), 1)
        out = self.read(dark_frame())[1]
        self.assertTrue((out == 19).all())
        self.assertEqual(self.cv2.VideoCapture._q2gate.dark, 1)

    def test_reloading_the_same_module_is_harmless(self):
        spec = importlib.util.spec_from_file_location("q2gate_reload", str(GATE))
        mod = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, {"cv2": self.cv2}):
            spec.loader.exec_module(mod)
            spec.loader.exec_module(mod)
        self.assertEqual(len([c for c in self.cv2.VideoCapture.__mro__ if c.__dict__.get("_q2gate_class")]), 1)


@unittest.skipIf(np is None, "numpy is needed")
class Switches(unittest.TestCase):
    def setUp(self):
        SCRIPTED.clear()

    def test_off_switch_by_environment_leaves_cv2_alone(self):
        for value in ("off", "0", "no", "false", "OFF"):
            cv2 = fake_cv2()
            load_gate("q2gate_off", cv2, env={"Q2_GATE": value})
            self.assertIs(cv2.VideoCapture, FakeCapture, value)

    def test_environment_sets_threshold_fill_and_log_every(self):
        cv2 = fake_cv2()
        load_gate("q2gate_env", cv2, env={"Q2_GATE_THRESHOLD": "30", "Q2_GATE_FILL": "12", "Q2_GATE_LOG_EVERY": "5"})
        cap = cv2.VideoCapture("x")
        SCRIPTED.append((True, frame_of(25)))
        out = cap.read()[1]
        self.assertTrue((out == 12).all())
        gate = cv2.VideoCapture._q2gate
        self.assertEqual((gate.settings.threshold, gate.settings.fill, gate.settings.log_every), (30.0, 12, 5))

    def test_bad_values_fall_back_to_the_defaults(self):
        cv2 = fake_cv2()
        load_gate("q2gate_bad", cv2, env={"Q2_GATE_THRESHOLD": "abc", "Q2_GATE_FILL": "999", "Q2_GATE_LOG_EVERY": "-3"})
        s = cv2.VideoCapture._q2gate.settings
        self.assertEqual((s.threshold, s.fill, s.log_every), (22.0, 19, 300))

    def test_config_file_and_runtime_off_switch(self):
        with tempfile.TemporaryDirectory() as tmp:
            conf = os.path.join(tmp, "q2-algo-gate.conf")
            clock = [1000.0]
            cv2 = fake_cv2()
            mod = load_gate("q2gate_conf", cv2, conf=conf)
            gate = cv2.VideoCapture._q2gate
            gate.settings.clock = lambda: clock[0]
            cap = cv2.VideoCapture("x")

            def read(frame):
                SCRIPTED.append((True, frame))
                return cap.read()[1]

            self.assertTrue((read(frame_of(10)) == 19).all())  # no file: defaults
            with open(conf, "w") as f:
                f.write("# the gate is switched off\noff\n")
            self.assertTrue((read(frame_of(10)) == 19).all(), "the file is looked at only every REFRESH_SECONDS")
            clock[0] += mod.REFRESH_SECONDS + 1
            dark = frame_of(10)
            self.assertIs(read(dark), dark)  # off without a restart
            with open(conf, "w") as f:
                f.write("threshold=12 fill=7 log_every=2\n")
            clock[0] += mod.REFRESH_SECONDS + 1
            self.assertTrue((read(frame_of(10)) == 7).all())
            bright = frame_of(13)  # above the new threshold
            self.assertIs(read(bright), bright)
            os.remove(conf)
            clock[0] += mod.REFRESH_SECONDS + 1
            self.assertTrue((read(frame_of(10)) == 19).all())  # back to the defaults

    def test_config_file_parsing(self):
        with tempfile.TemporaryDirectory() as tmp:
            conf = os.path.join(tmp, "c")
            with open(conf, "w") as f:
                f.write("threshold=25,fill=20 junk log_every=7 # comment fill=99\nthreshold=bad\n")
            mod = load_gate("q2gate_parse", fake_cv2(), conf=conf)
            s = mod.Settings(environ={"Q2_GATE_CONF": conf})
            self.assertEqual((s.enabled, s.threshold, s.fill, s.log_every), (True, 25.0, 20, 7))
            s = mod.Settings(environ={"Q2_GATE_CONF": conf, "Q2_GATE_FILL": "3"})  # the environment wins
            self.assertEqual(s.fill, 3)
            self.assertEqual(mod.Settings(environ={"Q2_GATE_CONF": os.path.join(tmp, "missing")}).threshold, 22.0)


class Logging(GateBase):
    def test_one_active_line_when_the_first_capture_is_opened_then_first_dark_frame_then_every_n(self):
        cv2 = fake_cv2()
        load_gate("q2gate_logging", cv2, env={"Q2_GATE_LOG_EVERY": "4"})
        with self.assertLogs(LOGGER, level="DEBUG") as logs:
            cap = cv2.VideoCapture("a")  # the service opens a capture at its start: that is when we say hello
            cv2.VideoCapture("b")
            for _ in range(3):
                SCRIPTED.append((True, light_frame()))
                cap.read()
            for _ in range(9):
                SCRIPTED.append((True, dark_frame()))
                cap.read()
        lines = [r.getMessage() for r in logs.records]
        self.assertEqual(sum("active" in m for m in lines), 1, lines)
        self.assertIn("active", lines[0])
        counted = [m for m in lines if "dark frame replaced" in m]
        self.assertEqual(len(counted), 3, lines)  # dark frame no. 1, 4 and 8
        for text, number in zip(counted, (1, 4, 8)):
            self.assertIn("(%d so far" % number, text)
        self.assertTrue(all(r.name == LOGGER for r in logs.records))
        self.assertTrue(all(r.levelname == "INFO" for r in logs.records))

    def test_light_frames_log_nothing_after_the_first_line(self):
        self.read(light_frame())
        with self.assertRaises(AssertionError):  # assertLogs fails when nothing is logged
            with self.assertLogs(LOGGER, level="DEBUG"):
                for _ in range(20):
                    self.read(light_frame())

    def test_counters(self):
        gate = self.cv2.VideoCapture._q2gate
        for f in (light_frame(), dark_frame(), dark_frame(), light_frame()):
            self.read(f)
        self.assertEqual((gate.seen, gate.dark), (4, 2))


class Memory(GateBase):
    def test_nothing_is_kept_between_frames(self):
        gate = self.cv2.VideoCapture._q2gate
        original = dark_frame()
        ref_in = weakref.ref(original)
        out = self.read(original)[1]
        ref_out = weakref.ref(out)
        del original, out
        SCRIPTED.clear()
        gc.collect()
        self.assertIsNone(ref_in())
        self.assertIsNone(ref_out())
        for value in vars(gate).values():
            self.assertNotIsInstance(value, np.ndarray)


@unittest.skipIf(np is None, "numpy is needed")
class NeverSubclassTheCapture(unittest.TestCase):
    """cv2.VideoCapture of OpenCV 4.12 on the printer (aarch64) crashes the process (free(): invalid pointer) as soon as an
    instance of a Python SUBCLASS of it is freed (measured 22.11.2026: plain object fine, subclass 5 of 5 crashes). The gate
    must therefore wrap the capture, also when the type could be subclassed."""

    def test_the_replacement_is_a_wrapper_not_a_subclass(self):
        SCRIPTED.clear()
        cv2 = fake_cv2(FakeCapture)
        load_gate("q2gate_nosub", cv2)
        self.assertIsNot(cv2.VideoCapture, FakeCapture)
        self.assertFalse(issubclass(cv2.VideoCapture, FakeCapture))
        cap = cv2.VideoCapture("x")
        self.assertFalse(isinstance(cap, FakeCapture))
        self.assertTrue(cap.isOpened())
        SCRIPTED.append((True, dark_frame()))
        self.assertTrue((cap.read()[1] == 19).all())
        self.assertEqual(cap.get(3), 640.0)
        cap.release()


@unittest.skipIf(np is None, "numpy is needed")
class WrapperFallback(unittest.TestCase):
    def test_class_that_cannot_be_subclassed_is_wrapped_instead(self):
        SCRIPTED.clear()
        cv2 = fake_cv2(SealedCapture)
        load_gate("q2gate_sealed", cv2)
        cap = cv2.VideoCapture("x")
        self.assertIsNot(cv2.VideoCapture, SealedCapture)
        self.assertTrue(cap.isOpened())  # delegated
        SCRIPTED.append((True, dark_frame()))
        self.assertTrue((cap.read()[1] == 19).all())
        light = light_frame()
        SCRIPTED.append((True, light))
        self.assertIs(cap.read()[1], light)
        cap.release()
        self.assertFalse(cap.isOpened())


class SourceAndModule(unittest.TestCase):
    def test_source_is_python_39_and_has_the_licence_header(self):
        text = GATE.read_text(encoding="utf-8")
        ast.parse(text, feature_version=(3, 9))
        self.assertIn("SPDX-License-Identifier: GPL-3.0-or-later", " ".join(text.splitlines()[:3]))
        text.encode("ascii")  # plain ASCII: nothing to go wrong with the file's encoding on the printer
        # cv2 is looked up in sys.modules (it is half-built while OpenCV's loader runs this file): no import by name
        self.assertIsNone(re.search(r"^\s*(import cv2|from cv2)", text, re.M), "do not import cv2 by name")

    def test_module_json(self):
        spec = json.loads((MOD / "module.json").read_text(encoding="utf-8"))
        self.assertEqual(spec["id"], "algo-app-gate")
        self.assertEqual(spec["default"], False)
        self.assertEqual(spec["order"], 153)
        self.assertEqual(spec["restart"], ["algo_app"])
        (target, entry), = spec["files"].items()
        # a folder without a leading underscore inside the cv2 package: OpenCV's loader imports it
        self.assertEqual(target, "/usr/local/bin/algo_app/_internal/cv2/q2gate/__init__.py")
        self.assertEqual((MOD / entry["source"]).resolve(), GATE.resolve())
        self.assertNotIn("edits", entry)  # no file of QIDI's or OpenCV's is edited
        self.assertNotIn("byte_edits", entry)

    def test_build_accepts_the_module(self):
        sys.path.insert(0, str(ROOT / "tools"))
        try:
            import build
            mods = [m for m in build.load_modules() if m["id"] == "algo-app-gate"]
            self.assertEqual(len(mods), 1)
            files, owners = build.build(mods, stock_reader=lambda p: self.fail("no stock file expected"),
                                        with_sources=False)
        finally:
            sys.path.pop(0)
        self.assertEqual(list(files), ["/usr/local/bin/algo_app/_internal/cv2/q2gate/__init__.py"])


def pip_cv2_dir():
    """The folder of a pip-installed OpenCV package that has the loader with extra sub-modules, or None."""
    try:
        spec = importlib.util.find_spec("cv2")
    except (ImportError, ValueError):
        return None
    if spec is None or not spec.submodule_search_locations:
        return None
    folder = Path(list(spec.submodule_search_locations)[0])
    init = folder / "__init__.py"
    if init.is_file() and "__collect_extra_submodules" in init.read_text(encoding="utf-8", errors="replace"):
        return folder
    return None


class RealOpenCvLoader(unittest.TestCase):
    """OpenCV's real loader (the same file the printer has) imports the q2gate folder and the gate is in place."""

    @unittest.skipIf(pip_cv2_dir() is None, "no pip OpenCV package with the extra-sub-module loader on this machine")
    def test_loader_imports_the_folder(self):
        src = pip_cv2_dir()
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "cv2"
            pkg.mkdir()
            for item in src.iterdir():
                if item.is_file() and item.suffix in (".py",):
                    shutil.copy2(item, pkg / item.name)
                elif item.is_file() and (item.suffix in (".pyd", ".dll", ".so") or ".so." in item.name):
                    try:
                        os.link(item, pkg / item.name)
                    except OSError:
                        shutil.copy2(item, pkg / item.name)
                elif item.is_dir() and item.name in ("mat_wrapper", "misc", "utils", "typing", "data", "gapi"):
                    shutil.copytree(item, pkg / item.name, ignore=shutil.ignore_patterns("__pycache__"))
            libs = src.parent / "opencv_python.libs"
            if libs.is_dir():
                os.symlink(libs, Path(tmp) / "opencv_python.libs", target_is_directory=True)
            shutil.copytree(GATE.parent, pkg / "q2gate", ignore=shutil.ignore_patterns("__pycache__"))
            code = (
                "import sys; sys.path.insert(0, %r)\n"
                "import cv2\n"
                "cap = cv2.VideoCapture('no-such-file.avi')\n"
                "print('LOADED', 'cv2.q2gate' in sys.modules, hasattr(cv2.VideoCapture, '_q2gate'), "
                "isinstance(cap, cv2.VideoCapture), cap.isOpened(), cap.read()[0])\n" % tmp)
            env = dict(os.environ, Q2_GATE_CONF=os.path.join(tmp, "none"))
            env.pop("Q2_GATE", None)
            run = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=120)
            self.assertIn("LOADED True True True False False", run.stdout, run.stdout + run.stderr)
            # and with the off switch OpenCV is left exactly as it was
            env["Q2_GATE"] = "off"
            run = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=120)
            self.assertIn("LOADED True False True False False", run.stdout, run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
