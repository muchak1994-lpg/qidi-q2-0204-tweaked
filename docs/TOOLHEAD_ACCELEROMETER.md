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

The fix rewrites the toolhead firmware. This project does **not** do it for you. It was done on one Q2 on
18.11.2026 with [rayaanatif/qidi-q2-accelerometer-fix](https://github.com/rayaanatif/qidi-q2-accelerometer-fix):

- printer firmware 01.01.02.04, bootloader `31f8344d`;
- original firmware `1d34b4b0`, replaced by `9d2360ba`;
- accelerometer 387 Hz before, 1602 Hz after;
- input shaper calibrated again afterwards.

Follow that guide step by step. Before you start:

- If the power fails while the firmware is being written, the toolhead may be left without working firmware.
  The bootloader is not touched, so recovery should be possible, but it is not guaranteed.
- The guide's tool, pinned in the guide, accepts only bootloader `31f8344d`. For bootloader `a21a3019` (seen after
  01.01.03.02 updates) only [Valve Oil](https://github.com/thelegendtubaguy/Valve-Oil) v26.11.15.1 or later knows
  it. Valve Oil is made for the QIDI Max 4, and its author supports the Q2 only to a limited extent.
- A QIDI update that brings new toolhead firmware overwrites the fix. Check again afterwards.
- Run `SHAPER_CALIBRATE` again after the fix, then `SAVE_CONFIG`. Earlier values came from the broken sample rate.
