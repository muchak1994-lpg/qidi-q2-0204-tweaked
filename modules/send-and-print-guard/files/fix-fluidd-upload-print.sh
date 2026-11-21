#!/bin/sh
exec python3 -I -B - <<'Q2_SEND_PRINT_GUARD'
# SPDX-License-Identifier: GPL-3.0-only
"""Timer payload: keeps Fluidd's "Upload & Print" working. It looks for the bug itself, not for checksums.

Fluidd's Upload & Print button uploads the file but then does not start the print (a missing branch in the upload code).
This script looks in the active Fluidd bundle for exactly that code:
  - the repaired code is there          -> nothing to do
  - the broken code is there, once      -> repair it (only while the printer is idle: no print, no motion, heaters off)
  - anything else (other Fluidd version, two matches, no single bundle) -> nothing is changed
Nothing is changed whenever it is not certain, and such a run still ends OK. It never starts a print.
"""
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(os.environ.get('Q2_FLUIDD_ROOT', '/home/qidi/fluidd'))
BASE = os.environ.get('Q2_MOONRAKER', 'http://127.0.0.1:7125')
BROKEN = (b'this.$store.getters["files/getCanPrint"]("gcodes",t)'
          b'&&(this.FileSystemSelectLineDialogState={open:!0,filename:t})}}saveConfigAndRestart')
FIXED = (b'this.$store.getters["files/getCanPrint"]("gcodes",t)'
         b'&&(this.FileSystemSelectLineDialogState={open:!0,filename:t})}'
         b'else this.uploadFile(e,"","gcodes",!0)}saveConfigAndRestart')


def query(path):
    with urlopen(BASE + path, timeout=5) as r:
        return json.load(r)['result']['status']


def printer_idle():
    """None when the printer is idle and still, otherwise the reason to wait."""
    s = query('/printer/objects/query?webhooks&print_stats&pause_resume&virtual_sdcard&motion_report&heaters')
    if (s['webhooks']['state'] != 'ready' or s['print_stats']['state'] not in ('standby', 'complete', 'cancelled')
            or s['pause_resume']['is_paused'] or s['virtual_sdcard']['is_active']):
        return 'printer busy'
    for key in ('live_velocity', 'live_extruder_velocity'):
        value = float(s['motion_report'][key])
        if not math.isfinite(value) or abs(value) > 1e-5:
            return 'printer moving'
    names = s['heaters']['available_heaters']
    if names:
        heaters = query('/printer/objects/query?' + urlencode([(n, '') for n in names]))
        if any(float(heaters[n]['target']) != 0 for n in names):
            return 'heater target active'
    return None


def main():
    index = ROOT / 'index.html'
    html = index.read_text() if index.is_file() else ''
    matches = re.findall(r'src="([^"]*index-[^"]+\.js)"', html)
    if len(matches) != 1:
        print('No single active Fluidd bundle; nothing changed')
        return
    target = ROOT / matches[0].lstrip('./')
    if target.is_symlink() or not target.is_file() or ROOT.resolve() not in target.resolve().parents:
        print('Active bundle is not a plain file in the Fluidd folder; nothing changed')
        return
    before = target.read_bytes()
    if FIXED in before:
        print('Already fixed; no changes')
        return
    if before.count(BROKEN) != 1:
        print('The Upload & Print code is not the known broken one (other Fluidd version?); nothing changed')
        return
    try:
        reason = printer_idle()
    except Exception as error:
        reason = 'Moonraker did not answer (%s)' % error
    if reason:
        print('Repair deferred: ' + reason)
        return
    after = before.replace(BROKEN, FIXED, 1)
    st = target.stat()
    fd, temporary = tempfile.mkstemp(prefix='.q2-send-print-', dir=str(target.parent))
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(after)
            os.fchmod(f.fileno(), st.st_mode & 0o7777)
            os.fchown(f.fileno(), st.st_uid, st.st_gid)
            f.flush()
            os.fsync(f.fileno())
        if target.read_bytes() != before:
            raise RuntimeError('Bundle changed while preparing the repair')
        os.replace(temporary, str(target))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print('Send & Print fixed; no print started')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('STOP: ' + str(error), file=sys.stderr)
        sys.exit(1)

Q2_SEND_PRINT_GUARD
