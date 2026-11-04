"""
tests/test_token_joined.py - the Combat Lab block models hold together (review pass, 2026-11-04).

    python tests/test_token_joined.py

A block model only reads as hardware if every block is held by another one. For a set of units that each had a
different builder fault (arm guns hanging beside the forearm, tube mouths in front of a slanted bay, an arm beside a
leaning torso, a head turret over a built-in cockpit, a Gauss rifle off its mount, jump jets behind the calf, feet
under martian legs...), with reference tags and with the name hash only: no part may float free of the body and none
may sink below the ground. The same measurement over all chart units: python -I tools/token_audit.py <meks folder>.
Needs numpy, scipy, trimesh and python-fcl (art tools); without them the check says so and passes.
"""

import os
import sys
import tempfile
import zipfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

try:
    import numpy  # noqa: F401
    import scipy  # noqa: F401
    import trimesh  # noqa: F401
    import fcl  # noqa: F401
    HAVE = True
except ImportError:
    HAVE = False

# (unit file, hash_only)
CASES = [("Atlas AS7-H", False), ("Locust LCT-3V", False), ("Mad Cat (Timber Wolf) Prime", False), ("Highlander HGN-694", False),
         ("Cataphract CTF-0X", False), ("Vindicator VND-5L", False), ("Awesome AWS-9M", False), ("Panther PNT-8Z", False),
         ("Trebuchet TBT-3C", True), ("Crab CRB-27", True), ("Hunchback HBK-7S", True), ("Wolverine WVR-1R", True)]


def main():
    if not HAVE:
        print("PASS  numpy / scipy / trimesh / python-fcl not installed: joined-blocks check skipped (art tools only)")
        return 0
    import json
    import INTEGRATION__tokens as T
    import token_audit as A
    ref = json.load(open(os.path.join(REPO_ROOT, "data", "token_reference_tags.json"), encoding="utf-8"))
    z = zipfile.ZipFile(os.path.join(REPO_ROOT, "data", "meks.zip"))
    names = {os.path.basename(n).lower(): n for n in z.namelist() if n.lower().endswith(".mtf")}
    bad, seen = [], 0
    for u, hash_only in CASES:
        key = (u + ".mtf").lower()
        if key not in names:
            continue
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, os.path.basename(names[key]))
            open(path, "wb").write(z.read(names[key]))
            unit = T.read_unit(path)
        model = T.build_model(unit, hash_only=True) if hash_only else T.build_model(unit, overrides=ref)
        r = A.audit(model)
        seen += 1
        nf = sum(len(c) for c in r["floating"])
        if nf:
            srcs = sorted({q[2] for c in r["floating"] for q in c})
            bad.append(f"{u}{' (hash)' if hash_only else ''}: {nf} floating parts ({', '.join(srcs)[:160]})")
        if r["ground"]:
            bad.append(f"{u}: {len(r['ground'])} parts below the ground")
    if bad or not seen:
        print("FAIL  " + ("; ".join(bad) or "no unit files found"))
        return 1
    print(f"PASS  {seen} models: every block joined to the body, nothing below the ground")
    return 0


if __name__ == "__main__":
    sys.exit(main())
