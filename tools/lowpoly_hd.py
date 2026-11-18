#!/usr/bin/env python3
"""HD reference models: the high-detail versions that the low-poly models are simplified from later (Claude, 2026-11-18).

Daniel, 2026-11-18: "Using the 5 fold view of the catapult, build a model that matches its appearance. For our purposes the art
is accurate enough, though you may need to compensate for it being art and not a technical drawing." Then: "Don't worry about
polygon count. This will be the HD version that gets simplified later."

Each builder writes reference_art/models_hd/<unit>.json in tools/lowpoly_ref.py's model format (parts of kind box, wedge, bar,
tube, hull, dome; "mirror" authors the left side and copies it to the right), with "detail": "hd" so the 800-triangle budget does
not apply. Every other check still does: the record sheet's weapons and jump-jet locations, the required assemblies, the feet on
the ground (`python -I tools/lowpoly_ref.py check reference_art/models_hd/*.json`).

    python -I tools/lowpoly_hd.py            # build every HD model and render its sheet into reference_art/sheets/<unit> HD.png

MEASUREMENTS. Read off a grid laid over the AI five-view sheet (reference_art/ai_sheets/Catapult CPLT-C1/batch2_1.webp). Units:
ground to the body's top = 10. Front and top views: 10/330 per pixel; the side view is drawn ~10 % taller: 10/362 per pixel,
z = 0 at the hip disc (side x = 179), forward = +z. +x is the 'Mech's LEFT. PRIVATE (reference_art/).
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lowpoly_ref as L  # noqa: E402

HD_DIR = os.path.join(L.REF, "models_hd")
LEG_SPLAY = 5.0          # degrees: the legs turn outward about the hips (the front view)
DARK, TRIM, PLATE, JOINT, METAL = 0.22, 0.97, 0.88, 0.78, 0.6


def rnd(v):
    return [round(x, 4) for x in v]


class Model:
    def __init__(self):
        self.parts = []
        self.n = 0

    def add(self, kind, name, assembly, tone=None, role=None, mirror=False, **kw):
        self.n += 1
        p = {"id": "%s_%d" % (name, self.n), "assembly": assembly, "kind": kind}
        for k, v in kw.items():
            if k == "pts":
                p[k] = [rnd(q) for q in v]
            elif isinstance(v, (list, tuple)):
                p[k] = rnd(v)
            else:
                p[k] = v
        if tone is not None:
            p["tone"] = tone
        if role:
            p["role"] = role
        if mirror:
            p["mirror"] = True
        self.parts.append(p)

    def tube(self, name, asm, a, b, d0, d1=None, n=24, **kw):
        self.add("tube", name, asm, a=a, b=b, w0=[d0, d0], w1=[d1 or d0, d1 or d0], n=n, **kw)

    def hull(self, name, asm, pts, **kw):
        self.add("hull", name, asm, pts=pts, **kw)

    def box(self, name, asm, c, s, **kw):
        self.add("box", name, asm, c=c, s=s, **kw)


def bevel_box(c, s, ch):
    """The corner points of a box (centre c, size s) with every edge bevelled by ch (Daniel, 2026-11-18: the art's bevelling is
    more pronounced than a plain box)."""
    hx, hy, hz = s[0] / 2, s[1] / 2, s[2] / 2
    ch = min(ch, hx * 0.45, hy * 0.45, hz * 0.45)
    pts = []
    for ax, ay, az in ((hx, hy - ch, hz - ch), (hx - ch, hy, hz - ch), (hx - ch, hy - ch, hz)):
        for i in (-1, 1):
            for j in (-1, 1):
                for k in (-1, 1):
                    pts.append((c[0] + i * ax, c[1] + j * ay, c[2] + k * az))
    return pts


def rounded_section(z, y_top, y_bot, w_top, w_mid, w_bot, n=10):
    """A rounded cross-section at z: an egg-shaped ring of n*2 points between y_bot and y_top, widest (w_mid) a little below the
    middle, w_top across the top, w_bot across the bottom (half-widths)."""
    pts = []
    cy, ry = (y_top + y_bot) / 2, (y_top - y_bot) / 2
    for k in range(2 * n):
        t = 2 * math.pi * k / (2 * n)
        s, c = math.sin(t), math.cos(t)              # s = +1 at the top
        w = w_mid + (w_top - w_mid) * max(0.0, s) ** 1.5 + (w_bot - w_mid) * max(0.0, -s) ** 1.5
        pts.append((w * c, cy + ry * s, z))
    return pts


def section_at(secs, z):
    """The body's section parameters interpolated at z (secs sorted nose first, z falling)."""
    for a, b in zip(secs, secs[1:]):
        if b[0] <= z <= a[0]:
            t = (a[0] - z) / (a[0] - b[0])
            return [a[i] + (b[i] - a[i]) * t for i in range(1, 6)]
    raise ValueError(z)


def surface_point(secs, z, theta, grow=0.0):
    """A point on the body's rounded surface at z and angle theta (pi/2 = the top), pushed out by `grow` from the section's middle."""
    yt, yb, wt, wm, wb = section_at(secs, z)
    cy, ry = (yt + yb) / 2, (yt - yb) / 2
    s_, c_ = math.sin(theta), math.cos(theta)
    w = wm + (wt - wm) * max(0.0, s_) ** 1.5 + (wb - wm) * max(0.0, -s_) ** 1.5
    x, y = w * c_, cy + ry * s_
    n = math.hypot(x, y - cy) or 1.0
    return (x + grow * x / n, y + grow * (y - cy) / n, z)


def conformal_glass(m, secs, z_cuts, theta_cuts, gap, name="pane", role_first=None):
    """COCKPIT RULE, WRAP (Daniel, 2026-11-18: "Cockpits need rules on how to wrap or cut into structure"): the glazing is a skin on
    the host's OWN surface, a hair proud of it, cut into panes by frame gaps along the given z and angle cuts. Each pane is a thin
    shell (outer + inner points), never a flat plate laid across a curve."""
    zs = [(z0 - gap / 2, z1 + gap / 2) for z0, z1 in zip(z_cuts, z_cuts[1:])]          # z falls toward the back: z0 > z1
    ts = [(t0 + gap / 3, t1 - gap / 3) for t0, t1 in zip(theta_cuts, theta_cuts[1:])]
    wrap_glass(m, lambda z, t, g: surface_point(secs, z, t, g), zs, ts, name=name, role_first=role_first)


def wrap_glass(m, surface, u_spans, v_spans, name="pane", role_first="canopy", asm="head", grow=(0.035, -0.01)):
    """HD BLOCK cockpit/wrap_glass: glazing WRAPPED on any host surface (`surface(u, v, grow)` -> a point on it, pushed out by grow):
    one pane per (u span, v span), each a thin shell sampled 3 x 3 across its span, a hair proud of the host. The frame gaps are the
    spaces between the spans. The Catapult's nose (u = z, v = angle round the body) and the Commando's visor (u = latitude, v =
    longitude on its dome) are the same block."""
    first = True
    for ua, ub in u_spans:
        for va, vb in v_spans:
            pts = []
            for u in (ua, (ua + ub) / 2, ub):
                for v in (va, (va + vb) / 2, vb):
                    for g in grow:
                        pts.append(surface(u, v, g))
            m.hull(name, asm, pts, tone=0.26, role=role_first if first else None)
            first = False


def centre_of_mass(parts):
    """Volume centroid of all solids (uniform density: a first estimate, good enough to aim the jump jets)."""
    tv, tc = 0.0, [0.0, 0.0, 0.0]
    for sol in L.expand_parts({"parts": parts}):
        vs, c = sol["verts"], sol["centroid"]
        for f in sol["faces"]:
            for k in range(1, len(f) - 1):
                a, b, d = vs[f[0]], vs[f[k]], vs[f[k + 1]]
                p = [a[i] - c[i] for i in range(3)]
                q = [b[i] - c[i] for i in range(3)]
                r = [d[i] - c[i] for i in range(3)]
                v = abs(p[0] * (q[1] * r[2] - q[2] * r[1]) - p[1] * (q[0] * r[2] - q[2] * r[0]) + p[2] * (q[0] * r[1] - q[1] * r[0])) / 6
                tv += v
                for i in range(3):
                    tc[i] += v * (c[i] + (p[i] + q[i] + r[i]) / 4)
    return [round(x / tv, 3) for x in tc]


def joint_cover(m, name, asm, centre, x0, r, sides=6, roll=0.0, thick=0.11, ky=1.0, kz=1.0, tone=None, mirror=True):
    """An ARMOUR COVER over a joint's outer face (Daniel, 2026-11-18: "All the circular joints start to look the same from the side.
    Might be worth putting artistic covers over some of them"): a chamfered plate, `sides`-sided (6 a hexagon, 5 a guard with a
    point), stretched by ky / kz, standing on the joint's outer end at x0 (+x outward; mirrored for the right). It turns with the
    joint's child, as a knee guard does."""
    pts = []
    for k in range(sides):
        th = math.radians(roll) + 2 * math.pi * k / sides
        for x, rr in ((x0 - 0.01, r), (x0 + thick, r * 0.78)):
            pts.append((x, centre[1] + rr * math.sin(th) * ky, centre[2] + rr * math.cos(th) * kz))
    m.hull(name, asm, pts, tone=PLATE if tone is None else tone, mirror=mirror)
    m.tube(name + "_boss", asm, (x0 + thick - 0.01, centre[1], centre[2]), (x0 + thick + 0.04, centre[1], centre[2]), r * 0.3, n=sides * 2,
           tone=0.7, mirror=mirror)


def conformal_panel(m, secs, z0, z1, t0, t1, asm, grow=0.05, tone=None, mirror=True):
    """A raised armour PANEL on a body's own surface (between sections z0 > z1 and angles t0 < t1), standing `grow` proud: the
    paneling that keeps a large surface from reading as one flat sheet (Daniel, 2026-11-18)."""
    pts = []
    for z in (z0, (z0 + z1) / 2, z1):
        for t in (t0, (t0 + t1) / 2, t1):
            pts.append(surface_point(secs, z, t, grow))
            pts.append(surface_point(secs, z, t, -0.02))
    m.hull("panel", asm, pts, tone=PLATE if tone is None else tone, mirror=mirror)


def bay_grid(m, asm, centre, w, h, rows, cols, role=None, depth=0.3, proud=0.15, name="bay", tone=None, mirror=False):
    """A WEAPON BAY sized to its MOUNT (Daniel, 2026-11-18: "This would involve changing the size of weapon blocks to make them
    fit"): a plate w x h set into a flat front face (its middle at `centre`, on the face; it stands `proud` out), with rows x cols
    tubes flush in its face, as big as the plate allows; the line-of-fire hole starts just in front of it."""
    cx, cy, zf = centre
    zc = zf + proud - depth / 2
    m.hull(name, asm, bevel_box((cx, cy, zc), (w, h, depth), min(0.08, w * 0.12, h * 0.12)), tone=PLATE if tone is None else tone,
           role=role, mirror=mirror,
           **({"fire": {"from": [cx, cy, zf + proud + 0.04], "dir": [0, 0, 1], "r": round(min(w, h) / 2 * 0.95, 3)}} if role else {}))
    d = min(w / cols, h / rows) * 0.78
    front = zf + proud
    for c in range(cols):
        for r_ in range(rows):
            x = cx + (c - (cols - 1) / 2) * (w * 0.86 / cols)
            y = cy + ((rows - 1) / 2 - r_) * (h * 0.86 / rows)
            m.tube(name + "_tube", asm, (x, y, front - 0.12), (x, y, front), d, n=12, tone=0.7, mirror=mirror)
            m.tube(name + "_bore", asm, (x, y, front), (x, y, front + 0.015), d * 0.63, n=12, tone=0.1, mirror=mirror)


def torso_stack(m, levels, ch=0.24, tone=0.88, name="chest"):
    """HD BLOCK torso/chamfered_stack (the Commando's upright chest): horizontal sections, each (y, half-width, front, back) with its
    corners chamfered by ch, hulled pair by pair (top first). Its surface is the sections themselves: flat front faces for mounts."""
    for (y0, w0, f0, b0), (y1, w1, f1, b1) in zip(levels, levels[1:]):
        m.hull(name, "torso", bevel_ring(y0, w0, f0, b0, ch) + bevel_ring(y1, w1, f1, b1, ch), tone=tone)


def slung_body(m, secs, tone=0.9, fire_cut_ok=True):
    """HD BLOCK body/slung_teardrop (the Catapult's): rounded cross-sections along z (nose first), each (z, y_top, y_bottom,
    half-widths across the top, at the widest, across the bottom), one convex slice between two. Its surface function is
    `surface_point(secs, z, angle, grow)` (the wrapped cockpit, the jet vents and the panels use it)."""
    for (z0, t0, b0, a0, m0, c0), (z1, t1, b1, a1, m1, c1) in zip(secs, secs[1:]):
        m.hull("body", "torso", rounded_section(z0, t0, b0, a0, m0, c0) + rounded_section(z1, t1, b1, a1, m1, c1), tone=tone,
               **({"fire_cut_ok": True} if fire_cut_ok else {}))


def helmet(m, hc, hr, neck_base, skirt_bottom, skirt_back_drop, ear_side=1):
    """HD BLOCK head/helmet (the Commando's; Daniel, 2026-11-18: "kind of a helmet that covers the back of the neck"): a faceted dome
    (centre hc, radii hr), a ribbed neck from neck_base, a SKIRT round the sides and back reaching down to skirt_bottom (lower at the
    back by skirt_back_drop; it must stop short of the torso: "a bit of a gap ... so that the head can rotate"), a brim, a wrapped
    visor, a brow, a crest, a jaw with a grille, a round fitting on one side (ear_side +1: the left). Sizes are the Commando's,
    measured from the dome centre."""
    cy, cz = hc[1], hc[2]
    for k in range(4):                                              # a ribbed neck (mostly under the skirt)
        m.tube("neck", "head", (0, neck_base + k * 0.13, cz - 0.13), (0, neck_base + 0.1 + k * 0.13, cz - 0.13), 1.0 - 0.04 * k, n=8,
               roll=22.5, tone=JOINT)
    m.tube("neck_core", "head", (0, neck_base, cz - 0.13), (0, neck_base + 0.6, cz - 0.13), 0.82, n=8, roll=22.5, tone=DARK)
    m.add("dome", "dome", "head", c=hc, r=hr, n=16, rings=5, half="top", tone=0.9)
    # the SKIRT: one convex piece per 22.5 degrees from the face's right edge round the back to its left edge; it reaches lower at
    # the back (over the neck) than at the cheeks, and flares a little
    step = 22.5
    lon = 135.0
    while lon < 405.0 - 1e-6:
        piece = []
        for lo in (lon, lon + step):
            back = (1 - math.sin(math.radians(lo))) / 2              # 0 at the face, 1 straight behind
            yb = skirt_bottom - skirt_back_drop * back
            for g in (-0.06, 0.05):
                piece.append(dome_point(hc, hr, 0, lo, g))
                b_ = dome_point(hc, hr, 0, lo, g + 0.1)
                piece.append((b_[0], yb, b_[2]))
        m.hull("helmet_skirt", "head", piece, tone=0.86)
        lon += step
    m.tube("brim", "head", (0, cy - 0.03, cz), (0, cy + 0.05, cz), 2 * hr[0] + 0.14, 2 * hr[0] + 0.08, n=16, tone=TRIM)
    # the VISOR (cockpit rule, WRAP): panes on the dome's own surface, a band across its front (the TRO's slit; the sheet's bands)
    wrap_glass(m, lambda la, lo, g: dome_point(hc, hr, la, lo, g), [(12, 32)], [(52, 76), (78, 102), (104, 128)], name="visor")
    m.hull("brow", "head", [dome_point(hc, hr, la, lo, g) for la in (35, 42) for lo in (48, 70, 90, 110, 132) for g in (0.09, -0.01)],
           tone=TRIM)
    # the crest: a low ridge from the brow over the top to the back, in short segments that follow the dome
    path = [(46, 90), (62, 90), (78, 90), (90, 90), (78, 270), (62, 270), (46, 270), (30, 270)]
    for (la0, lo0), (la1, lo1) in zip(path, path[1:]):
        m.hull("crest", "head", [dome_point(hc, hr, la, lo + dl, g) for la, lo in ((la0, lo0), (la1, lo1)) for dl in (-6, 6)
                                 for g in (0.06, -0.03)], tone=0.8)
    # the face below the visor: a jaw tapering forward (stopping short of the torso, as the skirt), a grille, a round fitting
    jb = skirt_bottom - 0.06
    m.hull("jaw", "head", [(sx * 0.62, cy - 0.03, z) for sx in (-1, 1) for z in (cz - 0.35, cz + 0.7)] +
           [(sx * 0.5, jb, z) for sx in (-1, 1) for z in (cz - 0.3, cz + 0.5)] +
           [(sx * 0.3, jb + 0.02, cz + 0.8) for sx in (-1, 1)] + [(sx * 0.4, cy - 0.1, cz + 0.9) for sx in (-1, 1)], tone=0.8)
    for k in range(4):
        m.box("grille", "head", (0, jb + 0.06 + k * 0.05, cz + 0.81 - k * 0.025), (0.46, 0.03, 0.06), tone=DARK)
    ex = ear_side
    m.tube("ear", "head", (ex * 0.5, cy - 0.18, cz + 0.2), (ex * 0.66, cy - 0.18, cz + 0.2), 0.3, n=12, tone=JOINT)
    m.tube("ear_hub", "head", (ex * 0.66, cy - 0.18, cz + 0.2), (ex * 0.7, cy - 0.18, cz + 0.2), 0.15, n=12, tone=DARK)


def pelvis_briefs(m, belt_y, belt_w, belt_d, top, point, crotch, plate_top, plate_bottom, vents=3):
    """HD BLOCK pelvis/briefs (the Commando's; Daniel: "it looks like an actual pelvis or 'Briefs' underwear"): a BELT band (middle
    at belt_y, belt_w wide, belt_d deep); under it one straight V, from `top` (y, half-width, front, back) down to `point`, its sloped
    sides the leg openings; a small crotch block under the point (`crotch`: top section, bottom section); a raised plate down the
    front and a seat plate behind (plate_top / plate_bottom: (y, half-width, z, z proud)); vents low on the front plate."""
    m.hull("belt", "pelvis", bevel_box((0, belt_y, 0.0), (belt_w, 0.36, belt_d), 0.1), tone=0.8)
    m.hull("briefs", "pelvis", bevel_ring(*top, 0.16) + bevel_ring(*point, 0.12), tone=0.74)
    m.hull("crotch_block", "pelvis", bevel_ring(*crotch[0], 0.1) + bevel_ring(*crotch[1], 0.08), tone=0.68)
    (ty, tw, tz, tp), (by, bw, bz, bp) = plate_top, plate_bottom
    for sz, name in ((1, "codpiece"), (-1, "seat_plate")):
        m.hull(name, "pelvis", [(sx * tw, ty, sz * tz) for sx in (-1, 1)] + [(sx * bw, by, sz * bz) for sx in (-1, 1)] +
               [(sx * (tw - 0.06), ty - 0.02, sz * tp) for sx in (-1, 1)] + [(sx * (bw - 0.04), by + 0.04, sz * bp) for sx in (-1, 1)],
               tone=0.82)
    for k in range(vents):                           # vents low on the front plate
        y = by + 0.16 + k * 0.1
        z = bp + (tp - bp) * (y - (by + 0.04)) / ((ty - 0.02) - (by + 0.04)) + 0.005
        m.box("crotch_vent", "pelvis", (0, y, z), (0.26 + 0.05 * k, 0.03, 0.03), tone=DARK)


def pelvis_box(m, centre, size, bevel, vent_rows=3):
    """HD BLOCK pelvis/box (the Catapult's: its sheet draws a box, principle 32 satisfied): a bevelled box, vent rows front and back,
    a plate on the back (no large flat space, principle 34). The hip discs are joints (axle_cap) on its sides."""
    cx, cy, cz = centre
    m.hull("pelvis", "pelvis", bevel_box(centre, size, bevel), tone=0.74)
    zf = cz + size[2] / 2 - 0.015
    for k in range(vent_rows):
        m.box("pelvis_vent", "pelvis", (cx, cy - 0.35 + k * 0.15, zf), (1.0, 0.06, 0.1), tone=DARK)
        m.box("pelvis_vent_back", "pelvis", (cx, cy - 0.35 + k * 0.15, -zf), (1.0, 0.06, 0.1), tone=DARK)
    m.hull("pelvis_back_plate", "pelvis", bevel_box((cx, cy + 0.32, -(zf + 0.01)), (1.2, 0.4, 0.06), 0.03), tone=PLATE)


def catapult():
    m = Model()
    # ---------------------------------------------------------------- the body: a rounded teardrop (side heights, top widths)
    # z, y_top, y_bottom, half-width across the top, at the widest, across the bottom
    secs = [(4.11, 8.12, 7.98, 0.03, 0.05, 0.03), (3.90, 8.45, 7.70, 0.22, 0.32, 0.22), (3.45, 8.82, 7.42, 0.45, 0.66, 0.50),
            (3.00, 9.00, 7.12, 0.66, 0.92, 0.72), (2.57, 9.12, 6.98, 0.82, 1.12, 0.88), (1.80, 9.38, 6.95, 0.98, 1.32, 1.02),
            (1.08, 9.62, 6.98, 1.08, 1.42, 1.08), (0.17, 9.95, 7.12, 1.12, 1.48, 1.10), (-1.10, 9.98, 7.55, 1.10, 1.45, 1.06),
            (-2.10, 9.90, 7.95, 1.02, 1.36, 0.98), (-2.35, 9.70, 8.15, 0.85, 1.15, 0.80)]
    slung_body(m, secs)              # the chest lasers' channel is cut through it (Daniel: "cut out a tube"): fire_cut_ok
    # THE BACK (Daniel, 2026-11-18: "the back of the catapult is completely flat. It should have at least some shape, paneling, and
    # greebling. There should almost never be a large flat space on a mech"): the body no longer ends in a flat disc but in a
    # tapering TAIL, a heat-exhaust grille on its end; raised armour panels on the rear flanks; a vent block under the tail
    zt, yt, yb_, wt, wm, wb = secs[-1]
    cyt = (yt + yb_) / 2
    tail = [(zt, 1.0), (zt - 0.22, 0.84), (zt - 0.36, 0.6)]
    ring = lambda z, k: rounded_section(z, cyt + (yt - cyt) * k, cyt - (cyt - yb_) * k, wt * k, wm * k, wb * k)
    for (za, ka), (zb, kb) in zip(tail, tail[1:]):
        m.hull("tail", "torso", ring(za, ka) + ring(zb, kb), tone=0.86)
    zend = tail[-1][0]
    m.hull("exhaust_plate", "torso", bevel_box((0, cyt, zend - 0.02), (1.1, 0.72, 0.06), 0.03), tone=0.6)
    for k in range(5):
        m.box("exhaust_slat", "torso", (0, cyt - 0.26 + k * 0.13, zend - 0.07), (0.96, 0.05, 0.06), tone=DARK)
    for (za, zb), (ta, tb) in (((-1.25, -2.25), (0.25, 0.75)), ((-1.25, -2.25), (0.85, 1.3)), ((-0.2, -1.1), (-0.55, -0.1))):
        conformal_panel(m, secs, za, zb, ta, tb, "torso")
    for k in range(3):                               # panel seams across the rear flank
        m.box("rear_seam", "torso", (0.0, 9.86, -1.4 - k * 0.35), (0.3, 0.02, 0.03), tone=DARK)
    m.hull("tail_vent", "torso", bevel_box((0, 7.78, -1.9), (0.9, 0.18, 0.7), 0.05), tone=0.62)
    for k in range(4):
        m.box("tail_vent_slat", "torso", (0, 7.68, -1.65 - k * 0.17), (0.8, 0.04, 0.05), tone=DARK)
    # panel seams round the body (thin dark rings, slightly proud)
    for z0, t0, b0, a0, m0, c0 in secs[3:-1:2]:
        ring = rounded_section(z0, t0 + 0.02, b0 - 0.02, a0 + 0.02, m0 + 0.02, c0 + 0.02)
        m.hull("seam", "torso", ring + [(x, y, z0 - 0.03) for x, y, _ in ring], tone=DARK)
    # the chin box under the nose, chamfered, with a hatched vent and the two centre-torso medium lasers
    m.hull("chin", "torso", [(-0.75, 7.75, 2.75), (0.75, 7.75, 2.75), (-0.75, 7.0, 2.6), (0.75, 7.0, 2.6),
                             (-0.8, 7.85, 1.35), (0.8, 7.85, 1.35), (-0.8, 6.92, 1.35), (0.8, 6.92, 1.35),
                             (-0.6, 7.2, 2.85), (0.6, 7.2, 2.85)], tone=0.78)
    for k in range(5):
        m.box("chin_vent", "torso", (0.82, 7.15 + k * 0.12, 2.0), (0.03, 0.05, 0.7), tone=DARK, mirror=True)
    for x in (0.38, -0.38):
        m.tube("ml_ct", "torso", (x, 7.3, 2.6), (x, 7.3, 3.05), 0.26, n=12, role="weapon:CT:Medium Laser", tone=METAL)
        m.tube("ml_ct_bore", "torso", (x, 7.3, 3.05), (x, 7.3, 3.08), 0.16, n=12, tone=DARK)
    # the JOWLS: the rounded "cheeks" low on each side of the body house the side-torso medium lasers (Daniel, 2026-11-18: "The
    # little 'cheeks or jowls' on the lower sides of the torso would be where they're housed"). In the front view they are the round
    # bulges flanking the chin; in the side view the hatched housing under the nose, ending behind in the round cap that was first
    # misread as a free-standing torso disc. A pod along the body: domed rear, hatched outer face, the laser's muzzle in front.
    # (the round cap behind the jowl is NOT the jowl's: it is the torso's tilt hinge, below)
    jx, jy, jd = 1.12, 7.5, 0.9
    m.add("dome", "jowl_back", "torso", c=(jx, jy, 1.15), r=(jd / 2, jd / 2, 0.2), n=20, rings=6, tone=0.84, mirror=True)
    m.tube("jowl", "torso", (jx, jy, 1.15), (jx, jy, 2.45), jd, jd * 0.9, n=24, tone=0.84, mirror=True)
    m.tube("jowl_lip", "torso", (jx, jy, 2.45), (jx, jy, 2.6), jd * 0.92, jd * 0.8, n=24, tone=TRIM, mirror=True)
    for k in range(4):                               # the hatching on its outer face (the striped panel in the side view)
        m.box("stripe", "torso", (jx + jd / 2 - 0.06, jy, 1.4 + k * 0.24), (0.14, 0.42, 0.09), tone=DARK, mirror=True)
    m.tube("ml_side", "torso", (jx, jy, 2.55), (jx, jy, 2.95), 0.32, 0.28, n=16, role="weapon:LT:Medium Laser", tone=METAL, mirror=True)
    m.tube("ml_side_bore", "torso", (jx, jy, 2.95), (jx, jy, 2.98), 0.18, n=16, tone=DARK, mirror=True)
    # ---------------------------------------------------------------- the cockpit: glazing WRAPPED on the nose (the cockpit rule)
    # three rows front to back, two panes a side, a frame spine down the middle and frame bands between rows (the side view's
    # dark wedge on the nose's upper faces, the front view's dark band)
    conformal_glass(m, secs, [3.85, 3.4, 2.95, 2.55], [math.pi / 2 + 0.06, math.pi / 2 + 0.5, math.pi / 2 + 0.95], 0.06, role_first="canopy")
    conformal_glass(m, secs, [3.85, 3.4, 2.95, 2.55], [math.pi / 2 - 0.95, math.pi / 2 - 0.5, math.pi / 2 - 0.06], 0.06)
    # the jump jets (2 LT, 2 RT) under the back
    # ---------------------------------------------------------------- the hatch deck between the launchers (the X box)
    m.hull("deck", "torso", bevel_box((0, 10.12, -1.12), (1.6, 0.62, 2.36), 0.16), tone=0.95)
    for a, b in (((-0.6, -2.05), (0.6, -0.2)), ((0.6, -2.05), (-0.6, -0.2))):           # the X on the hatch
        m.add("bar", "deck_x", "torso", a=(a[0], 10.43, a[1]), b=(b[0], 10.43, b[1]), w0=[0.07, 0.02], w1=[0.07, 0.02], tone=DARK)
    m.box("deck_rim", "torso", (0, 10.43, -1.12), (1.3, 0.03, 1.95), tone=0.8)
    # the X box is a RESERVED BAY (principle 22: Daniel, "maybe it houses a radar ... or extra weapons if someone edited the
    # catapult"): its mount point is in the model's `mounts`
    reserved_bay = {"id": "deck.reserved_bay", "kind": "reserved", "pos": [0, 10.43, -1.12], "facing": "+y",
                    "envelope": [1.3, 0.6, 1.95], "accepts": ["greeble:dish", "greeble:sensor", "equipment", "weapon (edited variants)"]}
    # ---------------------------------------------------------------- the arms: LRM 15 launchers on their shoulder discs
    # (record sheet: shoulder + upper arm actuator + LRM 15) - front x 1.60, width 1.45, y 8.6-11.1, z -2.54 .. 0.11
    axle_cap(m, "shoulder", "arm_L", 9.3, -0.85, 1.2, 2.2, 1.35, n=28, ring=(0.12, 1.1), hub=(0.08, 0.5))
    m.hull("rack", "arm_L", bevel_box((1.6, 9.9, -1.27), (1.44, 2.6, 2.54), 0.22), tone=PLATE, role="weapon:LA:LRM 15", mirror=True)
    m.box("rack_face", "arm_L", (1.6, 10.12, 0.03), (1.22, 1.9, 0.08), tone=DARK, mirror=True)
    for col in range(3):                             # the LRM 15's fifteen tubes: 3 across, 5 down (the front view's grid)
        for row in range(5):
            x, y = 1.6 + (col - 1) * 0.38, 10.82 - row * 0.35
            m.tube("tube", "arm_L", (x, y, 0.02), (x, y, 0.13), 0.3, n=12, tone=0.7, mirror=True)
            m.tube("bore", "arm_L", (x, y, 0.13), (x, y, 0.135), 0.19, n=12, tone=0.1, mirror=True)
    for k in range(4):                               # ribs down the launcher's sides and a hatch on top (the side and top views)
        m.box("rib", "arm_L", (2.33, 9.85, -0.4 - k * 0.55), (0.04, 2.3, 0.08), tone=TRIM, mirror=True)
    m.box("rack_hatch", "arm_L", (1.6, 11.21, -1.25), (1.0, 0.03, 1.6), tone=0.8, mirror=True)
    # the launcher's BACK (it was one flat face): a raised reload panel with a hatch, ribs across it, a handle
    m.hull("rack_back", "arm_L", bevel_box((1.6, 9.85, -2.56), (1.16, 2.1, 0.08), 0.04), tone=PLATE, mirror=True)
    for y in (9.15, 9.85, 10.55):
        m.box("rack_back_rib", "arm_L", (1.6, y, -2.62), (1.0, 0.08, 0.06), tone=TRIM, mirror=True)
    m.box("reload_hatch", "arm_L", (1.6, 10.2, -2.615), (0.62, 0.42, 0.03), tone=0.55, mirror=True)
    m.add("bar", "rack_handle", "arm_L", a=(1.35, 9.5, -2.62), b=(1.85, 9.5, -2.62), w0=[0.06, 0.1], w1=[0.06, 0.1], tone=DARK, mirror=True)
    # ---------------------------------------------------------------- the lower torso: waist, side discs, hip block and hip discs
    # the TORSO TILT HINGE (Daniel: "That round section was the hinge that allowed the torso to tilt up and down"): a drum across
    # the body's underside, axis x, at the round section of the side view (y 7.45, z 0.55); a hub ring at each end
    hinge = (0.0, 7.45, 0.55)
    axle_cap(m, "tilt_hinge", "torso", hinge[1], hinge[2], -1.55, 1.55, 1.2, n=28, across=True,
             ring=(1.4, 1.56, 1.28, 1.28), hub_at=(1.55, 1.62, 0.55))
    # the WAIST: an octagonal tower rising from the hip block, tilted so it meets the hinge squarely, topped by a pyramid that
    # closes round the hinge (Daniel: "a mix of octagon tower and pyramid"); the waist turns the torso, the hinge tilts it
    # its root is a BALL sunk in the hip block and a COWL rings it at the block's top (Daniel, 2026-11-18: the tilted tower's bottom
    # poked out of the hip block; "a cowl, or building waist blocks with extra structure (like a hemisphere) that is usually inside
    # the hip block if flat"): however the tower leans, its root stays inside
    top = (0.0, hinge[1] - 0.15, hinge[2] - 0.05)
    lean = (0.0, top[1] - 6.35, top[2] + 0.05)
    ln = math.hypot(lean[1], lean[2])
    base = (0.0, 6.35 - 0.3 * lean[1] / ln, -0.05 - 0.3 * lean[2] / ln)       # 0.3 further down the tower's own axis
    mid = (0.0, base[1] + (top[1] - base[1]) * 0.55, base[2] + (top[2] - base[2]) * 0.55)
    waist_joint(m, base, 0.8, ((0.0, 6.5, -0.05), (0.0, 6.82, -0.02), 1.95, 1.72), tower=(base, mid, top, 1.5, 1.42, 0.95))
    pelvis_box(m, (0.0, 5.8, 0.0), (1.67, 1.5, 2.15), 0.3)
    axle_cap(m, "hip_disc", "pelvis", 5.72, 0.0, 0.75, 1.02, 1.45, n=28, ring=(0.06, 1.2))
    # ---------------------------------------------------------------- the legs: reverse knee (side view), x 1.52
    # the thigh: a big rounded block, hip (y 5.72, z 0) down and BACK to the knee (y 4.31, z -1.68)
    # the hip at the hip discs' axis, so the thigh turns about it (Daniel: "circular end caps on the legs that engage with the
    # circular hip connecting points")
    hip, knee, ankle = (1.52, 5.72, 0.0), (1.52, 4.3, -1.68), (1.52, 0.72, 1.08)
    leg_from = len(m.parts)
    axle_cap(m, "thigh_cap", "leg_L", hip[1], hip[2], 1.06, 2.02, 1.4, n=28, ring=(0.08, 1.05), hub=(0.06, 0.5))
    joint_cover(m, "hip_cover", "leg_L", hip, 2.16, 0.8, sides=6, roll=30)        # covers vary the run of round joints

    limb(m, "thigh", "leg_L", hip, knee, 1.1, 1.55, 0.95, 1.15, tone=0.72, mirror=True, phase=0.0)
    axle_cap(m, "knee_cap", "leg_L", knee[1], knee[2] - 0.05, 0.95, 2.1, 1.05, n=24, hub=(0.06, 0.45, 16))
    joint_cover(m, "knee_cover", "leg_L", (knee[0], knee[1], knee[2] - 0.05), 2.16, 0.62, sides=5, roll=180, kz=1.15)
    limb(m, "shin", "leg_L", knee, ankle, 0.92, 1.0, 0.78, 0.82, steps=5, tone=0.72, mirror=True, phase=0.0)
    # armour plate down the shin's front and a vent hatch on its side
    m.add("bar", "shin_plate", "leg_L", a=(1.52, 3.6, -0.85), b=(1.52, 1.3, 0.75), w0=[0.7, 0.18], w1=[0.6, 0.16], tone=PLATE, mirror=True)
    for k in range(5):
        m.box("shin_vent", "leg_L", (1.9, 2.9 - k * 0.14, -0.15 + k * 0.1), (0.2, 0.06, 0.5), tone=DARK, mirror=True)
    # the ANKLE: built out into a flared housing from mid-shin to the foot (Daniel, 2026-11-18: "In the art its built out because
    # thats where the muscles would be housed"; the side view's wide trapezoid above the foot, the front view's widening lower leg)
    def on_shin(y):
        t = (knee[1] - y) / (knee[1] - ankle[1])
        return knee[2] + (ankle[2] - knee[2]) * t
    rings = []
    for y, w, d, back in ((2.35, 0.94, 1.0, 0.0), (1.4, 1.14, 1.45, 0.12), (0.5, 1.32, 1.95, 0.3)):
        zc = on_shin(y) - back
        rings.append([(1.52 + sx * w / 2 * (0.82 if abs(sz) == 1 else 1.0), y, zc + sz * d / 2 * (0.82 if abs(sx) == 1 else 1.0))
                      for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1), (-1.22, 0), (1.22, 0), (0, -1.12), (0, 1.12))])
    for r0, r1 in zip(rings, rings[1:]):
        m.hull("ankle_housing", "leg_L", r0 + r1, tone=0.72, mirror=True)
    m.add("bar", "ankle_plate", "leg_L", a=(1.52, 2.25, on_shin(2.25) + 0.52), b=(1.52, 0.75, on_shin(0.75) + 0.7),
          w0=[0.62, 0.12], w1=[0.85, 0.14], tone=PLATE, mirror=True)
    for k in range(4):                               # the hatching on the housing's side (the side view's hatched block)
        m.box("ankle_vent", "leg_L", (2.17, 0.95 + k * 0.17, on_shin(1.3) - 0.1), (0.03, 0.07, 0.75), tone=DARK, mirror=True)
    axle_cap(m, "ankle_hub", "leg_L", 0.85, on_shin(0.85) - 0.1, 2.12, 2.24, 0.55, n=20)
    foot_from = len(m.parts)
    # the foot: a long sole (side x 84-218, toes forward), three toes, a heel spur; the WHOLE foot turned 18 degrees outward about
    # the ankle (each part was first turned about its own middle, which slid the foot out from under the leg)
    ax_, az_ = 1.52, ankle[2]
    sp = math.radians(18)

    def turn(q):
        x, y, z = q[0] - ax_, q[1], q[2] - az_
        return (ax_ + x * math.cos(sp) + z * math.sin(sp), y, az_ - x * math.sin(sp) + z * math.cos(sp))
    for dx, ln in ((-0.42, 1.35), (0.0, 1.55), (0.42, 1.35)):
        m.hull("toe", "leg_L", [turn(q) for q in [(1.52 + dx - 0.2, 0, 0.9), (1.52 + dx + 0.2, 0, 0.9), (1.52 + dx - 0.16, 0, 0.9 + ln),
                                                  (1.52 + dx + 0.16, 0, 0.9 + ln), (1.52 + dx - 0.18, 0.42, 0.95), (1.52 + dx + 0.18, 0.42, 0.95),
                                                  (1.52 + dx - 0.1, 0.12, 0.85 + ln), (1.52 + dx + 0.1, 0.12, 0.85 + ln)]], tone=0.74, mirror=True)
    m.hull("instep", "leg_L", [turn(q) for q in [(0.82, 0, -0.25), (2.22, 0, -0.25), (0.82, 0, 1.05), (2.22, 0, 1.05),
                                                 (1.0, 0.62, -0.05), (2.04, 0.62, -0.05), (1.0, 0.62, 1.0), (2.04, 0.62, 1.0)]], tone=0.7, mirror=True)
    m.hull("heel", "leg_L", [turn(q) for q in [(1.17, 0, -0.2), (1.87, 0, -0.2), (1.17, 0, -1.1), (1.87, 0, -1.1),
                                               (1.2, 0.4, -0.2), (1.84, 0.4, -0.2)]], tone=0.74, mirror=True)
    # JUMP JETS (2 LT, 2 RT; Daniel, 2026-11-18: "The jump jets are off axis to actually act as rockets"): the nozzles point
    # straight down and their thrust centre is the 'Mech's centre of mass, or a jump would pitch it over. Each side torso's pair
    # stands one in front of and one behind the centre of mass, the same distance away: the front nozzle under the jowl's back, the
    # rear one under the body. (Before: both pairs far behind the centre of mass.)
    leg_end = len(m.parts)       # the parts after this are NOT the legs' (the splay below must not move them: it first swung the
                                 # jump-jet vents out off the body, found by the no-floating-bits check)
    cg = centre_of_mass(m.parts)
    # Second placement (Daniel: "they're clipping or crowding other features. They could be placed more on the body either angled
    # out, or with vents that come out just a bit"): VENTS on the body's flanks, in the clear strip between the tilt hinge (below)
    # and the launcher arms (above), each angled down and OUTWARD (the left and right thrusts' sideways parts cancel), one in front
    # of and one behind the centre of mass. A short lip stands proud of the skin; the jet itself is inside.
    tilt = math.radians(35)
    for k, (dz, y_want) in enumerate(((0.72, 8.33), (-0.72, 8.15))):
        z = cg[2] + dz
        cands = [surface_point(secs, z, t * 0.02) for t in range(-40, 41)]
        sp_ = min(cands, key=lambda q: abs(q[1] - y_want))
        dirn = (math.sin(tilt), -math.cos(tilt), 0.0)           # down and out (the 'Mech's left; mirrored for the right)
        root = (sp_[0] - dirn[0] * 0.12, sp_[1] - dirn[1] * 0.12, z)
        tip = (sp_[0] + dirn[0] * 0.14, sp_[1] + dirn[1] * 0.14, z)
        m.tube("jj_lip", "torso", root, tip, 0.46, 0.52, n=20, tone=0.45, mirror=True, role="jumpjet:LT" if k == 0 else None)
        m.tube("jj_throat", "torso", tip, (tip[0] + dirn[0] * 0.01, tip[1] + dirn[1] * 0.01, z), 0.38, n=20, tone=DARK, mirror=True)
        # a small hood over the vent, sloping into the skin above it
        m.hull("jj_hood", "torso", [(sp_[0] - 0.08, sp_[1] + 0.32, z + sz * 0.3) for sz in (-1, 1)] +
               [(sp_[0] + 0.1, sp_[1] + 0.12, z + sz * 0.3) for sz in (-1, 1)] +
               [(sp_[0] - 0.1, sp_[1] + 0.05, z + sz * 0.3) for sz in (-1, 1)], tone=PLATE, mirror=True)
    splay = splay_legs(m, leg_from, leg_end, foot_from, hip, ankle, LEG_SPLAY)
    # the PIVOTS, for animation: centre and axis of every joint (the left side; mirror x for the right)
    pivots = {"torso_tilt": {"centre": list(hinge), "axis": "x", "parent": "waist", "child": "torso"},
              "waist_turn": {"centre": rnd(base), "axis": rnd([0, top[1] - base[1], top[2] - base[2]]), "parent": "pelvis", "child": "waist"},
              "hip_L": {"centre": list(hip), "axis": "x", "parent": "pelvis", "child": "thigh"},
              "knee_L": {"centre": rnd(splay(knee)), "axis": "x", "parent": "thigh", "child": "shin"},
              "ankle_L": {"centre": rnd(splay(ankle)), "axis": "x", "parent": "shin", "child": "foot"},
              "shoulder_L": {"centre": [1.8, 9.3, -0.85], "axis": "x", "parent": "torso", "child": "launcher arm"}}
    return {"unit": "Catapult", "model": "CPLT-C1", "mass": 65, "detail": "hd", "stance": "a_stance", "pivots": pivots,
            "centre_of_mass": centre_of_mass(m.parts), "mounts": [reserved_bay],
            "poses": {"dynamic": {"torso_tilt": -10, "waist_turn": -12, "hip_L": -24, "knee_L": 18, "ankle_L": 6,
                                  "hip_R": 18, "knee_R": -8, "ankle_R": -10, "shoulder_L": -22, "shoulder_R": -8}},
            "scale": "ground to the body's top = 10; +x is the 'Mech's left",
            "source": "AI five-view sheet, reference_art/ai_sheets/Catapult CPLT-C1/batch2_1.webp (measured on a grid; tools/lowpoly_hd.py)",
            "simplified_to": "reference_art/models/Catapult CPLT-C1.json",
            "art_vs_unit_file": [
                "LRM 15s in the arms (record sheet: shoulder + upper arm actuator + LRM 15): the launchers ARE the arms, on the shoulder discs.",
                "The art draws one launcher raised (a pose): both built level.",
                "Medium lasers: the LT / RT lasers are housed in the 'jowls' low on the body's sides (Daniel); the two CT lasers in the chin. Jump jets (not drawn) under the back.",
                "Each view scaled to its own body-top height (the side view is drawn ~10 % taller than the front)."],
            "parts": m.parts}


def limb(m, name, asm, a, b, w0, d0, w1, d1, steps=4, sides=16, tone=0.72, mirror=False, bulge=0.15, phase=0.5):
    """HD BLOCK limb/rounded. A limb between a and b (both at the same x): slices of rounded (or, with few `sides`, faceted) sections
    of width w (across x) and depth d (across the limb, in the side plane), the middle a little fuller (`bulge`). `phase` turns the
    section (0.5: a flat face on top, as the Commando's six-sided forearm; 0: a corner on top, as the Catapult's legs)."""
    ax = (b[1] - a[1], b[2] - a[2])
    ln = math.hypot(*ax)
    uy, uz = ax[0] / ln, ax[1] / ln
    ny, nz = -uz, uy
    rings = []
    for i in range(steps + 1):
        t = i / steps
        cy, cz = a[1] + ax[0] * t, a[2] + ax[1] * t
        w = w0 + (w1 - w0) * t
        d = (d0 + (d1 - d0) * t) * (1 - bulge * (2 * t - 1) ** 2 if steps > 1 else 1)
        ring = []
        for k in range(sides):
            th = 2 * math.pi * (k + phase) / sides
            ring.append((a[0] + w / 2 * math.cos(th), cy + ny * d / 2 * math.sin(th), cz + nz * d / 2 * math.sin(th)))
        rings.append(ring)
    for r0, r1 in zip(rings, rings[1:]):
        m.hull(name, asm, r0 + r1, tone=tone, mirror=mirror)


def axle_cap(m, name, asm, y, z, x0, x1, d, n=24, ring=None, hub=None, hub_at=None, mirror=True, across=False, tone=None):
    """HD BLOCK joint/axle_cap (T15c item B; the HD review: "the most reused block"): a joint as its parts show it from the side - a
    DRUM on the joint's axis (x, from x0 to x1, diameter d), then on its outer end an optional TRIM RING and an optional dark HUB.
      ring: (length, outer diameter) - from x1, tapering from d; or (x_from, x_to, d0, d1[, n[, dy]]) given in full
      hub:  (length, diameter[, n]) - after the ring (or the drum); hub_at: (x_from, x_to, diameter[, n]) in full
    across=True: the drum spans both sides (one part, x0 = -x1: the Catapult's tilt hinge) and only the ring and hub are mirrored."""
    m.tube(name, asm, (x0, y, z), (x1, y, z), d, n=n, tone=JOINT if tone is None else tone, mirror=mirror and not across)
    end = x1
    if ring:
        if len(ring) == 2:
            m.tube(name + "_ring", asm, (x1, y, z), (x1 + ring[0], y, z), d, ring[1], n=n, tone=TRIM, mirror=mirror)
            end = x1 + ring[0]
        else:
            xa, xb, r0, r1 = ring[:4]
            rn = ring[4] if len(ring) > 4 else n
            dy = ring[5] if len(ring) > 5 else 0.0
            m.tube(name + "_ring", asm, (xa, y + dy, z), (xb, y + dy, z), r0, r1, n=rn, tone=TRIM, mirror=mirror)
            end = max(end, xb) if not across else end
    if hub:
        m.tube(name + "_hub", asm, (end, y, z), (end + hub[0], y, z), hub[1], n=hub[2] if len(hub) > 2 else 20, tone=DARK, mirror=mirror)
    if hub_at:
        m.tube(name + "_hub", asm, (hub_at[0], y, z), (hub_at[1], y, z), hub_at[2], n=hub_at[3] if len(hub_at) > 3 else 20, tone=DARK,
               mirror=mirror)


def waist_joint(m, ball, ball_r, cowl, ball_n=20, ball_rings=10, tower=None):
    """HD BLOCK waist/ball_cowl (the waist turns the torso): a BALL sunk in the pelvis and a COWL ringing the joint line (Daniel:
    "a cowl, or building waist blocks with extra structure (like a hemisphere) that is usually inside the hip block": the root stays
    inside however the waist leans). cowl = (bottom point, top point, d0, d1), octagonal. tower = (base, mid, top, d_base, d_mid,
    d_top): an octagonal tower and a pyramid above it, leaning to meet a tilt hinge (the Catapult: "a mix of octagon tower and
    pyramid")."""
    m.add("dome", "waist_ball", "pelvis", c=ball, r=(ball_r, ball_r, ball_r), n=ball_n, rings=ball_rings, tone=JOINT)
    m.tube("waist_cowl", "pelvis", cowl[0], cowl[1], cowl[2], cowl[3], n=8, roll=22.5, tone=0.7)
    if tower:
        base, mid, top, d0, d1, d2 = tower
        m.tube("waist_tower", "pelvis", base, mid, d0, d1, n=8, roll=22.5, tone=0.68)
        m.tube("waist_pyramid", "pelvis", mid, top, d1, d2, n=8, roll=22.5, tone=0.68)


def splay_legs(m, leg_from, leg_end, foot_from, hip, ankle, deg):
    """HD BLOCK: the leg SPLAY (Daniel: "the legs are splayed out slightly"). Every leg part (parts leg_from .. leg_end) turns `deg`
    degrees outward about the hip; the foot (parts from foot_from) only follows the ankle sideways, staying flat on the ground.
    Returns the splay function (for the pivots)."""
    a = math.radians(deg)

    def splay(q):
        dx, dy = q[0] - hip[0], q[1] - hip[1]
        return (hip[0] + dx * math.cos(a) - dy * math.sin(a), hip[1] + dx * math.sin(a) + dy * math.cos(a), q[2])
    shift = splay(ankle)[0] - ankle[0]
    for i in range(leg_from, leg_end):
        p = m.parts[i]
        f = (lambda q: (q[0] + shift, q[1], q[2])) if i >= foot_from else splay
        for key in ("a", "b", "c"):
            if key in p:
                p[key] = rnd(f(p[key]))
        if "pts" in p:
            p["pts"] = [rnd(f(q)) for q in p["pts"]]
        if i < foot_from and p["kind"] in ("box", "wedge"):
            p["rot"] = [0, 0, deg]
    return splay


def dome_point(c, r, lat, lon, grow=0.0):
    """A point on an ellipsoid dome (centre c, radii r) at latitude / longitude in degrees (longitude 90 = straight ahead, +z)."""
    a, t = math.radians(lat), math.radians(lon)
    return (c[0] + (r[0] + grow) * math.cos(a) * math.cos(t), c[1] + (r[1] + grow) * math.sin(a),
            c[2] + (r[2] + grow) * math.cos(a) * math.sin(t))


def bevel_ring(y, hw, zf, zb, ch, x0=0.0):
    """A horizontal section at height y: a rectangle (half-width hw, front zf, back zb) with its four corners chamfered by ch."""
    return [(x0 + sx * hw, y, z) for sx in (-1, 1) for z in (zf - ch, zb + ch)] + \
           [(x0 + sx * (hw - ch), y, z) for sx in (-1, 1) for z in (zf, zb)]


def commando():
    """COMMANDO COM-2D (25 t light). Measured on a grid over the Gemini five-view sheet (reference_art/ai_sheets/Commando COM-2D/
    gemini_1.webp; front view 10/352 per pixel, centre x 212, ground y 530) and tools/lowpoly_measure.py (crotch 0.489, shoulders
    0.494 wide at 0.855, feet 0.405 wide); the weapons and the arms from the TRO drawing and the record sheet; Daniel's rulings in
    reference_art/views.json. Units: ground to the dome's top = 10; +x is the 'Mech's LEFT, +z forward."""
    m = Model()
    # ---------------------------------------------------------------- the head: a HELMET (Daniel, 2026-11-18, second look: "the head
    # and neck are perhaps too simple. In the TRO ... kind of a helmet that covers the back of the neck. The AI version is just a well
    # designed futuristic looking head"): a faceted dome, a skirt sweeping down round the sides and back over the neck (open at the
    # face), a brow ridge over the visor, a crest, a jaw with a grille
    helmet(m, (0.0, 9.15, 0.05), (0.92, 0.85, 0.95), neck_base=8.3, skirt_bottom=8.88, skirt_back_drop=0.08)
    # ---------------------------------------------------------------- the upper torso: a chamfered block narrowing to the waist
    # (the sheet's "rectangular block torso"; the TRO's deep chest)
    # PROPORTIONS measured row by row on the sheet (2026-11-18, Daniel: "take measurements of it vs the AI drawings for torso
    # proportions"; the first build was a V, 2.84 wide at the chest, narrowing to 1.64 at the waist): front widths 2.3-2.5 at the
    # chest, narrowest (2.05) at the round belly, 2.4 below it; side depths about 1.9 at the chest, 1.7 at the belly
    lv = [(8.65, 1.05, 0.62, -0.65), (8.5, 1.25, 0.85, -0.85), (7.8, 1.25, 1.0, -0.9), (7.2, 1.17, 1.0, -0.9),
          (6.85, 1.03, 0.9, -0.85), (6.3, 1.2, 0.86, -0.8), (5.75, 1.2, 0.8, -0.75)]
    torso_stack(m, lv)
    m.box("chest_seam", "torso", (0, 7.2, 0), (2.38, 0.05, 1.94), tone=DARK)
    # (the SRM 6 is on the round belly: below, after the belly)
    # HIDDEN WEAPON MOUNTS (Daniel: "torso weapons would be placed flat on the torso sections much as the srm 6 is. A theoretical
    # arrangement could be a quad in the upper chest, middle chest, and lower belly. 4 small weapons grouped together in one mount";
    # "hidden. No hatches"): nothing is drawn; the model's `mounts` list them for an edited Commando. Each side torso: three quads
    # (3 x 4 = its 12 weapon slots), on the chest's flat front, the lower ones small enough to clear the round belly
    hidden = []
    for side, sx in (("LT", 1), ("RT", -1)):
        for level, (x, y, size) in (("upper_chest", (0.77, 8.2, 0.44)), ("middle_chest", (0.77, 7.5, 0.44)), ("lower_belly", (0.86, 5.88, 0.22))):
            hidden.append({"id": "%s.quad_%s" % (side, level), "kind": "weapon_quad", "location": side, "slots": 4, "hidden": True,
                           "pos": [round(sx * x, 3), y, 1.0 if y > 6.4 else 0.82], "facing": "+z", "envelope": [size, size, 0.3]})
    # the CENTRE TORSO's mount is the ROUND BELLY (Daniel, 2026-11-18, after the stress test: "For the center torso, you can move the
    # weapons onto the round belly to get more space"; it was the upper belly, 0.95 x 0.6): the square inside the belly's face
    hidden.append({"id": "CT.belly", "kind": "weapon_bay", "location": "CT", "slots": 2, "hidden": False, "holds": "SRM 6",
                   "pos": [0.0, 6.5, 0.97], "facing": "+z", "envelope": [1.28, 1.28, 0.3]})
    # the ROUND BELLY: kept for recognition, a RESERVED BAY (Daniel, 2026-11-18: it reads as a torso pivot, "not worth making it an
    # actual pivot point"; principle 24). Not a plate laid on the chest (the first build): the belly itself bulges out, faceted, and
    # BEVELS into the rest of the torso (Daniel: "its not a separate plate, its the belly that bevels into the rest of the lower
    # torso"): a faceted frustum in the torso's own tone, its back buried in the torso, its sloped sides the bevel
    # (second look, Daniel: "It looks like it has a beer gut now": the sheet's circle is about 2.0 across, nearly the torso's width,
    # and barely stands out of the front, which is at its NARROWEST there) - a shallow faceted disc, its rim bevelled into the torso
    m.tube("belly", "torso", (0, 6.5, 0.62), (0, 6.5, 0.97), 2.02, 1.82, n=16, roll=11.25, tone=0.88)
    m.box("belly_seam_v", "torso", (0, 6.5, 0.975), (0.04, 1.6, 0.02), tone=DARK)
    m.box("belly_seam_h", "torso", (0, 6.68, 0.975), (1.5, 0.04, 0.02), tone=DARK)
    # the SRM 6 (record sheet: centre torso) ON THE BELLY, the centre torso's mount (above), 3 x 2 tubes
    bay_grid(m, "torso", (0.0, 6.5, 0.97), 1.1, 0.74, 2, 3, role="weapon:CT:SRM 6", name="srm6_bay")
    # the back: a flat pack (the rear view's rectangle)
    m.hull("back_pack", "torso", bevel_box((0, 7.6, -1.08), (1.8, 1.7, 0.36), 0.12), tone=PLATE)
    for k in range(4):
        m.box("pack_vent", "torso", (0, 7.05 + k * 0.16, -1.27), (1.2, 0.06, 0.03), tone=DARK)
    # ---------------------------------------------------------------- the waist and the hips
    # the waist turns the upper torso: a ball sunk in the belt and a cowl ringing it at the joint line (principle: the root inside)
    waist_joint(m, (0, 5.72, 0), 0.62, ((0, 5.7, 0), (0, 5.84, 0), 2.3, 2.15), ball_n=16, ball_rings=8)
    # PROPORTIONS (self-review against the sheet, first build): the legs start right under the belt (the sheet's crotch at 0.49 of
    # the height, about 4.8 here) and are slim; the first build hung a tall hip block under the belt, which cut the legs short
    # the sheet's belt is the widest part of the lower body (about 2.9), the legs hang straight from under it, 2.2 apart
    # the PELVIS as BRIEFS (Daniel, 2026-11-18: "In the ai drawing it looks like an actual pelvis or 'Briefs' underwear. In yours its
    # just a rectangular box. The box is the wrong option here"): a belt band, and under it a shape that narrows from the belt's width
    # down to the crotch, its sloped sides the leg openings the thighs come out of; a raised plate down the front, a seat plate behind
    pelvis_briefs(m, 5.62, 2.85, 1.62, (5.46, 1.34, 0.74, -0.74), (4.6, 0.42, 0.52, -0.54),
                  ((4.62, 0.42, 0.5, -0.5), (4.38, 0.34, 0.42, -0.42)), (5.42, 0.62, 0.7, 0.79), (4.62, 0.24, 0.5, 0.57))
    # the legs are drawn at x 0.72 and moved out by LEG_OUT below (all their parts at once)
    LEG_OUT = 0.33
    hip, knee, ankle = (0.72, 4.95, 0.0), (0.72, 3.1, 0.1), (0.72, 0.8, -0.05)
    # ---------------------------------------------------------------- the legs (front and side views: Daniel calls them accurate)
    leg_from = len(m.parts)
    axle_cap(m, "thigh_cap", "leg_L", hip[1], 0, 0.22, 1.3, 0.86, n=24, hub=(0.06, 0.48, 16))     # turns in the hip block
    joint_cover(m, "hip_cover", "leg_L", hip, 1.36, 0.5, sides=6, roll=30, kz=1.1)
    # the thigh's top is cut on a SLANT that follows the briefs' side, a small gap below it (the sheet: the leg openings), high on
    # the outside, low at the crotch. Written where the leg ends up (x + LEG_OUT) and moved back, as the leg moves out below.
    slope = (5.46 - 4.6) / (1.34 - 0.42)
    top = lambda x: min(5.3, 4.6 + (x - 0.42) * slope - 0.1)
    m.hull("thigh_top", "leg_L", [(x - LEG_OUT, y, z) for x in (0.5, 1.2, 1.62) for y in (top(x), 4.45) for z in (-0.6, 0.6)],
           tone=0.8, mirror=True)
    limb(m, "thigh", "leg_L", hip, knee, 1.05, 1.3, 0.92, 1.0, steps=3, tone=0.74, mirror=True)
    m.add("bar", "thigh_plate", "leg_L", a=(0.72, 4.3, 0.58), b=(0.72, 3.55, 0.54), w0=[0.82, 0.12], w1=[0.7, 0.1], tone=PLATE, mirror=True)
    axle_cap(m, "knee_cap", "leg_L", knee[1], knee[2], 0.26, 1.18, 0.85, n=24, ring=(1.18, 1.26, 1.0, 0.86), hub=(0.04, 0.36, 16))
    joint_cover(m, "knee_cover", "leg_L", knee, 1.3, 0.56, sides=5, roll=180, ky=1.15)          # a guard, its point down
    m.add("bar", "knee_pad", "leg_L", a=(0.72, 3.6, 0.52), b=(0.72, 2.8, 0.64), w0=[0.82, 0.22], w1=[0.68, 0.2], tone=0.86, mirror=True)
    limb(m, "shin", "leg_L", knee, ankle, 0.86, 0.95, 0.8, 0.85, steps=4, tone=0.72, mirror=True)
    m.hull("calf", "leg_L", [(0.72 + sx * 0.32, y, z) for sx in (-1, 1) for y, z in ((2.65, -0.28), (1.55, -0.38), (2.3, -0.6), (1.7, -0.58))],
           tone=0.7, mirror=True)
    for k in range(4):
        m.box("shin_vent", "leg_L", (1.12, 2.3 - k * 0.14, 0.05), (0.06, 0.06, 0.45), tone=DARK, mirror=True)
    # the ANKLE built out (the muscles' housing; the sheet's flared lower leg)
    rings = []
    # its bottom ring goes down INTO the foot (Daniel, 2026-11-18: "The ankles are not firmly attached to the feet. There are gaps on
    # the side": the splay tilts the housing, lifting one side of a bottom that only touched the foot's top)
    for y, w, d in ((1.95, 0.8, 0.86), (1.2, 0.96, 1.12), (0.5, 1.12, 1.38), (0.22, 1.12, 1.38)):
        zc = knee[2] + (ankle[2] - knee[2]) * (knee[1] - y) / (knee[1] - ankle[1])
        rings.append(bevel_ring(y, w / 2, zc + d / 2, zc - d / 2, 0.14, x0=0.72))
    for r0, r1 in zip(rings, rings[1:]):
        m.hull("ankle_housing", "leg_L", r0 + r1, tone=0.72, mirror=True)
    axle_cap(m, "ankle_hub", "leg_L", 0.72, ankle[2], 1.26, 1.36, 0.44, n=16)
    foot_from = len(m.parts)
    # the foot: long and wedged (side view: toe 1.55 ahead of the ankle, heel 1.05 behind; front view 1.7 wide), a ridge on top
    fx = 0.72
    m.hull("foot", "leg_L", [(fx + sx * 0.76, 0, z) for sx in (-1, 1) for z in (-1.05, 1.15)] + [(fx + sx * 0.46, 0, 1.6) for sx in (-1, 1)] +
           [(fx + sx * 0.64, 0.46, z) for sx in (-1, 1) for z in (-0.85, 0.6)] + [(fx + sx * 0.4, 0.2, 1.5) for sx in (-1, 1)],
           tone=0.76, mirror=True)
    m.add("bar", "foot_ridge", "leg_L", a=(fx, 0.5, 0.35), b=(fx, 0.22, 1.45), w0=[0.5, 0.12], w1=[0.36, 0.1], tone=PLATE, mirror=True)
    m.hull("heel", "leg_L", [(fx + sx * 0.54, y, z) for sx in (-1, 1) for y, z in ((0, -1.05), (0, -1.35), (0.35, -1.05), (0.12, -1.3))],
           tone=0.7, mirror=True)
    leg_end = len(m.parts)
    # ---------------------------------------------------------------- the arms: shoulder pad, upper arm, elbow, faceted forearm, fist
    # A ready pose (the TRO's right arm; the sheet's side views): the upper arm 15 degrees forward, the forearm level, pointing ahead,
    # so the arm weapons fire forward (they are in line with the forearm, Daniel). Record sheet: both arms have all four actuators.
    pivots = {}
    for s, asm, side in ((1, "arm_L", "L"), (-1, "arm_R", "R")):
        X = lambda x: s * x
        sh = (X(2.05), 8.15, 0.0)
        # the pad: flat top, the outer side square, the underside sloping in and down to the chest (the sheet's front view)
        pad = []
        for z in (-0.95, 0.95):
            zi = z - math.copysign(0.14, z)
            pad += [(X(1.15), 8.8, zi), (X(2.62), 8.8, zi), (X(2.62), 8.1, zi), (X(1.15), 7.6, zi)]     # inner edge into the
            pad += [(X(1.27), 8.66, z), (X(2.48), 8.66, z), (X(2.48), 8.2, z), (X(1.27), 7.74, z)]     # narrower chest
        m.hull("shoulder_pad", asm, pad, tone=0.9)
        m.box("pad_trim", asm, (X(1.96), 8.81, 0), (1.1, 0.03, 1.5), tone=0.8)
        if side == "R":
            # the ANTENNA on the right shoulder pad, at its back (the sheet's place; Daniel, 2026-11-18: "I also kind of like the
            # antenna on the shoulder. Its not accurate to the picture, but being perfectly accurate is not the goal")
            m.tube("mast_base", asm, (X(1.75), 8.76, -0.62), (X(1.75), 8.98, -0.62), 0.26, 0.2, n=10, tone=DARK)
            m.add("bar", "mast", asm, a=(X(1.75), 8.95, -0.62), b=(X(1.8), 10.45, -0.78), w0=[0.07, 0.07], w1=[0.04, 0.04], tone=DARK)
        axle_cap(m, "shoulder", asm, sh[1], 0, X(1.15), X(2.66), 0.9, n=24, ring=(X(2.62), X(2.7), 0.8, 0.6, 20, -0.05), mirror=False)
        up = math.radians(15)
        elbow = (sh[0], sh[1] - 1.15 * math.cos(up), 1.15 * math.sin(up))
        limb(m, "upper_arm", asm, sh, elbow, 0.92, 0.92, 0.9, 0.86, steps=3, sides=8, tone=0.74)
        axle_cap(m, "elbow", asm, elbow[1], elbow[2], X(1.55), X(2.55), 0.86, n=20, mirror=False)
        dn = math.radians(8)
        wrist = (sh[0], elbow[1] - 1.6 * math.sin(dn), elbow[2] + 1.6 * math.cos(dn))
        limb(m, "forearm", asm, elbow, wrist, 1.25, 1.2, 1.15, 1.08, steps=2, sides=6, tone=0.78, bulge=0.08)
        m.tube("forearm_band", asm, (sh[0], *[elbow[i] + (wrist[i] - elbow[i]) * 0.55 for i in (1, 2)]),
               (sh[0], *[elbow[i] + (wrist[i] - elbow[i]) * 0.6 for i in (1, 2)]), 1.24, n=6, tone=DARK)
        # the FIST (record sheet: hand actuator; Daniel: "a hand ... curled up into a fist")
        fc = (sh[0], wrist[1] - 0.16, wrist[2] + 0.3)
        axle_cap(m, "wrist", asm, wrist[1], wrist[2], X(1.75), X(2.35), 0.62, n=16, mirror=False)
        m.hull("fist", asm, bevel_box(fc, (0.92, 0.95, 0.75), 0.14), tone=0.82)
        m.hull("knuckles", asm, bevel_box((fc[0], fc[1] + 0.22, fc[2] + 0.38), (0.88, 0.36, 0.14), 0.04), tone=0.86)
        for k in range(3):
            m.box("finger_gap", asm, (fc[0] + (k - 1) * 0.22, fc[1] - 0.05, fc[2] + 0.38), (0.03, 0.5, 0.03), tone=DARK)
        m.hull("thumb", asm, bevel_box((fc[0] - s * 0.5, fc[1] + 0.05, fc[2] + 0.12), (0.16, 0.42, 0.42), 0.05), tone=0.8)
        if side == "R":
            # the SRM 4 (record sheet: right arm): a four-tube pod ON TOP of the forearm, above the fist (Daniel, from the TRO)
            # It sits FLAT on the hexagonal forearm's upper OUTER face (Daniel, 2026-11-18: the first build sat it on the top EDGE,
            # "not supported"; "rotated to the outer upper flat edge of the hexagon"), turned with that face and lying along the
            # forearm. The face: between the forearm's top corner and its upper outer corner (limb() sections, 6 sides).
            t_ = 0.69                                               # the pod's middle along the forearm, elbow -> wrist (its front at the wrist)
            w_ = 1.25 + (1.15 - 1.25) * t_
            d_ = (1.2 + (1.08 - 1.2) * t_) * (1 - 0.08 * (2 * t_ - 1) ** 2)
            fu = [wrist[i] - elbow[i] for i in range(3)]
            fl = math.sqrt(sum(c * c for c in fu))
            fu = [c / fl for c in fu]
            up_ = (0.0, fu[2], -fu[1])                              # across the forearm, upward
            lat = (s, 0.0, 0.0)                                     # across the forearm, OUTWARD (s = -1: the right arm)
            # in (outward, up) coordinates: the top corner (0, d/2), the upper outer corner (0.866 w/2, d/4)
            mid2 = (0.433 * w_ / 2, 0.75 * d_ / 2)
            nrm = (d_ / 4, 0.866 * w_ / 2)
            nl_ = math.hypot(*nrm)
            nrm = (nrm[0] / nl_, nrm[1] / nl_)
            N = tuple(lat[i] * nrm[0] + up_[i] * nrm[1] for i in range(3))
            S_ = tuple(lat[i] * nrm[1] - up_[i] * nrm[0] for i in range(3))      # along the face, across the forearm
            # (taller than first built, 0.7: its fire passed through the fist's top and cut a channel in the fist and forearm,
            # found 2026-11-18 by the weapon stress test; the check now reports such a cut)
            pw, ph, pl, sink = 0.82, 0.88, 1.0, 0.06
            base = [elbow[i] + fu[i] * fl * t_ + lat[i] * mid2[0] + up_[i] * mid2[1] for i in range(3)]
            pc_ = [base[i] + N[i] * (ph / 2 - sink) for i in range(3)]

            def pod_pt(q, c=pc_):
                return tuple(c[i] + q[0] * S_[i] + q[1] * N[i] + q[2] * fu[i] for i in range(3))
            front = pod_pt((0, 0, pl / 2 + 0.03))
            m.hull("srm4_pod", asm, [pod_pt(q) for q in bevel_box((0, 0, 0), (pw, ph, pl), 0.1)], tone=PLATE, role="weapon:RA:SRM 4",
                   fire={"from": rnd(front), "dir": rnd(fu), "r": 0.34})
            m.hull("pod_strap", asm, [pod_pt(q) for q in bevel_box((0, -0.12, -0.05), (pw + 0.06, 0.34, 0.12), 0.02)], tone=DARK)
            for cx in (-0.19, 0.19):
                for cy in (-0.17, 0.17):
                    m.tube("srm4_tube", asm, pod_pt((cx, cy, pl / 2 - 0.15)), pod_pt((cx, cy, pl / 2)), 0.3, n=12, tone=0.7)
                    m.tube("srm4_bore", asm, pod_pt((cx, cy, pl / 2)), pod_pt((cx, cy, pl / 2 + 0.015)), 0.19, n=12, tone=0.1)
        else:
            # the MEDIUM LASER (record sheet: left arm), IN LINE with the forearm (Daniel) on its outer face, sunk 0.42 of its diameter,
            # the muzzle past the fist's outer side so its fire is clear
            d_ = (0.0, wrist[1] - elbow[1], wrist[2] - elbow[2])
            ln_ = math.hypot(d_[1], d_[2])
            u = (0.0, d_[1] / ln_, d_[2] / ln_)
            bx = sh[0] + 0.625 + 0.32 * (0.5 - 0.42)
            p0 = (bx, elbow[1] + u[1] * 0.35, elbow[2] + u[2] * 0.35)
            p1 = (bx, elbow[1] + u[1] * 1.2, elbow[2] + u[2] * 1.2)
            p2 = (bx, elbow[1] + u[1] * 2.35, elbow[2] + u[2] * 2.35)
            m.tube("laser_housing", asm, p0, p1, 0.5, 0.46, n=12, tone=PLATE)
            m.tube("laser_barrel", asm, p1, p2, 0.32, 0.28, n=12, tone=METAL, role="weapon:LA:Medium Laser")
            m.tube("laser_bore", asm, p2, (bx, p2[1] + u[1] * 0.02, p2[2] + u[2] * 0.02), 0.17, n=12, tone=DARK)
        pivots["shoulder_" + side] = {"centre": rnd(sh), "axis": "x", "parent": "torso", "child": "upper arm"}
        pivots["elbow_" + side] = {"centre": rnd(elbow), "axis": "x", "parent": "upper arm", "child": "forearm"}
        pivots["wrist_" + side] = {"centre": rnd(wrist), "axis": "x", "parent": "forearm", "child": "fist"}
    # ---------------------------------------------------------------- the legs moved OUT to the sheet's spacing, then SPLAYED
    for i in range(leg_from, leg_end):
        p = m.parts[i]
        for key in ("a", "b", "c"):
            if key in p:
                p[key] = rnd((p[key][0] + LEG_OUT, p[key][1], p[key][2]))
        if "pts" in p:
            p["pts"] = [rnd((q[0] + LEG_OUT, q[1], q[2])) for q in p["pts"]]
    hip, knee, ankle = [(q[0] + LEG_OUT, q[1], q[2]) for q in (hip, knee, ankle)]
    # the splay: 3 degrees (the sheet's feet are 4.1 wide over all; the Catapult's 5 would put them at 4.4)
    splay = splay_legs(m, leg_from, leg_end, foot_from, hip, ankle, 3.0)
    pivots.update({"neck": {"centre": [0, 8.7, -0.08], "axis": "y", "parent": "torso", "child": "head"},     # HD review F4
                   "waist_turn": {"centre": [0, 5.72, 0], "axis": "y", "parent": "pelvis", "child": "torso"},
                   "hip_L": {"centre": list(hip), "axis": "x", "parent": "pelvis", "child": "thigh"},
                   "knee_L": {"centre": rnd(splay(knee)), "axis": "x", "parent": "thigh", "child": "shin"},
                   "ankle_L": {"centre": rnd(splay(ankle)), "axis": "x", "parent": "shin", "child": "foot"}})
    return {"unit": "Commando", "model": "COM-2D", "mass": 25, "detail": "hd", "stance": "ready", "pivots": pivots,
            "centre_of_mass": centre_of_mass(m.parts), "mounts": hidden,
            "poses": {"dynamic": {"hip_L": -22, "knee_L": 30, "ankle_L": -8, "hip_R": 16, "knee_R": 14, "ankle_R": -30,
                                  "waist_turn": 12, "neck": -10, "shoulder_R": -14, "shoulder_L": 8, "elbow_L": -12}},
            "scale": "ground to the dome's top = 10; +x is the 'Mech's left",
            "source": "AI five-view sheet, reference_art/ai_sheets/Commando COM-2D/gemini_1.webp (front and side measured on a grid and "
                      "with tools/lowpoly_measure.py); weapons and arms from the TRO drawing (reference_art/originals/01 Commando COM-2D.jpg)",
            "simplified_to": "reference_art/models/Commando COM-2D.json",
            "art_vs_unit_file": [
                "SRM 4 (right arm): a pod on top of the forearm above the fist (Daniel, from the TRO); the sheet draws no pod.",
                "SRM 6 (centre torso): on the round belly, the centre torso's mount (Daniel); the TRO draws it high on the chest.",
                "Round belly: kept for recognition (Daniel), not a pivot; it is the centre torso's weapon mount.",
                "Arms in a ready pose (forearms level, pointing ahead) so both arm weapons fire forward; the sheet's front view hangs them.",
                "Antenna on the right shoulder pad (the sheet's place; Daniel likes it). The sheet's top view (feet drawn backwards, Daniel) was not used.",
                "Head: a helmet whose skirt covers the back of the neck (the TRO, Daniel), a brow, a crest, a jaw with a grille.",
                "No jump jets (record sheet: jump 0)."],
            "parts": m.parts}


BUILDERS = {"Catapult CPLT-C1": catapult, "Commando COM-2D": commando}


def main(argv=()):
    os.makedirs(HD_DIR, exist_ok=True)
    for unit, fn in BUILDERS.items():
        if argv and not any(a.lower() in unit.lower() for a in argv):
            continue
        model = fn()
        path = os.path.join(HD_DIR, unit + ".json")
        with open(path, "w") as f:
            json.dump(model, f, indent=1)
        errors, notes = L.check_model(model)
        print(unit, "; ".join(notes), "; ".join(errors) or "ok")
        sheet(model, os.path.join(L.SHEETS, unit + " HD.png"))
        turnaround(model, os.path.join(L.SHEETS, unit + " HD turnaround.png"))


# (screen x, screen y, depth: larger = nearer). Seen from the front, the 'Mech's left (+x) is on the viewer's right; from behind, on
# the viewer's left. (Before 2026-11-18 the FRONT and REAR panels had x the wrong way round: unseen on the symmetric Catapult, found
# on the Commando, whose antenna and SRM 4 pod came out on the wrong side.)
FIVE_VIEWS = [("FRONT", lambda q: (q[0], q[1], q[2])), ("REAR", lambda q: (-q[0], q[1], -q[2])),
              ("LEFT SIDE", lambda q: (-q[2], q[1], q[0])), ("RIGHT SIDE", lambda q: (q[2], q[1], -q[0])),
              ("TOP-DOWN", lambda q: (q[0], -q[2], q[1]))]


def sheet(model, path):
    """The FIVE-VIEW format (Daniel, 2026-11-18: "use 5 fold format for display"), as the AI turnaround sheets: front, rear, left
    side, right side, top-down (forward down), on one scale, then the underside and a 3/4 view. Depth-buffer renderer
    (lowpoly_blocks.render)."""
    import lowpoly_blocks as B
    from PIL import Image, ImageDraw
    sol = L.expand_parts(model)
    views = FIVE_VIEWS + [("UNDERSIDE (forward up)", lambda q: (q[0], q[2], -q[1])), ("3/4 FRONT", B.camera(-35, 12))]
    H = 520
    fit = [s_ for s_ in sol]
    out = Image.new("RGB", (H * len(views), H + 44), "white")
    d = ImageDraw.Draw(out)
    loose = L.floating_parts(sol)                   # the no-floating-bits check on every render (Daniel, 2026-11-18)
    d.text((10, 6), "%s %s HD | %d triangles | five-view format, one scale | %s" % (
        model["unit"].upper(), model["model"], sum(x["tris"] for x in sol),
        ("FLOATING PARTS: " + ", ".join(loose[:6])) if loose else "no floating parts"), fill="red" if loose else "black")
    if loose:
        print("WARNING %s: floating parts %s" % (model["unit"], loose))
    for i, (name, f) in enumerate(views):
        scale_ref = fit if i >= 5 else _box_solid(sol)
        out.paste(B.render(sol, f, (H, H), fit_solids=scale_ref), (i * H, 44))
        d.text((i * H + 8, 26), name, fill="black")
    out.save(path)


TORSO_FIXED = ("shoulder_pad", "pad_trim", "mast_base", "mast")      # arm-assembly parts that belong to the torso (they do not swing)


def _rotate(p, c, axis, deg):
    """p turned deg degrees about the axis (a unit-ish vector, or "x" / "y" / "z") through c (Rodrigues)."""
    a = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}.get(axis, axis) if isinstance(axis, str) else axis
    n = math.sqrt(sum(v * v for v in a))
    k = [v / n for v in a]
    v = [p[i] - c[i] for i in range(3)]
    t = math.radians(deg)
    ct, st = math.cos(t), math.sin(t)
    kv = sum(k[i] * v[i] for i in range(3))
    cr = (k[1] * v[2] - k[2] * v[1], k[2] * v[0] - k[0] * v[2], k[0] * v[1] - k[1] * v[0])
    return tuple(c[i] + v[i] * ct + cr[i] * st + k[i] * kv * (1 - ct) for i in range(3))


def _pivot(model, name):
    """A pivot by name; a right-hand one (…_R) not recorded is the left one mirrored."""
    pv = model.get("pivots", {})
    if name in pv:
        return pv[name]
    if name.endswith("_R") and name[:-2] + "_L" in pv:
        q = pv[name[:-2] + "_L"]
        return dict(q, centre=[-q["centre"][0], q["centre"][1], q["centre"][2]])
    return None


def _chain(model, sol):
    """The pivots that move this solid, the nearest first (forward kinematics: the leaf's turn, then its parents')."""
    import re
    name = re.sub(r"_\d+.*$", "", sol["id"])
    asm, c = sol["assembly"], sol["centroid"]
    torso = [n for n in ("torso_tilt", "waist_turn") if _pivot(model, n)]
    if asm in ("leg_L", "leg_R"):
        sd = asm[-1]
        knee, ankle = _pivot(model, "knee_" + sd), _pivot(model, "ankle_" + sd)
        if c[1] < ankle["centre"][1] - 0.2:
            return ["ankle_" + sd, "knee_" + sd, "hip_" + sd]
        return ["hip_" + sd] if c[1] >= knee["centre"][1] - 0.05 else ["knee_" + sd, "hip_" + sd]
    if asm in ("arm_L", "arm_R"):
        sd = asm[-1]
        if name in TORSO_FIXED:
            return torso
        el, wr, sh = _pivot(model, "elbow_" + sd), _pivot(model, "wrist_" + sd), _pivot(model, "shoulder_" + sd)
        if not el:
            return ["shoulder_" + sd] + torso
        e, w_, s_ = el["centre"], wr["centre"], sh["centre"]

        def dist(a, b):
            ab = [b[i] - a[i] for i in range(3)]
            t = sum((c[i] - a[i]) * ab[i] for i in range(3)) / max(1e-9, sum(x * x for x in ab))
            q = [a[i] + ab[i] * min(1.0, max(0.0, t)) for i in range(3)]
            return math.dist(c, q), t
        du, _ = dist(s_, e)
        df, tf = dist(e, w_)
        if tf > 1.0 and name not in ("srm4_pod", "srm4_tube", "srm4_bore", "pod_strap", "laser_barrel", "laser_bore"):
            return ["wrist_" + sd, "elbow_" + sd, "shoulder_" + sd] + torso
        return (["shoulder_" + sd] if du < df else ["elbow_" + sd, "shoulder_" + sd]) + torso
    if asm == "head":
        return (["neck"] if _pivot(model, "neck") else []) + torso
    if asm == "torso":
        return torso
    if asm == "pelvis" and name in ("waist_tower", "waist_pyramid"):
        return ["waist_turn"]
    return []


def posed_solids(model, pose):
    """The model's solids in a POSE (pivot name -> degrees; a missing pivot stays at 0), set back on the ground. Display only: the
    checks run on the model as built."""
    sol = L.expand_parts(model)
    out = []
    for s_ in sol:
        vs = s_["verts"]
        for pn in _chain(model, s_):
            ang = pose.get(pn, 0.0)
            pv = _pivot(model, pn)
            if ang and pv:
                vs = [_rotate(v, pv["centre"], pv["axis"], ang) for v in vs]
        out.append(dict(s_, verts=vs))
    low = min(v[1] for s_ in out for v in s_["verts"])
    res = []
    for s_ in out:
        vs = [(v[0], v[1] - low, v[2]) for v in s_["verts"]]
        # the centroid moves with the solid (the renderer uses it to tell a face's outside from its inside: left behind, the turned
        # parts drew inside-out - the Catapult's launcher tubes scattered, the Commando's forearm blank)
        cen = tuple(sum(v[i] for v in vs) / len(vs) for i in range(3))
        res.append(dict(s_, verts=vs, centroid=cen))
    return res


def turnaround(model, path, H=720):
    """A presentation five-view, laid out as the AI turnaround sheets (Daniel, 2026-11-18: "a good 5 fold view"): the top-down view
    above, then front, rear, left side and right side in a row, ALL ON ONE SCALE (each panel is framed on the same cube round the
    model, then trimmed of empty margin), and two 3/4 views. The floating-parts stamp as on `sheet`."""
    import lowpoly_blocks as B
    from PIL import Image, ImageDraw, ImageChops
    sol = L.expand_parts(model)
    cube = _box_solid(sol)

    def trim(im, rows=False):
        bg = Image.new("RGB", im.size, "white")
        box = ImageChops.difference(im, bg).getbbox() or (0, 0, im.width, im.height)
        pad = 18
        l, t, r, b = max(0, box[0] - pad), max(0, box[1] - pad), min(im.width, box[2] + pad), min(im.height, box[3] + pad)
        return im.crop((l, t, r, b) if rows else (l, 0, r, im.height))
    views = dict(FIVE_VIEWS)
    row2 = [(n, trim(B.render(sol, views[n], (H, H), fit_solids=cube))) for n in ("FRONT", "REAR", "LEFT SIDE", "RIGHT SIDE")]
    top = trim(B.render(sol, views["TOP-DOWN"], (H, H), fit_solids=cube), rows=True)
    q34 = [(n, trim(B.render(sol, f, (H // 2 + 120, H // 2 + 120)), rows=True)) for n, f in
           (("3/4 FRONT", B.camera(-35, 12)), ("3/4 REAR", B.camera(-145, 12)))]
    # a DYNAMIC POSE (Daniel, 2026-11-18: "5 views, 3/4 views, Think we need at least one Dynamic pose view too"): the model turned
    # about its own pivots (`poses` in the model), so the view also shows whether the joints really work
    if model.get("poses", {}).get("dynamic"):
        q34.append(("DYNAMIC POSE", trim(B.render(posed_solids(model, model["poses"]["dynamic"]), B.camera(-30, 14),
                                                  (H // 2 + 120, H // 2 + 120)), rows=True)))
    gap, head = 30, 64
    w2 = sum(im.width for _, im in row2) + gap * (len(row2) + 1)
    h1 = max(top.height, max(im.height for _, im in q34)) + 30
    out = Image.new("RGB", (max(w2, top.width + sum(im.width for _, im in q34) + gap * 4), head + h1 + H + 40), "white")
    d = ImageDraw.Draw(out)
    loose = L.floating_parts(sol)
    d.text((gap, 14), "%s %s  -  HD REFERENCE MODEL, TURNAROUND" % (model["unit"].upper(), model["model"]), fill="black")
    d.text((gap, 34), "%d t | %d solids, %d triangles | top, front, rear and side views on one scale (the 3/4 views are not) | %s" % (
        model.get("mass", 0), len(sol), sum(x["tris"] for x in sol),
        ("FLOATING PARTS: " + ", ".join(loose[:6])) if loose else "no floating parts"), fill="red" if loose else "black")
    x = gap
    for n, im in [("TOP-DOWN (forward down)", top)] + q34:
        out.paste(im, (x, head + 20))
        d.text((x + 6, head + 2), n, fill="black")
        x += im.width + gap
    x, y = gap, head + h1 + 20
    for n, im in row2:
        out.paste(im, (x, y))
        d.text((x + 6, y - 18), n, fill="black")
        x += im.width + gap
    d.line([(gap, y + H - 1), (out.width - gap, y + H - 1)], fill=(170, 170, 170))       # the ground line
    out.save(path)


def _box_solid(sol):
    """A cube round the whole model: framing every five-view panel on it keeps one scale in all five."""
    pts = [v for s_ in sol for v in s_["verts"]]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    c = [(lo[i] + hi[i]) / 2 for i in range(3)]
    h = max(hi[i] - lo[i] for i in range(3)) / 2
    return [{"verts": [(c[0] + a * h, c[1] + b * h, c[2] + e * h) for a in (-1, 1) for b in (-1, 1) for e in (-1, 1)], "faces": []}]

if __name__ == "__main__":
    main(sys.argv[1:])
