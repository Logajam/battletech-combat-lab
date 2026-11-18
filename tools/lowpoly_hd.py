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
    first = True
    for z0, z1 in zip(z_cuts, z_cuts[1:]):
        for t0, t1 in zip(theta_cuts, theta_cuts[1:]):
            za, zb = z0 - gap / 2, z1 + gap / 2                # z falls toward the back: z0 > z1
            ta, tb = t0 + gap / 3, t1 - gap / 3
            pts = []
            for z in (za, (za + zb) / 2, zb):
                for t in (ta, (ta + tb) / 2, tb):
                    pts.append(surface_point(secs, z, t, 0.035))
                    pts.append(surface_point(secs, z, t, -0.01))
            m.hull(name, "head", pts, tone=0.26, role=role_first if first else None)
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


def catapult():
    m = Model()
    # ---------------------------------------------------------------- the body: a rounded teardrop (side heights, top widths)
    # z, y_top, y_bottom, half-width across the top, at the widest, across the bottom
    secs = [(4.11, 8.12, 7.98, 0.03, 0.05, 0.03), (3.90, 8.45, 7.70, 0.22, 0.32, 0.22), (3.45, 8.82, 7.42, 0.45, 0.66, 0.50),
            (3.00, 9.00, 7.12, 0.66, 0.92, 0.72), (2.57, 9.12, 6.98, 0.82, 1.12, 0.88), (1.80, 9.38, 6.95, 0.98, 1.32, 1.02),
            (1.08, 9.62, 6.98, 1.08, 1.42, 1.08), (0.17, 9.95, 7.12, 1.12, 1.48, 1.10), (-1.10, 9.98, 7.55, 1.10, 1.45, 1.06),
            (-2.10, 9.90, 7.95, 1.02, 1.36, 0.98), (-2.35, 9.70, 8.15, 0.85, 1.15, 0.80)]
    for (z0, t0, b0, a0, m0, c0), (z1, t1, b1, a1, m1, c1) in zip(secs, secs[1:]):     # one convex slice between two sections
        m.hull("body", "torso", rounded_section(z0, t0, b0, a0, m0, c0) + rounded_section(z1, t1, b1, a1, m1, c1), tone=0.9)
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
        m.box("stripe", "torso", (jx + jd / 2 + 0.005, jy, 1.4 + k * 0.24), (0.03, 0.42, 0.09), tone=DARK, mirror=True)
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
    # ---------------------------------------------------------------- the arms: LRM 15 launchers on their shoulder discs
    # (record sheet: shoulder + upper arm actuator + LRM 15) - front x 1.60, width 1.45, y 8.6-11.1, z -2.54 .. 0.11
    m.tube("shoulder", "arm_L", (1.2, 9.3, -0.85), (2.2, 9.3, -0.85), 1.35, n=28, tone=JOINT, mirror=True)
    m.tube("shoulder_ring", "arm_L", (2.2, 9.3, -0.85), (2.32, 9.3, -0.85), 1.35, 1.1, n=28, tone=TRIM, mirror=True)
    m.tube("shoulder_hub", "arm_L", (2.32, 9.3, -0.85), (2.4, 9.3, -0.85), 0.5, n=20, tone=DARK, mirror=True)
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
    # ---------------------------------------------------------------- the lower torso: waist, side discs, hip block and hip discs
    # the TORSO TILT HINGE (Daniel: "That round section was the hinge that allowed the torso to tilt up and down"): a drum across
    # the body's underside, axis x, at the round section of the side view (y 7.45, z 0.55); a hub ring at each end
    hinge = (0.0, 7.45, 0.55)
    m.tube("tilt_hinge", "torso", (-1.55, hinge[1], hinge[2]), (1.55, hinge[1], hinge[2]), 1.2, n=28, tone=JOINT)
    m.tube("tilt_hub", "torso", (1.55, hinge[1], hinge[2]), (1.62, hinge[1], hinge[2]), 0.55, n=20, tone=DARK, mirror=True)
    m.tube("tilt_ring", "torso", (1.4, hinge[1], hinge[2]), (1.56, hinge[1], hinge[2]), 1.28, n=28, tone=TRIM, mirror=True)
    # the WAIST: an octagonal tower rising from the hip block, tilted so it meets the hinge squarely, topped by a pyramid that
    # closes round the hinge (Daniel: "a mix of octagon tower and pyramid"); the waist turns the torso, the hinge tilts it
    # its root is a BALL sunk in the hip block and a COWL rings it at the block's top (Daniel, 2026-11-18: the tilted tower's bottom
    # poked out of the hip block; "a cowl, or building waist blocks with extra structure (like a hemisphere) that is usually inside
    # the hip block if flat"): however the tower leans, its root stays inside
    top = (0.0, hinge[1] - 0.15, hinge[2] - 0.05)
    lean = (0.0, top[1] - 6.35, top[2] + 0.05)
    ln = math.hypot(lean[1], lean[2])
    base = (0.0, 6.35 - 0.3 * lean[1] / ln, -0.05 - 0.3 * lean[2] / ln)       # 0.3 further down the tower's own axis
    m.add("dome", "waist_ball", "pelvis", c=base, r=(0.8, 0.8, 0.8), n=20, rings=10, tone=JOINT)
    m.tube("waist_cowl", "pelvis", (0.0, 6.5, -0.05), (0.0, 6.82, -0.02), 1.95, 1.72, n=8, roll=22.5, tone=0.7)
    mid = (0.0, base[1] + (top[1] - base[1]) * 0.55, base[2] + (top[2] - base[2]) * 0.55)
    m.tube("waist_tower", "pelvis", base, mid, 1.5, 1.42, n=8, roll=22.5, tone=0.68)
    m.tube("waist_pyramid", "pelvis", mid, top, 1.42, 0.95, n=8, roll=22.5, tone=0.68)
    m.hull("pelvis", "pelvis", bevel_box((0.0, 5.8, 0.0), (1.67, 1.5, 2.15), 0.3), tone=0.74)
    for k in range(3):
        m.box("pelvis_vent", "pelvis", (0.0, 5.45 + k * 0.15, 1.11), (1.0, 0.06, 0.02), tone=DARK)
    m.tube("hip_disc", "pelvis", (0.75, 5.72, 0.0), (1.02, 5.72, 0.0), 1.45, n=28, tone=JOINT, mirror=True)
    m.tube("hip_ring", "pelvis", (1.02, 5.72, 0.0), (1.08, 5.72, 0.0), 1.45, 1.2, n=28, tone=TRIM, mirror=True)
    # ---------------------------------------------------------------- the legs: reverse knee (side view), x 1.52
    # the thigh: a big rounded block, hip (y 5.72, z 0) down and BACK to the knee (y 4.31, z -1.68)
    # the hip at the hip discs' axis, so the thigh turns about it (Daniel: "circular end caps on the legs that engage with the
    # circular hip connecting points")
    hip, knee, ankle = (1.52, 5.72, 0.0), (1.52, 4.3, -1.68), (1.52, 0.72, 1.08)
    leg_from = len(m.parts)
    m.tube("thigh_cap", "leg_L", (1.06, hip[1], hip[2]), (2.02, hip[1], hip[2]), 1.4, n=28, tone=JOINT, mirror=True)
    m.tube("thigh_cap_ring", "leg_L", (2.02, hip[1], hip[2]), (2.1, hip[1], hip[2]), 1.4, 1.05, n=28, tone=TRIM, mirror=True)
    m.tube("thigh_cap_hub", "leg_L", (2.1, hip[1], hip[2]), (2.16, hip[1], hip[2]), 0.5, n=20, tone=DARK, mirror=True)

    def limb(name, a, b, w0, d0, w1, d1, steps=4):
        """A rounded limb between a and b: slices of rounded sections (width w, depth d) turned along a->b (y-z plane)."""
        ax = (b[1] - a[1], b[2] - a[2])
        ln = math.hypot(*ax)
        uy, uz = ax[0] / ln, ax[1] / ln            # along the limb
        ny, nz = -uz, uy                           # across it, in the side plane (depth)
        rings = []
        for i in range(steps + 1):
            t = i / steps
            cy, cz = a[1] + ax[0] * t, a[2] + ax[1] * t
            w = w0 + (w1 - w0) * t
            d = (d0 + (d1 - d0) * t) * (1 - 0.15 * (2 * t - 1) ** 2 if steps > 1 else 1)
            ring = []
            for k in range(16):
                th = 2 * math.pi * k / 16
                ring.append((a[0] + w / 2 * math.cos(th), cy + ny * d / 2 * math.sin(th), cz + nz * d / 2 * math.sin(th)))
            rings.append(ring)
        for r0, r1 in zip(rings, rings[1:]):
            m.hull(name, "leg_L", r0 + r1, tone=0.72, mirror=True)
    limb("thigh", hip, knee, 1.1, 1.55, 0.95, 1.15)
    m.tube("knee_cap", "leg_L", (0.95, knee[1], knee[2] - 0.05), (2.1, knee[1], knee[2] - 0.05), 1.05, n=24, tone=JOINT, mirror=True)
    m.tube("knee_hub", "leg_L", (2.1, knee[1], knee[2] - 0.05), (2.16, knee[1], knee[2] - 0.05), 0.45, n=16, tone=DARK, mirror=True)
    limb("shin", knee, ankle, 0.92, 1.0, 0.78, 0.82, steps=5)
    # armour plate down the shin's front and a vent hatch on its side
    m.add("bar", "shin_plate", "leg_L", a=(1.52, 3.6, -0.85), b=(1.52, 1.3, 0.75), w0=[0.7, 0.18], w1=[0.6, 0.16], tone=PLATE, mirror=True)
    for k in range(5):
        m.box("shin_vent", "leg_L", (1.98, 2.9 - k * 0.14, -0.15 + k * 0.1), (0.03, 0.06, 0.5), tone=DARK, mirror=True)
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
    m.tube("ankle_hub", "leg_L", (2.12, 0.85, on_shin(0.85) - 0.1), (2.24, 0.85, on_shin(0.85) - 0.1), 0.55, n=20, tone=JOINT, mirror=True)
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
    cg = centre_of_mass(m.parts)
    d = 1.43
    for k, z in enumerate((cg[2] + d, cg[2] - d)):
        if k == 0:
            y_top = 7.15                                    # the jowl's underside
        else:                                               # the body's underside AT the nozzle's x (it curves up to the sides)
            under = [surface_point(secs, z, -math.pi / 2 + i * 0.02) for i in range(80)]
            y_top = min(under, key=lambda q: abs(q[0] - 1.12))[1] + 0.05
        m.tube("jj_mount", "torso", (1.12, y_top + 0.12, z), (1.12, y_top - 0.18, z), 0.5, 0.46, n=16, tone=METAL, mirror=True)
        m.tube("jj", "torso", (1.12, y_top - 0.18, z), (1.12, y_top - 0.62, z), 0.36, 0.6, n=20, tone=0.45, mirror=True,
               role="jumpjet:LT" if k == 0 else None)
        m.tube("jj_throat", "torso", (1.12, y_top - 0.62, z), (1.12, y_top - 0.64, z), 0.48, n=20, tone=DARK, mirror=True)
    # SPLAY (Daniel: "the legs are splayed out slightly"): the leg turns about the hip by LEG_SPLAY degrees, foot outward; the foot
    # follows the ankle but stays flat on the ground
    a = math.radians(LEG_SPLAY)

    def splay(q):
        dx, dy = q[0] - hip[0], q[1] - hip[1]
        return (hip[0] + dx * math.cos(a) - dy * math.sin(a), hip[1] + dx * math.sin(a) + dy * math.cos(a), q[2])
    shift = splay(ankle)[0] - ankle[0]
    for i in range(leg_from, len(m.parts)):
        p = m.parts[i]
        f = (lambda q: (q[0] + shift, q[1], q[2])) if i >= foot_from else splay
        for key in ("a", "b", "c"):
            if key in p:
                p[key] = rnd(f(p[key]))
        if "pts" in p:
            p["pts"] = [rnd(f(q)) for q in p["pts"]]
        if i < foot_from and p["kind"] in ("box", "wedge"):
            p["rot"] = [0, 0, LEG_SPLAY]
    # the PIVOTS, for animation: centre and axis of every joint (the left side; mirror x for the right)
    pivots = {"torso_tilt": {"centre": list(hinge), "axis": "x", "parent": "waist", "child": "torso"},
              "waist_turn": {"centre": rnd(base), "axis": rnd([0, top[1] - base[1], top[2] - base[2]]), "parent": "pelvis", "child": "waist"},
              "hip_L": {"centre": list(hip), "axis": "x", "parent": "pelvis", "child": "thigh"},
              "knee_L": {"centre": rnd(splay(knee)), "axis": "x", "parent": "thigh", "child": "shin"},
              "ankle_L": {"centre": rnd(splay(ankle)), "axis": "x", "parent": "shin", "child": "foot"},
              "shoulder_L": {"centre": [1.8, 9.3, -0.85], "axis": "x", "parent": "torso", "child": "launcher arm"}}
    return {"unit": "Catapult", "model": "CPLT-C1", "mass": 65, "detail": "hd", "stance": "a_stance", "pivots": pivots,
            "centre_of_mass": centre_of_mass(m.parts),
            "scale": "ground to the body's top = 10; +x is the 'Mech's left",
            "source": "AI five-view sheet, reference_art/ai_sheets/Catapult CPLT-C1/batch2_1.webp (measured on a grid; tools/lowpoly_hd.py)",
            "simplified_to": "reference_art/models/Catapult CPLT-C1.json",
            "art_vs_unit_file": [
                "LRM 15s in the arms (record sheet: shoulder + upper arm actuator + LRM 15): the launchers ARE the arms, on the shoulder discs.",
                "The art draws one launcher raised (a pose): both built level.",
                "Medium lasers: the LT / RT lasers are housed in the 'jowls' low on the body's sides (Daniel); the two CT lasers in the chin. Jump jets (not drawn) under the back.",
                "Each view scaled to its own body-top height (the side view is drawn ~10 % taller than the front)."],
            "parts": m.parts}


BUILDERS = {"Catapult CPLT-C1": catapult}


def main():
    os.makedirs(HD_DIR, exist_ok=True)
    for unit, fn in BUILDERS.items():
        model = fn()
        path = os.path.join(HD_DIR, unit + ".json")
        with open(path, "w") as f:
            json.dump(model, f, indent=1)
        errors, notes = L.check_model(model)
        print(unit, "; ".join(notes), "; ".join(errors) or "ok")
        sheet(model, os.path.join(L.SHEETS, unit + " HD.png"))


FIVE_VIEWS = [("FRONT", lambda q: (-q[0], q[1], q[2])), ("REAR", lambda q: (q[0], q[1], -q[2])),
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
    d.text((10, 6), "%s %s HD | %d triangles | five-view format, one scale" % (model["unit"].upper(), model["model"],
                                                                                 sum(x["tris"] for x in sol)), fill="black")
    for i, (name, f) in enumerate(views):
        scale_ref = fit if i >= 5 else _box_solid(sol)
        out.paste(B.render(sol, f, (H, H), fit_solids=scale_ref), (i * H, 44))
        d.text((i * H + 8, 26), name, fill="black")
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
    main()
