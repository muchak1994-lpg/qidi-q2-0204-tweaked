# SPDX-License-Identifier: GPL-3.0-or-later
# q2-0204-tweaked (thr-accel-check): read-only check of the toolhead (THR) board.
#
# QIDI's THR firmware 02.02.01.08 lacks Klipper commit 6269dda (LIS2DW FIFO handling): the toolhead
# accelerometer delivers about 390 samples a second instead of 1600, so input shaper calibration sees
# only part of the vibrations (QIDI_Q2 #39). A fix exists, but it rewrites the toolhead firmware and
# stays a manual, optional step (see docs). This command only looks:
#
#   TWEAKED_THR_CHECK          measure the accelerometer for 2 s, read the toolhead's bootloader and
#                         firmware with Klipper's debug_read (memory reads, nothing is written),
#                         and say whether the board has the bug and whether a known tool can fix it
#   TWEAKED_THR_CHECK SAVE=1   also save the bootloader and firmware as a backup in
#                         printer_data/config/q2_thr_backup/ (downloadable from Fluidd)
#
# Refused while a print is running or paused. Reading the memory takes about a minute;
# the console is busy meanwhile. The result is also in the object's status ("q2_thr_check"),
# which the installer reads at the end of an install.
import hashlib
import json
import logging
import os
import struct

FLASH = 0x08000000
BOOT_SIZE = 0x8000
APP_START = FLASH + BOOT_SIZE
PAGE = 2048
FLASH_SIZE_REG = 0x1FFFF7E0  # STM32F1: flash size in KiB (16 bit)

# Bootloaders: SHA-256 -> what is known about them.
KNOWN_BOOT = {
    "31f8344db7b091df5429960bc9cd06065e2188c3b8092e43fb65eb3f2833723c":
        "QIDI THR bootloader seen on Q2 01.01.02.0x - known to the accelerometer-fix flasher and to Valve Oil",
    "a21a3019004a4a3e50ec2e07882b8b39b7ff028161e692e83191144c14da7342":
        "QIDI THR bootloader seen after 01.01.03.02 updates (also QIDI Smart 5) - known to Valve Oil v26.11.15.1 and later",
}
# Toolhead firmware: SHA-256 -> (size, description, state)
KNOWN_APP = {
    "1d34b4b0142f2a2047f08c2fae59d827bcee0adbd1563b4bd1de311dff8b2d62":
        (35056, "QIDI THR 02.02.01.08 (original)", "stock"),
    "9d2360ba47ebd720dbef07a0a4ebaf26004360bca090997d7b4a118c41460ac9":
        (35056, "THR 02.02.01.08 with the LIS2DW FIFO fix (accelerometer-fix v1)", "fixed"),
    "b6e39b1def0bad6c2379cad600c1284cece0c26caab77dbb659adf64d4f4172a":
        (35056, "THR 02.02.01.08 with the LIS2DW FIFO fix (Valve Oil)", "fixed"),
    "e114de22c629167381b68eb6e477b2a8dc93ee98fb2fbdb3c828f95a224c8f8b":
        (34780, "QIDI KLP_MCU_THR_V2_1.0.5 (original, Q2 v1.1.1)", "stock"),
}
RATE_OK = 1200.     # LIS2DW at 1600 Hz
RATE_BUG = (250., 600.)  # the FIFO bug: about 390 Hz


def sha(data):
    return hashlib.sha256(data).hexdigest()


def identify_app(region):
    """(firmware bytes, sha, description, state) from the region read after the bootloader."""
    for digest, (size, desc, state) in KNOWN_APP.items():
        if len(region) >= size and sha(region[:size]) == digest:
            return region[:size], digest, desc, state
    data = region.rstrip(b"\xff")
    return data, sha(data), "unknown toolhead firmware (%d bytes)" % len(data), "unknown"


def verdict(rate, boot_sha, app_state):
    """(state, lines) - state: ok / bug / unknown."""
    lines = []
    if rate is None:
        state = "unknown"
        lines.append("Accelerometer: not measured.")
    elif rate >= RATE_OK:
        state = "ok"
        lines.append("Accelerometer: %.0f samples/s - OK." % rate)
    elif RATE_BUG[0] <= rate <= RATE_BUG[1]:
        state = "bug"
        lines.append("Accelerometer: %.0f samples/s instead of about 1600 - QIDI toolhead firmware bug "
                     "(QIDI_Q2 #39). Input shaper calibration sees only part of the vibrations." % rate)
    else:
        state = "unknown"
        lines.append("Accelerometer: %.0f samples/s - unusual, neither the known bug nor normal." % rate)
    if state == "bug":
        if boot_sha in KNOWN_BOOT and app_state == "stock":
            lines.append("A manual, optional fix exists for this bootloader and firmware (it rewrites the toolhead "
                         "firmware - read the risks in the project's docs first, keep the backup: TWEAKED_THR_CHECK SAVE=1).")
        elif boot_sha is not None:
            lines.append("No flashing tool we know accepts this bootloader/firmware combination - do not flash. "
                         "Keep a backup (TWEAKED_THR_CHECK SAVE=1); its authors need it to add support.")
    return state, lines


class Q2ThrCheck:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.mcu_name = config.get("mcu", "THR")
        self.chip_name = config.get("chip", "lis2dw")
        self.save_dir = config.get("save_dir", "/home/qidi/printer_data/config/q2_thr_backup")
        self.last = {"done": False}
        self.printer.lookup_object("gcode").register_command(
            "TWEAKED_THR_CHECK", self.cmd_TWEAKED_THR_CHECK,
            desc="Read-only check of the toolhead accelerometer and firmware (SAVE=1: also back them up)")

    def get_status(self, eventtime):
        return dict(self.last)

    # ---------------------------------------------------------------- measuring
    def measure(self):
        chip = self.printer.lookup_object(self.chip_name, None)
        if chip is None or not hasattr(chip, "start_internal_client"):
            return None, None
        client = chip.start_internal_client()
        self.printer.lookup_object("toolhead").dwell(2.)
        client.finish_measurements()
        samples = client.get_samples()
        if len(samples) < 2 or samples[-1][0] <= samples[0][0]:
            return None, None
        times = [s[0] for s in samples]
        gap = max(b - a for a, b in zip(times, times[1:]))
        return (len(times) - 1) / (times[-1] - times[0]), gap * 1000.

    # ---------------------------------------------------------------- reading
    def read_flash(self, gcmd):
        mcu = self.printer.lookup_object("mcu " + self.mcu_name)
        query = mcu.lookup_query_command("debug_read order=%c addr=%u", "debug_result val=%u")

        def word(addr, order=2):
            return query.send([order, addr])["val"]

        flash_kib = word(FLASH_SIZE_REG, 1) or 128
        flash_end = FLASH + min(max(flash_kib, 64), 512) * 1024
        boot = b"".join(struct.pack("<I", word(a)) for a in range(FLASH, APP_START, 4))
        pages = []
        for page in range(APP_START, flash_end, PAGE):
            data = b"".join(struct.pack("<I", word(a)) for a in range(page, page + PAGE, 4))
            if data == b"\xff" * PAGE:
                break  # first erased page: the firmware ends before it
            pages.append(data)
        status = mcu.get_status() if hasattr(mcu, "get_status") else {}
        return boot, b"".join(pages), status.get("mcu_version")

    def save(self, boot, app, report):
        folder = os.path.join(self.save_dir, "%s-%s" % (report["bootloader_sha256"][:8],
                                                         report["application_sha256"][:8]))
        os.makedirs(folder, exist_ok=True)
        for name, data in (("bootloader.bin", boot), ("application.bin", app),
                           ("report.json", (json.dumps(report, indent=1) + "\n").encode())):
            tmp = os.path.join(folder, name + ".tmp")
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, os.path.join(folder, name))
        return folder

    # ---------------------------------------------------------------- command
    def cmd_TWEAKED_THR_CHECK(self, gcmd):
        eventtime = self.printer.get_reactor().monotonic()
        stats = self.printer.lookup_object("print_stats", None)
        if stats is not None and stats.get_status(eventtime).get("state") in ("printing", "paused"):
            raise gcmd.error("TWEAKED_THR_CHECK: not while a print is running or paused")
        want_save = gcmd.get_int("SAVE", 0, minval=0, maxval=1)
        self.last = {"done": False}
        rate, gap = self.measure()
        gcmd.respond_info("TWEAKED_THR_CHECK: reading the toolhead's bootloader and firmware (read only, "
                          "about a minute)...")
        try:
            boot, region, version = self.read_flash(gcmd)
        except Exception as exc:
            logging.exception("q2_thr_check: reading the toolhead failed")
            boot = region = version = None
            read_error = str(exc)
        else:
            read_error = None
        report = {"done": True, "rate_hz": round(rate, 1) if rate else None,
                  "max_gap_ms": round(gap, 2) if gap else None, "version": version}
        app_state = None
        if boot is not None:
            app, app_sha, app_desc, app_state = identify_app(region)
            boot_sha = sha(boot)
            report.update(bootloader_sha256=boot_sha, application_sha256=app_sha,
                          bootloader=KNOWN_BOOT.get(boot_sha, "unknown bootloader"),
                          application=app_desc, application_state=app_state,
                          application_bytes=len(app))
        else:
            boot_sha = None
            report["read_error"] = read_error
        state, lines = verdict(rate, boot_sha, app_state)
        report["state"] = state
        if boot is not None:
            lines.append("Toolhead firmware: %s, %s (%s)." % (version or "?", app_desc, app_sha[:8]))
            lines.append("Bootloader: %s (%s)." % (report["bootloader"], boot_sha[:8]))
            if want_save:
                try:
                    report["saved"] = self.save(boot, app, dict(report))
                    lines.append("Backup saved: %s" % report["saved"])
                except OSError as exc:
                    lines.append("Backup NOT saved: %s" % exc)
        else:
            lines.append("Toolhead memory could not be read: %s" % read_error)
        report["lines"] = lines
        self.last = report
        gcmd.respond_info("\n".join(lines))


def load_config(config):
    return Q2ThrCheck(config)
