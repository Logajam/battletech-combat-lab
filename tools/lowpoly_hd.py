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
    # the hazard-striped intakes either side of the nose (the striped slots in the side view)
    m.hull("intake", "torso", [(1.05, 8.05, 2.1), (1.05, 7.55, 2.1), (1.05, 8.0, 1.1), (1.05, 7.5, 1.1),
                               (1.2, 7.98, 2.0), (1.2, 7.6, 2.0), (1.2, 7.95, 1.2), (1.2, 7.55, 1.2)], tone=0.82, mirror=True)
    for k in range(4):
        m.box("stripe", "torso", (1.21, 7.77, 1.25 + k * 0.22), (0.02, 0.4, 0.09), tone=DARK, mirror=True)
    # ---------------------------------------------------------------- the cockpit: framed glazing on the nose's upper faces
    for i, (z0, z1) in enumerate(((3.85, 3.42), (3.40, 2.95), (2.93, 2.55))):
        for side in (-1, 1):
            m.hull("pane", "head", [(side * 0.05, 8.42 + i * 0.3, z0), (side * 0.05, 8.72 + i * 0.25, z1),
                                    (side * (0.32 + i * 0.18), 8.32 + i * 0.25, z0 - 0.05), (side * (0.5 + i * 0.2), 8.6 + i * 0.22, z1),
                                    (side * 0.05, 8.38 + i * 0.3, z0), (side * 0.05, 8.68 + i * 0.25, z1)],
                   tone=0.28, role="canopy" if (i == 0 and side == 1) else None)
    m.box("canopy_frame", "head", (0, 8.95, 2.75), (0.08, 0.06, 1.6), tone=TRIM)
    # the side-torso medium lasers under the launchers' fronts, and the jump jets (2 LT, 2 RT) under the back
    m.tube("ml_side", "torso", (1.28, 8.25, 0.35), (1.28, 8.25, 1.2), 0.26, n=12, role="weapon:LT:Medium Laser", tone=METAL, mirror=True)
    m.tube("ml_side_bore", "torso", (1.28, 8.25, 1.2), (1.28, 8.25, 1.23), 0.16, n=12, tone=DARK, mirror=True)
    for k, z in enumerate((-1.35, -1.95)):
        m.tube("jj", "torso", (0.75, 8.05, z), (0.75, 7.5, z), 0.42, 0.62, n=16, tone=0.45, mirror=True,
               role="jumpjet:LT" if k == 0 else None)
        m.tube("jj_throat", "torso", (0.75, 7.5, z), (0.75, 7.48, z), 0.5, n=16, tone=DARK, mirror=True)
    # ---------------------------------------------------------------- the hatch deck between the launchers (the X box)
    m.hull("deck", "torso", [(-0.8, 9.9, -2.3), (0.8, 9.9, -2.3), (-0.8, 9.9, 0.05), (0.8, 9.9, 0.05),
                             (-0.72, 10.42, -2.2), (0.72, 10.42, -2.2), (-0.72, 10.42, -0.05), (0.72, 10.42, -0.05)], tone=0.95)
    for a, b in (((-0.6, -2.05), (0.6, -0.2)), ((0.6, -2.05), (-0.6, -0.2))):           # the X on the hatch
        m.add("bar", "deck_x", "torso", a=(a[0], 10.43, a[1]), b=(b[0], 10.43, b[1]), w0=[0.07, 0.02], w1=[0.07, 0.02], tone=DARK)
    m.box("deck_rim", "torso", (0, 10.43, -1.12), (1.3, 0.03, 1.95), tone=0.8)
    # ---------------------------------------------------------------- the arms: LRM 15 launchers on their shoulder discs
    # (record sheet: shoulder + upper arm actuator + LRM 15) - front x 1.60, width 1.45, y 8.6-11.1, z -2.54 .. 0.11
    m.tube("shoulder", "arm_L", (1.2, 9.3, -0.85), (2.2, 9.3, -0.85), 1.35, n=28, tone=JOINT, mirror=True)
    m.tube("shoulder_ring", "arm_L", (2.2, 9.3, -0.85), (2.32, 9.3, -0.85), 1.35, 1.1, n=28, tone=TRIM, mirror=True)
    m.tube("shoulder_hub", "arm_L", (2.32, 9.3, -0.85), (2.4, 9.3, -0.85), 0.5, n=20, tone=DARK, mirror=True)
    m.hull("rack", "arm_L", [(x, y, z) for x in (0.88, 2.32) for y in (8.6, 11.1) for z in (-2.54, 0.0)] +
           [(x, 11.2, z) for x in (0.98, 2.22) for z in (-2.44, -0.1)], tone=PLATE, role="weapon:LA:LRM 15", mirror=True)
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
    m.hull("waist", "pelvis", [(x, y, z) for x in (-0.65, 0.65) for y in (6.5, 7.15) for z in (-0.5, 0.95)], tone=0.68)
    m.tube("body_disc", "torso", (1.2, 7.4, 0.58), (1.55, 7.4, 0.58), 1.2, n=24, tone=JOINT, mirror=True)
    m.tube("body_disc_dot", "torso", (1.55, 7.4, 0.58), (1.59, 7.4, 0.58), 0.35, n=16, tone=DARK, mirror=True)
    m.hull("pelvis", "pelvis", [(x, y, z) for x in (-0.84, 0.84) for y in (5.15, 6.45) for z in (-0.95, 0.95)] +
           [(x, y, z) for x in (-0.7, 0.7) for y in (5.05, 6.55) for z in (-1.08, 1.1)], tone=0.74)
    for k in range(3):
        m.box("pelvis_vent", "pelvis", (0.0, 5.45 + k * 0.15, 1.11), (1.0, 0.06, 0.02), tone=DARK)
    m.tube("hip_disc", "pelvis", (0.75, 5.72, 0.0), (1.02, 5.72, 0.0), 1.45, n=28, tone=JOINT, mirror=True)
    m.tube("hip_ring", "pelvis", (1.02, 5.72, 0.0), (1.08, 5.72, 0.0), 1.45, 1.2, n=28, tone=TRIM, mirror=True)
    # ---------------------------------------------------------------- the legs: reverse knee (side view), x 1.52
    # the thigh: a big rounded block, hip (y 5.72, z 0) down and BACK to the knee (y 4.31, z -1.68)
    hip, knee, ankle = (1.52, 5.95, 0.15), (1.52, 4.3, -1.68), (1.52, 0.72, 1.08)

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
    m.tube("ankle", "leg_L", (1.05, 0.78, 1.08), (2.0, 0.78, 1.08), 0.7, n=20, tone=JOINT, mirror=True)
    # the foot: a long sole (side x 84-218, toes forward), three toe plates splayed, a heel spur; splayed 18 degrees outward
    toes = []
    for k, (dx, ln) in enumerate(((-0.42, 1.35), (0.0, 1.55), (0.42, 1.35))):
        toes.append([(1.52 + dx - 0.2, 0, 0.9), (1.52 + dx + 0.2, 0, 0.9), (1.52 + dx - 0.16, 0, 0.9 + ln), (1.52 + dx + 0.16, 0, 0.9 + ln),
                     (1.52 + dx - 0.18, 0.42, 0.95), (1.52 + dx + 0.18, 0.42, 0.95), (1.52 + dx - 0.1, 0.12, 0.85 + ln),
                     (1.52 + dx + 0.1, 0.12, 0.85 + ln)])
    for t in toes:
        m.hull("toe", "leg_L", t, tone=0.74, mirror=True, rot=[0, 18, 0])
    m.hull("instep", "leg_L", [(0.85, 0, -0.25), (2.2, 0, -0.25), (0.85, 0, 1.0), (2.2, 0, 1.0),
                               (1.1, 0.62, -0.05), (1.95, 0.62, -0.05), (1.1, 0.6, 0.95), (1.95, 0.6, 0.95)], tone=0.7, mirror=True, rot=[0, 18, 0])
    m.add("wedge", "heel", "leg_L", c=(1.52, 0.2, -0.65), s=(0.7, 0.4, 0.9), high="+z", tone=0.74, mirror=True, rot=[0, 18, 0])
    return {"unit": "Catapult", "model": "CPLT-C1", "mass": 65, "detail": "hd", "stance": "a_stance",
            "scale": "ground to the body's top = 10; +x is the 'Mech's left",
            "source": "AI five-view sheet, reference_art/ai_sheets/Catapult CPLT-C1/batch2_1.webp (measured on a grid; tools/lowpoly_hd.py)",
            "simplified_to": "reference_art/models/Catapult CPLT-C1.json",
            "art_vs_unit_file": [
                "LRM 15s in the arms (record sheet: shoulder + upper arm actuator + LRM 15): the launchers ARE the arms, on the shoulder discs.",
                "The art draws one launcher raised (a pose): both built level.",
                "Medium lasers and jump jets are not drawn: placed where the record sheet's locations allow (LT / RT lasers under the launchers' fronts, CT lasers in the chin, jets under the back).",
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


def sheet(model, path):
    """Front, side, top and two 3/4 views with the depth-buffer renderer (lowpoly_blocks.render: lowpoly_ref's face sort mis-orders
    the many overlapping parts of an HD model)."""
    import lowpoly_blocks as B
    from PIL import Image, ImageDraw
    sol = L.expand_parts(model)
    views = [("FRONT", lambda q: (-q[0], q[1], q[2])), ("LEFT SIDE", lambda q: (-q[2], q[1], q[0])),
             ("TOP (forward down)", lambda q: (q[0], -q[2], q[1])), ("3/4 FRONT", B.camera(-35, 12)), ("3/4 REAR", B.camera(145, 15))]
    H = 520
    out = Image.new("RGB", (H * len(views), H + 40), "white")
    d = ImageDraw.Draw(out)
    d.text((10, 6), "%s %s HD | %d triangles" % (model["unit"].upper(), model["model"], sum(x["tris"] for x in sol)), fill="black")
    for i, (name, f) in enumerate(views):
        out.paste(B.render(sol, f, (H, H)), (i * H, 40))
        d.text((i * H + 8, 24), name, fill="black")
    out.save(path)


if __name__ == "__main__":
    main()
