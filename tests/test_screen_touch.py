#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic)
"""printer-screen-touch: coordinates, the touch events, what the service accepts and refuses (arming), the module file."""
import copy
import io
import json
import shutil
import struct
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOD = ROOT / "modules" / "printer-screen-touch"
VIEW = ROOT / "modules" / "printer-screen-view"
sys.path.insert(0, str(MOD / "files"))
sys.path.insert(0, str(ROOT / "tools"))
import q2_touch  # noqa: E402
import install  # noqa: E402
import build  # noqa: E402
import firmware  # noqa: E402
from test_install import FakePrinter  # noqa: E402

EV = struct.Struct("llHHi")
RELEASE = [(3, 0x2f, 0), (3, 0x39, -1), (1, 0x14a, 0), (0, 0, 0)]


def decode(data):
    return [EV.unpack_from(data, i)[2:] for i in range(0, len(data), EV.size)]


class CoordinateTests(unittest.TestCase):
    def test_picture_position_to_touch_point(self):
        # 06.11.2026 test (owner watched): touch point 160,200 pressed "Cancel", which sits at pixel 160,200 of the
        # 480x272 screen picture -> the touch panel's numbers are screen pixels (1:1), although it reports 0-799 x 0-479
        self.assertEqual(q2_touch.to_touch(160 / 480, 200 / 272), (160, 200))

    def test_corners_stay_inside(self):
        self.assertEqual(q2_touch.to_touch(0, 0), (0, 0))
        self.assertEqual(q2_touch.to_touch(1, 1), (479, 271))

    def test_scale_can_be_changed(self):          # if a later test shows another factor, only these numbers change
        old = q2_touch.SCALE_X, q2_touch.SCALE_Y
        q2_touch.SCALE_X, q2_touch.SCALE_Y = 800 / 480, 480 / 272
        try:
            self.assertEqual(q2_touch.to_touch(1, 1), (798, 478))      # last pixel, inside the panel range
            self.assertEqual(q2_touch.to_touch(0.5, 0.5), (400, 240))
        finally:
            q2_touch.SCALE_X, q2_touch.SCALE_Y = old

    def test_bad_numbers_refused(self):
        for bad in (-0.1, 1.1, float("nan"), float("inf"), "0.5", None, True):
            with self.assertRaises(ValueError):
                q2_touch.to_touch(bad, 0.5)


class EventTests(unittest.TestCase):
    def test_tap_events_like_the_proven_script(self):
        out, waits = io.BytesIO(), []
        q2_touch.write_tap(out, 160, 200, sleep=waits.append)
        evs = decode(out.getvalue())
        EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
        self.assertEqual(evs[:8], [(EV_ABS, 0x2f, 0), (EV_ABS, 0x39, 4242), (EV_ABS, 0x35, 160), (EV_ABS, 0x36, 200),
                                   (EV_ABS, 0x30, 10), (EV_KEY, 0x14a, 1), (EV_ABS, 0, 160), (EV_ABS, 1, 200)])
        self.assertEqual(evs[8], (EV_SYN, 0, 0))
        self.assertEqual(evs[9:], [(EV_ABS, 0x2f, 0), (EV_ABS, 0x39, -1), (EV_KEY, 0x14a, 0), (EV_SYN, 0, 0)])
        self.assertEqual(waits, [q2_touch.PRESS_SECONDS])

    def test_release_is_sent_when_the_wait_is_interrupted(self):
        # the process is stopped (SIGTERM -> SystemExit) or the wait fails: the panel must not stay "pressed"
        for exc in (SystemExit, KeyboardInterrupt, RuntimeError):
            out = io.BytesIO()

            def boom(_s, exc=exc):
                raise exc()
            with self.assertRaises(exc):
                q2_touch.write_tap(out, 10, 20, sleep=boom)
            self.assertEqual(decode(out.getvalue())[-4:], RELEASE, exc)

    def test_release_is_tried_when_a_press_write_fails(self):
        class Flaky:
            def __init__(self):
                self.n, self.data = 0, io.BytesIO()

            def write(self, b):
                self.n += 1
                if self.n == 3:                 # the third press event fails
                    raise OSError("write failed")
                self.data.write(b)
        f = Flaky()
        with self.assertRaises(OSError):
            q2_touch.write_tap(f, 10, 20, sleep=lambda s: None)
        self.assertEqual(decode(f.data.getvalue())[-4:], RELEASE)

    def test_sigterm_handler_exits_so_that_finally_runs(self):
        with self.assertRaises(SystemExit):
            q2_touch.on_term(15, None)


class DeviceTests(unittest.TestCase):
    def test_finds_the_goodix_panel_only(self):
        with tempfile.TemporaryDirectory() as d:
            for n, name in (("event0", "icspring camera"), ("event1", "Goodix Capacitive TouchScreen")):
                (Path(d) / n / "device").mkdir(parents=True)
                (Path(d) / n / "device" / "name").write_text(name + "\n")
            self.assertEqual(q2_touch.find_device(d, "/dev/input").replace("\\", "/"), "/dev/input/event1")
            (Path(d) / "event1" / "device" / "name").write_text("something else\n")
            self.assertIsNone(q2_touch.find_device(d, "/dev/input"))


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.taps, self.clock = [], [100.0]
        self.orig = (q2_touch.inject, q2_touch.now)
        q2_touch.inject = lambda x, y: self.taps.append((x, y))
        q2_touch.now = lambda: self.clock[0]
        q2_touch.last_tap[0] = 0.0
        q2_touch.armed_until[0] = 0.0
        self.server = HTTPServer(("127.0.0.1", 0), q2_touch.Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d/?action=tap" % self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        q2_touch.inject, q2_touch.now = self.orig

    def post(self, body, headers=None, url=None, header=True):
        h = {"Content-Type": "application/json"}
        if header:
            h["X-Q2-Touch"] = "1"
        h.update(headers or {})
        req = urllib.request.Request(url or self.url, data=body if isinstance(body, bytes) else json.dumps(body).encode(),
                                     headers=h, method="POST")
        try:
            with urllib.request.urlopen(req) as r:
                return r.status
        except urllib.error.HTTPError as e:
            e.close()
            return e.code

    def arm(self, headers=None):
        return self.post({}, headers, url=self.url.replace("tap", "arm"))

    def disarm(self):
        return self.post({}, url=self.url.replace("tap", "disarm"))

    def tap(self, headers=None, **kw):
        return self.post({"x": 0.5, "y": 0.5}, headers, **kw)

    def test_tap_is_injected(self):
        self.assertEqual(self.arm(), 200)
        self.assertEqual(self.post({"x": 160 / 480, "y": 200 / 272}), 200)
        self.assertEqual(self.taps, [(160, 200)])

    def test_refusals(self):
        self.arm()
        self.assertEqual(self.post({"x": 2, "y": 0.5}), 400)
        self.assertEqual(self.post(b"not json"), 400)
        self.assertEqual(self.post({"x": 0.5}), 400)
        self.assertEqual(self.tap({"Content-Type": "text/plain"}), 415)   # a web page cannot send this quietly
        self.assertEqual(self.tap({"Sec-Fetch-Site": "cross-site"}), 403)  # another site
        self.assertEqual(self.tap(url=self.url.replace("tap", "other")), 404)
        self.assertEqual(self.post(b"{" + b" " * 1000 + b"}"), 413)
        self.assertEqual(self.taps, [])

    def test_same_origin_is_fine(self):
        # behind Fluidd's web server Host is not the browser's address (22.11.2026: a Host check refused every real tap)
        self.arm()
        self.assertEqual(self.tap({"Origin": "http://100.73.132.37", "Host": "mjpgstreamer3",
                                   "Sec-Fetch-Site": "same-origin"}), 200)

    def test_get_is_not_a_tap(self):
        with self.assertRaises(urllib.error.HTTPError) as c:
            urllib.request.urlopen(self.url)
        c.exception.close()
        self.assertEqual((c.exception.code, self.taps), (405, []))

    def test_taps_are_rate_limited(self):
        self.arm()
        self.assertEqual(self.tap(), 200)
        self.assertEqual(self.tap(), 429)
        self.clock[0] += 1
        self.assertEqual(self.tap(), 200)
        self.assertEqual(len(self.taps), 2)

    def test_no_panel_found(self):
        def none(x, y):
            raise OSError("no touch panel")
        q2_touch.inject = none
        self.arm()
        self.assertEqual(self.tap(), 503)

    # --- touch is OFF in the service itself (22.11.2026 audit: it was only a variable in the page) ---
    def test_off_after_start(self):
        self.assertEqual(q2_touch.armed_until[0], 0.0)
        self.assertEqual(self.tap(), 403)
        self.assertEqual(self.taps, [])

    def test_plain_curl_without_site_header_cannot_tap(self):
        # curl sends no Sec-Fetch-Site and no X-Q2-Touch: the old check let it through
        req = urllib.request.Request(self.url, data=b'{"x":.5,"y":.5}', method="POST",
                                     headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as c:
            urllib.request.urlopen(req)
        c.exception.close()
        self.assertEqual((c.exception.code, self.taps), (403, []))
        self.assertEqual(self.arm({"X-Q2-Touch": ""}), 403)       # an empty header does not count
        self.assertEqual(self.post({}, url=self.url.replace("tap", "arm"), header=False), 403)
        self.assertEqual(self.tap(), 403)                          # and none of that armed anything
        self.assertEqual(self.taps, [])

    def test_header_is_required_even_when_armed(self):
        self.arm()
        self.assertEqual(self.tap(header=False), 403)
        self.assertEqual(self.tap({"X-Q2-Touch": "0"}), 403)
        self.assertEqual(self.taps, [])

    def test_arm_from_another_site_refused(self):
        self.assertEqual(self.arm({"Sec-Fetch-Site": "cross-site"}), 403)
        self.assertEqual(self.tap(), 403)

    def test_arm_expires(self):
        self.assertEqual(self.arm(), 200)
        self.assertEqual(self.tap(), 200)
        self.clock[0] += q2_touch.ARM_SECONDS - 1
        self.assertEqual(self.tap(), 200)
        self.clock[0] += 2                                          # past the end; the rate limit is long over
        self.assertEqual(self.tap(), 403)
        self.assertEqual(len(self.taps), 2)

    def test_arm_can_be_renewed_and_taps_do_not_renew_it(self):
        self.arm()
        self.clock[0] += q2_touch.ARM_SECONDS - 5
        self.assertEqual(self.tap(), 200)                           # a tap alone does not extend it
        self.clock[0] += 10
        self.assertEqual(self.tap(), 403)
        self.arm()
        self.assertEqual(self.tap(), 200)

    def test_disarm(self):
        self.arm()
        self.assertEqual(self.disarm(), 200)
        self.assertEqual(self.tap(), 403)
        self.assertEqual(self.taps, [])

    def test_arm_and_disarm_follow_the_same_rules(self):
        self.assertEqual(self.arm({"Content-Type": "text/plain"}), 415)
        self.assertEqual(self.post({}, url=self.url.replace("tap", "bogus")), 404)
        self.assertEqual(self.tap(), 403)

    def test_no_cors_preflight_answer(self):
        # a page of another site needs a preflight for the custom header; the service must never grant one
        req = urllib.request.Request(self.url.replace("tap", "arm"), method="OPTIONS",
                                     headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST",
                                              "Access-Control-Request-Headers": "x-q2-touch,content-type"})
        try:
            with urllib.request.urlopen(req) as r:
                code, hdrs = r.status, r.headers
        except urllib.error.HTTPError as e:
            code, hdrs = e.code, e.headers
            e.close()
        self.assertGreaterEqual(code, 400)
        self.assertIsNone(hdrs.get("Access-Control-Allow-Origin"))
        self.assertIsNone(hdrs.get("Access-Control-Allow-Headers"))


def read(path):
    return path.read_text(encoding="utf-8")


class ModuleTests(unittest.TestCase):
    def test_module_is_optional_and_local(self):
        m = json.loads(read(MOD / "module.json"))
        self.assertEqual(m["id"], "printer-screen-touch")
        self.assertIs(m["default"], False)
        for dest, f in m["files"].items():
            if "source" in f:
                self.assertTrue((MOD / f["source"]).is_file(), dest)
        self.assertIn('("127.0.0.1", PORT)', read(MOD / "files" / "q2_touch.py"))

    def test_view_module_stays_look_only(self):
        self.assertNotIn("/dev/input", read(VIEW / "files" / "q2_screen.py"))

    def test_scripts_are_not_writable_by_the_printer_user(self):
        # 22.11.2026 audit: root scripts in /home/qidi could be rewritten by Klipper/Moonraker (user qidi)
        for folder, name, unit in ((MOD, "q2_touch.py", "q2-screen-touch.service"), (VIEW, "q2_screen.py", "q2-screen.service")):
            m = json.loads(read(folder / "module.json"))
            dest = "/usr/local/lib/q2-screen/" + name
            self.assertIn(dest, m["files"])
            self.assertIn("/usr/bin/python3 " + dest, read(folder / "files" / unit))
            self.assertNotIn("/home/qidi/q2-screen", json.dumps(m["files"]))
            self.assertNotIn("/home/qidi/q2-screen", read(folder / "files" / unit))
            self.assertEqual(install.default_owner(dest)[:2], ("root", "root"))

    def test_old_script_folder_is_cleaned_on_update(self):
        # each module removes only its own old file (a skipped sibling module keeps working), then the folder if empty
        for folder, name in ((MOD, "q2_touch.py"), (VIEW, "q2_screen.py")):
            acts = json.loads(read(folder / "module.json"))["actions"]
            # "find ... -empty -delete" removes the old folder only when it is empty and exits 0 when it is already gone
            # (rmdir failed with exit 1 on the second run and stopped the installer: 22.11.2026)
            rm = ["rm", "-f", "/home/qidi/q2-screen/" + name]
            rmdir = ["find", "/home/qidi", "-maxdepth", "1", "-name", "q2-screen", "-type", "d", "-empty", "-delete"]
            self.assertIn(rm, acts, folder.name)
            self.assertIn(rmdir, acts, folder.name)
            restart = max(i for i, a in enumerate(acts) if a[:2] == ["systemctl", "restart"])
            self.assertGreater(acts.index(rm), restart)          # the new service already runs from the new place
            self.assertGreater(acts.index(rmdir), acts.index(rm))
            for a in (rm, rmdir):
                self.assertFalse(install.is_state_action(a))
                self.assertIsNone(install.undo_action(a))

    def test_window_starts_with_touch_off(self):
        js = read(MOD / "files" / "q2-screen-touch.js")
        self.assertIn("var enabled = false", js)              # every time the window opens, touch is off
        self.assertIn("/webcam3/?action=tap", js)
        self.assertIn("q2-screen-open", read(VIEW / "files" / "q2-screen-view.js"))

    def test_window_arms_the_service_and_keeps_it_armed(self):
        js = read(MOD / "files" / "q2-screen-touch.js")
        for part in ("action=arm", "action=disarm", "X-Q2-Touch", "setInterval", "q2-screen-close", "pagehide",
                     "naturalWidth", "naturalHeight", "480", "272", "1500", "keepalive"):
            self.assertIn(part, js)
        self.assertLess(js.index("action=arm"), js.index("action=tap"))

    def test_window_refuses_a_click_on_a_stale_picture(self):
        js = read(MOD / "files" / "q2-screen-touch.js")
        self.assertIn("img.complete", js)
        self.assertIn("q2Ts", js)
        self.assertIn("document.hidden", js)

    def test_view_window_refuses_stale_and_hidden(self):
        js = read(VIEW / "files" / "q2-screen-view.js")
        for part in ("document.hidden", "visibilitychange", "q2-screen-close", "naturalWidth", "q2Ts"):
            self.assertIn(part, js)

    def test_script_versions_are_bumped(self):
        # The version number must be higher than the one a browser may have cached (1 before the audit fixes,
        # 2 after them; the touch script went to 3 with the shorter texts).
        for folder, js, version in ((MOD, "q2-screen-touch.js", 3), (VIEW, "q2-screen-view.js", 2)):
            text = read(folder / "module.json")
            self.assertNotIn(js + "?v=1\\", text)
            self.assertIn(js + "?v=%d\\" % version, text)


class RootPrinter(FakePrinter):
    """FakePrinter that also understands the two clean-up commands of the modules."""

    def action(self, argv, check=True):
        super().action(argv, check)
        if argv[:2] == ["rm", "-f"]:
            self.files.pop(argv[2], None)
        if argv[0] == "find" and "-delete" in argv:
            self.dirs_removed = getattr(self, "dirs_removed", []) + ["/home/qidi/q2-screen"]


class InstallAndUninstallTests(unittest.TestCase):
    """Both modules through the real installer code: new place, old place cleaned, uninstall leaves nothing."""
    OLD = ("/home/qidi/q2-screen/q2_touch.py", "/home/qidi/q2-screen/q2_screen.py")
    NEW = ("/usr/local/lib/q2-screen/q2_touch.py", "/usr/local/lib/q2-screen/q2_screen.py")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        saved = firmware.load_index
        firmware.load_index = lambda: {"files": {}}
        self.addCleanup(setattr, firmware, "load_index", saved)
        mods = [copy.deepcopy(m) for m in build.load_modules() if m["id"] in ("printer-screen-view", "printer-screen-touch")]
        for m in mods:                                   # the index.html edit needs QIDI's file; not what is tested here
            m["files"] = {k: v for k, v in m["files"].items() if "edits" not in v}
        self.mods = sorted(mods, key=lambda m: m["order"])
        self.built = build.build(self.mods, stock_reader=lambda p: b"")

    def printer(self, old):
        p = RootPrinter({path: b"old version" for path in old})
        p.files["/root/uuid"] = [b"abc\n", "root", "root", "644"]
        return p

    def test_update_of_an_existing_install_moves_the_scripts_and_cleans_the_old_place(self):
        p = self.printer(self.OLD)
        changes = install.plan(p, self.mods, built=self.built)
        install.do_install(p, self.mods, changes, "h", backups=self.tmp)
        for path in self.NEW:
            self.assertEqual(p.files[path][1:3], ["root", "root"], path)       # root's scripts belong to root
            self.assertEqual(p.files[path][3], "644")
        for path in self.OLD:
            self.assertNotIn(path, p.files)
        self.assertEqual(p.dirs_removed, ["/home/qidi/q2-screen"] * 2)
        # run again: nothing new to put on the printer
        self.assertEqual(install.plan(p, self.mods, built=self.built), [])

    def test_uninstall_removes_both_modules_completely(self):
        p = self.printer(())
        before = set(p.files)
        changes = install.plan(p, self.mods, built=self.built)
        backup = install.do_install(p, self.mods, changes, "h", backups=self.tmp)
        self.assertTrue(set(self.NEW) <= set(p.files))
        self.assertIn("/etc/systemd/system/q2-screen.service", p.files)
        self.assertIn("/etc/systemd/system/q2-screen-touch.service", p.files)
        install.do_uninstall(p, backup)
        self.assertEqual(set(p.files), before)                                  # nothing of ours is left
        self.assertIn(["systemctl", "disable", "--now", "q2-screen.service"], p.actions)
        self.assertIn(["systemctl", "disable", "--now", "q2-screen-touch.service"], p.actions)


if __name__ == "__main__":
    unittest.main()
