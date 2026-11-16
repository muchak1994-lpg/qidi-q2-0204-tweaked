# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""Optional Tailscale on the printer: reach Fluidd, OrcaSlicer uploads and the camera from anywhere.

QIDI's cloud does not serve printers on 02.04, so this is the way to reach the printer remotely.
The installer asks (default yes). The official static build of a version pinned here (with its
SHA-256) is downloaded on the PC, checked, and copied to the printer; a newer project release brings
a newer pin and the installer then offers the update. Moonraker is told to trust Tailscale addresses
(like it trusts the home network), otherwise Fluidd/OrcaSlicer would get "401 Unauthorized".
Logging in is the user's choice: the link is shown in the window (never written to the log), or it
is done later. Uninstall removes it only if this installer put it there (marker in /etc/default/tailscaled).
"""
import hashlib
import io
import re
import sys
import tarfile
import urllib.request
from pathlib import Path

VERSION = "1.104.7"
SHA256 = {  # https://pkgs.tailscale.com/stable/tailscale_<VERSION>_<arch>.tgz.sha256
    "arm64": "d6bed2720310b328b861f943d7b4016c5358a9bad60575eb51e8143b79068484",
    "arm": "1c753fef45d497491081db37552b7a2a42c7932292743bf6936cb1a42b6bceb0",
}
BASE_URL = "https://pkgs.tailscale.com/stable/"
DOWNLOADS = Path(__file__).resolve().parent.parent / "downloads" / "tailscale"
MARKER = "# installed by qidi-q2-0204-tweaked (uninstall removes it)"
BINARIES = {"tailscale": "/usr/bin/tailscale", "tailscaled": "/usr/sbin/tailscaled"}
UNIT = "/etc/systemd/system/tailscaled.service"
DEFAULTS = "/etc/default/tailscaled"
MODULES_LOAD = "/etc/modules-load.d/tailscale-tun.conf"
MOONRAKER_CONF = "/home/qidi/printer_data/config/moonraker.conf"
TRUST_TAG = "# tailscale (qidi-q2-0204-tweaked)"
TRUSTED = ("100.64.0.0/10", "fd7a:115c:a1e0::/48")
ARCHES = {"aarch64": "arm64", "arm64": "arm64", "armv7l": "arm", "armv6l": "arm"}
UP = "tailscale up --accept-dns=false --hostname=qidi-q2"
LOGIN_HINT = ("Log in later: run install.bat again, or over SSH on the printer:\n  sudo " + UP)
URL_RE = re.compile(r"https://login\.tailscale\.com/\S+")
STATE_RE = re.compile(r'"BackendState"\s*:\s*"(\w+)"')
VERSION_RE = re.compile(r"^(\d+\.\d+\.\d+)", re.M)


def _get(url, timeout=300):
    req = urllib.request.Request(url, headers={"User-Agent": "qidi-q2-0204-tweaked"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch(arch, get=_get, downloads=None):
    """{name: bytes} of the pinned build: tailscale, tailscaled, the systemd unit."""
    downloads = downloads or DOWNLOADS
    name = "tailscale_%s_%s.tgz" % (VERSION, arch)
    path = downloads / name
    data = path.read_bytes() if path.is_file() else None
    if data is None or hashlib.sha256(data).hexdigest() != SHA256[arch]:
        print("Downloading %s ..." % name, flush=True)
        data = get(BASE_URL + name)
        if hashlib.sha256(data).hexdigest() != SHA256[arch]:
            raise ValueError("Tailscale download does not match the SHA-256 pinned in this project - not installed")
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
    return out


def defaults_file(userspace):
    flags = "--tun=userspace-networking" if userspace else ""
    return ('%s\nPORT="41641"\nFLAGS="%s"\n' % (MARKER, flags)).encode()


def _q(text):
    return "'" + text.replace("'", "'\\''") + "'"


def status(p):
    """dict: installed, ours, running (service active), state (BackendState), version."""
    out = p._run("command -v tailscale >/dev/null && echo yes || echo no; "
                 "grep -qxF %s %s 2>/dev/null && echo ours || echo theirs; "
                 "systemctl is-active tailscaled 2>/dev/null || true; "
                 "tailscale version 2>/dev/null | head -1 || true; "
                 "tailscale status --json --peers=false 2>/dev/null || true"
                 % (_q(MARKER), DEFAULTS), sudo=True).decode("utf-8", "replace")
    lines = out.split("\n", 4) + [""] * 5
    m = STATE_RE.search(lines[4])
    v = VERSION_RE.search(lines[3])
    return {"installed": lines[0].strip() == "yes", "ours": lines[1].strip() == "ours",
            "running": lines[2].strip() == "active", "state": m.group(1) if m else None,
            "version": v.group(1) if v else None}


def trust_in_moonraker(p, add=True):
    """Add (or take out) Tailscale addresses in Moonraker's trusted_clients. True if the file changed."""
    data = p.read(MOONRAKER_CONF)
    if data is None:
        return False
    text = data.decode("utf-8")
    lines = [l for l in text.split("\n") if TRUST_TAG not in l]
    if add:
        for i, line in enumerate(lines):
            if line.strip() == "trusted_clients:":
                lines[i + 1:i + 1] = ["    %s  %s" % (net, TRUST_TAG) for net in TRUSTED]
                break
        else:
            return False  # no trusted_clients section: leave the file alone
    new = "\n".join(lines)
    if new == text:
        return False
    owner = p.stat(MOONRAKER_CONF) or ("qidi", "netdev", "644")
    p.install(new.encode("utf-8"), MOONRAKER_CONF, *owner)
    return True


def install(p, files):
    """Copy the build, start the service. Returns True for userspace networking (no TUN)."""
    tun = p._run("test -c /dev/net/tun && echo tun || (modprobe tun 2>/dev/null && test -c /dev/net/tun "
                 "&& echo loaded || echo none)", sudo=True).decode().strip()
    userspace = tun == "none"
    p.install(defaults_file(userspace), DEFAULTS, "root", "root", "644")  # marker first: a stop half-way is still ours
    if tun == "loaded":  # TUN only after modprobe: load it at every boot too
        p.install(b"tun\n", MODULES_LOAD, "root", "root", "644")
    p.install(files["tailscaled"], BINARIES["tailscaled"], "root", "root", "755")
    p.install(files["tailscale"], BINARIES["tailscale"], "root", "root", "755")
    p.install(files["systemd/tailscaled.service"], UNIT, "root", "root", "644")
    p._run("systemctl daemon-reload && systemctl enable tailscaled && systemctl restart tailscaled", sudo=True)
    if trust_in_moonraker(p, add=True):
        p._run("systemctl restart moonraker", sudo=True)
    return userspace


def login(p):
    """Start the login; returns the link to open, or None when already logged in / no link came."""
    out = p._run("timeout 25 %s 2>&1 || true" % UP, sudo=True).decode("utf-8", "replace")
    m = URL_RE.search(out)
    return m.group(0) if m else None


def uninstall(p):
    """Remove Tailscale if this installer put it there."""
    st = status(p)
    if not st["ours"]:
        return False
    p._run("timeout 15 tailscale logout 2>/dev/null; systemctl disable --now tailscaled; "
           "/usr/sbin/tailscaled --cleanup; rm -f %s %s %s %s %s; rm -rf /var/lib/tailscale; systemctl daemon-reload"
           % (BINARIES["tailscale"], BINARIES["tailscaled"], UNIT, DEFAULTS, MODULES_LOAD), sudo=True, check=False)
    if trust_in_moonraker(p, add=False):
        p._run("systemctl restart moonraker", sudo=True, check=False)
    print("  removed: Tailscale (logged out of your Tailscale account)")
    return True


def ask(question, default=True, read=input):
    answer = read("%s [%s] " % (question, "Y/n" if default else "y/N")).strip().lower()
    return default if not answer else answer in ("y", "yes", "t", "tak")


def show_private(text):
    """Print to the window only - never into the shared log (the login link is a key to the printer)."""
    stream = getattr(sys.stdout, "stream", sys.stdout)
    stream.write(text + "\n")
    stream.flush()
    log = getattr(sys.stdout, "log", None)
    if log is not None:
        try:
            log.write("[login link shown in the window - not saved in this log]\n")
        except (OSError, ValueError):
            pass


def offer(p, mode="ask", read=input, get=_get):
    """The installer's Tailscale step. mode: ask / yes / no."""
    if mode == "no":
        return
    try:
        _offer(p, mode, read, get)
    except (KeyboardInterrupt, EOFError):
        print("\nTailscale step left out. Run the installer again any time to add it.")


def _offer(p, mode, read, get):
    st = status(p)
    if st["installed"] and not st["ours"]:
        print("Tailscale is already on the printer (installed by you) - left as it is.")
        return
    needs_files = not st["installed"] or (st["ours"] and st["version"] != VERSION)
    if not st["installed"]:
        print("\nQIDI's cloud does not serve printers on 02.04. Tailscale (free, by tailscale.com) lets you use\n"
              "Fluidd, OrcaSlicer and the camera from anywhere, privately - only devices logged in to your\n"
              "own Tailscale account can reach the printer. It uses about 40 MB of the printer's memory.")
        if mode == "ask" and not ask("Install Tailscale on the printer?", True, read):
            print("Tailscale not installed. You can run the installer again any time to add it.")
            return
    elif needs_files and mode == "ask" and not ask(
            "Update Tailscale on the printer from %s to %s?" % (st["version"] or "?", VERSION), True, read):
        needs_files = False
    if needs_files or not st["running"]:
        arch = ARCHES.get(p._run("uname -m").decode().strip())
        if not arch:
            print("Tailscale: this printer's processor type is not supported - skipped.")
            return
        userspace = install(p, fetch(arch, get=get))
        print("Tailscale %s installed and running%s." % (VERSION, " (userspace networking)" if userspace else ""))
        st = status(p)
    else:
        trust_in_moonraker(p, add=True) and p._run("systemctl restart moonraker", sudo=True)
    if st["state"] == "Running":
        print("Tailscale is logged in.")
        return
    if mode == "ask" and not ask("Log in to Tailscale now?", True, read):
        print(LOGIN_HINT)
        return
    link = login(p)
    if link:
        show_private("Open this link in a browser and log in to your Tailscale account (do not share it):\n  " + link)
        print("The printer then shows up in your Tailscale admin page as 'qidi-q2'.")
    else:
        print("No login link came back (already logged in, or no internet on the printer).\n" + LOGIN_HINT)
