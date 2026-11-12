# QIDI Box heater fans: a threshold of your own that survives the screen
# program rewriting box.cfg. q2-0204-tweaked, QIDI_Q2 issue #25.
#
# box.cfg belongs to the screen program (qidiclient). Each time the screen
# program starts, it builds box.cfg again from a template inside the program
# (fan threshold 35 C). If the file on disk is different, it writes the
# template over it and restarts Klipper. A threshold changed in box.cfg
# therefore lasts only until the next power-on. QIDI's 03.02 does the same.
#
# This module keeps your threshold in saved_variables.cfg (variable
# box_fan_temp) and gives it to both heater fans of every Box each time
# Klipper connects. Above the threshold (Box air temperature) the fans run
# even when the Box is not heating; while the Box heats they always run.
# That logic is QIDI's and is unchanged.
#
#   SET_BOX_FAN_TEMP           show the threshold in use
#   SET_BOX_FAN_TEMP TEMP=40   use 40 C from now on, kept across restarts
#   SET_BOX_FAN_TEMP TEMP=0    back to the value in box.cfg (QIDI: 35 C)
import logging

VARIABLE = 'box_fan_temp'
MIN_TEMP = 25.
MAX_TEMP = 60.


class Q2BoxFans:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.box_cfg_temps = {}  # fan name -> threshold read from box.cfg
        self.printer.register_event_handler('klippy:connect',
                                            self._handle_connect)
        self.printer.lookup_object('gcode').register_command(
            'SET_BOX_FAN_TEMP', self.cmd_SET_BOX_FAN_TEMP,
            desc=self.cmd_SET_BOX_FAN_TEMP_help)

    def _fans(self):
        return [(name, fan)
                for name, fan in self.printer.lookup_objects('box_heater_fan')
                if hasattr(fan, 'heater_temp')]

    def _saved(self):
        """Your threshold from saved_variables.cfg, or None for box.cfg's."""
        sv = self.printer.lookup_object('save_variables', None)
        value = getattr(sv, 'allVariables', {}).get(VARIABLE)
        if value is None:
            return None
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = -1.
        if value == 0.:
            return None
        if not MIN_TEMP <= value <= MAX_TEMP:
            logging.info("q2_box_fans: ignoring %s=%r (allowed %g-%g or 0)",
                         VARIABLE, value, MIN_TEMP, MAX_TEMP)
            return None
        return value

    def _apply(self, temp):
        for name, fan in self._fans():
            default = self.box_cfg_temps.setdefault(name, fan.heater_temp)
            fan.heater_temp = default if temp is None else temp

    def _handle_connect(self):
        temp = self._saved()
        self._apply(temp)
        if temp is not None and self._fans():
            logging.info("q2_box_fans: Box heater fans run above %g C", temp)

    cmd_SET_BOX_FAN_TEMP_help = (
        "QIDI Box heater fans: show or set the Box temperature above which"
        " they run (kept across restarts; TEMP=0 = box.cfg)")

    def cmd_SET_BOX_FAN_TEMP(self, gcmd):
        temp = gcmd.get_float('TEMP', None)
        if temp is not None:
            if temp != 0. and not MIN_TEMP <= temp <= MAX_TEMP:
                raise gcmd.error(
                    "TEMP must be %g-%g C, or 0 to go back to box.cfg"
                    % (MIN_TEMP, MAX_TEMP))
            if self.printer.lookup_object('save_variables', None) is None:
                raise gcmd.error("No [save_variables] - the threshold"
                                 " could not be kept")
            self.printer.lookup_object('gcode').run_script_from_command(
                "SAVE_VARIABLE VARIABLE=%s VALUE=%r"
                % (VARIABLE, round(temp, 1)))
            self._apply(self._saved())
        self._report(gcmd)

    def _report(self, gcmd):
        temp = self._saved()
        fans = self._fans()
        if not fans:
            msg = "No QIDI Box connected."
            if temp is not None:
                msg += (" Your Box fan threshold %g C will be used when a"
                        " Box is connected." % temp)
            gcmd.respond_info(msg)
            return
        box_cfg = sorted(set(self.box_cfg_temps.get(name, fan.heater_temp)
                             for name, fan in fans))
        box_cfg = "/".join("%g" % t for t in box_cfg)
        if temp is None:
            gcmd.respond_info("Box heater fans run above %s C (box.cfg)."
                              % box_cfg)
        else:
            gcmd.respond_info("Box heater fans run above %g C (your setting,"
                              " kept across restarts; box.cfg: %s C)."
                              % (temp, box_cfg))


def load_config(config):
    return Q2BoxFans(config)
