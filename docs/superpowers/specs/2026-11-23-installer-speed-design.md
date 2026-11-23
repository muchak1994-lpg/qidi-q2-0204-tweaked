# Installer speed (2026-11-23)

Owner's request: optimise the installer ("1 and 2, not 3"): modules stay single (skipping one fix is more valuable than fewer modules).

## Measured before (plan with nothing to change, printer idle, over Tailscale)
29.1 s in total, 24 SSH commands (22.6 s of SSH time): `sha256sum` of ~220 files 14.4 s (4 commands), 8 separate `systemctl` probes 3.9 s,
5 file reads 1.6 s, the rest 0.2-0.8 s each. Build 1.4 s, login 2.1 s. Restarts cost nothing in the installer (`systemctl restart` returns at once).
A one-file install adds per file: upload, install, a separate `sha256sum` check, and a `stat` for the backup (3-4 round trips).

## Approaches
1. Hash cache only (small, biggest gain). 2. Cache + fewer/parallel round trips (chosen). 3. Group modules into categories (rejected by the owner).

## Design (all in `tools/install.py`, no change to modules)
* `HashCache` (PC side, `work/hash-cache-<printer id>.json`): per path the printer's own file identity `size|ctime(ns)|inode` and the SHA-256 seen
  with it. `ctime` changes on any write/rename/chmod and cannot be set with `touch`. Anything unknown, changed or unreadable is hashed again;
  a corrupt cache file is ignored. `--rehash` ignores the cache for one run (and refreshes it).
* `SSHPrinter.sha_many`: one `find -printf` for the identities, then `sha256sum` only for files whose identity changed, in chunks run in parallel
  (3 SSH channels). After `install()` the new identity and digest are stored (the same command prints both), after `remove()` the entry is dropped.
* Fewer round trips: `prefetch_units` (all `systemctl` probes in one command, dropped after any write/action/restart), `read_many` (config files in
  one command), `stat_many` (backup owner/group/mode in one command), `install()` verifies the digest in the same command as the write.
* `plan()` no longer hashes files it reads anyway (`base: printer`).
* Fake printers in the tests do not have the new methods: every use is `hasattr`-guarded, so old behaviour stays.

## Not changed
Restarts, the order of modules, backups, what is written to the printer, the questions asked. Success measure: plan with no change from 29 s to under ~10 s
(an estimate, measured after), a first install keeps working (cold cache).
