# Screen program build scripts

These scripts rebuild QIDI's screen program (`/home/qidi/QIDI_Client/bin/qidiclient`) on your PC; run
them through `py tools/screen.py build` (or simply `tools/install.py`), not by hand.

The folder names are the dates of the engineering steps in which each part was developed; they are kept
so the scripts run unchanged and their results can be compared with the tested ones. Words such as
"candidate", "private" or "DO_NOT_INSTALL" in file names and messages come from that development stage:
the scripts only build files on the PC and never contact the printer. Whether the result may be installed
is decided only by `tools/screen.py`, which checks the SHA-256 after every stage against the version
tested on a real printer.

| Folder | Stage | Result SHA-256 (first 8) |
|---|---|---|
| `QIDI_Q2_CLIENT_NARROW_ASYNC_20261024` | print history sync; `narrow_entry.c` is the source of the 88-byte fragment in `fragment.arm64.elf` | e6b0c3e9 |
| `QIDI_Q2_CLIENT_VERSION_ENTRY_20261026` | version entry | 2b0ef3b4 |
| `QIDI_Q2_SCREEN_QUEUE_PORT_20261028` (+ `..._FEASIBILITY_...`, `..._0302_REVIEW_...` helpers) | GUI queue carried over from QIDI's 01.01.03.02 program | da4b3c9f |

Inputs: the original 01.01.02.04 program (`tools/firmware.py fetch`) and the official 01.01.03.02 program
(downloaded by `tools/screen.py`). No QIDI code is stored here.
