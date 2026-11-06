"""Build the Combat Lab 3D token viewer (one HTML page, three.js) from the unit library.
Usage: python -I tools/token_3d.py <unzipped data/meks.zip folder> <out.html> [--glb <folder>] [--range]
--range builds only the phase 1 test range of the skeleton-and-shell builder (shell, name hash, and the old blocks)
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

# phase 1 test range of the skeleton-and-shell builder (INTEGRATION__COMBAT_LAB_SKELETON.md section 6): chassis key -> unit file shown
RANGE = [("atlas", "Atlas AS7-D"), ("mad cat", "Mad Cat (Timber Wolf) Prime"), ("locust", "Locust LCT-1V"), ("hunchback", "Hunchback HBK-4G"),
         ("archer", "Archer ARC-2R"), ("jagermech", "JagerMech JM6-S"), ("urbanmech", "UrbanMech UM-R60"), ("wendigo", "Wendigo (Prime)")]
PREFER = {"quickdraw": "Quickdraw QKD-8X"}              # the variant shown for a chassis when the shortest name is not the one wanted (QKD-8X has Stealth armor)
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
    for key, label in (("legs", "legs"), ("arm_style", "arm style"), ("kit", "shoulder kit"), ("feet", "feet"), ("asym", "bigger arm"), ("antennas", "antennas"), ("crouch", "stance")):
        if m.get(key):
            t.append((label, "crouched" if m[key] is True else str(m[key]).replace("_", " ")))
    t.append(("cockpit", f"{m['cockpit_tons']:g} t of {m['tons']} t (head scale x{(m['cockpit_tons'] / max(10, m['tons'])) ** (1 / 3) / (3 / 50) ** (1 / 3):.2f})"))
    if m.get("blocks"):                       # the faceted look's block per slot, and what picked it (a tag or the name hash)
        t.append(("blocks", ", ".join(f"{k} {v[0].replace('_', ' ')}{' (tag)' if v[1] == 'tag' else ''}" for k, v in m["blocks"].items())))
    t.append(("weapons", ", ".join(f"{k.replace('_', ' ')} x{v}" for k, v in sorted(hp.items())) or "none"))
    return t


def main_range(root, out, glb=None):
    """The phase 1 viewer: the test range only, each unit built by the shell builder (reference tags, then name hash only) and, for
    comparison, by the old block builder."""
    ref = json.load(open(os.path.join(HERE, "..", "data", "token_reference_tags.json"), encoding="utf-8"))
    units = []
    for key, fname in RANGE:
        p = find(root, fname)
        if not p:
            print("missing", fname)
            continue
        u = T.read_unit(p)
        mr, mh = T.build_model(u, overrides=ref), T.build_model(u, hash_only=True)
        mo = T.build_model(u, overrides=ref, shell=False)
        tag = ref.get(key, {})
        label = "Timber Wolf" if key == "mad cat" else key.title()
        e = {"id": label.lower().replace(" ", "-"), "name": mr["name"], "chassis": label, "tons": mr["tons"], "levels": mr["drawn_levels"],
             "rules": mr["rules_levels"], "config": mr["config"], "note": tag.get("note", "Named-unit override (data/token_overrides.json): digitigrade legs, canopy torso with wing bays, from the Timber Wolf kit study." if key == "mad cat" else "No reference tags: the name hash alone picks its features."),
             "source": tag.get("source", "override file" if key == "mad cat" else "name hash"), "stealth": bool(mr.get("stealth")), "confidence": tag.get("confidence", ""),
             "ref": M.unit_mesh(mr), "hash": M.unit_mesh(mh), "old": M.unit_mesh(mo), "tags": {"ref": tags(mr), "hash": tags(mh)}}
        if True:                                                 # the faceted look, on every chassis of the range
            mf = T.build_model(u, overrides=ref, style="facet")
            e["facet"] = M.unit_mesh(mf)                         # built first: the blocks are picked while building
            e["tags"]["facet"] = tags(mf)
            mfh = T.build_model(u, hash_only=True, style="facet")  # the faceted look from the name hash alone: what an untagged unit gets
            e["facet_hash"] = M.unit_mesh(mfh)
            e["tags"]["facet_hash"] = tags(mfh)
        units.append(e)
        print(label, mr["shell"], len(e["ref"]["parts"]), "parts", round(mr.get("shell_height_m", 0), 2), "m")
        if glb:
            os.makedirs(glb, exist_ok=True)
            M.write_glb(mr, os.path.join(glb, f"{label.replace(' ', '_')}.glb"))
    page = open(os.path.join(HERE, "token_3d_template.html"), encoding="utf-8").read()
    page = page.replace("/*__DATA__*/null", json.dumps(units, separators=(",", ":")))
    open(out, "w", encoding="utf-8").write(page)
    print(len(units), "units;", len(page) // 1024, "KB")


def main(root, out, glb=None):
    ref = json.load(open(os.path.join(HERE, "..", "data", "token_reference_tags.json"), encoding="utf-8"))
    units = []
    for chassis in ref:
        p = (find(root, PREFER[chassis]) if chassis in PREFER else None) or find_chassis(root, chassis)
        if not p:
            print("missing", chassis)
            continue
        u = T.read_unit(p)
        mr, mh = T.build_model(u, overrides=ref), T.build_model(u, hash_only=True)
        e = {"id": chassis.replace(" ", "-"), "name": mr["name"], "chassis": chassis.title(), "tons": mr["tons"],
             "levels": mr["drawn_levels"], "rules": mr["rules_levels"], "config": mr["config"],
             "note": ref[chassis].get("note", ""), "source": ref[chassis].get("source", "chart tags"), "stealth": bool(mr.get("stealth")),
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
    (main_range if "--range" in a else main)(a[0], a[1], a[a.index("--glb") + 1] if "--glb" in a else None)
