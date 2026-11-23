#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""algo-app-recycle: restarts the AI service after a print has been over for a while (only when it is big and idle).
algo-app-oom-priority / algo-app-malloc: the systemd drop-in files.

The script is for the printer: tests run in WSL/Linux with fake curl, systemctl, sleep and logger in front of PATH.
Run in WSL/Linux:  python3 tests/test_algo_recycle.py
"""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOD = ROOT / "modules" / "algo-app-recycle"
SCRIPT = MOD / "files" / "q2_algo_recycle.sh"

CURL = r"""#!/bin/sh
# fake curl: prints the next scripted print_stats state (the last one repeats); an empty line = Moonraker silent
f="$STUB/states"
line=$(head -n 1 "$f")
if [ "$(wc -l < "$f")" -gt 1 ]; then tail -n +2 "$f" > "$f.n" && mv "$f.n" "$f"; fi
echo "$line" >> "$STUB/curl_calls"
[ -z "$line" ] && exit 7
printf '{"result": {"status": {"print_stats": {"filename": "x.gcode", "state": "%s", "message": ""}}}}\n' "$line"
"""
SYSTEMCTL = r"""#!/bin/sh
case "$1" in
  is-active) cat "$STUB/active"; [ "$(cat "$STUB/active")" = active ] ;;
  show) echo 4242 ;;
  restart) echo "restart $2" >> "$STUB/restarts" ;;
  start) echo "start $2" >> "$STUB/restarts" ;;
  *) echo "unexpected: $*" >> "$STUB/unexpected" ;;
esac
"""
SLEEP = "#!/bin/sh\nexit 0\n"
LOGGER = "#!/bin/sh\necho \"$*\" >> \"$STUB/log\"\n"


@unittest.skipIf(sys.platform == "win32", "script for the printer; run in WSL/Linux")
class RecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stub = Path(self.tmp.name) / "stub"
        self.bin = Path(self.tmp.name) / "bin"
        self.proc = Path(self.tmp.name) / "proc"
        for d in (self.stub, self.bin, self.proc / "4242"):
            d.mkdir(parents=True)
        for name, body in (("curl", CURL), ("systemctl", SYSTEMCTL), ("sleep", SLEEP), ("logger", LOGGER)):
            p = self.bin / name
            p.write_text(body)
            p.chmod(p.stat().st_mode | stat.S_IXUSR)
        (self.stub / "active").write_text("active")
        self.set_rss(180000)

    def tearDown(self):
        self.tmp.cleanup()

    def set_rss(self, kb):
        (self.proc / "4242" / "status").write_text("Name:\tmain\nVmRSS:\t%d kB\nThreads:\t12\n" % kb)

    def run_script(self, states, delay=30, interval=10, extra=None):
        (self.stub / "states").write_text("\n".join(states) + "\n")
        env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ["PATH"], STUB=str(self.stub),
                   Q2_RECYCLE_INTERVAL=str(interval), Q2_RECYCLE_DELAY=str(delay), Q2_RECYCLE_PROC=str(self.proc),
                   Q2_RECYCLE_MAX_LOOPS=str(len(states) + 5))
        env.update(extra or {})
        r = subprocess.run(["sh", str(SCRIPT)], capture_output=True, text=True, timeout=60, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def restarts(self):
        f = self.stub / "restarts"
        return f.read_text().splitlines() if f.exists() else []

    def log(self):
        f = self.stub / "log"
        return f.read_text() if f.exists() else ""

    # --- the normal case ---
    def test_restart_once_when_the_print_has_been_over_long_enough(self):
        self.run_script(["printing"] * 3 + ["complete"] * 8)
        self.assertEqual(self.restarts(), ["restart algo_app"])
        self.assertFalse((self.stub / "unexpected").exists())

    def test_cancelled_and_standby_count_as_a_finished_print_too(self):
        for end in ("cancelled", "standby", "error"):
            with self.subTest(end):
                (self.stub / "restarts").unlink(missing_ok=True)
                self.run_script(["printing"] * 2 + [end] * 8)
                self.assertEqual(self.restarts(), ["restart algo_app"])

    def test_a_paused_print_counts_as_a_print(self):
        self.run_script(["paused"] * 2 + ["complete"] * 8)
        self.assertEqual(self.restarts(), ["restart algo_app"])

    def test_one_restart_per_print_not_one_per_check(self):
        self.run_script(["printing"] + ["complete"] * 40)
        self.assertEqual(self.restarts(), ["restart algo_app"])

    def test_two_prints_two_restarts(self):
        self.run_script(["printing"] * 2 + ["complete"] * 6 + ["printing"] * 2 + ["cancelled"] * 6)
        self.assertEqual(self.restarts(), ["restart algo_app", "restart algo_app"])

    # --- when nothing may happen ---
    def test_a_new_print_before_the_delay_cancels_the_restart(self):
        self.run_script(["printing", "complete", "complete", "printing", "printing", "printing"])
        self.assertEqual(self.restarts(), [])

    def test_a_print_that_starts_right_before_the_restart_is_not_interrupted(self):
        # delay 30 s at 10 s steps: the 3rd 'complete' reaches it; the re-check right before the restart sees 'printing'
        self.run_script(["printing", "complete", "complete", "complete", "printing", "printing", "printing"])
        self.assertEqual(self.restarts(), [])

    def test_no_print_seen_means_no_restart(self):
        self.run_script(["standby"] * 10)
        self.assertEqual(self.restarts(), [])

    def test_a_small_service_is_left_alone(self):
        self.set_rss(90000)
        self.run_script(["printing"] + ["complete"] * 8)
        self.assertEqual(self.restarts(), [])
        self.assertIn("skip", self.log().lower())

    def test_a_stopped_service_is_never_started(self):
        (self.stub / "active").write_text("inactive")
        self.run_script(["printing"] + ["complete"] * 8)
        self.assertEqual(self.restarts(), [])          # neither restart nor start: the owner stopped it on purpose

    def test_moonraker_silent_changes_nothing_and_does_not_crash(self):
        self.run_script(["printing", "", "", "", "", "", "", ""])
        self.assertEqual(self.restarts(), [])

    def test_silence_between_print_and_end_does_not_lose_the_print(self):
        self.run_script(["printing", "", "complete", "complete", "complete", "complete", "complete"])
        self.assertEqual(self.restarts(), ["restart algo_app"])

    def test_unknown_state_is_ignored(self):
        self.run_script(["printing", "weird", "weird", "weird", "weird", "weird"])
        self.assertEqual(self.restarts(), [])


class ModuleFileTests(unittest.TestCase):
    def load(self, mid):
        return json.loads((ROOT / "modules" / mid / "module.json").read_text(encoding="utf-8"))

    def test_recycle_module_is_optional_and_installs_script_and_unit(self):
        m = self.load("algo-app-recycle")
        self.assertEqual(m["id"], "algo-app-recycle")
        self.assertIs(m["default"], False)
        self.assertIn("/usr/local/lib/q2-algo-recycle/q2_algo_recycle.sh", m["files"])
        self.assertIn("/etc/systemd/system/q2-algo-recycle.service", m["files"])
        self.assertIn(["systemctl", "enable", "--now", "q2-algo-recycle.service"], m["actions"])
        unit = (MOD / "files" / "q2-algo-recycle.service").read_text()
        self.assertIn("ExecStart=/bin/sh /usr/local/lib/q2-algo-recycle/q2_algo_recycle.sh", unit)
        self.assertIn("Restart=on-failure", unit)

    def test_script_never_starts_a_service(self):
        text = SCRIPT.read_text()
        self.assertNotIn("systemctl start", text)

    def test_oom_priority_protects_klipper_and_moonraker_and_sacrifices_algo_app(self):
        m = self.load("algo-app-oom-priority")
        self.assertNotIn("default", m)            # on by default: same class as klipper-priority
        by_service = {}
        for path, spec in m["files"].items():
            text = (ROOT / "modules" / "algo-app-oom-priority" / spec["source"]).read_text()
            by_service[path.split("/")[-2].split(".")[0]] = text
        self.assertIn("OOMScoreAdjust=500", by_service["algo_app"])
        self.assertIn("OOMScoreAdjust=-300", by_service["klipper"])
        self.assertIn("OOMScoreAdjust=-300", by_service["moonraker"])
        self.assertIn(["systemctl", "daemon-reload"], m["actions"])

    def test_malloc_module_is_optional_and_only_sets_environment_for_algo_app(self):
        m = self.load("algo-app-malloc")
        self.assertIs(m["default"], False)
        self.assertEqual(list(m["files"]), ["/etc/systemd/system/algo_app.service.d/q2-algo-malloc.conf"])
        text = (ROOT / "modules" / "algo-app-malloc" / "files" / "q2-algo-malloc.conf").read_text()
        self.assertIn("Environment=MALLOC_ARENA_MAX=2", text)
        self.assertNotIn("ExecStart", text)


if __name__ == "__main__":
    unittest.main()
