"""Build the Combat Lab 3D token viewer (one HTML page, three.js) from the unit library.
Usage: python -I tools/token_3d.py <unzipped data/meks.zip folder> <out.html> [--glb <folder>]
Every chassis in data/token_reference_tags.json is built twice (reference tags applied /
name hash only); --glb also writes one .glb per unit. Art tools: needs numpy, scipy, trimesh."""
import html
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))      # -I drops the script folder
import INTEGRATION__tokens as T
import INTEGRATION__token_mesh as M
from token_sheet import find, find_chassis

EXTRAS = [("Mad Cat (Timber Wolf) Prime", "Timber Wolf")]     # units that live in data/token_overrides.json, not in the chart tags

HERE = os.path.dirname(os.path.abspath(__file__))


def tags(m):
    hp = {}
    for g in m["hardpoints"]:
        hp[g["mount"]] = hp.get(g["mount"], 0) + g["count"]
    t = [("archetype", m["archetype"]), ("torso", m["torso"]), ("plan", m["plan"]), ("profile", m["profile"]),
         ("head", f"{m['head_mount']} / {m['head_shape']}"), ("shoulders", m["shoulders"]), ("hips", m["hips"])]
    if m["arms"]:
        t.append(("arms", "/".join(m["arms"][c] for c in "LR")))
    for key, label in (("legs", "legs"), ("arm_style", "arm style"), ("kit", "shoulder kit")):
        if m.get(key):
            t.append((label, m[key].replace("_", " ")))
    t.append(("weapons", ", ".join(f"{k.replace('_', ' ')} x{v}" for k, v in sorted(hp.items())) or "none"))
    return t


def main(root, out, glb=None):
    ref = json.load(open(os.path.join(HERE, "..", "data", "token_reference_tags.json"), encoding="utf-8"))
    units = []
    for chassis in ref:
        p = find_chassis(root, chassis)
        if not p:
            print("missing", chassis)
            continue
        u = T.read_unit(p)
        mr, mh = T.build_model(u, overrides=ref), T.build_model(u, hash_only=True)
        e = {"id": chassis.replace(" ", "-"), "name": mr["name"], "chassis": chassis.title(), "tons": mr["tons"],
             "levels": mr["drawn_levels"], "rules": mr["rules_levels"], "config": mr["config"],
             "note": ref[chassis].get("note", ""), "source": ref[chassis].get("source", "chart tags"),
             "confidence": ref[chassis].get("confidence", ""),
             "ref": M.unit_mesh(mr), "hash": M.unit_mesh(mh), "tags": {"ref": tags(mr), "hash": tags(mh)}}
        units.append(e)
        if glb:
            os.makedirs(glb, exist_ok=True)
            M.write_glb(mr, os.path.join(glb, f"{chassis.replace(' ', '_')}.glb"))
    for fname, label in EXTRAS:
        p = find(root, fname)
        if not p:
            print("missing", fname)
            continue
        u = T.read_unit(p)
        mr, mh = T.build_model(u, overrides=ref), T.build_model(u, hash_only=True)
        units.append({"id": label.lower().replace(" ", "-"), "name": mr["name"], "chassis": label, "tons": mr["tons"],
                      "levels": mr["drawn_levels"], "rules": mr["rules_levels"], "config": mr["config"],
                      "note": "Named-unit override (data/token_overrides.json): digitigrade legs, canopy torso with wing bays, from the Timber Wolf kit study.",
                      "source": "override file", "confidence": "high", "ref": M.unit_mesh(mr), "hash": M.unit_mesh(mh),
                      "tags": {"ref": tags(mr), "hash": tags(mh)}})
        if glb:
            M.write_glb(mr, os.path.join(glb, f"{label.replace(' ', '_')}.glb"))
    units.sort(key=lambda x: (x["tons"], x["name"]))
    page = open(os.path.join(HERE, "token_3d_template.html"), encoding="utf-8").read()
    page = page.replace("/*__DATA__*/null", json.dumps(units, separators=(",", ":")))
    open(out, "w", encoding="utf-8").write(page)
    print(len(units), "units;", len(page) // 1024, "KB")


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1], a[a.index("--glb") + 1] if "--glb" in a else None)
