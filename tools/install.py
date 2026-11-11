#!/usr/bin/env python3
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
import io
import json
import posixpath
import shlex
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402
import firmware  # noqa: E402

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


class InstallError(Exception):
    pass


# ------------------------------------------------------------------ printer
class SSHPrinter:
    """Operations on the real printer over SSH. sudo uses the SSH password."""

    def __init__(self, host, user, password, port=22):
        import printer
        self.client = printer.connect(host, user, port, password=password)
        self.password = password
        self.sftp = self.client.open_sftp()
        self.staging = None

    def _run(self, command, sudo=False, check=True):
        if sudo:
            command = "sudo -S -p '' sh -c %s" % shlex.quote(command)
        stdin, out, err = self.client.exec_command(command, timeout=900)
        if sudo:
            stdin.write(self.password + "\n")
            stdin.flush()
        data = out.read()
        error = err.read().decode("utf-8", "replace")
        code = out.channel.recv_exit_status()
        if check and code != 0:
            raise InstallError("printer command failed (%d): %s\n%s" % (code, command[:160], error.strip()[:400]))
        return data

    def sha(self, path):
        out = self._run("sha256sum %s 2>/dev/null || true" % shlex.quote(path), sudo=True).decode()
        return out.split()[0] if out.strip() else None

    def sha_many(self, paths):
        """{path: sha256 or None} in one round trip."""
        result = {p: None for p in paths}
        paths = list(paths)
        for i in range(0, len(paths), 200):
            chunk = " ".join(shlex.quote(p) for p in paths[i:i + 200])
            out = self._run("sha256sum %s 2>/dev/null || true" % chunk, sudo=True).decode()
            for line in out.splitlines():
                digest, _, path = line.partition("  ")
                if path in result:
                    result[path] = digest
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
        self._run("mkdir -p %s && install -o %s -g %s -m %s %s %s && rm -f %s" % (
            shlex.quote(posixpath.dirname(path)), owner, group, mode, tmp, shlex.quote(path), tmp), sudo=True)
        if self.sha(path) != sha(data):
            raise InstallError("verification failed after writing " + path)

    def remove(self, path):
        self._run("rm -f %s" % shlex.quote(path), sudo=True)

    def action(self, argv, check=True):
        self._run(" ".join(shlex.quote(a) for a in argv), sudo=True, check=check)

    def needs(self, argv):
        """False when a state-type action is already in effect (so it is skipped)."""
        if argv[:2] == ["chattr", "+i"]:
            out = self._run("lsattr -d %s 2>/dev/null || true" % shlex.quote(argv[2]), sudo=True).decode()
            return not out.strip() or "i" not in out.split()[0]
        if argv[:2] == ["systemctl", "enable"] or argv[:2] == ["systemctl", "disable"]:
            unit = argv[-1]
            out = self._run("systemctl is-enabled %s 2>/dev/null; systemctl is-active %s 2>/dev/null; true"
                            % (shlex.quote(unit), shlex.quote(unit)), sudo=True).decode().split()
            enabled, active = (out + ["", ""])[:2]
            if argv[1] == "enable":
                return not (enabled == "enabled" and active == "active")
            return not (enabled in ("disabled", "masked", "") and active != "active")
        return True

    def restart(self, name):
        self._run("systemctl restart %s" % SERVICES[name], sudo=True)

    def http_json(self, url_path):
        return json.loads(self._run("curl -s -m 10 'http://127.0.0.1:7125%s'" % url_path))

    def close(self):
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
                   "and run the installer again.")


def plan(p, selected, built=None):
    """[(path, new_bytes, kind, modules)] that must change on the printer."""
    files, owners = built or build.build(selected)
    index = firmware.load_index()["files"]
    history = load_history()
    by_id = {m["id"]: m for m in selected}
    changes, problems = [], []
    shas = p.sha_many(sorted(files)) if hasattr(p, "sha_many") else {f: p.sha(f) for f in files}
    for path in sorted(files):
        mods = [by_id[mid] for mid in owners[path]]
        if any(m.get("files", {}).get(path, {}).get("base") == "printer" for m in mods):
            current = p.read(path)
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
            continue
        new = files[path]
        current = shas[path]
        if current == sha(new):
            continue
        if current is None:
            changes.append((path, new, "new", owners[path]))
        elif current == index.get(path, {}).get("sha256"):
            changes.append((path, new, "replace", owners[path]))
        elif current in history.get(path, []):
            changes.append((path, new, "upgrade", owners[path]))  # an earlier version of ours
        else:
            problems.append("%s is neither the 02.04 original nor a version of ours" % path)
    for m in selected:
        g = m.get("generate")
        if g and g.get("kind") == "ethernet-mac":
            new = ethernet_mac_file(p)
            current = p.sha(g["path"])
            if current != sha(new):
                changes.append((g["path"], new, "new" if current is None else "generated", [m["id"]]))
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


def default_owner(path):
    if path.startswith(("/etc/", "/usr/", "/root/")):
        return "root", "root", ("755" if path.endswith((".sh", ".so")) or path.endswith("/algo_app/main") else "644")
    return "qidi", "netdev", ("755" if path.endswith(".sh") else "644")


STATE_ACTIONS = (("chattr", "+i"), ("systemctl", "enable"), ("systemctl", "disable"))


def pending_actions(p, selected, changes):
    """[(module, action)] that still have to run.

    State actions (lock a folder, enable/disable a service) run only when not
    already in effect; other actions (daemon-reload, restart a service) only for
    modules whose files change in this run."""
    touched = {mid for _, _, _, mods in changes for mid in mods}
    out = []
    for m in selected:
        for action in m.get("actions", []):
            if tuple(action[:2]) in STATE_ACTIONS:
                if p.needs(action):
                    out.append((m["id"], action))
            elif m["id"] in touched:
                out.append((m["id"], action))
    return out


# ------------------------------------------------------------------ install / uninstall
def do_install(p, selected, changes, host, backups=BACKUPS, actions=None):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = backups / ("printer-%s-%s" % (host.replace(":", "_"), stamp))
    (backup / "files").mkdir(parents=True)
    index = firmware.load_index()["files"]
    record = {"host": host, "time": stamp, "version": VERSION, "modules": [m["id"] for m in selected],
              "files": {}, "actions": [], "complete": False}
    for path, new, kind, mods in changes:
        entry = {"modules": mods, "kind": kind, "new_sha256": sha(new)}
        if kind != "new":
            old = firmware.extract(path) if kind == "replace" and path in index else p.read(path)
            target = backup / "files" / path.lstrip("/")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(old)
            entry.update(old_sha256=sha(old), stat=p.stat(path))
        record["files"][path] = entry
    (backup / "modules.json").write_text(json.dumps(
        {m["id"]: {k: v for k, v in m["files"].items() if v.get("base") == "printer"} for m in selected},
        indent=1), encoding="utf-8")
    save = lambda: (backup / "install.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    save()
    print("Backup on the PC (%d file(s)): %s" % (len(changes), backup))
    try:
        for path, new, kind, mods in changes:
            st = record["files"][path].get("stat")
            owner, group, mode = st if st else default_owner(path)
            p.install(new, path, owner, group, mode)
            record["files"][path]["installed"] = True
            save()
        print("Installed %d file(s)" % len(changes))
        if actions is None:
            actions = pending_actions(p, selected, changes)
        for mid, action in actions:
            p.action(action)
            record["actions"].append(action)
            save()
            print("Done:", " ".join(action))
        touched = {mid for _, _, _, mods in changes for mid in mods}
        restarts = {r for m in selected for r in m.get("restart", []) if m["id"] in touched}
        for name in RESTART_ORDER:
            if name in restarts:
                p.restart(name)
                print("Restarted", name)
        record["complete"] = True
    finally:
        save()
    print("Done.")
    return backup


def undo_action(action):
    for key, fn in UNDO_ACTIONS.items():
        if tuple(action[:2]) == key:
            return fn(action)
    return None


def do_uninstall(p, backup):
    record = json.loads((backup / "install.json").read_text(encoding="utf-8"))
    for path, entry in sorted(record["files"].items()):
        if not entry.get("installed"):
            continue
        if entry["kind"] != "config" and p.sha(path) not in (entry["new_sha256"], None):
            print("  left alone (changed since install):", path)
            continue
        if entry["kind"] == "config":
            # take our edits out of the file as it is now (keeps calibration saved since)
            mods = [{"id": mid, "files": {path: json.loads((backup / "modules.json").read_text())[mid][path]}}
                    for mid in entry["modules"]]
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
    for action in reversed(record.get("actions", [])):
        undo = undo_action(action)
        if undo:
            p.action(undo, check=False)
    p.action(["systemctl", "daemon-reload"], check=False)
    for name in RESTART_ORDER:
        p.restart(name)
    print("Uninstalled using", backup)


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
        if g:
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
def main(argv=None):
    ap = argparse.ArgumentParser(description="Install QIDI Q2 02.04 Tweaked on the printer.")
    ap.add_argument("command", choices=("plan", "install", "uninstall"))
    ap.add_argument("--host", required=True, help="printer IP address")
    ap.add_argument("--user", default="mks")
    ap.add_argument("--port", type=int, default=22)
    ap.add_argument("--skip", action="append", default=[], help="leave this module out")
    ap.add_argument("--with", dest="extra", action="append", default=[],
                    help="also install an optional module that is off by default (e.g. journal-retention)")
    ap.add_argument("--backup", help="uninstall: backup folder (default: newest for this printer)")
    ap.add_argument("--from-stock", action="store_true",
                    help="uninstall without a PC backup, using the originals from the official 02.04 package")
    args = ap.parse_args(argv)
    print("QIDI Q2 02.04 Tweaked", VERSION)
    password = getpass.getpass("SSH password for %s@%s: " % (args.user, args.host))
    p = None
    try:
        p = SSHPrinter(args.host, args.user, password, args.port)
        check_printer(p, require_idle=args.command != "plan")
        if args.command == "uninstall":
            if args.from_stock:
                do_uninstall_stock(p, select([], [m["id"] for m in build.load_modules()]))
                return 0
            found = [Path(args.backup)] if args.backup else \
                sorted(BACKUPS.glob("printer-%s-*" % args.host.replace(":", "_")))
            if not found:
                raise InstallError("no backup for this printer in %s - try: uninstall --from-stock" % BACKUPS)
            do_uninstall(p, found[-1])
            return 0
        selected = select(args.skip, args.extra)
        changes = plan(p, selected)
        actions = pending_actions(p, selected, changes)
        for path, _, kind, mods in changes:
            print("  %-9s %s  (%s)" % (kind, path, ", ".join(mods)))
        for mid, action in actions:
            print("  action    %s  (%s)" % (" ".join(action), mid))
        print("%d file(s) to change, %d action(s), %d module(s)." % (len(changes), len(actions), len(selected)))
        if args.command == "plan" or not (changes or actions):
            return 0
        if input("Install now? Type yes: ").strip().lower() != "yes":
            print("Nothing changed.")
            return 0
        do_install(p, selected, changes, args.host, actions=actions)
        return 0
    except (InstallError, build.BuildError) as exc:
        print("STOPPED:", exc)
        return 1
    finally:
        if p is not None:
            p.close()


if __name__ == "__main__":
    sys.exit(main())
