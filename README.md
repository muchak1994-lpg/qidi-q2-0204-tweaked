# QIDI Q2 02.04 Tweaked

**English** · [Polski](README.pl.md)

Community fixes and small improvements for the **QIDI Q2** 3D printer running firmware **01.01.02.04** — and only that version.

> **Unofficial project.** Not affiliated with, endorsed by or supported by QIDI Technology. You use it at your own risk. Keep the official firmware package at hand so you can always go back to stock.

> **Status: release candidate.** All modules build from the official packages and match a tested printer byte for byte; the installer has been tested against a simulated printer and read-only against a real one. A full install on a freshly reflashed printer is the last test before the first release. See [docs/ROADMAP.md](docs/ROADMAP.md).

## What it fixes

44 small modules: screen program (print queue from 03.02, update popup off, dark mode for the light),
Klipper fixes (fuzzy skin, hotend fan, QIDI Box heaters, MCU errors, safe settings saving and more),
macros, Moonraker/Fluidd fixes, stable Ethernet MAC, and the missing camera-AI libraries.
**Full list with the problem each one solves: [docs/FIXES.md](docs/FIXES.md).**

## Principles

- **02.04 only.** Every change is checked against the exact 01.01.02.04 files (SHA-256). On any other version the installer refuses to run.
- **Firmware updates stay blocked.** The fixes are made for 02.04; an automatic update would silently replace them. Blocking updates is part of the package, not an option.
- **No QIDI code in this repository.** The installer downloads the official 01.01.02.04 package from QIDI's public server, checks its checksum, and applies the changes on your PC.
- **Backups on your PC, nothing left on the printer.** Before any change the original printer files are saved on your computer, so every module can be undone. Temporary files on the printer are removed after installation.
- **Add, never replace — on your PC too.** The OrcaSlicer profiles are added next to yours; a profile you already have is never overwritten.
- **Network security is your responsibility.** Keep the printer on a trusted network; do not expose it to the internet.

## Requirements

- QIDI Q2 on firmware **01.01.02.04**, reachable on your local network.
- A PC (Windows, macOS or Linux) with **Python 3.9 or newer** (on Windows: from python.org or the Microsoft Store; the `py` command works).
- For the profiles: OrcaSlicer with a QIDI Q2 printer added at least once.

## Before you start

> **Do not use the screen's online update.** It installs the newest QIDI firmware, which cannot be
> downgraded – you would lose the way back to 01.01.02.04 and this project. Use offline (USB) updates only,
> and only up to 01.01.02.04. See [docs/RECOVERY.md](docs/RECOVERY.md).

- The printer is idle: not printing, not paused, heaters off.
- You know its IP address (screen → network settings) and the SSH password of user `mks`.
- On the PC, open a terminal in this folder (Windows: in File Explorer type `cmd` in the address bar and press Enter).

## Install

**Windows, the easy way:** double-click `install.bat`. It asks for the printer's IP address and goes through
the five steps below, stopping at the first problem. You type the SSH password a few times; it is never saved.

**By hand** (any system):

```
py -m pip install -r requirements.txt          (once: paramiko for SSH, capstone for the screen build)
py tools/firmware.py fetch                     (downloads and checks the official 02.04 package)
py tools/printer.py check --host PRINTER_IP    (read-only: is it 02.04, what is changed)
py tools/install.py plan --host PRINTER_IP     (read-only: what will change)
py tools/install.py install --host PRINTER_IP  (backup on the PC, then install; asks "yes")
```

- The first build also downloads QIDI's official 01.01.03.02 package (about 245 MB; only its print-queue
  code is carried over) and the AI libraries from PyPI and Debian (about 100 MB). Everything is checked by SHA-256.
- The installer stops **before changing anything** if the firmware is not 01.01.02.04, the printer is busy,
  or any file is neither QIDI's original nor ours.
- Your calibration in `printer.cfg` is kept: only our lines are edited.
- The backup goes to `backups/` on your PC. Keep that folder.
- A module can be left out with `--skip MODULE` (list: `py tools/build.py --list`).
- The Ethernet MAC fix takes effect after the next reboot.

## Go back

```
py tools/install.py uninstall --host PRINTER_IP
```

Everything is put back from the PC backup; calibration saved since stays.
Lost the `backups` folder or changed PC? `py tools/install.py uninstall --from-stock --host PRINTER_IP`
puts QIDI's originals from the official package back instead.

**Other modifications on the printer?** The installer only accepts files that are QIDI's 01.01.02.04 originals
or a version of ours. If you installed other fixes, re-install 01.01.02.04 from USB first
([docs/RECOVERY.md](docs/RECOVERY.md), option 2), then run the installer.

**Updating to a newer release** of this project: download it and run `install` again - earlier versions of
our files are recognised and replaced (with a new backup). Changes: [CHANGELOG.md](CHANGELOG.md). Other ways back (re-install of
02.04 from USB, full reflash with the right update order): [docs/RECOVERY.md](docs/RECOVERY.md).

## OrcaSlicer profiles

What you get:

| Profile | What it changes against QIDI's own Q2 profile |
|---|---|
| `Qidi Q2 0.2 / 0.4 / 0.6 / 0.8 nozzle (Tweaked)` (printers) | End G-code that also turns off the chamber circulation fan; Z-hop type **Normal Lift** instead of Auto (Auto lifts in a spiral over the model and can leave spikes). |
| `[TL] ...` (22 processes, one per QIDI Q2 process) | Timelapse **Smooth**: the head parks at the back for every photo, with a 35 mm prime tower. Pick a process **without** `[TL]` when you do not record a timelapse — the parking costs time on every layer. |

Install (OrcaSlicer must be closed):

```
py tools/orca_profiles.py install            # shows what it would add
py tools/orca_profiles.py install --apply    # adds the profiles
py tools/orca_profiles.py status
py tools/orca_profiles.py uninstall --apply  # removes only what it added, if unchanged
```

On macOS/Linux use `python3` instead of `py`. If you are logged in to an Orca account, the profiles folder is named after the account number instead of `default`; the tool asks which one to use.

The profiles contain **no printer address or API key** — set the connection in OrcaSlicer yourself (pencil icon next to the printer → Connection).

## License

The code in this repository is licensed under the [GNU GPL v3.0](LICENSE). The files in `orca-profiles/` are derived from the QIDI profiles bundled with OrcaSlicer; see [orca-profiles/NOTICE.md](orca-profiles/NOTICE.md).

QIDI, QIDI Q2 and related names are trademarks of their owners and are used here only to say which printer this project is for.
