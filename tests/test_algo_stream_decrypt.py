#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""algo-app-stream-decrypt: the AI service decrypts its model in 1 MiB blocks instead of holding three whole copies.

QIDI's DetectionDeal.decrypt_weight reads the whole encrypted model, decrypts it, un-pads it (three copies of 44.6 MB
at once) and writes it to a temporary file. The module's package q2stream replaces that one method after QIDI's module
`src.detection_deal` has been imported: same result, same file, but block by block. Whatever goes wrong, the original
method gets to do the job (so the new code can never be worse than the old one).

The tests use a fake block cipher (a toy CBC with the interface of pycryptodome's AES, so the tests run anywhere) and,
when this machine has the `cryptography` package, real AES-CBC too. No QIDI file, model or key is needed or used.
Run:  python tests/test_algo_stream_decrypt.py
"""
import ast
import importlib
import importlib.util
import json
import logging
import os
import sys
import tempfile
import textwrap
import tracemalloc
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOD = ROOT / "modules" / "algo-app-stream-decrypt"
SRC = MOD / "files" / "q2stream" / "__init__.py"
BLOCK = 16
MIB = 1024 * 1024
TEST_KEY = "unit-test-key"  # the tests' own key; QIDI's key is never written anywhere in this project


# ---------------------------------------------------------------- a stand-in for Crypto.Cipher.AES and Padding.unpad
def _xor(a, b):
    n = len(a)
    return (int.from_bytes(a, "big") ^ int.from_bytes(b, "big")).to_bytes(n, "big")


class ToyCbc(object):
    """CBC with a toy block cipher (XOR with the key): the chaining and the padding are the real thing, so the
    streaming logic is tested for real; only the block cipher itself is a toy. Stateful decrypt like AES-CBC."""

    def __init__(self, key, iv):
        if len(iv) != BLOCK:
            raise ValueError("Incorrect IV length (it must be 16 bytes long)")
        self.k = key[:BLOCK]
        self.prev = bytes(iv)

    def decrypt(self, data):
        if len(data) % BLOCK:
            raise ValueError("Data must be padded to 16 byte boundary in CBC mode")
        if not data:
            return b""
        keys = self.k * (len(data) // BLOCK)
        plain = _xor(_xor(data, keys), self.prev + data[:-BLOCK])
        self.prev = bytes(data[-BLOCK:])
        return plain

    def encrypt(self, data):
        out = []
        for i in range(0, len(data), BLOCK):
            block = _xor(data[i:i + BLOCK], self.prev)
            self.prev = _xor(block, self.k)
            out.append(self.prev)
        return b"".join(out)


class ToyAES(object):
    block_size = BLOCK
    MODE_CBC = 2

    @staticmethod
    def new(key, mode, iv):
        return ToyCbc(key, iv)


def pad(data):
    n = BLOCK - len(data) % BLOCK
    return data + bytes([n]) * n


def unpad(data, block_size, style="pkcs7"):
    """Like Crypto.Util.Padding.unpad."""
    if not data:
        raise ValueError("Zero-length input cannot be unpadded")
    if len(data) % block_size:
        raise ValueError("Input data is not padded")
    n = data[-1]
    if n < 1 or n > min(block_size, len(data)) or data[-n:] != bytes([n]) * n:
        raise ValueError("PKCS#7 padding is incorrect.")
    return data[:-n]


def real_aes():
    """An AES with pycryptodome's interface from the `cryptography` package, or None."""
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError:
        return None

    class Cbc(object):
        def __init__(self, key, iv):
            if len(iv) != BLOCK:
                raise ValueError("Incorrect IV length (it must be 16 bytes long)")
            self.c = Cipher(algorithms.AES(key), modes.CBC(iv))
            self.d = self.c.decryptor()

        def decrypt(self, data):
            if len(data) % BLOCK:
                raise ValueError("Data must be padded to 16 byte boundary in CBC mode")
            return self.d.update(data)

    class RealAES(object):
        block_size = BLOCK
        MODE_CBC = 2

        @staticmethod
        def new(key, mode, iv):
            return Cbc(key, iv)

    def encrypt(key, iv, plain):
        enc = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
        return enc.update(pad(plain)) + enc.finalize()

    return RealAES, encrypt


# ---------------------------------------------------------------- QIDI's method, as a copy of the decompiled code
# (the fingerprint of the real one is: co_varnames below and the names AES, unpad, tempfile, encryption_key)
ORIGINAL_METHOD = '''
def decrypt_weight(self, encrypted_path):
    key = self.encryption_key.encode()[:32].ljust(32, b'\\x00')
    with open(encrypted_path, 'rb') as f_in:
        iv = f_in.read(16)
        ciphertext = f_in.read()

    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded_plaintext = cipher.decrypt(ciphertext)
    plaintext = unpad(padded_plaintext, AES.block_size)

    temp_model = tempfile.NamedTemporaryFile(delete=False)
    temp_model.write(plaintext)
    temp_model.close()
    return temp_model.name
'''


def make_module(method_source=ORIGINAL_METHOD, aes=ToyAES, name="src.detection_deal", temp=None):
    """A module like QIDI's src.detection_deal: a class DetectionDeal with the original decrypt_weight."""
    module = types.ModuleType(name)
    module.AES = aes
    module.unpad = unpad
    module.tempfile = temp or tempfile
    exec(compile(textwrap.dedent(method_source), "<detection_deal>", "exec"), module.__dict__)

    class DetectionDeal(object):
        def __init__(self):
            self.encryption_key = TEST_KEY

    DetectionDeal.decrypt_weight = module.__dict__.pop("decrypt_weight")
    module.DetectionDeal = DetectionDeal
    return module


def encrypted_file(folder, plain, aes_encrypt=None, name="model.enc"):
    """Write `plain` encrypted with TEST_KEY (as DetectionDeal derives the key) to a file; returns the path."""
    key = TEST_KEY.encode()[:32].ljust(32, b"\x00")
    iv = bytes(range(1, 17))
    data = aes_encrypt(key, iv, plain) if aes_encrypt else iv + ToyCbc(key, iv).encrypt(pad(plain))
    if aes_encrypt:
        data = iv + data
    path = os.path.join(folder, name)
    with open(path, "wb") as handle:
        handle.write(data)
    return path


def load_package():
    spec = importlib.util.spec_from_file_location("q2stream_under_test", SRC)
    module = importlib.util.module_from_spec(spec)
    keys = ("Q2_STREAM_DECRYPT", "Q2_STREAM_RELEASE")
    before = {k: os.environ.get(k) for k in keys}
    for k in keys:
        os.environ[k] = "off"  # the file installs itself when imported: not in the tests' own process
    try:
        spec.loader.exec_module(module)
    finally:
        for k in keys:
            if before[k] is None:
                del os.environ[k]
            else:
                os.environ[k] = before[k]
    return module


def pattern(size):
    return (bytes(range(256)) * (size // 256 + 1))[:size]


class Base(unittest.TestCase):
    def setUp(self):
        import importlib.util  # noqa: F401  (load_package needs it)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.q = load_package()
        self.records = []
        handler = logging.Handler()
        handler.emit = self.records.append
        self.logger = logging.getLogger(self.q.LOGGER_NAME)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.DEBUG)
        self.addCleanup(self.logger.removeHandler, handler)

    def decrypt_both(self, plain, aes=ToyAES, aes_encrypt=None):
        """(original result, patched result) of the same file; each is bytes or the exception it raised."""
        path = encrypted_file(self.tmp.name, plain, aes_encrypt)
        results = []
        for patched in (False, True):
            module = make_module(aes=aes)
            if patched:
                self.assertTrue(self.q.patch(module))
            obj = module.DetectionDeal()
            try:
                out = obj.decrypt_weight(path)
                with open(out, "rb") as handle:
                    results.append(handle.read())
                os.unlink(out)
            except Exception as exc:  # noqa: BLE001 - the comparison needs the exception itself
                results.append(exc)
        return results

    def messages(self):
        return [r.getMessage() for r in self.records]


class SameResultAsTheOriginal(Base):
    def test_many_sizes_around_the_block_edges(self):
        sizes = [0, 1, 15, 16, 17, 31, 32, 1000, MIB - 17, MIB - 16, MIB - 1, MIB, MIB + 1, 2 * MIB - 16,
                 2 * MIB, 2 * MIB + 15, 3 * MIB + 5]
        for size in sizes:
            plain = pattern(size)
            old, new = self.decrypt_both(plain)
            self.assertEqual(old, plain, size)
            self.assertEqual(new, plain, "size %d" % size)

    def test_random_looking_data(self):
        plain = os.urandom(2 * MIB + 123)
        old, new = self.decrypt_both(plain)
        self.assertEqual(new, old)
        self.assertEqual(new, plain)

    def test_real_aes_when_available(self):
        real = real_aes()
        if real is None:
            self.skipTest("the cryptography package is not installed here")
        aes, encrypt = real
        for size in (0, 1, 16, MIB - 1, MIB, MIB + 17, 2 * MIB + 3):
            plain = os.urandom(size)
            old, new = self.decrypt_both(plain, aes=aes, aes_encrypt=encrypt)
            self.assertEqual(old, plain, size)
            self.assertEqual(new, plain, size)

    def test_temp_file_is_a_normal_named_temporary_file(self):
        module = make_module()
        self.assertTrue(self.q.patch(module))
        path = encrypted_file(self.tmp.name, pattern(5000))
        out = module.DetectionDeal().decrypt_weight(path)
        self.addCleanup(os.unlink, out)
        self.assertTrue(os.path.isfile(out))
        self.assertEqual(os.path.getsize(out), 5000)
        self.assertNotEqual(os.path.abspath(out), os.path.abspath(path))


class WhenTheDataIsBad(Base):
    def count_temp_files(self):
        created = []
        real = tempfile.NamedTemporaryFile

        def tracking(*args, **kwargs):
            handle = real(*args, **kwargs)
            created.append(handle.name)
            return handle

        return created, tracking

    def run_bad(self, data):
        """Run the patched method on a file with `data`; returns (exception or None, created temp names)."""
        path = os.path.join(self.tmp.name, "bad.enc")
        with open(path, "wb") as handle:
            handle.write(data)
        created, tracking = self.count_temp_files()
        temp = types.SimpleNamespace(NamedTemporaryFile=tracking)
        module = make_module(temp=temp)
        self.assertTrue(self.q.patch(module))
        try:
            module.DetectionDeal().decrypt_weight(path)
        except Exception as exc:  # noqa: BLE001
            return exc, created
        return None, created

    def test_wrong_padding_raises_the_same_error_as_the_original_and_leaves_no_file(self):
        key = TEST_KEY.encode()[:32].ljust(32, b"\x00")
        iv = bytes(16)
        body = ToyCbc(key, iv).encrypt(pattern(2 * MIB + 16))  # a multiple of 16, but no padding in it
        exc, created = self.run_bad(iv + body)
        self.assertIsInstance(exc, ValueError)
        for name in created:
            self.assertFalse(os.path.exists(name), "a temp file was left behind: " + name)

    def test_length_not_a_multiple_of_16(self):
        exc, created = self.run_bad(bytes(16) + bytes(MIB + 7))
        self.assertIsInstance(exc, ValueError)
        for name in created:
            self.assertFalse(os.path.exists(name))

    def test_empty_file_and_iv_only_and_short_iv(self):
        for data in (b"", bytes(16), bytes(5)):
            exc, created = self.run_bad(data)
            self.assertIsInstance(exc, ValueError, repr(data))
            for name in created:
                self.assertFalse(os.path.exists(name))

    def test_missing_file_raises_what_the_original_raises(self):
        module = make_module()
        self.assertTrue(self.q.patch(module))
        with self.assertRaises(FileNotFoundError):
            module.DetectionDeal().decrypt_weight(os.path.join(self.tmp.name, "nothing-here.enc"))


class TheOriginalDoesTheJobWhenTheStreamFails(Base):
    def test_a_cipher_without_state_between_calls_falls_back_to_the_original(self):
        class OneShot(ToyCbc):
            raised = False

            def decrypt(self, data):
                if not OneShot.raised and len(data) == MIB:  # only a block-by-block caller sends exactly 1 MiB
                    OneShot.raised = True
                    raise TypeError("pretend this cipher cannot work block by block")
                return ToyCbc.decrypt(self, data)

        class FlakyAES(ToyAES):
            @staticmethod
            def new(key, mode, iv):
                return OneShot(key, iv)

        plain = pattern(2 * MIB + 9)
        old, new = self.decrypt_both(plain, aes=FlakyAES)
        self.assertEqual(new, plain)
        self.assertEqual(old, plain)
        self.assertTrue(any("falls back" in m or "fell back" in m or "fall back" in m for m in self.messages()),
                        self.messages())


class FewerCopiesInMemory(Base):
    def peak(self, patched, size):
        module = make_module()
        if patched:
            self.assertTrue(self.q.patch(module))
        path = encrypted_file(self.tmp.name, pattern(size))
        obj = module.DetectionDeal()
        tracemalloc.start()
        try:
            out = obj.decrypt_weight(path)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        os.unlink(out)
        return peak

    def test_peak_memory_does_not_grow_with_the_size_of_the_model(self):
        small, big = 4 * MIB, 12 * MIB
        old_small, old_big = self.peak(False, small), self.peak(False, big)
        new_small, new_big = self.peak(True, small), self.peak(True, big)
        self.assertGreater(old_big, 3 * big, "the original should hold about three copies (%d)" % old_big)
        self.assertGreater(old_big - old_small, 20 * MIB, "the original grows with the file")
        self.assertLess(new_big - new_small, MIB, "the streaming version must not grow with the file: %d -> %d"
                        % (new_small, new_big))
        self.assertLess(new_big, big, "less than one copy of the model: %d" % new_big)


class FingerprintAndPatching(Base):
    def test_patch_marks_the_method_and_logs(self):
        module = make_module()
        original = module.DetectionDeal.decrypt_weight
        self.assertTrue(self.q.patch(module))
        patched = module.DetectionDeal.decrypt_weight
        self.assertIsNot(patched, original)
        self.assertIs(getattr(patched, "_q2stream_original"), original)
        self.assertTrue(any("q2stream: " in m for m in self.messages()))

    def test_patching_twice_does_nothing_the_second_time(self):
        module = make_module()
        self.assertTrue(self.q.patch(module))
        first = module.DetectionDeal.decrypt_weight
        self.assertFalse(self.q.patch(module))
        self.assertIs(module.DetectionDeal.decrypt_weight, first)

    def test_a_changed_method_is_left_alone_with_a_warning(self):
        changed = ORIGINAL_METHOD.replace("ciphertext", "everything")  # QIDI renamed a variable: not our code any more
        module = make_module(method_source=changed)
        original = module.DetectionDeal.decrypt_weight
        self.assertFalse(self.q.patch(module))
        self.assertIs(module.DetectionDeal.decrypt_weight, original)
        self.assertTrue(any("not patched" in m for m in self.messages()), self.messages())

    def test_a_method_that_uses_other_names_is_left_alone(self):
        other = ORIGINAL_METHOD.replace("AES.new(key, AES.MODE_CBC, iv)", "AES.new(key, AES.MODE_CBC, iv)  # x").replace(
            "unpad(padded_plaintext, AES.block_size)", "padded_plaintext[:-1]")
        module = make_module(method_source=other)
        original = module.DetectionDeal.decrypt_weight
        self.assertFalse(self.q.patch(module))
        self.assertIs(module.DetectionDeal.decrypt_weight, original)

    def test_no_class_or_no_method_never_raises(self):
        self.assertFalse(self.q.patch(types.ModuleType("src.detection_deal")))
        module = types.ModuleType("src.detection_deal")
        module.DetectionDeal = type("DetectionDeal", (), {})
        self.assertFalse(self.q.patch(module))
        self.assertFalse(self.q.patch(None))


class ImportHook(Base):
    """The hook that patches QIDI's module when it is imported (it does not exist yet when our package loads)."""

    def setUp(self):
        Base.setUp(self)
        self.pkg = Path(self.tmp.name) / "fakeapp"
        (self.pkg / "src").mkdir(parents=True)
        (self.pkg / "src" / "__init__.py").write_text("", encoding="utf-8")
        (self.pkg / "src" / "other.py").write_text("VALUE = 7\n", encoding="utf-8")
        header = "import tempfile\nfrom q2stream_fake_crypto import AES, unpad\n\nclass DetectionDeal(object):\n    def __init__(self):\n        self.encryption_key = %r\n\n" % TEST_KEY
        body = textwrap.indent(textwrap.dedent(ORIGINAL_METHOD), "    ")
        (self.pkg / "src" / "detection_deal.py").write_text(header + body, encoding="utf-8")
        fake = types.ModuleType("q2stream_fake_crypto")
        fake.AES = ToyAES
        fake.unpad = unpad
        sys.modules["q2stream_fake_crypto"] = fake
        sys.path.insert(0, str(self.pkg))
        self.addCleanup(self.cleanup)
        for name in [n for n in sys.modules if n == "src" or n.startswith("src.")]:
            del sys.modules[name]

    def cleanup(self):
        self.q.uninstall()
        sys.path.remove(str(self.pkg))
        sys.modules.pop("q2stream_fake_crypto", None)
        for name in [n for n in sys.modules if n == "src" or n.startswith("src.")]:
            del sys.modules[name]

    def test_importing_the_module_patches_it(self):
        self.assertTrue(self.q.install(environ={}))
        deal = importlib.import_module("src.detection_deal")
        self.assertTrue(hasattr(deal.DetectionDeal.decrypt_weight, "_q2stream_original"))
        path = encrypted_file(self.tmp.name, pattern(3 * MIB + 1))
        out = deal.DetectionDeal().decrypt_weight(path)
        self.addCleanup(os.unlink, out)
        with open(out, "rb") as handle:
            self.assertEqual(handle.read(), pattern(3 * MIB + 1))

    def test_the_module_keeps_its_own_loader_and_other_modules_are_untouched(self):
        self.assertTrue(self.q.install(environ={}))
        deal = importlib.import_module("src.detection_deal")
        other = importlib.import_module("src.other")
        self.assertEqual(other.VALUE, 7)
        self.assertNotIn("q2stream", type(deal.__spec__.loader).__module__)
        self.assertNotIn("q2stream", type(deal.__loader__).__module__)
        self.assertEqual(deal.__spec__.name, "src.detection_deal")

    def test_installing_twice_adds_one_finder(self):
        self.assertTrue(self.q.install(environ={}))
        self.assertFalse(self.q.install(environ={}))
        self.assertEqual(len([f for f in sys.meta_path if getattr(f, "_q2stream_finder", False)]), 1)

    def test_off_switch_by_environment(self):
        for word in ("off", "0", "no", "false"):
            self.assertFalse(self.q.install(environ={"Q2_STREAM_DECRYPT": word, "Q2_STREAM_RELEASE": word}), word)
        deal = importlib.import_module("src.detection_deal")
        self.assertFalse(hasattr(deal.DetectionDeal.decrypt_weight, "_q2stream_original"))

    def test_already_imported_module_is_patched_at_once(self):
        deal = importlib.import_module("src.detection_deal")
        self.assertTrue(self.q.install(environ={}))
        self.assertTrue(hasattr(deal.DetectionDeal.decrypt_weight, "_q2stream_original"))

    def test_uninstall_removes_the_finder(self):
        self.assertTrue(self.q.install(environ={}))
        self.q.uninstall()
        self.assertEqual([f for f in sys.meta_path if getattr(f, "_q2stream_finder", False)], [])

    def test_an_import_error_inside_the_module_is_not_hidden(self):
        (self.pkg / "src" / "broken_one.py").write_text("raise RuntimeError('boom')\n", encoding="utf-8")
        self.assertTrue(self.q.install(environ={}))
        with self.assertRaises(RuntimeError):
            importlib.import_module("src.broken_one")

    def test_missing_module_still_raises_import_error(self):
        self.assertTrue(self.q.install(environ={}))
        with self.assertRaises(ImportError):
            importlib.import_module("src.no_such_module_here")


class SourceAndModule(unittest.TestCase):
    def test_source_is_python_39_ascii_with_header_and_no_key(self):
        text = SRC.read_text(encoding="utf-8")
        ast.parse(text, feature_version=(3, 9))
        self.assertIn("SPDX-License-Identifier: GPL-3.0-or-later", " ".join(text.splitlines()[:3]))
        text.encode("ascii")
        self.assertNotIn("encryption_key =", text)  # the key is read from the object, never written down here
        self.assertNotIn("import Crypto", text)  # the cipher comes from QIDI's own module (its globals)

    def test_module_json(self):
        spec = json.loads((MOD / "module.json").read_text(encoding="utf-8"))
        self.assertEqual(spec["id"], "algo-app-stream-decrypt")
        self.assertTrue(spec.get("default", True))
        self.assertEqual(spec["restart"], ["algo_app"])
        (target, entry), = spec["files"].items()
        self.assertEqual(target, "/usr/local/bin/algo_app/_internal/cv2/q2stream/__init__.py")
        self.assertEqual((MOD / entry["source"]).resolve(), SRC.resolve())
        self.assertNotIn("edits", entry)
        self.assertNotIn("byte_edits", entry)

    def test_build_accepts_the_module(self):
        sys.path.insert(0, str(ROOT / "tools"))
        try:
            import build
            mods = [m for m in build.load_modules() if m["id"] == "algo-app-stream-decrypt"]
            self.assertEqual(len(mods), 1)
            files, owners = build.build(mods, stock_reader=lambda p: self.fail("no stock file expected"),
                                        with_sources=False)
        finally:
            sys.path.pop(0)
        self.assertEqual(list(files), ["/usr/local/bin/algo_app/_internal/cv2/q2stream/__init__.py"])


if __name__ == "__main__":
    unittest.main()
