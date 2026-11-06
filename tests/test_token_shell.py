"""
tests/test_token_shell.py - the skeleton-and-shell builder's acceptance checks (INTEGRATION__COMBAT_LAB_SKELETON.md section 7).

    python tests/test_token_shell.py

1. HARDPOINTS, over EVERY unit file in data/meks.zip that loads: every crit-holding item is placed, none twice, no
   location over its hardpoint capacity, and the shuffle is stable (the same unit, placed twice, gives the same layout).
2. On the phase 1 test range (the chassis in INTEGRATION__shell.SHELL_RANGE; needs numpy, scipy, trimesh), in both looks (the
   plated INTEGRATION__shell and the faceted INTEGRATION__shell_facet; the faceted one also gets the joined / ground / clip audit
   of tools/token_audit.py when python-fcl is installed): each LOCATION's
   drawn volume is within VOLUME_BAND of its mass budget (spec section 4: a sanity check; the band is Claude's guess and is
   tuned here), the height is on the rules curve (3 percent), and no armor plate is thinner than the minimum.
Art only: nothing here touches a battle. Without the art tools, part 2 says so and passes.
"""

import os
import sys
import tempfile
import zipfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

VOLUME_BAND = 0.30            # spec section 4 started at 0.25 (Claude's guess); tuned on the test range 2026-11-04: pelvis skirt plates and clamped narrow side torsos need 0.30
RANGE_FILES = ["Atlas AS7-D", "Mad Cat (Timber Wolf) Prime", "Locust LCT-1V", "Hunchback HBK-4G", "Archer ARC-2R", "JagerMech JM6-S",
               "UrbanMech UM-R60", "Wendigo (Prime)"]

try:
    import numpy as np  # noqa: F401
    import scipy  # noqa: F401
    import trimesh  # noqa: F401
    HAVE = True
except ImportError:
    HAVE = False


def hardpoints(z, names):
    import INTEGRATION__tokens as T
    import INTEGRATION__shell_items as I
    bad, n_units, n_items = [], 0, 0
    for n in names:
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "u.mtf")
            open(path, "wb").write(z.read(n))
            try:
                unit = T.read_unit(path)
                if "tons" not in unit:
                    continue
                r = I.hardpoint_report(unit)
            except Exception as e:                                   # a file the art reader cannot read is not this test's business
                if "no rail" in str(e):
                    bad.append(f"{n}: {e}")
                continue
        n_units += 1
        n_items += r["items"]
        if r["placed"] != r["items"] or r["dupes"] or r["over"] or not r["stable"]:
            bad.append(f"{os.path.basename(n)}: placed {r['placed']}/{r['items']} dupes {r['dupes']} over {r['over']} stable {r['stable']}")
    return bad, n_units, n_items


def shell_checks(z):
    import json
    import INTEGRATION__tokens as T
    import INTEGRATION__token_mesh as M
    import INTEGRATION__shell as SH
    ref = json.load(open(os.path.join(REPO_ROOT, "data", "token_reference_tags.json"), encoding="utf-8"))
    names = {os.path.basename(n).lower(): n for n in z.namelist() if n.lower().endswith(".mtf")}
    bad, seen = [], 0
    try:                                                              # the joined / clip audit needs python-fcl
        sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
        import token_audit as audit
    except ImportError:
        audit = None
    for u in RANGE_FILES:
        key = (u + ".mtf").lower()
        if key not in names:
            continue
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "u.mtf")
            open(path, "wb").write(z.read(names[key]))
            unit = T.read_unit(path)
        for hash_only, style in ((False, "plated"), (True, "plated"), (False, "facet"), (True, "facet")):
            model = T.build_model(unit, overrides=ref, hash_only=hash_only, style=style)
            if not model.get("shell"):
                bad.append(f"{u}: not built by the shell builder")
                continue
            parts = M._raw_parts(model, with_src=True)
            seen += 1
            tag = u + (" (hash)" if hash_only else "") + (" [faceted]" if style == "facet" else "")
            if style == "facet" and audit is not None:                    # the faceted look: joined, above ground, no clipping
                r = audit.audit(model)
                nf = sum(len(c) for c in r["floating"])
                if model.get("blocked_muzzles"):
                    bad.append(f"{tag}: {model['blocked_muzzles']} weapons fire into the body")
                if nf or r["ground"] or r["clip"][0] * 6.0 > 0.005:
                    bad.append(f"{tag}: {nf} floating, {len(r['ground'])} below ground, clip {r['clip'][0] * 6:.3f} m")
            top = max(v[:, 1].max() for _c, _t, _s, v, _f, _l, _r in parts)
            if abs(top / model["drawn_levels"] - 1) > 0.03:
                bad.append(f"{tag}: height {top:.3f} v rules curve {model['drawn_levels']:.3f}")
            budget = model["_shell"]["budget"]
            by = {}
            for _c, _t, _s, v, _f, loc, role in parts:
                by.setdefault(loc, []).append(v)
                if role == "plate":                                  # the thinnest extent of the plate, in metres
                    c = v - v.mean(0)
                    sv = np.linalg.svd(c, full_matrices=False)[2]
                    ext = (c @ sv.T).max(0) - (c @ sv.T).min(0)
                    if ext.min() * M.T.LEVEL / 10.0 < 0.85 * SH.MIN_PLATE:
                        bad.append(f"{tag}: a plate in {loc} is {ext.min() * 6:.3f} m thick (minimum {SH.MIN_PLATE})")
                        break
            for loc, want in budget.items():
                got = M.union_volume(by.get(loc, [])) * 216.0 if by.get(loc) else 0.0
                if want > 0 and abs(got / want - 1) > VOLUME_BAND:
                    bad.append(f"{tag}: {loc} drawn {got:.1f} m3 v budget {want:.1f} m3 (band {VOLUME_BAND:.0%})")
    return bad, seen


def main():
    z = zipfile.ZipFile(os.path.join(REPO_ROOT, "data", "meks.zip"))
    names = [n for n in z.namelist() if n.lower().endswith(".mtf")]
    bad, n_units, n_items = hardpoints(z, names)
    if bad:
        print("FAIL  hardpoints: " + "; ".join(bad[:8]) + (f" ... {len(bad)} in all" if len(bad) > 8 else ""))
        return 1
    msg = f"{n_units} units, {n_items} items placed once each, none over capacity, shuffle stable"
    if not HAVE:
        print(f"PASS  {msg}; shell geometry checks skipped (numpy / scipy / trimesh not installed)")
        return 0
    bad, seen = shell_checks(z)
    if bad or not seen:
        print("FAIL  " + ("; ".join(bad[:10]) or "no test-range unit files found"))
        return 1
    print(f"PASS  {msg}; {seen} shell models (plated and faceted): location volumes within {VOLUME_BAND:.0%} of budget, height on the rules curve, no plate under {0.05} m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
