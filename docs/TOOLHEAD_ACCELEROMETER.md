# Toolhead accelerometer: ~390 instead of 1600 samples a second

[Polski](TOOLHEAD_ACCELEROMETER.pl.md)

QIDI's toolhead (THR) firmware 02.02.01.08 lacks Klipper commit
[6269dda](https://github.com/Klipper3d/klipper/commit/6269dda56bb7c08263153b18715d08e2d964bcab) (LIS2DW FIFO
handling). The accelerometer then delivers about 390 samples a second instead of 1600
([QIDI_Q2 #39](https://github.com/QIDITECH/QIDI_Q2/issues/39)), so input shaper calibration sees only part of the
vibrations.

## Check (read only) - module `thr-accel-check`

At the end of an install the installer tells you about the bug and asks whether to check your printer
(Enter = yes, `n` = no; `--toolhead yes|no` answers in advance). The check runs `TWEAKED_THR_CHECK SAVE=1` once,
prints the result and says whether you have the bug. It also keeps a copy of the toolhead's bootloader and firmware
on the PC (`backups/toolhead-<bootloader>-<firmware>/`) and removes it from the printer. You can run it yourself in
the Fluidd console at any time, for example after a QIDI update:

- `TWEAKED_THR_CHECK`: measures the accelerometer for 2 s and reads the toolhead's bootloader and firmware with
  Klipper's `debug_read`. These are memory reads only; nothing is written to the toolhead. It names them when they
  are known, and says whether a known tool can flash that combination.
- `TWEAKED_THR_CHECK SAVE=1`: also saves both to `config/q2_thr_backup/`, which you can download from Fluidd.

It is refused while a print is running or paused.

## What the result means

- **1200 samples a second or more: no bug.** Nothing to do.
- **About 390: the bug is there.** Nothing is required - the printer prints as it always did. The only thing that
  suffers is input shaper calibration (it sees part of the vibrations). Fixing it is optional.
- **Anything else, or firmware the check does not know:** do not flash. Keep the backup the check made.

## The fix is manual and optional - at your own risk

> **Disclaimer.** Rewriting the toolhead firmware can leave the toolhead unusable. You do it entirely at your own
> risk; this project, its authors and QIDI take no responsibility for it. It is not part of the installer.

The fix rewrites the toolhead firmware. This project does **not** do it for you: the installer never flashes the
toolhead. Below is how to do it by hand, step by step, from a Windows PC.

### What it was tested on

One Q2, 18.11.2026: printer firmware 01.01.02.04, bootloader `31f8344d`, original toolhead firmware `1d34b4b0`
(THR 02.02.01.08), replaced by `9d2360ba`. Accelerometer 387 samples a second before, 1602 after (1603 with
`TWEAKED_THR_CHECK` on 20.11.2026). Input shaper calibrated again afterwards.

Honestly said:

- The flashing commands below (snapshot, probe, transfer, verify) are the ones run on 18.11.2026, from a folder in
  `/home/qidi`. This guide uses `/tmp` instead (the `mks` user cannot write to `/home/qidi`), and the PowerShell
  commands were not run exactly as written here.
- The patch step was run again on 20.11.2026 on the PC from the original firmware read on 18.11: the result is
  byte for byte the image that was written then (`9d2360ba`).
- Going back to the original firmware has **not** been tested.

### Tools (not part of this project)

- The flashing tool from [Valve Oil](https://github.com/thelegendtubaguy/Valve-Oil) by thelegendtubaguy
  (GPL-3.0), at commit `ffb3029` - the version used on 18.11. It talks to the toolhead's bootloader, refuses
  firmware and bootloaders it does not know, and keeps the original firmware ready to put back if writing fails.
- `lis2dw_patch.py` from [rayaanatif/qidi-q2-accelerometer-fix](https://github.com/rayaanatif/qidi-q2-accelerometer-fix)
  (GPL-3.0), at commit `0e64967`. It makes the fixed firmware from **your own** original firmware (QIDI's firmware
  is not shared here). It never flashes anything.

Use exactly these versions: the SHA-256 sums below are checked against GitHub (20.11.2026). If a sum differs,
stop.

### Before you start

- **No print running, heaters off, printer idle.** Stable power, you at the printer, about 30 minutes.
- Do not switch the printer off and do not close the PowerShell window during step 9.
- If the power fails while the firmware is being written, the toolhead may be left without working firmware.
  The bootloader is not touched, so recovery should be possible, but it is not guaranteed.
- The tool at this version accepts only bootloader `31f8344d`. For bootloader `a21a3019` (seen after 01.01.03.02
  updates) only Valve Oil v26.11.15.1 or later knows it - not covered here. Valve Oil is made for the QIDI Max 4,
  and its author supports the Q2 only to a limited extent.
- You need: the project's Python (`py`, the same one `install.bat` uses), the `ssh` and `scp` commands built into
  Windows, and the SSH login of the printer user `mks` (the same one the installer uses).
- In every command replace `PRINTER` with your printer's address (screen - network settings). Each `ssh` command
  may ask for the `mks` password (twice when `sudo` needs it too). Run the steps one by one and compare each
  result with what is expected. **At the first thing that does not match: stop**, start the services again
  (step 4) and keep everything you saved.

### 1. Check that you have the bug and the right firmware

In the Fluidd console: `TWEAKED_THR_CHECK`. Go on only if it says all three:

- `Accelerometer: ... samples/s instead of about 1600`, with a number around 390 (the bug);
- `A manual, optional fix exists for this bootloader and firmware`;
- `Toolhead firmware: ... QIDI THR 02.02.01.08 (original) (1d34b4b0)` and `Bootloader: ... (31f8344d)`.

### 2. Download the tools to the PC

In PowerShell:

```powershell
mkdir $HOME\q2-thr
cd $HOME\q2-thr
Invoke-WebRequest -Uri https://github.com/thelegendtubaguy/Valve-Oil/archive/ffb302997910b0a02ac8a18b6e23274109d208f2.zip -OutFile flasher.zip
Expand-Archive flasher.zip -DestinationPath .
Rename-Item Valve-Oil-ffb302997910b0a02ac8a18b6e23274109d208f2 flasher
Invoke-WebRequest -Uri https://raw.githubusercontent.com/rayaanatif/qidi-q2-accelerometer-fix/0e649671c9d56b7dc7200c0b8311265821082574/tools/lis2dw_patch.py -OutFile lis2dw_patch.py
Get-FileHash flasher\scripts\flash_thr_firmware.py, flasher\scripts\thr_bootloaders.py, flasher\firmware\max4-thr-lis2dw-fifo-v1.json, lis2dw_patch.py
```

Expected (Windows prints capital letters; that does not matter):

```
B68E3032BD22CB441F01648EC20DCFC8FE58CD822F9AE7CB81CCA5679D9C6F0B  flash_thr_firmware.py
1169DA4CC843D6BF67FA0D11ED8A46D4B0D7F69095EA8D46F007141AB0923918  thr_bootloaders.py
8619820DE91730A37BE0E67DD66D38B2671C01B1B7508A032C5EC11F417CD5E1  max4-thr-lis2dw-fifo-v1.json
016C11B1A57FC9F01914A8B04EB61CFEE642D3DEC09E678C5A29D935F7AE9DF4  lis2dw_patch.py
```

All further PC commands run in this folder (`cd $HOME\q2-thr`).

### 3. Copy the flashing tool to the printer

```powershell
ssh mks@PRINTER 'mkdir -p /tmp/q2_thr_tools'
scp -r flasher\scripts flasher\firmware mks@PRINTER:/tmp/q2_thr_tools/
ssh mks@PRINTER 'cd /tmp/q2_thr_tools && sha256sum scripts/*.py firmware/*.json'
```

The printer must print the same three sums as in step 2 (in small letters).

### 4. Stop Klipper and the screen program

They use the toolhead's serial line; the tool refuses to run while they are active. The screen and Fluidd go
dark.

```powershell
ssh -t mks@PRINTER 'sudo systemctl stop qidi-client.service && sudo systemctl stop klipper.service; systemctl is-active klipper.service qidi-client.service'
```

Expected at the end: `inactive` twice. **To start them again** (at any moment you stop, and in step 11):

```powershell
ssh -t mks@PRINTER 'sudo systemctl start klipper.service; sleep 5; sudo systemctl start qidi-client.service; systemctl is-active klipper.service qidi-client.service'
```

### 5. Read the original firmware (read only)

```powershell
ssh -t mks@PRINTER 'cd /tmp/q2_thr_tools && sudo /home/qidi/klippy-env/bin/python scripts/flash_thr_firmware.py snapshot --output-dir dist/thr-before --printer-idle-confirmed; echo EXIT_CODE=$?; sudo chown -R mks dist'
```

Expected: `"application_sha256": "1d34b4b0..."`, `"bootloader_sha256": "31f8344d..."` and `EXIT_CODE=0`.
`EXIT_CODE=3` means a bootloader this tool does not know: stop.

### 6. Copy that backup to the PC

```powershell
scp -r mks@PRINTER:/tmp/q2_thr_tools/dist/thr-before .
Get-FileHash thr-before\application.bin, thr-before\bootloader.bin
```

Expected: `1D34B4B0...` and `31F8344D...`. If you ran the check from the installer, the same `application.bin`
is also in the project's `backups\toolhead-31f8344d-1d34b4b0\` - its sum must be the same. Keep `thr-before`:
it is your way back.

### 7. Test the connection to the bootloader (erases nothing)

```powershell
ssh -t mks@PRINTER 'cd /tmp/q2_thr_tools && sudo /home/qidi/klippy-env/bin/python scripts/flash_thr_firmware.py probe --backup-dir dist/thr-before --reset --printer-idle-confirmed; echo EXIT_CODE=$?'
```

Expected: `"bootloader_reply": "0102"`, `"erase_requested": false`, `EXIT_CODE=0`. Wait 15 seconds, then check
that nothing changed:

```powershell
ssh -t mks@PRINTER 'cd /tmp/q2_thr_tools && sudo /home/qidi/klippy-env/bin/python scripts/flash_thr_firmware.py snapshot --output-dir dist/thr-after-probe --printer-idle-confirmed; echo EXIT_CODE=$?'
```

Expected: the same two sums as in step 5 and `EXIT_CODE=0`.

### 8. Make the fixed firmware from your original

```powershell
py lis2dw_patch.py patch thr-before\application.bin QD_Q2_THR_02.02.01.08_20260303_FIFO_v1.bin
Get-FileHash QD_Q2_THR_02.02.01.08_20260303_FIFO_v1.bin
```

Expected: `template B at 0xbfa` and the sum `9D2360BA47EBD720DBEF07A0A4EBAF26004360BCA090997D7B4A118C41460AC9`.
Nothing else is accepted by the flashing tool. Copy it to the printer and check it there:

```powershell
scp QD_Q2_THR_02.02.01.08_20260303_FIFO_v1.bin mks@PRINTER:/tmp/q2_thr_tools/dist/
ssh mks@PRINTER 'sha256sum /tmp/q2_thr_tools/dist/QD_Q2_THR_02.02.01.08_20260303_FIFO_v1.bin'
```

### 9. Write it - the only step that changes the toolhead

Stay at the printer, do not touch the power, keep the window open until the end.

```powershell
ssh -t mks@PRINTER 'cd /tmp/q2_thr_tools && sudo /home/qidi/klippy-env/bin/python scripts/flash_thr_firmware.py transfer --image dist/QD_Q2_THR_02.02.01.08_20260303_FIFO_v1.bin --backup-dir dist/thr-before --reset --recover-to-stock --printer-idle-confirmed --confirm-write; echo EXIT_CODE=$?'
```

- `EXIT_CODE=0`: the toolhead accepted the fixed firmware. Go on.
- `EXIT_CODE=4`: writing failed and the tool put the original back. Do step 10 with
  `--image dist/thr-before/application.bin` to confirm it, then step 11.
- `EXIT_CODE=1` or `5`: **do not repeat it and do not start the services.** Leave the printer on, keep the window
  and its text, and ask for help (Valve Oil or accelerometer-fix issues, with `thr-before` and the output).

### 10. Read it back and verify

```powershell
ssh -t mks@PRINTER 'cd /tmp/q2_thr_tools && sleep 15 && sudo /home/qidi/klippy-env/bin/python scripts/flash_thr_firmware.py snapshot --output-dir dist/thr-after --printer-idle-confirmed; echo SNAP_EXIT=$?; sudo /home/qidi/klippy-env/bin/python scripts/flash_thr_firmware.py verify --image dist/QD_Q2_THR_02.02.01.08_20260303_FIFO_v1.bin --backup-dir dist/thr-after --original-backup-dir dist/thr-before; echo VERIFY_EXIT=$?; sudo chown -R mks dist'
scp -r mks@PRINTER:/tmp/q2_thr_tools/dist/thr-after .
```

Expected: `"verified": true`, the firmware sum `9d2360ba...`, the bootloader sum unchanged (`31f8344d...`),
`SNAP_EXIT=0` and `VERIFY_EXIT=0`.

### 11. Start the printer again

The command "to start them again" from step 4. Expected: `active` twice, and Fluidd shows Klipper ready without
errors. The fix stays after switching off.

### 12. Measure again

In the Fluidd console: `TWEAKED_THR_CHECK`. Expected: about 1600 samples a second and `Toolhead firmware: ... with
the LIS2DW FIFO fix (accelerometer-fix v1) (9d2360ba)`. Then `SHAPER_CALIBRATE` (the printer homes and vibrates
loudly for a few minutes) and `SAVE_CONFIG`: the earlier input shaper values came from the broken rate.

### 13. Clean up the printer

Copies are on the PC (`thr-before`, `thr-after`), so nothing needs to stay on the printer:

```powershell
ssh -t mks@PRINTER 'sudo rm -rf /tmp/q2_thr_tools'
```

`/tmp` on the Q2 is on the normal disk, so it is not emptied by a restart. Keep `$HOME\q2-thr` on the PC.

### Going back to the original firmware (not tested)

The same tool accepts the original image you saved in step 6. Copy the tool and the backup back (step 3, then
`scp -r thr-before mks@PRINTER:/tmp/q2_thr_tools/dist/`), stop the services (step 4), then:

```powershell
ssh -t mks@PRINTER 'cd /tmp/q2_thr_tools && sudo /home/qidi/klippy-env/bin/python scripts/flash_thr_firmware.py transfer --image dist/thr-before/application.bin --backup-dir dist/thr-before --reset --recover-to-stock --printer-idle-confirmed --confirm-write; echo EXIT_CODE=$?'
```

Then step 10 with `--image dist/thr-before/application.bin` and a new `--output-dir` (e.g. `dist/thr-back`),
step 11 and step 13. The official 01.01.02.04 package contains the same original firmware
(`QD_Q2_THR_02.02.01.08_20260303.bin`, `1d34b4b0`); whether installing that update again rewrites the toolhead
has not been tested.

### After a QIDI update

An update that brings new toolhead firmware overwrites the fix. Run `TWEAKED_THR_CHECK` again afterwards; with a
different bootloader or firmware, do not use this guide.
