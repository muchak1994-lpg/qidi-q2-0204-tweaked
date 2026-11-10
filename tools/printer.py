#!/usr/bin/env python3
"""QIDI Q2 02.04 Tweaked - read-only printer check.

    python tools/printer.py check --host 192.168.1.50

Connects over SSH (user "mks" by default; you type the password, it is not
stored), and compares the printer's files with the official 01.01.02.04
package prepared by `tools/firmware.py fetch`:

* the firmware manifest must be the 01.01.02.04 one, otherwise nothing else
  in this project will touch the printer;
* every Klipper and screen-program file is reported as original, changed
  (by an earlier modification - ours or someone else's) or not part of 02.04.

It changes nothing on the printer and leaves no files there.
Needs: pip install -r requirements.txt  (paramiko)
"""
import argparse
import getpass
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import firmware  # noqa: E402

MANIFEST_PATH = "/home/qidi/update/firmware_manifest.json"
CHECK_ROOTS = ("/home/qidi/klipper/klippy", "/home/qidi/QIDI_Client/bin")


def connect(host, user, port=22, password=None):
    try:
        import paramiko
    except ImportError:
        sys.exit("paramiko is missing. Run:  py -m pip install -r requirements.txt")
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    known = Path(__file__).resolve().parent.parent / "work" / "known_hosts"
    known.parent.mkdir(parents=True, exist_ok=True)
    if known.is_file():
        client.load_host_keys(str(known))
    client.set_missing_host_key_policy(_AskHostKey(known))
    if password is None:
        password = getpass.getpass("SSH password for %s@%s: " % (user, host))
    client.connect(host, port=port, username=user, password=password,
                   timeout=15, allow_agent=False, look_for_keys=False)
    return client


class _AskHostKey:
    """First connection: show the printer's key fingerprint and remember it."""

    def __init__(self, path):
        self.path = path

    def missing_host_key(self, client, hostname, key):
        import paramiko
        fp = key.get_fingerprint().hex(":")
        print("First connection to %s. Key %s %s" % (hostname, key.get_name(), fp))
        if input("Is this your printer? [y/N] ").strip().lower() != "y":
            raise paramiko.SSHException("host key not accepted")
        client.get_host_keys().add(hostname, key.get_name(), key)
        client.save_host_keys(str(self.path))


def run(client, command):
    _, out, err = client.exec_command(command, timeout=120)
    data = out.read().decode("utf-8", "replace")
    code = out.channel.recv_exit_status()
    return code, data, err.read().decode("utf-8", "replace")


def remote_hashes(client, roots):
    quoted = " ".join("'%s'" % r for r in roots)
    code, out, err = run(client, "find %s -type f -print0 | xargs -0 sha256sum" % quoted)
    hashes = {}
    for line in out.splitlines():
        digest, _, path = line.partition("  ")
        if len(digest) == 64:
            hashes[path] = digest
    return hashes


def classify(index_files, printer_files, roots):
    stock = {p: e["sha256"] for p, e in index_files.items()
             if any(p == r or p.startswith(r + "/") for r in roots)}
    report = {"original": [], "changed": [], "missing": [], "extra": []}
    for path, digest in sorted(stock.items()):
        if path not in printer_files:
            report["missing"].append(path)
        elif printer_files[path] == digest:
            report["original"].append(path)
        else:
            report["changed"].append(path)
    for path in sorted(printer_files):
        if path not in stock and not path.endswith((".pyc", ".pyo")):
            report["extra"].append(path)
    return report


def cmd_check(args):
    index = firmware.load_index()
    client = connect(args.host, args.user, args.port)
    try:
        code, out, _ = run(client, "sha256sum %s" % MANIFEST_PATH)
        digest = out.split()[0] if out else ""
        if digest != firmware.MANIFEST_SHA256:
            _, text, _ = run(client, "cat %s" % MANIFEST_PATH)
            print("This printer does not report firmware 01.01.02.04:")
            print(text.strip() or "(no firmware manifest found)")
            print("This project only works on 01.01.02.04 and will not change this printer.")
            return 2
        print("Firmware: 01.01.02.04 (manifest matches the official package)")
        printer_files = remote_hashes(client, CHECK_ROOTS)
    finally:
        client.close()
    report = classify(index["files"], printer_files, CHECK_ROOTS)
    print("Klipper and screen program, compared with the official package:")
    print("  original: %d   changed: %d   missing: %d   not part of 02.04: %d"
          % tuple(len(report[k]) for k in ("original", "changed", "missing", "extra")))
    for key, label in (("changed", "changed"), ("missing", "missing"), ("extra", "not in 02.04")):
        for path in report[key]:
            print("  %-13s %s" % (label, path))
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
        print("Saved:", args.json)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only check of a QIDI Q2 against the official 01.01.02.04 files.")
    parser.add_argument("command", choices=("check",))
    parser.add_argument("--host", required=True, help="printer IP address")
    parser.add_argument("--user", default="mks")
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--json", help="also save the report to this file")
    args = parser.parse_args(argv)
    sys.exit(cmd_check(args))


if __name__ == "__main__":
    main()
