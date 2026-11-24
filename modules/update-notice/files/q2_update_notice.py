#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""update-notice: every 12 hours asks GitHub for the latest release of this project and, when it is newer than the version
installed on the printer, shows ONE message per release (red line in the Fluidd console, the window on the printer screen
and, when phone-notifications is installed, a phone message). It never downloads or installs anything.

What leaves the printer: one HTTPS GET of the public "latest release" address (User-Agent "q2-update-notice"), nothing else.
The message is only built from a tag that is plain digits (x.y.z), so nothing from the internet reaches a G-code line.
Never while a print runs or is paused, and when Moonraker does not answer that counts as "busy".
Off switch: create the file "disabled" in the state folder (Q2_UPDATE_DIR, default /var/lib/q2-update-notice).
Python 3.9, standard library only.
"""
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

RELEASE_URL = "https://api.github.com/repos/muchak1994-lpg/qidi-q2-0204-tweaked/releases/latest"
MOONRAKER = "http://127.0.0.1:7125"
STATE_DIR = "/var/lib/q2-update-notice"
USER_AGENT = "q2-update-notice"
FIRST_DELAY = 300        # seconds after the service starts before the first look
CHECK_EVERY = 12 * 3600  # one request every 12 hours
RETRY_FETCH = 3600       # GitHub did not answer: try again in an hour
BUSY_RETRY = 600         # a print is running (or Moonraker is silent): ask again in 10 minutes
LOOP_SECONDS = 10

_TAG = re.compile(r"^v?(\d{1,4})\.(\d{1,4})\.(\d{1,4})$")


def parse_version(text):
    """'v1.4.0' or '1.4.0' -> (1, 4, 0); anything else (also with extra text, a newline inside, a suffix) -> None."""
    if not isinstance(text, str):
        return None
    m = _TAG.match(text.strip())
    return tuple(int(x) for x in m.groups()) if m else None


def text_of(version):
    return ".".join(str(x) for x in version)


def message(latest, current):
    return ("New TWEAKED version %s (currently %s). Download and install with the help of a computer."
            % (text_of(latest), text_of(current)))


def _get_json(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post_script(moonraker, script):
    body = json.dumps({"script": script}).encode("utf-8")
    req = urllib.request.Request(moonraker + "/printer/gcode/script", data=body,
                                 headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=10) as resp:
        resp.read()


class Notice:
    def __init__(self, release_url=RELEASE_URL, moonraker=MOONRAKER, state_dir=STATE_DIR, clock=time.monotonic):
        self.release_url = release_url
        self.moonraker = moonraker
        self.dir = Path(state_dir)
        self.next_fetch = clock() + FIRST_DELAY
        self.next_busy = 0
        self.pending = None

    # --- small helpers -------------------------------------------------------------------------------------------
    def _read(self, name):
        try:
            return (self.dir / name).read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def installed(self):
        return parse_version(self._read("VERSION"))

    def latest(self):
        """The newest published release as a tuple, or None (drafts, pre-releases and odd tags do not count);
        raises when GitHub cannot be reached."""
        data = _get_json(self.release_url, 10)
        if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
            return None
        return parse_version(data.get("tag_name"))

    def busy(self):
        try:
            q = _get_json(self.moonraker + "/printer/objects/query?print_stats", 5)
            state = q["result"]["status"]["print_stats"]["state"]
        except Exception:
            return True
        return state in ("printing", "paused")

    def has_phone_module(self):
        try:
            names = _get_json(self.moonraker + "/printer/objects/list", 5)["result"]["objects"]
            return "gcode_macro _TWEAKED_NOTIFY" in names
        except Exception:
            return False

    def announce(self, latest, current):
        text = message(latest, current)
        _post_script(self.moonraker, 'RESPOND TYPE=error MSG="%s"' % text)  # raises: nothing is marked as done
        try:
            if self.has_phone_module():
                t = "\t"
                _post_script(self.moonraker, "RUN_SHELL_COMMAND CMD=q2_notify PARAMS=\"--tsv 'New Tweaked version%s%s%s3%s'\""
                             % (t, text, t, t * 6))
        except Exception:
            pass  # the phone message is a bonus; the screen already got the news
        (self.dir / "announced").write_text(text_of(latest) + "\n", encoding="utf-8")

    # --- one decision --------------------------------------------------------------------------------------------
    def step(self, now):
        if (self.dir / "disabled").exists():
            return "off"
        current = self.installed()
        if current is None:
            return "no-version"
        if self.pending is not None and self.pending <= current:
            self.pending = None  # the owner installed it in the meantime
            return "up-to-date"
        if self.pending is None:
            if now < self.next_fetch:
                return "waiting"
            try:
                found = self.latest()
            except Exception:
                self.next_fetch = now + RETRY_FETCH
                return "fetch-failed"
            self.next_fetch = now + CHECK_EVERY
            if found is None or found <= current or text_of(found) == self._read("announced"):
                return "up-to-date"
            self.pending = found
        if now < self.next_busy:
            return "waiting"
        if self.busy():
            self.next_busy = now + BUSY_RETRY
            return "busy"
        try:
            self.announce(self.pending, current)
        except Exception:
            self.next_busy = now + BUSY_RETRY
            return "announce-failed"
        self.pending = None
        return "announced"


def main(environ=None):
    env = os.environ if environ is None else environ
    n = Notice(env.get("Q2_UPDATE_URL", RELEASE_URL), env.get("Q2_UPDATE_MOONRAKER", MOONRAKER),
               env.get("Q2_UPDATE_DIR", STATE_DIR))
    last = None
    while True:
        result = n.step(time.monotonic())
        if result != last and result not in ("waiting", "up-to-date"):
            print("q2-update-notice: %s" % result, flush=True)
        last = result
        time.sleep(LOOP_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
