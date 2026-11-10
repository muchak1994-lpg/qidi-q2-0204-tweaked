# Changelog

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
