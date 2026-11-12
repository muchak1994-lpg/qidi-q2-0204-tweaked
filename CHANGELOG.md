# Changelog

## Unreleased
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
