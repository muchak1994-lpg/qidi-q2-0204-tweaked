# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""Optional phone notifications (ntfy): the installer's questions and the private configuration.

The module phone-notifications puts the scripts and macros on the printer; this step makes them work. It creates two
random channel names (the "events" channel the phone subscribes to, and a secret "commands" channel the buttons of
the messages write to), writes q2_notify.conf (mode 600) and the Moonraker notifier for printer errors, and sends a
test message. The channel names are secrets like a password: they are shown in the installer window only, never in the
log file, never in the project; a copy of the configuration is kept on this PC in backups/ (not in the project).
Uninstall removes what this step added. Needs no account: the free server https://ntfy.sh is the default, an own
ntfy server can be given.
"""
import re
import secrets
import time
from pathlib import Path

import tailscale_setup

REPO = Path(__file__).resolve().parent.parent
BACKUPS = REPO / "backups"
CONF = "/home/qidi/printer_data/config/q2_notify.conf"
MOONRAKER_NOTIFIER = "/home/qidi/printer_data/config/q2_notify_moonraker.conf"
MOONRAKER_CONF = tailscale_setup.MOONRAKER_CONF
INCLUDE_LINE = "[include q2_notify_moonraker.conf]"
INCLUDE_TAG = "# phone notifications (qidi-q2-0204-tweaked)"
TEMPLATE = REPO / "modules" / "phone-notifications" / "files" / "q2_notify_moonraker.conf"
SEND = "/home/qidi/q2-notify/q2_notify_send.sh"
LISTEN_SERVICE = "q2-notify-listen.service"
DEFAULT_SERVER = "https://ntfy.sh"
OWNER = ("qidi", "qidi")


def _ask(question, default=False, read=input):
    try:
        answer = read("%s [%s] " % (question, "Y/n" if default else "y/N")).strip().lower()
    except EOFError:
        return default
    return default if not answer else answer in ("y", "yes", "t", "tak")


def wanted(mode="ask", read=input):
    """Before the modules are chosen: should the phone-notifications module be installed? (default: no)"""
    if mode == "yes":
        return True
    if mode == "no":
        return False
    print("\nPhone notifications (optional): messages on your phone when a print starts, at 25/50/75 %, ends,\n"
          "pauses (with the reason, a camera picture and Resume / Cancel buttons) or fails, and the timelapse\n"
          "video on a button. Free, no account, no phone number: it uses the ntfy app and server (ntfy.sh).")
    return _ask("Set up phone notifications?", False, read)


def parse_conf(data):
    """{KEY: value} of a q2_notify.conf."""
    out = {}
    for line in (data or b"").decode("utf-8", "replace").splitlines():
        key, sep, value = line.partition("=")
        if sep:
            out[key.strip()] = value.strip()
    return out


def render_conf(server, events, commands):
    return ("ENABLED=1\nNTFY_SERVER=%s\nEVENTS_TOPIC=%s\nCMD_TOPIC=%s\n" % (server, events, commands)).encode()


def apprise_url(server, topic):
    """ntfy address in the form Moonraker's notifier (apprise) understands."""
    m = re.match(r"^(https?)://([^/\s]+)", server)
    scheme = "ntfys" if m.group(1) == "https" else "ntfy"
    return "%s://%s/%s?priority=high" % (scheme, m.group(2), topic)


def _server(read):
    try:
        text = read("ntfy server address (Enter = %s, the free public server): " % DEFAULT_SERVER).strip()
    except EOFError:
        text = ""
    if not text:
        return DEFAULT_SERVER
    if not re.match(r"^https?://[^/\s]+/?$", text):
        print("That is not a server address (http://... or https://...) - using %s." % DEFAULT_SERVER)
        return DEFAULT_SERVER
    return text.rstrip("/")


def _eol(text):
    return "\r\n" if text.count("\r\n") * 2 > text.count("\n") else "\n"


def add_include(p):
    """[include q2_notify_moonraker.conf] at the end of moonraker.conf, once. True if the file changed."""
    data = p.read(MOONRAKER_CONF)
    if data is None:
        return False
    text = data.decode("utf-8")
    if INCLUDE_LINE in text:
        return False
    eol = _eol(text)
    if text and not text.endswith("\n"):
        text += eol
    text += eol + INCLUDE_TAG + eol + INCLUDE_LINE + eol
    owner = p.stat(MOONRAKER_CONF) or ("qidi", "netdev", "644")
    p.install(text.encode("utf-8"), MOONRAKER_CONF, *owner)
    return True


def remove_include(p):
    data = p.read(MOONRAKER_CONF)
    if data is None:
        return False
    text = data.decode("utf-8")
    eol = _eol(text)
    block = eol + INCLUDE_TAG + eol + INCLUDE_LINE + eol
    if block in text:
        new = text.replace(block, "", 1)
    else:
        new = eol.join(l for l in text.split(eol) if l.strip() not in (INCLUDE_TAG, INCLUDE_LINE))
    if new == text:
        return False
    owner = p.stat(MOONRAKER_CONF) or ("qidi", "netdev", "644")
    p.install(new.encode("utf-8"), MOONRAKER_CONF, *owner)
    return True


def configure(p, mode="ask", read=input, secrets_fn=secrets.token_urlsafe, backups=BACKUPS, host="printer"):
    """Create the configuration (or keep the existing one), connect Moonraker, restart, send a test message.
    Returns True when the notifications are set up."""
    if mode == "no":
        return False
    existing = parse_conf(p.read(CONF))
    if existing.get("EVENTS_TOPIC") and existing.get("CMD_TOPIC") and existing.get("NTFY_SERVER"):
        server, events, commands = existing["NTFY_SERVER"], existing["EVENTS_TOPIC"], existing["CMD_TOPIC"]
        conf = p.read(CONF)
        print("Phone notifications: the existing configuration is kept.")
    else:
        server = _server(read)
        events, commands = secrets_fn(16), secrets_fn(16)
        conf = render_conf(server, events, commands)
        p.install(conf, CONF, OWNER[0], OWNER[1], "600")
    try:
        copy_dir = Path(backups) / ("notify-%s-%s" % (host, time.strftime("%Y%m%d-%H%M%S")))
        copy_dir.mkdir(parents=True, exist_ok=True)
        (copy_dir / "q2_notify.conf").write_bytes(conf)
    except OSError as exc:
        print("Could not keep a copy of the notification settings on this PC:", exc)
    template = TEMPLATE.read_text(encoding="utf-8")
    notifier = template.replace("__NTFY_URL__", apprise_url(server, events)).encode("utf-8")
    changed = p.read(MOONRAKER_NOTIFIER) != notifier
    if changed:
        p.install(notifier, MOONRAKER_NOTIFIER, OWNER[0], OWNER[1], "600")
    changed = add_include(p) or changed
    p._run("systemctl daemon-reload && systemctl enable %s && systemctl restart %s" % (LISTEN_SERVICE, LISTEN_SERVICE),
           sudo=True, check=False)
    if changed:
        p._run("systemctl restart moonraker", sudo=True, check=False)
    p._run("sh %s 'Phone notifications are on' 'Test message from the installer. Buttons and messages work from now on.' "
           "--prio 3 --tags tada" % SEND, sudo=True, check=False)
    print("Phone notifications are set up (the channel names are not written to this log).")
    tailscale_setup.show_private(
        "Phone: install the free ntfy app (Android or iPhone), tap +, 'Subscribe to topic' and enter:\n"
        "  topic:   %s\n  server:  %s\n"
        "The test message should arrive in a few seconds. Treat the topic like a password (it shows the names of\n"
        "your prints). A second, secret channel carries the Resume/Cancel/timelapse buttons and is never shown."
        % (events, server))
    return True


def remove(p):
    """Uninstall: take out what configure() added. True if there was anything."""
    had = p.read(CONF) is not None or p.read(MOONRAKER_NOTIFIER) is not None
    data = p.read(MOONRAKER_CONF)
    had_include = data is not None and INCLUDE_LINE in data.decode("utf-8", "replace")
    if not (had or had_include):
        return False
    p._run("systemctl disable --now %s 2>/dev/null; true" % LISTEN_SERVICE, sudo=True, check=False)
    p.remove(CONF)
    p.remove(MOONRAKER_NOTIFIER)
    remove_include(p)
    p._run("systemctl restart moonraker", sudo=True, check=False)
    print("  removed: phone notification settings (the channel names are gone from the printer)")
    return True
