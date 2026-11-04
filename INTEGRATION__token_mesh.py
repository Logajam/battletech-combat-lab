"""
INTEGRATION__token_mesh.py  (NEW 2026-11-03, Claude - Combat Lab art, output only)

Turns a unit's PART MODEL (INTEGRATION__tokens.build_model) into real 3D meshes, so
the top / front / rear / side views are renders of ONE shaded object and a 3D viewer
(three.js) or a game engine can load it. Art project: nothing here touches a battle.

    model  = tokens.build_model(tokens.read_unit("Atlas AS7-D.mtf"))
    data   = unit_mesh(model)           # plain dict: parts with vertices and triangles
    write_glb(model, "atlas.glb")       # the same, as a binary glTF file

Each part of the 2D model is already a convex solid (a chamfered box is the hull of its
corners; a limb segment is the hull of two spheres), so each becomes one convex hull.
Colors are classes (t1..t4 body tones, we / wb / wm weapon classes, hl highlights, ln
seam lines); the viewer maps a class to a material, so a palette change is one table.

World units are LEVELS (one level = LEVEL px in the 2D drawings; a 'Mech's standee is 2
levels tall, 3 for a superheavy: Core p.57, p.240). Axes follow glTF / three.js:
X = the figure's LEFT (+), Y = up, Z = forward, so a camera on +Z sees the front.

Needs numpy, scipy and trimesh (art tools only; the simulator does not use them).
"""

import math

import numpy as np

import INTEGRATION__tokens as T

# class -> RGB (0-255) for the .glb file; the web viewer uses its own theme-aware table
GLB_COLORS = {"t1": (88, 96, 108), "t2": (112, 121, 134), "t3": (138, 148, 162), "t4": (52, 58, 68),
              "we": (222, 74, 62), "wb": (226, 160, 52), "wm": (142, 96, 214), "hl": (176, 190, 206), "ln": (30, 34, 42), "tm": (196, 200, 208), "gm": (58, 64, 74), "ck": (70, 150, 235)}

_SPHERE = None


def _sphere_points():
    """Unit-sphere vertices (an icosphere, one subdivision: 42 points) to inflate a limb end."""
    global _SPHERE
    if _SPHERE is None:
        import trimesh
        _SPHERE = np.array(trimesh.creation.icosphere(subdivisions=1, radius=1.0).vertices)
    return _SPHERE


_SLAB = None


def _slab_points():
    """A chamfered cube's 24 vertices (every permutation of +-1, +-1, +-a): the end of an armored
    limb slab. The 2D drawings keep round limb ends; in 3D the limbs are slabs, as in the reference
    kits (every edge cut, no true tubes). Weapons keep the round caps (barrels are round)."""
    global _SLAB
    if _SLAB is None:
        a, pts = 0.62, []
        for sx in (-1, 1):
            for sy in (-1, 1):
                for sz in (-1, 1):
                    pts += [(sx, sy, sz * a), (sx, sy * a, sz), (sx * a, sy, sz)]
        _SLAB = np.array(pts, dtype=float) * 0.92
    return _SLAB


def _to_world(p, k):
    """Model (x right, y forward, z up, raw units) -> viewer (X left, Y up, Z forward), in levels."""
    s = k / T.LEVEL
    return np.array([-p[0] * s, p[2] * s, p[1] * s])


def _hull(points):
    import trimesh
    try:
        m = trimesh.convex.convex_hull(np.asarray(points, dtype=float))
    except Exception:                                  # a flat / degenerate point set: skip it
        return None
    return m if len(m.faces) else None


def _raw_parts(model, drop=(), with_src=False):
    """[(cls, vertices (n,3), faces (m,3), tag)] for every convex solid of the unit, in levels, at the model's current fit.
    with_src: [(cls, tag, src, vertices, faces, loc, role)] instead, src = the builder line that made the part (tools/token_audit.py),
    loc / role = the location and role (core, plate, cover, item, detail) the shell builder gave it."""
    b, k = T._views(model, model["drawn_levels"] * T.LEVEL)
    s = k / T.LEVEL
    sph, slab = _sphere_points(), _slab_points()
    out = []
    for part in b.parts:
        if part["tag"] in drop:
            continue
        for grp in part["groups"]:
            pts = []
            if len(grp) == 2 and (grp[0][1] or grp[1][1]):
                # a limb segment or joint: a faceted CYLINDER / frustum along its own axis (8 sides, 12 for weapons
                # and joints), not a cube on each end; two ends at one point = a low-poly ball
                (pa, ra), (pb, rb) = grp
                wa, wb_ = _to_world(pa, k), _to_world(pb, k)
                ax = wb_ - wa
                ln = float(np.linalg.norm(ax))
                if ln < 1e-7:
                    pts = list(wa + sph * (ra * s))
                else:
                    ax = ax / ln
                    ref = np.array([1.0, 0.0, 0.0]) if abs(ax[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
                    u = np.cross(ax, ref); u /= np.linalg.norm(u)
                    v = np.cross(ax, u)
                    n = 12 if part["tag"] in ("w", "j") else 8
                    for ang in range(n):
                        t = 2 * math.pi * (ang + 0.5) / n
                        d = math.cos(t) * u + math.sin(t) * v
                        pts.append(wa + d * (ra * s))
                        pts.append(wb_ + d * (rb * s))
            else:
                for p, r in grp:
                    w = _to_world(p, k)
                    pts += [w] if not r else list(w + (sph if part["tag"] == "w" else slab) * (r * s))
            m = _hull(pts)
            if m is None:
                continue
            if with_src:
                out.append((part["cls"], part["tag"], part.get("src", ""), np.asarray(m.vertices), np.asarray(m.faces), part.get("loc", ""), part.get("role", "")))
            else:
                out.append((part["cls"], np.asarray(m.vertices), np.asarray(m.faces), part["tag"]))
    return out


# ---- the scaling law: equal mass, equal volume
DENSITY = 0.0037                 # levels^3 of body per ton: the median of the first 47 generated units, so the average look is kept
FIT_MIN, FIT_MAX = 0.45, 2.4


def union_volume(parts, cell=0.04):
    """Volume (levels^3) of the union of the convex solids, counted on a grid of cell centres (overlaps counted once)."""
    from scipy.spatial import ConvexHull
    allv = np.vstack([v for v in parts])
    lo, hi = allv.min(0) - cell, allv.max(0) + cell
    shape = np.ceil((hi - lo) / cell).astype(int)
    occ = np.zeros(shape, dtype=bool)
    for v in parts:
        try:
            h = ConvexHull(v)
        except Exception:
            continue
        i0 = np.maximum(((v.min(0) - lo) / cell).astype(int), 0)
        i1 = np.minimum(np.ceil((v.max(0) - lo) / cell).astype(int) + 1, shape)
        idx = np.stack(np.meshgrid(*[np.arange(i0[k], i1[k]) for k in range(3)], indexing="ij"), -1).reshape(-1, 3)
        pts = lo + (idx + 0.5) * cell
        inside = np.all(pts @ h.equations[:, :3].T + h.equations[:, 3] <= 1e-9, axis=1)
        occ[tuple(idx[inside].T)] = True
    return float(occ.sum() * cell ** 3)


def body_volume(model):
    """Measured volume of the body: every part except weapons (a weapon's bulk follows its own mass)."""
    return union_volume([v for _, v, _f, tag in _raw_parts(model) if tag != "w"])


def calibrate(model):
    """Set model["fit"] so that body volume = DENSITY x tons (two secant steps on f, volume ~ f^2). The 'Mech's height is
    already the rules curve; only its width and depth change. Heavy and light, crouched and upright: one density."""
    if model.get("_cal"):
        return
    if model.get("shell"):                                   # the shell builder's volume comes from its parts (INTEGRATION__shell), not a rescale
        model["_cal"] = True
        return
    model["nocap"] = True
    f0 = T._mass_factor(model) * (0.90 + 0.24 * min(model["tons"], 100) / 100.0)
    model["fit"] = f0
    target = DENSITY * model["tons"]
    v0 = body_volume(model)
    f1 = min(FIT_MAX, max(FIT_MIN, f0 * math.sqrt(target / max(v0, 1e-6))))
    model["fit"] = f1
    v1 = body_volume(model)
    slope = 2.0
    if abs(f1 - f0) > 1e-4 and v0 > 0 and v1 > 0:
        slope = min(3.0, max(0.8, math.log(v1 / v0) / math.log(f1 / f0)))
    f2 = min(FIT_MAX, max(FIT_MIN, f1 * (target / max(v1, 1e-6)) ** (1.0 / slope)))
    model["fit"] = f2
    model["fit_clamped"] = f2 in (FIT_MIN, FIT_MAX)
    model["_cal"] = True


def part_meshes(model, drop=()):
    """[(cls, vertices (n,3), faces (m,3))] for every convex solid of the unit, in levels, after volume calibration.
    `drop` lists part tags left out (none by default: weapons are drawn)."""
    calibrate(model)
    return [(c, v, f) for c, v, f, tag in _raw_parts(model) if tag not in drop]


def unit_mesh(model, digits=3):
    """The JSON-ready mesh: {"name", "tons", "levels", "rules_levels", "parts": [{"cls", "v", "f"}]}
    with vertices rounded to `digits` decimals (levels), flat lists."""
    parts = []
    for cls, v, f in part_meshes(model):
        parts.append({"cls": cls, "v": [round(float(x), digits) for x in v.reshape(-1)],
                      "f": [int(i) for i in f.reshape(-1)]})
    return {"name": model["name"], "tons": model["tons"], "levels": model["drawn_levels"],
            "rules_levels": model["rules_levels"], "parts": parts}


def write_glb(model, path):
    """One binary glTF: a mesh per part, face-colored by class. Returns the triangle count."""
    import trimesh
    scene = trimesh.Scene()
    tris = 0
    for i, (cls, v, f) in enumerate(part_meshes(model)):
        m = trimesh.Trimesh(vertices=v, faces=f, process=False)
        m.visual.face_colors = np.tile(np.array(GLB_COLORS.get(cls, (128, 128, 128)) + (255,), dtype=np.uint8), (len(f), 1))
        scene.add_geometry(m, node_name=f"{cls}_{i}", geom_name=f"{cls}_{i}")
        tris += len(f)
    scene.export(path)
    return tris
