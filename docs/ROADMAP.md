# Roadmap

Modules planned for the installer. Each one is checked against the stock 01.01.02.04 files and can be undone from the PC-side backup.

| Module | What it fixes or adds | State |
|---|---|---|
| Official package | Download from QIDI, SHA-256 check, index of all original files (`tools/firmware.py`) | **ready** |
| Printer check | Read-only: confirms 01.01.02.04, lists original / changed files (`tools/printer.py`) | **ready** |
| OrcaSlicer profiles | Printer profiles with chamber-fan-off end G-code and Normal Lift; `[TL]` timelapse processes | **ready** (`tools/orca_profiles.py`) |
| Update blocking | Keeps 02.04 from being replaced by an automatic update (mandatory) | tested on one printer, being packaged |
| Screen program | Rebuilt from the official package on the PC: print-queue and file-info fixes, update check off, dark-mode light popup | tested on one printer, being packaged |
| AI libraries | Missing Python libraries for the camera AI, downloaded from PyPI / Debian and verified by checksum | sources verified, being packaged |
| Dark mode light | Light off during a print = light and spaghetti detection off until the print ends; tap the screen for temporary light | tested on one printer |
| Hotend fan hysteresis | Fan no longer flickers around 50 °C; no false fan alarm on reheat | tested on one printer |
| Fuzzy skin (extrusion mode) | Fixes skipped small moves / doubled extrusion in fuzzy-skin extrusion mode | tested on one printer |
| Ethernet MAC | Stable MAC address from the first boot (QIDI issue #28) | tested on one printer |
| Box heater fixes | QIDI issues #23 and #34 | planned; the author has no Box, testers needed |
| Purge / wipe macro | Extra macro (does not replace the stock one), turns heaters and fans off afterwards | in the author's set, being packaged |
| MCU temperatures | Shows the MCU temperatures | in the author's set, being packaged |

"Tested on one printer" means it runs on the author's Q2; more testers are welcome.
