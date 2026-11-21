# QIDI Q2 02.04 Tweaked

**English** · [Polski](README.pl.md)

Community fixes and small improvements for the **QIDI Q2** 3D printer running firmware **01.01.02.04** — and only that version.

> **Unofficial project.** Not affiliated with, endorsed by or supported by QIDI Technology. You use it at your own risk. Keep the official firmware package at hand so you can always go back to stock.

> **Status: 1.2.0.** All modules build from the official packages and match a tested printer byte for byte; every module has been installed (and upgraded) with this installer on the author's printer, the installer is tested offline against a simulated printer, and a full install was done on a freshly reflashed printer (14.11.2026). See [docs/ROADMAP.md](docs/ROADMAP.md).

## What it fixes

71 small modules: screen program (print queue from 03.02, update popup off, dark mode for the light,
filament drying fixes), Klipper fixes (bed mesh probe retries, homing, fuzzy skin, hotend fan, QIDI Box heaters
and fan threshold, MCU errors, safe settings saving and more, several from upstream Klipper), macros (Z homing
guard, load temperature after a hotter filament, drying from Fluidd), Moonraker/Fluidd fixes, stable Ethernet MAC,
and the missing camera-AI libraries.
**Full list with the problem each one solves: [docs/FIXES.md](docs/FIXES.md).**

## Principles

- **02.04 only.** Every change is checked against the exact 01.01.02.04 files (SHA-256). On any other version the installer refuses to run.
- **Firmware updates stay blocked.** The fixes are made for 02.04; an automatic update would silently replace them. Blocking updates is part of the package, not an option.
- **No QIDI files in this repository** (only the short lines our changes replace). The installer downloads the official 01.01.02.04 package from QIDI's public server, checks its checksum, and applies the changes on your PC.
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

### Toolhead accelerometer check (read only)

QIDI's Q2 toolhead firmware has a known bug: the accelerometer delivers about 390 samples a second instead of 1600
([QIDI_Q2 #39](https://github.com/QIDITECH/QIDI_Q2/issues/39)), and most Q2 printers have it. At the end of the
install the installer asks whether to check yours (`--toolhead yes|no` answers in advance). The check only reads
the toolhead's memory, tells you whether you have the bug and what is recommended, and keeps a backup of the
toolhead firmware on your PC. Nothing is flashed: the optional manual fix is described in
[docs/TOOLHEAD_ACCELEROMETER.md](docs/TOOLHEAD_ACCELEROMETER.md) and is done at your own risk.

### Remote access (optional Tailscale)

QIDI's cloud does not serve printers on 02.04, so the QIDI app cannot reach the printer from outside your home.
At the end of the install the installer offers **Tailscale** (free, by tailscale.com): Fluidd, OrcaSlicer
uploads and the camera from anywhere, privately - only devices logged in to your own Tailscale account can
reach the printer. Answer Enter (yes) or `n`. The official build of a version pinned in this project is downloaded on the PC and
checked by SHA-256; it uses about 40 MB of the printer's memory. Moonraker is told to trust Tailscale addresses
(like the home network), otherwise Fluidd and OrcaSlicer would get error 401. The login link is shown in the
window only, never in the log - do not share it. The installer can show the login link right away, or you
log in later (run the installer again, or over SSH: `sudo tailscale up --accept-dns=false --hostname=qidi-q2`).
`--tailscale yes|no` answers the question in advance. Uninstall removes Tailscale if the installer added it.

### Phone notifications (optional, ntfy)

At the end of the install, one after the other with the other optional extras (each: question, yes = done right away, no = next question), the installer asks whether to set up messages on your phone: print started, 25/50/75 %, finished, **paused with the reason**
(with a camera picture and Resume / Cancel buttons), errors, and the timelapse video on a button. It uses the free ntfy app and
server (ntfy.sh) - no account, no phone number; or your own ntfy server. The installer shows a random channel name to subscribe to in the app
(in the window, and saved in a file `backups/notify-<printer address>-channel.txt` on your PC so it is not lost when the window closes) and sends a test message. `--notify yes|no` answers in advance; uninstall removes it.
Anyone who knows the secret command channel could resume or cancel a paused print, so keep the settings private.

## Go back

```
py tools/install.py uninstall --host PRINTER_IP
```

Everything is put back from the PC backups (all runs of the installer for that printer, so keep the whole
`backups` folder, and run updates from the same project folder); calibration saved since stays.
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
| `<filament> (Tweaked)` (filaments) | Chamber fan per material — see below. Added for the filaments enabled in your OrcaSlicer; the others you can import. |

The installer (`install.bat` / `tools/install.py install`) asks at the end whether to add them on the computer it
runs on (`--orca yes|no` to answer in advance). Or by hand (OrcaSlicer must be closed):

```
py tools/orca_profiles.py install            # shows what it would add
py tools/orca_profiles.py install --apply    # adds the profiles
py tools/orca_profiles.py status
py tools/orca_profiles.py uninstall --apply  # removes only what it added, if unchanged
```

On macOS/Linux use `python3` instead of `py`. If you are logged in to an Orca account, the profiles folder is named after the account number instead of `default`; the tool asks which one to use.

The profiles contain **no printer address or API key** — set the connection in OrcaSlicer yourself (pencil icon next to the printer → Connection).

### Filament profiles: chamber fan per material

QIDI's own Q2 filament profiles run the chamber circulation fan (M106 P3) during the print for PLA, PETG, TPU and
nylon; the generic OrcaSlicer filament library (SUNLU, eSUN, Polymaker, ... `@System`) leaves it off for every
material. `orca-profiles/filament/` has a `(Tweaked)` copy of every library filament usable on the Q2 (331): it takes
everything from the original and only sets the chamber fan:

| Material | During the print | After the print |
|---|---|---|
| PLA (PLA+, Silk, Matte, PLA-CF, ...), TPU | 100% | 0% |
| PETG (PETG-CF, PCTG, PET-CF) | 75% | 0% |
| Nylon (PA, PA-CF, PA-GF, PPA) | 25% - a little air exchange, the chamber stays warm | 0% |
| ABS, ASA, PC | 0% - as QIDI: these keep the chamber warm | 0% |

QIDI uses 100% for PETG and nylon; 75% and 25% are this project's choice. Other materials (PP, PVA, HIPS, ...) get no
profile. The installer and `orca_profiles.py install` add the `(Tweaked)` copies of the filaments enabled in your
OrcaSlicer (the ones you ticked under "Add/Remove filaments"); enable more there and run it again, or import single
ones: OrcaSlicer → **File → Import → Import Configs...** → open `orca-profiles/filament/<brand>/` and select one or
more `.json` files. They show only with a Q2 printer selected. To remove one: `orca_profiles.py uninstall --apply`
(the ones it added), or in OrcaSlicer: the filament's settings → delete preset. The list of all of them:
`orca-profiles/filament/index.tsv`. A filament your OrcaSlicer version does not know yet is skipped on import.

## License and credits

The code in this repository is licensed under the [GNU GPL v3.0](LICENSE). Each fix's source is named in
[docs/FIXES.md](docs/FIXES.md). Thanks to:

- [Klipper](https://github.com/Klipper3d/klipper) - Kevin O'Connor and contributors (GPL-3.0): several upstream fixes backported.
- [Valve-Oil](https://github.com/thelegendtubaguy/Valve-Oil) - thelegendtubaguy (GPL-3.0): the probe retry fix, same as theirs for the Max 4 / Plus 5, and the Klipper timer and status-update optimizations (adapted to 02.04).
- [n3oney](https://github.com/qidi-community/q2-wiki/tree/main/content/randomize-probing) (qidi-community Q2 wiki): the idea of a random Z homing point to spread the wear on the plate.
- AFSFigueiredo ([QIDI #34](https://github.com/QIDITECH/QIDI_Q2/issues/34)): the Box heater keep-alive fix, tested on 8000+ tool changes.
- ValitovTimur ([QIDI #23](https://github.com/QIDITECH/QIDI_Q2/issues/23)): the analysis of the Box heater "Min or 0" bug and the fix that `box-fixes` implements.
- ololonly ([QIDI #25](https://github.com/QIDITECH/QIDI_Q2/issues/25)): the report and analysis that led to `box-fan-threshold`.
- QIDI: the print queue, the fallback DNS and the Moonraker status merge are taken from QIDI's own 01.01.03.02.
- Earlier work by **Codex** (OpenAI's AI assistant, known around here as "Stefan"), which built the first modules and fixes with the author.
- Built together with **Claude** (Anthropic's AI assistant), which analysed QIDI's code, wrote and tested most of the changes with the author on his printer. The files in `orca-profiles/` are derived from the QIDI profiles bundled with OrcaSlicer; see [orca-profiles/NOTICE.md](orca-profiles/NOTICE.md).

QIDI, QIDI Q2 and related names are trademarks of their owners and are used here only to say which printer this project is for.
