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
              "we": (222, 74, 62), "wb": (226, 160, 52), "wm": (64, 132, 214), "hl": (176, 190, 206), "ln": (30, 34, 42)}

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


def part_meshes(model, drop=()):
    """[(cls, vertices (n,3), faces (m,3))] for every convex solid of the unit, in levels.
    `drop` lists part tags left out (none by default: weapons are drawn)."""
    b, k = T._views(model, model["drawn_levels"] * T.LEVEL)
    s = k / T.LEVEL
    sph, slab = _sphere_points(), _slab_points()
    out = []
    for part in b.parts:
        if part["tag"] in drop:
            continue
        for grp in part["groups"]:
            pts = []
            for p, r in grp:
                w = _to_world(p, k)
                pts += [w] if not r else list(w + (sph if part["tag"] == "w" else slab) * (r * s))
            m = _hull(pts)
            if m is not None:
                out.append((part["cls"], np.asarray(m.vertices), np.asarray(m.faces)))
    return out


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
