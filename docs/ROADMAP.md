# Roadmap

- **Done (release candidate):** 58 modules build from the official packages and match a tested printer byte
  for byte - see [FIXES.md](FIXES.md). Installer with PC-side backup, plan, install, upgrade and uninstall.
- **Next:** full test on a freshly reflashed printer (1.0.1 → 1.1.1 → 01.01.02.01 → 01.01.02.04 → install),
  then version 1.0.
- **Open tests:** `load-temp-memory` with a real filament change (PLA after a hotter filament, two colours).
  `box-fan-threshold` and `box-fixes` are checked in code only (`box-heater-keepalive`: tested by the QIDI #34
  reporter) - the author has no QIDI Box; reports from Box owners are welcome.
- **Later / ideas:** touchscreen view and a touchscreen-app restart in Fluidd, cutting and unloading without
  heating the nozzle (as in Valve-Oil for the Max 4 / Plus 5); more QIDI Box fixes when people report real problems;
  testers with other Q2 units welcome.
