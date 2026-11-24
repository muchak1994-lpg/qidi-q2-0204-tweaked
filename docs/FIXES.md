# What the modules fix

**English** · [Polski](FIXES.pl.md)

Every module is a small, separate change against the original QIDI 01.01.02.04 files. All of them run on
the author's Q2; "tested" below means a specific physical test on that printer beyond normal use.
List them with `py tools/build.py --list`; leave one out with `--skip MODULE`.

Sources in brackets: **QIDI #nn** = issue in [QIDITECH/QIDI_Q2](https://github.com/QIDITECH/QIDI_Q2/issues),
**Klipper** = backport of an upstream Klipper fix, **Valve-Oil** = the same fix as in
[Valve-Oil](https://github.com/thelegendtubaguy/Valve-Oil) (thelegendtubaguy, GPL-3.0) for the QIDI Max 4 / Plus 5.

## Screen program

| Module | Problem on stock 02.04 | What the module does |
|---|---|---|
| `screen-program` | The screen program can crash on rare MCU/toolhead events, and its print history can get out of sync. | Rebuilds the screen program on your PC from QIDI's 02.04 program plus the print-queue code of QIDI's own 03.02 program, and adds the history sync and version entry. Every build stage is SHA-256 checked. |
| `update-check-off` | A "new firmware" popup pushes the online update - which would replace 02.04 for good. | Turns the update check off (one byte in the screen program). |
| `firmware-download-guard` | The printer can download an update package in the background. | Makes the download folder read-only (immutable flag). Undo: `uninstall`. |
| `printer-timezone` | After a reflash the printer runs on UTC: times in Fluidd, the history and the logs are off by an hour or two. | Sets the printer's time zone to the one of the PC the installer runs on (Windows zone names mapped with the Unicode CLDR table). A zone the PC or the printer does not know is left alone; never stops the install. Full effect after the next restart. Undo: `uninstall` (previous zone back). |
| `dark-mode-light` | Turning the light off during a print is undone by the screen and by the spaghetti detection. | **Dark mode:** light off during a print = light and spaghetti detection off until the print ends. Tapping the screen gives temporary light; switching the light on ends dark mode (detection back after 60 s). Tested. |
| `screen-drying-layout` | On the drying page the time, bed and chamber temperature overlap the step list (English texts wrap to two lines). | Puts the three values in one line under the steps (eleven position values in the screen program). Checked on the screen. |
| `screen-drying-start-button` | After a restart of the screen program during drying, the drying page's Start button stays grey (disabled) when drying ends. Stop on the screen leaves the drying page for the Function list, while a drying whose time is up ends on the drying settings. | The Start button is re-checked when drying ends, with QIDI's own rule (disabled only while the printer is busy). Every drying end - time up, Stop on the screen, a stop from Fluidd or the console - ends on the drying settings page. A Stop usually means "something is not as I wanted": you want to change the filament, temperature or time and start again, not land in the Function list; from the settings, "back" still leads to the Function list and the home page. Checked: restart during drying, time up, Stop on the screen after a start from the screen's steps and after a start from Fluidd (screen coming from the home page), stop from the console, "back" afterwards. |
| `screen-drying-countdown-roundup` | The drying time left is rounded down: a 5-minute drying starts at 04min and shows 00min for its whole last minute. | Rounded up: 05min ... 01min; above one hour whole hours rounded up. Checked on the screen (07min at start of a 7-minute drying, 05min, 01min). After the time is up QIDI's drying module can take up to a few minutes to switch off; the screen shows 00min meanwhile. |
| `screen-gradient-cache-off` | After a drying ends, the drying page's Start button can stay drawn grey although it works (tapping it starts the drying steps). Cause: the screen's graphics library (LVGL 8.3) caches the last colour gradient by memory address and size only, not by colour, so the grey (disabled) look is reused for the enabled button. | The gradient cache is off (one instruction: cache size 0, LVGL's own workaround): every gradient is computed when drawn. Tested: a stale grey gradient left in the cache was drawn grey with the cache on and blue with the cache off, on the same wake-up redraw. |
| `screen-drying-autoshow` | When drying is started from Fluidd, the screen stays on its current page (and dark if it was asleep). | The screen wakes up like after one touch (backlight, chamber light, then sleeps again by itself) and opens its drying page the way a user gets there (through the Function list, without showing it), so "back" from the drying page leads to the Function list as after a start from the screen. It also wakes up when drying ends, and on the console line `q2_wake_screen` (sent by the Fluidd drying window's "Lower the bed"). Checked: start from Fluidd's commands with the screen asleep, end of drying with the screen asleep. |

## Klipper (motion, heaters, sensors)

| Module | Problem | Fix |
|---|---|---|
| `fuzzy-skin-extrusion` | QIDI's extruder "accumulator" skips small E moves and counts E twice in fuzzy skin **extrusion** mode: gaps and blobs. | Keeps the slicer's E targets unchanged. Tested with a fuzzy-skin print. |
| `hotend-fan-hysteresis` | The hotend fan switches on/off around 50 °C with no hysteresis, and a reheat while the fan runs can raise a false fan alarm. | Adds hysteresis and closes the watchdog gap. Tested. |
| `box-heater-keepalive` | QIDI Box heaters drying during a print can stop Klipper with "max_duration" (QIDI #34). | Sends the heater keep-alive earlier for Box heaters only; the safety limit is unchanged. Reported fix: 8000+ tool changes, no shutdown. |
| `box-fixes` | Box heater settings are invisible to Klipper's config checker, so Fluidd rejects any Box heater target with "Min or 0" (QIDI #23, #18). | Registers them like the other heater settings; Fluidd then gets the Box heater's limits. |
| `box-fan-threshold` | The QIDI Box heater fan threshold (fans run above 35 °C Box temperature even when the Box is not heating) cannot be changed for good: a change in box.cfg, as QIDI's wiki describes, is overwritten at the next start - the screen program writes its own box.cfg template over the file every time it starts (QIDI #25; also in 03.02). | `SET_BOX_FAN_TEMP TEMP=40` sets the threshold for both fans of every Box, kept in saved_variables.cfg and applied at every Klipper start; `SET_BOX_FAN_TEMP` shows it, `TEMP=0` goes back to box.cfg. Allowed 25-60 °C. QIDI's files are not changed. Tested on a printer without a Box; the fan part with stand-ins only (no Box available). |
| `mcu-ack-timeout` | After a lost MCU connection Klipper can hang instead of reporting the error. | Clean "No communication with MCU" error (Klipper). |
| `serialqueue-fixes` | Pipes are not closed and memory is not freed when the serial queue fails at start-up. | Proper clean-up (Klipper). |
| `pressure-advance-history` | Memory leak when the extruder is reset. | Frees the old pressure-advance history (Klipper). |
| `stepcompress-far` | A step far in the future can be written past the end of the step queue. | Klipper PR #7421 (Kevin O'Connor). |
| `tmc-direction-event` | A misspelled event name: TMC drivers never hear about a stepper direction change. | Correct event name. |
| `z-offset-persistence` | Temporary Z offsets set by QIDI's macros can be saved as if they were your Z offset. | Temporary offsets are marked and not saved. |
| `save-variables-atomic` | A power cut while saving settings can leave an empty settings file; Klipper then may not start. | Writes a temporary file and renames it (atomic); identical content is not rewritten. |
| `external-slot16-literal` | After loading from the external spool holder QIDI writes `slot16`, which the settings saver rejects. | Accepts that exact value. |
| `ai-fixes` | Pausing, resuming or cancelling while the AI foreign-object check waits breaks the print state; AI messages have broken characters. | Commands are handled correctly during the check; text encoding fixed. The foreign-object check itself stays as QIDI made it (it can be switched off on the screen); see *Camera AI* below. |
| `console-english` | Some console messages are Chinese (light sync, AI switches and sensitivity, PEI plate check, power-loss resume). | English messages. |
| `mcu-restart-shutdown` | When a board restarts on its own (e.g. a QIDI Box losing power), Klipper's shutdown code fails with an error instead of stopping cleanly. | One missing default parameter (Klipper 9ce631e8). |
| `homing-trsync` | Homing across two boards (the Q2 homes Z with the nozzle sensor on the toolhead board): the setup messages could be scheduled too late, and an earlier timeout could be sent to the board. | Two upstream fixes (Klipper 8e6e467e, 29d4ec2d). |
| `heater-comm-loss-message` | On a lost board connection a heater error can be reported before the real cause. | 7 s instead of 5 s before a heater's temperature counts as stale (Klipper 46912431). |
| `serialqueue-clock-margin` | Messages scheduled far ahead have no margin against a 31-bit clock overflow on the boards. | Wider margin (Klipper 867d73f0). |
| `probe-retry-fix` | When a probe point's two samples disagree (bed mesh, Z tilt), the nozzle load cell is re-zeroed with the nozzle still pressed on the bed - the next samples trigger in the air - and the retry count starts over, so a point that never agrees is probed forever and print start hangs. | Re-zero after the nozzle lifts, as before every point; at most `samples_tolerance_retries` retries, then an error. Same fix as Valve-Oil (Max 4, Plus 5). |
| `power-loss-resume-homing` | Resuming a print after a real power cut ends in a Klipper shutdown while X/Y home ("Homing failed due to printer shutdown"): the X/Y drivers come back reset and are first switched on by the homing move itself, and Klipper's TMC code pauses the toolhead in the middle of that move ([QIDITECH/klipper#18](https://github.com/QIDITECH/klipper/issues/18), with logs). | The resume sequence switches X and Y on, waits, then homes - the fix validated in that report with repeated real power cuts. Normal homing is untouched. 02.04: checked by building, not yet with a power cut on our printer. |
| `reactor-timer-scan` | Klipper's timer loop could re-arm a timer while its own callback was still running, and recalculated the next wake-up the long way. | A timer is not re-armed while its callback runs or is paused (no nested run; cleared safely with try/finally); the next wake-up is computed locally. One deliberate change: a request to run a paused timer again 'now' is dropped - nothing in Klipper's own code relies on it. From Valve-Oil (thelegendtubaguy), adapted to 02.04. |
| `webhooks-status-diff` | Klipper compares every status object for every client (Fluidd, Moonraker, screen) on each update, also when nothing changed, and runs QIDI's deep comparison even for equal values. | Unchanged status objects are skipped and the deep comparison runs only when a value differs. The same messages are sent, with less work. From Valve-Oil (thelegendtubaguy), adapted to 02.04. |
| `box-homing-timeout` | On by default (harmless without a Box). With 3 or more QIDI Boxes a tool change can stop the print with "Communication timeout during homing" (QIDI_Q2 #33): homing that involves a Box board gets only 50 ms for the boards to answer each other. | Homing that involves a Box board gets 250 ms (Klipper's own single-board value); Z homing and everything else keep 50 ms. Based on the issue report - the timeout itself is not tested here (no Box); Home all was checked on a printer without a Box. |

## Macros and configuration

Your calibration (`#*# SAVE_CONFIG` block) is kept: only these lines are edited in your own files.

| Module | What changes |
|---|---|
| `idle-timeout-drying` | Idle timeout 12 h → 5 min (heaters off), separate "pause" / "idle" messages, motors off; chamber drying keeps working. Drying start refused unless the bed is lowered (Z ≥ 190) and while the printer is busy (print, pause, moves, a running task); a stop is passed to QIDI only while drying runs, so it cannot switch the heaters off during a print; a second start and `prepare_filament_dry` refused while a drying already runs (stop first); `prepare_filament_dry` refused while busy; a beep (like at print end) when drying finishes by itself. |
| `resume-after-heating` | After a pause, the purge waits until the nozzle is hot again. |
| `park-rear-right` | After a print or a stop the head parks at the rear right, so the camera sees the bed. |
| `z-home-guard` | "Home Z" on its own (Fluidd's Home Z button, QIDI Studio's device page, the console: `G28 Z`) homes Z with the nozzle as the probe wherever the head stands - also over the purge bin or the plate edge. Home All centres the head first; Home Z alone does not. Home Z alone is refused unless X and Y are homed and the nozzle is over the build plate (X 0 to under 271, Y 5 to under 271 - at least 5 mm inside the measured PEI edges); the head is never moved for it, the message says to move it over the plate or use Home All. Home All, printing and every QIDI macro are unchanged (the screen's plate calibration homes Z at X240 Y32, inside the area). Same rule as Marlin 1.0's Z safe homing. |
| `z-home-random-point` | The Q2 homes Z by pressing the nozzle on the plate, and Home All always does it at the plate centre - several times per print - wearing the PEI at the spot where most prints sit. Home All homes Z at a random point within 10 mm of the centre (idea: n3oney, qidi-community Q2 wiki), only with a fresh bed mesh before every print (G29 k=1, the default); with a saved mesh (k=0) the centre stays fixed so the mesh still fits. |
| `thr-accel-check` | QIDI's Q2 toolhead firmware has an accelerometer bug: about 390 samples a second instead of 1600 (QIDI_Q2 #39), so input shaper calibration sees only part of the vibrations. | Only a check, read only: `TWEAKED_THR_CHECK` measures the rate and identifies the toolhead's bootloader and firmware (memory reads, nothing is written) and backs them up on request. The installer asks at the end whether to run it and says whether you have the bug. Flashing stays manual, at your own risk: [TOOLHEAD_ACCELEROMETER.md](TOOLHEAD_ACCELEROMETER.md). |
| `external-filament-load-finish` | After an external filament load: fan and heater off. |
| `load-temp-memory` | Loading a new filament after a hotter one (PLA after PETG, ABS or PA) heats only to the new filament's temperature, so the old material left in the nozzle is too stiff to be pushed out: crackling, ground or broken filament (QIDI #26). The printer remembers the temperature of the material in the nozzle (load, unload, print start and end). The first push (80 mm) runs at the higher of the two temperatures, the flush after it at the new filament's temperature; unload also uses the higher one. Nothing hotter remembered: QIDI's behaviour. Applies to loading and unloading from the screen and Fluidd (M604 / M603); QIDI Box tool changes inside a print are not changed. |
| `end-guard` | Chamber heater and fans off at the end of a print and when drying ends. Tested. |
| `filament-wipe` | Extra purge-and-wipe macro (`FILAMENT_WIPE`); does not replace QIDI's own. |
| `screws-tilt` | Bed screws tilt helper. |
| `mcu-temperatures` | Approximate mainboard / electronics temperatures shown in Fluidd. |

## Moonraker and Fluidd

| Module | What changes |
|---|---|
| `print-cache-protection` | Two print starts at the same moment can no longer corrupt the print cache; the screen shows file info (thumbnail, time). |
| `3mf-cache` | 3MF metadata and thumbnails are extracted once per file, not again on every request. |
| `orca-object-height` | Object height and layer count come from the slicer's metadata, not from parking moves in the G-code. |
| `emmc-info` | Fluidd shows the real eMMC information. |
| `gcode-history` | A multi-line console command stays one history entry. |
| `timelapse-capture-recovery` | One failed timelapse frame no longer stops the whole timelapse. |
| `timelapse-progress-note` | One short console note "Timelapse is on: layer N/total" at layer 1 and then every 50 layers. Not tested on a real print yet. |
| `phone-notifications` | OPTIONAL (installer question or `--notify yes`). Messages on your phone through the free ntfy app: print started (after the first layer), 25/50/75 % with elapsed / finish time / time left, finished, cancelled, **paused with the reason** (AI spaghetti, AI foreign object, filament runout, M0/M25 in the G-code, manual) with a camera picture and Resume / Cancel buttons, printer errors, and a print interrupted by a restart or power cut. After a print with timelapse, a button sends the video. No account or phone number needed; the channel names are random and secret. Pausing itself is unchanged (stock QIDI keeps bed and chamber heated). Not tested on a real print yet. |
| `fluidd-fixes` | Fluidd: file and folder names with spaces/special characters, upload/download progress per file, controls usable while paused, SoC temperature, disk usage, sane ETA at print start, keeps server info on a Klipper reset, hides dialogs while disconnected. |
| `send-and-print-guard` | Keeps Fluidd's "Upload & Print" working (checks at boot and nightly). |
| `fluidd-drying-button` | A "Filament drying" entry at the end of Fluidd's left navigation panel (phone and computer). It opens a window with the printer screen's own settings (15 filament types, build plate temperature up to 100 °C, time 1-24 h) and sends the same commands as the screen (`prepare_filament_dry`, `SET_FILAMENT_DRY`). Fluidd's own program file is not changed. While the printer is busy the drying entry shows an in-page "printer is busy" notice instead of the window (like the screen). Start (green) stays grey until the bed is lowered, "Lower the bed" also wakes the screen, Stop is grey when nothing is drying. Tested: lower the bed, start, time left, stop. |
| `fluidd-z-like-screen` | In Fluidd (also inside QIDI Studio) the down arrow for Z moved the bed **up** towards the nozzle (QIDI's factory Fluidd setting), while on the printer's screen "down" moves the bed down - easy to crush the nozzle. Fluidd's Z direction setting is set so that it mirrors the printer's screen: down = bed down, up = bed up. X and Y already matched the screen. Uninstall puts the earlier value back. Reload an open Fluidd page once after installing. |
| `fluidd-full-display` | Fluidd setting "Enable Full Display" switched on (a Fluidd setting in the printer's database, applies in every browser). |
| `fluidd-console-filters` | Hides technical lines in Fluidd's console: the echo of the timelapse's per-frame command, the AI service's status code (`noodle=0 status=0`, at every restart of the service), the echo of the phone-message command and of the update notice's command (the red message line stays). Six console filters in Fluidd's saved settings (every browser); the lines are only hidden from the display, your own filters stay, uninstall puts the saved list back. |
| `fluidd-bed-mesh-card` | QIDI's Fluidd has the bed mesh card switched off on the dashboard (only on the Tune page). It is switched on in Fluidd's saved layout on the printer, so after homing you can load or calibrate a mesh and see the deviations in 3D on the dashboard, in every browser. Your own card arrangement is kept. Uninstall puts the saved layout back. Reload an open Fluidd page once. |
| `moonraker-box-status-merge` | QIDI's Klipper sends only the changed nested parts of the BOX and drying status, but Moonraker 02.04 merged them one level deep, so its status cache lost the other fields (e.g. the drying end time, BOX slot data). The QIDI app gets a full refresh from that cache every 30 s. Nested status updates are merged recursively - QIDI's own fix from 03.02. Fluidd and the drying window read Klipper directly and were not affected. |
| `printer-screen-view` | OPTIONAL (`--with printer-screen-view`). A 'Printer screen' entry in Fluidd's left panel opens a window with a live picture of the printer's own touch screen (about twice a second while the window is open). Look only: nothing is sent to the screen or the printer. A small service reads the screen only when a picture is asked for. |
| `printer-screen-touch` | OPTIONAL, needs `printer-screen-view`. A 'Touch off/on' button in that window. Touch is off every time the window is opened; once on, a click in the picture presses the same place on the real screen (it can wake the screen, press Home, Stop, Pause, move axes). At most 4 clicks per second. |

## System

| Module | What changes |
|---|---|
| `ethernet-mac` | The printer's own stable Ethernet MAC address from the first moment of boot (QIDI #28). Generated per printer; active after a reboot. |
| `klipper-priority` | Klipper gets the CPU first (Nice -10). |
| `restart-on-exit` | Klipper and Moonraker also restart after a clean exit. |
| `legacy-qidilink-cleanup` | Old QIDILink / FRP remote services turned off. |
| `adb-root-shell-off` | QIDI's system starts Android Debug Bridge (`usbdevice.service`); it gives anyone on the network a root shell without a password (port 5555, checked on the Q2 02.04). Turned off; skipped if the printer has no such service. Updates, recovery and reflash do not use it. |
| `qidi-tuning-calm` | QIDI's CPU tuning script sets priorities and exits, and systemd started it again about every 35 s (30 s wait in the script + 3 s), forever. Now about every 1.5 min (same settings, a drop-in file; QIDI's files unchanged). |
| `journal-retention` | **Off by default** (`--with journal-retention`): system log kept 7 days, up to 2 GB, for diagnostics. |
| `dns-fallback-global` | 02.04's network hook adds the Chinese public DNS 114.114.114.114 and 223.5.5.5 as fallbacks after your router's DNS; with a typical home router one of them ends up in the printer's DNS list. QIDI's 03.02 international package uses 1.1.1.1 and 8.8.8.8. That one line of the hook is changed to 1.1.1.1 and 8.8.8.8, as in 03.02; the rest of QIDI's hook stays. Takes effect at the next network connect or reboot; uninstall puts QIDI's line back. |
| `update-notice` | On by default (`--skip update-notice` leaves it out). Every 12 hours the printer asks GitHub for the latest published release of this project (one small request, generic name, nothing about you) and, when it is newer than the installed version, shows ONE message per release: a red line in Fluidd's console, a window on the printer screen and, with phone-notifications, a phone message. It never downloads or installs anything and never speaks during a print. |
| `maintenance-reminders` | Counts print hours and, after a print that crosses a multiple of 100 h (X/Y rails) or 300 h (Z lead screws, fans), shows one notice window on the printer screen (and a phone message when phone-notifications is installed). Only a notice, once per interval; `TWEAKED_MAINT_STATUS` in Fluidd shows the hours. Counting starts at installation. |

## Camera AI

> **What "fixed" means here:** on stock 02.04 the camera AI does not work at all (its program is missing
> libraries, and the print flow breaks around the check). These modules make the AI **work as a function**,
> exactly the way QIDI designed it. They do **not** change or retrain QIDI's detection model. How well it
> detects (spaghetti, foreign objects) depends on QIDI's model and on many conditions - light, camera
> position, filament colour, the bed surface - and can vary from print to print.

| Module | What changes |
|---|---|
| `ai-libraries` | 02.04 ships the AI program without 153 of the Python library files it needs. They are downloaded from PyPI and Debian (numpy, onnxruntime, opencv, pycryptodome, psutil, pydantic-core, websockets, chardet, Python 3.9 modules), each checked by SHA-256. Also applies the MEDIUM8 detection setting to the AI program and enables AI autostart. |
| `algo-app-gate` | OPTIONAL (`--with algo-app-gate`). In the dark (case light off) the noodle model reports false noodle: it reads the toolhead LEDs as noodle (22.11: 3.2 % of 652 dark frames at the MEDIUM setting, 0 of 326 light frames). Inside the AI service, a frame whose mean grey value is below 22 becomes a uniform dark grey; light frames pass untouched. No file of QIDI's is edited. In a real print with the light on it let normal frames through (one dark frame at the start was replaced); NOT yet tested in a print in the dark. |
| `algo-app-malloc` | OPTIONAL (`--with algo-app-malloc`), effect NOT measured. Limits the AI service to 2 memory arenas (`MALLOC_ARENA_MAX=2`), so memory freed in one thread can be reused by another. Typical gain 0 to a few dozen MB. |
| `algo-app-oom-priority` | Insurance only, it does not lower memory use: if the printer ever runs out of memory, the kernel kills the AI service first (it comes back in 15 s) and not Klipper or Moonraker (`OOMScoreAdjust` +500 for the AI service, -300 for Klipper and Moonraker; all three were 0 before). Never needed so far. |
| `algo-app-recycle` | OPTIONAL (`--with algo-app-recycle`). Two minutes after a print has ended (finished, cancelled or failed) the AI service is restarted if it is bigger than 130 MB; this gives back 40-100 MB. Never while a print runs or is paused; the AI setting stays. Seen working on the author's printer. |
| `algo-app-stream-decrypt` | OPTIONAL (`--with algo-app-stream-decrypt`). When a print reaches its second layer the AI service decrypts its 44.6 MB noodle model block by block (1 MiB) instead of holding three whole copies for a moment; and it gives the model back two minutes after a print. Same key, same result; replaced inside the service only when QIDI's method looks exactly as expected, and QIDI's own method does the job if anything goes wrong. Seen in a real print (24.11.2026): the model loaded in 43 blocks, and after the print the service went from 177 to 135 MB. Whether it lowers the lowest free memory is NOT proven (85 MB in a 1 h print, the same range as before). |

## OrcaSlicer profiles (on your PC)

See the README: printer profiles "(Tweaked)" with Normal Lift and chamber fan off at the end, and `[TL]` timelapse processes.

## Not included

- Bed mesh only under the first layer (`adaptive-bed-mesh`, in 1.1.0): withdrawn after the 20.11.2026 test print. QIDI's
  own macro (KAMP, `klipper-macros-qd/KAMP_Settings.cfg`) already narrows the mesh to the objects in X (Y always whole);
  the module could not read OrcaSlicer's `.gcode.3mf` files and QIDI's macro ignored the area it passed on. The gain
  (a few probe points less) was not worth an extra layer over QIDI's.
- Old timelapse parking / vertical photo lift / photo-return wait: withdrawn, OrcaSlicer handles the parking.
- Corner parking choice and printer-side parking: not needed with OrcaSlicer.
- Box fixes are added only for problems people actually reported (GitHub / Reddit).
- Valve-Oil's Box fixes for the Max 4 / Plus 5 (load-cell timers left behind after every Box load, `INIT_RFID_READ`
  at startup, `LOAD_FILAMENT_CONTROL` / `FLOW_STOP` problems): checked against the Q2's 02.04 code, which is an older
  QIDI Box and probe code without those parts - not needed. Its Moonraker cloud-handshake fix: not ported, the Q2's
  QIDI cloud module is compiled and the fix depends on its internals.
- Root filesystem mounted `sync`: QIDI's Rockchip start script (`rockchip.service`) switches `/` to `sync` for a
  first-boot setup that always fails on the Q2 (the RK3308 is misspelled in the script and the packages are missing), so
  it happens again at every start. Measured on the Q2: small
  writes are much slower (about 2.5 ms each), but Klipper and Moonraker write their logs in separate threads and a
  2 h 46 min print showed no timing problems. Left as it is on purpose: with `sync` nothing written is lost when the
  printer is switched off at the mains or loses power (Z offset in `saved_variables.cfg`, history, logs).
