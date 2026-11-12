# What the modules fix

**English** · [Polski](FIXES.pl.md)

Every module is a small, separate change against the original QIDI 01.01.02.04 files. All of them run on
the author's Q2; "tested" below means a specific physical test on that printer beyond normal use.
List them with `py tools/build.py --list`; leave one out with `--skip MODULE`.

Sources in brackets: **QIDI #nn** = issue in [QIDITECH/QIDI_Q2](https://github.com/QIDITECH/QIDI_Q2/issues),
**Klipper** = backport of an upstream Klipper fix.

## Screen program

| Module | Problem on stock 02.04 | What the module does |
|---|---|---|
| `screen-program` | The screen program can crash on rare MCU/toolhead events, and its print history can get out of sync. | Rebuilds the screen program on your PC from QIDI's 02.04 program plus the print-queue code of QIDI's own 03.02 program, and adds the history sync and version entry. Every build stage is SHA-256 checked. |
| `update-check-off` | A "new firmware" popup pushes the online update - which would replace 02.04 for good. | Turns the update check off (one byte in the screen program). |
| `firmware-download-guard` | The printer can download an update package in the background. | Makes the download folder read-only (immutable flag). Undo: `uninstall`. |
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
| `box-fixes` | Box heater settings are invisible to Klipper's config checker (QIDI #23). | Registers them like the other heater settings. |
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
| `console-english` | Some console messages are Chinese. | English messages. |

## Macros and configuration

Your calibration (`#*# SAVE_CONFIG` block) is kept: only these lines are edited in your own files.

| Module | What changes |
|---|---|
| `idle-timeout-drying` | Idle timeout 12 h → 5 min (heaters off), separate "pause" / "idle" messages, motors off; chamber drying keeps working. Drying start refused unless the bed is lowered (Z ≥ 190) and while the printer is busy (print, pause, moves, a running task); a stop is passed to QIDI only while drying runs, so it cannot switch the heaters off during a print; a second start and `prepare_filament_dry` refused while a drying already runs (stop first); `prepare_filament_dry` refused while busy; a beep (like at print end) when drying finishes by itself. |
| `resume-after-heating` | After a pause, the purge waits until the nozzle is hot again. |
| `park-rear-right` | After a print or a stop the head parks at the rear right, so the camera sees the bed. |
| `z-home-guard` | "Home Z" on its own (Fluidd's Home Z button, QIDI Studio's device page, the console: `G28 Z`) homes Z with the nozzle as the probe wherever the head stands - also over the purge bin or the plate edge. Home All centres the head first; Home Z alone does not. | Home Z alone is refused unless X and Y are homed and the nozzle is over the build plate (X 0 to under 271, Y 5 to under 271 - at least 5 mm inside the measured PEI edges); the head is never moved for it, the message says to move it over the plate or use Home All. Home All, printing and every QIDI macro are unchanged (the screen's plate calibration homes Z at X240 Y32, inside the area). Same rule as Marlin 1.0's Z safe homing. |
| `z-home-random-point` | The Q2 homes Z by pressing the nozzle on the plate, and Home All always does it at the plate centre - several times per print - wearing the PEI at the spot where most prints sit. | Home All homes Z at a random point within 10 mm of the centre (as suggested in the qidi-community Q2 wiki), only with a fresh bed mesh before every print (G29 k=1, the default); with a saved mesh (k=0) the centre stays fixed so the mesh still fits. |
| `fluidd-z-like-screen` | In Fluidd (also inside QIDI Studio) the down arrow for Z moved the bed **up** towards the nozzle (QIDI's factory Fluidd setting), while on the printer's screen "down" moves the bed down - easy to crush the nozzle. | Fluidd's Z direction setting is set so that it mirrors the printer's screen: down = bed down, up = bed up. X and Y already matched the screen. Reload an open Fluidd page once after installing. |
| `dns-fallback-global` | 02.04's network hook adds the Chinese public DNS 114.114.114.114 and 223.5.5.5 as fallbacks after your router's DNS; with a typical home router one of them ends up in the printer's DNS list. QIDI's 03.02 international package uses 1.1.1.1 and 8.8.8.8. | That one line of the hook is changed to 1.1.1.1 and 8.8.8.8, as in 03.02; the rest of QIDI's hook stays. Takes effect at the next network connect or reboot; uninstall puts QIDI's line back. |
| `moonraker-box-status-merge` | QIDI's Klipper sends only the changed nested parts of the BOX and drying status, but Moonraker 02.04 merged them one level deep, so its status cache lost the other fields (e.g. the drying end time, BOX slot data). The QIDI app gets a full refresh from that cache every 30 s. | Nested status updates are merged recursively - QIDI's own fix from 03.02. Fluidd and the drying window read Klipper directly and were not affected. |
| `external-filament-load-finish` | After an external filament load: fan and heater off. |
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
| `fluidd-fixes` | Fluidd: file and folder names with spaces/special characters, upload/download progress per file, controls usable while paused, SoC temperature, disk usage, sane ETA at print start, keeps server info on a Klipper reset, hides dialogs while disconnected. |
| `send-and-print-guard` | Keeps Fluidd's "Upload & Print" working (checks at boot and nightly). |
| `fluidd-drying-button` | A "Filament drying" entry at the end of Fluidd's left navigation panel (phone and computer). It opens a window with the printer screen's own settings (15 filament types, build plate temperature up to 100 °C, time 1-24 h) and sends the same commands as the screen (`prepare_filament_dry`, `SET_FILAMENT_DRY`). Fluidd's own program file is not changed. While the printer is busy the drying entry shows an in-page "printer is busy" notice instead of the window (like the screen). Start (green) stays grey until the bed is lowered, "Lower the bed" also wakes the screen, Stop is grey when nothing is drying. Tested: lower the bed, start, time left, stop. |

## System

| Module | What changes |
|---|---|
| `ethernet-mac` | The printer's own stable Ethernet MAC address from the first moment of boot (QIDI #28). Generated per printer; active after a reboot. |
| `klipper-priority` | Klipper gets the CPU first (Nice -10). |
| `restart-on-exit` | Klipper and Moonraker also restart after a clean exit. |
| `legacy-qidilink-cleanup` | Old QIDILink / FRP remote services turned off. |
| `journal-retention` | **Off by default** (`--with journal-retention`): system log kept 7 days, up to 2 GB, for diagnostics. |

## Camera AI

> **What "fixed" means here:** on stock 02.04 the camera AI does not work at all (its program is missing
> libraries, and the print flow breaks around the check). These modules make the AI **work as a function**,
> exactly the way QIDI designed it. They do **not** change or retrain QIDI's detection model. How well it
> detects (spaghetti, foreign objects) depends on QIDI's model and on many conditions - light, camera
> position, filament colour, the bed surface - and can vary from print to print.

| Module | What changes |
|---|---|
| `ai-libraries` | 02.04 ships the AI program without 153 of the Python library files it needs. They are downloaded from PyPI and Debian (numpy, onnxruntime, opencv, pycryptodome, psutil, pydantic-core, websockets, chardet, Python 3.9 modules), each checked by SHA-256. Also applies the MEDIUM8 detection setting to the AI program and enables AI autostart. |

## OrcaSlicer profiles (on your PC)

See the README: printer profiles "(Tweaked)" with Normal Lift and chamber fan off at the end, and `[TL]` timelapse processes.

## Not included

- Old timelapse parking / vertical photo lift / photo-return wait: withdrawn, OrcaSlicer handles the parking.
- Corner parking choice and printer-side parking: not needed with OrcaSlicer.
- Box fixes are added only for problems people actually reported (GitHub / Reddit).
