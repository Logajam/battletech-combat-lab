"""
tools/third_party_licenses.py - THIRD_PARTY_LICENSES.txt: the licence of every open-source library compiled into the
programs (btsim, combatlab / CombatLab.exe), with each library's own licence and notice files, as those licences ask.

    python tools/third_party_licenses.py [OUT]        (default: THIRD_PARTY_LICENSES.txt at the repository root)

Reads `cargo tree` (the libraries the two programs really link, every target platform) and `cargo metadata` (each
library's declared licence and source folder), and copies the LICENSE* / COPYING* / NOTICE* / UNLICENSE* files from
each library's source. A text several libraries share word for word is printed once and named by each. Run it after
a change of libraries; tools/package_lab.py puts the file in the download. CREDITS.md says what the file is.
"""
import json
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(REPO_ROOT, "engine")
PROGRAMS = ["combatlab", "btsim"]
OURS = {"btsim", "btsim_core", "combatlab"}


def linked():
    """(name, version) of every library the programs link."""
    out = subprocess.run(["cargo", "tree", "-e", "normal", "--prefix", "none", "--target", "all"] + sum([["-p", p] for p in PROGRAMS], []),
                         cwd=ENGINE, capture_output=True, text=True, check=True).stdout
    found = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].startswith("v") and parts[0] not in OURS:
            found.add((parts[0], parts[1][1:]))
    return found


def main(argv):
    out_path = argv[0] if argv else os.path.join(REPO_ROOT, "THIRD_PARTY_LICENSES.txt")
    meta = json.loads(subprocess.run(["cargo", "metadata", "--format-version", "1"], cwd=ENGINE, capture_output=True, text=True, check=True).stdout)
    want = linked()
    crates = sorted((p for p in meta["packages"] if (p["name"], p["version"]) in want), key=lambda p: p["name"])
    texts = {}            # text -> [crate names]
    rows = []
    for p in crates:
        folder = os.path.dirname(p["manifest_path"])
        files = sorted(f for f in os.listdir(folder) if f.upper().startswith(("LICENSE", "LICENCE", "COPYING", "NOTICE", "UNLICENSE")))
        for f in files:
            full = os.path.join(folder, f)
            if os.path.isfile(full):
                with open(full, encoding="utf-8", errors="replace") as fh:
                    texts.setdefault(fh.read().strip(), []).append(f"{p['name']} {p['version']} ({f})")
        rows.append(f"{p['name']} {p['version']}  -  {p.get('license') or 'see its licence file'}  -  {p.get('repository') or ''}".rstrip(" -"))
    lines = [
        "THIRD-PARTY LICENCES",
        "====================",
        "",
        "The programs of this project (btsim, and combatlab / CombatLab.exe) are built with these open-source Rust",
        "libraries. Each keeps its own licence; their licence and notice files follow the list, word for word (a text",
        "several libraries share is given once, with every library it belongs to). Made by tools/third_party_licenses.py.",
        "",
        f"{len(rows)} libraries (name, version, licence, source):",
        "",
    ] + ["  " + r for r in rows] + [""]
    for i, (text, owners) in enumerate(sorted(texts.items(), key=lambda kv: kv[1][0]), 1):
        lines += ["", "-" * 100, f"Text {i}, from: " + "; ".join(owners), "-" * 100, "", text, ""]
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    print(f"{out_path}: {len(rows)} libraries, {len(texts)} distinct licence texts")


if __name__ == "__main__":
    main(sys.argv[1:])
