"""Combat Lab art: a GEOMETRIC AUDIT of the generated 'Mech models (2026-11-04, Claude; review pass).

Usage: python -I tools/token_audit.py <unzipped data/meks.zip folder> [chassis ...] [--detail]

The generator builds every 'Mech from convex blocks. A block model only reads as hardware if every block is
held by another one, so the audit measures, on the same meshes the viewer shows:
  * FLOATING: parts (or clusters of parts) that touch nothing joined to the main body. Exact distances
    between the convex solids (python-fcl); two solids touch when they are closer than TOUCH levels.
  * GROUND: parts below the ground plane (y < 0), deeper than SINK levels.
  * SYMMETRY: the model against its own mirror image (x -> -x). A 'Mech tagged `asym`, or with different
    weapons on each side, is allowed to differ; the score is reported so a change is visible.
Each floating part is named by the source line of `INTEGRATION__tokens.py` that built it.
Art tools only: needs numpy, scipy, trimesh and python-fcl (pip install python-fcl).
"""
import inspect
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

import INTEGRATION__tokens as T
import INTEGRATION__token_mesh as M

TOUCH = 0.004          # levels (2.4 cm at 6 m a level): closer than this counts as joined
SINK = 0.004           # levels: deeper than this below the ground is a fault
_B3_METHODS = {n for n, _ in inspect.getmembers(T.B3, inspect.isfunction)}
_TOKENS_FILE = os.path.abspath(T.__file__)
import INTEGRATION__shell as _SH                            # the skeleton-and-shell builder's frames are named too
_SHELL_FILE = os.path.abspath(_SH.__file__)


class _TrackedParts(list):
    """A part list that remembers, for every part, the line of INTEGRATION__tokens.py that asked for it."""

    def append(self, part):
        src = []
        for fr in inspect.stack()[1:]:
            fn = os.path.abspath(fr.filename)
            if (fn == _TOKENS_FILE and fr.function not in _B3_METHODS) or (fn == _SHELL_FILE and fr.function not in ("add", "emit", "<lambda>", "wrapped")):
                src.append(f"{fr.function}:{fr.lineno}")
                if fr.function in ("_build", "assemble"):
                    break
        part["src"] = " < ".join(src)
        super().append(part)


def _tracked(fn):
    def wrapped(self, *a, **k):
        fn(self, *a, **k)
        self.parts = _TrackedParts()
    return wrapped


T.B3.__init__ = _tracked(T.B3.__init__)


def solids(model):
    """[(cls, tag, src, vertices, faces)] for every convex solid, calibrated like the viewer's."""
    M.calibrate(model)
    return M._raw_parts(model, with_src=True)


def _fcl_obj(v, f):
    import fcl
    m = fcl.BVHModel()
    m.beginModel(len(v), len(f))
    m.addSubModel(v.astype(np.float64), f.astype(np.int32))
    m.endModel()
    return fcl.CollisionObject(m, fcl.Transform())


def contact_graph(parts):
    """Adjacency sets: i ~ j when solids i and j are closer than TOUCH (exact: python-fcl distance)."""
    import fcl
    from scipy.spatial import Delaunay
    n = len(parts)
    lo = np.array([p[3].min(0) for p in parts]) - TOUCH
    hi = np.array([p[3].max(0) for p in parts]) + TOUCH
    objs = [_fcl_obj(p[3], p[4]) for p in parts]
    adj = [set() for _ in range(n)]
    req = fcl.DistanceRequest()
    for i in range(n):
        cand = np.where(np.all(lo[i] <= hi, axis=1) & np.all(hi[i] >= lo, axis=1))[0]
        for j in cand:
            if j <= i:
                continue
            res = fcl.DistanceResult()
            d = fcl.distance(objs[i], objs[j], req, res)
            if d < TOUCH:
                adj[i].add(j)
                adj[j].add(i)
                continue
            # BVH distance is between SURFACES: a solid wholly inside another reads as apart. Check one vertex.
            for a, b in ((i, j), (j, i)):
                try:
                    if Delaunay(parts[b][3]).find_simplex(parts[a][3][:1])[0] >= 0:
                        adj[i].add(j)
                        adj[j].add(i)
                        break
                except Exception:
                    pass
    return adj


def components(adj):
    seen, comps = set(), []
    for s in range(len(adj)):
        if s in seen:
            continue
        stack, comp = [s], []
        seen.add(s)
        while stack:
            u = stack.pop()
            comp.append(u)
            for w in adj[u]:
                if w not in seen:
                    seen.add(w)
                    stack.append(w)
        comps.append(comp)
    comps.sort(key=len, reverse=True)
    return comps


def symmetry(parts):
    """Mean distance (levels) from each vertex to the nearest vertex of the mirrored model: 0 = perfectly mirror-symmetric."""
    from scipy.spatial import cKDTree
    pts = np.vstack([p[3] for p in parts if p[1] != "w"])
    mir = pts * np.array([-1.0, 1.0, 1.0])
    d, _ = cKDTree(pts).query(mir)
    return float(d.mean())


def clip(parts, limit=0.0):
    """CLIP measure (2026-11-04 review, spec section 7): the deepest overlap, in levels, between solids that must only touch.
    Arm cores and plates against the torso's solids, and one leg's solids against the other leg's. Joint covers (role `cover`: a
    pauldron, a disc, a collar) overlap by design and are left out, as are items. Exact: python-fcl penetration depth."""
    import fcl
    pairs = []
    idx = {i: p for i, p in enumerate(parts)}
    objs = {i: _fcl_obj(p[3], p[4]) for i, p in idx.items() if p[6] in ("core", "plate")}
    groups = [("Left Arm", "Center Torso"), ("Left Arm", "Left Torso"), ("Left Arm", "Right Torso"), ("Right Arm", "Center Torso"),
              ("Right Arm", "Left Torso"), ("Right Arm", "Right Torso"), ("Left Leg", "Right Leg")]
    worst = (0.0, "")
    req = fcl.CollisionRequest(num_max_contacts=4, enable_contact=True)
    for la, lb in groups:
        A = [i for i in objs if idx[i][5] == la]
        B = [i for i in objs if idx[i][5] == lb]
        for i in A:
            lo, hi = idx[i][3].min(0), idx[i][3].max(0)
            for j in B:
                if np.any(idx[j][3].min(0) > hi) or np.any(idx[j][3].max(0) < lo):
                    continue
                res = fcl.CollisionResult()
                if fcl.collide(objs[i], objs[j], req, res):
                    d = max((c.penetration_depth for c in res.contacts), default=0.0)
                    if d > worst[0]:
                        worst = (d, f"{la}:{idx[i][2]} v {lb}:{idx[j][2]}")
    return worst


def audit(model):
    parts = solids(model)
    adj = contact_graph(parts)
    comps = components(adj)
    floating = [[parts[i] for i in c] for c in comps[1:]]
    ground = [p for p in parts if p[3][:, 1].min() < -SINK]
    return {"name": model["name"], "parts": len(parts), "floating": floating, "ground": ground,
            "sym": symmetry(parts), "asym": bool(model.get("asym")), "clip": clip(parts) if model.get("shell") else (0.0, "")}


def main(argv):
    from token_sheet import find, find_chassis
    root = argv[0]
    detail = "--detail" in argv
    names = [a for a in argv[1:] if not a.startswith("--")]
    ref = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "token_reference_tags.json"), encoding="utf-8"))
    chassis = names or list(ref) + ["Mad Cat (Timber Wolf) Prime"]
    total_float = total_ground = 0
    for ch in chassis:
        p = find(root, ch) or find_chassis(root, ch)
        if not p:
            print("missing", ch)
            continue
        model = T.build_model(T.read_unit(p), overrides=ref)
        r = audit(model)
        nf = sum(len(c) for c in r["floating"])
        total_float += nf
        total_ground += len(r["ground"])
        print(f"{r['name']:<34} parts {r['parts']:4d}  floating {nf:3d} in {len(r['floating']):2d} clusters  below ground {len(r['ground']):2d}"
              f"  mirror {r['sym']:.4f}{' (asym tag)' if r['asym'] else ''}  clip {r['clip'][0] * 6:.3f} m")
        if detail:
            for c in r["floating"]:
                srcs = sorted({q[2] for q in c})
                ctr = np.vstack([q[3] for q in c]).mean(0)
                print(f"    float x{len(c):<3} at ({ctr[0]:+.3f},{ctr[1]:.3f},{ctr[2]:+.3f})  {', '.join(srcs)[:220]}")
            for q in r["ground"]:
                print(f"    ground {q[3][:, 1].min():+.4f}  {q[2]}")
    print(f"TOTAL floating parts {total_float}, below ground {total_ground}")


if __name__ == "__main__":
    main(sys.argv[1:])
