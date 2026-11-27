#!/usr/bin/env python3
"""Copies MegaMek's top-down 'Mech images, every one its unit list (mekset.txt) points to, into engine/lab/web/sprites/ UNCHANGED, and writes
engine/lab/web/spritemap.js, the map from a unit's name to its picture, so every stock 'Mech the 3D tabletop shows wears its own sprite
(Daniel, 2026-11-27: "Every stock unit in use from megamek should use its actual sprite").

    python tools/make_mechsprites_all.py --mmdata /path/to/mm-data     # a checkout of github.com/MegaMek/mm-data (data/images/units/meks + mekset.txt)

Licence (confirmed against MegaMek's own LICENSE / LICENSE.assets, CREDITS.md): CC BY-NC-SA 4.0, non-commercial only; the credit file
sprites/CREDITS.txt (with the artists MegaMek names in mekset.txt) ships with the images. Never relicense them. Run again after a MegaMek update."""
import argparse, json, os, re, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "engine", "lab", "web")
norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())

ap = argparse.ArgumentParser(); ap.add_argument("--mmdata", required=True); a = ap.parse_args()
units = os.path.join(a.mmdata, "data", "images", "units")
exact, chassis, files, credits = {}, {}, set(), []
for line in open(os.path.join(units, "mekset.txt"), encoding="utf-8", errors="replace"):
    if line.startswith("#"):
        c = line[1:].strip()
        if c and c != "Credits:" and not c.startswith("("): credits.append(c)
        continue
    m = re.match(r'^(exact|chassis)\s+"([^"]+)"\s+"([^"]+)"', line)
    if not m or not m.group(3).startswith("meks/"): continue
    kind, name, path = m.groups(); f = path[5:]
    if not os.path.exists(os.path.join(units, "meks", f)): continue
    (exact if kind == "exact" else chassis)[norm(name)] = f; files.add(f)
dst = os.path.join(OUT, "sprites"); shutil.rmtree(dst, ignore_errors=True); os.makedirs(dst)
for f in sorted(files): shutil.copyfile(os.path.join(units, "meks", f), os.path.join(dst, f))
open(os.path.join(dst, "CREDITS.txt"), "w").write(
    "MegaMek top-down unit images, unchanged. (C) The MegaMek Team and the unit image artists, licensed under Creative Commons\n"
    "Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0): https://creativecommons.org/licenses/by-nc-sa/4.0/\n"
    "Source: https://github.com/MegaMek/mm-data (data/images/units/meks, named by mekset.txt). Non-commercial use only; do not relicense.\n"
    "BattleTech, MechWarrior and BattleMech are trademarks of their owners; this is an unofficial fan work.\n\n"
    "Artists named in MegaMek's mekset.txt:\n" + "\n".join("  " + c for c in credits) + "\n")
open(os.path.join(OUT, "spritemap.js"), "w").write(
    "// Unit name -> MegaMek sprite file in sprites/ (made by tools/make_mechsprites_all.py; images CC BY-NC-SA 4.0, see sprites/CREDITS.txt).\n"
    "// Keys are the unit's name with everything but letters and digits dropped, lower case: exact = chassis + model, chassis = the chassis alone.\n"
    "window.MECH_SPRITE_MAP = " + json.dumps({"exact": exact, "chassis": chassis}, separators=(",", ":"), sort_keys=True) + ";\n")
print(f"{len(files)} images, {len(exact)} exact names, {len(chassis)} chassis -> {dst}")
