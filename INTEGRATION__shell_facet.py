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

FACET_RANGE = ("mad cat", "timber wolf", "atlas")


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


class FRail:
    """A hardpoint rail of the faceted builder. kind 'face': items stand out of a face along `axis` (a grid centred on the face);
    'line': items lie along a surface line, pointing along `axis`, seated where the ray `dr` leaves the solid (a run centred on
    the rail); 'post': missile launchers on a post above the solid, one housing for all of them, other items as on a line."""

    def __init__(self, kind, solid, o, axis, dr=None, lat=(1, 0, 0), up=(0, 0, 1), embed=0.5):
        self.kind, self.solid, self.o, self.a = kind, solid, np.asarray(o, float), _u(axis)
        self.dr = _u(dr if dr is not None else axis)
        self.lat, self.up, self.embed = _u(lat), _u(up), embed




def _arm_used(P, zone):
    """Metres of rail the arm's weapons need on its fullest rail (Daniel, 2026-11-04: pod length follows what is in it)."""
    nr = I.rail_count(zone)
    used = [0] * nr
    for it, r, c in P["plan"].get(zone, []):
        if it["visible"] and it["kind"] in SH.RAILKINDS:
            used[r % nr] += it["slots"]
    return max(used) * I.SLOT_M


def _common(model, P, S, Hm):
    cx = FCtx(model, P, S, Hm)
    cx.geoms, cx.arm_axis, cx.arm_j, cx.sec, cx.leg_j = {}, {}, {}, {}, {}
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
    cx.env = {z: max(0.4 * P["budget"][z], P["budget"][z] - ext.get(z, 0.0)) for z in P["budget"]}
    cx.hipv = {z: P["parts"][z].get("hip", 0.0) for z in ("Left Leg", "Right Leg")}
    return cx


def _hips(cx, legs, hx, zh, out, y=0.0):
    """Move the legs apart, add one faceted hip drum per side (sized by the hip actuator), record the joints."""
    Hm = cx.Hm
    for zone, (o, w, d, J0, segs0) in legs.items():
        sg = -1 if zone.startswith("Left") else 1
        mv = np.array([sg * hx, 0, 0])
        o = [(p + mv,) + tuple(r) for p, *r in o]
        rh = max(0.045 * Hm, (cx.hipv[zone] / (math.pi * 0.85 * (hx + w))) ** 0.5)
        o.append((prism(np.array([sg * 0.02, y, zh]), np.array([sg * (hx + w * 1.1), y, zh]), rh, rh * 1.1, n=8, lat=(0, 1, 0)), "t1", "core", "hip"))
        for p, cls, role, name in o:
            out.append((p, cls, role, name, zone))
        J = {k: v + mv for k, v in J0.items()}
        cx.leg_j["L" if sg < 0 else "R"] = (J, [(J[a], J[b], w0, d0, w1, d1) for a, b, w0, d0, w1, d1 in segs0])


def _fit_scale(make, target, iters=6):
    """Scale s so the hull volume of make(s) (one solid) is `target`."""
    s_ = 1.0
    for _ in range(iters):
        v = hull_vol(make(s_))
        s_ = min(3.0, max(0.3, s_ * (target / max(v, 1e-6)) ** 0.45))
    return s_


# ------------------------------------------------------------------------------------------------------- bird (Mad Cat)

def body_bird(cx):
    P, S, Hm, env = cx.P, cx.S, cx.Hm, cx.env
    out, vol = [], SH.vol_of
    zh = 0.50 * Hm
    J0 = {"hip": np.array([0, 0.0, zh]), "knee": np.array([0, 0.14 * Hm, zh * 0.72]), "hock": np.array([0, -0.07 * Hm, zh * 0.34]),
          "ankle": np.array([0, 0.03 * Hm, 0.075 * Hm])}

    def leg(s):
        w = 0.03 * Hm * s
        d = w * 1.35
        o = []
        segs = [("hip", "knee", 1.0, 0.95), ("knee", "hock", 0.95, 0.85), ("hock", "ankle", 0.75, 0.62)]
        for i, (a, b, k0, k1) in enumerate(segs):
            p0, p1 = J0[a] + (J0[a] - J0[b]) * 0.06, J0[b] + (J0[b] - J0[a]) * 0.04
            o.append((prism(p0, p1, w * k0, d * k0, w * k1, d * k1, 8), "t2" if i != 1 else "t1", "core", ("thigh", "shin", "tarsus")[i]))
        for jn, k in (("knee", 1.0), ("hock", 0.85)):
            o.append((prism(J0[jn] - np.array([w * 1.15 * k, 0, 0]), J0[jn] + np.array([w * 1.15 * k, 0, 0]), d * 0.9 * k, d * 0.9 * k, n=8, lat=(0, 1, 0)), "t4", "cover", jn + "_drum"))
        hub = np.array([0, J0["ankle"][1], 0.065 * Hm])                       # the hub rests ON the ground
        o.append((prism(hub - np.array([w * 1.0, 0, 0]), hub + np.array([w * 1.0, 0, 0]), 0.05 * Hm, 0.06 * Hm, n=6, lat=(0, 1, 0)), "t1", "core", "foot"))
        for ang, ln in ((-0.32, 0.17), (0.0, 0.2), (0.32, 0.17)):
            tip = np.array([math.sin(ang) * ln * Hm, hub[1] + math.cos(ang) * ln * Hm, 0.013 * Hm])
            o.append((prism(hub + np.array([0, 0.02 * Hm, 0]), tip, w * 0.42, 0.028 * Hm, w * 0.2, 0.012 * Hm, n=6, ch=0.3), "t2", "core", "toe"))
        o.append((prism(hub, np.array([0, hub[1] - 0.1 * Hm, 0.012 * Hm]), w * 0.36, 0.024 * Hm, w * 0.18, 0.01 * Hm, n=6, ch=0.3), "t2", "core", "spur"))
        segs0 = [("hip", "knee", w, d, w * 0.95, d * 0.95), ("knee", "hock", w * 0.95, d * 0.95, w * 0.85, d * 0.85), ("hock", "ankle", w * 0.75, d * 0.75, w * 0.62, d * 0.62)]
        return o, w, d, J0, segs0

    legs = {}
    for zone in ("Left Leg", "Right Leg"):
        s = fit(lambda s_: leg(s_)[0], max(0.4 * env[zone], env[zone] - cx.hipv[zone]), vol)
        legs[zone] = leg(s)
    hx = max(l[1] for l in legs.values()) * 1.2 + 0.05 * Hm                   # a wide stance
    _hips(cx, legs, hx, zh, out)

    pitch = math.radians(9)
    z0, yc = zh - 0.02 * Hm, 0.02 * Hm

    def housing(it):
        L, W, Hh, _g = cx.geoms[id(it)]
        return W + 0.5, max(L, 0.18 * Hm), Hh + 0.5
    cx.housing = housing
    hous = {z: sum(a * b * c for a, b, c in (housing(it) for it in P["items"].get(z, []) if it["kind"] == "missile" and it["visible"]))
            for z in ("Left Torso", "Right Torso")}

    def body(s):
        Lb, Wb, Hb = 0.52 * Hm * s, 0.30 * Hm * s, 0.30 * Hm * s
        return canopy(yc, z0, Lb, Wb, Hb, pitch), (Lb, Wb, Hb)

    s_c = _fit_scale(lambda s_: body(s_)[0], env["Center Torso"])
    cpts, (Lb, Wb, Hb) = body(s_c)
    out.append((cpts, "t2", "core", "canopy", "Center Torso"))
    ctsol = Solid(cpts)

    def side(s, sg):
        x0 = sg * Wb * 0.36
        x1 = sg * (Wb * 0.36 + 0.15 * Hm * s)
        c = np.array([(x0 + x1) / 2, yc - 0.06 * Hm, z0 + Hb * 0.55])
        return Frame(c, (0, 1, 0)).pp(lbox((0, 0, 0), (abs(x1 - x0), Lb * 0.5 * s, Hb * 0.62 * s), bev=0.05 * Hm, tap=(0.9, 0.75)))

    def inside(sol, q):
        return np.all(q @ sol.hull.equations[:, :3].T + sol.hull.equations[:, 3] <= 1e-9, axis=1)

    for sg, zone in ((-1, "Left Torso"), (1, "Right Torso")):
        tgt = max(0.3 * env[zone], env[zone] - hous[zone])
        s_s = 1.0
        for _ in range(6):                    # the part inside the canopy is not new volume: fit on the part outside it
            pts = side(s_s, sg)
            lo, hi = pts.min(0), pts.max(0)
            g = np.stack(np.meshgrid(*[np.linspace(lo[i], hi[i], 9) for i in range(3)], indexing="ij"), -1).reshape(-1, 3)
            inb = Solid(pts)
            frac = (inside(inb, g) & ~inside(ctsol, g)).sum() / max(1, inside(inb, g).sum())
            s_s = min(3.0, max(0.3, s_s * (tgt / max(hull_vol(pts) * frac, 1e-6)) ** 0.4))
        out.append((side(s_s, sg), "t1", "core", "side", zone))
    # head: the cockpit is the canopy's nose (the Head location's volume), glass on its upper face
    nose_y = yc + Lb / 2 * 0.86
    nose = canopy(nose_y - 0.06 * Hm, z0 + Hb * 0.05, 0.22 * Hm, Wb * 0.62, Hb * 0.62, pitch + math.radians(6))
    nc = nose.mean(0)
    nose = nc + (nose - nc) * min(1.3, max(0.7, (env["Head"] / max(hull_vol(nose), 1e-6)) ** (1 / 3)))
    out.append((nose, "t2", "core", "nose", "Head"))
    hsol = Solid(nose)
    pt, n = hsol.hit(nose.mean(0), _u((0, 0.55, 1)))
    out.append((SH.slab(pt - n * 0.02, n, (0, 1, 0.3), Wb * 0.32, 0.07 * Hm, 0.08), "ck", "cover", "glass", "Head"))
    sides = {z: Solid(p) for p, c, r, nm, z in out if nm == "side"}

    # arms: a short upper arm from a shoulder drum; the forearm is a gun pod aimed forward, as long as its guns need
    for sg, zone, sd_ in ((-1, "Left Arm", "L"), (1, "Right Arm", "R")):
        sd = sides["Left Torso" if sg < 0 else "Right Torso"]
        xo = float((sd.pts[:, 0] * sg).max())
        Lpod = min(0.40 * Hm, 0.17 * Hm + _arm_used(P, zone))

        def arm(s, sg=sg, xo=xo, Lpod=Lpod):
            wa = 0.03 * Hm * s
            S_ = np.array([sg * (xo + wa * 1.2), yc - 0.03 * Hm, z0 + Hb * 0.62])
            E_ = S_ + np.array([0, 0.03 * Hm, -0.13 * Hm])
            W_ = E_ + np.array([0, Lpod, 0.02 * Hm])
            o = [(prism(S_ - np.array([sg * wa * 1.4, 0, 0]), S_ + np.array([sg * wa * 0.9, 0, 0]), wa * 1.05, wa * 1.05, n=8, lat=(0, 1, 0)), "t4", "cover", "shoulder"),
                 (prism(S_, E_, wa * 0.75, wa * 0.85, wa * 0.7, wa * 0.8, 8), "t1", "core", "upper"),
                 (prism(E_ - np.array([wa * 0.9, 0, 0]), E_ + np.array([wa * 0.9, 0, 0]), wa * 0.8, wa * 0.8, n=8, lat=(0, 1, 0)), "t4", "cover", "elbow"),
                 (prism(E_ - np.array([0, 0.06 * Hm, 0]), W_, wa * 1.15, wa * 1.5, wa * 0.95, wa * 1.2, 8), "t2", "core", "fore")]
            return o, dict(S=S_, E=E_, W=W_, wa=wa, da=wa * 1.3)

        s_a = fit(lambda s_: arm(s_)[0], env[zone], vol)
        o, j = arm(s_a)
        out += [(p, c, r, nm, zone) for p, c, r, nm in o]
        cx.arm_j[sd_] = j
    cx.tor = dict(z0=z0, h=Hb, yc=yc, W=Wb, D=Lb, wc=Wb)
    hd = dict(hw=Wb * 0.2, hd=0.15 * Hm, hh=Hb * 0.4, z0=float(nose[:, 2].min()), yh=float(nose.mean(0)[1]))
    return out, dict(hx=hx, zh=zh, z0=z0, hd=hd, torso_names={"Center Torso": "canopy", "Left Torso": "side", "Right Torso": "side"},
                     head="nose", thigh="thigh", shin="shin", rails=rails_bird)


def rails_bird(cx):
    R, Hm = {}, cx.Hm
    for side, zone in (("L", "Left Arm"), ("R", "Right Arm")):
        sg = -1 if side == "L" else 1
        j, fo = cx.arm_j[side], cx.solids[f"arm_{side}_fore"]
        a, ex, ey = SH.limb_axes(j["E"], j["W"])
        mid = (j["E"] + j["W"]) / 2
        R[zone] = [FRail("face", fo, j["W"] - a * 0.3, a, lat=ex, up=ey), FRail("line", fo, mid, a, ey), FRail("line", fo, mid, a, sg * ex)]
    for zone in ("Left Torso", "Right Torso"):
        sg = -1 if zone.startswith("Left") else 1
        so = cx.sec[zone][0]
        c = so.pts.mean(0)
        R[zone] = [FRail("post", so, c, (0, 1, 0), (0, 0, 1)), FRail("face", so, c, (0, 1, 0)), FRail("line", so, c, (0, 1, 0), (sg, 0, 0)),
                   FRail("line", so, c + np.array([0, 0, 0]), (0, 1, 0), (0, 0, 1))]
    ct = cx.sec["Center Torso"][0]
    c = ct.pts.mean(0)
    R["Center Torso"] = [FRail("face", ct, c - np.array([0, 0, 0.04 * Hm]), (0, 1, 0)), FRail("line", ct, c, (0, 1, 0), (0, 0, 1)),
                         FRail("face", ct, c - np.array([0, 0, 0.07 * Hm]), (0, 1, 0))]
    hs = cx.solids["head"]
    R["Head"] = [FRail("face", hs, hs.pts.mean(0), (0, 1, 0)), FRail("line", hs, hs.pts.mean(0), (0, 1, 0), (0, 0, 1))]
    for side, zone in (("L", "Left Leg"), ("R", "Right Leg")):
        sg = -1 if side == "L" else 1
        th, sh = cx.solids[f"leg_{side}_thigh"], cx.solids[f"leg_{side}_shin"]
        J = cx.leg_j[side][0]
        R[zone] = [FRail("line", th, (J["hip"] + J["knee"]) / 2, J["knee"] - J["hip"], (sg, 0, 0)),
                   FRail("line", sh, (J["knee"] + J["hock"]) / 2, J["hock"] - J["knee"], (sg, 0, 0))]
    return R


# --------------------------------------------------------------------------------------------------- humanoid (Atlas)

# side view of a chest section: the belly pulled in, deep at the chest, the top cut back (the kit's V-shaped chest)
CHEST = [(-.62, 0), (.55, 0), (1, .32), (1, .8), (.62, 1), (-.8, 1), (-1, .84), (-1, .34)]


def body_humanoid(cx):
    """A humanoid in one solid per part: straight legs on big knee drums, heel-and-toe feet, a faceted chest whose side torsos
    stand taller than the centre (a notch for the head), box pauldrons, forearms with fists. Tags: head_shape, head_mount, kit
    pauldrons, legs slab / pillar."""
    P, S, Hm, env, m = cx.P, cx.S, cx.Hm, cx.env, cx.m
    out, vol = [], SH.vol_of
    zh = 0.50 * Hm
    J0 = {"hip": np.array([0, 0.0, zh]), "knee": np.array([0, 0.03 * Hm, 0.27 * Hm]), "ankle": np.array([0, 0.0, 0.085 * Hm])}
    asp = 1.0 if m.get("legs") in ("slab", "pillar") else 1.15

    def leg(s):
        w = 0.04 * Hm * s
        d = w * asp
        o = [(prism(J0["hip"] + np.array([0, 0, 0.03 * Hm]), J0["knee"], w, d, w * 0.9, d * 0.92, 8, ch=0.15), "t2", "core", "thigh"),
             (prism(J0["knee"] + np.array([0, 0, 0.02 * Hm]), J0["ankle"], w * 0.95, d * 1.08, w * 0.78, d * 0.84, 8, ch=0.15), "t2", "core", "shin"),
             (prism(J0["knee"] - np.array([w * 1.12, 0, 0]), J0["knee"] + np.array([w * 1.12, 0, 0]), d * 0.95, d * 0.95, n=8, lat=(0, 1, 0)), "t4", "cover", "knee_drum"),
             (prism(J0["ankle"] - np.array([w * 0.95, 0, 0]), J0["ankle"] + np.array([w * 0.95, 0, 0]), d * 0.6, d * 0.6, n=8, lat=(0, 1, 0)), "t4", "cover", "ankle_drum")]
        wf, Lf, hf = 0.07 * Hm * s ** 0.5, 0.27 * Hm, 0.075 * Hm
        heel = J0["ankle"][1] - 0.09 * Hm
        fr = Frame((0, heel, 0), (0, 1, 0))
        o.append((fr.pp(lbox((0, Lf * 0.3, hf / 2), (2 * wf, Lf * 0.6, hf), bev=0.2 * hf, tap=(0.95, 0.8))), "t1", "core", "foot"))
        for sx in (-1, 1):
            o.append((fr.pp(lbox((sx * wf * 0.5, Lf * 0.76, hf * 0.3), (wf * 0.92, Lf * 0.44, hf * 0.6), bev=0.18 * hf, tap=(0.85, 0.55))), "t2", "core", "toe"))
        segs0 = [("hip", "knee", w, d, w * 0.9, d * 0.92), ("knee", "ankle", w * 0.95, d * 1.08, w * 0.78, d * 0.84)]
        return o, w, d, J0, segs0

    legs = {}
    for zone in ("Left Leg", "Right Leg"):
        s = fit(lambda s_: leg(s_)[0], max(0.4 * env[zone], env[zone] - cx.hipv[zone]), vol)
        legs[zone] = leg(s)
    hx = max(l[1] for l in legs.values()) * 1.15 + 0.035 * Hm
    _hips(cx, legs, hx, zh, out)

    # chest: three sections fitted to their budgets by width; the side torsos stand taller than the centre (the head's notch)
    z0, yc = zh + 0.01 * Hm, 0.0
    h, D = 0.27 * Hm, 0.21 * Hm * m.get("bodyd", 1.0)          # wide and squat (Atlas kit chest 5.3 x 3.9 x 4.3 m with its recesses)
    notch = m.get("head_mount") in ("notch", "built_in")
    hct = h * (0.86 if notch else 1.0)

    def section(x0, x1, d, hh):
        return SH.prof_solid(x0, x1, yc, d, z0, hh, CHEST, wtop=1.28, e=0.03 * Hm, k=0.9)       # wider at the top: broad shoulders, narrow waist

    wc = _fit_scale(lambda w_: section(-w_ / 2, w_ / 2, D, hct), env["Center Torso"]) * 1.0
    wc = max(0.12 * Hm, min(0.3 * Hm, wc))
    cpts = section(-wc / 2, wc / 2, D, hct)
    out.append((cpts, "t2", "core", "chest", "Center Torso"))
    for sg, zone in ((-1, "Left Torso"), (1, "Right Torso")):
        e = 0.015 * Hm
        ws = _fit_scale(lambda w_: section(0, w_, D * 0.94, h), env[zone])
        x0, x1 = sg * (wc / 2 - e), sg * (wc / 2 - e + ws)
        out.append((section(min(x0, x1), max(x0, x1), D * 0.94, h), "t1", "core", "side", zone))
    # head: a skull sunk in the notch (or a box head on top), the cockpit glass in its face
    shape = m.get("head_shape", "box")

    def skull(s_):
        hw, hdp, hh = 0.07 * Hm * s_, 0.085 * Hm * s_, 0.10 * Hm * s_
        yh = yc + D * (0.22 if notch else 0.0)
        zb = z0 + hct - hh * (0.45 if notch else 0.05)
        prof = SH.HEAD_PROF.get(shape, SH.HEAD_PROF["box"])
        return SH.prof_solid(-hw, hw, yh, 2 * hdp, zb, hh, prof, wtop=0.86, e=0.02 * Hm, k=0.88), (hw, hdp, hh, yh, zb)

    s_h = _fit_scale(lambda s_: skull(s_)[0], env["Head"])
    hpts, (hw, hdp, hh, yh, zb) = skull(s_h)
    out.append((hpts, "t3", "core", "head", "Head"))
    hsol = Solid(hpts)
    for sx in (-1, 1):                                              # two eye slots of cockpit glass
        pt, n = hsol.hit(np.array([sx * hw * 0.42, yh, zb + hh * 0.62]), (0, 1, 0))
        out.append((SH.slab(pt - n * 0.02, n, (0, 0, 1), hw * 0.5, hh * 0.14, 0.07), "ck", "cover", "eye", "Head"))
    if shape == "skull":
        pt, n = hsol.hit(np.array([0, yh, zb + hh * 0.18]), (0, 1, 0))
        out.append((SH.slab(pt - n * 0.04, n, (0, 0, 1), hw * 0.9, hh * 0.24, 0.12), "t4", "cover", "jaw", "Head"))
    sides = {z: Solid(p) for p, c, r, nm, z in out if nm == "side"}

    # arms: shoulder drum under a box pauldron, upper arm, elbow drum, a forearm reaching forward, a fist
    kp = 1.0 + (0.25 if m.get("kit") == "pauldrons" else 0.0) + (0.12 if m.get("shoulders") == "boom" else 0.0)
    for sg, zone, sd_ in ((-1, "Left Arm", "L"), (1, "Right Arm", "R")):
        sd = sides["Left Torso" if sg < 0 else "Right Torso"]
        xo = float((sd.pts[:, 0] * sg).max())
        hand = (m.get("arms") or {}).get(sd_, "hand") == "hand"

        def arm(s, sg=sg, xo=xo, hand=hand):
            wa = 0.032 * Hm * s
            S_ = np.array([sg * (xo + wa * 1.15), yc, z0 + h * 0.82])
            E_ = S_ + np.array([0, 0.01 * Hm, -0.15 * Hm])
            pitch = math.radians(38)
            W_ = E_ + 0.16 * Hm * np.array([0, math.sin(pitch), -math.cos(pitch)])
            a = _u(W_ - E_)
            o = [(prism(S_ - np.array([sg * wa * 1.2, 0, 0]), S_ + np.array([sg * wa * 0.8, 0, 0]), wa * 0.9, wa * 0.9, n=8, lat=(0, 1, 0)), "t4", "cover", "shoulder"),
                 (prism(S_, E_, wa * 0.85, wa * 0.9, wa * 0.8, wa * 0.85, 8), "t1", "core", "upper"),
                 (prism(E_ - np.array([wa * 0.95, 0, 0]), E_ + np.array([wa * 0.95, 0, 0]), wa * 0.85, wa * 0.85, n=8, lat=(0, 1, 0)), "t4", "cover", "elbow"),
                 (prism(E_ - a * 0.02 * Hm, W_, wa * 1.1, wa * 1.2, wa * 1.0, wa * 1.05, 8), "t2", "core", "fore")]
            if hand:
                o.append((prism(W_ - a * 0.01 * Hm, W_ + a * 0.09 * Hm, wa * 0.95, wa * 1.0, wa * 0.85, wa * 0.85, 6, ch=0.2), "t1", "core", "fist"))
            # the pauldron: a faceted box over the joint, wider than the arm, overhanging outward (Atlas kit: 2.6 m)
            pc = S_ + np.array([sg * wa * 0.2, 0, wa * 0.45])
            o.append((Frame(pc, (0, 1, 0)).pp(lbox((0, 0, 0), (2.2 * wa * kp, 2.5 * wa * kp, 2.3 * wa * kp), bev=0.4 * wa, tap=(0.8, 0.72))), "t3", "cover", "pauldron"))
            return o, dict(S=S_, E=E_, W=W_, wa=wa, da=wa * 1.1)

        s_a = fit(lambda s_: arm(s_)[0], env[zone], vol)
        o, j = arm(s_a)
        out += [(p, c, r, nm, zone) for p, c, r, nm in o]
        cx.arm_j[sd_] = j
    cx.tor = dict(z0=z0, h=h, yc=yc, W=wc + 2 * D, D=D, wc=wc)
    hd = dict(hw=hw, hd=2 * hdp, hh=hh, z0=zb, yh=yh)
    return out, dict(hx=hx, zh=zh, z0=z0, hd=hd, torso_names={"Center Torso": "chest", "Left Torso": "side", "Right Torso": "side"},
                     head="head", thigh="thigh", shin="shin", rails=rails_humanoid)


def rails_humanoid(cx):
    R, Hm = {}, cx.Hm
    for side, zone in (("L", "Left Arm"), ("R", "Right Arm")):
        sg = -1 if side == "L" else 1
        j, fo = cx.arm_j[side], cx.solids[f"arm_{side}_fore"]
        a, ex, ey = SH.limb_axes(j["E"], j["W"])
        mid = (j["E"] + j["W"]) / 2
        R[zone] = [FRail("line", fo, mid, a, -ey), FRail("line", fo, mid, a, sg * ex), FRail("line", fo, mid, a, ey)]   # under (the kit's arm lasers), outer, top
    for zone in ("Left Torso", "Right Torso"):
        sg = -1 if zone.startswith("Left") else 1
        so = cx.sec[zone][0]
        lo, hi = so.pts.min(0), so.pts.max(0)
        c = (lo + hi) / 2
        R[zone] = [FRail("face", so, c + np.array([0, 0, 0.12 * (hi[2] - lo[2])]), (0, 1, 0), embed=0.55), FRail("line", so, c, (0, 1, 0), (sg, 0, 0)),
                   FRail("line", so, c, (0, 1, 0), (0, 0, 1)), FRail("face", so, c - np.array([0, 0, 0.22 * (hi[2] - lo[2])]), (0, 1, 0), embed=0.55)]
    ct = cx.sec["Center Torso"][0]
    lo, hi = ct.pts.min(0), ct.pts.max(0)
    c = (lo + hi) / 2
    R["Center Torso"] = [FRail("face", ct, c + np.array([0, 0, 0.1 * (hi[2] - lo[2])]), (0, 1, 0)), FRail("face", ct, c - np.array([0, 0, 0.2 * (hi[2] - lo[2])]), (0, 1, 0)),
                         FRail("line", ct, c, (0, 1, 0), (0, 0, 1))]
    hs = cx.solids["head"]
    R["Head"] = [FRail("face", hs, hs.pts.mean(0) - np.array([0, 0, 0.01 * Hm]), (0, 1, 0)), FRail("line", hs, hs.pts.mean(0), (0, 1, 0), (0, 0, 1))]
    for side, zone in (("L", "Left Leg"), ("R", "Right Leg")):
        sg = -1 if side == "L" else 1
        th, sh = cx.solids[f"leg_{side}_thigh"], cx.solids[f"leg_{side}_shin"]
        J = cx.leg_j[side][0]
        R[zone] = [FRail("line", th, (J["hip"] + J["knee"]) / 2, J["knee"] - J["hip"], (sg, 0, 0)),
                   FRail("line", sh, (J["knee"] + J["ankle"]) / 2, J["ankle"] - J["knee"], (0, -1, 0))]
    return R


# ------------------------------------------------------------------------------------------------------------- mounts

def mount_rails(cx, rails):
    """Every visible weapon on its shuffled rail (INTEGRATION__shell_items.place_items): a face rail lays its items out as a grid
    CENTRED on the face, a line rail as a run centred on the rail, a post rail puts its missiles in one launcher on a post. Vents,
    nozzles and domes keep the plated builder's fixed spots (INTEGRATION__shell.mount_peg)."""
    S, Hm, P = cx.S, cx.Hm, cx.P
    for zone, placed in P["plan"].items():
        if zone not in rails:
            continue
        rl = rails[zone]
        groups, pegs = {}, {}
        for it, r, c in sorted(placed, key=lambda q: (q[1], q[2])):
            if not it["visible"]:
                continue
            if it["kind"] in SH.RAILKINDS:
                post = next((i for i, x in enumerate(rl) if x.kind == "post"), None)
                if it["kind"] == "missile" and post is not None:          # a chassis with launcher posts keeps its missiles on them
                    r = post
                groups.setdefault(r % len(rl), []).append(it)
            else:
                pegs.setdefault(it["kind"], []).append(it)
        for r, items in groups.items():
            rail = rl[r]
            if rail.kind == "post":
                miss = [it for it in items if it["kind"] == "missile"]
                if miss:
                    _launcher(cx, zone, rail, miss)
                items = [it for it in items if it["kind"] != "missile"]
                rail = FRail("line", rail.solid, rail.o, rail.a, (0, 0, 1))
                if not items:
                    continue
            if rail.kind == "face":
                _face(cx, zone, rail, items)
            else:
                _line(cx, zone, rail, items)
        for kind, lst in pegs.items():
            lst = lst[:6]
            for idx, it in enumerate(lst):
                SH.mount_peg(cx, zone, it, idx, len(lst))


def _emit(cx, zone, it, fr):
    for cls, pts in cx.geoms[id(it)][3]:
        cx.S.add(fr.pp(pts), cls, zone, "item", "w")


def _face(cx, zone, rail, items):
    """Items standing out of a face: rows across `lat`, centred; rows stack along `up`, centred too."""
    so = rail.solid
    lo, hi = so.extent(rail.lat)
    face_w = 0.85 * (hi - lo)
    gap = 0.06
    rows, row, wsum = [], [], 0.0
    for it in items:
        W = cx.geoms[id(it)][1]
        if row and wsum + W > face_w:
            rows.append(row)
            row, wsum = [], 0.0
        row.append(it)
        wsum += W + gap
    rows.append(row)
    heights = [max(cx.geoms[id(it)][2] for it in r_) for r_ in rows]
    ztot = sum(heights) + gap * (len(rows) - 1)
    pt0, _n = so.hit(rail.o, rail.a)
    zc = ztot / 2
    for r_, hr in zip(rows, heights):
        zc -= hr / 2
        widths = [cx.geoms[id(it)][1] for it in r_]
        x = -(sum(widths) + gap * (len(r_) - 1)) / 2
        for it, W in zip(r_, widths):
            L, _W, Hh, _g = cx.geoms[id(it)]
            x += W / 2
            p_in = rail.o + rail.lat * x + rail.up * zc
            pt, n = so.hit(p_in, rail.a)
            emb = (L - 0.08) if it["kind"] == "missile" else rail.embed * L          # a rack sits flush, a gun half buried
            fr = Frame(pt - rail.a * emb - rail.up * (Hh / 2), rail.a, rail.up)
            _emit(cx, zone, it, fr)
            x += W / 2 + gap
        zc -= hr / 2 + gap


def _line(cx, zone, rail, items):
    """Items lying along a surface, one behind the other along the rail, the run centred on the rail's middle."""
    so, a = rail.solid, rail.a
    lo, hi = so.extent(a)
    gap = 0.08
    run = sum(cx.geoms[id(it)][0] for it in items) + gap * (len(items) - 1)
    mid = float(rail.o @ a)
    start = mid - run / 2 + 0.25 * min(run, hi - lo)                       # the run leans forward: muzzles past the front
    for it in items:
        L, W, Hh, _g = cx.geoms[id(it)]
        sc = SH._clamp(start + L / 2, lo + 0.08, hi - 0.08)
        pt, nrm = so.hit(rail.o + a * (sc - mid), rail.dr)
        _emit(cx, zone, it, Frame(pt + a * (start - sc) - nrm * (0.3 * Hh), a, nrm))
        start += L + gap


def _launcher(cx, zone, rail, miss):
    """The Mad Cat's launchers: every missile rack on this rail in ONE housing on a post above the solid, the racks' real tube
    faces side by side in its front."""
    so, Hm = rail.solid, cx.Hm
    top, _n = so.hit(so.pts.mean(0), (0, 0, 1))
    dims = [cx.housing(it) if hasattr(cx, "housing") else (cx.geoms[id(it)][1] + 0.5, max(cx.geoms[id(it)][0], 0.18 * Hm), cx.geoms[id(it)][2] + 0.5) for it in miss]
    Wh = sum(d[0] for d in dims) - 0.3 * (len(dims) - 1)
    Lh, Hhh = max(d[1] for d in dims), max(d[2] for d in dims)
    post_h = 0.07 * Hm
    base = top + np.array([0, -0.02 * Hm, 0])
    cx.S.add(prism(base - np.array([0, 0, 0.03 * Hm]), base + np.array([0, 0, post_h]), 0.035 * Hm, 0.05 * Hm, n=6), "t4", zone, "item")
    c = base + np.array([0, 0, post_h + Hhh / 2 - 0.05])
    cx.S.add(Frame(c, (0, 1, 0)).pp(lbox((0, 0, 0), (Wh, Lh, Hhh), bev=0.12)), "t1", zone, "item", "w")
    x = -Wh / 2 + 0.25
    for it, dm in zip(miss, dims):
        L, W, Hh, _g = cx.geoms[id(it)]
        x += W / 2
        _emit(cx, zone, it, Frame(c + np.array([x, Lh / 2 - L, -Hh / 2]), (0, 1, 0), (0, 0, 1)))
        x += W / 2 + 0.2


# ------------------------------------------------------------------------------------------------------------ assembly

def assemble(model, P, S, Hm):
    cx = _common(model, P, S, Hm)
    bird = model["archetype"] == "bird" or model.get("legs") == "digitigrade"
    out, info = (body_bird if bird else body_humanoid)(cx)
    sol = {}
    for p, cls, role, name, zone in out:
        so = S.add(p, cls, zone, role)
        if role == "core":
            sol[(zone, name)] = so
    for zone, nm in info["torso_names"].items():
        so = sol[(zone, nm)]
        lo, hi = so.pts.min(0), so.pts.max(0)
        cx.sec[zone] = (so, (lo[0] + hi[0]) / 2, hi[0] - lo[0], hi[1] - lo[1])
    cx.solids["head"] = sol[("Head", info["head"])]
    for side, zone in (("L", "Left Arm"), ("R", "Right Arm")):
        cx.solids[f"arm_{side}_up"] = sol[(zone, "upper")]
        cx.solids[f"arm_{side}_fore"] = sol[(zone, "fore")]
        j = cx.arm_j[side]
        cx.arm_axis[side] = _u(j["E"] - j["S"])
    for side, zone in (("L", "Left Leg"), ("R", "Right Leg")):
        cx.solids[f"leg_{side}_thigh"] = sol[(zone, info["thigh"])]
        cx.solids[f"leg_{side}_shin"] = sol[(zone, info["shin"])]
    SH.build_layers(cx, info["hd"], info["hx"], info["zh"], info["z0"])
    mount_rails(cx, info["rails"](cx))
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
