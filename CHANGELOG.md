# Changelog

## Unreleased

- New module `maintenance-reminders`: counts the printer's print hours and, after a print that pushes a task over its interval,
  shows an extra window on the printer screen (and a phone message with a Done button when `phone-notifications` is installed):
  X/Y rails every 100 h, Z lead screws every 300 h, fans every 300 h of printing (QIDI's manual: rails every 2-4 weeks, Z screws
  every 1-3 months). Repeats after every print until marked done (`TWEAKED_MAINT_DONE TASK=rails|zscrews|fans|all` in Fluidd, or
  the phone button); `TWEAKED_MAINT_STATUS` shows the hours. `phone-notifications`: the Photo button is now "Get a photo", and
  the listener understands `maintdone <task>`.
- `phone-notifications`: a "Photo" button on the start and 25/50/75 % messages sends the camera picture on request (any state;
  the message stays after the tap, unlike Resume/Cancel). The "Print finished" message now also says how much filament was used
  (whole grams: the slicer's weight of the file in proportion to the length used, from Moonraker; metres when that is not known). The message
  scripts no longer loop for ever if a time/filament token cannot be replaced. Tested on stand-ins only; not on a real print.
- `send-and-print-guard` no longer depends on checksums. It looks for the Upload & Print bug in the active Fluidd bundle by its code:
  repaired = nothing to do, the known broken code found once = repaired (only while the printer is idle), anything else = nothing
  changed and the run still ends OK. Before, any change to Fluidd or to the screen program made it stop ("Bundle differs from the
  known original") until new checksums were added. New tests (they did not exist). Tried on stand-ins and one real run on the printer.

- `box-homing-timeout` is now installed by default (it only changes homing that involves a QIDI Box board, so it does nothing without a Box): someone who adds a third Box
  does not have to search for the fix. Home all (G28) was run on a printer without a Box after installing it: no error.
- Installer: all optional extras now come at the end, one after the other: question, yes = installed right away, no = the next
  question (optional modules such as `journal-retention`, phone notifications, toolhead check, Tailscale, OrcaSlicer profiles).
  Without a window to ask in (a scripted run) nothing optional is offered; `--with`, `--notify yes|no` and the other flags still work.
- Phone notifications: the generated channel name is saved in `backups/notify-<printer>-channel.txt` on the PC (and the install log says where),
  so it is not lost if the window is closed.
- New optional module `phone-notifications`: messages on your phone through ntfy (free, no account): start, 25/50/75 %, finished,
  cancelled, **pause with its reason** (AI spaghetti / AI foreign object / filament runout / M0 or M25 / manual) with a camera picture and
  Resume / Cancel buttons, printer errors, a print interrupted by a restart, and the timelapse video on a button. The installer asks at
  the start (`--notify ask|yes|no`) and shows the random channel name at the end (window only, not in the log). Uninstall removes the settings.
  Pausing is unchanged. The tests run the scripts and the Klipper templates against stand-ins; not tried on a real print yet.
- `fluidd-fixes`: Fluidd's print ETA ("File") now uses the same progress as the printer's screen (the slicer's M73 progress,
  `elapsed x (100-P)/P`) instead of the position in the file, so Fluidd and the screen show the same time left. It no longer uses the
  duration of an earlier run of the same file. Seen on a real print only through the numbers (screen 30 min, this formula 30.6 min); not yet seen live.
  Same for up to 50 % progress: the screen then shows the slicer's estimate minus the print time (its `prediction`, e.g. 3644 s = 1h0m44),
  and Fluidd now does the same; above 50 % both extrapolate from the real pace. Found in the screen program; not seen live.
- `phone-notifications`: the 25 % and 50 % messages now show the same time left as the screen (the slicer's estimate from Moonraker minus
  the print time; extrapolation as before when there is no estimate or above 50 %). New small helper `q2_notify_eta.py`. Tested only
  against a stand-in Moonraker, not on a real print.
- New module `fluidd-full-display`: the installer switches Fluidd's "Enable Full Display" setting on.
- New module `timelapse-progress-note`: one short console note "Timelapse is on: layer N/total" at layer 1 and then every 20 layers.
  Fluidd's per-layer timelapse line (`SET_GCODE_VARIABLE ... takingframe VALUE=False`, an echo from Moonraker's timelapse component) can then
  be hidden with a Fluidd console filter. Not tested on a real print yet.
- Removed `adaptive-bed-mesh` (bed mesh only under the first layer). The 20.11.2026 test print showed it never worked
  with OrcaSlicer files: they are `.gcode.3mf` (a ZIP), which the module read as plain text, so it always fell back to
  the whole plate - and QIDI's own KAMP macro, which replaces `BED_MESH_CALIBRATE`, ignored the area anyway. QIDI's macro
  already narrows the mesh to the objects (in X; that print: 24 points instead of 36), so the module is not needed.
  The installer does not take it off a printer that has it: there it stays harmless (it passes on to QIDI's macro).
- Docs: step-by-step guide for the manual, optional toolhead accelerometer fix from a Windows PC
  (`docs/TOOLHEAD_ACCELEROMETER.md`, Polish version too). The flashing commands are the ones run on the author's
  printer on 18.11.2026; the guide's PowerShell commands and its `/tmp` folder were not run exactly as written, and
  going back to the original firmware is not tested. The installer still never flashes the toolhead.

## 1.1.0 - 2026-11-20
Second release. Everything listed here is installed on the author's printer. Not tested on the printer yet: the
bed mesh under the first layer in a real print (after its last fix), resuming after a real power cut
(`power-loss-resume-homing`), and the code-review fixes below in a print.

- Fixes from a code review of everything since 1.0.0 (tested with new unit tests; installed on the author's printer, not tested in a print yet):
  - Installer: when the run that finishes a stopped install is stopped too, the next run still restarts Klipper
    (before, it could say "nothing to do" with the new files not loaded yet).
  - Uninstall takes out the printer.cfg / macro edits of a module that a later install left out (`--skip`).
  - A wrong sudo password is noticed right after it is typed (asked again, up to 3 times), not halfway through.
  - `adaptive-bed-mesh`: a file printed object by object gets the whole plate measured (only the first object
    was measured before); G91 counts the extrusion as relative, as Klipper does.
  - Small: Moonraker database names are URL-encoded; a hand-edited Orca index line without a tab is skipped.
- New module `thr-accel-check` (from the 03.02 port, read only): QIDI's Q2 toolhead firmware has an accelerometer bug
  (about 390 samples a second instead of 1600, QIDI_Q2 #39). At the end of an install the installer says so and asks
  whether to check the printer (`--toolhead yes|no`); the console command `TWEAKED_THR_CHECK` measures the rate and
  identifies the toolhead bootloader and firmware (memory reads only), the installer prints whether you have the
  bug and what is recommended, and keeps a backup of the toolhead firmware on the PC. Flashing stays manual, at
  your own risk: docs/TOOLHEAD_ACCELEROMETER.md.
- OrcaSlicer filament profiles (orca-profiles/filament/, imported in OrcaSlicer with File > Import > Import
  Configs): a "(Tweaked)" copy of each of the 331 OrcaFilamentLibrary filaments usable on the Q2 with the chamber
  fan set like QIDI's own profiles - the library leaves it off. PLA and TPU 100%, PETG 75%, nylon 25%,
  ABS/ASA/PC 0%, 0% after the print. Generated by tools/orca_filaments.py.
  tools/orca_profiles.py install adds them by itself for the filaments enabled in OrcaSlicer, and the installer
  now asks at the end whether to add the project's OrcaSlicer profiles on that computer (--orca yes|no).
- New module power-loss-resume-homing: resuming after a real power cut no longer ends in a Klipper shutdown while X/Y
  home (QIDITECH/klipper#18) - X and Y are switched on before homing.
- New `adaptive-bed-mesh`: the bed mesh before a print is measured only where the first layer is printed - models,
  wipe tower, brim and skirt, read from the file itself - plus 10 mm, not the whole plate. A quicker start for small
  prints and fewer nozzle presses on the PEI. Whole plate as before for G29 from the screen or console, files without
  layer markers, a first layer over most of the plate, or any error.
  Fix: its command was called Q2_ADAPTIVE_MESH, which Klipper reads as the G-code "Q2" and QIDI's Klipper
  drops silently - G29 then measured no mesh at all. Renamed to TWEAKED_ADAPTIVE_MESH; a new test
  (tests/test_command_names.py) checks every module command name the way Klipper parses it.
  Fix: on the printer it then failed reading the mesh settings (configfile.get_status needs eventtime) and fell back
  to the whole plate; a new test runs the whole command against Klipper-like objects.
- Installer and `tools/printer.py`: when the printer accepts your SSH key, no password is asked to log in; when
  sudo on the printer also needs none, nothing is asked at all. Nothing changes for everyone else (password as
  before). The project never changes sudo settings on the printer.
- From reviewing the Q2's system and QIDI_Q2 issues against 02.04:
  - `adb-root-shell-off`: QIDI's ADB service (root shell without a password over the network on the Max 4) is
    turned off; skipped when the printer has no such service. Installer: enabling/disabling a service the printer
    does not have is now skipped instead of failing.
  - `qidi-tuning-calm`: QIDI's CPU tuning script ran again about every 35 s forever; now about every 1.5 min.
  - `box-homing-timeout` (optional, `--with box-homing-timeout`): 3+ QIDI Boxes - "Communication timeout during
    homing" on tool changes (QIDI_Q2 #33); 250 ms instead of 50 ms only for homing that involves a Box board.
  - Root filesystem `sync` (QIDI's failing Rockchip first-boot script): measured and left as it is on purpose -
    nothing is lost when the printer is switched off at the mains; see docs/FIXES.md, Not included.
- Installer: a printer is recognised by its own ID (the processor's serial number), not by the address used. Backups
  made over the home network and over Tailscale now belong to the same printer (uninstall and resumed runs see all of
  them, oldest first by time). Older backups without an ID are matched by address or by the printer's saved SSH key.
- Installer: a run that only adds new modules to an already installed printer is no longer taken for a first
  install (each run now records how many of the modules' files were already ours). Before, uninstall after such a run
  would have put back only the newly added modules.
- `console-english`: the last 7 Chinese console messages (AI switches and sensitivity, PEI plate check, power-loss
  resume) are now English.
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
- OrcaSlicer profiles: `tools/orca_profiles.py install --apply` stopped with "Could not check whether OrcaSlicer
  is running" on Windows in a non-English language with Python 3.15 (`tasklist` writes in the console code page,
  Python 3.15 reads UTF-8). The list is now read leniently.

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
