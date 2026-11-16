# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""Optional Tailscale on the printer: reach Fluidd, OrcaSlicer uploads and the camera from anywhere.

QIDI's cloud does not serve printers on 02.04, so this is the way to reach the printer remotely.
The installer asks (default yes). The official static build is downloaded on the PC from
pkgs.tailscale.com, checked against its published SHA-256, and copied to the printer.
Logging in is the user's choice: the installer can show the login link, or it can be done later.
Uninstall removes it only if this installer put it there (marker line in /etc/default/tailscaled).
"""
import hashlib
import io
import json
import re
import tarfile
import urllib.request
from pathlib import Path

INDEX_URL = "https://pkgs.tailscale.com/stable/?mode=json"
BASE_URL = "https://pkgs.tailscale.com/stable/"
DOWNLOADS = Path(__file__).resolve().parent.parent / "downloads" / "tailscale"
MARKER = "# installed by qidi-q2-0204-tweaked (uninstall removes it)"
BINARIES = {"tailscale": "/usr/bin/tailscale", "tailscaled": "/usr/sbin/tailscaled"}
UNIT = "/etc/systemd/system/tailscaled.service"
DEFAULTS = "/etc/default/tailscaled"
ARCHES = {"aarch64": "arm64", "arm64": "arm64", "armv7l": "arm", "armv6l": "arm"}
LOGIN_HINT = ("Log in later: run install.bat again, or over SSH on the printer:\n"
              "  sudo tailscale up --accept-dns=false --hostname=qidi-q2")
URL_RE = re.compile(r"https://login\.tailscale\.com/\S+")


def _get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "qidi-q2-0204-tweaked"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch(arch, get=_get, downloads=None):
    """{name: bytes} for tailscale, tailscaled and the systemd unit of the newest stable build."""
    downloads = downloads or DOWNLOADS
    index = json.loads(get(INDEX_URL))
    name = index["Tarballs"][arch]
    expected = get(BASE_URL + name + ".sha256").decode().split()[0].lower()
    path = downloads / name
    data = path.read_bytes() if path.is_file() else None
    if data is None or hashlib.sha256(data).hexdigest() != expected:
        print("Downloading %s ..." % name, flush=True)
        data = get(BASE_URL + name, timeout=300)
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("Tailscale download does not match its published SHA-256 - not installed")
        downloads.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    out = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        for member in tf.getmembers():
            base = member.name.split("/", 1)[-1]
            if base in ("tailscale", "tailscaled", "systemd/tailscaled.service"):
                out[base] = tf.extractfile(member).read()
    missing = {"tailscale", "tailscaled", "systemd/tailscaled.service"} - set(out)
    if missing:
        raise ValueError("Tailscale package incomplete: " + ", ".join(sorted(missing)))
    out["version"] = index.get("TarballsVersion", "?")
    return out


def defaults_file(userspace):
    flags = "--tun=userspace-networking" if userspace else ""
    return ('%s\nPORT="41641"\nFLAGS="%s"\n' % (MARKER, flags)).encode()


def status(p):
    """(installed, ours, backend_state) on the printer."""
    out = p._run("command -v tailscale >/dev/null && echo yes || echo no; "
                 "grep -qxF %s %s 2>/dev/null && echo ours || echo theirs; "
                 "tailscale status --json 2>/dev/null | head -c 20000 || true"
                 % (_q(MARKER), DEFAULTS), sudo=True).decode("utf-8", "replace").split("\n", 2)
    installed, ours = out[0].strip() == "yes", out[1].strip() == "ours"
    state = None
    try:
        state = json.loads(out[2]).get("BackendState")
    except (ValueError, IndexError, AttributeError):
        pass
    return installed, ours, state


def _q(text):
    return "'" + text.replace("'", "'\\''") + "'"


def install(p, files):
    """Copy the build, start the service. Returns True when the kernel has no TUN (userspace mode)."""
    userspace = p._run("test -c /dev/net/tun || modprobe tun 2>/dev/null; test -c /dev/net/tun && echo tun || echo none",
                       sudo=True).decode().strip() != "tun"
    p.install(files["tailscaled"], BINARIES["tailscaled"], "root", "root", "755")
    p.install(files["tailscale"], BINARIES["tailscale"], "root", "root", "755")
    p.install(files["systemd/tailscaled.service"], UNIT, "root", "root", "644")
    p.install(defaults_file(userspace), DEFAULTS, "root", "root", "644")
    p._run("systemctl daemon-reload && systemctl enable --now tailscaled", sudo=True)
    return userspace


def login(p):
    """Start the login; returns the link to open, or None when already logged in / no link came."""
    out = p._run("timeout 25 tailscale up --accept-dns=false --hostname=qidi-q2 2>&1 || true",
                 sudo=True).decode("utf-8", "replace")
    m = URL_RE.search(out)
    return m.group(0) if m else None


def uninstall(p):
    """Remove Tailscale if this installer put it there."""
    installed, ours, _ = status(p)
    if not (installed and ours):
        return False
    p._run("systemctl disable --now tailscaled; /usr/sbin/tailscaled --cleanup; "
           "rm -f %s %s %s %s; rm -rf /var/lib/tailscale; systemctl daemon-reload"
           % (BINARIES["tailscale"], BINARIES["tailscaled"], UNIT, DEFAULTS), sudo=True, check=False)
    print("  removed: Tailscale")
    return True


def ask(question, default=True, read=input):
    answer = read("%s [%s] " % (question, "Y/n" if default else "y/N")).strip().lower()
    return default if not answer else answer in ("y", "yes", "t", "tak")


def offer(p, mode="ask", read=input, get=_get):
    """The installer's Tailscale step. mode: ask / yes / no."""
    if mode == "no":
        return
    installed, ours, state = status(p)
    if not installed:
        print("\nQIDI's cloud does not serve printers on 02.04. Tailscale (free, by tailscale.com) lets you use\n"
              "Fluidd, OrcaSlicer and the camera from anywhere, privately - only devices logged in to your\n"
              "own Tailscale account can reach the printer. It uses about 40 MB of the printer's memory.")
        if mode == "ask" and not ask("Install Tailscale on the printer?", True, read):
            print("Tailscale not installed. You can run the installer again any time to add it.")
            return
        arch = ARCHES.get(p._run("uname -m").decode().strip())
        if not arch:
            print("Tailscale: this printer's processor type is not supported - skipped.")
            return
        files = fetch(arch, get=get)
        userspace = install(p, files)
        print("Tailscale %s installed%s." % (files["version"], " (userspace networking)" if userspace else ""))
        state = "NeedsLogin"
    if state == "Running":
        print("Tailscale is installed and logged in.")
        return
    if mode == "ask" and not ask("Log in to Tailscale now?", True, read):
        print(LOGIN_HINT)
        return
    link = login(p)
    if link:
        print("Open this link in a browser and log in to your Tailscale account:\n  " + link)
        print("The printer then shows up in your Tailscale admin page as 'qidi-q2'.")
    else:
        print("No login link came back (already logged in, or no internet on the printer).\n" + LOGIN_HINT)
