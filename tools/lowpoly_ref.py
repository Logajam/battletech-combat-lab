#!/usr/bin/env python3
"""Low-poly REFERENCE models of the TRO 3039 'Mechs (art only; nothing here touches a battle).

Daniel, 2026-11-16: the TRO drawings are redrawn as strict low-polygon models (boxes, wedges, 6/8-sided
prisms, hulls and domes, under 800 triangles, A-stance), five orthographic views each. These models are REFERENCE material:
the "lego pieces" for the Combat Lab block dictionary are read off them, so the generator's output ends up
recognisable but further from the source. Models and renders stay in the PRIVATE repo (`reference_art/` is
in tools/publish_public.py's PRIVATE_PATHS). Kept apart from the token generator (INTEGRATION__tokens.py).

Commands (run with `python -I tools/lowpoly_ref.py ...`):
  check  [MODEL.json ...]   triangle budget, required assemblies, parts on the ground, mtf cross-check
  render [MODEL.json ...]   five-view sheet(s) into reference_art/sheets/ (add --iso for a 3/4 panel)
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
    """Convex hull of a small point set (a few dozen at most): (vertices, faces). Brute force: every triple of points
    that has all the others on one side is a face plane; the points on a plane make one polygon, ordered by angle."""
    pts = []
    for p in points:
        if all(_len(_sub(p, q)) > 1e-9 for q in pts):
            pts.append(tuple(p))
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
                           "tris": tri_count(faces), "tone": part.get("tone")})
    return solids


# ---------------------------------------------------------------- the unit file (data/meks.zip)
def read_mtf(name):
    """name = 'Commando COM-2D'. Returns {mass, walk, jump, weapons: [(LOC, name)], jump_jets: {LOC: count}}."""
    with zipfile.ZipFile(MEKS_ZIP) as z:
        path = next((p for p in z.namelist() if p.endswith("/" + name + ".mtf")), None)
        if path is None:
            raise FileNotFoundError(name)
        lines = z.read(path).decode("utf-8", "replace").splitlines()
    out = {"file": path, "weapons": [], "jump_jets": {}, "mass": None, "walk": None, "jump": 0}
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
        elif not s:
            if in_weapons and out["weapons"]:
                in_weapons = False
    return out


# ---------------------------------------------------------------- checks
def check_model(model):
    """Returns (errors, notes). Errors fail the check."""
    errors, notes = [], []
    solids = expand_parts(model)
    tris = sum(s["tris"] for s in solids)
    notes.append("%d parts, %d triangles" % (len(solids), tris))
    if tris >= TRIANGLE_LIMIT:
        errors.append("triangle budget: %d (limit under %d)" % (tris, TRIANGLE_LIMIT))
    asm = {s["assembly"] for s in solids}
    for need in REQUIRED_ASSEMBLIES:
        if need not in asm:
            errors.append("no part in assembly %r" % need)
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
    dr.text((14, 10), "%s %s   |   %d parts, %d triangles   |   same scale in every view" %
            (model["unit"].upper(), model["model"], len(solids), tris), fill="black", font=font)
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


# ---------------------------------------------------------------- command line
def _load(path):
    with open(path) as f:
        return json.load(f)


def _models(args):
    paths = [a for a in args if a.endswith(".json")] or sorted(
        os.path.join(MODELS, f) for f in os.listdir(MODELS) if f.endswith(".json"))
    return paths


def main(argv):
    if len(argv) < 2 or argv[1] not in ("check", "render", "mtf"):
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
        else:
            out = os.path.join(SHEETS, os.path.basename(path)[:-5] + ".png")
            tris = render_sheet(model, out, iso="--iso" in args)
            print("wrote %s (%d triangles)" % (os.path.relpath(out, ROOT), tris))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
