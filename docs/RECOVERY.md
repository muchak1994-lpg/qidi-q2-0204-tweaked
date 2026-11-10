# Going back: uninstall, re-install 02.04, or full reflash

**English** · [Polski](RECOVERY.pl.md)

> **Never use the screen's online update ("Check for updates" → Update) while you want this project.**
> It installs the newest QIDI firmware (01.01.03.x or later). QIDI firmware cannot be downgraded, so you could
> never return to 01.01.02.04 – and this project only works on 01.01.02.04. The only way back would then be a
> full eMMC reflash (option 3).

Pick the lightest option that solves your problem.

| Option | When | What you lose |
|---|---|---|
| 1. `install.py uninstall` | You want stock 02.04 back, the printer works | nothing – your calibration stays |
| 2. Re-install the official 02.04 package from USB | Something is broken and option 1 is not enough | nothing of QIDI's; files this project added stay until you run option 1 |
| 3. Full reflash of the eMMC, then updates up to 02.04 | The system does not start, or you want a truly clean printer | everything on the printer: calibration, settings, files, history |

## Option 1 – uninstall (recommended)

On the PC, in the project folder:

```
py tools/install.py uninstall --host PRINTER_IP
```

It uses the backup that `install` saved in `backups/` on your PC: every replaced file goes back to the
QIDI original, files we added are removed, the module actions are undone (firmware-download lock removed,
services back as they were) and the services restart. In `printer.cfg` and the macros only our edits are
taken out, so calibration saved after the install stays. A file you changed yourself after the install is
left alone and listed.

The new Ethernet MAC file is removed as well; after the next reboot the printer behaves as stock again.

## Option 2 – re-install the official 01.01.02.04 package from USB

QIDI allows installing the **same** version again. This puts every QIDI file of the package back to the
original.

1. Run option 1 first if you can (it removes the firmware-download lock, which may block an update).
2. Format a USB stick (FAT32). Create the folder `QD_Update` in its root.
3. Put the official package **unextracted** into it:
   `USB:\QD_Update\QD_Q2_01.01.02.04_20260804_Release.zip`
   (`py tools/firmware.py fetch` already downloaded it into `downloads/`, SHA-256
   `92308ee19ddd49b3e8229118a4950d6f0dec993a5e99709e4c88f7e22b89092e`).
4. Insert the stick and follow QIDI's update prompt. Keep the printer (and a QIDI Box, if you have one)
   powered until it finishes.
5. Afterwards run bed leveling and input shaping, as QIDI recommends.

## Option 3 – full reflash, then updates **only up to 01.01.02.04**

A reflashed eMMC starts at firmware **1.0.x** (the guides' text says 1.0.0, but their screenshots and the current image are 1.0.1). QIDI's wiki says to update in this exact order, because
skipping a step can (rarely) damage the SOC board:

**1.0.x → 1.1.1 → 01.01.02.01 → 01.01.02.04** – and stop there. Do not go online.

| Step | Package (official) | SHA-256 | How to put it on the USB stick |
|---|---|---|---|
| 1.0.x → 1.1.1 | `Q2_V1.1.1.zip` from [QIDI's GitHub releases](https://github.com/QIDITECH/QIDI_Q2/releases/tag/Q2_V1.1.1) | `4c7d0f5b52d1a780f3e02b92bea6c7b751690c2b4da529eafd2ceb662241ecb7` | **extract**; the three files `QD_Q2_MCU`, `QD_Q2_SOC_V1.1.1_…`, `QD_Q2_THR` go into `USB:\QD_Update\` |
| 1.1.1 → 01.01.02.01 | [`QD_Q2_01.01.02.01_20260601_Release.zip`](https://public-cdn.qidimaker.com/upgrade/3DPrinter/QD_Q2/01.01.02.01/ikintbwrsx/QD_Q2_01.01.02.01_20260601_Release.zip) | `ee9010a4aafb7ab6fab0c6f7843b6b064c7e490e8a8dc1aa542d211d5f6ea31e` | **not extracted**, into `USB:\QD_Update\` |
| 01.01.02.01 → 01.01.02.04 | [`QD_Q2_01.01.02.04_20260804_Release.zip`](https://public-cdn.qidimaker.com/upgrade/3DPrinter/QD_Q2/01.01.02.04/nrpolyn8hx/QD_Q2_01.01.02.04_20260804_Release.zip) | `92308ee19ddd49b3e8229118a4950d6f0dec993a5e99709e4c88f7e22b89092e` | **not extracted**, into `USB:\QD_Update\` |

Put only **one** step's files on the stick at a time; after each update check the version on the screen.
Packages ending in `NA` are the international firmware (QIDI Maker international app); `CN` is the Chinese one.

The factory eMMC image is linked from QIDI's own wiki page
[Flash System Image (eMMC)](https://wiki.qidi3d.com/en/Memo/flash-emmc) ("QIDI Q2 Image for eMMC").
Two ways to write it:

- QIDI's way (that wiki page): eMMC module out of the printer, eMMC adapter + USB card reader, balenaEtcher or Rufus;
- through the USB-C SOC port on the mainboard with Rockchip's RKDevTool, without removing the module:
  [community guide](https://github.com/qidi-community/q2-wiki/blob/main/content/stock-firmware-flash/README.md).

Both pages end with "update to the latest firmware" / "Online Update" - **do not do that here**; follow
the order below and stop at 01.01.02.04. The image tested with this project:

| File | Size | SHA-256 |
|---|---|---|
| `KLP_IMG_QD_Q2_V1.0.1_20250505_Release.7z` (contains `KLP_IMG_QD_Q2_V1.0.1_20250505_Release.img`, 5.66 GB) | 1 900 160 385 bytes | `3eb6aa08d55054db19a20ef80d85eaf9297efe307ae5cfa7cc7fba4eb2e366e7` |

If you got the image elsewhere, compare its SHA-256 with this one before flashing. This image starts at
1.0.1; follow the same order (1.0.x → 1.1.1 → 01.01.02.01 → 01.01.02.04). This project does not provide
the image or flashing tools.

After reaching 01.01.02.04: bed leveling and input shaping, then `py tools/printer.py check` and
`py tools/install.py install` again.

### Before a reflash, save from the printer

A reflash erases everything. Copy to your PC first (Fluidd → Configuration lets you download files):

- `printer.cfg` – the block at the end (`#*# SAVE_CONFIG`) holds your input shaper, bed mesh and Z offset;
  you can copy those values back later instead of recalibrating;
- `saved_variables.cfg`, `box.cfg` (QIDI Box), `crowsnest.conf` (camera), `moonraker.conf`;
- your G-code files and timelapses you want to keep;
- your own SSH keys or other changes you made yourself.

## Already on 01.01.03.x?

QIDI does not support going back, and this project has **not tested** any way down. Two community reports:

- **"Qidi Restore"** – the author describes going back from 01.01.03.01 to 01.01.02.04 **without an eMMC
  reflash**, including the firmware of the other boards, and reports six Q2 restored this way:
  [reddit thread](https://www.reddit.com/r/QidiTech3D/comments/1xdff0k/firmware_01010301_for_the_q2_is_broken_fix_your/).
  Read the whole thread and use it at your own risk.
- Otherwise: a full reflash (option 3), then updates up to 01.01.02.04 only.

The mainboard and toolhead firmware are the same in 01.01.02.04 and 01.01.03.02 (MCU 02.01.01.09,
THR 02.02.01.08, Box 02.03.01.13); 01.01.03.02 only adds images for new accessories (Box RS485, buffer).

## After any way back: check the controller versions

On the screen (system / version information) check, for 01.01.02.04:
**MCU 02.01.01.09** and **THR 02.02.01.08** (Box 02.03.01.13 if you have one).
After a return to an older version some users got an "MCU protocol error" and had to update the controller
firmware once more
([example](https://www.reddit.com/r/QidiTech3D/comments/1txj48b/how_to_revert_qidi_q2_to_v111_if_youre_like_me/)).
Re-installing the official 01.01.02.04 package from USB (option 2) flashes these versions again.

Sources: [QIDI wiki – Q2 firmware update](https://wiki.qidi3d.com/en/Q2/firmware-update),
[QIDI wiki – flash eMMC](https://wiki.qidi3d.com/en/Memo/flash-emmc), [qidi-community q2-wiki – stock firmware flash](https://github.com/qidi-community/q2-wiki/blob/main/content/stock-firmware-flash/README.md),
[QIDI firmware downloads](https://www.qidimaker.com/en/downloads/firmware/Q2),
[QIDITECH/QIDI_Q2 releases](https://github.com/QIDITECH/QIDI_Q2/releases).
