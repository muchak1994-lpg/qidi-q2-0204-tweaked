# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""q2stream - the AI service of the QIDI Q2 (algo_app) decrypts its model block by block, written for Python 3.9.

Installed as <algo_app>/_internal/cv2/q2stream/__init__.py. OpenCV's own loader (cv2/__init__.py) imports every
sub-folder of the cv2 package at the very end of `import cv2`; this file therefore runs once, early in the service's
start, before QIDI's module `src.detection_deal` exists. No file of QIDI's or of OpenCV's is changed.

The problem: DetectionDeal.decrypt_weight() reads the whole encrypted model (44.6 MB), decrypts it into a second copy,
removes the padding into a third copy and only then writes the file the model is loaded from. For a moment the service
holds about 134 MB more than it needs, at the worst moment for Klipper (the model is loaded in the second layer of a
print, when the printer has the least free memory).

What this file does: it puts a finder at the front of sys.meta_path. When QIDI's module `src.detection_deal` is
imported, the finder lets the normal import machinery do its work and then, right after the module has been executed,
calls patch(module): the method DetectionDeal.decrypt_weight is replaced by one that does exactly the same, with the same
key, cipher and result file, but reads, decrypts and writes 1 MiB at a time (AES-CBC can be decrypted in a stream: every
block only needs the block of ciphertext before it). The peak is a few MiB instead of about 134 MB.

Safety:
  * The method is only replaced when it still looks exactly like the one this was written for (its local variable names
    and the names it uses). A new QIDI version that changed it is left alone, with a warning in the log.
  * The cipher, the padding function and the key are taken from QIDI's own module and object. No key is written here.
  * If anything at all goes wrong in the new method, the temporary file is deleted and QIDI's original method does the
    job (so a damaged model file gives the very same error as before).
  * Off switch: the environment variable Q2_STREAM_DECRYPT=off (also 0 / no / false), read once at the service start.

The log lines go to the logger "app.q2stream", a child of QIDI's logger "app" (file /var/log/algo_app/app_*.log).
"""
import logging
import os
import sys
import threading

LOGGER_NAME = "app.q2stream"
TARGET = "src.detection_deal"
CHUNK = 1024 * 1024  # a multiple of 16 (the AES block size)
OFF_WORDS = ("off", "0", "no", "false", "disable", "disabled")

# What QIDI's method looks like (from the service's own byte code): the local variables, in order, and names it uses.
EXPECTED_VARNAMES = ("self", "encrypted_path", "key", "f_in", "iv", "ciphertext", "cipher", "padded_plaintext",
                     "plaintext", "temp_model")
REQUIRED_NAMES = frozenset(("encryption_key", "AES", "MODE_CBC", "decrypt", "unpad", "block_size", "tempfile",
                            "NamedTemporaryFile"))
NEEDED_GLOBALS = ("AES", "unpad", "tempfile")


def _log():
    return logging.getLogger(LOGGER_NAME)


def _looks_like_qidis_method(method):
    code = getattr(method, "__code__", None)
    if code is None or code.co_argcount != 2:
        return False
    if tuple(code.co_varnames) != EXPECTED_VARNAMES:
        return False
    if not REQUIRED_NAMES <= set(code.co_names):
        return False
    glob = getattr(method, "__globals__", None)
    return isinstance(glob, dict) and all(name in glob for name in NEEDED_GLOBALS)


def _discard(temp):
    """Close and delete the temporary file of a failed attempt (never raises)."""
    if temp is None:
        return
    try:
        temp.close()
    except Exception:
        pass
    try:
        os.unlink(temp.name)
    except Exception:
        pass


def _streaming_method(original):
    """The replacement for DetectionDeal.decrypt_weight; `original` is QIDI's method (the fallback)."""

    def decrypt_weight(self, encrypted_path):
        temp = None
        try:
            glob = original.__globals__
            aes, unpad, tempfile = glob["AES"], glob["unpad"], glob["tempfile"]
            key = self.encryption_key.encode()[:32].ljust(32, b"\x00")
            temp = tempfile.NamedTemporaryFile(delete=False)
            blocks = 0
            size = 0
            with open(encrypted_path, "rb") as f_in:
                iv = f_in.read(16)
                cipher = aes.new(key, aes.MODE_CBC, iv)
                held = b""  # the newest decrypted block of data is kept back: the padding is cut from the very last
                while True:
                    chunk = f_in.read(CHUNK)
                    if not chunk:
                        break
                    plain = cipher.decrypt(chunk)
                    if held:
                        temp.write(held)
                        size += len(held)
                    held = plain
                    blocks += 1
                tail = unpad(held, aes.block_size)
            temp.write(tail)
            size += len(tail)
            temp.close()
            name = temp.name
        except Exception as exc:
            _discard(temp)
            try:
                _log().warning("q2stream: streaming decrypt failed (%r), falls back to QIDI's own method", exc)
            except Exception:
                pass
            return original(self, encrypted_path)
        try:
            _log().info("q2stream: model decrypted in %d block(s) of at most %d KiB, %.1f MB written", blocks,
                        CHUNK // 1024, size / 1e6)
        except Exception:
            pass
        return name

    decrypt_weight._q2stream_original = original
    decrypt_weight.__name__ = getattr(original, "__name__", "decrypt_weight")
    decrypt_weight.__doc__ = "Block-by-block version of QIDI's method (q2stream)."
    return decrypt_weight


def patch(module):
    """Replace DetectionDeal.decrypt_weight in QIDI's module. True when replaced now; False when not (already done,
    not the method this was written for, or any problem - this function never raises)."""
    try:
        cls = getattr(module, "DetectionDeal", None)
        original = getattr(cls, "decrypt_weight", None) if cls is not None else None
        if original is None:
            return False
        if getattr(original, "_q2stream_original", None) is not None:
            return False
        if not _looks_like_qidis_method(original):
            _log().warning("q2stream: DetectionDeal.decrypt_weight is not the method this was written for, "
                           "not patched (the model is loaded the old way)")
            return False
        cls.decrypt_weight = _streaming_method(original)
        _log().info("q2stream: DetectionDeal.decrypt_weight now decrypts the model in %d KiB blocks", CHUNK // 1024)
        return True
    except Exception as exc:
        try:
            _log().warning("q2stream: not patched: %r", exc)
        except Exception:
            pass
        return False


IDLE_SECONDS = 120      # the printer must have been idle this long (in a row) before the model is given back
POLL_SECONDS = 5
MAX_RELEASE_ERRORS = 5  # after this many failed releases the watcher stops trying until the service restarts
_flags = {"decrypt": True, "release": True}


def _malloc_trim():
    """Ask glibc to give free heap memory back to the system (a Python-level release alone leaves it in the process)."""
    import ctypes
    ctypes.CDLL("libc.so.6").malloc_trim(0)


def _rss_mb():
    try:
        with open("/proc/self/status", "r") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    except Exception:
        pass
    return None


def _printer_busy(inst):
    """True unless it is certain that the printer is neither printing, beginning a print nor paused."""
    try:
        printer = getattr(inst, "printer", None)
        if printer is None:
            return True
        for name in ("is_printing", "is_printing_begin"):
            if getattr(printer, name, True):
                return True
        paused = getattr(printer, "is_paused", None)
        if not callable(paused) or paused():
            return True
        return False
    except Exception:
        return True


class Releaser(object):
    """Decides, one look at a time, when the noodle model can be given back. step() never raises."""

    def __init__(self, idle_seconds=IDLE_SECONDS):
        self.idle = idle_seconds
        self.idle_since = None
        self.errors = 0

    def step(self, inst, now):
        """One look at the service. Returns "busy", "nothing", "waiting", "released", "error" or "off"."""
        if self.errors >= MAX_RELEASE_ERRORS:
            return "off"
        if _printer_busy(inst):
            self.idle_since = None
            return "busy"
        if getattr(inst, "detector", None) is None:
            self.idle_since = None
            return "nothing"
        if self.idle_since is None:
            self.idle_since = now
            return "waiting"
        if now - self.idle_since < self.idle:
            return "waiting"
        if _printer_busy(inst):  # look again right before: a print may have started meanwhile
            self.idle_since = None
            return "busy"
        before = _rss_mb()
        try:
            inst.detector_release()  # QIDI's own method: release_model(), detector = None, gc.collect()
            import gc
            gc.collect()
            _malloc_trim()
        except Exception as exc:
            self.errors += 1
            self.idle_since = None
            try:
                _log().warning("q2stream: releasing the model failed (%r) (%d of %d)", exc, self.errors,
                               MAX_RELEASE_ERRORS)
            except Exception:
                pass
            return "error"
        self.idle_since = None
        after = _rss_mb()
        try:
            if before is not None and after is not None:
                _log().info("q2stream: noodle model released after the print (process memory %.0f -> %.0f MB)", before, after)
            else:
                _log().info("q2stream: noodle model released after the print")
        except Exception:
            pass
        return "released"


def run_watcher(ref, releaser, clock=None, sleep=None, poll=POLL_SECONDS, max_loops=None):
    """The watcher thread's loop: ref is a weak reference to the DetectionDeal. Ends when the object is gone or its
    stop_event is set. Nothing a step does can end it (max_loops is for the tests)."""
    import time
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    loops = 0
    warned = False
    while max_loops is None or loops < max_loops:
        inst = ref()
        if inst is None:
            return
        try:
            stop = getattr(inst, "stop_event", None)
            if stop is not None and stop.is_set():
                return
            releaser.step(inst, clock())
        except Exception as exc:
            if not warned:
                warned = True
                try:
                    _log().warning("q2stream: watcher step failed: %r", exc)
                except Exception:
                    pass
        del inst  # never hold the object while sleeping
        sleep(poll)
        loops += 1


def start_watcher(inst):
    import threading
    import weakref
    thread = threading.Thread(target=run_watcher, args=(weakref.ref(inst), Releaser()), name="q2stream-release",
                              daemon=True)
    thread.start()


def patch_release(module):
    """Wrap DetectionDeal.__init__ so that every object gets a watcher thread. True when done now; False when not
    (already done, not the class this was written for, or any problem - this function never raises)."""
    try:
        cls = getattr(module, "DetectionDeal", None)
        original = getattr(cls, "__init__", None) if cls is not None else None
        if original is None or getattr(original, "_q2stream_original", None) is not None:
            return False
        code = getattr(original, "__code__", None)
        if code is None or tuple(code.co_varnames[:4]) != ("self", "config", "vi", "printer") \
                or code.co_argcount != 4 or not callable(getattr(cls, "detector_release", None)):
            _log().debug("q2stream: DetectionDeal is not the class the release was written for, not patched")
            return False

        def __init__(self, *args, **kwargs):
            original(self, *args, **kwargs)
            try:
                start_watcher(self)
            except Exception as exc:
                try:
                    _log().warning("q2stream: could not start the release watcher: %r", exc)
                except Exception:
                    pass

        __init__._q2stream_original = original
        cls.__init__ = __init__
        _log().info("q2stream: the noodle model is given back %d s after a print (no restart needed)", IDLE_SECONDS)
        return True
    except Exception as exc:
        try:
            _log().warning("q2stream: release not patched: %r", exc)
        except Exception:
            pass
        return False


class _Loader(object):
    """Stands in for the real loader of src.detection_deal for the moment of its import: runs the real one, then
    patches. It puts the real loader back into the module before running it, so the module never keeps us."""

    def __init__(self, real):
        self._real = real

    def create_module(self, spec):
        create = getattr(self._real, "create_module", None)
        return create(spec) if create is not None else None

    def exec_module(self, module):
        real = self._real
        try:
            module.__spec__.loader = real
            module.__loader__ = real
        except Exception:
            pass
        real.exec_module(module)
        if _flags["decrypt"]:
            patch(module)
        if _flags["release"]:
            patch_release(module)

    def __getattr__(self, name):
        return getattr(self._real, name)


class _Finder(object):
    _q2stream_finder = True

    def __init__(self):
        self._local = threading.local()

    def find_spec(self, fullname, path=None, target=None):
        if fullname != TARGET or getattr(self._local, "busy", False):
            return None
        self._local.busy = True
        try:
            spec = None
            for finder in list(sys.meta_path):
                if finder is self:
                    continue
                find = getattr(finder, "find_spec", None)
                if find is None:
                    continue
                spec = find(fullname, path, target)
                if spec is not None:
                    break
        finally:
            self._local.busy = False
        if spec is not None and spec.loader is not None and hasattr(spec.loader, "exec_module"):
            spec.loader = _Loader(spec.loader)
        return spec


def install(environ=None):
    """Put the finder in place (and patch QIDI's module at once if it was imported already). True when done now;
    False when not (switched off, already there, or any problem - this function never raises)."""
    try:
        env = os.environ if environ is None else environ
        _flags["decrypt"] = str(env.get("Q2_STREAM_DECRYPT", "")).strip().lower() not in OFF_WORDS
        _flags["release"] = str(env.get("Q2_STREAM_RELEASE", "")).strip().lower() not in OFF_WORDS
        if not (_flags["decrypt"] or _flags["release"]):
            return False
        if any(getattr(f, "_q2stream_finder", False) for f in sys.meta_path):
            return False
        sys.meta_path.insert(0, _Finder())
        module = sys.modules.get(TARGET)
        if module is not None:
            if _flags["decrypt"]:
                patch(module)
            if _flags["release"]:
                patch_release(module)
        return True
    except Exception as exc:
        try:
            _log().warning("q2stream: not installed: %r", exc)
        except Exception:
            pass
        return False


def uninstall():
    """Take the finder out again (the tests use this; the service never does)."""
    sys.meta_path[:] = [f for f in sys.meta_path if not getattr(f, "_q2stream_finder", False)]


install()
