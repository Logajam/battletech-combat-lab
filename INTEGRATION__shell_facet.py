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
from INTEGRATION__shell import Frame, lbox, cyl, ellipsoid, Solid, Sink, fit, hull_vol, item_dims, item_geometry, _u

FACET_RANGE = SH.SHELL_RANGE                     # every chassis of the phase 1 test range


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

    def __init__(self, kind, solid, o, axis, dr=None, lat=(1, 0, 0), up=(0, 0, 1), embed=0.5, prefer=None):
        self.kind, self.solid, self.o, self.a, self.prefer = kind, solid, np.asarray(o, float), _u(axis), prefer
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
    """Move the legs apart; build the PELVIS (one block between the hips, in two halves that meet at the centre line, each sized by
    its hip actuator) and a hip joint drum at each side of it; record the joints. Returns the pelvis top (the waist sits on it).
    Daniel, 2026-11-04: twin hip blocks lost the hips-to-waist actuator system the kits show (the torso twists on the waist)."""
    Hm = cx.Hm
    hp = 0.10 * Hm
    top = 0.0
    for zone, (o, w, d, J0, segs0) in legs.items():
        sg = -1 if zone.startswith("Left") else 1
        mv = np.array([sg * hx, 0, 0])
        o = [(p + mv,) + tuple(r) for p, *r in o]
        yh_, zh_ = J0["hip"][1], J0["hip"][2]
        wx = max(0.02, hx - w * 0.25)                                      # the pelvis half reaches into the hip joint
        dp = min(max(cx.hipv[zone] / (wx * hp * 0.85), d * 1.6), 0.32 * Hm)
        c = np.array([sg * (0.01 + wx / 2), yh_ * 0.5, zh_ + 0.012 * Hm])
        o.append((Frame(c, (0, 1, 0)).pp(lbox((0, 0, 0), (wx, dp, hp), bev=0.2 * hp, tap=(0.92, 0.8))), "t1", "core", "hip"))
        o.append((prism(np.array([sg * (hx - w * 0.55), yh_, zh_]), np.array([sg * (hx + w * 1.05), yh_, zh_]), w * 0.95, w * 0.95, n=8, lat=(0, 1, 0)),
                  "t4", "cover", "hip_joint"))
        top = max(top, c[2] + hp / 2)
        for p, cls, role, name in o:
            out.append((p, cls, role, name, zone))
        J = {k: v + mv for k, v in J0.items()}
        cx.leg_j["L" if sg < 0 else "R"] = (J, [(J[a], J[b], w0, d0, w1, d1) for a, b, w0, d0, w1, d1 in segs0])
    cx.pelvis_top = top
    return top


def _waist(cx, out, top, yc, env_ct):
    """The waist: a vertical drum on the pelvis that the torso turns on (the torso-twist actuator). Part of the centre torso;
    returns (its top, its volume)."""
    Hm = cx.Hm
    r, hw = 0.075 * Hm, 0.05 * Hm
    pts = prism(np.array([0, yc, top - 0.02 * Hm]), np.array([0, yc, top + hw]), r, r * 0.9, r * 0.95, r * 0.85, n=12, lat=(1, 0, 0))
    out.append((pts, "t4", "core", "waist", "Center Torso"))
    return top + hw, hull_vol(pts)


def _antennas(cx, out, hsol):
    """Thin faceted masts on the head (the `antennas` tag)."""
    n_a = int(cx.m.get("antennas") or 0) or (1 if cx.m.get("antenna") else 0)
    lo, hi = hsol.pts.min(0), hsol.pts.max(0)
    for i in range(n_a):
        x = (lo[0] + hi[0]) / 2 + (0 if n_a == 1 else (-1 if i % 2 == 0 else 1) * 0.3 * (hi[0] - lo[0]))
        top, _n = hsol.hit(np.array([x, lo[1] * 0.4 + hi[1] * 0.6 - 0.25 * (hi[1] - lo[1]), (lo[2] + hi[2]) / 2]), (0, 0, 1))
        out.append((prism(top - np.array([0, 0, 0.05]), top + np.array([0, -0.015 * cx.Hm, 0.11 * cx.Hm]), 0.05, 0.05, 0.02, 0.02, n=6, ch=0.1), "t4", "detail", "antenna", "Head"))


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
    b_pose = pick(cx, "pose")

    def leg(s, sg):
        J0, _l = pose_joints(b_pose, sg, zh, Hm, bird=True)
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
    for sg, zone in ((-1, "Left Leg"), (1, "Right Leg")):
        s = fit(lambda s_: leg(s_, sg)[0], max(0.4 * env[zone], env[zone] - cx.hipv[zone]), vol)
        legs[zone] = leg(s, sg)
    hx = max(l[1] for l in legs.values()) * 1.2 + 0.05 * Hm                   # a wide stance
    ptop = _hips(cx, legs, hx, zh, out)

    pitch = math.radians(9)
    yc = 0.02 * Hm
    wtop_, wv_ = _waist(cx, out, ptop, yc, env["Center Torso"])
    z0 = wtop_ - 0.03 * Hm
    env = dict(env)
    env["Center Torso"] = max(0.4 * env["Center Torso"], env["Center Torso"] - wv_)

    def housing(it):
        L, W, Hh, _g = cx.geoms[id(it)]
        return W + 0.5, max(L, 0.18 * Hm), Hh + 0.5
    cx.housing = housing
    hous = {z: sum(a * b * c for a, b, c in (housing(it) for it in P["items"].get(z, []) if it["kind"] == "missile" and it["visible"]))
            for z in ("Left Torso", "Right Torso")}

    wk = 0.8 if cx.m.get("torso") == "narrow" else 1.0

    def body(s):
        Lb, Wb, Hb = 0.52 * Hm * s, 0.30 * Hm * s * wk, 0.30 * Hm * s * cx.m.get("bodyh", 1.0) ** 0.5
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
    _antennas(cx, out, hsol)

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



# ------------------------------------------------------------------------------------------------------- block library
# Each SLOT of the faceted humanoid has interchangeable BLOCKS. A tag picks the block where it says something (TAG_PICKS); otherwise
# the unit's name hash does, so an untagged unit still gets a coherent, stable combination. The choice is written to model["blocks"].

BLOCKS = {
    "pose": ("stride", "ready", "crouch"),
    "torso": ("v_chest", "box", "slab", "wedge", "round"),
    "housing": ("none", "housing"),
    "missiles": ("face", "bay"),
    "arm": ("pod", "straight"),
    "leg": ("prism", "slab", "pillar", "greave"),
    "knee": ("drum", "cap", "guard"),
    "foot": ("heel_toe", "wedge", "three_toe"),
    "pauldron": ("box", "slant", "drum", "collar"),
    "head": ("box", "skull", "dome", "wedge", "bubble", "visor", "turret", "hood"),
    "forearm": ("octagon", "square", "round"),
}


def TAG_PICKS(m):
    t = {}
    if m.get("crouch"):
        t["pose"] = "crouch"
    tor, pk = m.get("torso"), m.get("profile")
    if tor in ("dome", "ovoid") or pk == "dome" or m.get("kit") == "round_blocks":
        t["torso"] = "round"                             # the old blocks' rounded ovoid body (Daniel liked it on the UrbanMech)
    elif tor == "slab" or pk == "tall_slab":
        t["torso"] = "slab"
    elif pk in ("wedge_up", "lean", "sloped", "prow"):
        t["torso"] = "wedge"
    elif pk in ("shoulder",) or m.get("head_mount") == "notch":
        t["torso"] = "v_chest"
    elif pk == "bell":
        t["torso"] = "box"
    if pk in ("hunch", "stepped"):
        t["housing"] = "housing"
    if m.get("kit") in ("tall_launchers", "launchers"):
        t["missiles"] = "bay"                            # the Archer: racks in the torso top under raised doors (Daniel, 2026-11-04)
    hs_, hm_ = m.get("head_shape"), m.get("head_mount")
    if hm_ == "built_in":
        t["head"] = "hood"                               # a cockpit built into the torso: a low armoured cowl
    elif hs_ in ("box", "skull", "dome", "wedge", "visor"):
        t["head"] = hs_
    if m.get("arm_style") == "long_barrel":
        t["arm"] = "straight"                            # the JagerMech: gun and upper arm in one line from the shoulder
    legs = m.get("legs")
    if legs in ("slab", "pillar"):
        t["leg"] = legs
    elif legs == "heavy":
        t["leg"] = "greave"
    if legs == "slab":
        t["knee"] = "guard"
    if m.get("feet") == "thrusters" or legs == "pillar":
        t["foot"] = "wedge"
    if m.get("kit") == "pauldrons":
        t["pauldron"] = "box"
    elif m.get("kit") == "round_blocks":
        t["pauldron"], t["forearm"], t["leg"] = "drum", "round", t.get("leg", "pillar")
    elif m.get("shoulders") == "flush":
        t["pauldron"] = "collar"
    return t


def pick(cx, slot):
    """The block for a slot: the tag's choice, else the name hash's (a byte of the hash per slot)."""
    tagged = TAG_PICKS(cx.m) if not cx.m.get("hash_only") else {}
    forced = cx.m.get("force_blocks") or {}               # a lineup or a test can force a block (tools/token_heads.py)
    if slot in forced:
        choice, why = forced[slot], "forced"
    elif slot in tagged:
        choice, why = tagged[slot], "tag"
    else:
        opts = BLOCKS[slot]
        choice, why = opts[(cx.P["hash"] >> (8 * (list(BLOCKS).index(slot) + 1))) % len(opts)], "name hash"
    cx.m.setdefault("blocks", {})[slot] = (choice, why)
    return choice


def leg_block(kind, J0, w, d):
    """Thigh and shin of a straight leg: [(pts, cls, role, name)] and the segments for the skeleton / myomer layers."""
    hip, knee, ankle = J0["hip"] + np.array([0, 0, 0.0]), J0["knee"], J0["ankle"]
    up = np.array([0, 0, 1.0])
    if kind == "slab":                                   # flat-faced: wide across, shallow front to back, six-sided
        tw, td, sw0, sd0, sw1, sd1, n = (w * 1.15, d * 0.8, w * 1.1, d * 0.85, w * 0.9, d * 0.7, 6)
    elif kind == "pillar":                               # round and even: the same section top to bottom
        tw, td, sw0, sd0, sw1, sd1, n = (w, d, w, d, w * 0.92, d * 0.92, 12)
    elif kind == "greave":                               # a flared armoured shin, wide under the knee, narrow at the ankle
        tw, td, sw0, sd0, sw1, sd1, n = (w * 0.95, d * 0.95, w * 1.12, d * 1.28, w * 0.66, d * 0.7, 8)
    else:
        tw, td, sw0, sd0, sw1, sd1, n = (w, d, w * 0.95, d * 1.08, w * 0.78, d * 0.84, 8)
    o = [(prism(hip + up * 0.03 * np.linalg.norm(hip - knee), knee, tw, td, tw * 0.9, td * 0.92, n, ch=0.15), "t2", "core", "thigh"),
         (prism(knee + up * 0.02 * np.linalg.norm(knee - ankle), ankle, sw0, sd0, sw1, sd1, n, ch=0.15), "t2", "core", "shin")]
    segs0 = [("hip", "knee", tw, td, tw * 0.9, td * 0.92), ("knee", "ankle", sw0, sd0, sw1, sd1)]
    return o, segs0


def knee_block(kind, J0, w, d, Hm):
    knee, ankle = J0["knee"], J0["ankle"]
    o = [(prism(ankle - np.array([w * 0.95, 0, 0]), ankle + np.array([w * 0.95, 0, 0]), d * 0.6, d * 0.6, n=8, lat=(0, 1, 0)), "t4", "cover", "ankle_drum")]
    r = d * (0.95 if kind == "drum" else 0.75)
    o.append((prism(knee - np.array([w * 1.12, 0, 0]), knee + np.array([w * 1.12, 0, 0]), r, r, n=8, lat=(0, 1, 0)), "t4", "cover", "knee_drum"))
    if kind in ("cap", "guard"):                         # a plate over the front of the knee (the Atlas kit's knee guard)
        hk = (0.07 if kind == "cap" else 0.12) * Hm
        c = knee + np.array([0, d * 0.95, -0.15 * hk])
        o.append((Frame(c, (0, 1, 0)).pp(lbox((0, 0, 0), (2 * w * 0.95, d * 0.55, hk), bev=0.2 * d, tap=(0.8, 0.75))), "t3", "cover", "knee_guard"))
    return o


def foot_block(kind, J0, w, s, Hm):
    wf, Lf, hf = 0.07 * Hm * s ** 0.5, 0.27 * Hm, 0.075 * Hm
    heel = J0["ankle"][1] - 0.09 * Hm
    fr = Frame((0, heel, 0), (0, 1, 0))
    if kind == "wedge":                                  # one block, low at the toe
        return [(fr.pp(lbox((0, Lf * 0.48, hf / 2), (2 * wf, Lf * 0.96, hf), bev=0.2 * hf, tap=(0.85, 0.45))), "t1", "core", "foot")]
    o = [(fr.pp(lbox((0, Lf * 0.3, hf / 2), (2 * wf, Lf * 0.6, hf), bev=0.2 * hf, tap=(0.95, 0.8))), "t1", "core", "foot")]
    toes = (-1, 1) if kind == "heel_toe" else (-1, 0, 1)
    tw = 2 * wf / len(toes)
    for i, sx in enumerate(toes):
        x = sx * (wf - tw / 2) if len(toes) == 2 else sx * tw
        o.append((fr.pp(lbox((x, Lf * 0.76, hf * 0.3), (tw * 0.92, Lf * 0.44, hf * 0.6), bev=0.18 * hf, tap=(0.85, 0.55))), "t2", "core", "toe"))
    return o


def pauldron_block(kind, S_, sg, wa, kp):
    """Over the shoulder joint: a box, a pad sloping outward and down, a drum across the joint, or only a collar."""
    if kind == "drum":
        return [(prism(S_ - np.array([sg * wa * 0.6, 0, 0]), S_ + np.array([sg * wa * 1.7 * kp, 0, 0]), 1.25 * wa * kp, 1.25 * wa * kp, n=10, lat=(0, 1, 0)), "t3", "cover", "pauldron")]
    if kind == "collar":
        return [(prism(S_ - np.array([sg * wa * 0.5, 0, -0.2 * wa]), S_ + np.array([sg * wa * 1.2, 0, 0.2 * wa]), 1.02 * wa, 1.1 * wa, n=8, lat=(0, 1, 0)), "t3", "cover", "pauldron")]
    if kind == "slant":
        pc = S_ + np.array([sg * wa * 0.45, 0, wa * 0.55])
        fr = Frame(pc, (0, 1, 0), up=(-sg * 0.42, 0, 1))
        return [(fr.pp(lbox((0, 0, 0), (2.5 * wa * kp, 2.4 * wa * kp, 1.3 * wa * kp), bev=0.35 * wa, tap=(0.85, 0.75))), "t3", "cover", "pauldron")]
    pc = S_ + np.array([sg * wa * 0.2, 0, wa * 0.45])
    return [(Frame(pc, (0, 1, 0)).pp(lbox((0, 0, 0), (2.2 * wa * kp, 2.5 * wa * kp, 2.3 * wa * kp), bev=0.4 * wa, tap=(0.8, 0.72))), "t3", "cover", "pauldron")]


FOREARM_N = {"octagon": 8, "square": 4, "round": 12}

def clip_x(pts, x0=None, x1=None):
    """The vertices of the part of a convex solid between the planes x = x0 and x = x1 (either may be None): how one torso solid
    is cut into its three locations."""
    from scipy.spatial import ConvexHull as _CH, HalfspaceIntersection
    pts = np.asarray(pts, float)
    h = _CH(pts)
    hs = [list(e) for e in h.equations]
    lo = pts[:, 0].min() if x0 is None else x0
    hi = pts[:, 0].max() if x1 is None else x1
    if x0 is not None:
        hs.append([-1.0, 0, 0, x0])
    if x1 is not None:
        hs.append([1.0, 0, 0, -x1])
    c = pts.mean(0).copy()
    c[0] = (lo + hi) / 2
    return HalfspaceIntersection(np.array(hs), c).intersections


def split_x(pts, v_left, v_right, min_c):
    """Cut one solid at x = xa and x = xb so the part left of xa holds v_left and the part right of xb holds v_right (bisection);
    the centre keeps at least min_c of width."""
    lo, hi = float(pts[:, 0].min()), float(pts[:, 0].max())

    def find(target, side):
        a, b = lo + 1e-3, hi - 1e-3
        for _ in range(28):
            m_ = (a + b) / 2
            v = hull_vol(clip_x(pts, None, m_)) if side < 0 else hull_vol(clip_x(pts, m_, None))
            if (v < target) == (side < 0):
                a = m_
            else:
                b = m_
        return (a + b) / 2
    xa, xb = find(v_left, -1), find(v_right, 1)
    if xb - xa < min_c:                                  # keep a centre torso: share the shortfall
        mid = (xa + xb) / 2
        xa, xb = mid - min_c / 2, mid + min_c / 2
    return xa, xb


def torso_block(kind, W, D, h, z0, yc, Hm):
    """One solid for the whole torso, by block: a V-chest (broad at the shoulders, pulled in at the belly), a box, a tall slab, a
    wedge (deep chest, low back), a dome (round in plan and front: the UrbanMech)."""
    if kind == "round":                                  # a faceted ovoid, the old blocks' UrbanMech body: round in plan, front and side
        pts = []
        for v, f in ((0.0, 0.5), (0.12, 0.8), (0.3, 0.96), (0.5, 1.0), (0.7, 0.94), (0.86, 0.76), (1.0, 0.42)):
            for i in range(10):
                ang = 2 * math.pi * (i + 0.5) / 10
                pts.append((W / 2 * f * math.cos(ang), yc + D / 2 * f * math.sin(ang), z0 + v * h * 1.1))
        return np.array(pts)
    prof = {"v_chest": CHEST, "box": T.PROFILES["upright"], "slab": T.PROFILES["upright"], "wedge": T.PROFILES["wedge_up"]}[kind]
    wtop = {"v_chest": 1.28, "box": 0.95, "slab": 1.0, "wedge": 1.05}[kind]
    return SH.prof_solid(-W / 2, W / 2, yc, D, z0, h * (1.12 if kind == "slab" else 1.0), prof, wtop=wtop, e=0.03 * Hm, k=0.9)


# the three torso parts of each torso block: (side-view profile, width at the top against the belly, height and depth factors)
TORSO_PARTS = {
    "v_chest": {"ct": ("chest", 1.0, 1.0, 1.0), "st": ("chest", 1.22, 1.0, 0.9)},             # side torsos broad at the shoulder
    "box": {"ct": ("upright", 0.96, 1.0, 1.0), "st": ("upright", 0.96, 0.95, 0.92)},
    "slab": {"ct": ("upright", 1.0, 1.12, 1.0), "st": ("upright", 1.0, 1.08, 0.9)},
    "wedge": {"ct": ("wedge_up", 1.0, 1.0, 1.0), "st": ("wedge_up", 1.08, 0.94, 0.9)},
}


def torso_pieces(kind, tgt, D, h, z0, yc, Hm, notch=False, min_outer=0.0):
    """The torso as THREE parts that fit together (Daniel, 2026-11-04: 'The torso of any mech should have 3 parts that fit
    together'): a centre torso standing a little forward and two side torsos set a little back, each its own block whose edges
    are cut (so a seam shows where they meet), each as wide as its own budget needs at the torso's depth. A round body is one ovoid
    solid cut into three, so that its parts still make one body."""
    if kind == "round":
        tp = torso_block("round", 0.4 * Hm * _fit_scale(lambda s_: torso_block("round", 0.4 * Hm * s_, D, h, z0, yc, Hm), sum(tgt.values())), D, h, z0, yc, Hm)
        xa, xb = split_x(tp, tgt["Left Torso"], tgt["Right Torso"], 0.035 * Hm)
        return {"Center Torso": clip_x(tp, xa, xb), "Left Torso": clip_x(tp, None, xa), "Right Torso": clip_x(tp, xb, None)}
    spec = TORSO_PARTS[kind]

    def prof(p):
        return CHEST if p == "chest" else T.PROFILES[p]
    pc, wc_top, hc, dc = spec["ct"]
    ps, ws_top, hs, ds = spec["st"]
    hct = h * hc * (0.86 if notch else 1.0)

    dct = D * dc
    for _round in range(4):                              # CT depth at most CT_RATIO x the side torsos' (Daniel: no cross from above)
        out, sdep = _torso_parts(ct_fn=lambda w, dd: SH.prof_solid(-w / 2, w / 2, yc + 0.03 * dd, dd, z0, hct, prof(pc), wtop=wc_top, e=0.03 * Hm, k=0.9),
                                 dct=dct, tgt=tgt, D=D, ds=ds, h=h, hs=hs, ps=prof(ps), ws_top=ws_top, z0=z0, yc=yc, Hm=Hm, min_outer=min_outer)
        if dct <= CT_RATIO * min(sdep) + 1e-6:
            break
        dct = CT_RATIO * min(sdep)
    return out


CT_RATIO = 1.25


def _torso_parts(ct_fn, dct, tgt, D, ds, h, hs, ps, ws_top, z0, yc, Hm, min_outer):
    wc = 0.15 * Hm * _fit_scale(lambda s_: ct_fn(0.15 * Hm * s_, dct), tgt["Center Torso"])
    out = {"Center Torso": ct_fn(wc, dct)}
    sdep = []
    e = 0.012 * Hm                                       # the side torsos tuck a little under the centre torso's cut edge
    for sg, zone in ((-1, "Left Torso"), (1, "Right Torso")):
        def st(w, dk=1.0, sg=sg):
            x0, x1 = sg * (wc / 2 - e), sg * (wc / 2 - e + w)
            return SH.prof_solid(min(x0, x1), max(x0, x1), yc - 0.03 * D, D * ds * dk, z0, h * hs, ps, wtop=ws_top, e=0.03 * Hm, k=0.9)
        ws = 0.12 * Hm * _fit_scale(lambda s_: st(0.12 * Hm * s_), tgt[zone])
        dk = 1.0
        if wc / 2 - e + ws < min_outer:                  # widen to reach the shoulder line, then thin the depth to keep the volume
            ws = min_outer - (wc / 2 - e)
            dk = max(0.45, min(1.0, _fit_scale(lambda s_: st(ws, s_), tgt[zone])))
        out[zone] = st(ws, dk)
        sdep.append(D * ds * dk)
    return out, sdep


def pose_joints(kind, sg, zh, Hm, bird=False):
    """Leg joints (at x = 0) for a pose. humanoid: stride (left leg forward, right back, knees bent), ready (both knees bent),
    crouch (deep bend); bird: stride staggers the legs, ready does not. Returns (J0, the hip height factor, the forward lean)."""
    if bird:
        k = 0.03 * Hm * (sg if kind == "stride" else 0)
        zb = zh * (0.94 if kind == "crouch" else 1.0)
        J = {"hip": np.array([0, k * 0.4, zb]), "knee": np.array([0, 0.14 * Hm + k, zb * 0.72]), "hock": np.array([0, -0.07 * Hm + k, zb * 0.34]),
             "ankle": np.array([0, 0.03 * Hm + k * 1.4, 0.075 * Hm])}
        return J, 0.0
    bend = {"stride": 0.07, "ready": 0.06, "crouch": 0.11}[kind]
    drop = {"stride": 0.96, "ready": 0.97, "crouch": 0.88}[kind]
    lean = {"stride": 7.0, "ready": 4.0, "crouch": 10.0}[kind]
    st = 0.045 * Hm * (-sg) if kind == "stride" else 0.0          # the left leg (sg -1) steps forward
    z = zh * drop
    J = {"hip": np.array([0, st * 0.3, z]), "knee": np.array([0, bend * Hm + st * 1.2, z * 0.53]), "ankle": np.array([0, st * 1.6, 0.085 * Hm])}
    return J, math.radians(lean)


def lean_pts(p, pivot, ang):
    """Rotate points about the x axis through `pivot` so the top moves forward (+y) by `ang`."""
    p = np.asarray(p, float)
    d = p - pivot
    cs, sn = math.cos(ang), math.sin(ang)
    return pivot + np.stack([d[:, 0], d[:, 1] * cs + d[:, 2] * sn, d[:, 2] * cs - d[:, 1] * sn], 1)



# ----------------------------------------------------------------------------------------------------------- head blocks
# One shaped solid each, with its cockpit glass and a detail or two. (width, depth, height) factors on the base head size; every
# head is fitted to the Head location's budget. The glass is class "ck" (blue), placed where a ray from the head's centre leaves it.
HEAD_SIZE = {"box": (1.0, 1.0, 1.0), "skull": (1.0, 1.0, 1.05), "dome": (1.05, 1.05, 0.95), "wedge": (0.95, 1.2, 0.85),
             "bubble": (1.0, 1.0, 0.9), "visor": (1.1, 1.0, 0.85), "turret": (0.9, 0.9, 1.1), "hood": (1.4, 1.1, 0.6)}
HEAD_DROP = {"notch": 0.55, "built_in": 0.62, "front": 0.8}                 # how deep the head sits in the torso, by mount


def head_block(kind, hw, hdp, hh, yh, zb, Hm):
    """[(pts, cls, role, name)] of a head block; the first entry is the head's own solid (the Head location's core)."""
    e = 0.02 * Hm
    out = []

    def glass(sol, p_in, d, w, h, up=(0, 0, 1), t=0.07):
        pt, n = sol.hit(np.asarray(p_in, float), d)
        out.append((SH.slab(pt - n * 0.02, n, up, w, h, t), "ck", "cover", "glass"))

    c = np.array([0.0, yh, zb + hh * 0.5])
    if kind == "dome":                                    # a rounded cap; a band of three windows round the front
        pts = []
        for v, f in ((0.0, 0.92), (0.35, 1.0), (0.6, 0.9), (0.8, 0.66), (0.94, 0.36), (1.0, 0.12)):
            for i in range(10):
                a_ = 2 * math.pi * (i + 0.5) / 10
                pts.append((hw * f * math.cos(a_), yh + hdp * f * math.sin(a_), zb + v * hh))
        main = np.array(pts)
        out.append((main, "t3", "core", "head"))
        so = Solid(main)
        for ang in (-38, 0, 38):
            d = np.array([math.sin(math.radians(ang)), math.cos(math.radians(ang)), 0.0])
            glass(so, c + np.array([0, 0, hh * 0.05]), d, hw * 0.5, hh * 0.2)
    elif kind == "bubble":                                # an armoured collar with a glass canopy on it
        main = prism(np.array([0, yh, zb]), np.array([0, yh, zb + hh * 0.45]), hw, hdp, hw * 0.92, hdp * 0.92, n=10, lat=(1, 0, 0))
        out.append((main, "t3", "core", "head"))
        out.append((ellipsoid((0, yh + hdp * 0.12, zb + hh * 0.45), (hw * 0.8, hdp * 0.85, hh * 0.55), 40), "ck", "cover", "canopy"))
    elif kind == "turret":                                # an eight-sided turret, a vertical slit, two sensor ears
        main = prism(np.array([0, yh, zb]), np.array([0, yh, zb + hh]), hw, hdp, hw * 0.9, hdp * 0.9, n=8, ch=0.1, lat=(1, 0, 0))
        out.append((main, "t3", "core", "head"))
        so = Solid(main)
        glass(so, c, (0, 1, 0), hw * 0.28, hh * 0.6)
        for sx in (-1, 1):
            out.append((prism(np.array([sx * hw * 0.8, yh - hdp * 0.1, zb + hh * 0.55]), np.array([sx * hw * 1.35, yh - hdp * 0.1, zb + hh * 0.6]),
                              hh * 0.12, hh * 0.18, n=6, lat=(0, 1, 0)), "t4", "cover", "ear"))
    else:
        prof = {"box": T.PROFILES["upright"], "skull": SH.HEAD_PROF["skull"], "wedge": [(-1, 0), (1, 0), (1, .3), (-.35, 1), (-1, 1)],
                "visor": T.PROFILES["upright"], "hood": [(-1, 0), (1, 0), (1, .42), (.35, 1), (-1, .8)]}[kind]
        main = SH.prof_solid(-hw, hw, yh, 2 * hdp, zb, hh, prof, wtop=0.86 if kind != "hood" else 0.95, e=e, k=0.88)
        out.append((main, "t3", "core", "head"))
        so = Solid(main)
        if kind == "box":                                 # one wide visor strip
            glass(so, c + np.array([0, 0, hh * 0.12]), (0, 1, 0), hw * 1.5, hh * 0.16)
        elif kind == "skull":                             # two eye sockets and a jaw plate
            for sx in (-1, 1):
                glass(so, c + np.array([sx * hw * 0.42, 0, hh * 0.12]), (0, 1, 0), hw * 0.5, hh * 0.14)
            pt, n = so.hit(c - np.array([0, 0, hh * 0.32]), (0, 1, 0))
            out.append((SH.slab(pt - n * 0.04, n, (0, 0, 1), hw * 0.9, hh * 0.24, 0.12), "t4", "cover", "jaw"))
        elif kind == "wedge":                             # the glass lies on the sloped front
            d = _u((0, 0.75, 0.66))
            pt, n = so.hit(c, d)
            out.append((SH.slab(pt - n * 0.02, n, _u(np.cross(n, (1, 0, 0))) * -1, hw * 1.4, hh * 0.5, 0.07), "ck", "cover", "glass"))
        elif kind == "visor":                             # a heavy brow over a recessed slit
            pt, n = so.hit(c + np.array([0, 0, hh * 0.32]), (0, 1, 0))
            out.append((Frame(pt + np.array([0, hdp * 0.12, 0]), (0, 1, 0)).pp(lbox((0, 0, 0), (hw * 2.1, hdp * 0.5, hh * 0.18), bev=0.03, tap=(0.95, 0.7))), "t4", "cover", "brow"))
            glass(so, c, (0, 1, 0), hw * 1.6, hh * 0.12)
        elif kind == "hood":                              # a low cowl: a long thin slot across its front
            glass(so, c + np.array([0, 0, hh * 0.05]), (0, 1, 0), hw * 1.4, hh * 0.18)
    return out


# --------------------------------------------------------------------------------------------------- humanoid (Atlas)

# side view of a chest section: the belly pulled in, deep at the chest, the top cut back (the kit's V-shaped chest)
CHEST = [(-.62, 0), (.55, 0), (1, .32), (1, .8), (.62, 1), (-.8, 1), (-1, .84), (-1, .34)]


def body_humanoid(cx):
    """A humanoid in one solid per part, assembled from the block library (BLOCKS, picked by tag or name hash): a pose (bent knees,
    a staggered stance, a forward lean), one torso solid cut into its three locations, an optional gun housing on a side torso,
    missile racks in the face or in a bay under raised doors, legs, knees, feet, pauldrons, and fist arms, gun pods or straight
    gun arms."""
    P, S, Hm, env, m = cx.P, cx.S, cx.Hm, cx.env, cx.m
    out, vol = [], SH.vol_of
    b_pose = pick(cx, "pose")
    zh0 = (0.42 if m.get("profile") == "dome" else 0.50) * Hm * m.get("legscale", 1.0) ** 0.5
    b_leg, b_knee, b_foot = pick(cx, "leg"), pick(cx, "knee"), pick(cx, "foot")
    asp = 1.15

    def leg(s, sg):
        J0, _l = pose_joints(b_pose, sg, zh0, Hm)
        w = 0.04 * Hm * s
        d = w * asp
        o, segs0 = leg_block(b_leg, J0, w, d)
        o += knee_block(b_knee, J0, w, d, Hm)
        o += foot_block(b_foot, J0, w, s, Hm)
        return o, w, d, J0, segs0

    legs = {}
    for sg, zone in ((-1, "Left Leg"), (1, "Right Leg")):
        s = fit(lambda s_: leg(s_, sg)[0], max(0.4 * env[zone], env[zone] - cx.hipv[zone]), vol)
        legs[zone] = leg(s, sg)
    hx = max(l[1] for l in legs.values()) * 1.15 + 0.035 * Hm
    ptop = _hips(cx, legs, hx, zh0, out)
    _jl, lean = pose_joints(b_pose, 1, zh0, Hm)
    zh = max(l[3]["hip"][2] for l in legs.values())
    yc = 0.0
    wtop_, wv_ = _waist(cx, out, ptop, yc, env["Center Torso"])

    # torso: three parts on the waist, deep (0.36 of the height), each part fitted to its own location's budget
    z0 = wtop_ - 0.015 * Hm
    env = dict(env)
    env["Center Torso"] = max(0.4 * env["Center Torso"], env["Center Torso"] - wv_)
    b_tor, b_hous, b_miss = pick(cx, "torso"), pick(cx, "housing"), pick(cx, "missiles")
    h, D = 0.27 * Hm * m.get("bodyh", 1.0), 0.36 * Hm * m.get("bodyd", 1.0)        # deep: wide side torsos (structure-point bulk) must not balloon sideways

    def housing(it):                                      # a missile bay's or post's share of its side torso
        L, W, Hh, _g = cx.geoms[id(it)]
        return W + 0.3, L, Hh + 0.3
    cx.housing, cx.missile_mount = housing, b_miss
    # the gun housing (a standard block: the Hunchback's hump): on the side torso with the heaviest gun, sized by that gun
    cx.hump = None
    guns = {z: [it for it in P["items"].get(z, []) if it["visible"] and it["kind"] in SH.RAILKINDS and it["kind"] != "missile"] for z in ("Left Torso", "Right Torso")}
    hz = max(guns, key=lambda z: max([it["tons"] for it in guns[z]] or [0]))
    big = max(guns[hz], key=lambda it: it["tons"]) if guns[hz] else None
    if b_hous == "housing" and big is not None and (big["tons"] >= 6 or "housing" == TAG_PICKS(m).get("housing")):
        L_, W_, H_, _g = cx.geoms[id(big)]
        hous_dims = (max(1.9 * W_, 0.13 * Hm), max(0.85 * L_, 0.22 * Hm), max(1.9 * H_, 0.12 * Hm))
        cap = 0.45 * env[hz] / 0.8                        # the housing never takes more than 45 percent of its side torso
        vh = hous_dims[0] * hous_dims[1] * hous_dims[2]
        if vh > cap:
            k_ = (cap / vh) ** (1 / 3)
            hous_dims = tuple(x * k_ for x in hous_dims)
    else:
        hz, hous_dims = None, None
        if b_hous == "housing":
            cx.m["blocks"]["housing"] = ("none", "no heavy gun")
    tz = ("Left Torso", "Center Torso", "Right Torso")
    tgt = {z: env[z] for z in tz}
    for z in ("Left Torso", "Right Torso"):
        if b_miss == "bay":       # racks in a bay sit INSIDE the side torso: their volume belongs to the torso block, not outside it
            tgt[z] += sum(SH.item_volume(cx.geoms[id(it)][3]) for it in P["items"].get(z, []) if it["kind"] == "missile" and it["visible"])
        if z == hz:
            tgt[z] -= hous_dims[0] * hous_dims[1] * hous_dims[2] * 0.8
        tgt[z] = max(0.35 * env[z], tgt[z])
    # shoulders outside the hips (Daniel, 2026-11-04: "shoulder joints should generally be farther out than the hip joints"; tiny
    # arms excepted): the side torsos reach far enough out, and get shallower rather than bigger to keep their volume
    hip_out = hx + max(l[1] for l in legs.values()) * 1.05
    wa_est = 0.032 * Hm * m.get("armscale", 1.0) ** 0.5
    min_out = 0.0 if m.get("arm_style") == "tiny" else 1.22 * hip_out - 1.15 * wa_est
    pieces = torso_pieces(b_tor, tgt, D, h, z0, yc, Hm, notch=(m.get("head_mount") == "notch"), min_outer=min_out)
    for zone, pp in pieces.items():
        out.append((pp, "t2" if zone == "Center Torso" else "t1", "core", "chest" if zone == "Center Torso" else "side", zone))
    tpts = np.vstack(list(pieces.values()))
    xa, xb = float(pieces["Center Torso"][:, 0].min()), float(pieces["Center Torso"][:, 0].max())
    if hz:
        sp = pieces[hz]
        top = float(sp[:, 2].max())
        xm = float(sp[:, 0].mean())
        c = np.array([xm, yc + 0.02 * Hm, top + hous_dims[2] * 0.32])
        hp = Frame(c, (0, 1, 0)).pp(lbox((0, 0, 0), hous_dims, bev=0.03 * Hm, tap=(0.9, 0.82)))
        out.append((hp, "t2", "core", "hump", hz))
        cx.hump = (hz, hp)
    # head: a block from the head library, set into the torso by its mount, fitted to the Head location's budget
    b_head = pick(cx, "head")
    ztop = float(tpts[:, 2].max())
    mount = m.get("head_mount", "top")
    hk = HEAD_SIZE[b_head]

    def head_of(s_):
        hw, hdp, hh = 0.07 * Hm * s_ * hk[0], 0.085 * Hm * s_ * hk[1], 0.10 * Hm * s_ * hk[2]
        yh = yc + D * {"notch": 0.24, "built_in": 0.2, "front": 0.36}.get(mount, 0.0)
        zb = ztop - hh * HEAD_DROP.get(mount, 0.08)
        return head_block(b_head, hw, hdp, hh, yh, zb, Hm), (hw, hdp, hh, yh, zb)

    s_h = _fit_scale(lambda s_: head_of(s_)[0][0][0], env["Head"])
    hparts, (hw, hdp, hh, yh, zb) = head_of(s_h)
    out += [(p, c, r, nm, "Head") for p, c, r, nm in hparts]
    hsol = Solid(hparts[0][0])
    sides = {z: Solid(p) for p, c, r, nm, z in out if nm == "side"}
    _antennas(cx, out, hsol)

    # arms: shoulder drum and pauldron, then a fist arm (bent), a gun pod (forearm forward), or a straight gun arm (one line)
    kp = 1.0 + (0.25 if m.get("kit") == "pauldrons" else 0.0) + (0.12 if m.get("shoulders") == "boom" else 0.0)
    b_paul, b_fore = pick(cx, "pauldron"), pick(cx, "forearm")
    hands = [(m.get("arms") or {}).get(x, "hand") == "hand" for x in "LR"]
    b_arm = pick(cx, "arm") if not all(hands) else None
    for sg, zone, sd_ in ((-1, "Left Arm", "L"), (1, "Right Arm", "R")):
        sd = sides["Left Torso" if sg < 0 else "Right Torso"]
        xo = float((sd.pts[:, 0] * sg).max())
        hand = hands[0 if sg < 0 else 1]

        def arm(s, sg=sg, xo=xo, hand=hand):
            wa = 0.032 * Hm * s * m.get("armscale", 1.0) ** 0.5
            S_ = np.array([sg * (xo + wa * 1.15), yc, z0 + h * 0.82])
            Lpod = min(0.40 * Hm, (0.13 * Hm + _arm_used(P, zone)) * (1.2 if m.get("arm_style") == "long_barrel" else 1.0))
            if hand:
                E_ = S_ + np.array([0, 0.01 * Hm, -0.15 * Hm])
                pitch = math.radians(38)
                W_ = E_ + 0.16 * Hm * np.array([0, math.sin(pitch), -math.cos(pitch)])
            elif b_arm == "straight":                     # the gun lines up with the upper arm, straight out of the shoulder
                E_ = S_ + np.array([0, 0.11 * Hm, -0.01 * Hm])
                W_ = E_ + np.array([0, Lpod, -0.004 * Hm])
            else:                                         # a gun pod: upper arm down, the forearm aimed forward
                E_ = S_ + np.array([0, 0.01 * Hm, -0.15 * Hm])
                W_ = E_ + np.array([0, Lpod, 0.01 * Hm])
            a = _u(W_ - E_)
            nf = FOREARM_N[b_fore]
            o = [(prism(S_ - np.array([sg * wa * 1.2, 0, 0]), S_ + np.array([sg * wa * 0.8, 0, 0]), wa * 0.9, wa * 0.9, n=8, lat=(0, 1, 0)), "t4", "cover", "shoulder"),
                 (prism(S_, E_, wa * 0.85, wa * 0.9, wa * 0.8, wa * 0.85, nf), "t1", "core", "upper"),
                 (prism(E_ - np.array([wa * 0.95, 0, 0]), E_ + np.array([wa * 0.95, 0, 0]), wa * 0.85, wa * 0.85, n=8, lat=(0, 1, 0)), "t4", "cover", "elbow"),
                 (prism(E_ - a * (0.02 if hand else 0.05) * Hm, W_, wa * 1.1, wa * 1.2, wa * 1.0, wa * 1.05, nf), "t2", "core", "fore")]
            if hand:
                o.append((prism(W_ - a * 0.01 * Hm, W_ + a * 0.09 * Hm, wa * 0.95, wa * 1.0, wa * 0.85, wa * 0.85, 6, ch=0.2), "t1", "core", "fist"))
            o += pauldron_block(b_paul, S_, sg, wa, kp)
            return o, dict(S=S_, E=E_, W=W_, wa=wa, da=wa * 1.1, hand=hand)

        s_a = fit(lambda s_: arm(s_)[0], env[zone], vol)
        o, j = arm(s_a)
        out += [(p, c, r, nm, zone) for p, c, r, nm in o]
        cx.arm_j[sd_] = j
    # the pose's forward lean: everything above the hips turns about the hip line
    pivot = np.array([0, 0, zh])
    if lean:
        legz = ("Left Leg", "Right Leg")
        out = [((lean_pts(p, pivot, lean) if z not in legz else p), c, r, nm, z) for p, c, r, nm, z in out]
        for j in cx.arm_j.values():
            for k_ in ("S", "E", "W"):
                j[k_] = lean_pts(j[k_][None], pivot, lean)[0]
        if cx.hump:
            cx.hump = (cx.hump[0], lean_pts(cx.hump[1], pivot, lean))
        hc = lean_pts(np.array([[0, yh, zb]]), pivot, lean)[0]
        yh, zb = float(hc[1]), float(hc[2])
    cx.tor = dict(z0=z0, h=h, yc=yc + math.sin(lean) * h * 0.5, W=float(xb - xa), D=D, wc=float(xb - xa))
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
        if j.get("hand", True):
            R[zone] = [FRail("line", fo, mid, a, -ey), FRail("line", fo, mid, a, sg * ex), FRail("line", fo, mid, a, ey)]   # under (the kit's arm lasers), outer, top
        else:                                                                                            # a gun pod: its muzzle, its top, its outer side
            R[zone] = [FRail("face", fo, j["W"] - a * 0.3, a, lat=ex, up=ey), FRail("line", fo, mid, a, ey), FRail("line", fo, mid, a, sg * ex)]
    for zone in ("Left Torso", "Right Torso"):
        sg = -1 if zone.startswith("Left") else 1
        so = cx.sec[zone][0]
        lo, hi = so.pts.min(0), so.pts.max(0)
        c = (lo + hi) / 2
        R[zone] = [FRail("face", so, c + np.array([0, 0, 0.12 * (hi[2] - lo[2])]), (0, 1, 0), embed=0.55), FRail("line", so, c, (0, 1, 0), (sg, 0, 0)),
                   FRail("line", so, c, (0, 1, 0), (0, 0, 1)), FRail("face", so, c - np.array([0, 0, 0.22 * (hi[2] - lo[2])]), (0, 1, 0), embed=0.55)]
        if getattr(cx, "missile_mount", "face") == "bay":                       # racks in the torso top under raised doors
            R[zone][2] = FRail("bay", so, c, (0, 1, 0), (0, 0, 1))
        elif getattr(cx, "missile_mount", "face") == "post":
            R[zone][2] = FRail("post", so, c, (0, 1, 0), (0, 0, 1))
        if cx.hump and cx.hump[0] == zone:                                     # the hump's front face takes the heaviest gun
            hs_ = Solid(cx.hump[1])
            R[zone][0] = FRail("face", hs_, hs_.pts.mean(0), (0, 1, 0), embed=0.45, prefer="heavy")
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
        heavy = next((i for i, x in enumerate(rl) if x.prefer == "heavy"), None)
        guns = [it for it, r, c in placed if it["visible"] and it["kind"] in SH.RAILKINDS and it["kind"] != "missile"]
        big = max(guns, key=lambda it: it["tons"]) if (heavy is not None and guns) else None
        for it, r, c in sorted(placed, key=lambda q: (q[1], q[2])):
            if it is big:                                              # the hump carries the side torso's heaviest gun
                groups.setdefault(heavy, []).append(it)
                continue
            if not it["visible"]:
                continue
            if it["kind"] in SH.RAILKINDS:
                post = next((i for i, x in enumerate(rl) if x.kind in ("post", "bay")), None)
                if it["kind"] == "missile" and post is not None:          # a chassis with launcher posts keeps its missiles on them
                    r = post
                groups.setdefault(r % len(rl), []).append(it)
            else:
                pegs.setdefault(it["kind"], []).append(it)
        for r, items in groups.items():
            rail = rl[r]
            if rail.kind in ("post", "bay"):
                miss = [it for it in items if it["kind"] == "missile"]
                if miss:
                    (_launcher if rail.kind == "post" else _bay)(cx, zone, rail, miss)
                items = [it for it in items if it["kind"] != "missile"]
                rail = FRail("line", rail.solid, rail.o, rail.a, (0, 0, 1))
                if not items:
                    continue
            cx.try_only = True
            failed = (_face if rail.kind == "face" else _line)(cx, zone, rail, items)
            for it in failed:                             # a muzzle that would fire into the body: try the location's other rails
                placed_ = False
                for r2, alt in enumerate(rl):
                    if r2 == r or alt.kind not in ("face", "line"):
                        continue
                    if not (_face if alt.kind == "face" else _line)(cx, zone, alt, [it]):
                        placed_ = True
                        break
                if not placed_:
                    cx.try_only = False
                    (_face if rail.kind == "face" else _line)(cx, zone, rail, [it])
            cx.try_only = False
        for kind, lst in pegs.items():
            lst = lst[:6]
            for idx, it in enumerate(lst):
                SH.mount_peg(cx, zone, it, idx, len(lst))


def _muzzle_blocked(cx, it, fr, reach=1.2):
    """True when the space in front of a weapon's muzzle (its cross-section, `reach` metres ahead) runs into the body: the
    negative space in front of every weapon (Daniel, 2026-11-04) must stay clear."""
    L, W, Hh, _g = cx.geoms[id(it)]
    c = fr.o + fr.a * L + fr.z * (Hh / 2)                 # the bore: the line ahead of the muzzle, a little of its width
    r = 0.12 * min(W, Hh)
    pts = np.array([c + fr.a * t + fr.l * dx + fr.z * dz for t in np.linspace(0.05, reach, 8) for dx, dz in ((0, 0), (-r, 0), (r, 0), (0, -r), (0, r))])
    for so in cx.S.body:
        if so.hull is None:
            continue
        eq = so.hull.equations
        if np.any(np.all(pts @ eq[:, :3].T + eq[:, 3] <= -1e-6, axis=1)):
            return True
    return False


def _emit(cx, zone, it, fr):
    """Draw an item in its frame. A weapon whose muzzle would fire into the body slides forward along its own axis (up to 0.7 of
    its length, so it stays seated in its mount) until the space ahead is clear. When it cannot clear and `cx.try_only` is set,
    nothing is drawn and False comes back, so the caller can try another rail (mount_rails)."""
    if it["kind"] in SH.RAILKINDS:
        L = cx.geoms[id(it)][0]
        moved = 0.0
        while moved < 0.7 * L and _muzzle_blocked(cx, it, fr):
            fr = Frame(fr.o + fr.a * 0.1, fr.a, fr.z)
            moved += 0.1
        if _muzzle_blocked(cx, it, fr):
            if getattr(cx, "try_only", False):
                return False
            cx.blocked = getattr(cx, "blocked", 0) + 1
    for cls, pts in cx.geoms[id(it)][3]:
        cx.S.add(fr.pp(pts), cls, zone, "item", "w")
    return True


def _face(cx, zone, rail, items):
    """Items standing out of a face: rows across `lat`, centred; rows stack along `up`, centred too. Returns the items that
    could not be placed with a clear muzzle (when cx.try_only)."""
    failed = []
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
            if not _emit(cx, zone, it, fr):
                failed.append(it)
            x += W / 2 + gap
        zc -= hr / 2 + gap
    return failed


def _line(cx, zone, rail, items):
    """Items lying along a surface, one behind the other along the rail, the run centred on the rail's middle. Returns the items
    that could not be placed with a clear muzzle (when cx.try_only)."""
    failed = []
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
        if not _emit(cx, zone, it, Frame(pt + a * (start - sc) - nrm * (0.3 * Hh), a, nrm)):
            failed.append(it)
        start += L + gap
    return failed


def _bay(cx, zone, rail, miss):
    """Missile racks set into the upper front of a side torso, aimed at the enemy and angled up for the ballistic arc, each behind a
    protective door hinged at the top of its opening and swung up (Daniel, 2026-11-04: missiles point at the enemy, sometimes
    angled up, as on the Archer; the Archer's tall 'boxes' are these doors, raised)."""
    so, Hm = rail.solid, cx.Hm
    lo, hi = so.pts.min(0), so.pts.max(0)
    aim = _u((0, 1.0, 0.36))                                 # about 20 degrees up
    widths = [cx.geoms[id(it)][1] for it in miss]
    x = (lo[0] + hi[0]) / 2 - (sum(widths) + 0.15 * (len(miss) - 1)) / 2
    for it, W in zip(miss, widths):
        L, _W, Hh, _g = cx.geoms[id(it)]
        x += W / 2
        zc = lo[2] + 0.74 * (hi[2] - lo[2])
        pt, n = so.hit(np.array([x, (lo[1] + hi[1]) / 2, zc]), (0, 1, 0))
        fr = Frame(pt - aim * (L - 0.06), aim, (0, 0, 1))
        _emit(cx, zone, it, Frame(fr.o - fr.z * (Hh / 2), aim, fr.z))
        hinge = pt + fr.z * (Hh / 2 + 0.05) - aim * 0.12
        up = _u((0, -0.28, 1.0))                             # the door stands up over the opening, leaning back a little
        dh = Hh + 0.3
        nrm = _u(np.cross(np.array([1.0, 0, 0]), up))
        if nrm[1] < 0:
            nrm = -nrm
        cx.S.add(SH.slab(hinge + up * (dh / 2 - 0.12), nrm, up, W + 0.2, dh, 0.14), "t3", zone, "item", "w")
        x += W / 2 + 0.15


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
    model["blocked_muzzles"] = getattr(cx, "blocked", 0)               # tests/test_token_shell.py: must be 0
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
