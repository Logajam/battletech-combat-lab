#!/usr/bin/env python3
"""The block library for the low-poly reference models: task T15a, first pass (Claude, 2026-11-17, session 28).

Daniel, 2026-11-17: "Begin a first pass at creating 'Lego blocks' ... For each block, you must be able to show the exact image
you used as reference material. After each block is made, compare your work to the reference material and decide if its close
enough." His answers that day: prune the taxonomy first (reference_art/block_taxonomy.json `prune_1`), build each block at TWO
levels of detail (HIGH, the one judged against the drawing, and LOW, the under-800-a-'Mech reference level, with an outline check
between them), and start with the common dozen named in INTEGRATION__TASK_SPECS.md T15. Stick to the session-27 material
(reference_art/): the earlier token and shell art is on the back burner and is not used here.

WHAT A BLOCK IS. A named, parametrised GENERATOR: `generate(block_id, lod, params)` returns
  parts    a list of convex solids in tools/lowpoly_ref.py's primitive format (box, wedge, bar, tube, hull, dome), so the same
           renderer and checks apply. "tone" marks dark recesses (bores, visors, vents) and lighter trim.
  anchors  named points where neighbouring blocks attach (a shin has `knee` and `ankle`). The same at every level of detail.
  mounts   weapon / equipment / greeble mount points (block_taxonomy.json `mount_points`): id, kind, position, facing, envelope
           (shares of the block's size), accepts. The same at every level of detail (the plan: "a mount must not move when the
           detail changes").
Sizes are in the models' units (a 'Mech about 10 tall), at the size of the reference unit; `params` scale them. Each block is
drawn in its own frame: +y up, +z forward, +x the 'Mech's LEFT (the side a mirrored part is authored on), anchors at sensible
origins (a limb's upper joint at the origin, hanging along -y).

THE RECORD. reference_art/blocks/library.json: for each block its form and preset (from prune_1), the reference (which TRO
drawing, the crop box in that picture's pixels, what the crop shows), the camera that matches the drawing's angle, the default
params, and the VERDICT (Claude's judgement after comparing: close enough or not, and why).

Commands (`python -I tools/lowpoly_blocks.py ...`):
  sheets [ID ...]   reference crop | HIGH in the drawing's angle | LOW the same | HIGH and LOW front / side / top, with the
                    triangle counts and the outline match, into reference_art/blocks/sheets/<part>__<type>.png
  check             every block: generates at both levels, anchors and mounts identical, LOW within its budget, outline match
                    of LOW to HIGH at least OUTLINE_MIN in each of the three views, reference crop inside its picture
  page OUT.html     one page with every sheet and verdict (images inlined), for Daniel
PRIVATE: the crops are Catalyst artwork; everything lives under reference_art/ (publish_public.py's PRIVATE_PATHS).
"""
import base64
import io
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lowpoly_ref as L  # noqa: E402

BLOCKS = os.path.join(L.REF, "blocks")
LIBRARY = os.path.join(BLOCKS, "library.json")
SHEETS = os.path.join(BLOCKS, "sheets")

# A 'Mech at LOW stays under lowpoly_ref.TRIANGLE_LIMIT (800) and is built of about 14 blocks, some mirrored: about 60 a block
# on average. Budgets per block at LOW are in the library; HIGH is free up to HIGH_LIMIT (the plan: about 15,000 a 'Mech).
HIGH_LIMIT = 1600
# LOW's outline must cover at least this share of HIGH's (intersection over union of the black shapes, each of front, side, top).
OUTLINE_MIN = 0.85

CREASE_DEG = 24   # the renderer outlines a fold between two faces of one part only when it is sharper than this
DARK = 0.14        # bores, recesses, visor glass, vent slots
TRIM = 0.97        # raised trim, rims


# ---------------------------------------------------------------- primitive helpers (lowpoly_ref part dictionaries)
_seq = [0]


def _id(name):
    _seq[0] += 1
    return "%s_%d" % (name, _seq[0])


def part(kind, name, tone=None, **kw):
    p = {"kind": kind, "id": _id(name), "assembly": "block"}
    p.update(kw)
    if tone is not None:
        p["tone"] = tone
    return p


def hull(name, pts, tone=None):
    return part("hull", name, tone, pts=[list(map(float, p)) for p in pts])


def cbox(name, c, s, ch=0.0, taper=(1.0, 1.0), shift=(0.0, 0.0), tone=None):
    """A box centred on c, size s, every edge chamfered by ch; the top face scaled by taper (x, z) and moved by shift (x, z)."""
    cx, cy, cz = c
    sx, sy, sz = (v / 2 for v in s)
    pts = []
    ch = min(ch, sx * 0.45, sy * 0.45, sz * 0.45)
    for ax, ay, az in ((sx, sy - ch, sz - ch), (sx - ch, sy, sz - ch), (sx - ch, sy - ch, sz)) if ch > 0 else ((sx, sy, sz),):
        for i in (-1, 1):
            for j in (-1, 1):
                for k in (-1, 1):
                    x, y, z = i * ax, j * ay, k * az
                    t = (y + sy) / (2 * sy)                       # 0 at the bottom, 1 at the top
                    x *= 1 + (taper[0] - 1) * t
                    z *= 1 + (taper[1] - 1) * t
                    pts.append((cx + x + shift[0] * t, cy + y, cz + z + shift[1] * t))
    return hull(name, pts, tone)


def tube(name, a, b, d0, d1=None, n=8, tone=None, roll=0.0):
    d1 = d0 if d1 is None else d1
    return part("tube", name, tone, a=list(a), b=list(b), w0=[d0, d0], w1=[d1, d1], n=n, roll=roll)


def dome(name, c, r, n=8, rings=4, half=True, tone=None, roll=0.0):
    kw = {"c": list(c), "r": list(r), "n": n, "rings": rings, "roll": roll}
    if half:
        kw["half"] = "top"
    return part("dome", name, tone, **kw)


def ring_points(center, axis, radius, n, roll=0.0):
    """n points on a circle about `center`, in the plane square to the unit axis 'x', 'y' or 'z'."""
    pts = []
    for k in range(n):
        t = math.radians(roll) + 2 * math.pi * k / n
        a, b = radius * math.cos(t), radius * math.sin(t)
        if axis == "x":
            pts.append((center[0], center[1] + a, center[2] + b))
        elif axis == "y":
            pts.append((center[0] + a, center[1], center[2] + b))
        else:
            pts.append((center[0] + a, center[1] + b, center[2]))
    return pts


def facet_section(y, w, d, ch=0.1, front=0.18, shoulder=0.3):
    """A limb's cross-section at height y (shin, thigh: one shape so the leg repeats its angles, art spec A4): back corners
    chamfered by ch x depth, a broad faceted front (a flat centre `front` x width each side of the middle, two facets back
    to the sides at `shoulder` x depth). Insets scale with the size, so the side faces stay flat."""
    c = ch * d
    return [(-w / 2 + c, y, -d / 2), (w / 2 - c, y, -d / 2), (-w / 2, y, -d / 2 + c), (w / 2, y, -d / 2 + c),
            (-w / 2, y, d * shoulder), (w / 2, y, d * shoulder), (-w * front, y, d / 2), (w * front, y, d / 2)]


def radial_tooth(name, x0, x1, angle, r0, r1, half_width, tone=None):
    """A small block standing out radially from a drum lying along x: from radius r0 to r1, x0..x1 long, turned to `angle`
    so its sides follow the ring (a gear tooth, a rib)."""
    u = (0.0, math.cos(angle), math.sin(angle))          # outward
    v = (0.0, -math.sin(angle), math.cos(angle))         # along the ring
    pts = []
    for x in (x0, x1):
        for r in (r0, r1):
            for w in (-half_width, half_width):
                pts.append((x, u[1] * r + v[1] * w, u[2] * r + v[2] * w))
    return hull(name, pts, tone)


def mount(mid, kind, pos, facing, envelope, accepts):
    return {"id": mid, "kind": kind, "pos": [round(v, 4) for v in pos], "facing": facing, "envelope": envelope, "accepts": accepts}


# ---------------------------------------------------------------- the generators
# Each takes (lod, p) with p the params (defaults from the library merged with the caller's) and returns (parts, anchors, mounts).
# `hi = lod == "high"` switches the detail; the anchors and mounts are computed BEFORE the switch so both levels share them.

def slab_boot(lod, p):
    """foot/slab_boot (Commando): a long sole with a stepped lip along each side; on it a long GABLED top running the whole
    length (sloped sides up to a flat ridge, highest at the ankle, falling toward the tip), a raised rib along the ridge, a
    squared tip with a dark slot, a low heel behind and the ankle socket on top."""
    Lg, W, H = p["length"], p["width"], p["height"]
    hi = lod == "high"
    z0, z1 = -Lg * 0.3, Lg * 0.7                      # heel end, toe end (the ankle sits over z = 0)
    anchors = {"ankle": [0.0, H, 0.0]}
    mounts = [mount("foot.side", "greeble", (W / 2, H * 0.3, Lg * 0.15), "+x", [0.1, 0.3, 0.4], ["hazard_panel", "vent_grille"]),
              mount("foot.rear", "equipment", (0.0, H * 0.5, z0), "-z", [0.6, 0.5, 0.2], ["jump_jet_nozzle"])]
    sole_h = H * 0.26
    rw = W * 0.34                                     # the ridge's width

    def gable(inset, lift):
        return [(-W / 2 + inset, sole_h, z0 + 0.04), (W / 2 - inset, sole_h, z0 + 0.04),
                (-W * 0.42 + inset, sole_h, z1 - 0.02), (W * 0.42 - inset, sole_h, z1 - 0.02),
                (-rw / 2, H * 0.78 + lift, z0 + Lg * 0.12), (rw / 2, H * 0.78 + lift, z0 + Lg * 0.12),
                (-rw / 2, H * 0.5 + lift, z1 - 0.1), (rw / 2, H * 0.5 + lift, z1 - 0.1)]
    parts = []
    if hi:
        parts.append(cbox("sole", (0, sole_h / 2, (z0 + z1) / 2), (W, sole_h, z1 - z0), ch=0.04, taper=(0.98, 1.0)))
        parts.append(hull("gable", gable(0.06, 0.0)))
        # the rib on the ridge
        parts.append(hull("rib", [(-rw * 0.18, H * 0.78, z0 + Lg * 0.16), (rw * 0.18, H * 0.78, z0 + Lg * 0.16),
                                  (-rw * 0.18, H * 0.5, z1 - 0.14), (rw * 0.18, H * 0.5, z1 - 0.14),
                                  (-rw * 0.12, H * 0.84, z0 + Lg * 0.18), (rw * 0.12, H * 0.84, z0 + Lg * 0.18),
                                  (-rw * 0.12, H * 0.56, z1 - 0.16), (rw * 0.12, H * 0.56, z1 - 0.16)], tone=TRIM))
        # the squared tip and its slot
        parts.append(cbox("tip", (0, sole_h + H * 0.1, z1 - 0.05), (W * 0.5, H * 0.24, 0.1), ch=0.02))
        parts.append(cbox("tip_slot", (0, sole_h + H * 0.1, z1 + 0.004), (W * 0.3, H * 0.07, 0.02), tone=DARK))
        # the stepped lips along the sides, with a dark seam above each
        for sx in (-1, 1):
            parts.append(hull("lip", [(sx * W * 0.5, sole_h, z0 + 0.08), (sx * W * 0.47, sole_h, z1 - 0.1),
                                      (sx * W * 0.44, sole_h + H * 0.1, z0 + 0.08), (sx * W * 0.41, sole_h + H * 0.1, z1 - 0.1),
                                      (sx * W * 0.38, sole_h, z0 + 0.08), (sx * W * 0.35, sole_h, z1 - 0.1)], tone=TRIM))
        # the heel and the ankle socket
        parts.append(cbox("heel", (0, H * 0.42, z0 + 0.12), (W * 0.7, H * 0.4, 0.24), ch=0.04))
        parts.append(cbox("heel_vent", (0, H * 0.42, z0 - 0.004), (W * 0.42, H * 0.12, 0.02), tone=DARK))
        parts.append(tube("socket", (0, H * 0.7, 0.0), (0, H, 0.0), W * 0.46, W * 0.4, n=12))
    else:
        parts.append(cbox("sole", (0, sole_h / 2, (z0 + z1) / 2), (W, sole_h, z1 - z0)))
        parts.append(hull("gable", gable(0.06, 0.0)))
        parts.append(tube("socket", (0, H * 0.7, 0.0), (0, H, 0.0), W * 0.46, n=6))
    return parts, anchors, mounts


def tapered_slab_shin(lod, p):
    """lower_leg/tapered_slab_shin (Commando): a column with a FACETED front (two faces meeting at a centre edge, pentagonal
    section), tapering between knee and ankle (the Commando narrows toward the ankle; other units flare: the taper is a
    param), a big round louvre disc on the knee end, a band at mid-shin, a hatch of vents low on the outer side, a cuff at
    the ankle."""
    Lg, w0, w1, d0, d1 = p["length"], p["top_width"], p["bottom_width"], p["top_depth"], p["bottom_depth"]
    hi = lod == "high"
    anchors = {"knee": [0.0, 0.0, 0.0], "ankle": [0.0, -Lg, 0.0]}
    mounts = [mount("shin.front", "greeble", (0, -Lg * 0.3, d0 / 2), "+z", [0.6, 0.2, 0.1], ["louvre_disc", "hazard_panel"]),
              mount("shin.rear", "equipment", (0, -Lg * 0.75, -d1 / 2), "-z", [0.6, 0.3, 0.3], ["jump_jet_nozzle"]),
              mount("shin.side", "greeble", (w1 / 2, -Lg * 0.6, 0), "+x", [0.1, 0.3, 0.6], ["vent_grille", "hazard_panel"])]

    def width(t):                                     # t = 0 at the knee, 1 at the ankle
        return w0 + (w1 - w0) * t, d0 + (d1 - d0) * t

    def section(y, t, grow=0.0, ch=0.0):
        """The column's cross-section at height y: square back corners chamfered, a broad faceted front (a flat centre
        a third of the width, two facets back to the sides). Every inset scales with the size, so the faces stay flat."""
        w, d = width(t)
        w, d = w + grow, d + grow
        c = ch * d
        return [(-w / 2 + c, y, -d / 2), (w / 2 - c, y, -d / 2), (-w / 2, y, -d / 2 + c), (w / 2, y, -d / 2 + c),
                (-w / 2, y, d * 0.3), (w / 2, y, d * 0.3), (-w * 0.18, y, d / 2), (w * 0.18, y, d / 2)]
    parts = []
    if hi:
        yb = -Lg * 0.46                                # the mid band splits the column in two
        parts.append(hull("upper", section(-Lg * 0.04, 0.04, 0, 0.1) + section(yb, 0.46, 0, 0.1)))
        parts.append(hull("lower", section(yb, 0.46, -0.03, 0.1) + section(-Lg * 0.93, 0.93, -0.03, 0.1)))
        parts.append(hull("band", section(yb + 0.06, 0.43, 0.05, 0.1) + section(yb - 0.06, 0.49, 0.05, 0.1)))
        # the louvre disc on the knee end: rim, dark face, vertical slats; it faces forward on the faceted front
        w, d = width(0.15)
        r = w * 0.42
        cy, zf = -Lg * 0.15, d / 2
        r = w * 0.36
        # the disc sits in a flat square frame standing on the faceted front (the drawing's box round the disc)
        parts.append(cbox("louvre_frame", (0, cy, zf - 0.04), (r * 2.3, r * 2.3, 0.14), ch=0.03))
        zf += 0.03
        parts.append(tube("louvre_rim", (0, cy, zf - 0.02), (0, cy, zf + 0.025), r * 2, n=20, tone=TRIM))
        parts.append(tube("louvre_face", (0, cy, zf + 0.03), (0, cy, zf + 0.04), r * 1.72, n=20, tone=DARK))
        for k in range(-3, 4):
            hgt = 2 * math.sqrt(max(0.0, (r * 0.84) ** 2 - (k * r * 0.22) ** 2))
            parts.append(cbox("slat", (k * r * 0.22, cy, zf + 0.05), (r * 0.08, hgt * 0.95, 0.025)))
        # hatch vents low on the outer side
        w, d = width(0.7)
        for k in range(5):
            parts.append(cbox("vent", (w / 2 + 0.006, -Lg * 0.62 - k * 0.055, -d * 0.05), (0.02, 0.028, d * 0.45), tone=DARK))
        parts.append(cbox("vent_frame", (w / 2 - 0.01, -Lg * 0.73, -d * 0.05), (0.03, Lg * 0.2, d * 0.55), ch=0.01))
        # the knee cap at the top and the cuff at the ankle
        parts.append(hull("knee_cap", section(0.0, 0.0, 0.02, 0.1) + section(-Lg * 0.06, 0.06, 0.02, 0.1)))
        parts.append(hull("cuff", section(-Lg * 0.92, 0.92, 0.06, 0.1) + section(-Lg, 1.0, 0.06, 0.1)))
    else:
        parts.append(hull("core", section(0.0, 0.0, 0, 0.1) + section(-Lg, 1.0, 0, 0.1)))
        w, d = width(0.15)
        parts.append(tube("louvre", (0, -Lg * 0.15, d / 2 - 0.1), (0, -Lg * 0.15, d / 2 + 0.02), w * 0.66, n=6, tone=DARK))
    return parts, anchors, mounts


def tapered_slab_thigh(lod, p):
    """upper_leg/tapered_slab_thigh (Commando): the shin's faceted section (centre edge in front), wide at the hip and
    narrower at the knee; an armor shell over the upper part whose lower edge comes to a V in front; hatch vents on the
    inner side; a short socket on top for the hip block."""
    Lg, w0, w1, d0, d1 = p["length"], p["top_width"], p["bottom_width"], p["top_depth"], p["bottom_depth"]
    hi = lod == "high"
    anchors = {"hip": [0.0, 0.0, 0.0], "knee": [0.0, -Lg, 0.0]}
    mounts = [mount("thigh.side", "greeble", (w0 / 2, -Lg * 0.4, 0), "+x", [0.1, 0.4, 0.6], ["hazard_panel", "vent_grille"]),
              mount("thigh.front", "greeble", (0, -Lg * 0.5, d0 / 2), "+z", [0.6, 0.3, 0.1], ["hazard_panel", "louvre_disc"])]

    def at(t, grow=0.0):
        return w0 + (w1 - w0) * t + grow, d0 + (d1 - d0) * t + grow
    parts = []
    if hi:
        parts.append(hull("core", facet_section(-Lg * 0.06, *at(0.06)) + facet_section(-Lg, *at(1.0))))
        # the armor shell: grown a little, its lower front edge a V (the centre lower than the sides)
        top = facet_section(-Lg * 0.04, *at(0.04, 0.07))
        ws, ds = at(0.5, 0.07)
        bottom = [q for q in facet_section(-Lg * 0.5, ws, ds) if q[2] < 0]                     # back and sides level
        bottom += [(-ws / 2, -Lg * 0.52, ds * 0.3), (ws / 2, -Lg * 0.52, ds * 0.3),
                   (-ws * 0.18, -Lg * 0.66, ds / 2), (ws * 0.18, -Lg * 0.66, ds / 2)]           # the V in front
        parts.append(hull("shell", top + bottom))
        # a seam across the shell's front and a knee plate below the V
        w, d = at(0.25, 0.075)
        parts.append(cbox("seam", (0, -Lg * 0.25, d / 2 + 0.004), (w * 0.36, 0.025, 0.02), tone=DARK))
        w, d = at(0.82)
        parts.append(hull("knee_plate", facet_section(-Lg * 0.74, w + 0.03, d + 0.03) + facet_section(-Lg * 0.96, w + 0.03, d + 0.03)))
        # hatch vents on the inner side (-x), under the shell
        w, d = at(0.62)
        parts.append(cbox("vent_frame", (-w / 2 - 0.005, -Lg * 0.64, -d * 0.05), (0.04, Lg * 0.26, d * 0.62), ch=0.01))
        for k in range(6):
            parts.append(cbox("vent", (-w / 2 - 0.03, -Lg * 0.54 - k * 0.04, -d * 0.05), (0.02, 0.022, d * 0.52), tone=DARK))
        parts.append(tube("socket", (0, 0.0, 0), (0, -Lg * 0.06, 0), w0 * 0.5, w0 * 0.56, n=12))
    else:
        parts.append(hull("core", facet_section(0.0, *at(0.0, 0.04)) + facet_section(-Lg, *at(1.0))))
    return parts, anchors, mounts


def boxy_chest(lod, p):
    """upper_torso/boxy_chest_sloped_shoulders (Commando): a broad, nearly flat-topped upper chest narrowing to the waist;
    boxy shoulder blocks at the top corners whose tops rise a little outward; a V-shaped upper plate pointing down to the
    centre (the missile grid sits at its point: a mount); a big round plate on the lower chest; a dark neck well on top;
    hatched vent panels on the lower sides."""
    W, H, D = p["width"], p["height"], p["depth"]
    hi = lod == "high"
    anchors = {"waist": [0.0, 0.0, 0.0], "neck": [0.0, H * 0.96, D * 0.02],
               "shoulder_L": [W / 2, H * 0.8, 0.0], "shoulder_R": [-W / 2, H * 0.8, 0.0]}
    mounts = [mount("chest.bay_L", "weapon", (W * 0.1, H * 0.6, D / 2), "+z", [0.2, 0.15, 0.3], ["srm", "lrm", "mrm", "laser", "mg"]),
              mount("chest.bay_R", "weapon", (-W * 0.1, H * 0.6, D / 2), "+z", [0.2, 0.15, 0.3], ["srm", "lrm", "mrm", "laser", "mg"]),
              mount("chest.centre", "weapon", (0, H * 0.32, D / 2), "+z", [0.25, 0.25, 0.3], ["laser", "mg", "flamer"]),
              mount("chest.rear", "equipment", (0, H * 0.5, -D / 2), "-z", [0.6, 0.5, 0.2], ["jump_jet_nozzle", "heat_sink_vent"]),
              mount("chest.top_L", "greeble", (W * 0.4, H * 1.02, 0), "+y", [0.2, 0.2, 0.4], ["antenna_whip", "blade_fin"])]
    bw, mw = W * 0.46, W * 0.66                       # waist width, upper chest width
    body = [(-bw / 2, 0, -D * 0.36), (bw / 2, 0, -D * 0.36), (-bw / 2, 0, D * 0.36), (bw / 2, 0, D * 0.36),
            (-mw / 2, H * 0.56, -D / 2), (mw / 2, H * 0.56, -D / 2), (-mw / 2, H * 0.56, D / 2), (mw / 2, H * 0.56, D / 2),
            (-mw / 2, H * 0.94, -D * 0.44), (mw / 2, H * 0.94, -D * 0.44), (-mw / 2, H * 0.94, D * 0.42), (mw / 2, H * 0.94, D * 0.42)]
    parts = []
    parts.append(hull("body", body))
    for sx in (-1, 1):                                # the shoulder blocks
        x0, x1 = sx * W * 0.28, sx * W * 0.52
        sh = [(x0, H * 0.48, -D * 0.44), (x0, H * 0.48, D * 0.46), (x1, H * 0.52, -D * 0.44), (x1, H * 0.52, D * 0.46),
              (x0, H * 0.97, -D * 0.42), (x0, H * 0.97, D * 0.44), (x1, H * 1.02, -D * 0.42), (x1, H * 1.02, D * 0.44)]
        if hi:                                        # chamfer the outer top edge
            sh = [q for q in sh if not (abs(q[0]) == abs(x1) and q[1] > H)]
            sh += [(x1, H * 0.94, -D * 0.42), (x1, H * 0.94, D * 0.44), (x1 - sx * 0.1, H * 1.02, -D * 0.42), (x1 - sx * 0.1, H * 1.02, D * 0.44)]
        parts.append(hull("shoulder", sh))
    if hi:
        # the V plate: across the upper chest at the top, narrowing to a point above the round plate
        z = D * 0.42
        parts.append(hull("v_plate", [(-mw * 0.47, H * 0.92, z), (mw * 0.47, H * 0.92, z), (-W * 0.1, H * 0.52, D / 2),
                                      (W * 0.1, H * 0.52, D / 2), (-mw * 0.44, H * 0.9, z + 0.07), (mw * 0.44, H * 0.9, z + 0.07),
                                      (-W * 0.09, H * 0.55, D / 2 + 0.07), (W * 0.09, H * 0.55, D / 2 + 0.07)]))
        # its centre seam and the two plate seams
        for xs in (-1, 1):
            parts.append(hull("seam", [(xs * W * 0.02, H * 0.9, z + 0.075), (xs * W * 0.025, H * 0.9, z + 0.075),
                                       (xs * W * 0.02, H * 0.57, D / 2 + 0.075), (xs * W * 0.025, H * 0.57, D / 2 + 0.075),
                                       (xs * W * 0.02, H * 0.9, z + 0.06), (xs * W * 0.02, H * 0.57, D / 2 + 0.06)], tone=DARK))
        # the big round plate on the lower chest, with a cross bar
        # (the lower chest's front leans: tilt the plate to lie on it, along the face's normal)
        cy = H * 0.3
        slope = (D / 2 - D * 0.36) / (H * 0.56)                     # dz / dy of the lower front face
        zr = D * 0.36 + slope * cy
        nn = L._unit((0.0, -slope, 1.0))
        at = lambda out: (nn[0] * out, cy + nn[1] * out, zr + nn[2] * out)
        parts.append(tube("disc_rim", at(-0.05), at(0.06), W * 0.34, n=24, tone=TRIM))
        parts.append(tube("disc", at(0.06), at(0.09), W * 0.3, n=24))
        u = L._unit((0.0, 1.0, slope))                              # up along the face
        for name, (sx, sy) in (("disc_bar", (W * 0.29, 0.03)), ("disc_bar2", (0.03, W * 0.29))):
            c = at(0.1)
            pts = []
            for i in (-1, 1):
                for j in (-1, 1):
                    for o in (0.0, 0.015):
                        pts.append((c[0] + i * sx / 2, c[1] + j * sy / 2 * u[1] + nn[1] * o, c[2] + j * sy / 2 * u[2] + nn[2] * o))
            parts.append(hull(name, pts, tone=DARK))
        # the neck well, and vent panels low on the sides
        parts.append(cbox("neck_well", (0, H * 0.945, D * 0.0), (W * 0.24, 0.02, D * 0.5), tone=DARK))
        for sx in (-1, 1):
            xv = sx * (bw / 2 + (mw - bw) / 2 * 0.55) + sx * 0.01
            for k in range(5):
                parts.append(cbox("vent", (xv, H * 0.22 + k * 0.07, D * 0.1), (0.02, 0.03, D * 0.4), tone=DARK))
        # a belt plate at the waist
        parts.append(cbox("belt", (0, H * 0.05, D * 0.37), (bw * 0.8, H * 0.08, 0.06), ch=0.02))
    return parts, anchors, mounts


def shoulder_drum(lod, p):
    """shoulder/shoulder_pod and shoulder/shoulder_disc: ONE drum generator (prune_1: the drum family). A drum lying across
    (axis x) on the outside of the shoulder, the arm hangs from its underside. Pod (Javelin): small diameter, longer, a toothed
    collar at the body end, a ring face with a dark hub. Disc (Dragon): big diameter, short, a ribbed outer band, a raised
    inner face carrying a slatted vent window."""
    D, Lg, style = p["diameter"], p["length"], p["style"]
    hi = lod == "high"
    x0, x1 = 0.0, Lg                                     # the body face at x = 0, the outer face at x = Lg
    anchors = {"torso": [0.0, 0.0, 0.0], "arm": [Lg * 0.5, -D * 0.5, 0.0]}
    mounts = [mount("drum.top", "greeble", (Lg * 0.5, D * 0.5, 0), "+y", [0.6, 0.3, 0.5], ["blade_fin", "antenna_whip"]),
              mount("drum.face", "weapon" if style == "disc" else "greeble", (Lg, 0, 0), "+x", [0.2, 0.6, 0.6],
                    ["laser", "mg"] if style == "disc" else ["vent_grille"])]
    parts = []
    n = 24 if hi else 6
    if hi:
        if style == "pod":
            parts.append(tube("collar", (x0, 0, 0), (Lg * 0.22, 0, 0), D * 1.12, n=24))
            for k in range(28):                         # the collar's crown of teeth, like a gear
                parts.append(radial_tooth("tooth", Lg * 0.0, Lg * 0.22, 2 * math.pi * k / 28, D * 0.54, D * 0.585, D * 0.03))
            parts.append(tube("body", (Lg * 0.22, 0, 0), (Lg * 0.92, 0, 0), D, n=n))
            for k in (0.4, 0.6, 0.78):
                parts.append(tube("rib", (Lg * k, 0, 0), (Lg * k + 0.03, 0, 0), D * 1.04, n=n, tone=TRIM))
            parts.append(tube("rim", (Lg * 0.9, 0, 0), (x1, 0, 0), D * 1.02, D * 0.96, n=n, tone=TRIM))
            parts.append(tube("face", (x1, 0, 0), (x1 + 0.01, 0, 0), D * 0.78, n=n))
            parts.append(tube("hub", (x1 + 0.01, 0, 0), (x1 + 0.03, 0, 0), D * 0.34, n=16, tone=DARK))
        else:
            # the big drum, a rim, then a raised BOSS with ribs round its side; the port and a dot on the boss's face (Dragon)
            parts.append(tube("body", (x0, 0, 0), (Lg * 0.42, 0, 0), D, n=n))
            parts.append(tube("rim", (Lg * 0.42, 0, 0), (Lg * 0.5, 0, 0), D * 0.98, D * 0.86, n=n, tone=TRIM))
            parts.append(tube("boss", (Lg * 0.5, 0, 0), (x1, 0, 0), D * 0.64, D * 0.62, n=n))
            for k in range(30):
                parts.append(radial_tooth("boss_rib", Lg * 0.52, Lg * 0.94, 2 * math.pi * k / 30, D * 0.3, D * 0.33, D * 0.012, tone=TRIM))
            parts.append(tube("boss_face_rim", (x1, 0, 0), (x1 + 0.02, 0, 0), D * 0.6, D * 0.56, n=n, tone=TRIM))
            parts.append(tube("port", (x1 + 0.02, -D * 0.04, D * 0.05), (x1 + 0.04, -D * 0.04, D * 0.05), D * 0.32, n=20, tone=DARK))
            for k in range(-3, 4):
                hgt = 2 * math.sqrt(max(0.0, (D * 0.15) ** 2 - (k * D * 0.038) ** 2))
                parts.append(cbox("slat", (x1 + 0.045, -D * 0.04, D * 0.05 + k * D * 0.038), (0.02, hgt * 0.95, D * 0.016)))
            parts.append(tube("dot", (x1 + 0.02, D * 0.02, -D * 0.16), (x1 + 0.05, D * 0.02, -D * 0.16), D * 0.12, n=12, tone=DARK))
    else:
        if style == "pod":
            parts.append(tube("collar", (x0, 0, 0), (Lg * 0.22, 0, 0), D * 1.26, n=n))
            parts.append(tube("body", (Lg * 0.22, 0, 0), (x1, 0, 0), D * 1.06, n=n))
            parts.append(tube("face", (x1, 0, 0), (x1 + 0.02, 0, 0), D * 0.5, n=6, tone=DARK))
        else:
            parts.append(tube("body", (x0, 0, 0), (Lg * 0.5, 0, 0), D * 1.06, n=n))
            parts.append(tube("boss", (Lg * 0.5, 0, 0), (x1, 0, 0), D * 0.68, n=n))
            parts.append(tube("port", (x1, 0, 0), (x1 + 0.02, 0, 0), D * 0.34, n=6, tone=DARK))
    return parts, anchors, mounts


def launcher_bay(lod, p):
    """side_torso/launcher_bay (Javelin): a housing whose front face LEANS BACK (top further back than the bottom, as the
    Javelin's chest facets), a small lip over it, and a tight grid of nearly flush tube mouths (rows x cols): each a light
    rim round a dark bore with a light wedge across a quarter of it (the drawing's hatched pie)."""
    W, H, D, rows, cols = p["width"], p["height"], p["depth"], int(p["rows"]), int(p["cols"])
    lean = p.get("lean", 0.3)                       # how far back the top of the face is, as a share of the depth
    hi = lod == "high"
    anchors = {"torso": [0.0, 0.0, -D / 2]}
    mounts = [mount("bay.grid", "weapon", (0, 0, D / 2 - lean * D / 2), "+z", [0.8, 0.7, 0.2], ["srm", "lrm", "mrm", "atm", "mml"]),
              mount("bay.side", "greeble", (W / 2, 0, 0), "+x", [0.1, 0.6, 0.6], ["hazard_panel", "vent_grille"])]
    zb, zt = D / 2, D / 2 - lean * D                # the face's z at the bottom and the top
    th = math.atan2(zb - zt, H)                     # the face leans back by th; its normal points forward and up
    nrm = (0.0, math.sin(th), math.cos(th))

    def on_face(x, y, out=0.0):
        z = zb + (zt - zb) * (y + H / 2) / H
        return (x + nrm[0] * out, y + nrm[1] * out, z + nrm[2] * out)
    ch = 0.05 if hi else 0.0
    box = [(-W / 2, -H / 2, -D / 2), (W / 2, -H / 2, -D / 2), (-W / 2, H / 2, -D / 2), (W / 2, H / 2, -D / 2),
           (-W / 2 + ch, -H / 2, zb), (W / 2 - ch, -H / 2, zb), (-W / 2 + ch, H / 2, zt), (W / 2 - ch, H / 2, zt),
           (-W / 2, -H / 2 + ch, zb - ch), (W / 2, -H / 2 + ch, zb - ch), (-W / 2, H / 2 - ch, zt - ch), (W / 2, H / 2 - ch, zt - ch)]
    parts = [hull("housing", box)]
    pitch_x, pitch_y = W * 0.84 / cols, H * 0.8 / rows
    d_tube = min(pitch_x, pitch_y) * 0.9
    lip = [(-W * 0.52, H / 2, zt + 0.02), (W * 0.52, H / 2, zt + 0.02), (-W * 0.52, H / 2 - 0.06, zt + 0.02),
           (W * 0.52, H / 2 - 0.06, zt + 0.02), (-W * 0.5, H / 2, zt + 0.12), (W * 0.5, H / 2, zt + 0.12)]
    parts.append(hull("lip", lip, tone=TRIM if hi else None))
    for r in range(rows):
        for c in range(cols):
            x = (c - (cols - 1) / 2) * pitch_x
            y = -H * 0.04 + ((rows - 1) / 2 - r) * pitch_y
            if hi:
                parts.append(tube("rim", on_face(x, y, -0.02), on_face(x, y, 0.03), d_tube, n=16, tone=TRIM, roll=0))
                parts.append(tube("bore", on_face(x, y, 0.03), on_face(x, y, 0.035), d_tube * 0.74, n=16, tone=DARK))
                # the light wedge across a quarter of the bore
                rr = d_tube * 0.36
                u = (1.0, 0.0, 0.0)
                v = (0.0, nrm[2], -nrm[1])            # up along the leaning face
                pts = []
                for out in (0.035, 0.045):
                    cen = on_face(x, y, out)
                    pts.append(cen)
                    for k in range(5):
                        t = math.radians(-20 + k * 22.5)
                        pts.append(tuple(cen[i] + rr * (math.cos(t) * u[i] + math.sin(t) * v[i]) for i in range(3)))
                parts.append(hull("wedge", pts))
            else:
                parts.append(tube("mouth", on_face(x, y, -0.02), on_face(x, y, 0.03), d_tube * 0.62, n=4, tone=DARK))
    if hi:
        parts.append(cbox("hazard", (W * 0.505, -H * 0.2, 0), (0.02, H * 0.25, D * 0.5), tone=DARK))
    return parts, anchors, mounts


def fist_arm(lod, p):
    """lower_arm/fist_arm (Commando, left): STACKED SEGMENTS that get bigger toward the wrist (the Commando's forearm widens
    downward): a narrower upper box under the elbow cap, a band, then a big lower housing whose bottom edges are chamfered in
    toward the wrist opening; an outer side plate on the housing. The fist is its own block on the `wrist` anchor."""
    Lg, w0, w1, d0, d1 = p["length"], p["top_width"], p["bottom_width"], p["top_depth"], p["bottom_depth"]
    hi = lod == "high"
    anchors = {"elbow": [0.0, 0.0, 0.0], "wrist": [0.0, -Lg, 0.0]}
    mounts = [mount("forearm.front", "weapon", (0, -Lg * 0.6, d1 / 2), "+z", [0.6, 0.5, 0.3], ["laser", "mg", "flamer", "srm"]),
              mount("forearm.side", "greeble", (w1 / 2, -Lg * 0.6, 0), "+x", [0.1, 0.5, 0.6], ["hazard_panel", "vent_grille"])]
    parts = []
    if hi:
        parts.append(cbox("elbow_cap", (0, -Lg * 0.05, -0.02), (w0 * 1.04, Lg * 0.1, d0 * 1.02), ch=0.05))
        parts.append(cbox("upper", (0, -Lg * 0.25, 0), (w0, Lg * 0.3, d0), ch=0.04))
        parts.append(cbox("band", (0, -Lg * 0.42, 0), ((w0 + w1) / 2 * 1.03, Lg * 0.06, (d0 + d1) / 2 * 1.03), ch=0.02, tone=TRIM))
        # the lower housing: full size, its bottom chamfered in toward the wrist
        y0, y1 = -Lg * 0.45, -Lg * 0.98
        ci = 0.18
        parts.append(hull("housing", [(-w1 / 2, y0, -d1 / 2), (w1 / 2, y0, -d1 / 2), (-w1 / 2, y0, d1 / 2), (w1 / 2, y0, d1 / 2),
                                      (-w1 / 2, y1 + 0.18, -d1 / 2), (w1 / 2, y1 + 0.18, -d1 / 2), (-w1 / 2, y1 + 0.18, d1 / 2),
                                      (w1 / 2, y1 + 0.18, d1 / 2), (-w1 / 2 + ci, y1, -d1 / 2 + ci), (w1 / 2 - ci, y1, -d1 / 2 + ci),
                                      (-w1 / 2 + ci, y1, d1 / 2 - ci), (w1 / 2 - ci, y1, d1 / 2 - ci)]))
        for k in range(2):                               # seams across the housing's front
            parts.append(cbox("seam", (0, -Lg * (0.58 + 0.13 * k), d1 / 2 + 0.004), (w1 * 0.86, 0.022, 0.02), tone=DARK))
        parts.append(cbox("side_plate", (w1 / 2 + 0.025, -Lg * 0.66, 0), (0.05, Lg * 0.3, d1 * 0.66), ch=0.015))
    else:
        parts.append(cbox("upper", (0, -Lg * 0.24, 0), (w0, Lg * 0.48, d0)))
        parts.append(cbox("housing", (0, -Lg * 0.72, 0), (w1, Lg * 0.52, d1)))
    return parts, anchors, mounts


def barrel_arm(lod, p):
    """lower_arm/barrel_arm (Clint): no hand; a rounded housing under the elbow, a fin on top, then a fat barrel ending in a
    thick muzzle ring with a black bore. The forearm points forward (+z) as in the drawing; the elbow is at the origin."""
    Lg, D, Dm, hw = p["length"], p["barrel"], p["muzzle"], p["housing"]
    hi = lod == "high"
    anchors = {"elbow": [0.0, 0.0, 0.0]}
    mounts = [mount("barrel.muzzle", "weapon", (0, 0, Lg), "+z", [0.5, 0.5, 0.1], ["laser", "ppc", "ac", "lbx", "uac", "gauss"]),
              mount("barrel.top", "greeble", (0, D / 2, Lg * 0.5), "+y", [0.3, 0.3, 0.4], ["blade_fin", "antenna_whip"])]
    parts = []
    if hi:
        parts.append(tube("housing", (0, 0, -hw * 0.1), (0, 0, Lg * 0.36), hw, hw * 0.9, n=20))
        parts.append(tube("barrel", (0, 0, Lg * 0.3), (0, 0, Lg * 0.84), D, D * 0.94, n=20))
        parts.append(tube("collar", (0, 0, Lg * 0.32), (0, 0, Lg * 0.42), D * 1.12, n=20, tone=TRIM))
        parts.append(tube("muzzle", (0, 0, Lg * 0.82), (0, 0, Lg), Dm, Dm * 0.96, n=24))
        # the muzzle face: an outer ring, an inner ring, and ticks between them (Clint)
        parts.append(tube("inner_ring", (0, 0, Lg), (0, 0, Lg + 0.02), Dm * 0.8, n=24, tone=TRIM))
        for k in range(10):
            t = 2 * math.pi * k / 10 + math.pi / 10
            ux, uy = math.cos(t), math.sin(t)
            vx, vy = -uy, ux
            pts = []
            for r in (Dm * 0.405, Dm * 0.47):
                for wv in (-0.012, 0.012):
                    for z in (Lg, Lg + 0.015):
                        pts.append((ux * r + vx * wv, uy * r + vy * wv, z))
            parts.append(hull("tick", pts, tone=DARK))
        parts.append(tube("bore", (0, 0, Lg + 0.02), (0, 0, Lg + 0.03), Dm * 0.66, n=24, tone=DARK))
        # the fin: a triangle standing on the barrel's top, its point toward the elbow
        parts.append(hull("fin", [(-0.03, D * 0.45, Lg * 0.42), (0.03, D * 0.45, Lg * 0.42), (-0.03, D * 0.45, Lg * 0.8),
                                  (0.03, D * 0.45, Lg * 0.8), (-0.015, D * 0.45 + Dm * 0.42, Lg * 0.78), (0.015, D * 0.45 + Dm * 0.42, Lg * 0.78)]))
    else:
        parts.append(tube("housing", (0, 0, -hw * 0.1), (0, 0, Lg * 0.36), hw * 1.08, n=6))
        parts.append(tube("barrel", (0, 0, Lg * 0.35), (0, 0, Lg * 0.82), D * 1.08, n=6))
        parts.append(tube("muzzle", (0, 0, Lg * 0.82), (0, 0, Lg), Dm * 1.08, n=6))
        parts.append(tube("bore", (0, 0, Lg), (0, 0, Lg + 0.012), Dm * 0.7, n=6, tone=DARK))
    return parts, anchors, mounts


def fist(lod, p):
    """hand/fist (Commando): hanging from the wrist, knuckles forward. The back of the hand on top; a knuckle row; the curled
    fingers' middle segments make the FRONT face as four vertical blocks; their tips tucked under and back; the thumb wraps
    diagonally across the front of the fingers from the outer side. The wrist at the origin, the hand along -y."""
    S = p["size"]
    hi = lod == "high"
    anchors = {"wrist": [0.0, 0.0, 0.0]}
    mounts = [mount("hand.grip", "equipment", (0, -S * 0.7, S * 0.1), "+z", [0.4, 0.3, 0.6], ["club", "gun_grip"])]
    w, h, d = S * 0.7, S * 0.95, S * 0.66
    parts = []
    if hi:
        parts.append(cbox("back", (0, -h * 0.3, -d * 0.12), (w, h * 0.56, d * 0.72), ch=0.04))
        parts.append(cbox("knuckles", (0, -h * 0.5, d * 0.27), (w * 1.02, h * 0.16, d * 0.28), ch=0.03, tone=TRIM))
        fw = w / 4
        for k in range(4):
            x = (k - 1.5) * fw
            parts.append(cbox("finger_mid", (x, -h * 0.76, d * 0.3), (fw * 0.88, h * 0.4, d * 0.3), ch=0.02))
            parts.append(cbox("finger_tip", (x, -h * 0.93, d * 0.0), (fw * 0.86, h * 0.14, d * 0.34), ch=0.02))
        parts.append(cbox("palm", (0, -h * 0.68, -d * 0.18), (w * 0.94, h * 0.5, d * 0.5), ch=0.03))
        # the thumb: from the outer side, across the front of the fingers, down and in
        parts.append(hull("thumb", [(w * 0.5, -h * 0.42, d * 0.05), (w * 0.5, -h * 0.58, d * 0.05), (w * 0.56, -h * 0.42, d * 0.3),
                                    (w * 0.56, -h * 0.58, d * 0.3), (w * 0.0, -h * 0.84, d * 0.48), (w * 0.0, -h * 0.97, d * 0.48),
                                    (w * 0.12, -h * 0.84, d * 0.56), (w * 0.12, -h * 0.97, d * 0.56)]))
        parts.append(cbox("back_plate", (0, -h * 0.28, -d * 0.49), (w * 0.8, h * 0.42, 0.04), ch=0.012))
    else:
        parts.append(cbox("back", (0, -h * 0.3, -d * 0.12), (w, h * 0.56, d * 0.76)))
        parts.append(cbox("palm", (0, -h * 0.72, -d * 0.12), (w * 0.94, h * 0.5, d * 0.62)))
        parts.append(cbox("fingers", (0, -h * 0.72, d * 0.32), (w, h * 0.56, d * 0.34)))
    return parts, anchors, mounts


def dome_helmet(lod, p):
    """head/dome_helmet (Commando): a round helmet over a stepped skirt, a brim band round it, a dark visor slot across the
    face under the brim, a chin block and a knob on the side. The neck at the origin."""
    R, Hs = p["radius"], p["skirt"]
    hi = lod == "high"
    anchors = {"neck": [0.0, 0.0, 0.0]}
    mounts = [mount("head.side", "greeble", (R, Hs * 0.6, 0), "+x", [0.2, 0.3, 0.3], ["ear_cheek_pod", "searchlight"]),
              mount("head.top", "greeble", (0, Hs + R * 0.9, -R * 0.3), "+y", [0.1, 0.4, 0.1], ["antenna_whip"]),
              mount("head.front", "weapon", (0, Hs * 0.3, R), "+z", [0.3, 0.2, 0.2], ["laser", "mg"])]
    parts = []
    if hi:
        parts.append(dome("cap", (0, Hs, 0), (R, R * 0.92, R * 1.02), n=20, rings=6))
        parts.append(tube("brim", (0, Hs - 0.04, 0), (0, Hs + 0.06, 0), R * 2.12, n=20, tone=TRIM))
        parts.append(tube("skirt", (0, Hs * 0.2, 0), (0, Hs - 0.04, 0), R * 1.7, R * 1.96, n=20))
        # visor: a dark band across the front of the skirt
        vis = []
        for t in range(-4, 5):
            a = math.radians(t * 11)
            for y in (Hs * 0.5, Hs * 0.82):
                tt = (y - Hs * 0.2) / (Hs * 0.84)          # where y sits on the skirt (its radius grows upward)
                rr = (0.85 + 0.13 * tt) * R * math.cos(math.pi / 20) + 0.02
                vis.append((math.sin(a) * (rr + 0.015), y, math.cos(a) * (rr + 0.015)))
                vis.append((math.sin(a) * (rr - 0.04), y, math.cos(a) * (rr - 0.04)))
        parts.append(hull("visor", vis, tone=DARK))
        parts.append(cbox("chin", (0, Hs * 0.2, R * 0.6), (R * 0.7, Hs * 0.4, R * 0.5), ch=0.04))
        parts.append(tube("knob", (R * 0.9, Hs * 0.45, R * 0.35), (R * 1.08, Hs * 0.45, R * 0.35), R * 0.34, n=12))
        parts.append(tube("knob_face", (R * 1.08, Hs * 0.45, R * 0.35), (R * 1.1, Hs * 0.45, R * 0.35), R * 0.2, n=12, tone=DARK))
        parts.append(cbox("hazard", (R * 0.3, Hs + R * 0.62, R * 0.62), (R * 0.36, R * 0.24, 0.03), tone=DARK))
        parts.append(tube("neck", (0, 0, 0), (0, Hs * 0.22, 0), R * 0.9, R * 1.1, n=12))
    else:
        parts.append(dome("cap", (0, Hs, 0), (R * 1.08, R * 0.92, R * 1.08), n=8, rings=2))
        parts.append(tube("skirt", (0, 0, 0), (0, Hs, 0), R * 1.75, R * 2.16, n=8))
        parts.append(cbox("visor", (0, Hs * 0.66, R * 1.04), (R * 0.9, Hs * 0.3, 0.06), tone=DARK))
    return parts, anchors, mounts


def bubble_canopy(lod, p):
    """head/bubble_canopy (Javelin): a big low dome, wider than tall, sitting on a rim ring; a dark window band of framed
    panes across the front low on the dome; a spine rib front to back. The neck at the origin."""
    R, Hr = p["radius"], p["rise"]
    hi = lod == "high"
    anchors = {"neck": [0.0, 0.0, 0.0]}
    mounts = [mount("canopy.side", "greeble", (R, R * 0.2, R * 0.2), "+x", [0.2, 0.3, 0.3], ["dish", "searchlight"]),
              mount("canopy.top", "greeble", (0, Hr, -R * 0.3), "+y", [0.1, 0.3, 0.1], ["antenna_whip"])]
    parts = []
    base = R * 0.14
    if hi:
        parts.append(tube("rim", (0, 0, 0), (0, base, 0), R * 2.08, R * 2.12, n=24, tone=TRIM))
        parts.append(dome("bubble", (0, base, 0), (R, Hr, R * 1.05), n=24, rings=7))
        # window band: framed panes across the front, from about 20 to 50 degrees up
        for k in range(-3, 4):
            a0, a1 = math.radians(k * 16 - 7.2), math.radians(k * 16 + 7.2)
            pts = []
            for a in (a0, a1):
                for lat, grow in ((math.radians(5), 0.035), (math.radians(34), 0.035)):
                    rr = math.cos(lat)
                    y = base + Hr * math.sin(lat)
                    for g in (grow, -0.03):
                        pts.append((math.sin(a) * R * rr * (1 + g), y, math.cos(a) * R * 1.05 * rr * (1 + g)))
            parts.append(hull("pane", pts, tone=DARK))
        parts.append(hull("spine", [(-0.035, base + Hr * 0.98, -R * 0.3), (0.035, base + Hr * 0.98, -R * 0.3),
                                    (-0.035, base + Hr * 0.88, R * 0.5), (0.035, base + Hr * 0.88, R * 0.5),
                                    (-0.035, base + Hr * 1.03, 0.0), (0.035, base + Hr * 1.03, 0.0)], tone=TRIM))
    else:
        parts.append(tube("rim", (0, 0, 0), (0, base, 0), R * 2.2, n=8))
        parts.append(dome("bubble", (0, base, 0), (R * 1.06, Hr, R * 1.1), n=8, rings=2))
        parts.append(hull("window", [(-R * 0.5, base + Hr * 0.06, R * 1.12), (R * 0.5, base + Hr * 0.06, R * 1.12),
                                     (-R * 0.4, base + Hr * 0.5, R * 0.98), (R * 0.4, base + Hr * 0.5, R * 0.98),
                                     (-R * 0.5, base + Hr * 0.06, R * 0.95), (R * 0.5, base + Hr * 0.06, R * 0.95)], tone=DARK))
    return parts, anchors, mounts


GENERATORS = {"slab_boot": slab_boot, "tapered_slab_shin": tapered_slab_shin, "tapered_slab_thigh": tapered_slab_thigh,
              "boxy_chest": boxy_chest, "shoulder_drum": shoulder_drum, "launcher_bay": launcher_bay, "fist_arm": fist_arm,
              "barrel_arm": barrel_arm, "fist": fist, "dome_helmet": dome_helmet, "bubble_canopy": bubble_canopy}


# ---------------------------------------------------------------- the library
def library():
    with open(LIBRARY) as f:
        return json.load(f)


def _merge_flat_pairs(solid, cos_min=0.998):
    """Join two triangles that share an edge and lie (nearly) in one plane into one quad, so a tapered face that is not quite
    flat shows as one panel, not two with a seam. Drawing only: the triangle count still counts the triangles."""
    verts, faces = solid["verts"], [list(f) for f in solid["faces"]]
    normal = lambda f: L._face_normal(verts, f, solid["centroid"])
    done = True
    while done:
        done = False
        tris = [i for i, f in enumerate(faces) if len(f) == 3]
        for ai in range(len(tris)):
            for bi in range(ai + 1, len(tris)):
                fa, fb = faces[tris[ai]], faces[tris[bi]]
                shared = set(fa) & set(fb)
                if len(shared) != 2 or L._dot(normal(fa), normal(fb)) < cos_min:
                    continue
                a_only = (set(fa) - shared).pop()
                b_only = (set(fb) - shared).pop()
                k = fa.index(a_only)                     # walk fa from its own vertex, put b's vertex between the shared two
                quad = [fa[k], fa[(k + 1) % 3], b_only, fa[(k + 2) % 3]]
                faces = [f for i, f in enumerate(faces) if i not in (tris[ai], tris[bi])] + [quad]
                done = True
                break
            if done:
                break
    solid["faces"] = faces


def generate(block_id, lod, params=None, lib=None):
    """{'parts', 'anchors', 'mounts', 'tris'} for one block at 'high' or 'low'."""
    lib = lib or library()
    rec = lib["blocks"][block_id]
    p = dict(rec["params"])
    p.update(params or {})
    _seq[0] = 0
    parts, anchors, mounts = GENERATORS[rec["generator"]](lod, p)
    solids = L.expand_parts({"parts": parts})
    tris = sum(s["tris"] for s in solids)
    for sol in solids:
        _merge_flat_pairs(sol)
    return {"parts": parts, "solids": solids, "anchors": anchors, "mounts": mounts, "tris": tris}


# ---------------------------------------------------------------- rendering
def camera(yaw, pitch, mirror=False):
    """A view turned `yaw` degrees about the up axis (positive turns the block's left side, +x, toward the viewer) and
    looking down `pitch` degrees. mirror=True shows the right-hand copy (x flipped), for a drawing of a right-side part."""
    ya, pa = math.radians(yaw), math.radians(pitch)

    def f(pt):
        x, y, z = pt
        if mirror:
            x = -x
        sx = x * math.cos(ya) - z * math.sin(ya)
        zz = x * math.sin(ya) + z * math.cos(ya)
        sy = y * math.cos(pa) - zz * math.sin(pa)
        d = y * math.sin(pa) + zz * math.cos(pa)
        return (sx, sy, d)
    return f


# front: the block's left (+x) on screen right, as a 'Mech facing the viewer; side: seen from its left; top: forward is up
ORTHO = {"front": camera(0, 0), "side": camera(90, 0), "top": lambda q: (-q[0], q[2], q[1])}


def _fit(solids, fmap, size, pad=0.08):
    pts = [fmap(v) for s in solids for v in s["verts"]]
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    scale = min(size[0] * (1 - 2 * pad) / max(x1 - x0, 1e-6), size[1] * (1 - 2 * pad) / max(y1 - y0, 1e-6))
    return scale, (size[0] / 2 - (x0 + x1) / 2 * scale, size[1] / 2 - (y0 + y1) / 2 * scale)


def render(solids, fmap, size, fit_solids=None, ss=2):
    """A shaded picture of the solids through view function fmap, scaled to fit `fit_solids` (default: the same solids).
    Same shading as lowpoly_ref.render_view, but with a DEPTH BUFFER: each pixel shows the nearest face, so small parts
    standing on a big part (tube mouths on a panel) are never hidden by a sorting mistake (lowpoly_ref's face-by-face sort
    hid them). Outlines are drawn where neighbouring pixels belong to different faces, so they follow what is visible."""
    import numpy as np
    from PIL import Image
    scale, origin = _fit(fit_solids or solids, fmap, size)
    w, h = size[0] * ss, size[1] * ss
    zbuf = np.full((h, w), -np.inf)
    ids = np.full((h, w), -1, dtype=np.int32)
    shade_of = [1.0]
    normal_of = [(0.0, 0.0, 0.0)]
    solid_of = [-1]
    light = L._unit((-0.45, 0.75, 0.5))
    zero = fmap((0, 0, 0))
    ys, xs = np.mgrid[0:h, 0:w]
    xs = xs + 0.5
    ys = ys + 0.5
    for si, sol in enumerate(solids):
        tone = L._tone(sol)
        for f in sol["faces"]:
            n_world = L._face_normal(sol["verts"], f, sol["centroid"])
            n_cam = L._sub(fmap(n_world), zero)
            if n_cam[2] <= -0.02:
                continue
            fid = len(shade_of)
            shade_of.append(tone * (0.62 + 0.38 * max(0.0, L._dot(L._unit(n_cam), light))))
            normal_of.append(n_world)
            solid_of.append(si)
            pts = [fmap(sol["verts"][i]) for i in f]
            px = [((origin[0] + q[0] * scale) * ss, h - (origin[1] + q[1] * scale) * ss, q[2]) for q in pts]
            for k in range(1, len(px) - 1):                       # fan into triangles, one face id for all of them
                (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = px[0], px[k], px[k + 1]
                det = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
                if abs(det) < 1e-9:
                    continue
                c0, c1 = int(max(0, min(x0, x1, x2) - 1)), int(min(w, max(x0, x1, x2) + 2))
                r0, r1 = int(max(0, min(y0, y1, y2) - 1)), int(min(h, max(y0, y1, y2) + 2))
                if c0 >= c1 or r0 >= r1:
                    continue
                X, Y = xs[r0:r1, c0:c1], ys[r0:r1, c0:c1]
                l0 = ((y1 - y2) * (X - x2) + (x2 - x1) * (Y - y2)) / det
                l1 = ((y2 - y0) * (X - x2) + (x0 - x2) * (Y - y2)) / det
                l2 = 1 - l0 - l1
                inside = (l0 >= -1e-6) & (l1 >= -1e-6) & (l2 >= -1e-6)
                z = l0 * z0 + l1 * z1 + l2 * z2
                zb = zbuf[r0:r1, c0:c1]
                win = inside & (z > zb + 1e-6)
                zb[win] = z[win]
                ids[r0:r1, c0:c1][win] = fid
    shades = np.array(shade_of)
    grey = np.where(ids >= 0, shades[np.maximum(ids, 0)], 1.0)
    # an outline where two neighbouring pixels show different faces AND the change is a real edge: the background, another
    # part, or a crease sharper than CREASE_DEG (so a faceted dome or drum reads smooth, as the drawings show them)
    normals = np.array(normal_of)
    owner = np.array(solid_of)
    cos_crease = math.cos(math.radians(CREASE_DEG))

    def is_edge(a, b):
        diff = a != b
        bg = (a < 0) | (b < 0)
        other = owner[np.maximum(a, 0)] != owner[np.maximum(b, 0)]
        crease = (normals[np.maximum(a, 0)] * normals[np.maximum(b, 0)]).sum(axis=-1) < cos_crease
        return diff & (bg | other | crease)
    edge = np.zeros((h, w), dtype=bool)
    edge[:, 1:] |= is_edge(ids[:, 1:], ids[:, :-1])
    edge[1:, :] |= is_edge(ids[1:, :], ids[:-1, :])
    edge[:, :-1] |= edge[:, 1:].copy()                            # thicken to about ss + 1 pixels
    edge[:-1, :] |= edge[1:, :].copy()
    grey[edge] = 0.0
    img = Image.fromarray((np.clip(grey, 0, 1) * 255).astype(np.uint8), "L").convert("RGB")
    return img.resize(size, Image.LANCZOS)


def silhouette(solids, fmap, size, fit_solids):
    """The black shape (a set of pixels) of the solids, framed by fit_solids."""
    from PIL import Image, ImageDraw
    scale, origin = _fit(fit_solids, fmap, size)
    img = Image.new("1", size, 0)
    dr = ImageDraw.Draw(img)
    for s in solids:
        for f in s["faces"]:
            pts = [fmap(s["verts"][i]) for i in f]
            dr.polygon([(origin[0] + q[0] * scale, size[1] - (origin[1] + q[1] * scale)) for q in pts], fill=1)
    return img


def outline_match(high, low, size=(240, 240)):
    """Intersection over union of LOW's and HIGH's black shapes, per orthographic view."""
    out = {}
    for name, fmap in ORTHO.items():
        a = silhouette(high["solids"], fmap, size, high["solids"]).convert("L").tobytes()
        b = silhouette(low["solids"], fmap, size, high["solids"]).convert("L").tobytes()
        inter = sum(1 for u, v in zip(a, b) if u and v)
        union = sum(1 for u, v in zip(a, b) if u or v)
        out[name] = round(inter / union, 3) if union else 1.0
    return out


def reference_crop(rec):
    from PIL import Image
    ref = rec["reference"]
    img = Image.open(os.path.join(L.REF, ref["original"])).convert("RGB")
    return img.crop(tuple(ref["box"]))


def _sheet_name(block_id):
    return block_id.replace("/", "__") + ".png"


def make_sheet(block_id, lib):
    """reference | HIGH at the drawing's angle | LOW the same, over HIGH and LOW front / side / top, with the numbers."""
    from PIL import Image, ImageDraw, ImageFont
    rec = lib["blocks"][block_id]
    high, low = generate(block_id, "high", lib=lib), generate(block_id, "low", lib=lib)
    cam = rec["camera"]
    fmap = camera(cam["yaw"], cam["pitch"], cam.get("mirror", False))
    big = (380, 380)
    crop = reference_crop(rec)
    k = min(big[0] / crop.width, big[1] / crop.height)
    crop = crop.resize((max(1, int(crop.width * k)), max(1, int(crop.height * k))), Image.LANCZOS)
    small = (186, 186)
    match = outline_match(high, low)
    try:
        font, tiny = ImageFont.load_default(size=17), ImageFont.load_default(size=13)
    except TypeError:
        font = tiny = ImageFont.load_default()
    W = 3 * big[0] + 40
    sheet = Image.new("RGB", (W, 40 + big[1] + 30 + 2 * (small[1] + 22) + 12), "white")
    dr = ImageDraw.Draw(sheet)
    dr.text((10, 10), "%s   |   HIGH %d triangles, LOW %d   |   reference: %s" % (
        block_id, high["tris"], low["tris"], rec["reference"]["unit"]), fill="black", font=font)
    y = 40
    sheet.paste(crop, (10 + (big[0] - crop.width) // 2, y + (big[1] - crop.height) // 2))
    sheet.paste(render(high["solids"], fmap, big), (20 + big[0], y))
    sheet.paste(render(low["solids"], fmap, big, fit_solids=high["solids"]), (30 + 2 * big[0], y))
    for i, lab in enumerate(("REFERENCE (TRO 3025 drawing, crop)", "HIGH, at the drawing's angle", "LOW, the same")):
        dr.text((10 + i * (big[0] + 10), y + big[1] + 6), lab, fill="black", font=tiny)
    y += big[1] + 30
    for row, (name, blk) in enumerate((("HIGH", high), ("LOW", low))):
        for j, (vname, vmap) in enumerate(ORTHO.items()):
            x = 10 + j * (small[0] + 8)
            sheet.paste(render(blk["solids"], vmap, small, fit_solids=high["solids"]), (x, y))
            dr.text((x + 4, y + 4), "%s %s" % (name, vname), fill="black", font=tiny)
        y += small[1] + 22
    tx = 10 + 3 * (small[0] + 8) + 10
    ty = 40 + big[1] + 40
    lines = ["outline match LOW v HIGH (IoU): " + ", ".join("%s %.2f" % kv for kv in match.items()),
             "anchors: " + ", ".join(high["anchors"]), "mounts: " + ", ".join(m["id"] for m in high["mounts"]), ""]
    v = rec.get("verdict") or {}
    lines.append("VERDICT: " + (v.get("call") or "not judged yet"))
    import textwrap
    for para in (v.get("why") or "").split("\n"):
        lines += textwrap.wrap(para, 52)
    for i, line in enumerate(lines):
        dr.text((tx, ty + i * 17), line, fill="black", font=tiny)
    os.makedirs(SHEETS, exist_ok=True)
    path = os.path.join(SHEETS, _sheet_name(block_id))
    sheet.save(path)
    return path, high, low, match


def check(lib):
    """(errors, rows) for every block."""
    from PIL import Image
    errors, rows = [], []
    for bid, rec in lib["blocks"].items():
        try:
            high, low = generate(bid, "high", lib=lib), generate(bid, "low", lib=lib)
        except Exception as e:                           # noqa: BLE001 - report and go on
            errors.append("%s: does not generate (%s)" % (bid, e))
            continue
        if high["anchors"] != low["anchors"]:
            errors.append("%s: anchors differ between HIGH and LOW" % bid)
        if high["mounts"] != low["mounts"]:
            errors.append("%s: mounts differ between HIGH and LOW" % bid)
        if low["tris"] > rec["low_budget"]:
            errors.append("%s: LOW has %d triangles, budget %d" % (bid, low["tris"], rec["low_budget"]))
        if high["tris"] > HIGH_LIMIT:
            errors.append("%s: HIGH has %d triangles, limit %d" % (bid, high["tris"], HIGH_LIMIT))
        match = outline_match(high, low)
        for view, iou in match.items():
            if iou < OUTLINE_MIN:
                errors.append("%s: LOW's %s outline matches HIGH's only %.2f (minimum %.2f)" % (bid, view, iou, OUTLINE_MIN))
        ref = rec["reference"]
        path = os.path.join(L.REF, ref["original"])
        if not os.path.exists(path):
            errors.append("%s: reference picture %s missing" % (bid, ref["original"]))
        else:
            w, h = Image.open(path).size
            x0, y0, x1, y1 = ref["box"]
            if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
                errors.append("%s: crop box outside the picture" % bid)
        if not (rec.get("verdict") or {}).get("call"):
            errors.append("%s: no verdict recorded" % bid)
        rows.append((bid, high["tris"], low["tris"], match))
    return errors, rows


def page(lib, out):
    """One self-contained HTML page: each block's sheet and verdict."""
    import html
    items = []
    for bid, rec in lib["blocks"].items():
        path = os.path.join(SHEETS, _sheet_name(bid))
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        v = rec.get("verdict") or {}
        items.append('<section><h2>%s</h2><p class="v %s"><b>%s</b> %s</p><p class="r">Reference: %s, crop %s of <code>%s</code>: %s</p>'
                     '<img alt="%s" src="data:image/png;base64,%s"></section>' % (
                         html.escape(bid), "ok" if (v.get("call") or "").startswith("close enough") else "no",
                         html.escape(v.get("call") or "not judged"), html.escape(v.get("why") or ""),
                         html.escape(rec["reference"]["unit"]), rec["reference"]["box"], html.escape(rec["reference"]["original"]),
                         html.escape(rec["reference"]["shows"]), html.escape(bid), data))
    with open(out, "w") as f:
        f.write(PAGE % "\n".join(items))


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Block Library Pass One</title><style>
:root{--bg:#fafaf8;--fg:#1d1d1b;--mut:#666;--ok:#2f6f3e;--no:#9a3b1c;--card:#fff;--line:#ddd}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#1b1b1a;--fg:#ecece8;--mut:#aaa;--ok:#7fc28f;--no:#e39a7a;--card:#262624;--line:#3a3a38}}
:root[data-theme="dark"]{--bg:#1b1b1a;--fg:#ecece8;--mut:#aaa;--ok:#7fc28f;--no:#e39a7a;--card:#262624;--line:#3a3a38}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
main{max-width:1240px;margin:0 auto;padding:16px}
section{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 14px;margin:14px 0}
h1{font-size:22px}h2{font-size:17px;margin:0 0 4px}img{max-width:100%%;height:auto;display:block;background:#fff}
.v.ok b{color:var(--ok)}.v.no b{color:var(--no)}.r{color:var(--mut);font-size:13px}code{font-size:12px}
</style></head><body><main><h1>Block library, first pass: the common dozen</h1>
<p>Each block shows the exact piece of the TRO 3025 drawing it was built from (left), the block at HIGH detail turned to the
drawing's angle, the LOW reference level the same, and both from the front, side and top. The verdict is Claude's comparison
with the drawing. Private: the drawings are Catalyst artwork.</p>
%s</main></body></html>
"""


def main(argv):
    lib = library()
    if not argv or argv[0] not in ("sheets", "check", "page"):
        print(__doc__)
        return 2
    if argv[0] == "sheets":
        ids = argv[1:] or list(lib["blocks"])
        for bid in ids:
            path, high, low, match = make_sheet(bid, lib)
            print("%-36s HIGH %4d  LOW %3d  outline %s  -> %s" % (bid, high["tris"], low["tris"], match, os.path.relpath(path, L.ROOT)))
        return 0
    if argv[0] == "check":
        errors, rows = check(lib)
        for bid, th, tl, m in rows:
            print("%-36s HIGH %4d  LOW %3d  outline %s" % (bid, th, tl, m))
        for e in errors:
            print("FAIL", e)
        print("%s: %d blocks" % ("FAIL" if errors else "OK", len(rows)))
        return 1 if errors else 0
    page(lib, argv[1] if len(argv) > 1 else os.path.join(BLOCKS, "blocks.html"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
