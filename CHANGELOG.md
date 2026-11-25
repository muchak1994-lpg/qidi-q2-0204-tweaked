# Changelog

## Unreleased
- `ai-fixes`: the foreign-object check at the start of a print switches the case light on itself (if it is off) and waits 5 seconds before it starts the AI. Why (test on the printer without a print, 26.11.2026): started at once with the light, the AI wrote a "foreign object" alarm within four seconds in 2 of 2 runs, from badly exposed, completely white frames of an EMPTY plate (the screen window appeared while the console said "nothing found"); started 5 s after the light it wrote no alarm in 0 of 2 runs. Measured on the camera stream: the frames 1.5-2.5 s after the light came on scored 0.83-0.90 "foreign", from 3.3 s on 0.03-0.18. The wait is written in the console, the check stops at once when the print is cancelled or paused during it, and the stored alarm is still cleared first. A print starts about 5 seconds later. Still open: the position of the toolhead before the axes are homed may be a second source of false alarms (not tested). Not seen in a real print yet.
- `ai-fixes`: the foreign-object check at the start of a print now writes down WHEN. (1) If the AI reports an object in the first 6 seconds (which the check does not judge), the console and `klippy.log` get a line with the date and time of the report, and that this print is not paused by it. (2) If an AI alarm (`qdc_ai_error_code` with `foreign` above 0) is already stored when the print starts, a line says so, with the time the alarm was raised (from its `time=`) and the time the print started. Why: on 25.11.2026 the printer screen showed the AI's window "Foreign object detected on platform" (QDC_500_005_005_001) through two whole prints on an empty plate, while the console and the log said "nothing found"; the AI itself had raised the alarm about 4 s after the check started, inside the seconds the check does not judge (and in the second print the alarm was probably the stored one from the first, a hypothesis). (3) The log also says where the toolhead and the bed stand (X, Y, Z and the homed axes) and whether the case light is on or off at the start of the check and at the time of such a report (a line with the date and time). Only log lines are added: the verdict, the pause logic and the AI's own alarm are unchanged, and the window on the screen cannot carry a time (its text is a fixed file of the screen program). Tested offline (5 new tests, both main ones fail without the change); not installed on a printer and not seen in a print.
- `ai-fixes`: the AI alarm text that the printer screen reads (`qdc_ai_error_code` with `status=1`) is cleared at the end of every print (complete, cancelled, error, standby) and when the foreign-object check starts, each time with a log line that says what was cleared and when. Why: the old pre-print check of QIDI cleared it before it started (its code is still in the stock `save_variables.py`, commented out), the check restored by this project did not, and the screen program decides whether to show its "Foreign object detected" window from this text each time the print state changes (found by reading the screen program, 25.11.2026). So an alarm left from one print opened the window again 0.15 s after the start of the next one (seen in the second print of 25.11.2026: the window with nothing new in the log). The first alarm of a print, raised by the AI itself, is not changed, and neither is a pause; the window on the screen is still closed by pressing a button (that the end-of-print clearing does not close it is a reading of the screen code, not seen). Tested offline (5 more tests, 24 in the file). Seen on the author's printer on 25.11.2026 in four start-and-cancel tests on an empty plate (camera picture before): the AI reported an object in 2 of the 4 (at 4 s and at 1 s after the check started, the case light already on), in one of them our check found an object too after its first 6 seconds, and the end-of-print clearing wrote `foreign=0 status=0`.
- `ai-fixes`: when the AI reports an object at the start of a print (in the first seconds or after them), the foreign-object check saves the pictures the AI looked at (`/history_frames?type=foreign`, up to 3) and one current picture (`/capture`) as JPEG files in `/home/qidi/printer_data/logs/q2-alarm-frames/` (the newest 12 files are kept) and says so in the console and the log. Why: on 25.11.2026 the printer reported an object on an empty plate in 2 of 4 tests and not a single picture of what the AI had seen existed, so nobody could tell a mistake of the model from a real object or a bad exposure. Only reading and a few small files; nothing in the verdict, the pause or the alarm changes. Tested offline (5 tests; the three main ones fail without the change); not installed on a printer yet and not seen with real pictures (the format of the answer of `/history_frames` is a guess from the code and the audit: a list of base64 texts or of objects with an `image` field; an empty list was seen).

## 1.4.1 - 2026-11-25
Seventh release: small fixes, no new features. Everything else is as in 1.4.0. Not tested in a real print yet: the brightness gate in the dark, prints of 10 hours or more, a power cut on the zram kernel. Memory measurements on the zram kernel (author's printer, one variant, n=2 prints) are in the project notes, not a claim for every printer.

- Removed the optional module `algo-app-recycle` (`--with algo-app-recycle`, which restarted the AI service two minutes after a print). `algo-app-stream-decrypt` now gives the noodle model back after a print by itself (seen on the author's printer on 24.11. and 25.11.2026: the model is released two minutes after the end, the service keeps running), and it was the one module that restarted a service on its own. It gives back less than the restart did (on a stock kernel 177 to 135 MB, against 193 to 97 MB after a restart); the owner decided that is enough. The module is not part of the installer any more. If you installed it earlier, it keeps working until you remove it: `sudo systemctl disable --now q2-algo-recycle`, then `sudo rm -r /etc/systemd/system/q2-algo-recycle.service /usr/local/lib/q2-algo-recycle`, then `sudo systemctl daemon-reload`. Or run `py tools/install.py uninstall --host PRINTER_IP` and then the installer again (the uninstall takes out the files an earlier install added, using the backup in `backups/` on your PC; not tried yet for a module that is no longer in the project). Re-installing the official 02.04 package from USB does not remove it: that puts back QIDI's files only. Without `algo-app-stream-decrypt` nothing gives the model back after a print any more.
- Docs: the module list in `docs/FIXES.md` and `docs/FIXES.pl.md` was missing nine modules (`algo-app-gate`, `algo-app-malloc`, `algo-app-oom-priority`, `algo-app-recycle`, `algo-app-stream-decrypt`, `printer-screen-view`, `printer-screen-touch`, `update-notice`, `maintenance-reminders`); they are listed now, with what was and was not seen on a printer. The README module count (71) was out of date: 80 modules, 72 installed by default and 8 optional. Corrections to the 1.3.2 notes below: both the console filter for the screen-state echo and the new short screen line (`Light sync: screen OFF, ...`) were seen on 24.11.2026 in Fluidd's console after the release, including in the history of a print; the notes say "not yet seen".
- `ai-fixes`: the foreign-object check at the start of a print asks the AI service again when the first answer is late (up to 5 tries, one second apart, so at most about 5 s); until now one missing answer within 0.2 s skipped the whole check ("PEI foreign object check: unavailable; continuing without popup."). Seen once, on 25.11.2026 in the first print on the zram kernel, after the AI service had been swapped out overnight (its memory use had dropped from about 87 to 35 MB); that this is the cause is a hypothesis, not proven. A service that answers with an error, or does not exist, is not waited for: the print still goes on without the check. Tested offline, and on the author's printer on 25.11.2026 (zram kernel, AI service paused with SIGSTOP at the start of a print): silent for 2 s the check still ran ("nothing found"); silent for 4 s or 10 s it gave up after about 4-5 s ("unavailable", print not paused), and the version without this fix gave up already at 2 s. One trial each, so the limit between 2 and 4 s is a rough measurement. The 0.27 s answer time of a cold, swapped-out service was measured once (n=1).
- `update-notice` looks for a new release every 12 hours instead of once a day (still one small request to GitHub's public 'latest release' address each time; a new release is shown at most one message per version, as before). Tested offline; takes effect when the module is installed.

## 1.4.0 - 2026-11-24
Sixth release: the installer is simpler and less strict about our own files. Everything else is as in 1.3.2. Seen on the author's printer: the installer change (below); the rest of the testing status is that of 1.3.2 - not yet tested in a real print are the brightness gate in the dark, a print on another kernel or with swap, and prints of 10 hours or more.

- Installer, simpler and less strict about OUR files: a text file that our modules edit (the Fluidd web page, Klipper and Moonraker `.py` files) is now also accepted when it is the 02.04 original everywhere EXCEPT in the places our modules edit, whatever stands in those places. Until now such a file had to match the SHA-256 of a result we had produced, so a printer with only some of the optional modules, or with an older release of one edit, was refused (found by a user). The hash list stays as the first, quick check and is still used for the binary files; this is only a second check after it, so nothing that was accepted before is refused now. A change anywhere else in the file (another tool, a hand edit, a different Fluidd) still stops the installer. Checked offline on the real 02.04 files: every file that releases 1.0.0 to 1.3.2 can produce, for each module alone and for all together (246 files), is recognised; 600 random single-byte changes outside our places are all refused. Tried on the author's printer (24.11.2026): `index.html` set to the file of the user's report (original plus drying and screen-view scripts, SHA-256 214c6c1a...), `plan` with the full set and without the screen modules both accepted it as ours, and a normal install put the file back to the all-modules version (same SHA-256 as before the test).

## 1.3.2 - 2026-11-24
Fifth release. Contains a fix for a user's installer problem, new optional modules and the first real print with them. Seen in a real print on the author's printer (24.11.2026, 1 h PLA tube, stock kernel, old `q2-algo-recycle` off): the model loaded in blocks, the model released 2 min after the end, the "PEI foreign object check" lines (at the start of the print: "looking at the plate" / "nothing found"), the phone messages at start, 25/50/75 % with photo buttons, the timelapse video, and the Fluidd console without the echo lines. Lowest free memory 85 MB (81 MB just after the end), no OOM, no restart. NOT tested in a real print yet: the brightness gate in the dark, a print on another kernel or with swap, long prints (10 h and more), the new short screen line on a real screen change, the installer fix on the user's printer (tested offline, with his file's exact SHA-256).

- Installer: a Fluidd web page (`index.html`) with just SOME of our optional modules (for example the drying button and the screen window without the touch button) was refused with "neither the 02.04 original nor a version of ours", although every byte was ours; the installer knew only the result of all modules together and of earlier releases. It now also accepts every mix of our modules that edit that file (found by a user: his file is the original plus the two script tags, SHA-256 214c6c1a...). Tested with synthetic modules and with the real files offline; not yet seen on his printer. A file with anything else in it is still refused.
- `fluidd-console-filters`: the filter for the screen-state echo never matched (Fluidd adds the `$ ` in front of a command only when it draws the line, the filters see the raw text); it now looks for `SMART_STATUS MODE=`. The installer replaces the old value, but only when it is exactly the one this project shipped before; a value you wrote stays. Labels of existing filters are refreshed too (switch on/off is never touched). Not yet seen on a printer.
- New module `update-notice` (installed by default, `--skip update-notice` leaves it out): once a day the printer asks GitHub for the latest published release
  (one HTTPS request, generic name `q2-update-notice`, nothing about you) and, when it is newer than the installed version, shows one
  message per release (Fluidd console, printer screen, and phone when phone-notifications is installed): "New TWEAKED version X.Y.Z
  (currently A.B.C). Download and install with the help of a computer." It never downloads or installs anything, never speaks during a
  print, accepts only plain-digit tags, and has an off switch file. Tested offline against fake GitHub and Moonraker servers (19 tests);
  installed on the author's printer and seen on 24.11 with a faked lower version: phone message, window on the printer screen and red line in the Fluidd console; never yet with a really newer release. Release step: `modules/update-notice/files/VERSION` must equal `VERSION` (a test checks it).
- New optional module `algo-app-stream-decrypt` (`--with algo-app-stream-decrypt`): the AI service decrypts its 44.6 MB model block by block
  (1 MiB) instead of holding three whole copies for a moment (about 134 MB more than needed when the model is loaded in a print's second layer;
  worked out from the service's code, not measured). Same key, cipher and result file, byte for byte; a replacement for that one method, applied
  inside the service after QIDI's module is imported (no file of QIDI's is edited), only when the method still looks exactly as expected, and QIDI's
  own method does the job if anything goes wrong. Tested offline (26 tests, including real AES). The block-by-block part is installed on the author's
  printer; seen in a real print on 24.11.2026: the model was loaded in 43 blocks of at most 1 MiB (44.6 MB) in the print's second layer. Lowest free memory of that 1 h print was 85 MB, inside the range of earlier prints of the same length, so this is NOT a proof of a gain.
  Second part of the same module (separate off switch `Q2_STREAM_RELEASE=off`, tested offline with a fake clock; installed, and seen in the same print: "noodle model released after the print (process memory 177 -> 135 MB)" 2 min 4 s after the end): the
  service gives the noodle model back 120 s after a print (QIDI's own `detector_release()`, garbage collection, `malloc_trim`) instead of keeping
  ~100 MB until a restart; never while printing, paused or starting a print; a QIDI change to the objects it looks at makes it do nothing.
- Ghidra scripts used for the screen-program audit are now in `tools/ghscripts/` (four small scripts and a README; no QIDI code or binary).

## 1.3.1 - 2026-11-23
Fix release, no new features. Version 1.3.0 failed its automatic tests on Python 3.9 (and would not have run there): two places wrote files
with `Path.write_text(..., newline=...)`, which only exists from Python 3.10. They now use `open(..., newline="\n")`, which works from 3.9
(`tools/orca_profiles.py` for the `hook` command and profile copies, `tools/orca_machine_hook.py` for the maintainer's profile generator).
A new test (`tests/test_py39_compat.py`) scans tools, tests and module files for this mistake. Nothing else changed since 1.3.0, so everything
the 1.3.0 notes say about what is and is not tested still applies.

## 1.3.0 - 2026-11-23
Fourth release. Everything listed here is installed on the author's printer except the OrcaSlicer changes (profiles and `hook` command, tested
offline and by slicing in OrcaSlicer 2.5.2). Seen in the first real print with these modules (23.11.2026, 52 min): the phone messages at 25/50/75 %
and the end, the print-hours counter, KAMP, the timelapse notes and video, and the AI service's memory (flat, no restart). Not tested in a real
print yet: the brightness gate in the dark, the new "PEI foreign object check" lines, the "Get a timelapse" link buttons at the end of a print
(link buttons tried by hand), the Fluidd console filters on screen, `algo-app-recycle`, a full first install and uninstall with the new installer
on a printer, and the chamber-fan code from the OrcaSlicer printer profiles on a printer (only the first filament counts; a Box with mixed
materials is not handled).

- Console: every screen on/off change printed three lines (`$ SMART_STATUS ...`, `// SMART_STATUS state updated ...` and the light line). Now it is
  one: the two SMART_STATUS lines are hidden by `fluidd-console-filters`, and `console-english` shortens the light line from
  `[smart_output_pin caselight] Lighting sync: SCREEN=OFF, PRINT=standby, AI=1, TIMELAPSE=1 -> LIGHT=OFF` to
  `Light sync: screen OFF, standby, AI=1, timelapse=1 -> LIGHT=OFF` (same values; MODE is always 1 when this line appears). Not yet seen on a printer.
- `fluidd-console-filters`: two more hidden lines, the echo of the phone-message command (`RUN_SHELL_COMMAND CMD=q2_notify ...`, with the raw
  message text) and of the update notice's `RESPOND TYPE=error MSG="New TWEAKED version ...` (the red line with the message stays). Seen in
  Fluidd's console on 24.11.2026; the new filters themselves are not yet seen working on a printer.
- New module `fluidd-console-filters`: hides two internal lines in Fluidd's console, the echo of the timelapse's per-frame command
  (`MACRO=TIMELAPSE_TAKE_FRAME VARIABLE=takingframe`, one per layer) and the AI service's status code
  (`SAVE_VARIABLE ... qdc_ai_error_code`, e.g. `noodle=0 status=0`, written when the service restarts). Two "contains" filters in Fluidd's
  console filters (Moonraker database, so every browser); the lines are only hidden from the display, the log keeps them. Your own filters
  and a filter you switched off stay; uninstall puts the saved list back. The readable lines stay ("Timelapse is on: layer N/total",
  "PEI foreign object check: ...").
- OrcaSlicer: for printer profiles added by 1.2.0 or older (no fan code) there is `py tools/orca_profiles.py hook --apply`: it adds the
  fan code to the project's `(Tweaked)` printer profiles that have none, keeps print_host, the API key and everything else, leaves a profile with
  its own before-layer code alone, makes a zip backup first and bumps the profile's `updated_time`. The installer's OrcaSlicer step now says
  when it finds such a profile and when OrcaSlicer is older than 2.5.2 (the version the code was checked with). When OrcaSlicer has several user
  folders the installer takes the one named in `OrcaSlicer.conf` (`preset_folder`) instead of stopping to ask.
- OrcaSlicer: the chamber fan (M106 P3) per material now comes from the printer profiles `Qidi Q2 ... (Tweaked)`
  (`before_layer_change_gcode`, once before layer 1, from the first filament's type: PLA/TPU 100 %, PETG 75 %, PA 25 %,
  ABS/ASA/PC none - the same values as before), not from 331 `(Tweaked)` copies of the library filaments. OrcaSlicer lists
  user presets flat, so the copies filled the list; the ordinary grouped filaments are used now. `orca-profiles/filament/`
  and `tools/orca_filaments.py` are gone, `tools/orca_machine_hook.py` writes the hook into the four printer profiles
  (taken over from the 03.02 port). `orca_profiles.py uninstall` still removes the old copies (unchanged ones) after a zip backup.
  Checked by slicing in OrcaSlicer 2.5.2 only (not on a printer); only the first filament counts.
- `phone-notifications`: a failed attachment upload is no longer silent. The upload may take up to 15 min (it is stopped after 30 s without any data) and is
  treated as failed when the server refuses it (`--fail`); then the same message goes out as plain text with "(the attachment could not be sent)".
  Found on the first real print (23.11.2026): the public ntfy.sh answers 413 ("attachment too large, or bandwidth limit reached") to a 3 MB or 6.4 MB
  timelapse video from the printer, a 200 kB file goes through; the old 60 s limit hid it completely.
  So the video is no longer uploaded: the button "Get a timelapse" (was "Show timelapse") now sends a message with link buttons that open the file from the printer's
  own web server, one per address it has ("Home network", "Tailscale"; read from the printer when the message is made). New `--view LABEL=URL` option in the sender.
- `ai-fixes`: the pre-print foreign-object check always ends with a result line and no longer shows the internal command name. Every line now starts with
  "PEI foreign object check:", a clean check says "nothing found.". Fixed: when the AI service ended its own 15 s window and zeroed its counters the loop
  returned silently, so the console showed only "looking at the plate" (real print 23.11.2026).
- `timelapse-progress-note`: the console note comes every 50 layers instead of every 20 (still also at layer 1).
- Installer: faster (23.11.2026, measured on the real printer over Tailscale). A plan with nothing to change went from 25-29 s to about 10 s,
  installing one file from about a minute to 16 s; the first run (empty cache) from about 25 s to 17 s. The printer's files are no longer
  hashed again each time: the PC remembers a hash together with the file's identity on the printer (size, ctime in nanoseconds, inode;
  `work/hash-cache-<printer>.json`) and hashes only files whose identity changed, in parallel chunks; `--rehash` ignores the memory for one run.
  Also fewer round trips: all service checks in one command, config files read in one command, owner/mode of the backed-up files in one
  command, and a written file is verified in the same command as the write. Modules are unchanged (still one by one, `--skip` works per module).
- New optional module `algo-app-gate`: brightness gate for the AI service. With the case light off the camera frame is almost uniform dark
  grey with the toolhead's green/red LEDs, and the noodle model read the LEDs as noodle in about 3 % of the dark frames (lab, 978 real
  frames: 20 false positives on 652 dark frames at MEDIUM, 0 on 326 light frames); the service counts them for the whole print and never
  forgets them. One file of our own, `cv2/q2gate/__init__.py`, is loaded by OpenCV's own loader; the wrapper around `cv2.VideoCapture`
  hands a frame with mean grey below 22 to the models as a uniform frame (19), every other frame untouched. No QIDI file is changed;
  remove = delete the file. Log lines start with `q2gate`; off without restart: `echo off > /etc/q2-algo-gate.conf`. Note: the wrapper is
  never a subclass - a Python subclass of `cv2.VideoCapture` crashes the printer's OpenCV 4.12 (aarch64) with `free(): invalid pointer`
  (measured; a first version did it and the service restarted every few seconds). Measured at rest: CPU 7.2 % of one core vs 6.9-7.0 %
  without the gate, free RAM the same. Seen on the idle printer; not seen in a real print yet.
- Phone notifications: the end of a print is now reported correctly (22.11.2026). On the QIDI printer print_stats jumps to "standby"
  and is wiped the moment a print ends, so a finished print was reported as "Print cancelled ... layer 0/0 after 0 min". The macro now
  remembers file name, layer, time and filament while the print runs and sends both texts; the sender asks Moonraker's history
  (`q2_notify_eta.py --end`) and picks "Print finished" (with time, grams or metres of filament, timelapse button), "Print cancelled",
  "Print stopped" (error, shutdown) or, without an answer, "Print ended". Tested with a pretend Moonraker; a real print end not seen yet.
- `printer-screen-touch`: dragging in the "Printer screen" window now scrolls the printer's screen (a swipe: press, move, release),
  and the browser's own "drag the picture" is switched off. The moving part is not proven on the real touch panel yet (only the tap was).
- New optional modules for the AI service's memory (all three came from the memory audit of 22.11.2026; not proven over many prints):
  `algo-app-oom-priority` (default on: the kernel's out-of-memory killer takes `algo_app` first and protects Klipper and Moonraker),
  `algo-app-malloc` (`--with`: `MALLOC_ARENA_MAX=2`, effect not measured) and `algo-app-recycle` (`--with`: restarts `algo_app` two
  minutes after a print when it is over 130 MB, never starts a stopped one, never touches a printing or paused printer).
- `ai-fixes`: the pre-print foreign-object check (M4050) no longer judges the first 6 seconds (the camera is badly exposed right after
  the light comes on; on real frames of an empty plate that was the only false alarm). The check still takes its 20 s.
- Phone notifications (ntfy), message texts reworked after the first real print (22.11.2026):
  * No more icons: every message goes out without tags (no rocket, camera, hourglass, check mark, warning, wrench, tada, movie camera
    in front of or under the title). Priorities stay, so a pause still rings louder.
  * "Print started" now says how long the print will take: the slicer's whole estimate and the finish time (e.g. "estimated 4h 58m, done at 19:51").
    Left out when the print file carries no estimate.
  * The "Camera" message (the reply to "Get a photo") now has its own button "Get another photo", so the next picture needs no
    scrolling back to the first message. The message stays after the tap, like the first one.
  * Pause and cancel messages no longer say "Layer 0/0": before the first layer they say "Before the first layer" (e.g. the check for foreign
    objects at the start), with the layer numbers they show "Layer 12/100, 12%". Not seen on a real printer yet (tests only).
- New optional module `printer-screen-view` (`--with printer-screen-view`): a "Printer screen" entry in Fluidd's left navigation
  panel opens a window with a live picture of the printer's touch screen (about twice a second while open). Look only: no touch,
  nothing sent to the printer. A small service reads `/dev/fb0` and serves it on 127.0.0.1 (shown through Fluidd's unused `/webcam4/`).
  Installed and seen working on the author's printer (idle); not watched during a print yet.
- New optional module `printer-screen-touch` (`--with printer-screen-touch`, needs `printer-screen-view`): a "Touch" button in the
  "Printer screen" window. Off every time the window opens; when switched on, a click in the picture presses the same place on the real
  touch screen. Separate small service (127.0.0.1 only; accepts only same-site JSON, 4 taps a second at most). Coordinates 1:1 with the
  480x272 picture, from one test on 06.11.2026; tried on the printer on 22.11.2026 (all taps from the Fluidd window hit their place, up to the drying page; nothing was started).
- `printer-screen-touch` / `printer-screen-view` hardening (from a security audit, 22.11.2026; the touch part was only ever "off" as a
  variable in the Fluidd page, so any client on the network could POST a tap):
  * Touch is now off **in the service**: it must be armed first (`?action=arm`, valid 60 s, renewed every 20 s by the open window while its
    Touch button is on; `disarm` on switching off, closing the window or leaving the page; off after every service start). A tap without
    arming gets 403. Every request must also carry `X-Q2-Touch: 1`, so a page of another site needs a CORS preflight, which is never granted.
    Honest limit: a client that knows the protocol can still arm and tap, like it can already use Moonraker (printer commands, E-STOP) on this network.
  * The root scripts moved from `/home/qidi/q2-screen/` (writable by Klipper/Moonraker) to `/usr/local/lib/q2-screen/` (root only); the update removes the old copies.
  * A tap always sends its "release", even if a write fails or the service is stopped in the middle of it (SIGTERM).
  * The window clicks only on a loaded 480x272 picture shown less than 1.5 s ago; no refresh while the tab is hidden; an error message
    clears with the next good picture and the touch warning has its own line.
- Installer: a new systemd service is now enabled in the same run that installs its unit file (before, the first run only
  copied the files and "enable" had to be repeated by running the installer a second time).

## 1.2.0 - 2026-11-21
Third release. Everything listed here is installed on the author's printer. Not tested in a real print yet: the phone
messages (ETA below 50 %, "Get a photo", filament in grams), the maintenance reminder after a real print (only forced on
the screen), the bed mesh, and the Upload & Print guard repairing a really broken Fluidd (stand-in tests only).

- New module `maintenance-reminders`: counts the printer's print hours and, after a print that crosses a multiple of an interval,
  shows an extra window on the printer screen (and sends a phone message when `phone-notifications` is installed): X/Y rails every
  100 h, Z lead screws and fans every 300 h of printing, as two separate windows/messages (QIDI's manual: rails every 2-4 weeks,
  Z screws every 1-3 months). Only a notice, once per interval, no buttons. `TWEAKED_MAINT_STATUS` shows the hours.
  `phone-notifications`: the Photo button is now "Get a photo".
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
