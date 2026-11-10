#!/usr/bin/env python3
"""QIDI Q2 02.04 Tweaked - rebuild the screen program on the PC.

The screen program (/home/qidi/QIDI_Client/bin/qidiclient) is QIDI's closed
binary, so it is not in this repository. The changes are rebuilt here, on
your PC, from QIDI's own official packages:

  1. the original 01.01.02.04 program  (tools/firmware.py fetch)
  2. the official 01.01.03.02 program  (downloaded from QIDI by this tool; its
     print-queue code is carried over to 02.04 - "screen queue port")

and the build scripts in screen/ (our own code). Every stage must give the
exact expected SHA-256, otherwise the build stops:

  02.04 original 21d0c448 -> history sync (28) e6b0c3e9 -> version entry (28b)
  2b0ef3b4 -> queue port da4b3c9f

Small text/byte changes on top (update check off, dark-mode popup) are normal
modules in modules/. Needs: pip install capstone (see requirements.txt).

    python tools/screen.py build
"""
import hashlib
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import firmware  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "screen"
WORK = REPO / "work" / "screen"
CLIENT = "/home/qidi/QIDI_Client/bin/qidiclient"

V0302_URL = ("https://public-cdn.qidimaker.com/upgrade/3DPrinter/QD_Q2/01.01.03.02/"
             "yjwvejt6ui/QD_Q2_01.01.03.02_20261023_Release.zip")
V0302_ZIP = "QD_Q2_01.01.03.02_20261023_Release.zip"
V0302_ZIP_SHA256 = "b42f83d0e1bbc002e62db6276c2a5739fb3343522ee071829ff8c5f56f7f2fcb"
V0302_SOC = "QD_Q2_SOC_01.01.03.02_20261023_Release_NA"
V0302_CLIENT_SHA256 = "c222bb9c77df6fe714e974f915834841be96c291bb75d44cd6f4d371e174f423"

STOCK_SHA256 = "21d0c448a1c0f6d974e4a10d8ba787fe26a7bf7b5e30c2638b5c5dbce9029af3"
STAGES = [  # (folder, script, output file, expected SHA-256)
    ("QIDI_Q2_CLIENT_NARROW_ASYNC_20261024", ["build_full_copy.py"],
     "qidiclient.CANDIDATE_NOT_INSTALLED", "e6b0c3e95cdbf6db52a9a3c2638a0c5cbf76a8ee7096e749727631a26a8f4c51"),
    ("QIDI_Q2_CLIENT_VERSION_ENTRY_20261026", ["build_private_candidate.py"],
     "qidiclient.VERSION_ENTRY_PRIVATE_DO_NOT_INSTALL", "2b0ef3b449b8d2e319f3c972325681f116ba1a479c688993752f1b40cb853e6a"),
    ("QIDI_Q2_SCREEN_QUEUE_PORT_20261028",
     ["inspect_port_metadata.py", "inspect_bindings.py", "inspect_exception_tables.py", "inspect_startup.py",
      "build_fragment.py", "build_candidate.py", "fix_static_initializer_r2.py"],
     "qidiclient.QUEUE_PORT_R2_LAPTOP_ONLY", "da4b3c9f9ca38660b10d452ee307285558317a02c4346c9650a5e05c7aa2e7b9"),
]
RESULT_SHA256 = STAGES[-1][3]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def client_0302():
    cached = WORK / "inputs" / "qidiclient-01.01.03.02"
    if cached.is_file() and sha(cached.read_bytes()) == V0302_CLIENT_SHA256:
        return cached.read_bytes()
    zip_path = firmware.DOWNLOADS / V0302_ZIP
    if not zip_path.is_file() or firmware.sha256_file(zip_path) != V0302_ZIP_SHA256:
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        print("Downloading the official 01.01.03.02 package from QIDI (about 245 MB)...")
        req = urllib.request.Request(V0302_URL, headers={"User-Agent": "qidi-q2-0204-tweaked"})
        part = zip_path.with_name(zip_path.name + ".part")
        with urllib.request.urlopen(req, timeout=60) as resp, open(part, "wb") as out:
            shutil.copyfileobj(resp, out, 1 << 20)
        part.replace(zip_path)
        if firmware.sha256_file(zip_path) != V0302_ZIP_SHA256:
            sys.exit("The downloaded 01.01.03.02 package has the wrong SHA-256; delete it and try again.")
    print("Taking the 01.01.03.02 screen program out of the package...")
    with zipfile.ZipFile(zip_path) as zf, zf.open(V0302_SOC) as soc:
        for name, offset, size in firmware.ar_members(soc):
            if name == "data.tar.xz":
                soc.seek(offset)
                with tarfile.open(fileobj=soc, mode="r|xz") as tf:
                    for member in tf:
                        if member.name == "." + CLIENT:
                            data = tf.extractfile(member).read()
                            break
                    else:
                        raise SystemExit("screen program not found in 01.01.03.02")
                break
    if sha(data) != V0302_CLIENT_SHA256:
        sys.exit("The 01.01.03.02 screen program is not the expected one.")
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(data)
    return data


def build():
    """Return the rebuilt screen program (bytes), SHA-256 checked at every stage."""
    try:
        import capstone  # noqa: F401
    except ImportError:
        sys.exit("capstone is missing. Run:  py -m pip install -r requirements.txt")
    final = WORK / "W" / STAGES[-1][0] / STAGES[-1][2]
    if final.is_file() and sha(final.read_bytes()) == RESULT_SHA256:
        return final.read_bytes()
    stock = firmware.extract(CLIENT)
    if sha(stock) != STOCK_SHA256:
        sys.exit("The 02.04 screen program is not the expected one.")
    new = client_0302()
    tree = WORK / "W"
    if tree.exists():
        shutil.rmtree(tree)
    shutil.copytree(SCRIPTS, tree)
    inputs = {
        tree / "QIDI_Q2_CLIENT_REA_REVIEW_20261024/inputs/qidiclient": stock,
        tree / "QIDI_Q2_FIRMWARE_0302_REVIEW_20261028/changed-files/home/qidi/QIDI_Client/bin/qidiclient": new,
    }
    for path, data in inputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    for folder, scripts, output, expected in STAGES:
        for script in scripts:
            print("  screen build:", folder.split("_")[-2].lower(), script)
            run = subprocess.run([sys.executable, script], cwd=tree / folder,
                                 capture_output=True, text=True)
            if run.returncode != 0:
                (WORK / "error.log").write_text(run.stdout + run.stderr, encoding="utf-8")
                sys.exit("Screen build step %s failed; see %s" % (script, WORK / "error.log"))
        got = sha((tree / folder / output).read_bytes())
        if got != expected:
            sys.exit("Screen build stage %s gave %s, expected %s" % (folder, got[:12], expected[:12]))
    return final.read_bytes()


if __name__ == "__main__":
    if sys.argv[1:] != ["build"]:
        sys.exit(__doc__)
    data = build()
    print("Screen program rebuilt: %s (%d bytes)" % (sha(data)[:12], len(data)))
