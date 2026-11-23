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
        patch(module)

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
        if str(env.get("Q2_STREAM_DECRYPT", "")).strip().lower() in OFF_WORDS:
            return False
        if any(getattr(f, "_q2stream_finder", False) for f in sys.meta_path):
            return False
        sys.meta_path.insert(0, _Finder())
        module = sys.modules.get(TARGET)
        if module is not None:
            patch(module)
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
