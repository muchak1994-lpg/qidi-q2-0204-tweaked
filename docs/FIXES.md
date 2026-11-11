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

## Klipper (motion, heaters, sensors)

| Module | Problem | Fix |
|---|---|---|
| `fuzzy-skin-extrusion` | QIDI's extruder "accumulator" skips small E moves and counts E twice in fuzzy skin **extrusion** mode: gaps and blobs. | Keeps the slicer's E targets unchanged. Tested with a fuzzy-skin print. |
| `hotend-fan-hysteresis` | The hotend fan switches on/off around 50 °C with no hysteresis, and a reheat while the fan runs can raise a false fan alarm. | Adds hysteresis and closes the watchdog gap. Tested. |
| `box-heater-keepalive` | QIDI Box heaters drying during a print can stop Klipper with "max_duration" (QIDI #34). | Sends the heater keep-alive earlier for Box heaters only; the safety limit is unchanged. Reported fix: 8000+ tool changes, no shutdown. |
| `box-fixes` | Box heater settings are invisible to Klipper's config checker (QIDI #23). | Registers them like the other heater settings. |
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
| `idle-timeout-drying` | Idle timeout 12 h → 5 min (heaters off), separate "pause" / "idle" messages, motors off; chamber drying keeps working. |
| `resume-after-heating` | After a pause, the purge waits until the nozzle is hot again. |
| `park-rear-right` | After a print or a stop the head parks at the rear right, so the camera sees the bed. |
| `external-filament-load-finish` | After an external filament load: fan and heater off. |
| `end-guard` | Chamber heater and fans off at the end of a print and when drying ends. Tested. |
| `filament-wipe` | Extra purge-and-wipe macro (`FILAMENT_WIPE`); does not replace QIDI's own. |
| `drying-skip-homing` | Filament drying preparation (`prepare_filament_dry`, used by the screen and by the Fluidd drying window) homes only when the axes are not homed yet, instead of every time. Tested from the screen and from Fluidd. |
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
| `fluidd-drying-button` | A "Filament drying" entry at the end of Fluidd's left navigation panel (phone and computer). It opens a window with the printer screen's own settings (15 filament types, build plate temperature up to 100 °C, time 1-24 h) and sends the same commands as the screen (`prepare_filament_dry`, `SET_FILAMENT_DRY`). Fluidd's own program file is not changed. Tested: lower the bed, start, time left, stop. |

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
