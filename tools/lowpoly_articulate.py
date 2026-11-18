#!/usr/bin/env python3
"""ARTICULATION TEST: turn a joint through its range and report what clips (Claude, 2026-11-18).

Daniel, 2026-11-18: "I think there may be a clipping issue with the arms freely rotating around the shoulder ... Can it torso twist
without something clipping? Needs to be able to rotate 90 degrees to left and right." The HD models are built to articulate
(principle: "imagine that the mech has to articulate"); this checks it. For each angle, the model is posed about its own pivots
(`lowpoly_hd.posed_solids`) and every pair of solids that overlaps now but did NOT overlap at rest is a CLIP (parts built into each
other at rest - a drum in its housing - are not counted).

    python -I tools/lowpoly_articulate.py "Atlas AS7-D"                    # each joint over its recorded "range" (else the standard sweep)
    python -I tools/lowpoly_articulate.py "Atlas AS7-D" waist_turn -90 90  # one joint, one range
PRIVATE (reference_art/).
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lowpoly_ref as L  # noqa: E402
import lowpoly_hd as HD  # noqa: E402

GAP = -0.02          # an overlap deeper than this is a clip (a touch or a hair is not)
SWEEPS = [("waist_turn", -90, 90, 15), ("shoulder_L", -90, 60, 15), ("shoulder_R", -90, 60, 15), ("elbow_L", -45, 75, 15),
          ("elbow_R", -45, 75, 15), ("neck", -45, 45, 15)]


def _name(sid):
    return re.sub(r"_\d+.*$", "", sid)


def overlaps(solids):
    """Pairs (i, j) of solids that overlap, found by bounding boxes then the separating-axis test."""
    import numpy as np
    arrs = [L._solid_arrays(s_) for s_ in solids]
    lo = np.array([np.min(s_["verts"], axis=0) for s_ in solids])
    hi = np.array([np.max(s_["verts"], axis=0) for s_ in solids])
    out = set()
    for i in range(len(solids)):
        cand = np.where(np.all(lo[i + 1:] <= hi[i] + GAP * 0, axis=1) & np.all(hi[i + 1:] >= lo[i], axis=1))[0] + i + 1
        for j in cand:
            if not L.separated(arrs[i], arrs[j], GAP):
                out.add((i, j))
    return out


def sweep(model, joint, a0, a1, step, base_pose=None):
    base_pose = dict(base_pose or {})
    rest = overlaps(HD.posed_solids(model, base_pose))
    ids = [s_["id"] for s_ in L.expand_parts(model)]
    report = {}
    a = a0
    while a <= a1 + 1e-9:
        if abs(a) > 1e-9:
            pose = dict(base_pose, **{joint: a})
            new = overlaps(HD.posed_solids(model, pose)) - rest
            if new:
                report[a] = sorted({(_name(ids[i]), _name(ids[j])) for i, j in new})
        a += step
    return report


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    model = json.load(open(os.path.join(HD.HD_DIR, argv[0] + ".json")))
    if len(argv) > 3:
        sweeps = [(argv[1], float(argv[2]), float(argv[3]), float(argv[4]) if len(argv) > 4 else 15)]
    else:                                                 # a joint's recorded RANGE wins over the standard sweep
        sweeps = []
        for j, a0, a1, st in SWEEPS:
            pv = HD._pivot(model, j)
            if pv:
                r = pv.get("range") or [a0, a1]
                sweeps.append((j, r[0], r[1], st))
    bad = 0
    for joint, a0, a1, step in sweeps:
        rep = sweep(model, joint, a0, a1, step)
        print("%-11s %+4.0f .. %+4.0f: %s" % (joint, a0, a1, "CLEAR" if not rep else "%d angle(s) clip" % len(rep)))
        for a, pairs in sorted(rep.items()):
            print("    %+5.0f  %s" % (a, ", ".join("%s x %s" % p for p in pairs[:8]) + (" ..." if len(pairs) > 8 else "")))
        bad += bool(rep)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
