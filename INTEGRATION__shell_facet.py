"""
INTEGRATION__shell_facet.py  (NEW 2026-11-04, Claude - Combat Lab art EXPERIMENT, output only)

A second look for the skeleton-and-shell model, tried on the Mad Cat first (Daniel, 2026-11-04: a low-poly Mad Cat print "arguably
looks more refined than the blocks we currently have"; "Lets experiment with the madcat. See if its worth pursuing").

What changes against INTEGRATION__shell (the "plated" look):
  * ONE designed solid per part: limbs are faceted prisms (octagons, chamfered ends), joints are drums across the joint, the torso
    is one teardrop canopy, feet are claws. No plates stuck on faces.
  * SILHOUETTE and POSE first: body pitched forward, arms raised as forward-aimed gun pods, launchers on posts above the shoulders,
    a wide digitigrade stance.
  * Everything else is shared: the mass budgets, the hardpoints and their shuffle, the layers (skeleton, myomer, internal
    equipment), the rules height. Each location's solids are still fitted to its volume budget.
Only units that `use_facet` accepts are built this way, and only when build_model is asked for style "facet".
"""

import math

import numpy as np

import INTEGRATION__tokens as T
import INTEGRATION__shell as SH
import INTEGRATION__shell_items as I
from INTEGRATION__shell import Frame, lbox, cyl, Solid, Sink, fit, hull_vol, item_dims, item_geometry, _u

FACET_RANGE = ("mad cat", "timber wolf")


def use_facet(unit):
    names = {unit.get("chassis", "").lower(), unit.get("clanname", "").lower()}
    return bool(names & set(FACET_RANGE))


def _basis(a, lat):
    a = _u(a)
    lat = np.asarray(lat, float)
    ex = lat - (lat @ a) * a
    if np.linalg.norm(ex) < 1e-6:
        ex = np.array([0.0, 0, 1]) - a[2] * a
    ex = _u(ex)
    return a, ex, np.cross(a, ex)


def prism(p0, p1, w0, d0, w1=None, d1=None, n=8, ch=0.12, lat=(1, 0, 0)):
    """A faceted prism from p0 to p1: an n-gon of half-sizes (w along `lat`, d across) at each end, flat faces top and bottom,
    both ends chamfered by `ch` of the smaller size. The building block of this style (limbs, drums, pods, posts)."""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    w1 = w0 if w1 is None else w1
    d1 = d0 if d1 is None else d1
    a, ex, ey = _basis(p1 - p0, lat)
    L = np.linalg.norm(p1 - p0)
    e = min(ch * min(w0, d0, w1, d1) * 2, 0.3 * L)
    pts = []
    for t, k in ((0.0, 0.8), (e / L, 1.0), (1 - e / L, 1.0), (1.0, 0.8)):
        c = p0 + (p1 - p0) * t
        w, d = (w0 + (w1 - w0) * t) * k, (d0 + (d1 - d0) * t) * k
        for i in range(n):
            ang = 2 * math.pi * (i + 0.5) / n
            pts.append(c + ex * w * math.cos(ang) + ey * d * math.sin(ang))
    return np.array(pts)


def canopy(yc, z0, L, W, H, pitch):
    """The torso: one faceted teardrop, wide and tall at the back, a pointed nose; stations along y, an octagon each, pitched
    nose-down by `pitch` (radians) about its centre."""
    # (u along the body -1 rear .. 1 nose, half-width, bottom, top) as fractions
    st = [(-1.0, 0.70, 0.22, 0.80), (-0.7, 0.96, 0.05, 1.0), (-0.1, 1.0, 0.0, 0.98), (0.45, 0.78, 0.1, 0.8), (0.82, 0.42, 0.28, 0.6), (1.0, 0.16, 0.4, 0.5)]
    pts = []
    for u, hw, zb, zt in st:
        y = yc + u * L / 2
        zm, hz = (zb + zt) / 2 * H, (zt - zb) / 2 * H
        for i in range(8):
            ang = 2 * math.pi * (i + 0.5) / 8
            pts.append((hw * W / 2 * math.cos(ang), y, z0 + zm + hz * math.sin(ang)))
    pts = np.array(pts)
    c = np.array([0, yc, z0 + H / 2])
    cs, sn = math.cos(pitch), math.sin(pitch)
    d = pts - c
    return c + np.stack([d[:, 0], d[:, 1] * cs + d[:, 2] * sn, -d[:, 1] * sn + d[:, 2] * cs], 1)


class FCtx(SH.Ctx):
    pass


def assemble(model, P, S, Hm):
    cx = FCtx(model, P, S, Hm)
    cx.geoms, cx.arm_axis, cx.arm_j, cx.sec, cx.leg_j = {}, {}, {}, {}, {}
    out = []                                         # (pts, cls, role, name, loc)
    ext = {}
    for zone, lst in P["items"].items():
        if zone == "_cap":
            continue
        for it in lst:
            if it["visible"]:
                L, W, Hh = item_dims(it, Hm)
                g = item_geometry(it, L, W, Hh)
                cx.geoms[id(it)] = (L, W, Hh, g)
                ext[zone] = ext.get(zone, 0.0) + SH.item_volume(g)
    env = {z: max(0.4 * P["budget"][z], P["budget"][z] - ext.get(z, 0.0)) for z in P["budget"]}
    vol = SH.vol_of

    # ---- legs: digitigrade, three faceted segments, drums at knee and hock, a claw foot
    zh = 0.50 * Hm
    J0 = {"hip": np.array([0, 0.0, zh]), "knee": np.array([0, 0.14 * Hm, zh * 0.72]), "hock": np.array([0, -0.07 * Hm, zh * 0.34]),
          "ankle": np.array([0, 0.03 * Hm, 0.075 * Hm])}
    hipv = {z: P["parts"][z].get("hip", 0.0) for z in ("Left Leg", "Right Leg")}

    def leg(s, sg):
        w = 0.03 * Hm * s
        d = w * 1.35
        o = []
        segs = [("hip", "knee", 1.0, 0.95), ("knee", "hock", 0.95, 0.85), ("hock", "ankle", 0.75, 0.62)]
        for i, (a, b, k0, k1) in enumerate(segs):
            p0, p1 = J0[a] + (J0[a] - J0[b]) * 0.06, J0[b] + (J0[b] - J0[a]) * 0.04
            o.append((prism(p0, p1, w * k0, d * k0, w * k1, d * k1, 8), "t2" if i != 1 else "t1", "core", ("thigh", "shin", "tarsus")[i]))
        for jn, k in (("knee", 1.0), ("hock", 0.85)):
            o.append((prism(J0[jn] - np.array([w * 1.15 * k, 0, 0]), J0[jn] + np.array([w * 1.15 * k, 0, 0]), d * 0.9 * k, d * 0.9 * k, n=8, lat=(0, 1, 0)),
                      "t4", "cover", jn + "_drum"))
        # claw foot: a hub, three toes fanned forward, a spur behind
        an = J0["ankle"]
        hub = np.array([0, an[1], 0.065 * Hm])                         # the hub rests ON the ground
        o.append((prism(hub - np.array([w * 1.0, 0, 0]), hub + np.array([w * 1.0, 0, 0]), 0.05 * Hm, 0.06 * Hm, n=6, lat=(0, 1, 0)), "t1", "core", "foot"))
        for ang, ln in ((-0.32, 0.17), (0.0, 0.2), (0.32, 0.17)):
            tip = np.array([math.sin(ang) * ln * Hm, hub[1] + math.cos(ang) * ln * Hm, 0.013 * Hm])
            o.append((prism(hub + np.array([0, 0.02 * Hm, 0]), tip, w * 0.42, 0.028 * Hm, w * 0.2, 0.012 * Hm, n=6, ch=0.3), "t2", "core", "toe"))
        o.append((prism(hub, np.array([0, hub[1] - 0.1 * Hm, 0.012 * Hm]), w * 0.36, 0.024 * Hm, w * 0.18, 0.01 * Hm, n=6, ch=0.3), "t2", "core", "spur"))
        return o, w, d

    legs = {}
    for sg, zone in ((-1, "Left Leg"), (1, "Right Leg")):
        s = fit(lambda s_: leg(s_, sg)[0], max(0.4 * env[zone], env[zone] - hipv[zone]), vol)
        legs[zone] = leg(s, sg)
    wmax = max(l[1] for l in legs.values())
    hx = wmax * 1.2 + 0.05 * Hm                                   # a wide stance
    for zone, (o, w, d) in legs.items():
        sg = -1 if zone.startswith("Left") else 1
        mv = np.array([sg * hx, 0, 0])
        o = [(p + mv,) + tuple(r) for p, *r in o]
        # the hip: one faceted drum per side, sized by the hip actuator, meeting the other at the centre line
        rh = max(0.045 * Hm, (hipv[zone] / (math.pi * 0.85 * (hx + w))) ** 0.5)
        o.append((prism(np.array([sg * 0.02, 0, zh]), np.array([sg * (hx + w * 1.1), 0, zh]), rh, rh * 1.1, n=8, lat=(0, 1, 0)), "t1", "core", "hip"))
        for p, cls, role, name in o:
            out.append((p, cls, role, name, zone))
        J = {k: v + mv for k, v in J0.items()}
        cx.leg_j["L" if sg < 0 else "R"] = (J, [(J["hip"], J["knee"], w, d, w * 0.95, d * 0.95), (J["knee"], J["hock"], w * 0.95, d * 0.95, w * 0.85, d * 0.85),
                                                (J["hock"], J["ankle"], w * 0.75, d * 0.75, w * 0.62, d * 0.62)])

    # ---- torso: canopy body (centre torso) with the nose as the head, side blocks (side torsos) over the hips
    pitch = math.radians(9)
    z0 = zh - 0.02 * Hm
    yc = 0.02 * Hm

    def housing(it):
        L, W, Hh, _g = cx.geoms[id(it)]
        return W + 0.5, max(L, 0.18 * Hm), Hh + 0.5

    hous = {z: sum(a * b * c for a, b, c in (housing(it) for it in P["items"].get(z, []) if it["kind"] == "missile" and it["visible"]))
            for z in ("Left Torso", "Right Torso")}

    def body(s):
        Lb, Wb, Hb = 0.52 * Hm * s, 0.30 * Hm * s, 0.30 * Hm * s
        return canopy(yc, z0, Lb, Wb, Hb, pitch), (Lb, Wb, Hb)

    # each location fitted to its own budget: the canopy to the centre torso, each side block to its side torso less its launcher
    s_c = fit(lambda s_: [(body(s_)[0],)], env["Center Torso"] * SH.OVERLAP, vol)          # one solid: no overlap to allow for
    cpts, (Lb, Wb, Hb) = body(s_c)
    tparts = [(cpts, "t2", "core", "canopy", "Center Torso")]
    ctsol = Solid(cpts)

    def side(s, sg, zone):
        x0 = sg * Wb * 0.36
        x1 = sg * (Wb * 0.36 + 0.15 * Hm * s)
        c = np.array([(x0 + x1) / 2, yc - 0.06 * Hm, z0 + Hb * 0.55])
        return Frame(c, (0, 1, 0)).pp(lbox((0, 0, 0), (abs(x1 - x0), Lb * 0.5 * s, Hb * 0.62 * s), bev=0.05 * Hm, tap=(0.9, 0.75)))

    for sg, zone in ((-1, "Left Torso"), (1, "Right Torso")):
        # the part of the block inside the canopy is not new volume: fit on the block's volume outside it (a grid estimate)
        def outside(s_, sg=sg, zone=zone):
            pts = side(s_, sg, zone)
            lo, hi = pts.min(0), pts.max(0)
            g = np.stack(np.meshgrid(*[np.linspace(lo[i], hi[i], 9) for i in range(3)], indexing="ij"), -1).reshape(-1, 3)
            inb = Solid(pts)
            def inside(sol, q):
                return np.all(q @ sol.hull.equations[:, :3].T + sol.hull.equations[:, 3] <= 1e-9, axis=1)
            frac = (inside(inb, g) & ~inside(ctsol, g)).sum() / max(1, inside(inb, g).sum())
            return [(pts,)], frac
        tgt = max(0.3 * env[zone], env[zone] - hous[zone])
        s_s = 1.0
        for _ in range(6):
            parts_, frac = outside(s_s)
            v = hull_vol(parts_[0][0]) * frac
            s_s = min(3.0, max(0.3, s_s * (tgt / max(v, 1e-6)) ** 0.4))
        tparts.append((side(s_s, sg, zone), "t1", "core", "side", zone))
    out += tparts
    tz = ("Left Torso", "Center Torso", "Right Torso")
    ct = Solid(tparts[0][0])
    # head: the cockpit is the canopy's nose (the Head location's volume), glass on its upper face
    nose_y = yc + Lb / 2 * 0.86
    nose = canopy(nose_y - 0.06 * Hm, z0 + Hb * 0.05, 0.22 * Hm, Wb * 0.62, Hb * 0.62, pitch + math.radians(6))
    nk = (env["Head"] / max(hull_vol(nose), 1e-6)) ** (1 / 3)
    nc = nose.mean(0)
    nose = nc + (nose - nc) * min(1.3, max(0.7, nk))
    out.append((nose, "t2", "core", "nose", "Head"))
    hsol = Solid(nose)
    pt, n = hsol.hit(nose.mean(0), _u((0, 0.55, 1)))
    out.append((SH.slab(pt - n * 0.02, n, (0, 1, 0.3), Wb * 0.32, 0.07 * Hm, 0.08), "ck", "cover", "glass", "Head"))
    sides = {z: Solid(p) for p, c, r, nm, z in tparts if nm == "side"}

    # ---- arms: short upper arm down from a shoulder drum, the forearm a long gun pod aimed forward
    for sg, zone, side in ((-1, "Left Arm", "L"), (1, "Right Arm", "R")):
        sd = sides["Left Torso" if sg < 0 else "Right Torso"]
        xo = float((sd.pts[:, 0] * sg).max())

        def arm(s, sg=sg, xo=xo):
            wa = 0.03 * Hm * s
            xa = sg * (xo + wa * 1.2)
            S_ = np.array([xa, yc - 0.03 * Hm, z0 + Hb * 0.62])
            E_ = S_ + np.array([0, 0.03 * Hm, -0.13 * Hm])
            W_ = E_ + np.array([0, 0.34 * Hm, 0.02 * Hm])
            o = [(prism(S_ - np.array([sg * wa * 1.4, 0, 0]), S_ + np.array([sg * wa * 0.9, 0, 0]), wa * 1.05, wa * 1.05, n=8, lat=(0, 1, 0)), "t4", "cover", "shoulder"),
                 (prism(S_, E_, wa * 0.75, wa * 0.85, wa * 0.7, wa * 0.8, 8), "t1", "core", "upper"),
                 (prism(E_ - np.array([wa * 0.9, 0, 0]), E_ + np.array([wa * 0.9, 0, 0]), wa * 0.8, wa * 0.8, n=8, lat=(0, 1, 0)), "t4", "cover", "elbow"),
                 (prism(E_ - np.array([0, 0.06 * Hm, 0]), W_, wa * 1.15, wa * 1.5, wa * 0.95, wa * 1.2, 8), "t2", "core", "fore")]
            return o, dict(S=S_, E=E_, W=W_, wa=wa, da=wa * 1.3)

        s_a = fit(lambda s_: arm(s_)[0], env[zone], vol)
        o, j = arm(s_a)
        for p, cls, role, name in o:
            out.append((p, cls, role, name, zone))
        cx.arm_j[side] = j

    # write the body
    sol = {}
    for p, cls, role, name, zone in out:
        so = S.add(p, cls, zone, role)
        if role in ("core",):
            sol[(zone, name)] = so
    # what the shared layers and mounts read
    for zone in tz:
        so = sol[(zone, "canopy" if zone == "Center Torso" else "side")]
        lo, hi = so.pts.min(0), so.pts.max(0)
        cx.sec[zone] = (so, (lo[0] + hi[0]) / 2, hi[0] - lo[0], hi[1] - lo[1])
    cx.tor = dict(z0=z0, h=Hb, yc=yc, W=Wb, D=Lb, wc=Wb)
    cx.solids["head"] = sol[("Head", "nose")]
    for side, zone in (("L", "Left Arm"), ("R", "Right Arm")):
        cx.solids[f"arm_{side}_up"] = sol[(zone, "upper")]
        cx.solids[f"arm_{side}_fore"] = sol[(zone, "fore")]
    for side, zone in (("L", "Left Leg"), ("R", "Right Leg")):
        cx.solids[f"leg_{side}_thigh"] = sol[(zone, "thigh")]
        cx.solids[f"leg_{side}_shin"] = sol[(zone, "shin")]
    hm = nose.mean(0)
    hd = dict(hw=Wb * 0.2, hd=0.15 * Hm, hh=Hb * 0.4, z0=float(nose[:, 2].min()), yh=float(hm[1]))
    SH.build_layers(cx, hd, hx, zh, z0)

    # ---- mounts: launchers on posts over the side torsos, guns out of the pod muzzles, the rest on faces
    for zone, placed in P["plan"].items():
        vis = [it for it, r, c in placed if it["visible"]]
        if not vis:
            continue
        sg = -1 if zone.startswith("Left") else 1
        k_gun = 0
        for it in vis:
            L, W, Hh, geom = cx.geoms[id(it)]
            kind = it["kind"]
            if zone.endswith("Arm") and kind in SH.RAILKINDS:
                j = cx.arm_j["L" if sg < 0 else "R"]
                a = _u(j["W"] - j["E"])
                fo = cx.solids[f"arm_{'L' if sg < 0 else 'R'}_fore"]
                guns = [x for x in vis if x["kind"] in SH.RAILKINDS]
                ng = len(guns)
                # the guns come out of the pod's muzzle face, side by side across it (the pod is 2 x 1.15 wa wide at the back)
                lat = (k_gun - (ng - 1) / 2) * min(j["wa"] * 1.1 / max(ng, 1), W * 1.1)
                pt, n = fo.hit(j["W"] - a * 0.3 + np.array([lat, 0, 0]), a)
                fr = Frame(pt - a * max(L * 0.6, 0.25) - np.array([0, 0, Hh / 2]), a, (0, 0, 1))      # seated in the muzzle face
                k_gun += 1
            elif zone.endswith("Torso") and kind == "missile" and zone != "Center Torso":
                so = cx.sec[zone][0]
                top, _n = so.hit(so.pts.mean(0), (0, 0, 1))
                post_h = 0.07 * Hm
                base = top + np.array([0, -0.02 * Hm, 0])
                S.add(prism(base - np.array([0, 0, 0.03 * Hm]), base + np.array([0, 0, post_h]), 0.035 * Hm, 0.05 * Hm, n=6), "t4", zone, "item")
                # the launcher housing: the real tube grid plus a wall, a box that reads from across the board
                Wh, Lh, Hhh = housing(it)
                c = base + np.array([0, 0, post_h + Hhh / 2 - 0.05])
                S.add(Frame(c, (0, 1, 0)).pp(lbox((0, 0, 0), (Wh, Lh, Hhh), bev=0.12)), "t1", zone, "item", "w")
                fr = Frame(c + np.array([0, Lh / 2 - L, -Hh / 2]), (0, 1, 0), (0, 0, 1))
            elif kind in SH.RAILKINDS:
                so = cx.sec.get(zone, (cx.solids.get("head"),))[0]
                p_in = so.pts.mean(0) + np.array([0, 0, -0.02 * Hm + 0.03 * Hm * k_gun])
                pt, n = so.hit(p_in, (0, 1, 0))
                fr = Frame(pt - np.array([0, L * 0.6, Hh / 2]), (0, 1, 0), (0, 0, 1))
                k_gun += 1
            elif kind.startswith("heatsink"):
                so = cx.solids.get(f"arm_{'L' if sg < 0 else 'R'}_fore") if zone.endswith("Arm") else cx.sec.get(zone, (None,))[0]
                if so is None:
                    continue
                c = so.pts.mean(0) + np.array([0, -0.05 * Hm + 0.1 * Hm * (k_gun % 2), 0])
                pt, n = so.hit(c, (sg, 0, 0))
                fr = Frame(pt - n * 0.03, (0, 0, 1), n)
                k_gun += 1
            else:
                continue
            for cls, pts in geom:
                S.add(fr.pp(pts), cls, zone, "item", "w")
    return S.zmax


def build(model, k):
    """The faceted build, at the rules height (the same loop as INTEGRATION__shell.build)."""
    P = SH.prepare(model)
    Ht = SH.M_LEVEL * model["drawn_levels"]
    Hm = Ht
    for _ in range(6):
        b = T.B3(1.0, k)
        S = Sink(b, Ht)
        top = assemble(model, P, S, Hm)
        if abs(top / Ht - 1) < 0.003:
            break
        Hm *= Ht / top
    return b
