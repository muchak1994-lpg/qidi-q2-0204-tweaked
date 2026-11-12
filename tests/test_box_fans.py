#!/usr/bin/env python3
"""QIDI Box fan threshold module (box-fan-threshold) against stand-in Klipper objects.

Run:  python tests/test_box_fans.py
"""
import ast
import importlib.util
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "modules/box-fan-threshold/files/q2_box_fans.py"
spec = importlib.util.spec_from_file_location("q2_box_fans", SRC)
q2_box_fans = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q2_box_fans)


class GcodeError(Exception):
    pass


class Fan:  # stands in for QIDI's box_heater_fan.BoxHeaterFan
    def __init__(self, heater_temp):
        self.heater_temp = heater_temp


class SaveVariables:
    def __init__(self, variables):
        self.allVariables = dict(variables)


class Gcode:
    def __init__(self, printer):
        self.printer, self.commands, self.scripts = printer, {}, []

    def register_command(self, name, func, desc=None):
        self.commands[name] = func

    def run_script_from_command(self, script):  # only SAVE_VARIABLE is used
        self.scripts.append(script)
        params = dict(p.split("=", 1) for p in script.split()[1:])
        sv = self.printer.objects["save_variables"]
        sv.allVariables[params["VARIABLE"]] = ast.literal_eval(params["VALUE"])


class GCmd:
    def __init__(self, **params):
        self.params, self.replies = params, []

    def get_float(self, name, default):
        return float(self.params[name]) if name in self.params else default

    def respond_info(self, msg):
        self.replies.append(msg)

    def error(self, msg):
        return GcodeError(msg)


class Printer:
    def __init__(self, fans, variables=None):
        self.objects, self.handlers = {}, {}
        self.objects["gcode"] = Gcode(self)
        if variables is not None:
            self.objects["save_variables"] = SaveVariables(variables)
        for name, fan in fans.items():
            self.objects["box_heater_fan " + name] = fan

    def lookup_object(self, name, default=None):
        return self.objects.get(name, default)

    def lookup_objects(self, module):
        return [(n, o) for n, o in self.objects.items() if n.startswith(module + " ")]

    def register_event_handler(self, event, func):
        self.handlers[event] = func


class Config:
    def __init__(self, printer):
        self.printer = printer

    def get_printer(self):
        return self.printer


def start(fans, variables=None):
    printer = Printer(fans, variables)
    mod = q2_box_fans.load_config(Config(printer))
    printer.handlers["klippy:connect"]()
    return printer, mod


def run(printer, **params):
    gcmd = GCmd(**params)
    printer.objects["gcode"].commands["SET_BOX_FAN_TEMP"](gcmd)
    return gcmd.replies


class BoxFans(unittest.TestCase):
    def fans(self):
        return {"heater_fan_a_box1": Fan(35.), "heater_fan_b_box1": Fan(35.),
                "heater_fan_a_box2": Fan(35.), "heater_fan_b_box2": Fan(35.)}

    def test_nothing_saved_keeps_box_cfg(self):
        fans = self.fans()
        printer, _ = start(fans, {})
        self.assertEqual({f.heater_temp for f in fans.values()}, {35.})
        self.assertIn("above 35 C (box.cfg)", run(printer)[0])

    def test_saved_value_applied_to_every_fan_at_connect(self):
        fans = self.fans()
        start(fans, {"box_fan_temp": 40.0})
        self.assertEqual({f.heater_temp for f in fans.values()}, {40.})

    def test_set_saves_and_applies_now(self):
        fans = self.fans()
        printer, _ = start(fans, {})
        reply = run(printer, TEMP="42")
        self.assertEqual(printer.objects["gcode"].scripts, ["SAVE_VARIABLE VARIABLE=box_fan_temp VALUE=42.0"])
        self.assertEqual({f.heater_temp for f in fans.values()}, {42.})
        self.assertIn("above 42 C (your setting", reply[0])
        # a restart: new objects from box.cfg (35), the saved value comes back
        fans2 = self.fans()
        start(fans2, printer.objects["save_variables"].allVariables)
        self.assertEqual({f.heater_temp for f in fans2.values()}, {42.})

    def test_zero_goes_back_to_box_cfg(self):
        fans = self.fans()
        printer, _ = start(fans, {"box_fan_temp": 40.0})
        run(printer, TEMP="0")
        self.assertEqual({f.heater_temp for f in fans.values()}, {35.})
        self.assertEqual(printer.objects["save_variables"].allVariables["box_fan_temp"], 0.0)

    def test_out_of_range_refused_and_nothing_saved(self):
        fans = self.fans()
        printer, _ = start(fans, {})
        for bad in ("10", "24.9", "60.1", "-5"):
            with self.assertRaises(GcodeError):
                run(printer, TEMP=bad)
        self.assertEqual(printer.objects["gcode"].scripts, [])
        self.assertEqual({f.heater_temp for f in fans.values()}, {35.})

    def test_hand_edited_bad_value_ignored(self):
        for bad in (99.0, "abc", -3, [1]):
            fans = self.fans()
            start(fans, {"box_fan_temp": bad})
            self.assertEqual({f.heater_temp for f in fans.values()}, {35.})

    def test_no_box_connected(self):
        printer, _ = start({}, {})
        self.assertEqual(run(printer), ["No QIDI Box connected."])
        reply = run(printer, TEMP="40")
        self.assertIn("will be used when a Box is connected", reply[0])
        self.assertEqual(printer.objects["save_variables"].allVariables["box_fan_temp"], 40.0)

    def test_no_save_variables(self):
        fans = self.fans()
        printer, _ = start(fans, None)
        with self.assertRaises(GcodeError):
            run(printer, TEMP="40")
        self.assertEqual({f.heater_temp for f in fans.values()}, {35.})


if __name__ == "__main__":
    unittest.main()
