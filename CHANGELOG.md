# Changelog

## Unreleased
- New module `screen-drying-countdown-roundup`: the screen's drying time left is rounded up (a 5-minute
  drying shows 05min, 04min ... 01min instead of 04min ... 00min; above one hour whole hours rounded up).
- Drying end: the printer beeps like at the end of a print (`idle-timeout-drying`), and the screen wakes up
  (`screen-drying-autoshow`). A drying start from Fluidd also wakes the screen and the chamber light, which
  then go to sleep by themselves as after one touch.
- Drying start is refused (screen, Fluidd, console) unless the bed is lowered (Z ≥ 190, `prepare_filament_dry`).
  In the Fluidd window Start stays grey with a hint until the bed is lowered, and Stop is grey when nothing
  is drying.
- New module `screen-drying-start-button`: the screen's drying Start button no longer stays grey after a
  screen restart during drying. When drying ends the screen stays on the drying page (as in stock firmware).
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
