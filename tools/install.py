#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
"""QIDI Q2 02.04 Tweaked - install / uninstall on the printer.

    python tools/install.py plan      --host IP     what would change (changes nothing)
    python tools/install.py install   --host IP     backup on the PC, then install
    python tools/install.py uninstall --host IP     put the backed-up originals back
    --skip MODULE (repeatable) leaves a module out; --with MODULE adds an optional one

install:
  1. checks: firmware 01.01.02.04; printer idle (not printing, paused or heating)
  2. builds every file on the PC (tools/build.py) and compares with the printer:
     each file must be the 02.04 original or already our version - otherwise stop
  3. backup on the PC (backups/printer-...): every file that will change, with
     owner and mode, plus a record of what was done
  4. uploads into a private temporary folder, installs with sudo, checks each
     file's SHA-256, runs the module actions, restarts the affected services and
     removes the temporary folder. Nothing else of ours stays on the printer.
Configuration files that hold your calibration (printer.cfg, macros) are not
replaced: the same edits are applied to the file that is on your printer.
"""
import argparse
import base64
import getpass
import hashlib
import os
import io
import json
import posixpath
import re
import shlex
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402
import firmware  # noqa: E402
import notify_setup  # noqa: E402
import orca_profiles  # noqa: E402
import tailscale_setup  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
VERSION = (REPO / "VERSION").read_text(encoding="utf-8").strip() if (REPO / "VERSION").is_file() else "dev"
BACKUPS = REPO / "backups"
SERVICES = {"klipper": "klipper.service", "moonraker": "moonraker.service",
            "algo_app": "algo_app.service", "qidi-client": "qidi-client.service"}
RESTART_ORDER = ["klipper", "moonraker", "algo_app", "qidi-client"]
UNDO_ACTIONS = {  # how to reverse a module action on uninstall
    ("chattr", "+i"): lambda a: ["chattr", "-i"] + a[2:],
    ("systemctl", "enable"): lambda a: ["systemctl", "disable", "--now"] + a[3:],
    ("systemctl", "disable"): lambda a: ["systemctl", "enable", "--now"] + a[3:],
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def db_url(namespace, key):
    """Moonraker's address of one database entry, with the names encoded for a URL."""
    from urllib.parse import urlencode
    return "http://127.0.0.1:7125/server/database/item?" + urlencode({"namespace": namespace, "key": key})


class InstallError(Exception):
    pass


# ------------------------------------------------------------------ printer
HASH_CHUNK = 40      # files per sha256sum command
HASH_WORKERS = 3     # commands that run at the same time (separate SSH channels)
FIND_FORMAT = "'%p|%s|%C@|%i\n'"   # path | size | ctime (nanoseconds) | inode: the printer's own identity of a file


class HashCache:
    """What the printer's files hashed to last time, kept on the PC (work/hash-cache-<printer>.json).

    A file counts as unchanged only when its identity (size, ctime in nanoseconds, inode) is exactly what it was when the hash was
    taken. ctime changes on every write, rename or chmod and cannot be set with touch; anything else is hashed again. path=None:
    only in memory. A file that cannot be read or is not the expected shape is ignored."""

    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.data = {}
        self.dirty = False
        if self.path and self.path.is_file():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.data = {k: v for k, v in loaded.items()
                                 if isinstance(v, dict) and isinstance(v.get("key"), str) and isinstance(v.get("sha"), str)}
            except (OSError, ValueError):
                self.data = {}

    def get(self, path, key):
        entry = self.data.get(path)
        return entry["sha"] if entry and entry["key"] == key else None

    def put(self, path, key, digest):
        if self.data.get(path) != {"key": key, "sha": digest}:
            self.data[path] = {"key": key, "sha": digest}
            self.dirty = True

    def drop(self, path):
        if self.data.pop(path, None) is not None:
            self.dirty = True

    def save(self):
        if not (self.path and self.dirty):
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps(self.data, indent=0), encoding="utf-8")
            tmp.replace(self.path)
            self.dirty = False
        except OSError:
            pass  # a cache is a help, never a reason to stop


def hash_cache_file(printer_id, host):
    """work/hash-cache-<printer>.json for this printer."""
    name = re.sub(r"[^0-9A-Za-z_.-]", "_", printer_id or host)
    return REPO / "work" / ("hash-cache-%s.json" % name)


class SSHPrinter:
    """Operations on the real printer over SSH. sudo uses the SSH password (None: sudo needs none)."""
    hash_cache = None
    rehash = False
    _units = None

    def __init__(self, host, user, password, port=22, client=None):
        import printer
        self.client = client or printer.connect(host, user, port, password=password)
        self.password = password
        self.sftp = self.client.open_sftp()
        self.staging = None

    @classmethod
    def open(cls, host, user, port=22):
        """With the user's SSH key and passwordless sudo when the printer allows both (set up by the owner,
        never by this project); otherwise the password is asked once, as before, for login and sudo."""
        import printer
        client = printer.connect_with_key(host, user, port)
        if client is not None:
            p = cls(host, user, None, port, client=client)
            if p._run("sudo -n true", check=False, raw=True) is not None:
                print("Logged in with the SSH key (sudo needs no password).")
                return p
            for _ in range(3):  # checked here, not halfway through the install
                p.password = getpass.getpass("sudo password for %s@%s: " % (user, host))
                if p.sudo_works():
                    print("Logged in with the SSH key.")
                    return p
                print("Wrong sudo password, try again.")
            raise InstallError("sudo password not accepted by the printer")
        password = getpass.getpass("SSH password for %s@%s: " % (user, host))
        return cls(host, user, password, port)

    def sudo_works(self):
        """True when sudo accepts self.password (the password goes on stdin, never on the command line)."""
        stdin, out, _ = self.client.exec_command("sudo -S -p '' true", timeout=60)
        stdin.write(self.password + "\n")
        stdin.flush()
        out.read()
        return out.channel.recv_exit_status() == 0

    def _run(self, command, sudo=False, check=True, raw=False):
        """raw: run as is and return None on a non-zero exit."""
        if raw:
            _, out, _ = self.client.exec_command(command, timeout=60)
            data = out.read()
            return data if out.channel.recv_exit_status() == 0 else None
        if sudo and self.password is None:
            command = "sudo -n sh -c %s" % shlex.quote(command)
        elif sudo:
            command = "sudo -S -p '' sh -c %s" % shlex.quote(command)
        stdin, out, err = self.client.exec_command(command, timeout=900)
        if sudo and self.password is not None:
            stdin.write(self.password + "\n")
            stdin.flush()
        data = out.read()
        error = err.read().decode("utf-8", "replace")
        code = out.channel.recv_exit_status()
        if check and code != 0:
            raise InstallError("printer command failed (%d): %s\n%s" % (code, command[:160], error.strip()[:400]))
        return data

    def printer_id(self):
        """This printer's own ID (the processor's serial number), the same over any address and after a
        reflash - so backups made over the home network and over Tailscale belong to one printer."""
        out = self._run("sed -n 's/.*androidboot.serialno=\\([0-9A-Za-z]*\\).*/\\1/p' /proc/cmdline; "
                        "cat /etc/machine-id 2>/dev/null; true").decode().split()
        if not out:
            return None
        return ("serial:" if len(out) > 1 or len(out[0]) != 32 else "machine:") + out[0]

    def known_as(self, host):
        """True when the SSH key saved for that address is this printer's key (backups from before printer IDs)."""
        key = self.client.get_transport().get_remote_server_key()
        for store in (self.client.get_host_keys(), getattr(self.client, "_system_host_keys", None)):
            entry = store.lookup(host) if store is not None else None
            if entry and key.get_name() in entry and entry[key.get_name()] == key:
                return True
        return False

    def sha(self, path):
        out = self._run("sha256sum %s 2>/dev/null || true" % shlex.quote(path), sudo=True).decode()
        return out.split()[0] if out.strip() else None

    def use_hash_cache(self, cache, rehash=False):
        """Remember hashes between runs (see HashCache); rehash: ignore what is remembered this time."""
        self.hash_cache, self.rehash = cache, rehash

    def file_keys(self, paths):
        """{path: "size|ctime|inode"} of the files that exist, in one command."""
        keys = {}
        paths = list(paths)
        for i in range(0, len(paths), 300):
            chunk = " ".join(shlex.quote(p) for p in paths[i:i + 300])
            out = self._run("find -L %s -maxdepth 0 -printf %s 2>/dev/null; true" % (chunk, FIND_FORMAT), sudo=True).decode()
            for line in out.splitlines():
                parts = line.rsplit("|", 3)  # the path comes first and may itself contain a "|"
                if len(parts) == 4:
                    keys[parts[0]] = "|".join(parts[1:])
        return keys

    def _hash_chunk(self, chunk):
        out = self._run("sha256sum %s 2>/dev/null || true" % " ".join(shlex.quote(p) for p in chunk), sudo=True).decode()
        found = {}
        for line in out.splitlines():
            digest, _, path = line.partition("  ")
            found[path] = digest
        return found

    def sha_many(self, paths):
        """{path: sha256 or None}. With a hash cache only files whose identity changed are hashed (in parallel chunks)."""
        paths = list(paths)
        result = {p: None for p in paths}
        cache, keys, todo = self.hash_cache, {}, paths
        if cache is not None:
            keys = self.file_keys(paths)
            todo = []
            for path in paths:
                if path not in keys:
                    cache.drop(path)  # not there (any more)
                    continue
                cached = None if self.rehash else cache.get(path, keys[path])
                if cached:
                    result[path] = cached
                else:
                    todo.append(path)
        chunks = [todo[i:i + HASH_CHUNK] for i in range(0, len(todo), HASH_CHUNK)]
        if len(chunks) > 1:
            with ThreadPoolExecutor(max_workers=HASH_WORKERS) as pool:
                found_all = list(pool.map(self._hash_chunk, chunks))
        else:
            found_all = [self._hash_chunk(c) for c in chunks]
        for found in found_all:
            for path, digest in found.items():
                if path in result:
                    result[path] = digest
                    if cache is not None and path in keys:
                        cache.put(path, keys[path], digest)
        if cache is not None:
            cache.save()
        return result

    def read(self, path):
        out = self._run("test -f %s && base64 -w0 %s || echo -n MISSING" % ((shlex.quote(path),) * 2), sudo=True)
        return None if out == b"MISSING" else base64.b64decode(out)

    def stat(self, path):
        out = self._run("stat -c '%%U %%G %%a' %s 2>/dev/null || true" % shlex.quote(path), sudo=True).decode()
        return out.split() or None

    def install(self, data, path, owner, group, mode):
        if self.staging is None:
            self.staging = self._run("mktemp -d /tmp/q2t.XXXXXXXX").decode().strip()
        tmp = posixpath.join(self.staging, "upload")
        self.sftp.putfo(io.BytesIO(data), tmp)
        self._units = None  # what was remembered about services may be out of date now
        # one command: write, then print the digest and the identity of the file as it is on the printer
        out = self._run("mkdir -p %s && install -o %s -g %s -m %s %s %s && rm -f %s && sha256sum %s && find -L %s -maxdepth 0 -printf %s" % (
            shlex.quote(posixpath.dirname(path)), owner, group, mode, tmp, shlex.quote(path), tmp,
            shlex.quote(path), shlex.quote(path), FIND_FORMAT), sudo=True).decode().splitlines()
        if not out or out[0].partition("  ")[0] != sha(data):
            raise InstallError("verification failed after writing " + path)
        if self.hash_cache is not None:
            parts = out[1].rsplit("|", 3) if len(out) > 1 else []
            if len(parts) == 4:
                self.hash_cache.put(path, "|".join(parts[1:]), sha(data))
            else:
                self.hash_cache.drop(path)

    def remove(self, path):
        self._units = None
        if self.hash_cache is not None:
            self.hash_cache.drop(path)
        self._run("rm -f %s" % shlex.quote(path), sudo=True)

    def action(self, argv, check=True):
        self._units = None  # an action may change a service: ask again next time
        if argv[0] == "moonraker-db":
            # ["moonraker-db", namespace, key, JSON value(, JSON value on uninstall)]: one Moonraker database entry
            body = json.dumps({"namespace": argv[1], "key": argv[2], "value": json.loads(argv[3])})
            self._run("curl -sf -X POST -H 'Content-Type: application/json' -d %s "
                      "http://127.0.0.1:7125/server/database/item >/dev/null" % shlex.quote(body), check=check)
            return
        if argv[0] == "moonraker-db-delete":
            # ["moonraker-db-delete", namespace, key]: the entry was not there before the install
            self._run("curl -s -X DELETE %s >/dev/null" % shlex.quote(db_url(argv[1], argv[2])), check=check)
            return
        if argv[0] == "timezone":
            self._run("timedatectl set-timezone %s" % shlex.quote(argv[1]), sudo=True, check=check)
            return
        if argv[:2] == ["chattr", "+i"]:
            # a freshly flashed printer has no /home/qidi/download yet: make it, then lock it
            self._run("mkdir -p %s && chattr +i %s" % (shlex.quote(argv[2]), shlex.quote(argv[2])),
                      sudo=True, check=check)
            return
        self._run(" ".join(shlex.quote(a) for a in argv), sudo=True, check=check)

    def db_value(self, namespace, key):
        """The JSON text of one Moonraker database entry, or None when it is not set."""
        out = self._run("curl -s %s || true" % shlex.quote(db_url(namespace, key))).decode()
        try:
            return json.dumps(json.loads(out)["result"]["value"])
        except (ValueError, KeyError, TypeError):
            return None

    def has_timezone(self, zone):
        return self._run("test -f /usr/share/zoneinfo/%s && echo yes || echo no" % shlex.quote(zone)
                         ).decode().strip() == "yes"

    def timezone(self):
        return self._run("timedatectl show -p Timezone --value 2>/dev/null || true").decode().strip() or None

    def prefetch_units(self, units):
        """Ask about all these services in ONE command; needs() then answers from it until something is written."""
        units = sorted(set(units))
        if not units:
            return
        out = self._run("for u in %s; do p=$(systemctl cat \"$u\" >/dev/null 2>&1 && echo present || echo missing); "
                        "e=$(systemctl is-enabled \"$u\" 2>/dev/null); a=$(systemctl is-active \"$u\" 2>/dev/null); "
                        "echo \"$u|$p|$e|$a\"; done" % " ".join(shlex.quote(u) for u in units), sudo=True).decode()
        states = {}
        for line in out.splitlines():
            parts = (line.split("|") + ["", "", ""])[:4]
            states[parts[0]] = (parts[1], parts[2], parts[3])
        self._units = dict(self._units or {}, **states)

    def _unit_state(self, unit):
        if not self._units or unit not in self._units:
            self.prefetch_units([unit])
        return (self._units or {}).get(unit, ("missing", "", ""))

    def read_many(self, paths):
        """{path: bytes or None (not there)} for several files in ONE command."""
        paths = list(paths)
        if not paths:
            return {}
        out = self._run("for f in %s; do echo \"@@$f\"; if [ -f \"$f\" ]; then base64 -w0 \"$f\"; echo; else echo MISSING; fi; done"
                        % " ".join(shlex.quote(p) for p in paths), sudo=True).decode()
        result, current = {p: None for p in paths}, None
        for line in out.splitlines():
            if line.startswith("@@") and line[2:] in result and current is None:
                current = line[2:]
            elif current is not None:
                result[current] = None if line == "MISSING" else base64.b64decode(line)
                current = None
        return result

    def stat_many(self, paths):
        """{path: [owner, group, mode] or None} for several files in ONE command."""
        paths = list(paths)
        result = {p: None for p in paths}
        if not paths:
            return result
        out = self._run("stat -c '%%n|%%U|%%G|%%a' %s 2>/dev/null || true" % " ".join(shlex.quote(p) for p in paths),
                        sudo=True).decode()
        for line in out.splitlines():
            parts = line.rsplit("|", 3)
            if len(parts) == 4 and parts[0] in result:
                result[parts[0]] = parts[1:]
        return result

    def needs(self, argv):
        """False when a state-type action is already in effect (so it is skipped)."""
        if argv[0] == "timezone":
            return self.timezone() != argv[1]
        if argv[0] == "moonraker-db":
            current = self.db_value(argv[1], argv[2])
            return current is None or json.loads(current) != json.loads(argv[3])
        if argv[:2] == ["chattr", "+i"]:
            out = self._run("lsattr -d %s 2>/dev/null || true" % shlex.quote(argv[2]), sudo=True).decode()
            return not out.strip() or "i" not in out.split()[0]
        if argv[:2] == ["systemctl", "enable"] or argv[:2] == ["systemctl", "disable"]:
            present, enabled, active = self._unit_state(argv[-1])
            if present == "missing":
                return False  # this printer has no such service: nothing to do (and nothing to undo)
            if argv[1] == "enable":
                return not (enabled == "enabled" and active == "active")
            return not (enabled in ("disabled", "masked", "") and active != "active")
        return True

    def restart(self, name):
        self._units = None
        self._run("systemctl restart %s" % SERVICES[name], sudo=True)

    def http_json(self, url_path):
        return json.loads(self._run("curl -s -m 10 'http://127.0.0.1:7125%s'" % url_path))

    def gcode(self, script, timeout=300):
        """Run one G-code command through Moonraker and wait for it (Moonraker's JSON answer)."""
        body = json.dumps({"script": script})
        return json.loads(self._run("curl -s -m %d -X POST -H 'Content-Type: application/json' -d %s "
                                    "http://127.0.0.1:7125/printer/gcode/script" % (timeout, shlex.quote(body))))

    def remove_tree(self, path):
        """A folder of the toolhead check under THR_SAVE_DIR, then that folder too when it is empty."""
        if not path.startswith(THR_SAVE_DIR + "/") or ".." in path:
            raise InstallError("refusing to remove " + path)
        self._run("rm -rf %s; rmdir %s 2>/dev/null; true" % (shlex.quote(path), shlex.quote(THR_SAVE_DIR)), sudo=True)

    def close(self):
        if self.hash_cache is not None:
            self.hash_cache.save()
        if self.staging:
            self._run("rm -rf %s" % shlex.quote(self.staging), sudo=True, check=False)
            self.staging = None
        self.client.close()


# ------------------------------------------------------------------ checks and plan
def check_printer(p, require_idle=True):
    if p.sha("/home/qidi/update/firmware_manifest.json") != firmware.MANIFEST_SHA256:
        raise InstallError("this printer is not on firmware 01.01.02.04 - nothing was changed")
    if not require_idle:
        return
    status = p.http_json("/printer/objects/query?print_stats&extruder&heater_bed")["result"]["status"]
    state = status["print_stats"]["state"]
    if state in ("printing", "paused"):
        raise InstallError("the printer is %s - run this when it is idle" % state)
    if status["extruder"].get("target", 0) or status["heater_bed"].get("target", 0):
        raise InstallError("a heater is on - turn the heaters off first")


def select(skip, extra=()):
    """All modules except --skip ones; modules marked "default": false only with --with."""
    mods = build.load_modules()
    unknown = (set(skip) | set(extra)) - {m["id"] for m in mods}
    if unknown:
        raise InstallError("unknown module(s): " + ", ".join(sorted(unknown)))
    return [m for m in mods if m["id"] not in skip and (m.get("default", True) or m["id"] in extra)]


def apply_config_edits(data, mods, path, reverse=False):
    for m in (reversed(mods) if reverse else mods):
        edits = m["files"][path].get("edits", [])
        if reverse:
            edits = [[new, old] for old, new in reversed(edits)]
        data = build.apply_edits(data, edits, "%s: %s" % (m["id"], path), any_eol=True)
    return data


def strip_config_edits(data, mods, path):
    """Take out the edits of every module, in its current or any earlier version.

    A module whose edits are not found is treated as not installed; the forward
    step afterwards proves that its original lines are really there."""
    for m in reversed(mods):
        spec = m["files"][path]
        for edits in [spec.get("edits", [])] + spec.get("previous", []):
            undo = [[new, old] for old, new in reversed(edits)]
            try:
                data = build.apply_edits(data, undo, "%s: %s" % (m["id"], path), any_eol=True)
                break
            except build.BuildError:
                continue
    return data


def load_history():
    """Every result this project ever produced for a file: earlier releases (LOCK-history.json) and the
    current result with all modules (LOCK.json). The latter matters when a printer has an optional module
    and the installer now runs without it."""
    path = build.MODULES / "LOCK-history.json"
    history = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    if build.LOCK.is_file():
        for name, digest in json.loads(build.LOCK.read_text(encoding="utf-8")).items():
            history.setdefault(name, []).append(digest)
    return history


OTHER_MODS_HINT = ("\nIf this printer has other modifications (other community fixes, manual edits), put the "
                   "official 01.01.02.04 back first - re-install it from USB, see docs/RECOVERY.md option 2 - "
                   "and run the installer again."
                   "\nIt can also be a half-restored printer: the version check only reads a manifest file, so a printer "
                   "that was restored with another tool, or went back from 01.01.03.x, can pass it while some files "
                   "(for example the Fluidd web files) still come from another version. If you report this, include the "
                   "SHA-256 above and what System > Version shows on the screen.")


class Plan(list):
    """The changes, plus how many of the modules' files were already our version (0 on a first install)."""
    already_ours = 0


def plan(p, selected, built=None):
    """[(path, new_bytes, kind, modules)] that must change on the printer."""
    files, owners = built or build.build(selected)
    index = firmware.load_index()["files"]
    history = load_history()
    by_id = {m["id"]: m for m in selected}
    changes, problems = Plan(), []
    on_printer = {path for path in files
                  if any(by_id[mid].get("files", {}).get(path, {}).get("base") == "printer" for mid in owners[path])}
    hashed = sorted(set(files) - on_printer)  # the others are read and edited, not compared by hash
    shas = p.sha_many(hashed) if hasattr(p, "sha_many") else {f: p.sha(f) for f in hashed}
    reads = p.read_many(sorted(on_printer)) if hasattr(p, "read_many") else {}
    for path in sorted(files):
        mods = [by_id[mid] for mid in owners[path]]
        if path in on_printer:
            current = reads[path] if path in reads else p.read(path)
            if current is None:
                problems.append("%s is missing" % path)
                continue
            try:
                new = apply_config_edits(strip_config_edits(current, mods, path), mods, path)
            except build.BuildError as exc:
                problems.append(str(exc))
                continue
            if new != current:
                changes.append((path, new, "config", owners[path]))
            elif strip_config_edits(current, mods, path) != current:
                changes.already_ours += 1
            continue
        new = files[path]
        current = shas[path]
        if current == sha(new):
            if current != index.get(path, {}).get("sha256"):
                changes.already_ours += 1
            continue
        if current is None:
            changes.append((path, new, "new", owners[path]))
        elif current == index.get(path, {}).get("sha256"):
            changes.append((path, new, "replace", owners[path]))
        elif current in history.get(path, []):
            changes.append((path, new, "upgrade", owners[path]))  # an earlier version of ours
        else:
            problems.append("%s is neither the 02.04 original nor a version of ours (its SHA-256 is %s)" % (path, current))
    for m in selected:
        g = m.get("generate")
        if g and g.get("kind") == "ethernet-mac":
            new = ethernet_mac_file(p)
            current = p.sha(g["path"])
            if current != sha(new):
                changes.append((g["path"], new, "new" if current is None else "generated", [m["id"]]))
        if g and g.get("kind") == "dns-fallback":
            current = p.read(g["path"])
            new = dns_fallback_file(current) if current is not None else None
            if new is None:
                print("  left alone (not QIDI's 02.04 network hook):", g["path"])
            elif new != current:
                changes.append((g["path"], new, "generated", [m["id"]]))
    if problems:
        raise InstallError("the printer is not in a state this installer knows (nothing was changed):\n  "
                           + "\n  ".join(problems) + OTHER_MODS_HINT)
    return changes


def ethernet_mac_file(p):
    uuid = p.read("/root/uuid")
    if not uuid:
        raise InstallError("/root/uuid not found - cannot make the Ethernet MAC file")
    digest = hashlib.md5(uuid).hexdigest()  # as /root/.set_mac.sh: cat /root/uuid | md5sum
    mac = "02:" + ":".join(digest[i:i + 2] for i in range(0, 10, 2))
    return ("# QIDI Q2: use the existing UUID-derived Ethernet identity before DHCP.\n"
            "# Generated for this printer; do not copy a rendered MAC to another printer.\n"
            "[Match]\nOriginalName=eth0\nPath=platform-ff4e0000.ethernet\n\n[Link]\n"
            "NamePolicy=keep kernel database onboard slot path\n"
            "AlternativeNamesPolicy=database onboard slot path\nMACAddressPolicy=none\n"
            "MACAddress=%s\n" % mac).encode()


DNS_HOOK = "/etc/dhcpcd.exit-hook"
DNS_QIDI = b'RAW_DNS_LIST="${RAW_DNS_LIST}114.114.114.114\\n8.8.8.8\\n223.5.5.5\\n"'
DNS_OURS = (b'RAW_DNS_LIST="${RAW_DNS_LIST}1.1.1.1\\n8.8.8.8\\n"'
            b'  # q2-0204-tweaked: global fallback DNS as in QIDI 03.02 (was 114.114.114.114 and 223.5.5.5)')


def dns_fallback_file(data, reverse=False):
    """QIDI's network hook with the fallback DNS of QIDI 03.02 (international): 1.1.1.1 and 8.8.8.8.

    02.04 writes the hook from its package scripts with the Chinese public DNS 114.114.114.114 and
    223.5.5.5 as fallbacks. Only that one line changes; anything else in the file stays as it is.
    Returns None when the line is not there (a hook this installer does not know: left alone)."""
    old, new = (DNS_OURS, DNS_QIDI) if reverse else (DNS_QIDI, DNS_OURS)
    if data.count(old) == 1:
        return data.replace(old, new)
    if data.count(new) == 1:
        return data
    return None


def default_owner(path):
    if path.startswith(("/etc/", "/usr/", "/root/")):
        return "root", "root", ("755" if path.endswith((".sh", ".so")) or path.endswith("/algo_app/main") else "644")
    return "qidi", "netdev", ("755" if path.endswith(".sh") else "644")


STATE_ACTIONS = (("chattr", "+i"), ("systemctl", "enable"), ("systemctl", "disable"))


def is_state_action(action):
    """Lock a folder, enable/disable a service, set a Moonraker database entry or the time zone."""
    return (tuple(action[:2]) in STATE_ACTIONS
            or action[0] in ("moonraker-db", "timezone", "pc-timezone", "fluidd-card", "fluidd-console-filters"))


TZ_NAME = __import__("re").compile(r"^[A-Za-z][A-Za-z0-9_+-]*(/[A-Za-z0-9_+-]+){0,2}$")


def clean_timezone(name):
    """An IANA zone name like Europe/Warsaw from what the PC reports, or None."""
    if not name:
        return None
    name = name.strip().lstrip(":")
    if "zoneinfo/" in name:
        name = name.split("zoneinfo/", 1)[1]
    if name.startswith("/") or not TZ_NAME.match(name):
        return None  # a POSIX rule or a path that is not under zoneinfo
    return name


def pc_timezone():
    """The IANA time zone of the PC the installer runs on, or None."""
    import subprocess
    if os.name == "nt":
        from windows_zones import WINDOWS_TO_IANA
        try:
            name = subprocess.run(["tzutil", "/g"], capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None
        if name.endswith("_dstoff"):
            name = name[:-len("_dstoff")]
        return WINDOWS_TO_IANA.get(name)
    zone = clean_timezone(os.environ.get("TZ", ""))
    if zone:
        return zone
    return clean_timezone(os.path.realpath("/etc/localtime"))


# Fluidd's own default dashboard (QIDI's Fluidd 1.30.5 bundle), used when the printer has none saved yet
FLUIDD_DEFAULT_DASHBOARD = {
    "container1": [{"id": i, "enabled": e, "collapsed": False} for i, e in (
        ("printer-status-card", True), ("box-card", True), ("spoolman-card", False), ("camera-card", True),
        ("toolhead-card", True), ("macros-card", False), ("outputs-card", True), ("runout-sensors-card", False),
        ("printer-limits-card", False), ("retract-card", False))],
    "container2": [{"id": i, "enabled": e, "collapsed": False} for i, e in (
        ("temperature-card", True), ("sensors-card", True), ("console-card", True), ("jobs-card", True),
        ("job-queue-card", False), ("gcode-preview-card", False), ("bed-mesh-card", False))],
}


def fluidd_layouts_with_card(current, card):
    """Fluidd's saved layouts with `card` switched on in every dashboard layout (None: already on)."""
    layouts = json.loads(current) if current else {}
    if not isinstance(layouts, dict):
        layouts = {}
    layouts = json.loads(json.dumps(layouts))
    if not any(name.startswith("dashboard") for name in layouts):
        layouts["dashboard"] = json.loads(json.dumps(FLUIDD_DEFAULT_DASHBOARD))
    changed = False
    for name, layout in layouts.items():
        if not name.startswith("dashboard") or not isinstance(layout, dict):
            continue
        cards = [c for col in layout.values() if isinstance(col, list) for c in col if isinstance(c, dict)]
        found = [c for c in cards if c.get("id") == card]
        if not found:
            last = [col for col in layout.values() if isinstance(col, list)]
            if last:
                last[-1].append({"id": card, "enabled": True, "collapsed": False})
                changed = True
        for c in found:
            if not c.get("enabled"):  # a card the user only collapsed stays as it is
                c["enabled"], c["collapsed"] = True, False
                changed = True
    return layouts if changed else None


def fluidd_console_filters_with(current, wanted):
    """Fluidd's saved console filters plus the `wanted` ones ({"id", "name", "value"}; type "contains", on), or None when all of
    them are already there. A filter with the same id keeps its on/off state and value (also one the user switched off), only its label is refreshed; the user's own filters
    keep their place; a saved value that is not a list of filters is replaced."""
    try:
        saved = json.loads(current) if current else []
    except ValueError:
        saved = []
    filters = [f for f in saved if isinstance(f, dict)] if isinstance(saved, list) else []
    have = {f.get("id") for f in filters}
    names = {w["id"]: w["name"] for w in wanted}
    # a filter we shipped earlier gets the current label; whether it is on, and its value, stay the user's
    filters = [dict(f, name=names[f["id"]]) if f.get("id") in names and f.get("name") != names[f["id"]] else f
               for f in filters]
    added = [{"id": w["id"], "enabled": True, "name": w["name"], "type": "contains", "value": w["value"]}
             for w in wanted if w["id"] not in have]
    if not added and filters == saved:
        return None
    return filters + added


def resolve_action(p, action):
    """Turn an action that depends on the PC or on the printer's current settings into a plain one.

    ["pc-timezone"] -> ["timezone", <the PC's zone>]
    ["fluidd-card", <card>] -> ["moonraker-db", "fluidd", "layout.layouts", <layouts with the card on>]
    ["fluidd-console-filters", <JSON list of {"id","name","value"}>] -> ["moonraker-db", "fluidd", "console.consoleFilters", <filters>]
    None when there is nothing to do (or the PC's zone is not known)."""
    if action[0] == "pc-timezone":
        zone = pc_timezone()
        if zone and hasattr(p, "has_timezone") and not p.has_timezone(zone):
            print("Time zone %s of this PC is not known to the printer - left as it is." % zone)
            zone = None
        return ["timezone", zone] if zone else None
    if action[0] == "fluidd-console-filters":
        current = p.db_value("fluidd", "console.consoleFilters") if hasattr(p, "db_value") else None
        filters = fluidd_console_filters_with(current, json.loads(action[1]))
        return None if filters is None else ["moonraker-db", "fluidd", "console.consoleFilters", json.dumps(filters)]
    if action[0] == "fluidd-card":
        current = p.db_value("fluidd", "layout.layouts") if hasattr(p, "db_value") else None
        layouts = fluidd_layouts_with_card(current, action[1])
        return None if layouts is None else ["moonraker-db", "fluidd", "layout.layouts", json.dumps(layouts)]
    return action


def unfinished_modules(host, backups=BACKUPS, p=None):
    """Modules whose files the newest run put on the printer before it stopped, or that it was itself
    finishing for an earlier run (restarts still owed)."""
    found = host_backups(host, backups, p)
    if not found:
        return set()
    record = json.loads((found[-1] / "install.json").read_text(encoding="utf-8"))
    if record.get("complete", True):
        return set()
    return ({mid for e in record["files"].values() if e.get("installed") for mid in e.get("modules", [])}
            | set(record.get("resumed", [])))


def pending_actions(p, selected, changes, resumed=()):
    """[(module, action)] that still have to run.

    State actions (lock a folder, enable/disable a service, set a Moonraker
    database entry) run only when not already in effect; other actions (daemon-reload, restart a service) only for
    modules whose files change in this run."""
    touched = {mid for _, _, _, mods in changes for mid in mods} | set(resumed)
    out = []
    units = [a[-1] for m in selected for a in m.get("actions", []) if a[:2] in (["systemctl", "enable"], ["systemctl", "disable"])]
    if units and hasattr(p, "prefetch_units"):
        p.prefetch_units(units)  # one command instead of one per service
    for m in selected:
        for action in m.get("actions", []):
            if is_state_action(action):
                action = resolve_action(p, action)
                if action is not None and p.needs(action):
                    out.append((m["id"], action))
            elif m["id"] in touched:
                out.append((m["id"], action))
    return out


# ------------------------------------------------------------------ install / uninstall
def progress(what, n, total):
    """One line that counts up, e.g. "Backup  12/203  [#####-----]"; a new line at the end."""
    if total <= 0:
        return
    width = 30
    done = int(width * n / total)
    end = "\n" if n >= total else ""
    sys.stdout.write("\r%s %4d/%d  [%s%s]%s" % (what, n, total, "#" * done, "-" * (width - done), end))
    sys.stdout.flush()


def do_install(p, selected, changes, host, backups=BACKUPS, actions=None, resumed=None):
    if resumed is None:
        resumed = unfinished_modules(host, backups, p)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = backups / ("printer-%s-%s" % (host.replace(":", "_"), stamp))
    (backup / "files").mkdir(parents=True)
    index = firmware.load_index()["files"]
    record = {"host": host, "printer_id": _printer_id(p), "time": stamp, "version": VERSION,
              "already_ours": getattr(changes, "already_ours", None),
              "modules": [m["id"] for m in selected], "resumed": sorted(resumed),
              "files": {}, "actions": [], "complete": False}
    stock = [path for path, _, kind, _ in changes if kind == "replace" and path in index]
    if stock:
        print("Backup: reading %d original file(s) from QIDI's official package (one pass, can take a minute)..."
              % len(stock), flush=True)
        stock = firmware.extract_many(stock)
    else:
        stock = {}
    stats = p.stat_many([path for path, _, kind, _ in changes if kind != "new"]) if hasattr(p, "stat_many") else None
    for n, (path, new, kind, mods) in enumerate(changes, 1):
        progress("Backup", n, len(changes))
        entry = {"modules": mods, "kind": kind, "new_sha256": sha(new)}
        if kind != "new":
            old = stock[path] if path in stock else p.read(path)
            target = backup / "files" / path.lstrip("/")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(old)
            entry.update(old_sha256=sha(old), stat=stats[path] if stats is not None else p.stat(path))
        record["files"][path] = entry
    (backup / "modules.json").write_text(json.dumps(
        {m["id"]: {k: v for k, v in m["files"].items() if v.get("base") == "printer"} for m in selected},
        indent=1), encoding="utf-8")
    save = lambda: (backup / "install.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    save()
    print("Backup on the PC (%d file(s)): %s" % (len(changes), backup))
    try:
        for n, (path, new, kind, mods) in enumerate(changes, 1):
            progress("Installing", n, len(changes))
            st = record["files"][path].get("stat")
            owner, group, mode = st if st else default_owner(path)
            p.install(new, path, owner, group, mode)
            record["files"][path]["installed"] = True
            save()
        print("Installed %d file(s)" % len(changes))
        # Look again now the files are on the printer: "enable this service" was judged "not there, nothing to do"
        # when the plan was made, before the service file existed.
        fresh = pending_actions(p, selected, changes, resumed)
        actions = fresh if actions is None else list(actions) + [a for a in fresh if a not in actions]
        for mid, action in actions:
            if action[0] == "moonraker-db" and hasattr(p, "db_value"):
                before = p.db_value(action[1], action[2])  # put back exactly this on uninstall
                # nothing there before: the module's factory value if it names one, else remove it again
                action = action[:4] + [before if before is not None else (action[4] if len(action) > 4 else None)]
            if action[0] == "timezone" and hasattr(p, "timezone"):
                action = action[:2] + [p.timezone()]  # the zone before, for uninstall
            if action[0] == "timezone":
                try:
                    p.action(action[:2])
                except InstallError as exc:  # a clock setting is not worth a half-finished install
                    print("Time zone not changed:", str(exc).splitlines()[0])
                    continue
            else:
                p.action(action[:4] if action[0] == "moonraker-db" else action)
            record["actions"].append(action)
            save()
            print("Done:", describe_action(action))
        touched = {mid for _, _, _, mods in changes for mid in mods} | set(resumed)
        restarts = {r for m in selected for r in m.get("restart", []) if m["id"] in touched}
        for name in RESTART_ORDER:
            if name in restarts:
                p.restart(name)
                print("Restarted", name)
        record["complete"] = True
    finally:
        save()
        if not record["complete"] and (resumed or any(e.get("installed") for e in record["files"].values())):
            print("\nNOT FINISHED. Some files are already on the printer, but the services were not restarted.\n"
                  "Do not print yet: run the installer again (it continues where it stopped), or turn the\n"
                  "printer off and on. Backup of this run: %s" % backup)
    print("Done.")
    return backup


# ------------------------------------------------------------------ toolhead check (thr-accel-check)
THR_FILES = ("bootloader.bin", "application.bin", "report.json")
THR_SAVE_DIR = "/home/qidi/printer_data/config/q2_thr_backup"
THR_DOC = "docs/TOOLHEAD_ACCELEROMETER.md"
THR_INTRO = (
    "QIDI's Q2 toolhead firmware has a known bug: the accelerometer delivers about 390 samples a second instead of "
    "1600, so the input shaper calibration sees only part of the vibrations (QIDI_Q2 #39). Most Q2 printers have it.")


def toolhead_check(p, backups=BACKUPS, wait=90, sleep=time.sleep):
    """Run TWEAKED_THR_CHECK SAVE=1 once, print its result, keep the toolhead backup on the PC, remove it from
    the printer. Read only on the toolhead; any problem here is reported and never fails the install."""
    for _ in range(max(1, wait // 3)):
        try:
            if p.http_json("/printer/info")["result"]["state"] == "ready":
                break
        except (InstallError, ValueError, KeyError, TypeError):
            pass
        sleep(3)
    else:
        print("Toolhead check skipped: Klipper is not ready.")
        return None
    if "q2_thr_check" not in p.http_json("/printer/objects/list")["result"]["objects"]:
        print("Toolhead check skipped: TWEAKED_THR_CHECK is not loaded.")
        return None
    print("Toolhead check (read only, about a minute) ...")
    p.gcode("TWEAKED_THR_CHECK SAVE=1")
    result = p.http_json("/printer/objects/query?q2_thr_check")["result"]["status"]["q2_thr_check"]
    if not result.get("done"):
        print("Toolhead check: no result.")
        return None
    for line in result.get("lines", []):
        print("  " + line)
    if result.get("state") == "bug":
        print("  What to do: nothing is required - the printer works as it is. Fixing it means rewriting the "
              "toolhead firmware by hand, at your own risk. Read " + THR_DOC + " first.")
    saved = result.get("saved")
    if not saved:
        return result
    target = Path(backups) / ("toolhead-%s-%s" % (result["bootloader_sha256"][:8], result["application_sha256"][:8]))
    if not all((target / name).is_file() for name in THR_FILES):
        target.mkdir(parents=True, exist_ok=True)
        for name in THR_FILES:
            data = p.read(posixpath.join(saved, name))
            if data is None:
                raise InstallError("toolhead backup incomplete: %s" % name)
            (target / name).write_bytes(data)
        print("  Toolhead backup on the PC:", target)
    else:
        print("  Toolhead backup already on the PC:", target)
    p.remove_tree(saved)
    return result


def toolhead_offer(p, mode="ask", read=input, backups=BACKUPS):
    """The installer's question: check this printer's toolhead? Read only; never fails the install."""
    if mode == "no":
        return None
    print()
    print(THR_INTRO)
    if mode == "ask":
        try:
            answer = read("Check whether this printer has it (read only, about a minute)? [Y/n] ")
        except (EOFError, KeyboardInterrupt):
            return None
        if answer.strip().lower() in ("n", "no"):
            print("Skipped. You can check any time: TWEAKED_THR_CHECK in the Fluidd console (%s)." % THR_DOC)
            return None
    return toolhead_check(p, backups)


def describe_action(action):
    if action[0] == "moonraker-db" and len(action[3]) > 60:
        return "moonraker-db %s %s (%d characters)" % (action[1], action[2], len(action[3]))
    if action[0] == "timezone":
        return "timezone %s" % action[1]
    return " ".join(str(a) for a in action[:4] if a is not None)


def undo_action(action):
    if action[0] == "moonraker-db":
        # 5th element: the value to put back on uninstall; None = there was none, so remove it again
        if len(action) > 4:
            return action[:3] + [action[4]] if action[4] is not None else ["moonraker-db-delete"] + action[1:3]
        return None
    if action[0] == "timezone":
        return ["timezone", action[2]] if len(action) > 2 and action[2] else None
    for key, fn in UNDO_ACTIONS.items():
        if tuple(action[:2]) == key:
            return fn(action)
    return None


def _printer_id(p):
    get = getattr(p, "printer_id", None)
    try:
        return get() if get else None
    except Exception:  # an ID is a help, never a reason to stop
        return None


def host_backups(host, backups=BACKUPS, p=None):
    """This printer's backup folders, oldest first - whichever address (home network, Tailscale) was used.

    A backup belongs to the printer when it carries the same printer ID. Older backups (no ID yet) belong to
    it when they were made over the same address, or over an address whose saved SSH key is this printer's."""
    pid = _printer_id(p)
    known_as = getattr(p, "known_as", None)
    found = []
    for b in backups.glob("printer-*-*"):
        try:
            record = json.loads((b / "install.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        other = record.get("host") or b.name[len("printer-"):].rsplit("-", 2)[0]
        if pid and record.get("printer_id"):
            mine = record["printer_id"] == pid
        elif other.replace(":", "_") == host.replace(":", "_"):
            mine = True
        else:
            try:
                mine = bool(known_as and known_as(other))
            except Exception:
                mine = False
        if mine:
            found.append((record.get("time", ""), b.name, b))
    return [b for _, _, b in sorted(found)]


def is_first_install(record):
    """A run on a printer with QIDI's files (fresh or reflashed): it changed files and none was ours already.

    Runs record how many of the modules' files were already our version; a run that only added new modules
    to an installed printer is therefore not mistaken for a first install. Records without that number
    (1.0) are judged by their own files: no "upgrade" among them."""
    kinds = [e.get("kind") for e in record.get("files", {}).values() if e.get("installed")]
    if not kinds or "upgrade" in kinds:
        return False
    already = record.get("already_ours")
    return already is None or already == 0


def merged_record(found):
    """One uninstall plan from the backups of a printer (oldest first).

    Backups older than the newest first install (e.g. from before a reflash) no longer describe the
    printer and are left out. Each file goes back to what was there before OUR FIRST change of it
    (the oldest backup that installed it); "changed since install" is judged against our latest
    version (the newest one). Config files are cleaned of the edits of every module that changed them,
    each with its newest edits (also a module left out of a later run). Actions are undone
    newest run first. Returns (files, actions, complete) - complete is False when no first install
    is among the backups (the originals may then be missing)."""
    records = [(b, json.loads((b / "install.json").read_text(encoding="utf-8"))) for b in found]
    start, complete = 0, False
    for i in range(len(records) - 1, -1, -1):
        if is_first_install(records[i][1]):
            start, complete = i, True
            break
    files, actions = {}, []
    for backup, record in records[start:]:
        for path, entry in record["files"].items():
            if not entry.get("installed"):
                continue
            edits = dict(files[path]["_edits"]) if path in files else {}
            if entry["kind"] == "config":
                edits.update((mid, backup) for mid in entry.get("modules", []))
            if path not in files:
                files[path] = dict(entry, _backup=backup, _edits=edits)
            else:
                first = files[path]
                first["new_sha256"] = entry["new_sha256"]
                first["_edits"] = edits
                if entry["kind"] == "config" or first["kind"] == "config":
                    files[path] = dict(entry, _backup=backup, kind="config", _edits=edits)
        actions.append(record.get("actions", []))
    return files, [a for run in reversed(actions) for a in reversed(run)], complete


def do_uninstall(p, backup):
    found = backup if isinstance(backup, list) else [backup]
    files, all_actions, complete = merged_record(found)
    if not complete:
        print("Note: no backup of a first install of this printer was found (lost, or made in another project\n"
              "folder). Files that were already ours before the oldest backup cannot be put back from it;\n"
              "afterwards run: py tools/install.py uninstall --from-stock --host <IP>  to be sure.")
    for path, entry in sorted(files.items()):
        backup = entry["_backup"]
        if entry["kind"] != "config" and p.sha(path) not in (entry["new_sha256"], None):
            print("  left alone (changed since install):", path)
            continue
        if entry["kind"] == "config":
            # take our edits out of the file as it is now (keeps calibration saved since)
            edits = entry.get("_edits") or {mid: backup for mid in entry["modules"]}
            mods = [{"id": mid, "files": {path: json.loads((b / "modules.json").read_text())[mid][path]}}
                    for mid, b in edits.items()]  # in the order the modules were first installed
            current = p.read(path)
            try:
                old = apply_config_edits(current, mods, path, reverse=True)
            except build.BuildError:
                print("  left alone (our edits not found):", path)
                continue
            owner, group, mode = entry["stat"]
            p.install(old, path, owner, group, mode)
        elif "old_sha256" in entry:
            old = (backup / "files" / path.lstrip("/")).read_bytes()
            owner, group, mode = entry["stat"]
            p.install(old, path, owner, group, mode)
        else:
            p.remove(path)
        print("  restored:", path)
    for action in all_actions:
        undo = undo_action(action)
        if undo:
            p.action(undo, check=False)
    p.action(["systemctl", "daemon-reload"], check=False)
    for name in RESTART_ORDER:
        p.restart(name)
    print("Uninstalled using %d backup(s): %s" % (len(found), ", ".join(b.name for b in found)))


def do_uninstall_stock(p, selected):
    """Uninstall without a PC backup: put QIDI's originals from the official package back.

    Only files that are a version of ours are touched; anything else is reported and left."""
    files, owners = build.build(selected)
    index = firmware.load_index()["files"]
    history = load_history()
    by_id = {m["id"]: m for m in selected}
    ours = {path: {sha(data)} | set(history.get(path, []))
            for path, data in files.items()}
    for m in selected:
        g = m.get("generate")
        if g and g.get("kind") == "dns-fallback":  # QIDI's own file: put its line back, never remove it
            data = p.read(g["path"])
            old = dns_fallback_file(data, reverse=True) if data is not None else None
            if old is not None and old != data:
                p.install(old, g["path"], *(p.stat(g["path"]) or default_owner(g["path"])))
                print("  restored:", g["path"])
        elif g:
            files[g["path"]] = None
            owners[g["path"]] = [m["id"]]
    shas = p.sha_many(sorted(files)) if hasattr(p, "sha_many") else {f: p.sha(f) for f in files}
    left = []
    for path in sorted(files):
        mods = [by_id[mid] for mid in owners[path]]
        current = shas.get(path)
        if current is None:
            continue
        if any(m.get("files", {}).get(path, {}).get("base") == "printer" for m in mods):
            data = p.read(path)
            stripped = strip_config_edits(data, mods, path)
            if stripped != data:
                st = p.stat(path) or default_owner(path)
                p.install(stripped, path, *st)
                print("  restored:", path)
            continue
        if path in index:
            if current == index[path]["sha256"]:
                continue
            if current in ours.get(path, set()):
                st = p.stat(path) or default_owner(path)
                p.install(firmware.extract(path), path, *st)
                print("  original back:", path)
            else:
                left.append(path)
        else:
            if files[path] is None or current in ours.get(path, set()):
                p.remove(path)
                print("  removed:", path)
            else:
                left.append(path)
    for m in reversed(selected):
        for action in reversed(m.get("actions", [])):
            undo = undo_action(action)
            if undo:
                p.action(undo, check=False)
    p.action(["systemctl", "daemon-reload"], check=False)
    for name in RESTART_ORDER:
        p.restart(name)
    for path in left:
        print("  left alone (not ours):", path)
    print("Uninstalled using the official 01.01.02.04 originals.")


# ------------------------------------------------------------------ main
def remove_notify(p):
    try:
        notify_setup.remove(p)
    except Exception as exc:  # report, do not fail the uninstall
        print("Phone notification settings not removed:", exc)


def remove_tailscale(p):
    try:
        tailscale_setup.uninstall(p)
    except Exception as exc:  # the files are already back; report, do not fail the uninstall
        print("Tailscale not removed:", exc)


def show_plan(p, selected, host):
    """Print what would change; returns (changes, resumed, actions)."""
    changes = plan(p, selected)
    resumed = unfinished_modules(host, BACKUPS, p)
    if resumed:
        print("The last install stopped before the end - its restarts are done in this run.")
    actions = pending_actions(p, selected, changes, resumed)
    for path, _, kind, mods in changes:
        print("  %-9s %s  (%s)" % (kind, path, ", ".join(mods)))
    for mid, action in actions:
        print("  action    %s  (%s)" % (describe_action(action), mid))
    print("%d file(s) to change, %d action(s), %d module(s)." % (len(changes), len(actions), len(selected)))
    return changes, resumed, actions


def install_round(p, selected, host):
    """Install what is still missing for this selection (the question was the confirmation). True if anything was done."""
    changes, resumed, actions = show_plan(p, selected, host)
    if not (changes or actions or resumed):
        return False
    do_install(p, selected, changes, host, actions=actions, resumed=resumed)
    return True


def configure_notify(p, host):
    try:
        notify_setup.configure(p, "yes", host=host)
    except Exception as exc:  # optional extra: never fail the install because of it
        print("Phone notifications step skipped:", exc)


def _ask_yes_no(question):
    try:
        return input("%s [y/N] " % question).strip().lower() in ("y", "yes", "t", "tak")
    except EOFError:
        return False


def optional_modules(selected, args, interactive, ask, round_fn, notify_fn, notify_wanted=None):
    """After the main install: every optional module (marked "default": false) that is not installed yet is offered one by
    one - question, then yes = installed right away, no = next question. Without a window to ask in (a scripted run) none is
    offered. Phone notifications keep their own question text and --notify; they are configured right after their install.
    Returns the selection including what was added."""
    notify_wanted = notify_wanted or notify_setup.wanted
    chosen = {m["id"] for m in selected if not m.get("default", True)}
    for m in build.load_modules():
        mid = m["id"]
        if m.get("default", True) or mid in args.skip or mid in chosen:
            continue
        if mid == "phone-notifications":
            mode = args.notify if (args.notify != "ask" or interactive) else "no"
            if not notify_wanted(mode):
                continue
        else:
            if not interactive:
                continue
            title = m.get("title", mid)
            if not ask("Install the optional module %s - %s?" % (mid, title)):
                continue
        trial = select(args.skip, sorted(chosen | {mid}))
        if not round_fn(trial):
            print("  %s: nothing to do (already installed)." % mid)
        chosen.add(mid)
        selected = trial
        if mid == "phone-notifications":
            notify_fn()
    return selected


LOGS = REPO / "logs"


class _Tee(io.TextIOBase):
    """Everything printed also goes to a log file, so a message survives a closed window."""
    def __init__(self, stream, log):
        self.stream, self.log = stream, log

    def write(self, text):
        self.stream.write(text)
        if text.startswith("\r") and not text.endswith("\n"):
            return len(text)  # a progress line that is still counting: only its last state goes in the log
        try:
            self.log.write(text)
            self.log.flush()
        except (OSError, ValueError):
            pass
        return len(text)

    def flush(self):
        self.stream.flush()


def _start_log(command):
    try:
        LOGS.mkdir(exist_ok=True)
        path = LOGS / ("%s-%s.txt" % (command, time.strftime("%Y%m%d-%H%M%S")))
        log = open(path, "w", encoding="utf-8")
    except OSError:
        return None
    sys.stdout = _Tee(sys.stdout, log)
    sys.stderr = _Tee(sys.stderr, log)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description="Install QIDI Q2 02.04 Tweaked on the printer.")
    ap.add_argument("command", choices=("plan", "install", "uninstall"))
    ap.add_argument("--host", required=True, help="printer IP address")
    ap.add_argument("--user", default="mks")
    ap.add_argument("--port", type=int, default=22)
    ap.add_argument("--skip", action="append", default=[], help="leave this module out")
    ap.add_argument("--with", dest="extra", action="append", default=[],
                    help="also install an optional module that is off by default (e.g. journal-retention)")
    ap.add_argument("--tailscale", choices=("ask", "yes", "no"), default="ask",
                    help="install: optional Tailscale for remote access (ask = ask in the window)")
    ap.add_argument("--toolhead", choices=("ask", "yes", "no"), default="ask",
                    help="install: check the toolhead accelerometer bug, read only (ask = ask in the window)")
    ap.add_argument("--notify", choices=("ask", "yes", "no"), default="ask",
                    help="install: optional phone notifications through ntfy (ask = ask in the window)")
    ap.add_argument("--orca", choices=("ask", "yes", "no"), default="ask",
                    help="install: add the project's OrcaSlicer profiles on this computer (ask = ask in the window)")
    ap.add_argument("--rehash", action="store_true",
                    help="hash every file on the printer again this time (normally only files that changed are hashed)")
    ap.add_argument("--backup", help="uninstall: backup folder (default: newest for this printer)")
    ap.add_argument("--from-stock", action="store_true",
                    help="uninstall without a PC backup, using the originals from the official 02.04 package")
    args = ap.parse_args(argv)
    log_path = _start_log(args.command) if argv is None else None
    print("QIDI Q2 02.04 Tweaked", VERSION)
    if log_path:
        print("Log (no password in it):", log_path)
    p = None
    try:
        p = SSHPrinter.open(args.host, args.user, args.port)
        if isinstance(p, SSHPrinter):
            p.use_hash_cache(HashCache(hash_cache_file(_printer_id(p), args.host)), rehash=args.rehash)
        check_printer(p, require_idle=args.command != "plan")
        if args.command == "uninstall":
            if args.from_stock:
                remove_notify(p)
                do_uninstall_stock(p, select([], [m["id"] for m in build.load_modules()]))
                remove_tailscale(p)
                return 0
            found = [Path(args.backup)] if args.backup else host_backups(args.host, BACKUPS, p)
            if not found:
                raise InstallError("no backup for this printer in %s - try: uninstall --from-stock" % BACKUPS)
            remove_notify(p)
            do_uninstall(p, found)
            remove_tailscale(p)
            return 0
        extra = list(args.extra)
        if args.notify == "yes" and "phone-notifications" not in extra:
            extra.append("phone-notifications")
        selected = select(args.skip, extra)
        changes, resumed, actions = show_plan(p, selected, args.host)
        if args.command == "plan":
            return 0
        if changes or actions or resumed:
            if input("Install now? Type yes: ").strip().lower() != "yes":
                print("Nothing changed.")
                return 0
            do_install(p, selected, changes, args.host, actions=actions, resumed=resumed)
        if any(m["id"] == "phone-notifications" for m in selected):
            configure_notify(p, args.host)  # --with / --notify yes: set it up right away
        # The optional extras, one after the other: question -> yes -> done (no -> next question).
        interactive = sys.stdin.isatty()
        selected = optional_modules(
            selected, args, interactive, _ask_yes_no,
            lambda sel: install_round(p, sel, args.host),
            lambda: configure_notify(p, args.host))
        if any(m["id"] == "thr-accel-check" for m in selected):
            mode = args.toolhead
            if mode == "ask" and not sys.stdin.isatty():
                mode = "no"  # no one to ask (scripted run)
            try:
                toolhead_offer(p, mode)
            except Exception as exc:  # a check, never a reason to fail the install
                print("Toolhead check skipped:", str(exc).splitlines()[0] if str(exc) else exc)
        mode = args.tailscale
        if mode == "ask" and not sys.stdin.isatty():
            mode = "no"  # no one to ask (scripted run)
        try:
            tailscale_setup.offer(p, mode)
        except Exception as exc:  # optional extra: never fail the install because of it
            print("Tailscale step skipped:", exc)
        mode = args.orca
        if mode == "ask" and not sys.stdin.isatty():
            mode = "no"
        try:
            orca_profiles.offer(mode)
        except Exception as exc:  # optional extra on the PC: never fail the install because of it
            print("OrcaSlicer step skipped:", exc)
        return 0
    except (InstallError, build.BuildError) as exc:
        print("STOPPED:", exc)
        return 1
    except Exception:
        import traceback
        traceback.print_exc()
        print("STOPPED: unexpected error (details above and in the log).")
        return 1
    finally:
        if p is not None:
            p.close()


if __name__ == "__main__":
    sys.exit(main())
