"""
tools/package_lab.py - Combat Lab for Windows as one zip Daniel downloads, unpacks and starts (CombatLab.exe).

    python tools/package_lab.py OUT_DIR [--version alpha-1] [--split]

Builds the Lab for Windows (cargo, target x86_64-pc-windows-gnu: needs `rustup target add x86_64-pc-windows-gnu` and the
MinGW compiler and strip, `apt-get install gcc-mingw-w64-x86-64 binutils-mingw-w64-x86-64`), then writes OUT_DIR/CombatLab-<version>.zip:

    CombatLab/
        CombatLab.exe                 the whole engine and the pages, in one program (needs nothing else installed)
        README.txt                    how to start it
        engine/defaults/config.json   the engine's settings defaults (the program finds its folder by this file)
        data/                         the units (*.mtf; the unit pack as meks.pack.xz) and boards (*.board, maps.zip)

The program writes beside itself: lab_cache/ (the unit list, built on first start) and data/meks/, data/maps/ (units
and boards unpacked from the packs when first used), and copies unit files dropped on a team into data/.
"""
import io
import lzma
import os
import shutil
import subprocess
import sys
import zipfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = "x86_64-pc-windows-gnu"

README = """COMBAT LAB ({version})
==========================

If it came in two parts (-program and -data): unzip both into the SAME folder, so that the folder CombatLab holds
CombatLab.exe, README.txt, engine and data together. (Unzip the first one; then unzip the second one to the same
place - Windows asks whether to merge the CombatLab folders: yes.)

Start: double-click CombatLab.exe. A black window opens (the program) and Combat Lab opens in your web browser.
Close the black window to stop Combat Lab. If the browser does not open, type the address the black window shows
(http://127.0.0.1:8765/ or near it) into your browser.

Windows may warn the first time ("Windows protected your PC"): the program is not signed. Choose "More info", then
"Run anyway". Nothing leaves your computer: only this computer's browser can reach Combat Lab.

Keep the folder together: CombatLab.exe reads the units and boards in data/ and its settings in engine/defaults/.
Unit files (.mtf) you drop on a team are copied into data/. The first start takes a few seconds longer (it builds the
unit list once; it is kept in lab_cache/).
"""


def main(argv):
    out = os.path.abspath(argv[0])
    version = argv[argv.index("--version") + 1] if "--version" in argv else "alpha"
    engine = os.path.join(REPO_ROOT, "engine")
    subprocess.run(["cargo", "build", "--release", "-p", "combatlab", "--target", TARGET], cwd=engine, check=True)
    stage = os.path.join(out, "CombatLab")
    if os.path.exists(stage):
        shutil.rmtree(stage)
    os.makedirs(os.path.join(stage, "engine", "defaults"))
    os.makedirs(os.path.join(stage, "data"))
    shutil.copy(os.path.join(engine, "target", TARGET, "release", "combatlab.exe"), os.path.join(stage, "CombatLab.exe"))
    shutil.copy(os.path.join(engine, "defaults", "config.json"), os.path.join(stage, "engine", "defaults", "config.json"))
    data = os.path.join(REPO_ROOT, "data")
    for name in sorted(os.listdir(data)):
        if name.endswith((".mtf", ".board")) or name == "maps.zip":
            shutil.copy(os.path.join(data, name), os.path.join(stage, "data", name))
    # the unit pack as one xz block (a tenth of meks.zip's size); CombatLab.exe makes meks.zip from it on the first start
    # (engine/lab/src/catalog.rs, unpack_solid: per file, name length, name, content length, content)
    block = io.BytesIO()
    with zipfile.ZipFile(os.path.join(data, "meks.zip")) as z:
        for info in z.infolist():
            if info.filename.endswith(".mtf"):
                name, body = info.filename.encode("utf-8"), z.read(info)
                block.write(len(name).to_bytes(4, "little") + name + len(body).to_bytes(4, "little") + body)
    with open(os.path.join(stage, "data", "meks.pack.xz"), "wb") as f:
        f.write(lzma.compress(block.getvalue(), format=lzma.FORMAT_XZ, check=lzma.CHECK_CRC64, preset=9 | lzma.PRESET_EXTREME))
    # no debugging symbols: a smaller download
    subprocess.run(["x86_64-w64-mingw32-strip", os.path.join(stage, "CombatLab.exe")], check=True)
    with open(os.path.join(stage, "README.txt"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(README.format(version=version))
    # --split: two zips, the program and the data, both under the same CombatLab/ folder, so unzipping both into one
    # place merges them (for an upload that takes only ~3 MB a file); otherwise one zip
    parts = {"": lambda rel: True}
    if "--split" in argv:
        is_data = lambda rel: rel.startswith(os.path.join("CombatLab", "data") + os.sep)
        parts = {"-program": lambda rel: not is_data(rel), "-data": is_data}
    for suffix, keep in parts.items():
        zip_path = os.path.join(out, f"CombatLab-{version}{suffix}.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for root, _, files in os.walk(stage):
                for name in sorted(files):
                    full = os.path.join(root, name)
                    rel = os.path.relpath(full, out)
                    if keep(rel):
                        z.write(full, rel)
        print(f"{zip_path}: {os.path.getsize(zip_path) / 1e6:.2f} MB")


if __name__ == "__main__":
    main(sys.argv[1:])
