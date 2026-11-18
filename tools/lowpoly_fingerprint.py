#!/usr/bin/env python3
"""Geometry fingerprints of the HD models, for refactoring them into HD blocks (T15c item B; Claude, 2026-11-18).

A refactor (a builder's code turned into a library block) must not change the model: the fingerprint is every solid's vertices
(rounded to 0.001) with its assembly, role and tone - part ids and part order ignored - plus the pivots, mounts and centre of mass.

    python -I tools/lowpoly_fingerprint.py save DIR      # before the change
    python -I tools/lowpoly_fingerprint.py compare DIR   # after it: SAME, or how many solids differ
PRIVATE (reference_art/).
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lowpoly_ref as L  # noqa: E402


def fingerprint(path):
    m = json.load(open(path))
    solids = sorted((s["assembly"], s.get("role") or "", round(s.get("tone") or 0, 3),
                     tuple(sorted(tuple(round(c, 3) for c in v) for v in s["verts"]))) for s in L.expand_parts(m))
    return json.loads(json.dumps([solids, m.get("pivots"), m.get("mounts"), m.get("centre_of_mass")]))


def main(argv):
    if len(argv) != 2 or argv[0] not in ("save", "compare"):
        print(__doc__)
        return 2
    mode, d = argv
    os.makedirs(d, exist_ok=True)
    bad = 0
    for p in sorted(glob.glob(os.path.join(L.REF, "models_hd", "*.json"))):
        name = os.path.basename(p)
        cur = fingerprint(p)
        if mode == "save":
            json.dump(cur, open(os.path.join(d, name), "w"))
            print("saved", name)
            continue
        if not os.path.exists(os.path.join(d, name)):
            print(name, "NEW (no saved fingerprint)")
            continue
        old = json.load(open(os.path.join(d, name)))
        parts = ["geometry", "pivots", "mounts", "centre of mass"]
        diff = [n for n, a, b in zip(parts, old, cur) if a != b]
        print(name, "SAME" if not diff else "DIFFERENT: " + ", ".join(diff))
        if "geometry" in diff:
            a, b = set(map(json.dumps, old[0])), set(map(json.dumps, cur[0]))
            print("   solids only before: %d, only after: %d" % (len(a - b), len(b - a)))
        bad += bool(diff)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
