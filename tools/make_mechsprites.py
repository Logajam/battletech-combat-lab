#!/usr/bin/env python3
"""Packs MegaMek's top-down unit images (reference_art/megamek_sprites/*.png) into engine/lab/web/mechsprites.js, the sprites the 3D tabletop
puts on its unit bases (PROJECT_MAP P10). The images are unchanged (CC BY-NC-SA 4.0, credit in CREDITS.md, MegaMek's notice kept in the file);
the page loads the file with the 3D view. Run again after adding images."""
import base64, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "reference_art", "megamek_sprites"); OUT = os.path.join(ROOT, "engine", "lab", "web", "mechsprites.js")
d = {}
for n in sorted(os.listdir(SRC)):
    if n.lower().endswith(".png"):
        d[n[:-4]] = "data:image/png;base64," + base64.b64encode(open(os.path.join(SRC, n), "rb").read()).decode()
head = ("// MegaMek top-down unit images (84 x 72, forward is up), unchanged. (C) The MegaMek Team and the unit image artists, CC BY-NC-SA 4.0:\n"
        "// https://creativecommons.org/licenses/by-nc-sa/4.0/ . Non-commercial use only; see CREDITS.md. Made by tools/make_mechsprites.py.\n")
open(OUT, "w").write(head + "window.MECH_SPRITES = " + json.dumps(d, separators=(",", ":")) + ";\n")
print(f"{len(d)} sprites -> {OUT} ({os.path.getsize(OUT) // 1024} KB)")
