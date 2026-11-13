# 01.01.03.02 vs 01.01.02.04 - notes for maintainers

Written 2026-11-13 for whoever continues this project (a person, Claude, Codex "Stefan" or the next one).
Question asked: can the new RS-485 QIDI Box (03.02) be brought to 02.04, and how hard would a 03.02 line of
this project be? Nothing here is built yet; this is the analysis only.

## How the comparison was made

Both official packages from QIDI's CDN (URLs and SHA-256 in `tools/firmware.py` and `tools/screen.py`):
`QD_Q2_01.01.02.04_20260804_Release.zip` (sha256 `92308ee1...`) and `QD_Q2_01.01.03.02_20261023_Release.zip`
(sha256 `b42f83d0...`). The SOC member is an `ar` archive; its `data.tar.xz` is the printer's file tree.
Both trees were unpacked and compared file by file (SHA-256).

## Result in one line

03.02 is 02.04 plus a small, concentrated change: **15 files changed, 111 added, 9 removed** (the removed ones are
demo models and a temp .deb). Everything else is byte-identical.

## What changed or was added

| Layer | Files |
| --- | --- |
| Klipper, new (RS-485 Box) | `extras/box2base.so`, `box485.py` (loader), `box485_multicolor.so`, `box485_buffer.so`, `box485_rack.so`, `box_device.so`, `box_protocol.so` (Cython, compressed string tables); `crcmod` 1.7 in `klippy-env` |
| Klipper, changed | `box_extras.so`, `box_rfid.so`, `box_stepper.so`, `multi_color_controller.so`, `closed_loop.so`, `toolhead.py` |
| `toolhead.py` | additions only: `feed_move()` / `unload_move()` and helpers used by `box2base` (remote Box motor activity, error codes QDE_004_042/043/055/056/057) |
| Config | `printer.cfg`: new `[box485]` (`serial_port: /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0`, 115200 baud - a CH340 USB-RS485 adapter on the host) and `[box2base]`; `gcode_macro.cfg`: LAZY_HOME / G28 wrapper (`rename_existing: G28.6245197`), homing_override `axes:xyz` rewritten, **`INIT_RFID_READ` added to `PRINTER_INIT`** (the startup race Valve-Oil fixes on the Max 4) |
| Moonraker | `database.py`, `klippy_apis.py` (`/printer/multi_color_controller/flow_stop`), `klippy_connection.py` (the nested status merge = our `moonraker-box-status-merge`), `websockets.py`, `mqtt.so` |
| Screen (`qidiclient`) | 2418 new strings: RS-485 Box pages, auto refill, flow retry, Box485/buffer firmware update over RS-485 (`tcsetattr`), print queue (already ported as `screen-program`), error texts; 64 new resource files |
| Board firmware | MCU 02.01.01.09, THR 02.02.01.08, Box 02.03.01.13 identical to 02.04; new `BOX485 02.04.01.01` and `BUFFER 02.05.01.01` images |
| Other | `/etc/dhcpcd.exit-hook` with 1.1.1.1 / 8.8.8.8 (= our `dns-fallback-global`) |

## Porting the RS-485 Box to 02.04

- Klipper side: feasible (new files, `crcmod`, two config sections, additive `toolhead.py`, the changed Box modules).
  Open point: what the compressed Cython modules import and call (decompress their string tables first).
- Screen side: the Box UI and the Box firmware update live in the 03.02 screen program. Grafting that into the
  02.04 program is not realistic (thousands of changes, not one feature like the print queue). Taking the whole
  03.02 screen program means the result is effectively 03.02.
- Conclusion: "02.04 + new Box" ends up as 03.02 with a 02.04 label, and keeps the same files where 03.x bugs are
  reported. Not recommended.

## A 03.02 line of this project instead

Of the 58 modules (2026-11-13):

- 36 change files that are identical in 03.02 - should apply as they are (re-check hashes).
- 2 are already done by QIDI in 03.02: `dns-fallback-global`, `moonraker-box-status-merge`.
- 20 need porting: 9 macro modules (text edits on the new `gcode_macro.cfg`), `fuzzy-skin-extrusion`
  (toolhead.py), `print-cache-protection` (klippy_apis.py), `idle-timeout-drying` + `mcu-temperatures`
  (printer.cfg), and 8 screen-program modules (byte patches to be re-located in the new `qidiclient`:
  `screen-program`, `update-check-off`, `dark-mode-light`, the 4 `screen-drying-*`, `screen-gradient-cache-off`).
- New in 03.02 to check: `INIT_RFID_READ` in `PRINTER_INIT`, QIDI's new homing macros vs `z-home-guard` /
  `z-home-random-point`, the 03.x issue reports.
- Side effect for users: on 03.02 the QIDI cloud no longer demands an update.

Estimate: a few weeks; most of it testable on a printer without a Box, the RS-485 Box parts only with one.
