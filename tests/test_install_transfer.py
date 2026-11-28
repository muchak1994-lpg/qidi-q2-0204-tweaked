#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic)
"""How files get onto the printer: a file is always the old one or the new one, many files travel in one upload,
and the connection is compressed.

The tests of the real shell commands run them in a temporary folder with this computer's sh (Linux only: Windows
has no GNU install/mv); nothing is sent anywhere.

Run:  python tests/test_install_transfer.py
"""
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))
sys.path.insert(0, str(HERE))
import build  # noqa: E402
import firmware  # noqa: E402
import install  # noqa: E402
import printer  # noqa: E402
from test_install import FakePrinter, MODS, STOCK, sha  # noqa: E402

FAN = "/home/qidi/klipper/klippy/extras/fan.py"
CFG = "/home/qidi/printer_data/config/printer.cfg"


# ------------------------------------------------------------------ the real commands, run on this computer
class Channel:
    def __init__(self, process):
        self.process = process

    def recv_exit_status(self):
        return self.process.wait()


class Stdin:
    def __init__(self, process):
        self.process = process

    def write(self, text):
        self.process.stdin.write(text.encode() if isinstance(text, str) else text)

    def flush(self):
        self.process.stdin.flush()


class Stdout:
    def __init__(self, process):
        self.process, self.channel = process, Channel(process)

    def read(self):
        self.process.stdin.close()
        return self.process.stdout.read()

    def __iter__(self):
        self.process.stdin.close()
        for line in self.process.stdout:
            yield line.decode()


class Stderr:
    def __init__(self, process):
        self.process = process

    def read(self):
        return self.process.stderr.read()


class LocalClient:
    """Stands in for paramiko: every command runs in this computer's sh, uploads are local files."""

    def __init__(self, env):
        self.env, self.commands, self.uploads, self.processes = env, [], [], []

    def exec_command(self, command, timeout=None):
        self.commands.append(command)
        process = subprocess.Popen(["sh", "-c", command], env=self.env, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.processes.append(process)
        return Stdin(process), Stdout(process), Stderr(process)

    def open_sftp(self):
        client = self

        class SFTP:
            def putfo(self, source, path):
                client.uploads.append(path)
                Path(path).write_bytes(source.read())

        return SFTP()

    def close(self):
        pass


FAKE_SUDO = """#!/bin/sh
while [ "$#" -gt 0 ]; do
  case "$1" in
    -n) shift ;;
    -S) read -r password; [ "$password" = "secret" ] || exit 1; shift ;;
    -p) shift 2 ;;
    *) break ;;
  esac
done
exec "$@"
"""


@unittest.skipUnless(os.name == "posix" and shutil.which("sh"), "needs a Linux shell")
class RealCommandsTest(unittest.TestCase):
    password = None

    def setUp(self):
        import grp
        import pwd
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.tool("sudo", FAKE_SUDO)
        self.env = dict(os.environ, PATH="%s:%s" % (self.bin, os.environ["PATH"]))
        self.client = LocalClient(self.env)
        self.p = install.SSHPrinter("test", "mks", self.password, client=self.client)
        self.addCleanup(self.p.close)
        self.who = (pwd.getpwuid(os.getuid()).pw_name, grp.getgrgid(os.getgid()).gr_name)
        self.root = self.tmp / "printer files"  # a space: every path must be quoted
        self.root.mkdir()

    def tool(self, name, script):
        path = self.bin / name
        path.write_bytes(script.encode())
        path.chmod(0o755)

    def break_tool(self, name, when, instead="exit 1"):
        """From now on `name` fails (or does `instead`) when its arguments contain `when`."""
        real = shutil.which(name, path=os.environ["PATH"])
        self.tool(name, '#!/bin/sh\ncase "$*" in *"%s"*) %s ;; esac\nexec %s "$@"\n' % (when, instead, real))

    def item(self, name, data, mode="644"):
        return (str(self.root / name), data) + self.who + (mode,)

    def put(self, name, data, mode="644"):
        path, data, owner, group, mode = self.item(name, data, mode)
        self.p.install(data, path, owner, group, mode)

    def content(self, name):
        path = self.root / name
        return path.read_bytes() if path.exists() else None

    def leftovers(self):
        return sorted(str(f.relative_to(self.root)) for f in self.root.rglob("*.q2tmp"))

    def many(self, items):
        log = []
        self.p.install_many(items, lambda: log.append("sending"), lambda path: log.append(Path(path).name))
        return log

    def test_a_file_is_replaced_and_no_temporary_file_stays(self):
        self.put("a.cfg", b"old\n")
        self.put("a.cfg", b"new\n", "600")
        self.assertEqual(self.content("a.cfg"), b"new\n")
        self.assertEqual((self.root / "a.cfg").stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.leftovers(), [])

    def test_a_copy_cut_half_way_leaves_the_old_file(self):
        self.put("a.cfg", b"old content\n")
        # "install ... SOURCE TARGET": write a few bytes of the source into the target, then die
        self.break_tool("install", "a.cfg", 'for a; do s=$t; t=$a; done; head -c 3 "$s" > "$t"; exit 1')
        with self.assertRaises(install.InstallError):
            self.put("a.cfg", b"new content\n")
        self.assertEqual(self.content("a.cfg"), b"old content\n")
        (self.bin / "install").unlink()
        self.put("a.cfg", b"new content\n")  # the next run finishes the job and takes the leftover with it
        self.assertEqual(self.content("a.cfg"), b"new content\n")
        self.assertEqual(self.leftovers(), [])

    def test_a_cut_before_the_swap_leaves_the_old_file(self):
        self.put("a.cfg", b"old\n")
        self.break_tool("mv", "a.cfg")
        with self.assertRaises(install.InstallError):
            self.put("a.cfg", b"new\n")
        self.assertEqual(self.content("a.cfg"), b"old\n")
        self.assertEqual(self.leftovers(), ["a.cfg.q2tmp"])

    def test_remove_takes_the_temporary_file_too(self):
        self.put("a.cfg", b"old\n")
        (self.root / "a.cfg.q2tmp").write_bytes(b"half")
        self.p.remove(str(self.root / "a.cfg"))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_many_files_travel_in_one_upload_and_each_is_reported(self):
        self.put("b.sh", b"old b\n")
        self.client.uploads.clear()
        before = len(self.client.commands)
        log = self.many([self.item("new folder/a.py", b"a" * 5000), self.item("b.sh", b"new b\n", "755"),
                         self.item("it's.js", b"")])
        self.assertEqual(log, ["sending", "a.py", "b.sh", "it's.js"])
        self.assertEqual(self.content("new folder/a.py"), b"a" * 5000)
        self.assertEqual(self.content("b.sh"), b"new b\n")
        self.assertEqual(self.content("it's.js"), b"")
        self.assertEqual((self.root / "b.sh").stat().st_mode & 0o777, 0o755)
        self.assertEqual(self.leftovers(), [])
        self.assertEqual(len(self.client.uploads), 1)
        self.assertLessEqual(len(self.client.commands) - before, 3)  # not one command per file

    def test_a_second_batch_works_after_the_first(self):
        self.many([self.item("a", b"1")])
        self.many([self.item("b", b"2"), self.item("a", b"3")])
        self.assertEqual((self.content("a"), self.content("b")), (b"3", b"2"))

    def test_what_was_written_does_not_need_hashing_again(self):
        self.p.hash_cache = install.HashCache()
        one, two = self.item("one.cfg", b"1\n"), self.item("two words.cfg", b"22\n")
        self.p.install(one[1], one[0], *one[2:])
        self.many([two])
        keys = self.p.file_keys([one[0], two[0]])
        self.assertEqual(self.p.hash_cache.get(one[0], keys[one[0]]), sha(one[1]))
        self.assertEqual(self.p.hash_cache.get(two[0], keys[two[0]]), sha(two[1]))

    def test_many_files_stop_at_the_one_that_fails(self):
        for name in ("a", "b", "c"):
            self.put(name + ".cfg", b"old " + name.encode())
        self.break_tool("mv", "b.cfg")
        log = []
        with self.assertRaises(install.InstallError) as caught:
            self.p.install_many([self.item(n + ".cfg", b"new " + n.encode()) for n in "abc"],
                                lambda: log.append("sending"), lambda path: log.append(Path(path).name))
        self.assertIn("b.cfg", str(caught.exception))
        self.assertEqual(log, ["sending", "a.cfg"])
        self.assertEqual([self.content(n + ".cfg") for n in "abc"], [b"new a", b"old b", b"old c"])

    def test_a_failure_in_any_step_stops_the_rest(self):
        # found by the dry run of the printer trial: "set -e" does not act on a step in the middle of an && chain
        for tool in ("mkdir", "install", "sync", "mv"):
            with self.subTest(tool=tool):
                for name in ("a", "b", "c"):
                    self.put(name + ".cfg", b"old " + name.encode())
                # mkdir is given the folder, the other tools the file
                self.break_tool(tool, "folder-b" if tool == "mkdir" else "b.cfg", 'echo "%s broke" >&2; exit 1' % tool)
                items = [self.item("a.cfg", b"new a"), self.item("folder-b/b.cfg" if tool == "mkdir" else "b.cfg", b"new b"),
                         self.item("c.cfg", b"new c")]
                log = []
                with self.assertRaises(install.InstallError) as caught:
                    self.p.install_many(items, lambda: None, lambda path: log.append(Path(path).name))
                time.sleep(0.3)  # a shell that went on would have written c by now
                (self.bin / tool).unlink()
                self.assertIn("%s broke" % tool, str(caught.exception))
                self.assertIn("after 1 of 3", str(caught.exception))
                self.assertEqual(log, ["a.cfg"])
                self.assertEqual((self.content("b.cfg"), self.content("c.cfg")), (b"old b", b"old c"))

    def test_the_message_of_the_failing_command_is_shown(self):
        self.break_tool("mv", "a.cfg", 'echo "no space left on device" >&2; exit 1')
        with self.assertRaises(install.InstallError) as caught:
            self.many([self.item("a.cfg", b"1")])
        self.assertIn("no space left on device", str(caught.exception))

    def test_a_lot_of_error_text_cannot_stall_the_install(self):
        # more than a pipe holds, written while the PC is still waiting for the next answer line
        self.break_tool("sync", "a.cfg", 'head -c 300000 /dev/zero | tr "\0" x >&2')
        failures = []

        def run():
            try:
                self.many([self.item("a.cfg", b"1")])
            except Exception as exc:
                failures.append(exc)

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        worker.join(20)
        if worker.is_alive():
            for process in self.client.processes:
                process.kill()
            worker.join(5)
            self.fail("the install waits for ever")
        self.assertEqual(failures, [])
        self.assertEqual(self.content("a.cfg"), b"1")

    def test_a_file_that_arrives_different_is_an_error(self):
        self.break_tool("install", "a.cfg", 'for a; do t=$a; done; echo wrong > "$t"; exit 0')
        with self.assertRaises(install.InstallError) as caught:
            self.many([self.item("a.cfg", b"right\n")])
        self.assertIn("verification failed", str(caught.exception))

    def test_nothing_is_reported_as_sending_when_the_upload_fails(self):
        self.break_tool("tar", "batch")
        log = []
        with self.assertRaises(install.InstallError):
            self.p.install_many([self.item("a", b"1")], lambda: log.append("sending"), log.append)
        self.assertEqual(log, [])


class RealCommandsWithPasswordTest(RealCommandsTest):
    password = "secret"  # sudo asks: the password goes on standard input


# ------------------------------------------------------------------ the install steps (any computer)
class Batched(FakePrinter):
    """A pretend printer that takes many files at once. cut_after: it writes that many files, then the connection is
    lost; reported: how many of them the PC still hears about."""
    cut_after = None
    reported = None

    def __init__(self, files):
        super().__init__(files)
        self.batches = []

    def install_many(self, items, sending, written):
        self.batches.append([item[0] for item in items])
        sending()
        for n, (path, data, owner, group, mode) in enumerate(items):
            if self.cut_after is not None and n >= self.cut_after:
                raise install.InstallError("connection lost")
            self.install(data, path, owner, group, mode)
            if self.reported is None or n < self.reported:
                written(path)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.saved = (firmware.load_index, firmware.extract, firmware.extract_many)
        firmware.load_index = lambda: {"files": {p: {"sha256": sha(d)} for p, d in STOCK.items()}}
        firmware.extract = lambda p: STOCK[p]
        firmware.extract_many = lambda paths: {p: STOCK[p] for p in paths}
        self.built = build.build(MODS, stock_reader=lambda p: STOCK[p])
        self.p = Batched(STOCK)
        self.out = io.StringIO()

    def tearDown(self):
        firmware.load_index, firmware.extract, firmware.extract_many = self.saved
        shutil.rmtree(self.tmp)

    def install_all(self):
        changes = install.plan(self.p, MODS, built=self.built)
        with contextlib.redirect_stdout(self.out):
            return install.do_install(self.p, MODS, changes, "h", backups=self.tmp)

    def uninstall(self):
        with contextlib.redirect_stdout(self.out):
            install.do_uninstall(self.p, install.host_backups("h", self.tmp))

    def originals_are_back(self):
        for path, data in STOCK.items():
            self.assertEqual(self.p.read(path), data, path)


class BatchTest(Base):
    def test_the_files_go_in_batches_and_every_one_is_recorded(self):
        with mock.patch.object(install, "BATCH_FILES", 1):
            backup = self.install_all()
        self.assertEqual(sorted(len(b) for b in self.p.batches), [1, 1])
        record = install.json.loads((backup / "install.json").read_text(encoding="utf-8"))
        self.assertTrue(record["complete"])
        for entry in record["files"].values():
            self.assertTrue(entry["installed"])
            self.assertNotIn("pending", entry)
        self.uninstall()
        self.originals_are_back()

    def test_a_batch_is_limited_in_bytes_and_a_big_file_goes_alone(self):
        items = [("/a", b"x" * 3), ("/b", b"x" * 3), ("/big", b"x" * 20), ("/c", b"x")]
        with mock.patch.object(install, "BATCH_BYTES", 8):
            got = [[i[0] for i in b] for b in install.batches(items)]
        self.assertEqual(got, [["/a", "/b"], ["/big"], ["/c"]])

    def test_files_written_but_not_reported_are_found_by_the_next_run(self):
        self.p.reported = 0
        self.p.cut_after = 2  # both files are on the printer, the PC heard about neither
        self.p.install_many = self.lost_after_writing
        with self.assertRaises(install.InstallError):
            self.install_all()
        self.assertEqual(install.unfinished_modules("h", self.tmp, self.p), {"fan", "idle"})
        del self.p.install_many
        time.sleep(1.1)
        self.install_all()
        self.assertEqual(self.p.restarts, ["klipper"])
        self.uninstall()
        self.originals_are_back()

    def lost_after_writing(self, items, sending, written):
        sending()
        for path, data, owner, group, mode in items:
            self.p.install(data, path, owner, group, mode)
        raise install.InstallError("connection lost")

    def test_uninstall_right_after_a_lost_connection_restores_the_files(self):
        self.p.install_many = self.lost_after_writing
        with self.assertRaises(install.InstallError):
            self.install_all()
        self.uninstall()
        self.originals_are_back()

    def test_a_file_that_was_never_written_is_not_counted(self):
        self.p.cut_after = 1
        with self.assertRaises(install.InstallError):
            self.install_all()
        first = self.p.batches[0][0]
        owners = {FAN: {"fan"}, CFG: {"idle"}}
        self.assertEqual(install.unfinished_modules("h", self.tmp, self.p), owners[first])
        record = install.json.loads((install.host_backups("h", self.tmp)[-1] / "install.json").read_text(encoding="utf-8"))
        self.assertEqual({p for p, e in record["files"].items() if e.get("installed")}, {first})
        self.assertFalse([e for e in record["files"].values() if "pending" in e])
        self.uninstall()
        self.originals_are_back()
        self.assertNotIn("left alone", self.out.getvalue())

    def test_a_config_saved_by_the_printer_since_the_cut_still_counts(self):
        self.p.files[CFG][0] = STOCK[CFG] + b"#*# mine = 1\r\n"
        self.p.install_many = self.lost_after_writing
        with self.assertRaises(install.InstallError):
            self.install_all()
        self.p.files[CFG][0] += b"#*# saved later = 2\r\n"
        self.uninstall()
        self.assertEqual(self.p.read(CFG), STOCK[CFG] + b"#*# mine = 1\r\n#*# saved later = 2\r\n")


class OddRecordTest(unittest.TestCase):
    """confirm_pending with a record that lacks fields (another version of the installer, an edited file)."""

    def confirm(self, entry, files):
        with tempfile.TemporaryDirectory() as tmp:
            backup = Path(tmp)
            (backup / "install.json").write_text(install.json.dumps({"files": {FAN: entry}}), encoding="utf-8")
            install.confirm_pending(FakePrinter(files), [backup])
            return install.json.loads((backup / "install.json").read_text(encoding="utf-8"))["files"][FAN]

    def test_without_the_new_checksum_the_file_is_not_counted(self):
        self.assertEqual(self.confirm({"pending": True}, {FAN: b"x"}), {})

    def test_a_config_without_the_old_checksum_is_not_guessed(self):
        got = self.confirm({"pending": True, "kind": "config", "new_sha256": sha(b"ours")}, {FAN: b"theirs"})
        self.assertNotIn("installed", got)
        self.assertNotIn("pending", got)

    def test_a_missing_file_is_not_counted(self):
        got = self.confirm({"pending": True, "kind": "config", "new_sha256": sha(b"ours"), "old_sha256": sha(b"old")}, {})
        self.assertNotIn("installed", got)


# ------------------------------------------------------------------ the connection
class CompressionTest(unittest.TestCase):
    def connect(self, call):
        client = mock.Mock()
        with mock.patch.object(printer, "_client", lambda: client), \
                mock.patch.dict(sys.modules, {"paramiko": mock.Mock(AuthenticationException=KeyError,
                                                                    SSHException=ValueError)}):
            call()
        return client.connect.call_args.kwargs

    def test_the_key_login_is_compressed(self):
        self.assertTrue(self.connect(lambda: printer.connect_with_key("h", "mks"))["compress"])

    def test_the_password_login_is_compressed(self):
        self.assertTrue(self.connect(lambda: printer.connect("h", "mks", password="x"))["compress"])


if __name__ == "__main__":
    unittest.main()
