#!/usr/bin/env python3
"""Low-poly REFERENCE models of the TRO 3025 'Mechs (art only; nothing here touches a battle).

Daniel, 2026-11-16: the TRO drawings are redrawn as strict low-polygon models (boxes, wedges, 6/8-sided
prisms, hulls and domes, under 800 triangles, A-stance), five orthographic views each. These models are REFERENCE material:
the "lego pieces" for the Combat Lab block dictionary are read off them, so the generator's output ends up
recognisable but further from the source. Models and renders stay in the PRIVATE repo (`reference_art/` is
in tools/publish_public.py's PRIVATE_PATHS). Kept apart from the token generator (INTEGRATION__tokens.py).

Commands (run with `python -I tools/lowpoly_ref.py ...`):
  check  [MODEL.json ...]   triangle budget, required assemblies, parts on the ground, mtf cross-check
  render [MODEL.json ...]   five-view sheet(s) into reference_art/sheets/ (add --iso for a 3/4 panel)
  compare [MODEL.json ...]  the TRO drawing beside the model's 3/4 panel, into reference_art/sheets/compare_<unit>.png
  mtf    "Commando COM-2D"  print the unit file's weapons / jump jets per location (from data/meks.zip)

COORDINATES. Figure height is about 10 units, feet on y = 0. +y up, +z the way the 'Mech faces, +x the
'Mech's LEFT. A part given with "mirror": true is authored on the +x (left) side and copied to -x (right).

PRIMITIVES ("kind"). Every part is ONE convex solid; "id", "assembly" and optional "role" are required/kept.
  box    "c": centre, "s": [sx, sy, sz], optional "taper": [tx, tz] (top face scaled), "rot": [rx, ry, rz] degrees
  wedge  "c", "s", "high": "-z"|"+z"|"-x"|"+x" (the tall wall's side; the top slopes down to the other side)
  bar    "a", "b": the two end centres; "w0", "w1": [across1, across2] at each end (w1 may be [0,0] = a point).
         The cross-section axes: for a mostly-vertical bar they are [x, z]; for a mostly-z bar [x, y]; for a
         mostly-x bar [z, y]. A bar is a limb segment: it tapers, and it can point anywhere (the arms' A-stance).
  tube   as bar with "n": 6 or 8 sides; "w0"/"w1" are the diameters across the corners; "roll" turns the sides.
  hull   "pts": 4 or more [x, y, z] points; the part is their convex hull (sloped armor plates, wedge-and-bevel shapes).
  dome   "c", "r": [rx, ry, rz], "n" sides (default 8), "rings" (default 4), "half": "top" for a flat-based cap
         (a canopy, a helmet), otherwise a full ellipsoid (a round chest). A hull of latitude rings.
Optional "tone" (0-1) overrides the flat grey so neighbouring pieces read apart.
Roles: "weapon:<LOC>:<mtf name>", "jumpjet:<LOC>", "canopy", "antenna", "armor" (anything else: no role).
Triangle count: a box 12, a wedge 8, a hexagonal tube 20, an octagonal tube 28, an 8-sided 4-ring dome 40-48
(faces fan-triangulated; the limit is TRIANGLE_LIMIT).
"""
import json
import math
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = os.path.join(ROOT, "reference_art")
MODELS = os.path.join(REF, "models")
SHEETS = os.path.join(REF, "sheets")
MEKS_ZIP = os.path.join(ROOT, "data", "meks.zip")
# Daniel, 2026-11-16: "perfectly happy to cheat on that '95 look" (retro look, modern tools; animation later): 800, up from 400
TRIANGLE_LIMIT = 800

# the assemblies a model must show as separate pieces (Daniel's prompt: pelvis, legs, torso, arms, head/canopy)
REQUIRED_ASSEMBLIES = ["pelvis", "torso", "head", "leg_L", "leg_R", "arm_L", "arm_R"]

# flat tones (0 = black, 1 = white) by role, then by assembly name; every plane stays light so the black seams read
TONE_ROLE = {"weapon": 0.50, "canopy": 0.32, "jumpjet": 0.42, "antenna": 0.40}
TONE_ASSEMBLY = {"pelvis": 0.74, "torso": 0.90, "shoulder": 0.80, "head": 0.92, "leg": 0.70, "arm": 0.78}

LOC_NAMES = {"Head": "HD", "Center Torso": "CT", "Left Torso": "LT", "Right Torso": "RT", "Left Arm": "LA",
             "Right Arm": "RA", "Left Leg": "LL", "Right Leg": "RL"}


# ---------------------------------------------------------------- small vector helpers
def _sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def _add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def _mul(a, k): return (a[0] * k, a[1] * k, a[2] * k)
def _dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def _cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def _len(a): return math.sqrt(_dot(a, a))
def _unit(a):
    n = _len(a)
    return (a[0] / n, a[1] / n, a[2] / n) if n else (0.0, 0.0, 0.0)


def _rot(p, rot, about):
    """Rotate point p by rot = [rx, ry, rz] degrees (x, then y, then z) about the point `about`."""
    x, y, z = _sub(p, about)
    rx, ry, rz = (math.radians(v) for v in rot)
    y, z = y * math.cos(rx) - z * math.sin(rx), y * math.sin(rx) + z * math.cos(rx)
    x, z = x * math.cos(ry) + z * math.sin(ry), -x * math.sin(ry) + z * math.cos(ry)
    x, y = x * math.cos(rz) - y * math.sin(rz), x * math.sin(rz) + y * math.cos(rz)
    return _add((x, y, z), about)


# ---------------------------------------------------------------- primitives: each returns (vertices, faces)
def _frustum(a, b, sec0, sec1, n):
    """Faces joining two cross-sections (lists of n points each, same order): two caps and n side quads.
    A section of None is a point (the bar narrows to a tip): its side faces become triangles."""
    faces = []
    verts = []
    if sec0 is not None:
        i0 = list(range(len(verts), len(verts) + n)); verts += sec0
    else:
        i0 = len(verts); verts.append(a)
    if sec1 is not None:
        i1 = list(range(len(verts), len(verts) + n)); verts += sec1
    else:
        i1 = len(verts); verts.append(b)
    if sec0 is not None:
        faces.append(list(reversed(i0)))
    if sec1 is not None:
        faces.append(list(i1))
    for k in range(n):
        k2 = (k + 1) % n
        if sec0 is None:
            faces.append([i0, i1[k], i1[k2]])
        elif sec1 is None:
            faces.append([i0[k], i0[k2], i1])
        else:
            faces.append([i0[k], i0[k2], i1[k2], i1[k]])
    return verts, faces


def _section(center, u, v, width, n, roll):
    """The n corner points of a cross-section about `center`. n = 4 is a rectangle width[0] x width[1];
    other n are regular polygons (width = the diameter across the corners)."""
    if width is None or (width[0] == 0 and width[1] == 0):
        return None
    pts = []
    for k in range(n):
        if n == 4:
            t = math.radians(roll) + math.pi / 4 + k * math.pi / 2
            su, sv = width[0] / 2 * math.sqrt(2), width[1] / 2 * math.sqrt(2)
        else:
            t = math.radians(roll) + k * 2 * math.pi / n
            su, sv = width[0] / 2, width[1] / 2
        pts.append(_add(center, _add(_mul(u, math.cos(t) * su), _mul(v, math.sin(t) * sv))))
    return pts


def _axes(axis):
    """The two cross-section directions for a bar along `axis` (see the module docstring)."""
    ax = _unit(axis)
    ref = (0.0, 0.0, 1.0) if abs(ax[1]) > 0.7 else (0.0, 1.0, 0.0)
    u = _unit(_cross(ax, ref))
    v = _unit(_cross(ax, u))
    return u, v


def make_bar(part, n=4):
    a, b = tuple(part["a"]), tuple(part["b"])
    u, v = _axes(_sub(b, a))
    w0, w1 = part["w0"], part.get("w1", part["w0"])
    roll = part.get("roll", 0.0)
    return _frustum(a, b, _section(a, u, v, w0, n, roll), _section(b, u, v, w1, n, roll), n)


def make_box(part):
    c, s = part["c"], part["s"]
    tx, tz = part.get("taper", [1.0, 1.0])
    a = (c[0], c[1] - s[1] / 2, c[2])
    b = (c[0], c[1] + s[1] / 2, c[2])
    verts, faces = _frustum(a, b, _section(a, (1, 0, 0), (0, 0, 1), [s[0], s[2]], 4, 0),
                            _section(b, (1, 0, 0), (0, 0, 1), [s[0] * tx, s[2] * tz], 4, 0), 4)
    if "rot" in part:
        verts = [_rot(p, part["rot"], tuple(c)) for p in verts]
    return verts, faces


def make_wedge(part):
    c, s = part["c"], part["s"]
    hx, hy, hz = s[0] / 2, s[1] / 2, s[2] / 2
    high = part.get("high", "-z")
    if high in ("-z", "+z"):
        zt = -hz if high == "-z" else hz                       # the tall wall's z
        verts = [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (-hx, -hy, hz), (-hx, hy, zt), (hx, hy, zt)]
        far = [0, 1] if high == "-z" else [3, 2]               # the base edge under the tall wall
        near = [3, 2] if high == "-z" else [0, 1]
        faces = [[0, 1, 2, 3], [far[0], far[1], 5, 4], [4, 5, near[1], near[0]], [far[0], near[0], 4], [far[1], near[1], 5]]
    else:
        xt = -hx if high == "-x" else hx
        verts = [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (-hx, -hy, hz), (xt, hy, -hz), (xt, hy, hz)]
        far = [0, 3] if high == "-x" else [1, 2]
        near = [1, 2] if high == "-x" else [0, 3]
        faces = [[0, 1, 2, 3], [far[0], far[1], 5, 4], [4, 5, near[1], near[0]], [far[0], near[0], 4], [far[1], near[1], 5]]
    verts = [_add(p, tuple(c)) for p in verts]
    if "rot" in part:
        verts = [_rot(p, part["rot"], tuple(c)) for p in verts]
    return verts, faces


def _hull(points):
    """Convex hull of a point set: (vertices, faces), each face one polygon ordered by angle. Qhull (scipy) finds the face planes;
    the points lying on a plane make its polygon, as before. (2026-11-18: the first version tested every triple of points against
    all the others - fourth power of the point count; a 200-point dome took 18 s and the assembly check 4.5 minutes. The brute
    force stays as the fallback for flat or tiny point sets that Qhull refuses.)"""
    pts = []
    for p in points:
        if all(_len(_sub(p, q)) > 1e-9 for q in pts):
            pts.append(tuple(p))
    planes = None
    if len(pts) >= 5:
        try:
            import numpy as np
            from scipy.spatial import ConvexHull
            arr = np.asarray(pts, dtype=float)
            h = ConvexHull(arr)
            planes = {}
            for eq in h.equations:                       # outward normal (a, b, c) and offset: n.x + e = 0
                nrm = eq[:3] / np.linalg.norm(eq[:3])
                d = -eq[3] / np.linalg.norm(eq[:3])
                members = tuple(int(m) for m in np.where(np.abs(arr @ nrm - d) <= 1e-7)[0])
                if len(members) >= 3 and members not in planes:
                    planes[members] = (-nrm[0], -nrm[1], -nrm[2])   # the brute force kept the inward normal: same ordering
        except Exception:                                # noqa: BLE001 - degenerate set: the brute force below
            planes = None
    if planes is None:
        planes = {}
        n = len(pts)
        for i in range(n):
            for j in range(i + 1, n):
                for k in range(j + 1, n):
                    nrm = _cross(_sub(pts[j], pts[i]), _sub(pts[k], pts[i]))
                    if _len(nrm) < 1e-9:
                        continue
                    nrm = _unit(nrm)
                    d = _dot(nrm, pts[i])
                    side = [_dot(nrm, p) - d for p in pts]
                    if all(x <= 1e-7 for x in side):
                        pass
                    elif all(x >= -1e-7 for x in side):
                        nrm = _mul(nrm, -1)
                    else:
                        continue
                    members = tuple(m for m, x in enumerate(side) if abs(x) <= 1e-7)
                    planes[members] = nrm
    faces, used = [], set()
    for members, nrm in planes.items():
        c = (sum(pts[m][0] for m in members) / len(members), sum(pts[m][1] for m in members) / len(members),
             sum(pts[m][2] for m in members) / len(members))
        u = _unit(_sub(pts[members[0]], c))
        v = _cross(nrm, u)
        order = sorted(members, key=lambda m: math.atan2(_dot(_sub(pts[m], c), v), _dot(_sub(pts[m], c), u)))
        faces.append(order)
        used.update(order)
    remap = {old: new for new, old in enumerate(sorted(used))}
    return [pts[o] for o in sorted(used)], [[remap[m] for m in f] for f in faces]

def make_hull(part):
    verts, faces = _hull(part["pts"])
    if "rot" in part:
        cen = tuple(sum(p[k] for p in verts) / len(verts) for k in range(3))
        verts = [_rot(p, part["rot"], cen) for p in verts]
    return verts, faces


def make_dome(part):
    cx, cy, cz = part["c"]
    rx, ry, rz = part["r"]
    n, rings, roll = int(part.get("n", 8)), int(part.get("rings", 4)), math.radians(part.get("roll", 0.0))
    top = part.get("half") == "top"
    lats = [90.0 * k / rings for k in range(rings)] if top else [-90.0 + 180.0 * k / rings for k in range(1, rings)]
    pts = [(cx, cy + ry, cz)] + ([] if top else [(cx, cy - ry, cz)])
    for lat in lats:
        a = math.radians(lat)
        for k in range(n):
            t = roll + k * 2 * math.pi / n
            pts.append((cx + rx * math.cos(a) * math.cos(t), cy + ry * math.sin(a), cz + rz * math.cos(a) * math.sin(t)))
    verts, faces = _hull(pts)
    if "rot" in part:
        verts = [_rot(p, part["rot"], (cx, cy, cz)) for p in verts]
    return verts, faces


def build_part(part):
    kind = part["kind"]
    if kind == "box":
        return make_box(part)
    if kind == "wedge":
        return make_wedge(part)
    if kind == "hull":
        return make_hull(part)
    if kind == "dome":
        return make_dome(part)
    if kind == "bar":
        return make_bar(part, 4)
    if kind == "tube":
        return make_bar(part, int(part.get("n", 6)))
    raise ValueError("unknown kind %r in part %r" % (kind, part.get("id")))


def tri_count(faces):
    return sum(len(f) - 2 for f in faces)


def _flip_role(role):
    """'weapon:LA:Medium Laser' authored on the left becomes the right-hand copy's 'weapon:RA:Medium Laser'."""
    bits = role.split(":")
    if len(bits) >= 2 and bits[1] in ("LA", "LT", "LL"):
        bits[1] = "R" + bits[1][1]
    return ":".join(bits)


# ---------------------------------------------------------------- "anti-existence": every weapon's line of fire (Daniel, 2026-11-18)
# "The 2 medium lasers in the center torso. The torso clips their attack path. Solution in this case is to cut out a tube along
# their firing path. If all weapons include a region of 'Anti existence' in front of them as part of their blocks, this should
# never be a problem again." A FIRING CORRIDOR is a square channel from just past the muzzle along the firing direction; every
# other solid it passes through is cut (split into convex pieces round the channel), and the check proves every corridor clear.
FIRE_LENGTH = 4.0          # how far a corridor reaches (models' units; past the model's own parts)
FIRE_START = 0.04          # a corridor starts this far past the muzzle (the bore's dark disc stays)


def corridor(start, direction, r, length=FIRE_LENGTH):
    d = _unit(direction)
    up = (0.0, 1.0, 0.0) if abs(d[1]) < 0.9 else (1.0, 0.0, 0.0)
    u = _unit(_cross(d, up))
    v = _cross(d, u)
    return {"s": tuple(start), "d": d, "u": u, "v": v, "r": r, "len": length}


def part_corridors(part):
    """A weapon part's corridors: its "fire" field ({"from", "dir", "r", optional "len"}), else, for a tube or bar with a weapon
    role, from its far end along its axis, as wide as its muzzle. A mirrored part's corridor is mirrored too."""
    out = []
    if "fire" in part:
        f = part["fire"]
        out.append(corridor(f["from"], f["dir"], f["r"], f.get("len", FIRE_LENGTH)))
    elif part.get("role", "").startswith("weapon:") and part["kind"] in ("tube", "bar"):
        a, b = tuple(part["a"]), tuple(part["b"])
        d = _unit(_sub(b, a))
        r = max(part.get("w1", part["w0"])) / 2
        out.append(corridor(_add(b, _mul(d, FIRE_START)), d, r))
    if part.get("mirror"):
        out += [dict(c, s=(-c["s"][0], c["s"][1], c["s"][2]), d=(-c["d"][0], c["d"][1], c["d"][2]),
                     u=(-c["u"][0], c["u"][1], c["u"][2]), v=(-c["v"][0], c["v"][1], c["v"][2])) for c in list(out)]
    return out


def corridor_solid(c):
    """The corridor as a convex solid (for the clear-line-of-fire check)."""
    pts = []
    for t in (0.0, c["len"]):
        for i in (-1, 1):
            for j in (-1, 1):
                pts.append(_add(c["s"], _add(_mul(c["d"], t), _add(_mul(c["u"], i * c["r"]), _mul(c["v"], j * c["r"])))))
    verts, faces = _hull(pts)
    return {"verts": verts, "faces": faces}


def _clip(verts, faces, n, k):
    """The convex solid (verts, faces) cut to the half-space n.x <= k: (verts, faces) or None if nothing is left."""
    side = [_dot(n, p) - k for p in verts]
    keep = [p for p, sd in zip(verts, side) if sd <= 1e-9]
    if len(keep) == len(verts):
        return verts, faces
    if not keep:
        return None
    edges = set()
    for f in faces:
        for i in range(len(f)):
            a, b = f[i], f[(i + 1) % len(f)]
            edges.add((min(a, b), max(a, b)))
    for a, b in edges:
        if (side[a] < -1e-9 and side[b] > 1e-9) or (side[a] > 1e-9 and side[b] < -1e-9):
            t = side[a] / (side[a] - side[b])
            keep.append(_add(verts[a], _mul(_sub(verts[b], verts[a]), t)))
    if len(keep) < 4:
        return None
    try:
        v2, f2 = _hull(keep)
    except Exception:                                    # noqa: BLE001 - a flat sliver: nothing worth keeping
        return None
    if len(f2) < 4:
        return None
    return v2, f2


def subtract(solid, hole):
    """`solid` minus the convex `hole` (a HOLE, Tinkercad's word; a boolean difference elsewhere - Daniel, 2026-11-18: "A shape
    you add to another shape to remove from it"): the standard convex decomposition, one piece per face of the hole: piece i is
    the part of the solid outside the hole's face i but inside its faces 0..i-1. Every piece is convex, so the rest of the
    pipeline (renderer, checks) is unchanged."""
    import numpy as np
    hv = hole["verts"]
    cen = tuple(sum(p[k] for p in hv) / len(hv) for k in range(3))
    planes = []
    for f in hole["faces"]:
        n = _face_normal(hv, f, cen)                     # outward
        planes.append((n, _dot(n, hv[f[0]])))
    pieces = []
    inside = []                                          # half-spaces 'inside face j' for the faces already used
    for n, k in planes:
        cur = (solid["verts"], solid["faces"])
        for nn, kk in [(_mul(n, -1), -k)] + inside:      # outside face i (n.x >= k), inside the earlier faces
            cur = _clip(cur[0], cur[1], nn, kk)
            if cur is None:
                break
        if cur is not None:
            pieces.append(cur)
        inside.append((n, k))
    return pieces


def cut_channel(solid, c):
    """`solid` with the corridor's hole subtracted (a weapon's line of fire)."""
    return subtract(solid, corridor_solid(c))


def apply_fire_cuts(solids, corridors, owner=None):
    """Cut every corridor's channel through every solid it meets (not the weapon's own solids, `owner` index -> weapon key)."""
    out = list(solids)
    for ci, c in enumerate(corridors):
        cs = corridor_solid(c)
        ca = _solid_arrays(cs)
        nxt = []
        for s in out:
            if c.get("own") is not None and s.get("weapon_key") == c["own"]:
                nxt.append(s)
                continue
            if separated(_solid_arrays(s), ca, -1e-6):
                nxt.append(s)
                continue
            for k, (vs, fs) in enumerate(cut_channel(s, c)):
                cen = tuple(sum(p[i] for p in vs) / len(vs) for i in range(3))
                nxt.append(dict(s, id="%s~cut%d.%d" % (s["id"], ci, k), verts=vs, faces=fs, centroid=cen, tris=tri_count(fs)))
        out = nxt
    return out


def blocked_lines_of_fire(solids, corridors):
    """(corridor index, blocking solid id) pairs: a solid other than the weapon's own still inside a corridor."""
    bad = []
    for ci, c in enumerate(corridors):
        ca = _solid_arrays(corridor_solid(dict(c, r=c["r"] * 0.9)))
        for s in solids:
            if c.get("own") is not None and s.get("weapon_key") == c["own"]:
                continue
            if not separated(_solid_arrays(s), ca, -0.005):
                bad.append((ci, s["id"]))
    return bad


def expand_parts(model):
    """The model's parts as solids: [{id, assembly, role, verts, faces, centroid}], mirrors written out."""
    solids = []
    for part in model["parts"]:
        verts, faces = build_part(part)
        variants = [(part["id"] + ("_L" if part.get("mirror") else ""), verts, False)]
        if part.get("mirror"):
            variants.append((part["id"] + "_R", [(-x, y, z) for x, y, z in verts], True))
        for pid, vs, flipped in variants:
            asm, role = part["assembly"], part.get("role", "")
            if flipped:                                        # the copy on the right-hand side
                asm = asm[:-2] + "_R" if asm.endswith("_L") else asm
                role = _flip_role(role)
            cen = (sum(p[0] for p in vs) / len(vs), sum(p[1] for p in vs) / len(vs), sum(p[2] for p in vs) / len(vs))
            solids.append({"id": pid, "assembly": asm, "role": role, "verts": vs, "faces": faces, "centroid": cen,
                           "tris": tri_count(faces), "tone": part.get("tone"), "weapon_key": part["id"] if part_corridors(part) else None,
                           "hole": bool(part.get("hole"))})
    # HOLES: a part marked "hole": true is never drawn; it is subtracted from every other solid it meets
    holes = [s_ for s_ in solids if s_.get("hole")]
    if holes:
        solids = [s_ for s_ in solids if not s_.get("hole")]
        for h in holes:
            ha = _solid_arrays(h)
            nxt = []
            for s_ in solids:
                if separated(_solid_arrays(s_), ha, -1e-6):
                    nxt.append(s_)
                    continue
                for k, (vs, fs) in enumerate(subtract(s_, h)):
                    cen = tuple(sum(p[i] for p in vs) / len(vs) for i in range(3))
                    nxt.append(dict(s_, id="%s~%s.%d" % (s_["id"], h["id"], k), verts=vs, faces=fs, centroid=cen, tris=tri_count(fs)))
            solids = nxt
    # every weapon carries a hole along its line of fire (its "anti-existence" region): cut through whatever stands in it
    corridors = []
    for part in model["parts"]:
        for c in part_corridors(part):
            corridors.append(dict(c, own=part["id"]))
    if corridors:
        solids = apply_fire_cuts(solids, corridors)
    return solids


# ---------------------------------------------------------------- the unit file (data/meks.zip)
def read_mtf(name):
    """name = 'Commando COM-2D'. Returns {mass, walk, jump, weapons: [(LOC, name)], jump_jets: {LOC: count}}."""
    with zipfile.ZipFile(MEKS_ZIP) as z:
        path = next((p for p in z.namelist() if p.endswith("/" + name + ".mtf")), None)
        if path is None:
            raise FileNotFoundError(name)
        lines = z.read(path).decode("utf-8", "replace").splitlines()
    out = {"file": path, "weapons": [], "jump_jets": {}, "mass": None, "walk": None, "jump": 0, "crits": {}}
    loc = None
    in_weapons = False
    for line in lines:
        s = line.strip()
        low = s.lower()                                         # some files write "Mass:30", others "mass:25"
        if low.startswith("mass:"):
            out["mass"] = int(s.split(":")[1])
        elif low.startswith("walk mp:"):
            out["walk"] = int(s.split(":")[1])
        elif low.startswith("jump mp:"):
            out["jump"] = int(s.split(":")[1])
        elif low.startswith("weapons:"):
            in_weapons = True
        elif in_weapons and "," in s and s.rsplit(",", 1)[1].strip() in LOC_NAMES:
            nm, lc = s.rsplit(",", 1)
            out["weapons"].append((LOC_NAMES[lc.strip()], nm.strip()))
        elif s.endswith(":") and s[:-1] in LOC_NAMES:
            in_weapons = False
            loc = LOC_NAMES[s[:-1]]
        elif loc and s == "Jump Jet":
            out["jump_jets"][loc] = out["jump_jets"].get(loc, 0) + 1
            out["crits"].setdefault(loc, []).append(s)
        elif loc and s and not s.endswith(":") and ":" not in s:
            # every critical slot by location (2026-11-18: the arm's actuators decide how an arm is built - the record sheet's
            # Shoulder / Upper Arm / Lower Arm / Hand Actuator lines)
            out["crits"].setdefault(loc, []).append(s)
        elif not s:
            if in_weapons and out["weapons"]:
                in_weapons = False
    return out


# ---------------------------------------------------------------- the no-floating-bits check (Daniel, 2026-11-18)
TOUCH_GAP = 0.02          # two solids touch when no direction separates them by more than this (models' units)


def _solid_arrays(s):
    import numpy as np
    v = np.asarray(s["verts"], dtype=float)
    normals, edges = [], set()
    for f in s["faces"]:
        p = v[f]
        n = np.zeros(3)
        for i in range(len(f)):                                      # Newell's normal
            q, r = p[i], p[(i + 1) % len(f)]
            n += np.array([(q[1] - r[1]) * (q[2] + r[2]), (q[2] - r[2]) * (q[0] + r[0]), (q[0] - r[0]) * (q[1] + r[1])])
            e = r - q
            ln = np.linalg.norm(e)
            if ln > 1e-9:
                e = e / ln
                if e[0] < 0 or (e[0] == 0 and (e[1] < 0 or (e[1] == 0 and e[2] < 0))):
                    e = -e
                edges.add(tuple(np.round(e, 4)))
        ln = np.linalg.norm(n)
        if ln > 1e-9:
            normals.append(n / ln)
    return v, np.array(normals) if normals else np.zeros((0, 3)), np.array(sorted(edges)) if edges else np.zeros((0, 3))


def separated(a, b, gap=TOUCH_GAP):
    """True when two convex solids are further apart than `gap` (separating-axis test: both solids' face normals and the cross
    products of their edge directions; exact for convex solids)."""
    import numpy as np
    va, na, ea = a
    vb, nb, eb = b
    axes = [na, nb]
    if len(ea) and len(eb):
        c = np.cross(ea[:, None, :], eb[None, :, :]).reshape(-1, 3)
        ln = np.linalg.norm(c, axis=1)
        axes.append(c[ln > 1e-6] / ln[ln > 1e-6, None])
    ax = np.concatenate(axes)
    pa, pb = va @ ax.T, vb @ ax.T
    gap_ab = np.maximum(pb.min(0) - pa.max(0), pa.min(0) - pb.max(0))
    return bool((gap_ab > gap).any())


def floating_parts(solids, gap=TOUCH_GAP, group=None):
    """The ids of solids not joined to the main body: every solid must touch (within `gap`) a chain of solids reaching the largest
    connected group. `group(i)` may name solids that belong together whatever (one block's own pieces). Daniel, 2026-11-18: "There
    needs to be a no floaty bits check when you render" - the box-overlap test let a jump-jet vent float beside the body."""
    import numpy as np
    n = len(solids)
    arrs = [_solid_arrays(s) for s in solids]
    lo = np.array([a[0].min(0) for a in arrs]) - gap
    hi = np.array([a[0].max(0) for a in arrs]) + gap
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    if group is not None:
        first = {}
        for i in range(n):
            g = group(i)
            if g is not None:
                if g in first:
                    parent[find(i)] = find(first[g])
                else:
                    first[g] = i
    for i in range(n):
        near = np.where(np.all(lo[i] <= hi, axis=1) & np.all(lo <= hi[i], axis=1))[0]
        for j in near:
            if j <= i or find(i) == find(j):
                continue
            if not separated(arrs[i], arrs[j], gap):
                parent[find(i)] = find(int(j))
    comps = {}
    for i in range(n):
        comps.setdefault(find(i), []).append(i)
    main = max(comps.values(), key=len)
    return [solids[i]["id"] for c in comps.values() if c is not main for i in c]


# ---------------------------------------------------------------- checks
def check_model(model):
    """Returns (errors, notes). Errors fail the check."""
    errors, notes = [], []
    solids = expand_parts(model)
    tris = sum(s["tris"] for s in solids)
    notes.append("%d parts, %d triangles" % (len(solids), tris))
    if tris >= TRIANGLE_LIMIT and model.get("detail") != "hd":      # an HD model (2026-11-18, Daniel: "Don't worry about polygon
                                                                       # count. This will be the HD version that gets simplified later")
        errors.append("triangle budget: %d (limit under %d)" % (tris, TRIANGLE_LIMIT))
    asm = {s["assembly"] for s in solids}
    for need in REQUIRED_ASSEMBLIES:
        if need not in asm:
            errors.append("no part in assembly %r" % need)
    corridors = [dict(c, own=p["id"]) for p in model["parts"] for c in part_corridors(p)]
    for ci, sid in blocked_lines_of_fire(solids, corridors):
        errors.append("a weapon's line of fire is blocked by %s" % sid)
    loose = floating_parts(solids)
    if loose:
        errors.append("floating parts (not touching the body): %s" % ", ".join(loose[:12]) + (" ..." if len(loose) > 12 else ""))
    ids = [s["id"] for s in solids]
    if len(ids) != len(set(ids)):
        errors.append("duplicate part ids")
    ys = [p[1] for s in solids for p in s["verts"]]
    if min(ys) < -0.001 or min(ys) > 0.05:
        errors.append("lowest point is y=%.3f (feet should rest on y=0)" % min(ys))
    notes.append("height %.2f" % max(ys))
    # the unit file: every weapon in the right location, every jump jet location, nothing weapon-like that is not in it
    mtf = read_mtf(model["unit"] + " " + model["model"])
    want = sorted(mtf["weapons"])
    have = []
    for s in solids:
        if s["role"].startswith("weapon:"):
            _, loc, nm = s["role"].split(":", 2)
            have.append((loc, nm))
    if sorted(have) != want:
        missing = list(want)
        for h in have:
            if h in missing:
                missing.remove(h)
        extra = list(have)
        for w in want:
            if w in extra:
                extra.remove(w)
        errors.append("weapons differ from the unit file: missing %s, extra %s" % (missing, extra))
    jj_have = {}
    for s in solids:
        if s["role"].startswith("jumpjet:"):
            loc = s["role"].split(":")[1]
            jj_have[loc] = jj_have.get(loc, 0) + 1
    if set(jj_have) != set(mtf["jump_jets"]):
        errors.append("jump-jet locations %s differ from the unit file %s" % (sorted(jj_have), sorted(mtf["jump_jets"])))
    if mtf["mass"] != model.get("mass"):
        errors.append("mass %s differs from the unit file's %s" % (model.get("mass"), mtf["mass"]))
    return errors, notes


# ---------------------------------------------------------------- rendering (PIL, painter's algorithm)
VIEWS = ["front", "rear", "left", "right", "top"]
_VIEW_MAP = {                                  # (x, y, z) -> (screen x, screen y up, depth: larger = nearer the camera)
    "front": lambda p: (p[0], p[1], p[2]),
    "rear": lambda p: (-p[0], p[1], -p[2]),
    "left": lambda p: (-p[2], p[1], p[0]),     # camera on the 'Mech's left (+x): it faces screen-left
    "right": lambda p: (p[2], p[1], -p[0]),
    "top": lambda p: (-p[0], p[2], p[1]),      # forward is screen-up
    "iso": None,                               # set below
}


def _iso(p):
    """A 3/4 front-left view (an aid for review, not one of the five): yaw 35 degrees, pitch 20 degrees."""
    yaw, pitch = math.radians(-35), math.radians(20)
    x = p[0] * math.cos(yaw) + p[2] * math.sin(yaw)
    z = -p[0] * math.sin(yaw) + p[2] * math.cos(yaw)
    y = p[1] * math.cos(pitch) - z * math.sin(pitch)
    d = p[1] * math.sin(pitch) + z * math.cos(pitch)
    return (x, y, d)


_VIEW_MAP["iso"] = _iso


def _tone(s):
    if s.get("tone") is not None:
        return s["tone"]
    role = s["role"].split(":")[0]
    if role in TONE_ROLE:
        return TONE_ROLE[role]
    return TONE_ASSEMBLY.get(s["assembly"].split("_")[0], 0.8)


def _face_normal(verts, face, centroid):
    n = (0.0, 0.0, 0.0)
    for i in range(len(face)):                                  # Newell's method
        p, q = verts[face[i]], verts[face[(i + 1) % len(face)]]
        n = (n[0] + (p[1] - q[1]) * (p[2] + q[2]), n[1] + (p[2] - q[2]) * (p[0] + q[0]), n[2] + (p[0] - q[0]) * (p[1] + q[1]))
    n = _unit(n)
    fc = (sum(verts[i][0] for i in face) / len(face), sum(verts[i][1] for i in face) / len(face),
          sum(verts[i][2] for i in face) / len(face))
    return n if _dot(n, _sub(fc, centroid)) >= 0 else _mul(n, -1)


def render_view(solids, view, scale, size, origin, ss=2):
    """One panel: a PIL image `size` px (already x ss). origin = world (sx, sy) shown at the panel's bottom-centre."""
    from PIL import Image, ImageDraw
    w, h = size[0] * ss, size[1] * ss
    img = Image.new("RGB", (w, h), "white")
    dr = ImageDraw.Draw(img)
    fmap = _VIEW_MAP[view]
    light = _unit((-0.45, 0.75, 0.5))                           # key light in camera space: upper left, toward the viewer
    polys = []
    for s in solids:
        tone = _tone(s)
        for f in s["faces"]:
            n_world = _face_normal(s["verts"], f, s["centroid"])
            # the normal's camera-space direction
            n_cam = _sub(fmap(n_world), fmap((0, 0, 0)))
            pts = [fmap(s["verts"][i]) for i in f]
            depth = sum(p[2] for p in pts) / len(pts)
            if n_cam[2] <= -0.02:                                # a back face: hidden (convex parts)
                continue
            shade = tone * (0.62 + 0.38 * max(0.0, _dot(_unit(n_cam), light)))
            polys.append((depth, [((origin[0] + p[0] * scale) * ss, h - (origin[1] + p[1] * scale) * ss) for p in pts], shade))
    polys.sort(key=lambda t: t[0])
    for _, pts, shade in polys:
        g = int(max(0, min(255, round(shade * 255))))
        dr.polygon(pts, fill=(g, g, g), outline=(0, 0, 0))
        dr.line(pts + [pts[0]], fill=(0, 0, 0), width=ss + 1)
    return img


def render_sheet(model, path, iso=False):
    from PIL import Image, ImageDraw, ImageFont
    solids = expand_parts(model)
    pts = [p for s in solids for p in s["verts"]]
    ex = max(p[0] for p in pts) - min(p[0] for p in pts)
    ey = max(p[1] for p in pts)
    ez = max(p[2] for p in pts) - min(p[2] for p in pts)
    scale = 56.0                                               # px per unit: one scale for every view
    pad = 0.8
    cw = int(max(ex, ez) * scale + pad * scale * 2)
    ch = int(max(ey, ez) * scale + pad * scale * 2)
    ss = 2
    views = VIEWS + (["iso"] if iso else [])
    sheet = Image.new("RGB", (cw * len(views), ch + 70), "white")
    dr = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default(size=22)
        small = ImageFont.load_default(size=15)
    except TypeError:
        font = small = ImageFont.load_default()
    tris = sum(s["tris"] for s in solids)
    loose = floating_parts(solids)                  # every render runs the no-floating-bits check and says so on the sheet
    dr.text((14, 10), "%s %s   |   %d parts, %d triangles   |   same scale in every view   |   %s" %
            (model["unit"].upper(), model["model"], len(solids), tris,
             ("FLOATING PARTS: " + ", ".join(loose[:6])) if loose else "no floating parts"), fill="red" if loose else "black", font=font)
    if loose:
        print("WARNING %s %s: floating parts %s" % (model["unit"], model["model"], loose))
    zc = (max(p[2] for p in pts) + min(p[2] for p in pts)) / 2
    xc = (max(p[0] for p in pts) + min(p[0] for p in pts)) / 2
    for i, view in enumerate(views):
        # origin: where world (0, 0) of the screen mapping lands in the panel
        if view in ("front", "rear"):
            ox = cw / 2 - (xc if view == "front" else -xc) * scale
            oy = pad * scale
        elif view in ("left", "right"):
            ox = cw / 2 - (-zc if view == "left" else zc) * scale
            oy = pad * scale
        elif view == "top":
            ox = cw / 2 - (-xc) * scale
            oy = ch / 2 - zc * scale
        else:
            ox, oy = cw / 2, pad * scale + 0.4 * scale
        panel = render_view(solids, view, scale, (cw, ch), (ox, oy), ss).resize((cw, ch), Image.LANCZOS)
        sheet.paste(panel, (i * cw, 70))
        dr.text((i * cw + 12, 46), view.upper(), fill="black", font=small)
        dr.line([(i * cw, 70), (i * cw, ch + 70)], fill=(200, 200, 200), width=1)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sheet.save(path)
    return tris


def compare_picture(model, path):
    """The TRO drawing (left) beside the model's 3/4 panel (right): the quickest likeness check for a person or a model."""
    from PIL import Image
    unit = model["unit"] + " " + model["model"]
    units = json.load(open(os.path.join(REF, "units.json")))["units"]
    entry = next(u for u in units if u["unit"] == unit)
    drawing = Image.open(os.path.join(REF, entry["original"])).convert("RGB")
    tmp = path + ".tmp.png"
    render_sheet(model, tmp, iso=True)
    sheet = Image.open(tmp)
    os.remove(tmp)
    w = sheet.width // 6
    panel = sheet.crop((5 * w, 70, 6 * w, sheet.height))
    height = 700
    drawing = drawing.resize((int(drawing.width * height / drawing.height), height), Image.LANCZOS)
    panel = panel.resize((int(panel.width * height / panel.height), height), Image.LANCZOS)
    out = Image.new("RGB", (drawing.width + panel.width + 30, height + 20), "white")
    out.paste(drawing, (10, 10))
    out.paste(panel, (drawing.width + 20, 10))
    out.save(path)


# ---------------------------------------------------------------- command line
def _load(path):
    with open(path) as f:
        return json.load(f)


def _models(args):
    paths = [a for a in args if a.endswith(".json")] or sorted(
        os.path.join(MODELS, f) for f in os.listdir(MODELS) if f.endswith(".json"))
    return paths


def main(argv):
    if len(argv) < 2 or argv[1] not in ("check", "render", "compare", "mtf"):
        print(__doc__)
        return 2
    cmd, args = argv[1], argv[2:]
    if cmd == "mtf":
        m = read_mtf(args[0])
        print(json.dumps(m, indent=1))
        return 0
    bad = 0
    for path in _models(args):
        model = _load(path)
        if cmd == "check":
            errors, notes = check_model(model)
            print("%-4s %-28s %s" % ("FAIL" if errors else "ok", os.path.basename(path), "; ".join(notes)))
            for e in errors:
                print("       -", e)
            bad += bool(errors)
        elif cmd == "compare":
            out = os.path.join(SHEETS, "compare_" + os.path.basename(path)[:-5] + ".png")
            compare_picture(model, out)
            print("wrote", os.path.relpath(out, ROOT))
        else:
            out = os.path.join(SHEETS, os.path.basename(path)[:-5] + ".png")
            tris = render_sheet(model, out, iso="--iso" in args)
            print("wrote %s (%d triangles)" % (os.path.relpath(out, ROOT), tris))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
