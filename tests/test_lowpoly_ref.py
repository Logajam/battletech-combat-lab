"""
tests/test_lowpoly_ref.py - the low-poly reference models (reference_art/, Daniel 2026-11-16)

    python tests/test_lowpoly_ref.py

Every model in reference_art/models must: stay under 800 triangles; show a pelvis, torso, head and both legs and arms as
separate assemblies; stand on y = 0; and carry exactly the weapons and jump-jet locations its unit file lists
(tools/lowpoly_ref.py `check`). Every unit in units.json must name a unit file that exists, and the folder must stay on
tools/publish_public.py's private list (the TRO drawings are Catalyst artwork). The block library (reference_art/blocks,
tools/lowpoly_blocks.py `check`) passes its check. Art only: nothing here touches a battle.
"""
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
import lowpoly_blocks as B  # noqa: E402
import lowpoly_ref as L  # noqa: E402
import publish_public  # noqa: E402


def main():
    bad = 0
    units = json.load(open(os.path.join(L.REF, "units.json")))["units"]
    for u in units:
        try:
            L.read_mtf(u["unit"])
        except FileNotFoundError:
            print("FAIL units.json: no unit file for", u["unit"]); bad += 1
        if not os.path.exists(os.path.join(L.REF, u["original"])):
            print("FAIL units.json: no original picture for", u["unit"]); bad += 1
    built = [f for f in sorted(os.listdir(L.MODELS)) if f.endswith(".json")]
    for f in built:
        errors, notes = L.check_model(json.load(open(os.path.join(L.MODELS, f))))
        for e in errors:
            print("FAIL %s: %s" % (f, e)); bad += 1
        if f[:-5] not in {u["unit"] for u in units}:
            print("FAIL %s: not listed in units.json" % f); bad += 1
    # the block library (T15a, 2026-11-17): every block generates at HIGH and LOW with the same anchors and mounts, LOW
    # within its budget and its outline close to HIGH's, the reference crop inside its picture, a verdict recorded
    errors, rows = B.check(B.library())
    for e in errors:
        print("FAIL block", e); bad += 1
    # whole 'Mechs on the socket skeleton (2026-11-17): every unit's two builds at both levels are one connected piece, stand on
    # the ground, and every seated block found its surface (tools/lowpoly_assemble.py check)
    import lowpoly_assemble as A
    for e in A.check_all():
        print("FAIL mech", e); bad += 1
    # HD models (reference_art/models_hd: no triangle budget; the simplified models are made from them later)
    hd_dir = os.path.join(L.REF, "models_hd")
    for f in sorted(os.listdir(hd_dir)) if os.path.isdir(hd_dir) else []:
        if f.endswith(".json"):
            errors, notes = L.check_model(json.load(open(os.path.join(hd_dir, f))))
            for e in errors:
                print("FAIL HD %s: %s" % (f, e)); bad += 1
    if "reference_art/" not in publish_public.PRIVATE_PATHS:
        print("FAIL reference_art/ is not in publish_public.PRIVATE_PATHS"); bad += 1
    print("%s: %d units indexed, %d models built, %d blocks" % ("FAIL" if bad else "OK", len(units), len(built), len(rows)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
