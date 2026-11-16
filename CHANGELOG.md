# Changelog

## Unreleased
- From reviewing Valve-Oil's (thelegendtubaguy) Max 4 findings and QIDI_Q2 issues against 02.04:
  - `adb-root-shell-off`: QIDI's ADB service (root shell without a password over the network on the Max 4) is
    turned off; skipped when the printer has no such service. Installer: enabling/disabling a service the printer
    does not have is now skipped instead of failing.
  - `qidi-tuning-calm`: QIDI's CPU tuning script ran again every ~3 s forever; now once a minute.
  - `box-homing-timeout` (optional, `--with box-homing-timeout`): 3+ QIDI Boxes - "Communication timeout during
    homing" on tool changes (QIDI_Q2 #33); 250 ms instead of 50 ms only for homing that involves a Box board.
- Fixes from an independent audit of the changes since 1.0 (16.11.2026):
  - Uninstall uses **all** backups of the printer, not only the newest: a later small run (or an update) no longer
    hides the originals saved by the first install. Files go back to what was there before our first change.
    Backups from before the newest first install (e.g. before a reflash) are left out; if no first-install
    backup is found, uninstall says so and points to `--from-stock`.
  - A run that stopped half-way is finished by the next run: the restarts it still owed are done.
  - Tailscale: Moonraker trusts Tailscale addresses (else Fluidd/OrcaSlicer got "401 Unauthorized"); the version
    and its SHA-256 are pinned in the project and a newer pin is offered as an update; a half-finished install is
    completed and stays removable (marker written first); TUN loaded at boot when it needed modprobe; the login
    link is never written to the log; uninstall logs out first; Ctrl+C at a question is handled; a user's own
    Tailscale is never touched.
  - Time zone: names from the PC are cleaned (POSIX rules and paths refused, `_dstoff` handled), a zone the
    printer does not know is skipped, and a failure no longer stops the install.
  - Fluidd: a bed mesh card the user only collapsed is left alone.
  - Docs: `reactor-timer-scan` does change one thing (a re-run request for a paused timer is dropped) - now said.
- Installer: optional **Tailscale** for remote access (QIDI's cloud does not serve 02.04). Asked at the end of
  the install (default yes); the official static build is downloaded on the PC, checked by SHA-256, copied to
  the printer and started (userspace networking when the kernel has no TUN). Login link right away or later.
  Uninstall removes it only if the installer added it (marker in /etc/default/tailscaled). `--tailscale ask|yes|no`.
- New Klipper modules from Valve-Oil (thelegendtubaguy), adapted to 02.04 and part of a normal install:
  `reactor-timer-scan` (a timer is not re-armed while its callback runs; next wake-up computed locally) and
  `webhooks-status-diff` (unchanged status objects skipped, deep comparison only when a value differs).
  `webhooks-status-diff` sends the same messages; `reactor-timer-scan` additionally drops a request to re-run a
  timer whose callback is paused (no nested run) - nothing in Klipper's own code relies on it. Prepared with Codex "Stefan".
- New module `printer-timezone`: the installer sets the printer's time zone to the one of the PC it runs on
  (after a reflash the printer runs on UTC). Windows zone names are mapped to IANA names with the Unicode CLDR
  table (`tools/windows_zones.py`). Uninstall puts the previous zone back.
- New module `fluidd-bed-mesh-card`: the bed mesh card is switched on on Fluidd's dashboard (QIDI ships it off),
  so a mesh can be loaded after homing and its deviations seen in 3D. The saved layout is kept and put back on
  uninstall.
- Installer: the backup reads all original files from QIDI's package in one pass instead of one pass per file
  (it took very long on a fresh install), and the backup and the install show a progress bar.
- Installer: a Moonraker database entry that did not exist before the install is removed again on uninstall.

## 1.0.0 - 2026-11-14
First release. Tested with a full reflash (eMMC by USB-C, USB updates 1.1.1 -> 02.01 -> 02.04) and an install
from a fresh copy of the project on 14.11.2026.

- Installer: on a freshly flashed printer the folder `/home/qidi/download` does not exist yet, so locking it
  (`firmware-download-guard`) stopped the install half-way - files on the printer, services not restarted.
  The folder is now made before it is locked. Found in the reflash test on 14.11.2026.
- Installer: everything it prints also goes to `logs/<command>-<time>.txt` in the project folder (no password
  in it), so an error is not lost when the window closes. If an install stops after files were written, it now
  says so plainly: run it again or restart the printer before printing.
- Fix in `print-cache-protection`: a print started from the screen's "recently printed" entry (the file with
  the clock icon, the copy in the print cache) was refused and the screen stayed on "Preparing to print... 10%".
  The screen starts that entry as `/.cache/<name>` without copying; the module took only names relative to the
  G-code directory. Such a start now prints the file from the print cache, as QIDI's code does, and full paths
  are taken again, but only inside the G-code directory and the print cache. The log now shows what the screen
  asked for, and a refused start names the file. Tested on the printer.
- Uninstall puts Fluidd's Z direction setting (`fluidd-z-like-screen`) back to the value it had before the install
  (`--from-stock`: QIDI's factory value); before, uninstall left it changed.
- Docs: module count, release status and credits (Klipper, Valve-Oil, n3oney, AFSFigueiredo, ValitovTimur,
  ololonly, QIDI, Codex "Stefan", Claude) updated; rows of the fixes list moved to
  the right sections; Valve-Oil's Max 4 / Plus 5 Box fixes that the Q2's older code does not need are listed.
- New module `probe-retry-fix`: when a probe point's two samples disagree, QIDI re-zeroed the nozzle load cell
  while the nozzle was still pressed on the bed (the next samples then triggered in the air, 2.9 and 5.9 mm in
  this printer's logs) and reset the retry count, so a point that never agreed was probed forever and print
  start hung. The load cell is now re-zeroed after the nozzle lifts, and a point fails after
  `samples_tolerance_retries` tries. Same fix as Valve-Oil for the Max 4 and Plus 5.
- Four small fixes from upstream Klipper (QIDI's Klipper is upstream from August 2024), each checked to be
  missing in 02.04: `mcu-restart-shutdown` (a board that restarts on its own, e.g. a QIDI Box losing power,
  now stops Klipper cleanly - the shutdown code itself failed with an error), `homing-trsync` (two timing
  fixes for homing across two boards, as the Q2 does for Z with the nozzle sensor), `heater-comm-loss-message`
  (a lost board is reported as lost instead of first as a heater error) and `serialqueue-clock-margin`
  (wider margin against a 31-bit clock overflow).
- New module `load-temp-memory` (QIDI_Q2 #26): a filament loaded after a hotter material (e.g. PLA after
  PETG) no longer has to push the old material out at its own, too low temperature (crackling, ground or
  broken filament). The printer remembers the temperature of the material in the nozzle (load, unload, print);
  the push runs at the higher of the two temperatures, the flush after it at the new filament's temperature.
  Unload uses the higher temperature as well. Nothing hotter remembered: as in QIDI's macros.
- New module `box-fan-threshold` (QIDI_Q2 #25): the QIDI Box heater fan threshold (Box temperature above
  which the two heater fans run while the Box is not heating; QIDI: 35 C) can be set with
  `SET_BOX_FAN_TEMP TEMP=40` and is kept across restarts. A change in box.cfg never lasted: the screen
  program writes its own box.cfg template over the file at every start (also in 03.02). The value is kept in
  saved_variables.cfg; QIDI's files are not changed.
- New module `z-home-random-point`: Home All homes Z at a random point within 10 mm of the plate centre instead
  of always the same spot, spreading the nozzle-probe wear on the PEI (only with a fresh bed mesh before every
  print, G29 k=1, QIDI's default).
- New module `moonraker-box-status-merge`: Moonraker keeps the BOX and drying status complete - nested updates
  from QIDI's Klipper are merged instead of replacing whole sub-objects (QIDI's own fix from 03.02; affects the
  QIDI app's 30-second refresh and Moonraker's status diffs).
- New module `dns-fallback-global`: the printer's fallback DNS are 1.1.1.1 and 8.8.8.8, as in QIDI's 03.02
  international package, instead of the Chinese public DNS 114.114.114.114 and 223.5.5.5 that 02.04's network
  hook adds (one line of QIDI's hook changed; installer: new generated-file kind that edits that line and puts it
  back on uninstall, also without a PC backup).
- New module `fluidd-z-like-screen`: Fluidd's Z arrows now mirror the printer's screen - down moves the
  bed down, up moves it up (before, with QIDI's factory setting, Fluidd's down arrow raised the bed towards the
  nozzle). The installer
  sets Fluidd's Z direction setting on the printer (new installer action: one Moonraker database entry,
  set only when different).
- New module `z-home-guard`: "Home Z" on its own (`G28 Z` from Fluidd, QIDI Studio or the console) is refused
  unless X and Y are homed and the nozzle is over the build plate - the Q2 homes Z with the nozzle as the
  probe, and QIDI's own safety (head to the plate centre first) covers only Home All. The head is never moved;
  Home All, printing and QIDI's macros are unchanged.
- Every drying end now lands on the screen's drying settings page: time up (as in stock firmware), Stop on
  the screen and a stop from Fluidd or the console (before: Stop led to the Function list). A Stop usually
  means something is not as you wanted - filament, temperature or time to change - so the settings are the
  useful place to land, not the Function list; "back" from there still leads to the Function list and home.
- A second drying start while a drying runs is refused (console `SET_FILAMENT_DRY`, `prepare_filament_dry`):
  it restarted the drying behind the screen's back, so the screen showed no drying although it ran, and
  `prepare_filament_dry` would home and move the bed during drying. Stop first, then start again - as on
  the screen.
- New module `screen-gradient-cache-off`: the screen's drying Start button no longer stays drawn grey after
  a drying ends. The screen's graphics library (LVGL 8.3) reused a cached colour gradient that was keyed by
  memory address and size only, so the grey (disabled) look could stick to the enabled button. Same in stock
  firmware. The gradient cache is now off (LVGL's own workaround).
- Drying is locked while the printer is busy, like on the screen: the
  Fluidd drying entry shows an in-page notice instead of the window during a print, pause, calibration,
  homing or any running task; `SET_FILAMENT_DRY` and `prepare_filament_dry` refuse to start in that state
  (Klipper's idle_timeout state "Printing"). A drying stop is passed to QIDI only while drying runs, so a
  stop typed during a print can no longer switch the bed and chamber heaters off. A drying started from
  Fluidd opens the screen's drying page through the Function page, so "back" from the drying page
  leads to the Function list, as after a start from the screen.
- New module `screen-drying-countdown-roundup`: the screen's drying time left is rounded up (a 5-minute
  drying shows 05min, 04min ... 01min instead of 04min ... 00min; above one hour whole hours rounded up).
- Drying end: the printer beeps like at the end of a print (`idle-timeout-drying`), and the screen wakes up
  (`screen-drying-autoshow`). A drying start from Fluidd also wakes the screen and the chamber light, which
  then go to sleep by themselves as after one touch.
- Drying start is refused (screen, Fluidd, console) unless the bed is lowered (Z ≥ 190, `prepare_filament_dry`).
  In the Fluidd window Start stays grey with a hint until the bed is lowered, and Stop is grey when nothing
  is drying.
- New module `screen-drying-start-button`: the screen's drying Start button no longer stays grey after a
  screen restart during drying.
- Fluidd drying window: "Lower the bed" also wakes the printer screen and the chamber light (console line
  `q2_wake_screen`), and the Start button is green.
- `idle-timeout-drying`: the idle timeout is set once for the whole drying time instead of every 10 s, so the
  console is no longer flooded with "idle_timeout: Timeout set to 600.00 s".
- New module `screen-drying-autoshow`: the screen wakes up and opens its drying page by itself
  when drying is started from Fluidd.
- New module `fluidd-drying-button`: a "Filament drying" entry in Fluidd's left panel and a window with the
  printer screen's own settings and commands (tested: lower the bed, start, time left, stop).
- New module `screen-drying-layout`: on the screen's drying page the time and temperatures are shown in one
  line instead of overlapping the step list (checked on the screen).

## 0.9.0-rc2 - 2026-11-10
- Installer recognises earlier versions of its own files (`modules/LOCK-history.json`, `previous` edits
  for configuration files) and upgrades them instead of refusing.
- `install.py uninstall --from-stock`: uninstall without the PC backup, using the originals from the
  official package.
- Clearer message when a printer has other modifications (what to do first).
- `install.bat`: guided install for Windows (double-click).
- `screen/README.md`, automatic offline tests on GitHub (Python 3.9 and 3.13), problem-report template.
- Macro comments in English (park-rear-right).

## 0.9.0-rc1 - 2026-11-10
- First public release candidate: 40 modules, installer with backup / plan / install / uninstall,
  OrcaSlicer profiles, recovery guide (EN/PL).
