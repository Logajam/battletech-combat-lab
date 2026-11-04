"""
INTEGRATION__shell.py  (NEW 2026-11-04, Claude - Combat Lab art, output only)

The skeleton-and-shell builder (spec: INTEGRATION__COMBAT_LAB_SKELETON.md). It replaces the block builder
INTEGRATION__tokens._build for the units it covers (phase 1: the test range, SHELL_RANGE) and gives the same kind of output: convex
solids in a `B3`, tagged by class, so INTEGRATION__token_mesh, tools/token_3d.py, the viewer and tools/token_audit.py work unchanged.

How a 'Mech is made here (Daniel, design_principles in data/token_dictionary.json):
  1. SKELETON  - joints and bone lengths from the rules height (2 x (t/100)^(1/3) levels, 6 m a level), the archetype and the stance.
                 Never drawn: it places and sizes things.
  2. VOLUMES   - each of the eight locations holds a volume (INTEGRATION__shell_items.budgets: its items by tons / density, its
                 share of structure and armor, the engine, gyro and cockpit). Its envelope around its bones is sized to hold it.
  3. SHELL     - the envelope is a bevelled core; armor plates lie over it, thicker and more layered where the location carries
                 more armor. Joints are covered by overlapping plates, discs and collars: no gap shows the inside.
  4. MOUNTS    - every crit-holding item takes hardpoint cells on a rail of its location (the unit's name hash shuffles the
                 order); items with a face are drawn: length from their slots, cross-section from mass / density.
Everything is built in METRES (1 level = 6 m) and written to the part list divided by the height, as INTEGRATION__tokens expects.
Needs numpy and scipy (art tools; the simulator does not use them).
"""

import math

import numpy as np
from scipy.spatial import ConvexHull

import INTEGRATION__tokens as T
import INTEGRATION__shell_items as I

# phase 1 test range (spec section 6): the chassis built by this module. Phase 2 widens it to every biped.
SHELL_RANGE = ("atlas", "mad cat", "timber wolf", "locust", "hunchback", "archer", "jagermech", "urbanmech", "wendigo")
M_LEVEL = 6.0
MIN_PLATE = I.DENS["min_plate_m"]
OVERLAP = 0.80                       # sum of hull volumes x this = the union's volume (parts overlap); tuned on the test range
ARCH = {                             # fractions of the height; leg length, torso height
    "humanoid": dict(leg=0.46, torso=0.32, fwd=0.0),
    "bird": dict(leg=0.50, torso=0.29, fwd=0.035),
    "martian": dict(leg=0.54, torso=0.28, fwd=0.0),
}


def enabled(unit):
    names = {unit.get("chassis", "").lower(), unit.get("clanname", "").lower()}
    return bool(names & set(SHELL_RANGE)) and "Quad" not in unit.get("config", "") and "Tripod" not in unit.get("config", "")


# -------------------------------------------------------------------------------------------------------- geometry

def _u(v):
    v = np.asarray(v, float)
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


class Frame:
    """A local frame: origin, axis (local y), `up` hint (local z) and the lateral axis (local x = axis x up)."""

    def __init__(self, origin, axis, up=(0, 0, 1)):
        self.o = np.asarray(origin, float)
        self.a = _u(axis)
        lat = np.cross(self.a, np.asarray(up, float))
        if np.linalg.norm(lat) < 1e-6:
            lat = np.cross(self.a, (0, 1, 0)) if abs(self.a[1]) < 0.9 else np.cross(self.a, (1, 0, 0))
        self.l = _u(lat)
        self.z = np.cross(self.l, self.a)

    def pp(self, pts):
        pts = np.asarray(pts, float)
        return self.o + pts[:, 0:1] * self.l + pts[:, 1:2] * self.a + pts[:, 2:3] * self.z


def lbox(c, s, bev=0.0, tap=(1.0, 1.0)):
    """A bevelled box (local coords): centre c, sizes s; each corner is cut by `bev`; the +y end is scaled by tap (x, z)."""
    cx, cy, cz = c
    hx, hy, hz = s[0] / 2, s[1] / 2, s[2] / 2
    bev = min(bev, 0.3 * min(s))
    pts = []
    for sy in (-1, 1):
        kx, kz = tap if sy > 0 else (1.0, 1.0)
        for sx in (-1, 1):
            for sz in (-1, 1):
                x, y, z = cx + sx * hx * kx, cy + sy * hy, cz + sz * hz * kz
                if bev > 0:
                    pts += [(x - sx * bev, y, z), (x, y, z - sz * bev), (x, y - sy * bev, z)]
                else:
                    pts.append((x, y, z))
    return np.array(pts)


def cyl(p0, p1, r0, r1=None, n=10):
    """A faceted cylinder / frustum from p0 to p1 (any coordinates)."""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    r1 = r0 if r1 is None else r1
    ax = p1 - p0
    ln = np.linalg.norm(ax)
    if ln < 1e-9:
        ax = np.array([0.0, 1.0, 0.0])
    ax = ax / max(ln, 1e-9)
    ref = np.array([1.0, 0, 0]) if abs(ax[0]) < 0.9 else np.array([0, 1.0, 0])
    u = _u(np.cross(ax, ref))
    v = np.cross(ax, u)
    pts = []
    for i in range(n):
        t = 2 * math.pi * (i + 0.5) / n
        d = math.cos(t) * u + math.sin(t) * v
        pts += [p0 + d * r0, p1 + d * r1]
    return np.array(pts)


def ellipsoid(c, r, n=40):
    """Points of an ellipsoid (centre c, radii r): a dome or a rounded cap when hulled."""
    golden = math.pi * (3 - math.sqrt(5))
    pts = []
    for i in range(n):
        y = 1 - 2 * (i + 0.5) / n
        rr = math.sqrt(max(0.0, 1 - y * y))
        th = golden * i
        pts.append((c[0] + r[0] * rr * math.cos(th), c[1] + r[1] * y, c[2] + r[2] * rr * math.sin(th)))
    return np.array(pts)


def limb_axes(p0, p1):
    """(a, ex, ey): the limb's axis, its width direction (the figure's right) and its depth direction (forward)."""
    a = _u(np.asarray(p1, float) - np.asarray(p0, float))
    ex = _u(np.array([1.0, 0, 0]) - a[0] * a)
    if np.linalg.norm(ex) < 1e-6:
        ex = np.array([1.0, 0, 0])
    ey = np.cross(ex, a)
    if ey[1] < -1e-6 or (abs(ey[1]) < 1e-6 and ey[2] < 0):
        ey = -ey
    return a, ex, ey


def frustum(p0, p1, w0, d0, w1, d1, ch=0.22, end=0.0):
    """An oriented tapered block from p0 to p1: half-widths (w across the figure, d forward) at each end, every long edge cut by
    `ch` (fraction of the smaller half-size), both ends chamfered by `end` metres when given."""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    a, ex, ey = limb_axes(p0, p1)
    L = np.linalg.norm(p1 - p0)
    rings = [(0.0, 1.0)] if not end else [(0.0, 0.84), (end / L, 1.0), (1 - end / L, 1.0), (1.0, 0.84)]
    pts = []
    for t, k in rings:
        c = p0 + (p1 - p0) * t
        w = (w0 + (w1 - w0) * t) * k
        d = (d0 + (d1 - d0) * t) * k
        m = ch * min(w, d)
        for sx in (-1, 1):
            for sy in (-1, 1):
                pts.append(c + sx * (w - m) * ex + sy * d * ey)
                pts.append(c + sx * w * ex + sy * (d - m) * ey)
    if not end:
        c = p1
        w, d = w1, d1
        m = ch * min(w, d)
        for sx in (-1, 1):
            for sy in (-1, 1):
                pts.append(c + sx * (w - m) * ex + sy * d * ey)
                pts.append(c + sx * w * ex + sy * (d - m) * ey)
    return np.array(pts)


def slab(c, nrm, up, w, h, t, ch=0.38):
    """An armor plate: centre c, outward normal nrm, `up` the direction of its height, w wide, h high, t THICK, every edge cut."""
    nrm = _u(nrm)
    f = Frame(np.asarray(c, float) - nrm * t / 2, nrm, up)
    return f.pp(lbox((0, t / 2, 0), (w, t, h), bev=min(ch * t, 0.3 * min(w, h))))


def prof_solid(x0, x1, yc, d, z0, h, prof, wtop=1.0, fw=1.0, bulge=0.0, e=0.07, k=0.93):
    """A solid whose SIDE view is `prof` (T.PROFILES: u -1 rear .. 1 front, v 0 belly .. 1 top), extruded from x0 to x1: the
    torso section. wtop = width at the top against the belly, fw = width at the front against the rear (the plan), bulge = plan
    swell. Every edge is cut: the outer faces use the polygon shrunk by k about its centre, the inner ring is full size."""
    prof = np.asarray(prof, float)
    cu, cv = prof[:, 0].mean(), prof[:, 1].mean()
    xm, hw = (x0 + x1) / 2, (x1 - x0) / 2
    e = min(e, 0.2 * hw)
    pts = []
    for shrink, dx in ((k, hw), (1.0, hw - e), (1.0, -(hw - e)), (k, -hw)):
        for u, v in prof:
            u2, v2 = cu + (u - cu) * shrink, cv + (v - cv) * shrink
            half = abs(dx) * (1 - (1 - wtop) * v2)
            plan_k = (1 + (fw - 1) * (u2 + 1) / 2) * (1 - bulge * u2 * u2)
            pts.append(((xm + math.copysign(half, dx)) * plan_k, yc + u2 * d / 2, z0 + v2 * h))
    return np.array(pts)


def hull_vol(pts):
    try:
        return float(ConvexHull(np.asarray(pts)).volume)
    except Exception:
        return 0.0


class Solid:
    """A convex solid with its hull, for ray tests and mounting."""

    def __init__(self, pts):
        self.pts = np.asarray(pts, float)
        try:
            self.hull = ConvexHull(self.pts)
        except Exception:
            self.hull = None

    def hit(self, p, d):
        """(point, outward normal) where the ray from p (inside) along d leaves the solid."""
        if self.hull is None:
            return np.asarray(p, float), _u(d)
        eq = self.hull.equations
        d = _u(d)
        nd = eq[:, :3] @ d
        m = nd > 1e-9
        t = -(eq[m, :3] @ np.asarray(p, float) + eq[m, 3]) / nd[m]
        i = int(np.argmin(np.where(t > -1e-9, t, np.inf)))
        return np.asarray(p, float) + d * max(float(t[i]), 0.0), eq[m][i, :3] / np.linalg.norm(eq[m][i, :3])

    def extent(self, axis):
        pr = self.pts @ _u(axis)
        return float(pr.min()), float(pr.max())


LAYER_OF = {"core": "armor", "plate": "armor", "cover": "armor", "item": "equipment", "detail": "equipment", "internal": "equipment",
            "bone": "skeleton", "muscle": "myomer"}


class Sink:
    """Writes solids (metres) into a B3 as raw part groups (divided by the height), tagged by location and role."""

    def __init__(self, b, scale):
        self.b, self.s = b, 1.0 / scale
        self.zmax = 0.0

    def add(self, pts, cls, loc, role="core", tag="b"):
        pts = np.asarray(pts, float)
        if len(pts) < 4:
            return None
        self.zmax = max(self.zmax, float(pts[:, 2].max()))
        self.b.parts.append({"groups": [[(tuple(float(x) * self.s for x in p), 0.0) for p in pts]], "cls": cls, "vis": None, "tag": tag,
                             "vol": 0.0, "loc": loc, "role": role, "layer": LAYER_OF.get(role, "armor")})
        return Solid(pts)


def fit(make, target, vol_of, iters=7, lo=0.35, hi=3.0):
    """Scale s so vol_of(make(s)) x OVERLAP is about `target`: make(s) returns a list of (pts, ...) tuples."""
    s = 1.0
    for _ in range(iters):
        v = vol_of(make(s)) * OVERLAP
        if v <= 1e-9:
            break
        s = min(hi, max(lo, s * (target / v) ** 0.45))
    return s


# ------------------------------------------------------------------------------------------------------ plates and items

def plate_t(ratio, Hm):
    """Plate thickness in metres from the location's armor ratio (0 thin .. 1 full) and the 'Mech's size."""
    return max(MIN_PLATE, (0.07 + 0.15 * ratio) * math.sqrt(Hm / 12.0))


def n_layers(ratio):
    return 1 + (ratio > 0.5) + (ratio > 0.85)


class Ctx:
    """Everything one build needs."""

    def __init__(self, model, P, S, Hm):
        self.m, self.P, self.S, self.Hm = model, P, S, Hm
        self.solids = {}                 # name -> Solid: what rails and pegs mount on
        self.rails = {}                  # zone -> [Rail]
        self.parts = {}                  # zone -> [(pts, cls, role)] collected for the volume fit
        self.top = 0.0


class Rail:
    """A hardpoint rail: `cap` cells of SLOT_M along `axis`. mode 'along': items lie along a face (ray `dr` finds the face);
    mode 'out': items stand out of a face along the axis. fill 'back': cell 0 is at the front end, later cells behind it;
    'fwd': cell 0 at the rear end."""

    def __init__(self, solid, o, axis, dr, cap, mode="along", fill="back", over=0.2, up=None):
        self.solid, self.o, self.a, self.dr, self.cap, self.mode, self.fill, self.over, self.up = solid, np.asarray(o, float), _u(axis), _u(dr), cap, mode, fill, over, up


def item_dims(it, Hm):
    """(L, W, Hh): length from slots, cross-section from volume / length (spec section 3). A missile rack's face is its real
    tube grid (T.rack_grid, tube pitch in metres)."""
    L = max(0.3, it["slots"] * I.SLOT_M * (0.85 if it["kind"] == "missile" else 0.96))
    cap_d = 0.11 * Hm
    if it["kind"] == "missile":
        fam = T.gfam({"fam": {it["gr"].get("fam", ""): 1}})
        cols, rows, pitch_px, _depth = T.rack_grid(fam, max(2, it["gr"].get("tubes") or 4))
        pitch = pitch_px / T.PX_PER_M
        return L, cols * pitch + 0.1, rows * pitch + 0.1
    A = max(it["vol"], 0.01) / L
    W = min(cap_d, max(0.14, math.sqrt(A)))
    return L, W, min(cap_d, max(0.14, A / W))


def item_geometry(it, L, W, Hh):
    """[(class, points)] of one visible item in its own frame: x across, y from 0 (rear) to L (muzzle), z from 0 (the base that
    sits on the shell) up. Length follows slots, cross-section follows density; the families keep the old weapon looks."""
    k, gr = it["kind"], it["gr"]
    cz, r = Hh / 2, min(W, Hh) / 2
    out = []

    def bar(y0, y1, rad, x=0.0, z=None, cls="t4", n=10, r1=None):
        out.append((cls, cyl((x, y0, cz if z is None else z), (x, y1, cz if z is None else z), rad, r1, n)))

    def box(y0, y1, w, h, x=0.0, z=None, cls="t4", bev=0.03):
        out.append((cls, lbox((x, (y0 + y1) / 2, cz if z is None else z), (w, y1 - y0, h), bev=bev)))

    fam = gr.get("fam", "")
    if k == "laser":
        hl = 0.45 * L
        box(0, hl, W, Hh)
        box(hl * 0.1, hl * 0.8, W * 0.45, 0.06, z=Hh + 0.02, cls="t4")               # cooling fin on top
        bar(hl * 0.9, L, r * 0.42)
        if gr.get("pulse"):
            bar(hl * 0.9, L, r * 0.3, x=-r * 0.45)
        if gr.get("er"):
            bar(hl + (L - hl) * 0.5, hl + (L - hl) * 0.62, r * 0.62)
        bar(L - 0.05, L, r * 0.44, cls="we")                                           # the lens
    elif k == "ppc":
        bar(0, L, r * 0.55)
        for t in (0.25, 0.45, 0.65):
            bar(L * t, L * t + 0.09, r * 0.95, cls="we")
        for ang in (90, 210, 330):
            bar(L * 0.88, L, r * 0.16, x=r * 0.7 * math.cos(math.radians(ang)), z=cz + r * 0.7 * math.sin(math.radians(ang)), n=6)
    elif k in ("ac", "lbx", "uac", "rotary"):
        rl = 0.38 * L
        box(0, rl, W, Hh)
        box(rl * 0.2, rl * 0.8, W * 0.3, Hh * 0.5, x=W * 0.5, bev=0.02)                # ammo feed
        if k == "uac":
            for d in (-1, 1):
                bar(rl * 0.7, L, r * 0.36, x=d * r * 0.5)
            box(L * 0.7, L, W * 0.9, Hh * 0.62)
        elif k == "rotary":
            bar(rl * 0.5, rl * 1.1, r * 0.95)
            for ang in (90, 210, 330):
                bar(rl, L, r * 0.22, x=r * 0.5 * math.cos(math.radians(ang)), z=cz + r * 0.5 * math.sin(math.radians(ang)), n=6)
        else:
            bar(rl * 0.6, L, r * (0.5 if k == "ac" else 0.62))
            bar(L * 0.88, L, r * 0.78)                                                  # muzzle brake
            bar(L * 0.55, L * 0.55 + 0.08, r * 0.7, cls="wb")
    elif k == "gauss":
        out.append(("t4", cyl((0, 0, cz), (0, L, cz), r * 0.8, None, 3)))
        for t in (0.3, 0.55, 0.8):
            out.append(("wb", cyl((0, L * t, cz), (0, L * t + 0.09, cz), r * 1.0, None, 3)))
    elif k == "plasma":
        bar(0, L, r * 0.4)
        bar(L * 0.35, L * 0.7, r * 0.9)
        bar(L * 0.5, L * 0.58, r * 0.95, cls="we")
    elif k == "flamer":
        box(0, L * 0.4, W, Hh, cls="t4")
        bar(L * 0.35, L, r * 0.28)
    elif k == "mg":
        box(0, L * 0.5, W, Hh)
        for d in (-1, 1):
            bar(L * 0.4, L, r * 0.16, x=d * r * 0.4, n=6)
    elif k == "missile":
        n = max(2, min(gr.get("tubes") or 4, 40))
        fm = T.gfam({"fam": {fam: 1}})
        cols, rows, pitch_px, _d = T.rack_grid(fm, n)
        pitch = pitch_px / T.PX_PER_M
        tr = T.tube_px(fm)[0] / T.PX_PER_M
        box(0, L, W, Hh, bev=0.04)
        box(L * 0.82, L * 0.82 + 0.03, W * 1.02, 0.04, z=Hh + 0.0, cls="ln", bev=0.0) if False else None
        for i in range(min(n, cols * rows)):
            rr, cc = divmod(i, cols)
            inrow = min(cols, n - rr * cols)
            x = (cc - (inrow - 1) / 2) * pitch
            z = Hh / 2 + ((rows - 1) / 2 - rr) * pitch
            bar(L - 0.01, L + 0.05, tr, x=x, z=z, cls="wm", n=8)
            bar(L + 0.04, L + 0.06, tr * 0.62, x=x, z=z, cls="ln", n=8)
    elif k == "jumpjet":
        out.append(("t4", cyl((0, 0, cz), (0, L, cz), r * 0.6, r * 1.0, 10)))
        out.append(("ln", cyl((0, L - 0.02, cz), (0, L + 0.03, cz), r * 0.74, None, 10)))
    elif k in ("ecm", "probe", "c3", "ams"):
        if k == "ams":
            box(0, L * 0.6, W, Hh)
            bar(L * 0.4, L, r * 0.3)
        else:
            out.append(("t4", cyl((0, 0, 0), (0, 0, 0.1), r * 0.9, None, 10) if False else cyl((0, L * 0.5, 0), (0, L * 0.5, 0.12), r * 0.95, None, 12)))
            out.append(("hl" if k == "ecm" else "t4", ellipsoid((0, L * 0.5, 0.1), (r * 0.9, r * 0.9, r * 1.0), 30)))
    elif k in ("heatsink_single", "heatsink_double"):
        out.append(("t4", lbox((0, L / 2, 0.06), (W, L, 0.12), bev=0.02)))
        n_sl = 3 if it["slots"] >= 2 else 2
        for i in range(n_sl):
            y = L * (i + 1) / (n_sl + 1)
            out.append(("ln", lbox((0, y, 0.13), (W * 0.85, 0.06, 0.04), bev=0.0)))
    else:
        box(0, L, W, Hh)
    return out


def item_volume(parts):
    return sum(hull_vol(p) for _c, p in parts)


# ------------------------------------------------------------------------------------------------------------ the shell

LAYER_CLS = ("t2", "t3", "t1")


def seg_plates(p0, p1, w0, d0, w1, d1, ratio, Hm, sg, faces=("front", "outer", "rear"), spec=None):
    """Armor plates over a limb segment (the frustum p0..p1): [(pts, cls, role)]. Plates are real thickness (plate_t) and lie
    on the front, the outer side and the back; where the location carries more armor a second and third layer steps up on them.
    No plate overhangs the inner face (legs and arms must not touch their neighbours)."""
    a, ex, ey = limb_axes(p0, p1)
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    L = np.linalg.norm(p1 - p0)
    t = plate_t(ratio, Hm)
    out = []
    spec = spec or {"front": (0.5, 0.92, 0.62), "outer": (0.5, 0.86, 0.55), "rear": (0.45, 0.8, 0.4)}
    for face in faces:
        u, wf, hf = spec[face]
        c = p0 + (p1 - p0) * u
        w, d = w0 + (w1 - w0) * u, d0 + (d1 - d0) * u
        if face == "outer":
            n, half, across = sg * ex, w, d
        else:
            n, half, across = (ey if face == "front" else -ey), d, w
        for li in range(n_layers(ratio)):
            k = 0.74 ** li
            wd = 2 * across * wf * k
            hh = L * hf * k
            shift = (0.0 if face == "outer" else sg * across * (1 - wf * k))             # inner edge stays on the inner face
            cen = c + n * (half - 0.4 * t + li * 0.75 * t + t / 2) + (ex * shift if face != "outer" else 0)
            out.append((slab(cen, n, a, wd, hh, t), LAYER_CLS[li], "plate"))
    return out


def leg_make(cx, sg, s):
    """One leg at x = 0 (the caller shifts it): [(pts, cls, role, name)] and the joint dict."""
    Hm, m = cx.Hm, cx.m
    arch = m["archetype"]
    bird = arch == "bird" or m.get("legs") == "digitigrade"
    ratio = cx.P["ratio"]["Left Leg" if sg < 0 else "Right Leg"]
    slab_legs = m.get("legs") in ("slab", "pillar", "heavy")
    asp = 1.6 if m.get("legs") == "slab" else 1.0 if m.get("legs") == "pillar" else 1.25
    legs_k = m.get("legscale", 1.0) * (1.25 if m.get("legs") == "heavy" else 1.0)
    A = ARCH[arch]
    zh, fwd = A["leg"] * Hm * (0.93 if m.get("crouch") else 1.0), A["fwd"] * Hm
    if bird:
        J = {"hip": (0, fwd + 0.01 * Hm, zh), "knee": (0, 0.125 * Hm, zh * 0.74), "hock": (0, -0.035 * Hm, zh * 0.39), "ankle": (0, 0.045 * Hm, 0.06 * Hm)}
    else:
        J = {"hip": (0, 0.0, zh), "knee": (0, 0.035 * Hm * (2.2 if m.get("crouch") else 1.0), zh * 0.54), "ankle": (0, -0.005 * Hm, 0.06 * Hm)}
    J = {k: np.array(v, float) for k, v in J.items()}
    wt = 0.034 * Hm * s * legs_k
    dt = wt / asp
    out = []
    chain = ["hip", "knee", "hock", "ankle"] if bird else ["hip", "knee", "ankle"]
    sizes = {"hip": (1.0, 1.0), "knee": (0.88, 0.9), "hock": (0.62, 0.7), "ankle": (0.6, 0.65)} if bird else {"hip": (1.0, 1.0), "knee": (0.88, 0.9), "ankle": (0.62, 0.66)}
    segs = []
    for i in range(len(chain) - 1):
        a_, b_ = chain[i], chain[i + 1]
        p0, p1 = J[a_].copy(), J[b_].copy()
        if i == 0:
            p0 = p0 + np.array([0, 0, 0.025 * Hm])                                       # the thigh starts inside the pelvis
        sb = sizes[b_]
        w1, d1 = wt * sb[0], dt * sb[1]
        w0, d0 = (wt, dt) if i == 0 else (segs[-1][4], segs[-1][5])          # each segment starts as wide as the one above ends
        segs.append((p0, p1, w0, d0, w1, d1))
        out.append((frustum(p0, p1, w0, d0, w1, d1, ch=0.25, end=0.04 * Hm * 0.5), "t1", "core", f"leg{i}"))
    # the foot: a block from heel to toe, the toe narrower; the shin ends inside it
    wf = segs[-1][4] * 1.35
    Lf = 0.17 * Hm * (1.3 if bird else 1.0)
    hf = 0.065 * Hm
    heel = J["ankle"][1] - 0.06 * Hm
    fr = Frame((0, heel, 0), (0, 1, 0))
    out.append((fr.pp(lbox((0, Lf / 2, hf / 2), (2 * wf, Lf, hf), bev=0.1 * hf * 2, tap=(0.7, 0.45))), "t1", "core", "foot"))
    out.append((slab((0, heel + Lf * 0.4, hf + 0.01), (0, 0, 1), (0, 1, 0), 2 * wf * 0.8, Lf * 0.62, max(MIN_PLATE, 0.5 * plate_t(ratio, Hm))), "t2", "plate", "foot_top"))
    # armor plates on every segment
    for i, sg_ in enumerate(segs):
        spec = None
        if slab_legs:
            spec = {"front": (0.5, 1.0, 0.82), "outer": (0.5, 0.95, 0.8), "rear": (0.5, 0.9, 0.55)}
        for pts, cls, role in seg_plates(sg_[0], sg_[1], sg_[2], sg_[3], sg_[4], sg_[5], ratio, Hm, sg, spec=spec, faces=("front", "outer", "rear") if i < len(segs) - 0 else ("front", "outer")):
            out.append((pts, cls, role, f"leg{i}_plate"))
    # joint covers: a knee disc (and a hock disc), a hip collar, an ankle collar: overlapping plates, no gap shows the inside
    for jn in chain[1:-1]:
        i = chain.index(jn)
        w_, d_ = segs[i][4], segs[i][5]
        rk = max(d_, w_ * 0.75) * 1.0
        out.append((cyl(J[jn] - np.array([w_ * 1.04, 0, 0]), J[jn] + np.array([w_ * 1.04, 0, 0]), rk, None, 12), "t4", "cover", f"{jn}_disc"))
    out.append((frustum(J["hip"] + np.array([0, 0, 0.03 * Hm]), J["hip"] - np.array([0, 0, 0.045 * Hm]), wt * 1.08, dt * 1.1, wt * 1.04, dt * 1.06, ch=0.3), "t4", "cover", "hip_collar"))
    aw, ad = segs[-1][4], segs[-1][5]
    out.append((frustum(J["ankle"] + np.array([0, 0, 0.05 * Hm]), J["ankle"] - np.array([0, 0, 0.012 * Hm]), aw * 1.18, ad * 1.2, aw * 1.3, ad * 1.3, ch=0.3), "t4", "cover", "ankle_collar"))
    return out, J, segs


def shift(items, v):
    v = np.asarray(v, float)
    return [(pts + v,) + tuple(rest) for pts, *rest in items]


def vol_of(items):
    return sum(hull_vol(i[0]) for i in items)


# ------------------------------------------------------------------------------------------------------------- torso

PLAN = {"block": (1.0, 0.0), "wedge": (0.8, 0.0), "flare": (1.18, 0.0), "arrow": (0.62, 0.0), "oval": (1.0, 0.22)}      # name -> (front width, bulge)
HEAD_PROF = {"box": T.PROFILES["upright"], "dome": T.PROFILES["dome"],
             "wedge": [(-1, 0), (1, 0), (1, .5), (-.2, 1), (-1, 1)], "visor": [(-1, 0), (1, 0), (1, .45), (.55, 1), (-1, 1)],
             "skull": [(-1, 0), (.7, 0), (1, .2), (1, .72), (.5, 1), (-1, 1)]}


def torso_spec(cx):
    m = cx.m
    prof = T.PROFILES.get(m.get("profile", "upright"), T.PROFILES["upright"])
    fw, bulge = PLAN.get(m.get("plan", "block"), (1.0, 0.0))
    wtop, wmul, hmul, asp = 0.9, 1.0, 1.0, 0.9
    tor = m.get("torso", "box")
    if tor == "ovoid":
        bulge, asp = bulge + 0.2, 0.95
    elif tor == "canopy":
        bulge, asp, wtop = bulge + 0.24, 1.0, 0.8
    elif tor == "narrow":
        wmul, asp = 0.82, 1.0
    elif tor == "slab":
        wmul, hmul, asp = 0.9, 1.1, 0.78
    elif tor == "dome":
        bulge, wtop, hmul, asp = bulge + 0.22, 0.82, 1.05, 0.95
    if m.get("profile") in ("tall_slab",):
        wmul, hmul = 0.88 * wmul, 1.12 * hmul
    if m.get("profile") in ("hunch", "stepped"):
        wtop = 0.9
    A = ARCH[m["archetype"]]
    return dict(prof=prof, fw=fw, bulge=bulge, wtop=wtop, wmul=wmul * m.get("girth", 1.0), asp=asp * m.get("bodyd", 1.0),
                h=A["torso"] * hmul * m.get("bodyh", 1.0), yc=A["fwd"] * cx.Hm)


def sec_plates(cx, sol, xm, yc, z0, h, w, D, ratio, sg, kind):
    """Armor plates over one torso section (its convex solid `sol`): front upper and lower, rear, and on a side torso the top
    deck and the outer side; second and third layers where the section carries more armor."""
    Hm = cx.Hm
    t = plate_t(ratio, Hm)
    out = []
    z = np.array([0.0, 0, 1])

    def face(p_in, d, wd, hh, up, name, layers=None):
        pt, n = sol.hit(p_in, d)
        for li in range(layers or n_layers(ratio)):
            k = 0.76 ** li
            cen = pt + n * (t / 2 - 0.4 * t + li * 0.75 * t)
            out.append((slab(cen, n, up, wd * k, hh * k, t), LAYER_CLS[li], "plate", name))

    face((xm, yc, z0 + 0.7 * h), (0, 1, 0), 0.86 * w, 0.46 * h, z, "front_hi")
    face((xm, yc, z0 + 0.27 * h), (0, 1, 0), 0.8 * w, 0.3 * h, z, "front_lo", layers=1)
    face((xm, yc, z0 + 0.58 * h), (0, -1, 0), 0.82 * w, 0.62 * h, z, "rear")
    if kind == "side":
        face((xm, yc, z0 + 0.5 * h), (0, 0, 1), 0.9 * w, 0.62 * D, np.array([0, 1.0, 0]), "deck")
        face((xm, yc, z0 + 0.55 * h), (sg, 0, 0), 0.74 * D, 0.66 * h, z, "side")
    else:
        face((xm, yc, z0 + 0.5 * h), (0, 0, 1), 0.7 * w, 0.4 * D, np.array([0, 1.0, 0]), "collar_plate", layers=1)
    return out


def torso_make(cx, s, spec, z0, pelvis_half, env):
    """The three torso sections, their plates, the pelvis and its skirt plates: [(pts, cls, role, name, loc)] and the solids."""
    Hm = cx.Hm
    h = spec["h"] * Hm
    W, D = 0.40 * Hm * spec["wmul"] * s, 0.40 * Hm * spec["wmul"] * spec["asp"] * s
    v = {z: max(env[z], 0.05) for z in ("Left Torso", "Center Torso", "Right Torso")}
    tot = sum(v.values())
    fr = {z: max(0.06, v[z] / tot) for z in v}
    ft = sum(fr.values())
    wl, wc, wr = (W * fr["Left Torso"] / ft, W * fr["Center Torso"] / ft, W * fr["Right Torso"] / ft)
    yc = spec["yc"]
    e = 0.02 * Hm
    kw = dict(prof=spec["prof"], wtop=spec["wtop"], fw=spec["fw"], bulge=spec["bulge"], e=0.025 * Hm)
    sec = {"Center Torso": (-wc / 2, wc / 2, D, "Center Torso", 0, 0),
           "Right Torso": (wc / 2 - e, wc / 2 + wr, D * 0.96, "Right Torso", 1, 1),
           "Left Torso": (-(wc / 2 + wl), -wc / 2 + e, D * 0.96, "Left Torso", -1, 1)}
    out, sols = [], {}
    for zone, (x0, x1, d, loc, sg, side) in sec.items():
        pts = prof_solid(x0, x1, yc, d, z0, h, **kw)
        sol = Solid(pts)
        sols[zone] = (sol, (x0 + x1) / 2, x1 - x0, d)
        out.append((pts, "t1", "core", "section", zone))
        for pp, cls, role, name in sec_plates(cx, sol, (x0 + x1) / 2, yc, z0, h, x1 - x0, d, cx.P["ratio"][zone], sg, "side" if side else "center"):
            out.append((pp, cls, role, name, zone))
    # pelvis: a belt block between the torso and the legs, with skirt plates that cover the hip joints (overlapping the thighs)
    pw = max(pelvis_half, wc / 2 * 1.05)
    zp = z0 - 0.045 * Hm
    out.append((frustum((0, yc, zp), (0, yc, z0 + 0.02 * Hm), pw, D * 0.5, pw * 0.96, D * 0.5, ch=0.25, end=0.02 * Hm), "t1", "core", "pelvis", "Center Torso"))
    tp = plate_t(cx.P["ratio"]["Center Torso"], Hm)
    for nm, n, off, wd in (("skirt_front", (0, 1, 0), D * 0.5, 2 * pw * 0.9), ("skirt_rear", (0, -1, 0), D * 0.5, 2 * pw * 0.9)):
        n = np.array(n, float)
        out.append((slab(np.array([0, yc, zp - 0.012 * Hm]) + n * (off - 0.4 * tp + tp / 2), n, (0, 0, 1), wd, 0.06 * Hm, tp), "t3", "plate", nm, "Center Torso"))
    for sx in (-1, 1):
        n = np.array([sx, 0, 0.0])
        out.append((slab(np.array([0, yc, zp - 0.012 * Hm]) + n * (pw - 0.4 * tp + tp / 2), n, (0, 0, 1), D * 0.7, 0.06 * Hm, tp), "t3", "plate", "skirt_side", "Center Torso"))
    return out, sols, dict(W=W, D=D, wc=wc, wl=wl, wr=wr, h=h, z0=z0, yc=yc)


# ---------------------------------------------------------------------------------------------------------- head, arms

def head_make(cx, s, spec, ct_sol, yc, ctw, ctd, env, ztop_fn):
    """The head: its solid (shape from head_shape, position from head_mount), a brow plate, a blue visor, a neck collar."""
    Hm, m = cx.Hm, cx.m
    mount, shape = m.get("head_mount", "top"), m.get("head_shape", "box")
    ratio = cx.P["ratio"]["Head"]
    k_ck = (m.get("cockpit_tons", 3.0) / 3.0) ** (1 / 3)
    hw = 0.05 * Hm * s * k_ck
    hd, hh = hw * 1.9, hw * 1.7
    if mount == "built_in":
        hw, hd, hh = hw * 0.9, hd * 0.85, hh * 0.7
    # where it sits
    y_front = yc + ctd / 2
    if mount == "notch":
        yh, drop = yc + ctd * 0.18, 0.45
    elif mount == "front":
        yh, drop = yc + ctd * 0.2, 0.35
    elif mount == "built_in":
        yh, drop = yc + ctd * 0.05, 0.42
    else:
        yh, drop = yc - ctd * 0.04, 0.05
    zt = ztop_fn(yh)
    z0 = zt - hh * drop
    prof = HEAD_PROF.get(shape, HEAD_PROF["box"])
    out = []
    core = prof_solid(-hw, hw, yh, hd, z0, hh, prof, wtop=0.9, e=0.02 * Hm, k=0.9)
    out.append((core, "t1", "core", "head", "Head"))
    t = plate_t(ratio, Hm)
    sol = Solid(core)
    for li in range(1):
        k = 0.8 ** li
        pt, n = sol.hit((0, yh, z0 + hh * 0.85), (0, 0, 1))
        out.append((slab(pt + n * (t / 2 - 0.4 * t + li * 0.75 * t), n, (0, 1, 0), 2 * hw * 0.85 * k, hd * 0.8 * k, t), LAYER_CLS[li], "plate", "head_top", "Head"))
    pt, n = sol.hit((0, yh, z0 + hh * 0.4), (0, 1, 0))
    out.append((slab(pt + n * (t * 0.1), n, (0, 0, 1), 2 * hw * 0.7, hh * 0.3, max(MIN_PLATE, t * 0.6)), "ck", "cover", "visor", "Head"))   # the cockpit glass
    if shape == "skull":
        pt, n = sol.hit((0, yh, z0 + hh * 0.15), (0, 1, 0))
        out.append((slab(pt + n * t * 0.1, n, (0, 0, 1), 2 * hw * 0.55, hh * 0.2, max(MIN_PLATE, t * 0.6)), "t4", "cover", "jaw", "Head"))
    # the neck collar covers the joint between head and torso
    out.append((frustum((0, yh, z0 - hh * 0.12), (0, yh, z0 + hh * 0.18), hw * 1.05, hd * 0.5, hw * 0.95, hd * 0.46, ch=0.3), "t4", "cover", "neck", "Head"))
    return out, dict(hw=hw, hd=hd, hh=hh, z0=z0, yh=yh), sol


def arm_make(cx, sg, s, x_a, z_s, yc, zone, x_torso=None):
    """One arm: shoulder dome (pauldron), upper arm, elbow disc, forearm, a fist (or a gun housing, or a trunk of rings), all covered."""
    Hm, m = cx.Hm, cx.m
    kind = (m.get("arms") or {}).get("L" if sg < 0 else "R", "hand")
    style = m.get("arm_style", "")
    ratio = cx.P["ratio"][zone]
    sc = m.get("armscale", 1.0) * (0.6 if style == "tiny" else 1.0) * s
    wa = 0.027 * Hm * sc * (1.25 if style == "long_barrel" else 1.0)
    da = wa * (1.0 if style != "a_frame" else 0.9)
    Lu = 0.165 * Hm * m.get("armscale", 1.0) * (0.6 if style == "tiny" else 1.0)
    Lf = 0.165 * Hm * m.get("armscale", 1.0) * (1.2 if style == "long_barrel" else 1.0) * (0.8 if kind == "pod" else 1.0)
    out = []
    spread = 0.04 * Hm if style == "a_frame" else 0.0
    S_ = np.array([sg * x_a, yc, z_s])
    E_ = S_ + np.array([sg * spread, 0.02 * Hm, -Lu])
    pitch = math.radians(36 if style != "a_frame" else 20)
    W_ = E_ + Lf * np.array([sg * spread * 0.6, math.sin(pitch), -math.cos(pitch)])
    rd = m.get("kit") == "round_blocks"
    ch = 0.5 if rd else 0.24
    sol = {}
    if style == "trunk":
        n_r = 6
        prev = S_
        for i in range(n_r):
            u = (i + 1) / n_r
            nxt = S_ + np.array([sg * 0.01 * Hm * math.sin(u * 3.0), 0.09 * Hm * u * u + 0.02 * Hm * u, -(Lu + Lf) * 0.95 * u])
            w0 = wa * (1.1 - 0.45 * i / n_r)
            w1 = wa * (1.1 - 0.45 * (i + 1) / n_r)
            pts = frustum(prev - (nxt - prev) * 0.25 * (1 if i else 0), nxt + (nxt - prev) * 0.2, w0 * (1.12 if i % 2 else 1.0), w0 * (1.12 if i % 2 else 1.0), w1 * (1.12 if i % 2 else 1.0), w1 * (1.12 if i % 2 else 1.0), ch=0.4)
            out.append((pts, "t4" if i % 2 else "t1", "core", f"trunk{i}"))
            prev = nxt
        E_, W_ = S_ + np.array([sg * 0.01 * Hm, 0.03 * Hm, -Lu * 1.0]), nxt
    else:
        out.append((frustum(S_ + np.array([0, 0, 0.02 * Hm]), E_, wa, da, wa * 0.86, da * 0.86, ch=ch, end=0.03 * Hm * 0.5), "t1", "core", "upper"))
        wf = wa * (1.1 if kind != "hand" else 0.86)
        out.append((frustum(E_ + (E_ - W_) * 0.04, W_, wa * 0.86, da * 0.86, wf * 0.9, wf * 0.9 if kind != "hand" else da * 0.8, ch=ch, end=0.03 * Hm * 0.5), "t1", "core", "fore"))
        for pts, cls, role in seg_plates(S_, E_, wa, da, wa * 0.86, da * 0.86, ratio, Hm, sg, faces=("front", "outer")):
            out.append((pts, cls, role, "upper_plate"))
        for pts, cls, role in seg_plates(E_, W_, wa * 0.86, da * 0.86, wf * 0.9, wf * 0.9, ratio, Hm, sg, faces=("front", "outer", "rear")):
            out.append((pts, cls, role, "fore_plate"))
        # elbow disc and wrist cuff: the joint is covered, not open
        out.append((cyl(E_ - np.array([wa * 1.02, 0, 0]), E_ + np.array([wa * 1.02, 0, 0]), max(da, wa * 0.8) * 0.98, None, 12), "t4", "cover", "elbow"))
        a_, ex_, ey_ = limb_axes(E_, W_)
        out.append((frustum(W_ - a_ * 0.05 * Hm, W_ + a_ * 0.01 * Hm, wf * 1.0, wf * 1.0, wf * 1.08, wf * 1.08, ch=0.3), "t4", "cover", "wrist"))
        if kind == "hand":
            if style == "ball":
                r_ = wa * 1.5
                out.append((ellipsoid(W_ + a_ * r_ * 0.7, (r_, r_, r_), 44), "t2", "core", "fist"))
            else:
                out.append((frustum(W_ - a_ * 0.01 * Hm, W_ + a_ * 0.12 * Hm, wa * 0.95, da * 0.95, wa * 0.8, da * 0.7, ch=0.3, end=0.015 * Hm), "t2", "core", "fist"))
                tk = plate_t(ratio, Hm)
                out.append((slab(W_ + a_ * 0.09 * Hm + ey_ * (da * 0.7 + tk * 0.1), ey_, a_, wa * 1.4, 0.07 * Hm, tk * 0.8), "t3", "plate", "knuckles"))
        else:
            out.append((frustum(W_ - a_ * 0.01 * Hm, W_ + a_ * 0.045 * Hm, wf * 0.95, wf * 0.95, wf * 0.8, wf * 0.8, ch=0.3), "t2", "core", "muzzle_collar"))
    # shoulder: a dome of plate over the joint, bigger on `boom` shoulders and the pauldron kit
    kp = (1.0 + (0.22 if m.get("shoulders") == "boom" else 0.0) + (0.3 if m.get("kit") == "pauldrons" else 0.0))
    out.append((ellipsoid(S_ + np.array([0, 0, 0.008 * Hm]), (wa * 1.3 * kp, da * 1.3 * kp, wa * 1.0 * kp), 46), "t3", "cover", "pauldron"))
    if x_torso is not None:                      # the shoulder socket: a collar from the torso's side into the arm, so the joint is closed
        out.append((cyl(np.array([sg * (x_torso - 0.03 * Hm), yc, z_s]), np.array([sg * x_a, yc, z_s]), wa * 0.8, wa * 0.9, 10), "t4", "cover", "socket"))
    return out, dict(S=S_, E=E_, W=W_, wa=wa, da=da, kind=kind)


# -------------------------------------------------------------------------------------------------------------- mounts

def _clamp(v, lo, hi):
    return max(lo, min(hi, v)) if hi > lo else (lo + hi) / 2


def mount_on_rail(cx, zone, it, rail, cell):
    """Draw one visible weapon on its rail: the item takes cells [cell, cell + slots) along the rail, its base seated into the
    face the rail's ray finds (so it touches and is held), its length along the rail."""
    L, W, Hh, geom = cx.geoms[id(it)]
    a, sol = rail.a, rail.solid
    lo, hi = sol.extent(a)
    n = it["slots"]
    if rail.mode == "along":
        if rail.fill == "back":
            s1 = hi + rail.over - cell * I.SLOT_M
            start = s1 - L
        else:
            start = lo + rail.over + cell * I.SLOT_M
        sc = _clamp(start + L / 2, lo + 0.08, hi - 0.08)
        p_in = rail.o + a * (sc - float(rail.o @ a))
        pt, nrm = sol.hit(p_in, rail.dr)
        fr = Frame(pt + a * (start - sc) - nrm * (0.3 * Hh), a, nrm)
    else:
        lat = rail.up if rail.up is not None else np.array([1.0, 0, 0])
        p_in = rail.o + lat * ((cell + n / 2 - rail.cap / 2) * 0.32)
        pt, nrm = sol.hit(p_in, a)
        fr = Frame(pt - a * (0.3 * L) - lat * 0.0 - np.array([0, 0, 0.5 * Hh]), a, (0, 0, 1))
    for cls, pts in geom:
        cx.S.add(fr.pp(pts), cls, zone, "item", "w")


def peg_anchor(cx, zone, kind, idx, count):
    """(solid, inside point, ray, item axis, base normal hint) for an item that sits on a fixed spot rather than a rail: heat-sink
    vents (rear and sides), jump-jet nozzles (rear, pointing down), sensor domes (on top). The unit's name hash shuffles the spots."""
    P, Hm = cx.P, cx.Hm
    r = (idx + 0.5) / max(1, count) - 0.5
    name = {"Left Torso": "LT", "Right Torso": "RT", "Center Torso": "CT"}.get(zone)
    sg = -1 if zone.startswith("Left") else 1
    up_axis, down_axis = np.array([0.0, 0, 1]), np.array([0.0, 0, -1])
    if name:
        sol, xm, w, d = cx.sec[zone]
        z0, h, yc = cx.tor["z0"], cx.tor["h"], cx.tor["yc"]
        flip = (P["hash"] >> (idx + 3 * len(zone))) & 1
        if kind == "jumpjet":
            return sol, np.array([xm + r * w * 0.8, yc, z0 + 0.14 * h]), (0, -1, 0), down_axis
        if kind in ("ecm", "probe", "c3", "ams"):
            return sol, np.array([xm + r * w * 0.5, yc - 0.1 * d, z0 + 0.5 * h]), (0, 0, 1), np.array([0.0, 1, 0])
        if flip and name != "CT":
            return sol, np.array([xm, yc + r * d * 0.5, z0 + (0.3 + 0.28 * (idx % 2)) * h]), (sg, 0, 0), up_axis
        return sol, np.array([xm + r * w * 0.7, yc, z0 + (0.3 + 0.28 * (idx % 2)) * h]), (0, -1, 0), up_axis
    if zone == "Head":
        sol = cx.solids["head"]
        c = sol.pts.mean(0)
        if kind in ("ecm", "probe", "c3", "ams"):
            return sol, c, (0, 0, 1), np.array([0.0, 1, 0])
        return sol, c, (0, -1, 0), up_axis
    if zone.endswith("Arm"):
        sol = cx.solids[f"arm_{zone[0]}_up"]
        lo, hi = sol.extent(cx.arm_axis[zone[0]])
        u = 0.35 + 0.22 * idx
        c = sol.pts.mean(0) + cx.arm_axis[zone[0]] * ((u - 0.5) * (hi - lo))
        return sol, c, (sg, 0, 0), up_axis
    if zone.endswith("Leg"):
        key = "leg_%s_%s" % (zone[0], "shin" if kind == "jumpjet" else "thigh")
        sol = cx.solids[key]
        c = sol.pts.mean(0) + np.array([0, 0, 0.12 * Hm * (idx - (count - 1) / 2)])
        if kind == "jumpjet":
            return sol, c, (0, -1, 0), down_axis
        return sol, c, (sg, 0, 0), up_axis
    sol = next(iter(cx.solids.values()))
    return sol, sol.pts.mean(0), (0, 0, 1), up_axis


def mount_peg(cx, zone, it, idx, count):
    L, W, Hh, geom = cx.geoms[id(it)]
    sol, p_in, dr, axis = peg_anchor(cx, zone, it["kind"], idx, count)
    pt, nrm = sol.hit(p_in, dr)
    fr = Frame(pt - nrm * (0.3 * Hh if it["kind"] != "jumpjet" else 0.2), axis, nrm)
    tag = "j" if it["kind"] == "jumpjet" else "b" if it["kind"].startswith("heatsink") else "w"
    for cls, pts in geom:
        cx.S.add(fr.pp(pts), cls, zone, "item", tag)


RAILKINDS = ("laser", "ppc", "ac", "lbx", "uac", "rotary", "gauss", "mg", "flamer", "plasma", "missile")


def build_rails(cx):
    """Lay out each location's rails on its solids (INTEGRATION__shell_items.rail_count says how many)."""
    P, Hm = cx.P, cx.Hm
    cap = P["items"]["_cap"]
    tor = cx.tor
    z0, h, yc = tor["z0"], tor["h"], tor["yc"]
    fwd, up = np.array([0.0, 1, 0]), np.array([0.0, 0, 1])
    for zone in ("Left Torso", "Right Torso"):
        sol, xm, w, d = cx.sec[zone]
        sg = -1 if zone.startswith("Left") else 1
        c = max(1, cap.get(zone, 12))
        cx.rails[zone] = [Rail(sol, (xm, yc, z0 + 0.66 * h), fwd, (sg, 0, 0), c, over=0.3), Rail(sol, (xm, yc, z0 + 0.34 * h), fwd, (sg, 0, 0), c, over=0.2),
                          Rail(sol, (xm - sg * w * 0.22, yc, z0 + 0.5 * h), fwd, up, c, over=0.25), Rail(sol, (xm + sg * w * 0.22, yc, z0 + 0.5 * h), fwd, up, c, over=0.35)]
    sol, xm, w, d = cx.sec["Center Torso"]
    c = max(1, cap.get("Center Torso", 2))
    cx.rails["Center Torso"] = [Rail(sol, (-w * 0.16, yc, z0 + 0.68 * h), fwd, fwd, c, "out"), Rail(sol, (w * 0.16, yc, z0 + 0.4 * h), fwd, fwd, c, "out"),
                                Rail(sol, (0, yc, z0 + 0.5 * h), fwd, up, c, over=0.2)]
    hs = cx.solids["head"]
    hc = hs.pts.mean(0)
    c = max(1, cap.get("Head", 1))
    cx.rails["Head"] = [Rail(hs, hc, fwd, up, c, over=0.15), Rail(hs, hc, fwd, fwd, c, "out")]
    for side, zone in (("L", "Left Arm"), ("R", "Right Arm")):
        sol = cx.solids[f"arm_{side}_fore"]
        sg = -1 if side == "L" else 1
        j = cx.arm_j[side]
        a, ex, ey = limb_axes(j["E"], j["W"])
        mid = (j["E"] + j["W"]) / 2
        c = max(1, cap.get(zone, 8))
        cx.rails[zone] = [Rail(sol, mid, a, ey, c, fill="fwd", over=-0.2), Rail(sol, mid, a, sg * ex, c, fill="fwd", over=-0.2), Rail(sol, mid, a, _u(ey + sg * ex), c, fill="fwd", over=-0.2)]
        cx.arm_axis[side] = a
    for side, zone in (("L", "Left Leg"), ("R", "Right Leg")):
        sol = cx.solids[f"leg_{side}_thigh"]
        sg = -1 if side == "L" else 1
        c = max(1, cap.get(zone, 2))
        cx.rails[zone] = [Rail(sol, sol.pts.mean(0), np.array([0.0, 0, -1]), (sg, 0, 0), c, fill="fwd", over=0.0), Rail(sol, sol.pts.mean(0), np.array([0.0, 0, -1]), fwd, c, fill="fwd", over=0.0)]


# ------------------------------------------------------------------------------------------- the layers under the armor

def spindle(p0, p1, r, n=8):
    """A muscle: a fat spindle from p0 to p1, thick in the middle, tapering at both ends (myomer bundle)."""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    a = _u(p1 - p0)
    ref = np.array([1.0, 0, 0]) if abs(a[0]) < 0.9 else np.array([0, 1.0, 0])
    u = _u(np.cross(a, ref))
    v = np.cross(a, u)
    pts = [p0, p1]
    for t, k in ((0.2, 0.75), (0.5, 1.0), (0.8, 0.75)):
        c = p0 + (p1 - p0) * t
        for i in range(n):
            ang = 2 * math.pi * (i + 0.5) / n
            pts.append(c + (math.cos(ang) * u + math.sin(ang) * v) * r * k)
    return np.array(pts)


def build_layers(cx, hd, hx, zh, z0):
    """Skeleton (bones and ball joints), myomer (spindle bundles around each bone) and the internal equipment (engine, gyro, cockpit,
    ammo bins, other unseen items), all INSIDE the armor shell. Spec: they are not visible frame (no exposed internals); they exist
    to place and size things, and the viewer's layer switches can show them. Each part carries its layer (LAYER_OF)."""
    S, Hm, P, tor = cx.S, cx.Hm, cx.P, cx.tor
    br = 0.012 * Hm                                               # bone radius

    def bone(a, b, r=br, zone="Frame"):               # the spine, hip, shoulder and rib bars belong to no one location
        S.add(cyl(a, b, r, None, 8), "bn", zone, "bone")

    def ball(c, r, zone):
        S.add(ellipsoid(c, (r, r, r), 24), "bn", zone, "bone")

    def muscles(p0, p1, w, d, zone, n=4, k=0.5):
        a, ex, ey = limb_axes(p0, p1)
        for i in range(n):
            ang = 2 * math.pi * i / n + math.pi / 4
            off = ex * math.cos(ang) * w * k + ey * math.sin(ang) * d * k
            S.add(spindle(p0 + off + (p1 - p0) * 0.06, p1 + off - (p1 - p0) * 0.06, 0.3 * min(w, d)), "my", zone, "muscle")
    for side, zone in (("L", "Left Leg"), ("R", "Right Leg")):
        J, segs = cx.leg_j[side]
        names = [k for k in ("hip", "knee", "hock", "ankle") if k in J]
        for a, b in zip(names, names[1:]):
            bone(J[a], J[b], br, zone)
        for k in names:
            ball(J[k], br * 1.5, zone)
        toe = J["ankle"] + np.array([0, 0.1 * Hm, 0])
        toe[2] = 0.03 * Hm
        bone(J["ankle"], toe, br * 0.9, zone)
        for p0, p1, w0, d0, w1, d1 in segs:
            muscles(p0, p1, (w0 + w1) / 2, (d0 + d1) / 2, zone)
    for side, zone in (("L", "Left Arm"), ("R", "Right Arm")):
        j = cx.arm_j[side]
        bone(j["S"], j["E"], br * 0.9, zone)
        bone(j["E"], j["W"], br * 0.9, zone)
        for k in ("S", "E", "W"):
            ball(j[k], br * 1.3, zone)
        muscles(j["S"], j["E"], j["wa"], j["da"], zone)
        muscles(j["E"], j["W"], j["wa"] * 0.8, j["da"] * 0.8, zone)
    # spine, hip bar, shoulder bar, ribs, skull
    yc, h = tor["yc"], tor["h"]
    hips = [cx.leg_j[x][0]["hip"] for x in "LR"]
    bone(hips[0], hips[1], br * 1.1)
    neck = np.array([0, hd["yh"], hd["z0"]])
    bone(np.array([0, yc, zh]), neck, br * 1.3)
    sh = [cx.arm_j[x]["S"] for x in "LR"]
    bone(sh[0], sh[1], br * 1.1)
    for fz in (0.25, 0.5, 0.75):
        wid = tor["W"] * 0.42
        bone(np.array([-wid, yc, z0 + fz * h]), np.array([wid, yc, z0 + fz * h]), br * 0.7)
    S.add(ellipsoid((0, hd["yh"], hd["z0"] + hd["hh"] * 0.5), (hd["hw"] * 0.6, hd["hd"] * 0.4, hd["hh"] * 0.4), 30), "bn", "Head", "bone")
    # torso muscle: vertical bundles front and back of each section
    for zone, (sol, xm, w, d) in cx.sec.items():
        for sy in (-1, 1):
            for sx in (-1, 1):
                a = np.array([xm + sx * 0.2 * w, yc + sy * 0.22 * d, z0 + 0.1 * h])
                S.add(spindle(a, a + np.array([0, 0, 0.8 * h]), 0.16 * min(w, d)), "my", zone, "muscle")
    # internal equipment: engine and gyro in the centre torso, the cockpit in the head, ammo and other unseen items in their location
    solids = {"Center Torso": cx.sec["Center Torso"][0], "Left Torso": cx.sec["Left Torso"][0], "Right Torso": cx.sec["Right Torso"][0],
              "Head": cx.solids["head"], "Left Arm": cx.solids["arm_L_up"], "Right Arm": cx.solids["arm_R_up"],
              "Left Leg": cx.solids["leg_L_thigh"], "Right Leg": cx.solids["leg_R_thigh"]}
    for zone, sol in solids.items():
        lo, hi = sol.pts.min(0), sol.pts.max(0)
        ctr, ext = (lo + hi) / 2, (hi - lo)
        pieces = []                                                # (volume, class, shape)
        for name, v in P["parts"][zone].items():
            if name in ("engine", "gyro", "cockpit") and v > 0:
                pieces.append((v, {"engine": "tm", "gyro": "hl", "cockpit": "t3"}[name], name))
        for it in P["items"].get(zone, []):
            if not it["visible"] and it["vol"] > 0:
                pieces.append((it["vol"], "wb" if it["kind"] == "ammo" else "t3", it["kind"]))
        if not pieces:
            continue
        axis = int(np.argmax(ext))
        cursor, total = 0.0, sum(v for v, _c, _n in pieces)
        for v, cls, name in pieces:
            frac = v / total
            cell = ext[axis] * 0.7 * frac
            side = (v / max(cell, 1e-3)) ** 0.5
            dims = np.minimum(np.array([side, side, side]), ext * 0.62)
            dims[axis] = max(cell * 0.92, 0.05)
            c = ctr.copy()
            c[axis] = lo[axis] + ext[axis] * 0.15 + cursor + cell / 2
            cursor += cell
            if name == "gyro":
                S.add(ellipsoid(c, tuple(dims / 2), 30), cls, zone, "internal")
            elif name == "engine":
                S.add(cyl(c - np.array([0, dims[1] / 2, 0]), c + np.array([0, dims[1] / 2, 0]), min(dims[0], dims[2]) / 2, None, 12), cls, zone, "internal")
            else:
                S.add(lbox(c, tuple(dims), bev=0.02 * min(dims)), cls, zone, "internal")


# ------------------------------------------------------------------------------------------------------------ assembly

def emit(cx, items, loc=None):
    """Write a list of (pts, cls, role, name[, loc]) to the sink; returns {(loc, name): Solid} of the core solids."""
    out = {}
    for it in items:
        pts, cls, role, name = it[:4]
        zone = it[4] if len(it) > 4 else loc
        sol = cx.S.add(pts, cls, zone, role)
        if role == "core" and sol is not None:
            out[(zone, name)] = sol
    return out


def prepare(model):
    P = model.get("_shell")
    if P is None:
        unit = model["_unit"]
        items = I.parse_items(unit)
        budget, parts = I.budgets(unit, items)
        P = dict(unit=unit, items=items, plan=I.place_items(unit, items), budget=budget, parts=parts,
                 ratio={z: I.armor_ratio(unit, z) for z in budget}, hash=I.name_hash(unit))
        model["_shell"] = P
    return P


def assemble(model, P, S, Hm):
    cx = Ctx(model, P, S, Hm)
    cx.geoms, cx.arm_axis, cx.arm_j, cx.sec = {}, {}, {}, {}
    A = ARCH[model["archetype"]]
    # 1. drawn items and the volume they take outside the shell
    ext = {}
    for zone, lst in P["items"].items():
        if zone == "_cap":
            continue
        for it in lst:
            if it["visible"]:
                L, W, Hh = item_dims(it, Hm)
                g = item_geometry(it, L, W, Hh)
                cx.geoms[id(it)] = (L, W, Hh, g)
                ext[zone] = ext.get(zone, 0.0) + item_volume(g)
    env = {z: max(0.4 * P["budget"][z], P["budget"][z] - ext.get(z, 0.0)) for z in P["budget"]}
    cx.env, cx.ext = env, ext
    # 2. legs (built at x = 0, then moved apart so their plates never touch)
    legs = {}
    for sg, zone in ((-1, "Left Leg"), (1, "Right Leg")):
        s = fit(lambda s_: leg_make(cx, sg, s_)[0], env[zone], vol_of)
        items, J, segs = leg_make(cx, sg, s)
        allp = np.vstack([i[0] for i in items])
        h_in = float((allp[:, 0] * -sg).max())
        h_out = float((allp[:, 0] * sg).max())
        legs[zone] = (items, J, segs, h_in, h_out, sg)
    g = 0.03 * Hm
    hx = max(l[3] for l in legs.values()) + g / 2
    zh = legs["Left Leg"][1]["hip"][2]
    pelvis_half = hx + max(l[4] for l in legs.values())
    for zone, (items, J, segs, h_in, h_out, sg) in legs.items():
        sol = emit(cx, shift(items, (sg * hx, 0, 0)), zone)
        side = "L" if sg < 0 else "R"
        cx.leg_j = getattr(cx, "leg_j", {})
        cx.leg_j[side] = ({k: v + np.array([sg * hx, 0, 0]) for k, v in J.items()}, [(sg_[0] + np.array([sg * hx, 0, 0]), sg_[1] + np.array([sg * hx, 0, 0])) + tuple(sg_[2:]) for sg_ in segs])
        cx.solids[f"leg_{side}_thigh"] = sol[(zone, "leg0")]
        cx.solids[f"leg_{side}_shin"] = sol[(zone, "leg1")]
    # 3. torso
    spec = torso_spec(cx)
    z0 = zh + 0.005 * Hm
    s_t = fit(lambda s_: torso_make(cx, s_, spec, z0, pelvis_half, env)[0], sum(env[z] for z in ("Left Torso", "Center Torso", "Right Torso")) - 0.3 * env["Center Torso"], vol_of)
    items, sols, tor = torso_make(cx, s_t, spec, z0, pelvis_half, env)
    emit(cx, items)
    cx.sec = sols
    cx.tor = tor
    ct = sols["Center Torso"][0]
    # 4. head
    ct_pts = ct.pts

    def ztop_fn(y):
        return ct.hit((0, y, z0 + 0.5 * tor["h"]), (0, 0, 1))[0][2]

    s_h = fit(lambda s_: head_make(cx, s_, spec, ct, tor["yc"], tor["wc"], tor["D"], env, ztop_fn)[0], env["Head"], vol_of)
    items, hd, hsol = head_make(cx, s_h, spec, ct, tor["yc"], tor["wc"], tor["D"], env, ztop_fn)
    emit(cx, items)
    cx.solids["head"] = hsol
    # 5. arms: beside the side torsos' outer faces and beside the pelvis, never inside them
    for sg, zone, side in ((-1, "Left Arm", "L"), (1, "Right Arm", "R")):
        sec = sols["Left Torso" if sg < 0 else "Right Torso"][0]
        z_s = z0 + 0.84 * tor["h"]

        def arm_items(s_, sg=sg, zone=zone):
            wa_ = 0.027 * Hm * s_ * model.get("armscale", 1.0)
            xo = float((sec.pts[:, 0] * sg).max())
            x_a = max(xo, pelvis_half) + wa_ * 1.35 + 0.012 * Hm
            return arm_make(cx, sg, s_, x_a, z_s, tor["yc"], zone, x_torso=xo)

        s_a = fit(lambda s_: arm_items(s_)[0], env[zone], vol_of)
        items, j = arm_items(s_a)
        sol = emit(cx, items, zone)
        cx.arm_j[side] = j
        cx.solids[f"arm_{side}_up"] = sol[(zone, "upper")] if (zone, "upper") in sol else sol[(zone, "trunk0")]
        cx.solids[f"arm_{side}_fore"] = sol[(zone, "fore")] if (zone, "fore") in sol else sol[(zone, "trunk5")]
    # 6. antennas
    for i in range(int(model.get("antennas") or 0) or (1 if model.get("antenna") else 0)):
        sx = (-1 if i % 2 == 0 else 1) * (0.45 if model.get("antennas", 0) > 1 else 0.0) * hd["hw"]
        base = np.array([sx, hd["yh"] - hd["hd"] * 0.3, hd["z0"] + hd["hh"] * 0.85])
        cx.S.add(cyl(base, base + np.array([sx * 0.4, -0.02 * Hm, 0.11 * Hm]), 0.035 * Hm / 12 * 3, 0.018, 6), "t4", "Head", "detail")
    # 6b. the layers under the armor: skeleton, myomer, internal equipment (drawn inside the shell; the viewer can show each alone)
    build_layers(cx, hd, hx, zh, z0)
    # 7. mounts: rails for weapons, fixed spots for vents, nozzles and domes
    build_rails(cx)
    for zone, placed in P["plan"].items():
        if zone not in cx.rails:
            continue
        pegs = {}
        for it, r, c in placed:
            if not it["visible"]:
                continue
            if it["kind"] in RAILKINDS:
                mount_on_rail(cx, zone, it, cx.rails[zone][r % len(cx.rails[zone])], c)
            else:
                pegs.setdefault(it["kind"], []).append(it)
        for kind, lst in pegs.items():
            lst = lst[:6]                                # a vent bank or nozzle row is capped so the surface stays readable
            for idx, it in enumerate(lst):
                mount_peg(cx, zone, it, idx, len(lst))
    return S.zmax


def build(model, k):
    """The skeleton-and-shell build: returns a B3 whose tallest point is the rules height (INTEGRATION__tokens._build calls this)."""
    P = prepare(model)
    Ht = M_LEVEL * model["drawn_levels"]
    Hm = Ht
    for _ in range(6):
        b = T.B3(1.0, k)
        S = Sink(b, Ht)
        top = assemble(model, P, S, Hm)
        if abs(top / Ht - 1) < 0.003:
            break
        Hm *= Ht / top
    model["shell_height_m"] = Hm
    return b
