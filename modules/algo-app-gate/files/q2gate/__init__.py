# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""q2gate - brightness gate for the camera AI of the QIDI Q2 (service algo_app), written for Python 3.9.

Installed as <algo_app>/_internal/cv2/q2gate/__init__.py. OpenCV's own loader (cv2/__init__.py) imports every
sub-folder of the cv2 package at the very end of `import cv2`, so this file runs once, inside the AI service, after
cv2 is complete and before the service opens its first camera. No file of QIDI's or of OpenCV's is changed.

What it does: cv2.VideoCapture is replaced by a wrapper class (never a subclass: that crashes the printer's OpenCV) whose read() looks at each frame. A frame whose mean grey
value is below THRESHOLD (22) is a frame of a dark case (light off): there the noodle model reports false noodle
(it reads the toolhead LEDs as noodle). Such a frame is replaced by a uniform grey frame of FILL (19), the colour of
the dark background, which both models treat as "nothing to see". Every other frame is returned untouched (the very
same object). The grey value uses OpenCV's BGR2GRAY weights on a sampled grid of about 160 x 120 pixels.

It must never hurt the AI service: any error inside the gate returns the original frame, is logged once, and after
MAX_ERRORS errors the gate switches itself off for the rest of the process. Nothing is kept between frames.

Settings (all optional). Environment variables (read once, when the service starts; systemd drop-in):
    Q2_GATE=off          do not touch cv2 at all (also 0 / no / false)
    Q2_GATE_THRESHOLD    mean grey value below which a frame is dark (default 22)
    Q2_GATE_FILL         grey value of the replacement frame, 0..255 (default 19)
    Q2_GATE_LOG_EVERY    log every N-th dark frame (default 300; the first one is always logged)
    Q2_GATE_CONF         path of the file below (default /etc/q2-algo-gate.conf)
A file /etc/q2-algo-gate.conf (not installed by the module; made by hand) is read again every 30 seconds, so it
works without a restart. Words separated by spaces, commas or lines; "#" starts a comment:
    off                  the gate passes every frame unchanged (also: on)
    threshold=22 fill=19 log_every=300
The environment wins over the file. Wrong values are ignored.

The log lines go to the logger "app.q2gate", a child of QIDI's logger "app" (file /var/log/algo_app/app_*.log).
"""
import logging
import os
import sys
import time

try:
    import numpy as np
except Exception:  # without numpy there is nothing to do (the AI service always has it)
    np = None

LOGGER_NAME = "app.q2gate"
DEFAULT_THRESHOLD = 22.0
DEFAULT_FILL = 19
DEFAULT_LOG_EVERY = 300
DEFAULT_CONF = "/etc/q2-algo-gate.conf"
REFRESH_SECONDS = 30
MAX_ERRORS = 20
SAMPLE_COLUMNS = 160  # the grid has about this many columns: 640 wide -> every 4th pixel, 1920 wide -> every 12th

_OFF = ("off", "0", "no", "false", "disable", "disabled")
_ON = ("on", "1", "yes", "true", "enable", "enabled")


_RANGES = {"threshold": (0.0, 255.0, float), "fill": (0, 255, int), "log_every": (1, 10 ** 9, int)}


def _number(text, name):
    """text as the number `name` stands for (inside its allowed range), or None."""
    low, high, kind = _RANGES[name]
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    if value != value or not low <= value <= high:
        return None
    return kind(value)


class Settings(object):
    """Threshold, fill, logging interval and the off switch: defaults, then the file, then the environment."""

    def __init__(self, environ=None, clock=None):
        source = os.environ if environ is None else environ
        keys = ("Q2_GATE", "Q2_GATE_THRESHOLD", "Q2_GATE_FILL", "Q2_GATE_LOG_EVERY", "Q2_GATE_CONF")
        self._env = {k: source.get(k) for k in keys if source.get(k) not in (None, "")}  # a copy: read once
        self.conf_path = self._env.get("Q2_GATE_CONF") or DEFAULT_CONF
        self.clock = clock or time.monotonic
        self.version = 0
        self._checked = None
        self._values = None
        self.enabled, self.threshold, self.fill, self.log_every = True, DEFAULT_THRESHOLD, DEFAULT_FILL, DEFAULT_LOG_EVERY
        self.env_off = self._env.get("Q2_GATE", "").strip().lower() in _OFF
        self.refresh(force=True)

    def refresh(self, force=False):
        """Read the file again (at most every REFRESH_SECONDS)."""
        now = self.clock()
        if not force and self._checked is not None and 0 <= now - self._checked < REFRESH_SECONDS:
            return
        self._checked = now
        try:
            with open(self.conf_path, "r") as handle:
                text = handle.read(4096)
        except (OSError, ValueError):  # no file (the normal case), or not readable text
            text = ""
        self._apply(text)

    def _apply(self, text):
        enabled = True
        values = {"threshold": DEFAULT_THRESHOLD, "fill": DEFAULT_FILL, "log_every": DEFAULT_LOG_EVERY}
        for line in text.splitlines():
            for word in line.split("#", 1)[0].replace(",", " ").split():
                key, equals, value = word.partition("=")
                key = key.lower()
                if not equals:
                    if key in _OFF:
                        enabled = False
                    elif key in _ON:
                        enabled = True
                elif key in values and _number(value, key) is not None:
                    values[key] = _number(value, key)
        for name in values:  # the environment wins over the file
            number = _number(self._env.get("Q2_GATE_" + name.upper()), name)
            if number is not None:
                values[name] = number
        if self._env.get("Q2_GATE", "").strip().lower() in _ON:
            enabled = True
        if self.env_off:
            enabled = False
        current = (enabled, values["threshold"], values["fill"], values["log_every"])
        if current != self._values:
            if self._values is not None:
                self.version += 1
            self._values = current
            self.enabled, self.threshold, self.fill, self.log_every = current


class Gate(object):
    """Looks at the frames a capture returns and replaces the dark ones. One instance per process."""

    def __init__(self, settings, logger=None):
        self.settings = settings
        self.logger = logger or logging.getLogger(LOGGER_NAME)
        self.seen = 0
        self.dark = 0
        self.errors = 0
        self.broken = False
        self._announced = False
        self._warned = False
        self._version = settings.version

    @staticmethod
    def frame_mean(frame):
        """Mean grey value 0..255 of a sampled grid of the frame (OpenCV's BGR2GRAY weights, integer arithmetic so
        that a uniform frame of 22 gives exactly 22.0); None for anything that is not an 8-bit image."""
        if frame.dtype != np.uint8 or frame.ndim not in (2, 3) or frame.size == 0:
            return None
        step = max(1, max(frame.shape[0], frame.shape[1]) // SAMPLE_COLUMNS)
        view = frame[::step, ::step]
        if view.ndim == 3 and view.shape[2] in (3, 4):
            blue, green, red = [int(view[..., i].sum(dtype=np.int64)) for i in range(3)]  # 7x faster than one axis=(0, 1) sum
            return (114 * blue + 587 * green + 299 * red) / (1000.0 * view.shape[0] * view.shape[1])
        return int(view.sum(dtype=np.int64)) / float(view.size)

    def apply(self, result, target=None):
        """result is what read() returned, (ok, frame). Returns it unchanged, or with the frame replaced.
        target: the buffer the caller passed to read(), if any (then that buffer is filled instead)."""
        try:
            if self.broken:
                return result
            settings = self.settings
            settings.refresh()
            if settings.version != self._version:
                self._version = settings.version
                self._announced = False
            if not self._announced:
                self._announce()
            if not settings.enabled:
                return result
            if not isinstance(result, tuple) or len(result) != 2:
                return result
            ok, frame = result
            if not ok or not isinstance(frame, np.ndarray):
                return result
            self.seen += 1
            mean = self.frame_mean(frame)
            if mean is None or not mean < settings.threshold:
                return result
            if target is not None and frame is target:
                frame[...] = settings.fill
                new = frame
            else:
                new = np.full(frame.shape, settings.fill, dtype=np.uint8)
            self.dark += 1
            if self.dark == 1 or self.dark % settings.log_every == 0:
                self.logger.info("q2gate: dark frame replaced by a uniform %d (%d so far, mean grey %.1f, %d frames seen)",
                                 settings.fill, self.dark, mean, self.seen)
            return (ok, new)
        except Exception as exc:  # the AI service must get its frame whatever happens here
            self._failed(exc)
            return result

    def opened(self):
        """A capture was created (the AI service does that at its start, when its logger is ready): say we are here."""
        try:
            if not self._announced:
                self._announce()
        except Exception:
            pass

    def _announce(self):
        self._announced = True
        s = self.settings
        if s.enabled:
            self.logger.info("q2gate: active - frames with a mean grey value below %s become a uniform %d "
                             "(every %d-th dark frame is logged)", s.threshold, s.fill, s.log_every)
        else:
            self.logger.info("q2gate: loaded but switched off (%s)", s.conf_path)

    def _failed(self, exc):
        try:
            self.errors += 1
            if not self._warned:
                self._warned = True
                self.logger.warning("q2gate: error in the gate, frames are passed on unchanged: %r", exc)
            if self.errors >= MAX_ERRORS and not self.broken:
                self.broken = True
                self.logger.warning("q2gate: %d errors, the gate is off until the service restarts", self.errors)
        except Exception:
            self.broken = True


def _wrap(base, gate):
    """The class that replaces cv2.VideoCapture: a WRAPPER around a real capture, never a subclass of it.

    A Python subclass of cv2.VideoCapture crashes the process on the printer (OpenCV 4.12, aarch64: "free(): invalid
    pointer" when an instance is freed; measured on the printer, plain objects are fine)."""
    class WrappedVideoCapture(object):
        _q2gate_class = True
        _q2gate = gate

        def __init__(self, *args, **kwargs):
            self._cap = base(*args, **kwargs)
            gate.opened()

        def read(self, *args, **kwargs):
            target = args[0] if args else kwargs.get("image")
            return gate.apply(self._cap.read(*args, **kwargs), target)

        def retrieve(self, *args, **kwargs):
            target = args[0] if args else kwargs.get("image")
            return gate.apply(self._cap.retrieve(*args, **kwargs), target)

        def __getattr__(self, name):
            return getattr(self._cap, name)

        def __enter__(self):
            self._cap.__enter__()
            return self

        def __exit__(self, *exc):
            return self._cap.__exit__(*exc)

    cls = WrappedVideoCapture
    cls.__name__ = getattr(base, "__name__", "VideoCapture")
    cls.__qualname__ = cls.__name__
    cls.__module__ = getattr(base, "__module__", "cv2")
    return cls


def install(cv2_module=None, environ=None, clock=None):
    """Put the gate on cv2.VideoCapture. True when it was put there now; False when not (already there, switched
    off, no cv2, or any problem - this function never raises)."""
    try:
        if np is None:
            return False
        if cv2_module is None:
            cv2_module = sys.modules.get("cv2")
        if cv2_module is None:
            return False
        base = getattr(cv2_module, "VideoCapture", None)
        if base is None or getattr(base, "_q2gate_class", False):
            return False
        settings = Settings(environ, clock)
        if settings.env_off:
            return False
        cv2_module.VideoCapture = _wrap(base, Gate(settings))
        return True
    except Exception as exc:
        try:
            logging.getLogger(LOGGER_NAME).warning("q2gate: not installed: %r", exc)
        except Exception:
            pass
        return False


install()
