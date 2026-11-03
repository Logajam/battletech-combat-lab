"""
INTEGRATION__tokens.py  (NEW 2026-10-31, Claude - Combat Lab ground work, output only)

Procedural unit tokens (INTEGRATION__COMBAT_LAB.md, Part A): a top-down token
and front / rear / side standees drawn from a unit file, with no copied art.

    unit  = read_unit("Atlas AS7-D.mtf")      # what the file says (no engine)
    model = build_model(unit)                 # the PART MODEL (plain dict)
    svg   = top_svg(model) / card_svg(model) / rear_svg(model) / side_svg(model)

Where each feature comes from (Daniel, 2026-10-31):
  - the unit file: tonnage, chassis type, arm actuators (hand / forearm / gun
    pod), jump jets, heat sinks, armor, and each weapon's ZONE (location);
  - the weapon's class and size, which pick a MOUNT STYLE (the file's slot order
    is not geometry, so a rack, barrel or turret is chosen by rule, not read);
  - the NAME hash: the chassis name picks the silhouette (legs, torso, head), so
    variants of one chassis look related;
  - data/token_overrides.json: named-unit overrides beat the hash.
Sizes: the standee is the RULES height (2 levels, 3 for a superheavy, Core
p.57 / p.240); the figure on it follows the cube-square law inside its band.

Everything is drawn in a unit-less "raw" frame (height 1, y up) and scaled once,
so a shape can be changed without touching the scale. Fill-only SVG with CSS
classes (f g hl, we wb wm wo), so the page chooses the colors.
"""

import hashlib
import json
import math
import os
import re
import sys

LEVEL = 60                     # px for one level of height in every drawing
OVERRIDES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "token_overrides.json")

ARCHETYPES = ("humanoid", "humanoid", "bird", "bird", "martian")      # bipeds; quads get dog / lizard, tripods their own

ZONES = ("Left Arm", "Right Arm", "Left Torso", "Right Torso", "Center Torso", "Head")
# the .mtf's armor line codes -> zones (front armor; the rear codes RTL / RTR / RTC are left out)
ARMOR_CODES = {"LA": "Left Arm", "RA": "Right Arm", "LT": "Left Torso", "RT": "Right Torso", "CT": "Center Torso",
               "HD": "Head", "LL": "Left Leg", "RL": "Right Leg", "CL": "Center Leg", "FLL": "Front Left Leg",
               "FRL": "Front Right Leg", "RLL": "Rear Left Leg", "RRL": "Rear Right Leg"}
SLOT_HEADERS = ZONES + ("Left Leg", "Right Leg", "Front Left Leg", "Front Right Leg",
                        "Rear Left Leg", "Rear Right Leg", "Center Leg")


# --------------------------------------------------------------------- reading

def weapon_class(name):
    """energy / ballistic / missile / other, from the weapon's name."""
    n = name.lower()
    if "anti-missile" in n or "ams" in n or "tag" in n or "probe" in n or "ecm" in n:
        return "other"
    if any(k in n for k in ("lrm", "srm", "mrm", "atm", "mml", "streak", "rocket", "narc", "arrow", "thunderbolt")):
        return "missile"
    if any(k in n for k in ("laser", "ppc", "flamer", "plasma", "pulse")):
        return "energy"
    if any(k in n for k in ("ac/", "ac ", "autocannon", "gauss", "machine gun", "rifle", "ultra", "rotary", "lb ")) \
            or n.endswith(" ac") or n.startswith("ac"):
        return "ballistic"
    return "other"


def weapon_is_big(name):
    """A weapon drawn as a heavy barrel / big rack rather than a small port."""
    n = name.lower()
    if re.search(r"(ac/?\s?(10|20)|gauss|ppc|large|heavy|lrm\s?(15|20)|srm\s?6|lb\s?(10|20)|rotary|ultra ac/?\s?(10|20))", n):
        return True
    return False


def read_unit(path):
    """Read the parts of a .mtf this module needs (not the engine's parser)."""
    unit = {"weapons": [], "slots": {}, "jets": 0, "jets_by": {}}
    cur = None
    in_weapons = False
    for raw in open(path, errors="ignore").read().splitlines():
        line = raw.strip()
        if line.startswith("#"):
            continue
        if not line:
            in_weapons = False
            continue
        key, sep, val = line.partition(":")
        key = "" if not sep else key.lower()                  # the files mix "Mass:" and "mass:"
        if key == "chassis":
            unit["chassis"] = val.strip()
        elif key == "clanname":
            unit["clanname"] = val.strip()
        elif key == "model":
            unit["model"] = val.strip()
        elif key == "config":
            unit["config"] = val.strip()
        elif key == "mass":
            unit["tons"] = int(val)
        elif key == "jump mp":
            unit["jump_mp"] = int(val or 0)
        elif key == "heat sinks":
            m = re.match(r"\s*(\d+)", val)
            unit["heat_sinks"] = int(m.group(1)) if m else 10
        elif key == "cockpit":
            unit["cockpit"] = val.strip()
        elif key.endswith(" armor") and key.split()[0].upper() in ARMOR_CODES and val.strip().isdigit():
            zone = ARMOR_CODES[key.split()[0].upper()]         # front armor only (RTL / RTR / RTC are rear and not listed)
            unit.setdefault("armor_by", {})[zone] = int(val)
            unit["armor"] = unit.get("armor", 0) + int(val)
        elif key == "weapons":
            in_weapons = True
        elif line[:-1] in SLOT_HEADERS and line.endswith(":"):
            cur = line[:-1]
            unit["slots"][cur] = []
            in_weapons = False
        elif in_weapons and "," in line:
            w, _, loc = line.rpartition(",")
            loc = loc.replace("(R)", "").strip()
            if loc in SLOT_HEADERS:
                unit["weapons"].append({"name": w.strip(), "zone": loc, "rear": "(R)" in line})
        elif cur is not None:
            unit["slots"][cur].append(line)
            if "Jump Jet" in line:
                unit["jets"] += 1
                unit["jets_by"][cur] = unit["jets_by"].get(cur, 0) + 1
    unit["jets"] = unit["jets"] if unit.get("jump_mp") else 0
    unit.setdefault("jump_mp", 0)
    unit.setdefault("heat_sinks", 10)
    unit.setdefault("armor", 0)
    return unit


# ----------------------------------------------------------------------- model

def _hash(text):
    return list(hashlib.sha256(text.lower().encode()).digest())


def _overrides():
    try:
        return json.load(open(OVERRIDES_PATH))
    except (OSError, ValueError):
        return {}


def rules_levels(tons):
    """The standee's height in levels: Core p.57 (2) and p.240 (superheavy, 3)."""
    return 3 if tons > 100 else 2


def drawn_levels(tons):
    """The figure's height: the cube-square law inside each rules band (never
    above the rules height): normal 2 x (t/100)^(1/3), superheavy 3 x (t/200)^(1/3)."""
    if tons > 100:
        return 3 * (tons / 200.0) ** (1.0 / 3.0)
    return 2 * (tons / 100.0) ** (1.0 / 3.0)


def mount_style(zone, cls, big, n_zone, classes_in_zone, hands, archetype, torso=""):
    """Pick how a weapon group is drawn from its zone, class and size.
    Daniel's style rule (2026-10-31): units with hands seldom carry over-the-shoulder
    weapons, so they get flank mounts; dogs and lizards carry hip pods. The files
    do not say this (hands do not predict torso weapons): it is art."""
    arm = zone.endswith("Arm")
    side = zone in ("Left Torso", "Right Torso")
    if arm:
        return "arm_rack" if cls == "missile" else "arm_barrel" if cls == "ballistic" else "arm_port"
    if side:
        if torso == "canopy" and cls == "missile":
            return "wing_bay"                                  # the rear wing bay carries the cells (Timber Wolf kit study)
        if hands == 2:
            return "flank_" + cls
        if archetype in ("dog", "lizard"):
            return "hip_pod"
        if cls == "missile":
            return "shoulder_rack"
        if cls == "ballistic" and big:
            return "shoulder_barrel"
        if n_zone >= 3 and len(classes_in_zone) >= 2:
            return "turret"
        return "flank_" + cls
    return "head_port" if zone == "Head" else "chest_" + cls


FEATURE_KEYS = ("archetype", "torso", "panels", "head_mount", "head_shape", "shoulders", "antenna", "arms_flex", "tilt", "arms_up",
                "plan", "profile", "hips")


def armor_thinness(unit, tons):
    """zone -> 0.78..1.00: how slim a location is drawn, from its armor against its
    maximum (twice the internal structure, mechsim.mech_state; head 9). Full armor = 1.0."""
    here = os.path.dirname(os.path.abspath(__file__))              # mechsim's modules import each other by bare name
    for sub in ("mechsim", "pathfinder"):
        if os.path.join(here, sub) not in sys.path:
            sys.path.append(os.path.join(here, sub))
    from mech_state import structure_for_tonnage
    try:
        structure = structure_for_tonnage(tons, "quad" if "Quad" in unit.get("config", "") else "biped")
    except ValueError:
        return {}
    out = {}
    for zone, armor in (unit.get("armor_by") or {}).items():
        cap = 9 if zone == "Head" else 2 * structure.get(zone, 0)
        if cap:
            out[zone] = round(0.78 + 0.22 * min(1.0, armor / (0.8 * cap)), 3)
    return out


def build_model(unit, overrides=None, hash_only=False):
    """The part model: a plain dict a renderer (or a person) can read and edit.
    `overrides` (name -> features) is added to data/token_overrides.json; `hash_only`
    ignores every override, to show what the name hash alone gives."""
    tons = unit["tons"]
    chassis = unit.get("clanname") or unit.get("chassis", "?")
    names = {unit.get("chassis", "").lower(), unit.get("clanname", "").lower()}
    hc = _hash(unit.get("chassis", "?"))
    config = unit.get("config", "Biped")
    quad = "Quad" in config

    # Daniel (2026-11-01): a location gets THINNER when it is under-armored; it never swells
    # (bulk causes clipping). Armor is judged against the location's maximum (twice its
    # structure, head 9; Core "Armor Diagram"), then mapped to 0.78-1.00 of the plain size.
    bulk = 1.0
    thin = armor_thinness(unit, tons)

    arche = ARCHETYPES[hc[0] % len(ARCHETYPES)]
    if quad:
        arche = ("dog", "lizard")[hc[0] % 2]
    elif "Tripod" in config:
        arche = "martian"
    model = {
        "name": f'{unit.get("chassis", "?")} {unit.get("model", "")}'.strip(),
        "chassis": chassis, "tons": tons, "config": config, "quad": quad, "tripod": "Tripod" in config,
        "rules_levels": rules_levels(tons), "drawn_levels": round(drawn_levels(tons), 3),
        "bulk": round(bulk, 3), "thin": thin,
        "archetype": arche,
        "plan": ("block", "block", "wedge", "flare")[hc[8] % 4],           # the torso seen from above
        "profile": ("upright", "sloped", "lean", "upright", "sloped", "upright", "lean", "hunch")[hc[9] % 8],   # seen from the side
        "hips": "flare" if hc[10] % 4 == 0 else "plain",
        "torso": ("box", "ovoid", "narrow", "slab")[hc[1] % 4],
        "panels": ("flush", "wings", "stepped")[hc[5] % 3],
        "head_mount": ("built_in", "front", "top", "full")[hc[2] % 4],
        "head_shape": ("box", "dome", "wedge", "visor")[hc[4] % 4],
        "shoulders": ("flush", "boom")[hc[6] % 2],
        "antenna": hc[7] % 3 == 0,
        "jets": min(unit["jets"], 6), "jets_by": dict(unit.get("jets_by", {})),
        "overridden": [],
    }
    head_slots = unit["slots"].get("Head")
    if head_slots and not any("Cockpit" in x for x in head_slots):
        model["head_mount"] = "built_in"                    # cockpit not in the head

    # named-unit overrides beat the hash (a name looks the features up and substitutes them)
    if not hash_only:
        ov = {**_overrides(), **(overrides or {})}
        for n in names:
            for k, v in (ov.get(n) or {}).items():
                if k in FEATURE_KEYS:
                    model[k] = v
                    model["overridden"].append(k)
    arche = model["archetype"]

    # arms from the actuators in each arm's slots (data, not the hash)
    arms = {}
    for side, zone in (("L", "Left Arm"), ("R", "Right Arm")):
        s = " ".join(unit["slots"].get(zone, []))
        arms[side] = "hand" if "Hand Actuator" in s else "forearm" if "Lower Arm Actuator" in s \
            else "pod" if s else "none"
    model["arms"] = None if quad else arms
    hands = sum(1 for v in arms.values() if v == "hand")

    # hardpoints: one group per zone and class
    groups = {}
    for w in unit["weapons"]:
        cls = weapon_class(w["name"])
        if cls == "other":
            continue
        g = groups.setdefault((w["zone"], cls), {"zone": w["zone"], "cls": cls, "count": 0, "big": False, "tubes": 0})
        g["count"] += 1
        if cls == "missile":
            m = re.search(r"(\d+)", w["name"])
            g["tubes"] += int(m.group(1)) if m else 4
        g["big"] = g["big"] or weapon_is_big(w["name"])
        nm = w["name"].lower()
        g.setdefault("subs", set()).update(
            k for k, hit in (("gauss", "gauss" in nm), ("uac", "ultra" in nm or "uac" in nm), ("lbx", "lb " in nm or "lb-" in nm or "lbx" in nm),
                             ("rotary", "rotary" in nm or "gatling" in nm), ("ppc", "ppc" in nm)) if hit)
    per_zone = {}
    for (zone, cls), g in groups.items():
        per_zone.setdefault(zone, []).append(g)
    for zone, gs in per_zone.items():
        n_zone = sum(g["count"] for g in gs)
        for g in gs:
            g["mount"] = mount_style(zone, g["cls"], g["big"], n_zone, {x["cls"] for x in gs}, hands, arche, model["torso"])
    model["hardpoints"] = [g for gs in per_zone.values() for g in gs]
    # a large weapon in a side torso pushes the head to the other side (Daniel)
    big_side = [z for z in ("Left Torso", "Right Torso") for g in per_zone.get(z, []) if g["big"]]
    model["head_offset"] = 0 if len(big_side) != 1 else (1 if big_side[0] == "Left Torso" else -1)   # figure's right = +1

    return model



# ------------------------------------------------------------ the 3D part model
# One object, drawn from four sides (Daniel, 2026-10-31: "technical drawings ... the
# measurements have to match"). Axes: x = the figure's right (+), y = forward (+),
# z = up. Parts are boxes (frustums) and limbs (sphere sweeps); each view is an
# orthographic projection of the SAME parts, hulled and drawn far to near.
#   top   : screen (x, -y)      front : (-x, -z)      rear : (x, -z)      side : (y, -z)
# A part lists the views it shows in (`vis`), so a port on the chest face is not
# painted onto the side view. Weapons have ABSOLUTE pixel sizes (k px per raw unit).

LEVEL_PX = LEVEL
ARCH3 = {   # leg_h, hips (w, d), torso (w, d, h), tilt, leg_r
    "humanoid": dict(lh=.42, hw=.20, hd=.16, tw=.34, td=.24, th=.32, tilt=.03, lr=.050),
    "bird":     dict(lh=.50, hw=.17, hd=.16, tw=.30, td=.28, th=.28, tilt=.14, lr=.042),
    "martian":  dict(lh=.56, hw=.17, hd=.16, tw=.32, td=.26, th=.26, tilt=-.04, lr=.036),
    "dog":      dict(lh=.30, hw=.30, hd=.50, tw=.30, td=.52, th=.24, tilt=.06, lr=.042),
    "lizard":   dict(lh=.26, hw=.34, hd=.50, tw=.34, td=.50, th=.22, tilt=.02, lr=.046),
}
TRIPOD3 = dict(lh=.44, hw=.20, hd=.20, tw=.36, td=.30, th=.24, tilt=.0, lr=.036)
WCLS = {"energy": "we", "ballistic": "wb", "missile": "wm"}
TONE = {"1": "t1", "2": "t2", "3": "t3", "4": "t4"}


def _hull(pts):
    pts = sorted(set((round(x, 4), round(y, 4)) for x, y in pts))
    if len(pts) < 3:
        return pts

    def half(ps):
        h = []
        for p in ps:
            while len(h) >= 2 and (h[-1][0] - h[-2][0]) * (p[1] - h[-2][1]) - (h[-1][1] - h[-2][1]) * (p[0] - h[-2][0]) <= 0:
                h.pop()
            h.append(p)
        return h
    lo, up = half(pts), half(pts[::-1])
    return lo[:-1] + up[:-1]


def _proj(view, p):
    x, y, z = p
    return {"top": (x, -y), "front": (-x, -z), "rear": (x, -z), "side": (y, -z)}[view]


def _depth(view, p):
    x, y, z = p
    return {"top": z, "front": y, "rear": -y, "side": -x}[view]       # larger = nearer the viewer is drawn last


class B3:
    """Collects parts. `f` scales x and y (the mass fit); `k` is px per raw unit."""

    def __init__(self, f=1.0, k=100.0):
        self.parts, self.f, self.k = [], f, k
        self.chamfer = 0.007                                   # BLOCK RULE: every body box has cut corners (the MWO look)

    def px(self, v):
        return v / self.k

    def box(self, c, s, tone, tilt=0.0, tx=1.0, ty=1.0, vis=None, tag="b", cls=None, plan=None, ch=None):
        """`plan` = (fw, y_back, y_front): x is scaled from 1 at y_back to fw at y_front, so a
        torso seen from above is a wedge (fw < 1) or flares forward (fw > 1) while the front
        and rear views still read its widest edge."""
        f = self.f
        cx, cy, cz = c[0] * f, c[1] * f, c[2]
        sx, sy, sz = s[0] * f, s[1] * f, s[2]
        z0, z1 = cz - sz / 2, cz + sz / 2
        pts = []
        if ch is None:
            ch = 0.0 if tag == "w" or min(s) < 0.02 else self.chamfer
        ch = min(ch, 0.3 * min(sx, sy, sz))                    # a chamfer never eats the box
        for zz, zin, scx, scy, ax, ay in ((z0, 1, cx, cy, sx / 2, sy / 2), (z1, -1, cx, cy + tilt * sz, sx / 2 * tx, sy / 2 * ty)):
            for dx in (-1, 1):
                for dy in (-1, 1):
                    px_, py_ = scx + dx * ax, scy + dy * ay
                    if ch:                                      # each corner becomes three points: the corner cut off
                        pts += [(px_ - dx * ch, py_, zz), (px_, py_ - dy * ch, zz), (px_, py_, zz + zin * ch)]
                    else:
                        pts.append((px_, py_, zz))
        if plan:
            fw, yb, yf = plan
            pts = [(x * (1 + (fw - 1) * max(0.0, min(1.0, (y / f - yb) / (yf - yb)))), y, z) for x, y, z in pts]
        self.parts.append({"groups": [[(p, 0.0) for p in pts]], "cls": cls or TONE[tone], "vis": vis, "tag": tag,
                           "vol": sx * sy * sz * (1 + tx * ty) / 2})

    def seg(self, points, radii, tone, vis=None, tag="b", cls=None):
        f = self.f
        pts = [(p[0] * f, p[1] * f, p[2]) for p in points]
        rs = [r * f for r in radii]
        groups = [[(pts[i], rs[i]), (pts[i + 1], rs[i + 1])] for i in range(len(pts) - 1)]
        vol = sum(math.pi * ((groups[i][0][1] + groups[i][1][1]) / 2) ** 2 * math.dist(groups[i][0][0], groups[i][1][0])
                  for i in range(len(groups)))
        self.parts.append({"groups": groups, "cls": cls or TONE[tone], "vis": vis, "tag": tag, "vol": vol})

    def ball(self, c, r, tone, vis=None, tag="b"):
        self.seg([c, c], [r, r], tone, vis, tag)

    def blob(self, ellipsoids, tone, vis=None, tag="b", cls=None, n=96):
        """ONE convex body: the hull of several ellipsoids [(centre, (rx, ry, rz))]. A teardrop torso
        that holds all three torso sections is the hull of a wide rear lobe pair and a narrow nose."""
        f = self.f
        golden = math.pi * (3 - math.sqrt(5))
        pts, vol = [], 0.0
        for c, (rx, ry, rz) in ellipsoids:
            for i in range(n):
                y = 1 - 2 * (i + 0.5) / n
                r = math.sqrt(max(0.0, 1 - y * y))
                th_ = golden * i
                pts.append(((c[0] + rx * r * math.cos(th_)) * f, (c[1] + ry * y) * f, c[2] + rz * r * math.sin(th_)))
            vol = max(vol, 4 / 3 * math.pi * rx * ry * rz * f * f)
        self.parts.append({"groups": [[(p, 0.0) for p in pts]], "cls": cls or TONE[tone], "vis": vis, "tag": tag,
                           "vol": vol * len(ellipsoids) * 0.75})

    def prism(self, c, length_px, r_px, sides, cls, vis=None):
        """A barrel with a polygonal section (Gauss = triangle), pointing forward (+y)."""
        x, y, z = c
        r = self.px(r_px) / self.f
        n = self.px(length_px)
        ring = [(r * math.sin(2 * math.pi * i / sides), r * math.cos(2 * math.pi * i / sides)) for i in range(sides)]
        pts = [(x + dx, yy, z + dz) for yy in (y, y + n) for dx, dz in ring]
        self.parts.append({"groups": [[(p, 0.0) for p in pts]], "cls": cls, "vis": vis, "tag": "w",
                           "vol": math.pi * r * r * n})

    def barrel(self, c, length_px, r_px, cls, vis=None):
        x, y, z = c
        self.seg([(x, y, z), (x, y + self.px(length_px) / self.f, z)], [self.px(r_px) / self.f] * 2, None, vis, "w", cls)


def weapon_barrel(b, c, gr, length_px, r_px, vis=None, embed=0.0):
    """One weapon's barrel, drawn by its kind (read from the name): each class has its own
    SECTION so it reads from the front (Timber Wolf kit study, 2026-11-03):
    PPC = smooth cylinder with a muzzle collar; Gauss = triangular tube; Ultra AC = twin
    barrels; LB-X = thick cylinder with an underside rail; rotary = three barrels."""
    x, y, z = c
    if embed:                                           # start inside the part it is mounted on: no gap
        y -= embed
        length_px += embed * b.k
    cls = WCLS[gr["cls"]]
    subs = gr.get("subs") or set()
    if "gauss" in subs:
        b.prism((x, y, z), length_px, r_px * 1.3, 3, cls, vis)
    elif "uac" in subs:
        for d in (-1, 1):
            b.barrel((x + d * b.px(r_px * 0.85) / b.f, y, z), length_px, r_px * 0.62, cls, vis)
        b.box((x, y + b.px(length_px * 0.3) / b.f, z), (b.px(r_px * 3.6) / b.f, b.px(length_px * 0.3), b.px(r_px * 1.6)), "3", tag="w")
    elif "lbx" in subs:
        b.barrel((x, y, z), length_px, r_px * 1.2, cls, vis)
        b.box((x, y + b.px(length_px * 0.4) / b.f, z - b.px(r_px * 1.5)), (b.px(r_px * 0.8) / b.f, b.px(length_px * 0.7), b.px(r_px * 0.8)), "3", tag="w")
    elif "rotary" in subs:
        for ang in (90, 210, 330):
            dx = b.px(r_px * 0.8) * math.cos(math.radians(ang)) / b.f
            dz = b.px(r_px * 0.8) * math.sin(math.radians(ang))
            b.barrel((x + dx, y, z + dz), length_px, r_px * 0.5, cls, vis)
    elif "ppc" in subs:
        b.barrel((x, y, z), length_px, r_px, cls, vis)
        b.barrel((x, y + b.px(length_px) / b.f, z), length_px * 0.18, r_px * 1.35, cls, vis)       # the muzzle collar
    else:
        b.barrel((x, y, z), length_px, r_px, cls, vis)


def _pod(b, c, tubes, tone="3"):
    """A missile pod, sized from the tube count (real masses are small: a cube-root law
    with a fudge so it never disappears). Cells on the front, a stripe on top and side."""
    n = max(2, min(tubes, 30))
    w = b.px(5 + 2.4 * n ** (1 / 3))
    h = w * (0.9 if n <= 6 else 1.1)
    d = w * 1.4
    x, y, z = c
    b.box((x, y, z), (w, d, h), tone, tag="w")
    cols = max(2, math.ceil(math.sqrt(n)))
    rows = math.ceil(n / cols)
    cell = w / (cols + 0.6)
    for i in range(min(n, 30)):
        r, cc = divmod(i, cols)
        b.box((x + (cc - (cols - 1) / 2) * cell, y + d / 2 + 0.002, z + ((rows - 1) / 2 - r) * cell * 0.9),
              (cell * 0.55, 0.004, cell * 0.55), "1", vis={"front"}, tag="w", cls="wm")
    b.box((x, y, z + h / 2 + 0.002), (w * 0.6, d * 0.9, 0.004), "1", vis={"top"}, tag="w", cls="wm")
    b.box((x + w / 2 + 0.002, y, z), (0.004, d * 0.8, h * 0.2), "1", vis={"side"}, tag="w", cls="wm")
    return w, h, d


def _build(model, f, k):
    """All the parts of one unit. Returns a B3."""
    b = B3(f, k)
    arche = model["archetype"]
    A = dict(TRIPOD3 if model["tripod"] else ARCH3[arche])
    wf = (0.92 + 0.14 * min(model["tons"], 100) / 100.0) * model["bulk"]
    A["tw"] *= wf * {"box": 1.0, "ovoid": 0.95, "narrow": 0.82, "slab": 1.12, "canopy": 1.05}[model["torso"]]
    A["hw"] *= wf
    A["lr"] *= wf * (1.0 + 0.0)
    if model.get("hips") == "flare" and not model["tripod"]:
        A["hw"] *= 1.35
    lh, hw, hd, tw, td, th, lr = A["lh"], A["hw"], A["hd"], A["tw"], A["td"], A["th"], A["lr"]
    thin = model.get("thin") or {}

    def slim(zone):                                            # under-armored locations are drawn thinner, never thicker
        return thin.get(zone, 1.0)
    tilt = model.get("tilt", A["tilt"])
    profile = model.get("profile", "upright")
    plan = model.get("plan", "block")
    if profile == "lean":
        tilt += 0.16
    quad = model["quad"]
    stance = (0.05, -0.05)                                     # mid-step: left foot forward, right back

    # ---- hips and legs: the legs join the hips from the SIDE
    hips_z = lh + 0.035
    if quad:
        b.box((0, 0, hips_z), (hw, hd, 0.07), "3")
    else:
        # PELVIS (Atlas / Timber Wolf kit studies): a flat plate, hexagonal from above (full width at the
        # sides, narrowing front and rear), cut corners, with a short apron hanging at the front
        b.box((0, 0, hips_z), (hw, hd * 1.05, 0.07), "3", tx=0.92, plan=(0.66, -hd * 0.52, hd * 0.52), ch=0.02)
        b.box((0, -hd * 0.1, hips_z), (hw * 0.78, hd * 0.8, 0.07), "3", plan=(1.0, -hd * 0.4, hd * 0.4), ch=0.02)
        b.box((0, hd * 0.42, hips_z - 0.05), (hw * 0.3, hd * 0.3, 0.07), "3", tx=0.7, ty=0.5, ch=0.01)
    hx = hw / 2 + 0.014

    def foot(x, y, z0, big=1.0):
        b.box((x, y + 0.035, z0 + 0.016), (lr * 2.3 * big, 0.12 * big, 0.032), "4")

    if model["tripod"]:
        feet = ((-0.24, 0.20), (0.24, 0.20), (0.0, -0.30))
        for i, (fx, fy) in enumerate(feet):
            top = (fx * 0.25, fy * 0.25, lh + 0.01)
            knee = (fx * 0.75 + (0.04 if fx >= 0 else -0.04) * (1 if i < 2 else 0), fy * 0.7, lh * 0.60)
            b.seg([top, knee, (fx, fy, 0.05)], [lr * 1.3, lr * 0.95, lr * 0.85], "2")
            b.ball(knee, lr * 0.95, "2")
            foot(fx, fy - 0.04, 0.0)
    elif quad:
        for fx in (-1, 1):
            for fy, st in ((1, stance[0]), (-1, stance[1])):
                y0 = fy * hd / 2.2
                if arche == "dog":
                    pts = [(fx * hx, y0, lh), (fx * hx, y0 + fy * 0.04 + st * 0.3, lh * 0.5), (fx * (hx - 0.01), y0 + st, 0.05)]
                else:
                    pts = [(fx * hx, y0, lh), (fx * (hx + 0.14), y0 + st * 0.3, lh * 0.5), (fx * (hx + 0.08), y0 + st, 0.05)]
                b.seg(pts, [lr * 1.3, lr, lr * 0.8], "2")
                b.ball(pts[1], lr, "2")
                foot(pts[2][0], pts[2][1] - 0.04, 0.0)
    else:
        for fx, st in ((-1, stance[0]), (1, stance[1])):             # figure's left is -x
            x = fx * hx
            lr = A['lr'] * slim('Left Leg' if fx < 0 else 'Right Leg')
            if arche == "bird":                                      # digitigrade: hock back, long foot
                pts = [(x, 0, lh), (x + fx * 0.012, -0.075 + st * 0.3, lh * 0.55), (x, 0.045 + st, lh * 0.17), (x, 0.11 + st, 0.02)]
                b.seg(pts, [lr * 1.5, lr * 1.1, lr * 0.75, lr * 0.5], "2")
                b.ball(pts[1], lr * 1.15, "2")
                b.seg([(pts[1][0] - 0.016, pts[1][1], pts[1][2]), (pts[1][0] + 0.016, pts[1][1], pts[1][2])], [lr * 1.45] * 2, "3")   # knee disc cover
                b.box((x, 0.06 + st, 0.02), (lr * 2.0, 0.17, 0.035), "4")
            elif arche == "martian":                                 # long legs, knees splayed out
                pts = [(x, 0, lh), (x + fx * 0.09, 0.03 + st * 0.4, lh * 0.55), (x + fx * 0.12, st, 0.05)]
                b.seg(pts, [lr * 1.4, lr, lr * 0.8], "2")
                b.ball(pts[1], lr * 1.1, "2")
                foot(pts[2][0], pts[2][1] - 0.04, 0.0)
            else:                                                    # humanoid: knee forward
                pts = [(x, 0, lh), (x + fx * 0.006, 0.045 + st * 0.5, lh * 0.5), (x, st, 0.05)]
                b.seg(pts, [lr * 1.5, lr * 1.2, lr * 0.95], "2")
                b.ball(pts[1], lr * 1.2, "2")
                b.seg([(pts[1][0] - 0.016, pts[1][1], pts[1][2]), (pts[1][0] + 0.016, pts[1][1], pts[1][2])], [lr * 1.5] * 2, "3")    # knee disc cover
                foot(x, st - 0.04, 0.0)

    # ---- torso: centre + two side torsos, seams between them
    z0 = hips_z + 0.035
    ztop = z0 + th
    cw = tw * 0.46
    sw = (tw - cw) / 2
    shape = model["torso"]
    tx, ty = {"box": (0.94, 0.9), "ovoid": (0.72, 0.72), "narrow": (1.22, 1.0), "slab": (1.0, 1.0), "canopy": (1.0, 1.0)}[shape]
    step = 0.03 if model["panels"] == "stepped" else 0.0
    flare = 1.12 if model["panels"] == "wings" else 1.0
    # SIDE profile: "sloped" = the front face leans back to the top (the rear stays upright), which
    # the top view cannot show; "lean" = the whole torso pitches forward; "hunch" adds a hump (below).
    if profile == "sloped":
        ty = 0.55
        tilt = (td / 2) * (ty - 1) / th
    # PLAN (top view): "wedge" narrows to the front, "flare" widens to it, both drawn from the back
    fw = {"block": 1.0, "wedge": 0.70, "flare": 1.18}[plan]
    pl = (fw, -td / 2, td / 2) if fw != 1.0 else None
    tw_eff = tw * (1 + (fw - 1) * 0.5)                             # half-way along the depth: where the arms attach
    cw = cw * slim("Center Torso")
    bays = {}                                                      # canopy torso: side -> (x, y, z, w, d, h) of its bay
    canopy = {}                                                    # canopy anchors for arms, flank weapons, head
    if shape == "canopy":
        # CANOPY TORSO (Timber Wolf kit study, 2026-11-03; Daniel's review 2026-11-03: the centre body
        # holds ALL THREE torso sections). One convex teardrop: a wide rear pair of lobes (the side
        # torsos) and a narrow dome nose (the centre torso), seams between the thirds, and a missile
        # bay sitting on each side torso. Plan = broad rear, round nose; profile = sloped nose.
        tilt = 0.0
        zc = z0 + th * 0.5
        sct = slim("Center Torso")
        b.blob([((0, -td * 0.14, zc), (tw * 0.5 * (0.5 + 0.5 * sct), td * 0.30, th * 0.5)),
                ((0, td * 0.20, zc - th * 0.06), (tw * 0.20 * sct, td * 0.28, th * 0.42)),
                ((-tw * 0.33 * (0.7 + 0.3 * slim("Left Torso")), -td * 0.10, zc - th * 0.02), (tw * 0.17, td * 0.26, th * 0.46)),
                ((tw * 0.33 * (0.7 + 0.3 * slim("Right Torso")), -td * 0.10, zc - th * 0.02), (tw * 0.17, td * 0.26, th * 0.46))], "1")
        for fx in (-1, 1):
            zone_t = "Left Torso" if fx < 0 else "Right Torso"
            bw = tw * 0.30 * slim(zone_t)
            bx = fx * tw * 0.33
            bays[fx] = (bx, -td * 0.16, zc + th * 0.5 + th * 0.12, bw, td * 0.40, th * 0.52)
            b.box((bx, bays[fx][1], bays[fx][2]), (bw, bays[fx][4], bays[fx][5]), "2", tx=0.9, ty=0.82, tilt=-0.10, ch=0.016)
            b.box((fx * tw * 0.168, td * 0.02, zc + th * 0.30), (0.007, td * 0.62, th * 0.50), "1", vis={"front", "rear", "top"}, cls="ln")   # seam between the thirds
        canopy = {"y_flank": td * 0.06, "z_flank": zc - th * 0.04, "y_nose": td * 0.36, "z_nose": zc - th * 0.07,
                  "x_arm": tw * 0.5 + 0.012, "y_arm": -td * 0.02, "z_arm": zc + th * 0.06, "y_rear": -td * 0.40,
                  "visor": (0, td * 0.22, zc + th * 0.30)}
        tw_eff = tw
    else:
        b.box((0, 0, z0 + th / 2 + step / 2), (cw, td, th + step), "1", tilt=tilt, tx=tx, ty=ty, plan=pl)
    for fx in () if shape == "canopy" else (-1, 1):
        zone_t = "Left Torso" if fx < 0 else "Right Torso"
        sw_f = sw * slim(zone_t)                                   # a thin side torso is narrower on that side only
        cxx = fx * (cw / 2 + sw_f / 2)
        b.box((cxx, 0, z0 + th / 2), (sw_f, td * 0.96, th), "2", tilt=tilt, tx=tx * flare, ty=ty, plan=pl)
        sx_ = fx * cw / 2
        b.box((sx_, 0.0, z0 + th / 2), (0.006, td * 0.98, th * 0.96), "1", tilt=tilt, vis={"front", "rear", "top"}, cls="ln", plan=pl)
    ftop = tilt * th                                               # the top face shifts by this

    # ---- head
    mount, shape_h = model["head_mount"], model["head_shape"]
    if shape == "canopy":
        mount = "built_in"                                          # the cockpit is the dome
    hoff = model["head_offset"] * tw * 0.16
    hs = slim("Head")
    if mount == "built_in" and canopy:                              # the glass sits on the dome of the nose
        b.box((canopy["visor"][0] + hoff, canopy["visor"][1], canopy["visor"][2]), (tw * 0.18, td * 0.30, 0.03), "4", tilt=-0.12, cls="hl")
    elif mount == "built_in":
        b.box((hoff, td / 2 * 0.5 + ftop * 0.8, ztop - 0.07), (0.09, td * 0.5, 0.035), "4", vis={"front", "side"}, cls="hl")
    else:
        big = mount in ("full", "boom")
        hw_, hh_ = ((0.15, 0.115) if big else (0.105, 0.085))
        hw_, hh_ = hw_ * hs, hh_ * hs
        if mount == "boom":                                        # head in the centre torso, out front on a neck
            hz = ztop - 0.06
            hy = td / 2 + 0.12
            b.seg([(hoff, td / 4, hz), (hoff, hy - 0.04, hz)], [0.04, 0.035], "3")
        elif mount == "front":
            hz, hy = ztop - 0.03, td / 2 + 0.01 + ftop * 0.5
        else:
            hz, hy = ztop + 0.035 + hh_ / 2, ftop * 0.7 + (td * 0.18 if profile == "hunch" else 0.0)
            b.seg([(hoff, hy, ztop - 0.01), (hoff, hy, ztop + 0.045)], [0.06, 0.05], "3")
        tpx = {"box": (1, 1), "dome": (0.7, 0.8), "wedge": (0.75, 0.5), "visor": (1, 1)}[shape_h]
        b.box((hoff, hy, hz), (hw_, hw_ * 0.85, hh_), "1", tx=tpx[0], ty=tpx[1], tilt=-0.2 if shape_h == "wedge" else 0)
        b.box((hoff, hy + hw_ * 0.43 + 0.002, hz), (hw_ * (0.9 if shape_h == "visor" else 0.6), 0.004, 0.022), "4", vis={"front"}, cls="hl")
        b.box((hoff, hy + hw_ * 0.3, hz), (hw_ * 0.5, hw_ * 0.5, 0.02), "4", vis={"top"}, cls="hl")
        if model.get("antenna"):
            b.seg([(hoff + hw_ * 0.3, hy, hz + hh_ / 2), (hoff + hw_ * 0.3, hy - 0.02, hz + hh_ / 2 + 0.08)], [0.006, 0.004], "3")

    if profile == "hunch":                                         # a hump rising behind the head: seen from the side
        b.box((0, -td * 0.2, ztop + 0.045), (tw * 0.78, td * 0.62, 0.09), "1", tx=0.78, ty=0.55, tilt=-0.12, plan=pl)

    # ---- arms (not on quads): a hand arm, a forearm arm, or a turret-pod arm
    zs = ztop - 0.05
    arms = model["arms"] or {}
    boom = 0.045 if model["shoulders"] == "boom" else 0.012
    for name, fx in (("L", -1), ("R", 1)):
        kind = arms.get(name)
        if not kind or quad:
            continue
        zone = "Left Arm" if name == "L" else "Right Arm"
        gs = _groups(model, zone)
        sl = slim(zone)
        ay = canopy["y_arm"] if canopy else 0.0                    # the shoulder socket sits on the side torso itself
        zs_ = canopy["z_arm"] if canopy else zs
        sx = fx * canopy["x_arm"] if canopy else fx * (tw_eff / 2 + boom + 0.02)
        b.seg([(fx * (tw_eff / 2 * 0.92), ay, zs_), (sx, ay, zs_)], [0.045 * sl, 0.04 * sl], "3")           # connective tissue
        b.ball((sx, ay, zs_), 0.038, "3")
        small = bool(gs) and not any(x["big"] for x in gs)
        up = model.get("arms_up")
        muz = None
        if kind == "pod" or (kind != "hand" and small and kind != "forearm"):               # upper actuator only: a turret
            n_w = max(1, sum(x["count"] for x in gs))
            pw = 0.05 + 0.014 * min(n_w, 4)
            pz = zs_ - 0.07 if not up else ztop + 0.08
            # POD ARM (block from the kit study): a lozenge - leaf-shaped in plan (narrows to the muzzle),
            # chamfered, with a raised spine on top and a stub underneath
            b.box((sx + fx * 0.012, ay + 0.03, pz), (pw * sl, 0.18, 0.10), "1", tx=0.85, plan=(0.55, -0.06, 0.12), ch=0.012)
            b.box((sx + fx * 0.012, ay + 0.02, pz + 0.06), (pw * sl * 0.4, 0.14, 0.025), "3")
            b.box((sx + fx * 0.012, ay - 0.03, pz - 0.06), (pw * sl * 0.3, 0.05, 0.03), "3")
            muz = (sx + fx * 0.012, ay + 0.03 + 0.08, pz)
        else:
            if up:
                el, wr = (sx + fx * 0.02, ay + 0.02, zs_ + 0.12), (sx + fx * 0.01, ay + 0.04, zs_ + 0.24)
            else:
                el, wr = (sx + fx * 0.012, ay + 0.02, zs_ - 0.13), (sx + fx * 0.006, ay + 0.075, zs_ - 0.25)
            w1 = (0.042 if kind == "hand" else 0.037) * sl
            b.seg([(sx, ay, zs_), el, wr], [w1 * 1.3, w1 * 1.1, w1], "2")
            b.ball(el, w1 * 1.15, "2")
            if kind == "hand":
                b.box((wr[0], wr[1] + 0.02, wr[2] - (0.03 if not up else -0.03)), (0.05, 0.05, 0.06), "4")
            muz = (wr[0], wr[1] + 0.03, wr[2])
        for gr in gs:                                          # weapons in line with the forearm / pod
            if gr["cls"] == "missile":
                _pod(b, (muz[0], muz[1] - 0.01, muz[2] - 0.06), gr["tubes"])
            else:
                nn = min(gr["count"], 3)
                for i in range(nn):
                    dx = (i - (nn - 1) / 2) * b.px(5) * f
                    weapon_barrel(b, (muz[0] + dx / f, muz[1], muz[2]), gr,
                                  22 if (gr["big"] and gr["cls"] == "ballistic") else 12 if gr["cls"] == "ballistic" else 7,
                                  2.2 + (1.4 if gr["big"] else 0) if gr["cls"] == "ballistic" else 1.5 + (0.8 if gr["big"] else 0), embed=0.04)

    # ---- torso-zone weapons
    for name, fx in (("L", -1), ("R", 1)):
        zone = "Left Torso" if name == "L" else "Right Torso"
        sxx = fx * tw * 0.33 if canopy else fx * (cw / 2 + sw * slim(zone) / 2)
        for gr in _groups(model, zone):
            m, c, n = gr["mount"], gr["cls"], gr["count"]
            if m == "wing_bay" and fx in bays:
                bx_, by_, bz_, bw_, bd_, bh_ = bays[fx]
                nt = max(2, min(gr["tubes"], 30))
                cols = max(2, math.ceil(math.sqrt(nt)))
                rows = math.ceil(nt / cols)
                cell = min(bw_ * 0.86 / cols, bh_ * 0.8 / rows)
                for i in range(nt):
                    rr, cc = divmod(i, cols)
                    b.box((bx_ + (cc - (cols - 1) / 2) * cell, by_ + bd_ / 2 + 0.002, bz_ + ((rows - 1) / 2 - rr) * cell),
                          (cell * 0.7, 0.004, cell * 0.7), "1", vis={"front"}, tag="w", cls="wm")
                b.box((bx_, by_, bz_ + bh_ / 2 + 0.002), (bw_ * 0.6, bd_ * 0.9, 0.004), "1", vis={"top"}, tag="w", cls="wm")
            elif m == "shoulder_rack":
                if model.get("arms_up") or model["archetype"] == "bird" and model["torso"] == "ovoid":
                    _pod(b, (fx * (tw_eff / 2 + 0.01), 0.0, ztop + 0.10), gr["tubes"])         # rises like ears
                    b.box((fx * (tw_eff / 2 + 0.01), 0.0, ztop + 0.03), (0.035, 0.05, 0.08), "3", tag="w")   # its stalk
                else:
                    _pod(b, (sxx, -0.01, ztop + 0.05), gr["tubes"])
                    b.box((sxx, -0.01, ztop + 0.005), (0.05, 0.06, 0.04), "3", tag="w")                      # the rack's mount
            elif m == "shoulder_barrel":
                b.box((sxx, 0.0, ztop + 0.015), (b.px(8), 0.07, 0.03), "3", tag="w")
                weapon_barrel(b, (sxx, 0.03, ztop + 0.035), gr, 24, 3.2)
            elif m == "turret":
                b.box((sxx, 0.0, ztop + 0.03), (0.09, 0.09, 0.05), "3", tag="w")
                for i in range(min(n, 4)):
                    b.barrel((sxx + (i - (min(n, 4) - 1) / 2) * b.px(5), 0.04, ztop + 0.04), 10, 1.6, WCLS[c])
            elif m == "hip_pod":
                if c == "missile":
                    _pod(b, (fx * (hw / 2 + 0.07), 0.0, hips_z), gr["tubes"])
                else:
                    b.barrel((fx * (hw / 2 + 0.05), 0.0, hips_z), 14, 2.4, WCLS[c])
            else:                                               # flank mounts on the torso face
                zf = canopy["z_flank"] if canopy else z0 + th * 0.62
                fy = canopy["y_flank"] if canopy else td / 2 + ftop * 0.6
                if c == "missile":
                    _pod(b, (sxx, fy + 0.02, zf), gr["tubes"])
                else:
                    for i in range(min(n, 3)):
                        weapon_barrel(b, (sxx, fy - 0.02, zf + 0.02 - i * b.px(5)), gr, 7, 1.5 + (0.9 if gr["big"] else 0), embed=0.04 if canopy else 0.0)
    for gr in _groups(model, "Center Torso"):
        for i in range(min(gr["count"], 4)):
            if canopy:                                              # barrels poking from the nose, buried in it
                weapon_barrel(b, ((i - (min(gr["count"], 4) - 1) / 2) * b.px(6), canopy["y_nose"], canopy["z_nose"]), gr, 6, 1.4, embed=0.06)
                continue
            b.box(((i - (min(gr["count"], 4) - 1) / 2) * b.px(6), td / 2 + ftop * 0.3 + 0.002, z0 + th * 0.3),
                  (b.px(3), 0.004, b.px(3)), "1", vis={"front"}, tag="w", cls=WCLS[gr["cls"]])

    # ---- jump jets, by location (the file says where): torso rear, or on the legs
    jb = model.get("jets_by") or {}
    for zone, n in jb.items():
        for i in range(min(n, 3)):
            if canopy:
                x, y, z = (-1 if "Left" in zone else 1 if "Right" in zone else 0) * tw * 0.3, canopy["y_rear"] - 0.02, z0 + 0.06 + i * 0.06
            elif zone == "Left Torso":
                x, y, z = -(cw / 2 + sw / 2) + 0.0, -td / 2 - 0.02, z0 + 0.04 + i * 0.06
            elif zone == "Right Torso":
                x, y, z = (cw / 2 + sw / 2), -td / 2 - 0.02, z0 + 0.04 + i * 0.06
            elif zone == "Center Torso":
                x, y, z = (i - (min(n, 3) - 1) / 2) * 0.05, -td / 2 - 0.02, z0 + 0.10
            else:
                x, y, z = (-1 if "Left" in zone else 1) * (hx + 0.03), -0.04, lh * 0.8 - i * 0.06
            b.box((x, y, z), (0.04, 0.05, 0.05), "4", cls="hl")
    return b


def _volume(b):
    return sum(p["vol"] for p in b.parts if p["tag"] != "w")


_VREF = {}


def _mass_factor(model):
    """Scale x and y so the body's volume matches a plain humanoid's: the cube-square
    law makes every 'Mech the same fraction of its bounding volume, so a unit that
    looks heavier than its tonnage is too fat (Scorpion)."""
    if "v" not in _VREF:
        ref = {"archetype": "humanoid", "torso": "box", "panels": "flush", "head_mount": "top", "head_shape": "box",
               "shoulders": "flush", "antenna": False, "jets": 0, "jets_by": {}, "bulk": 1.0, "tons": 70, "quad": False,
               "tripod": False, "arms": {"L": "hand", "R": "hand"}, "hardpoints": [], "head_offset": 0}
        _VREF["v"] = _volume(_build(ref, 1.0, 100.0))
    v = _volume(_build(model, 1.0, 100.0))
    return max(0.7, min(1.2, (_VREF["v"] / v) ** 0.5)) if v else 1.0


def _views(model, height_px):
    """Build the parts at the right scale; return (parts, k) with k px per raw unit."""
    f = _mass_factor(model)
    k = height_px
    for _ in range(3):
        b = _build(model, f, k)
        zmax = max(p[2] + g[1] for part in b.parts for grp in part["groups"] for g in [(p, r) for p, r in grp] for p in [g[0]]) if False else \
            max(pt[2] + r for part in b.parts for grp in part["groups"] for pt, r in grp)
        k = height_px / zmax
    xs = [(pt[0] + s * r) for part in b.parts for grp in part["groups"] for pt, r in grp for s in (-1, 1)]
    ys = [(pt[1] + s * r) for part in b.parts for grp in part["groups"] for pt, r in grp for s in (-1, 1)]
    half_w = max(abs(v) for v in xs)
    half_d = max(abs(v) for v in ys)
    rl = model["rules_levels"]
    cap = min(0.96 * 20 * rl / half_w, 0.96 * 56 / half_d, 0.95 * 50 / half_w, 0.90 * 50 / half_d)   # the base / hex cap
    if k > cap:                                                 # never draw outside the standee or its base
        k = cap
        b = _build(model, f, k)
    return b, k


def _render(b, k, view):
    polys = []
    for part in b.parts:
        if part["vis"] and view not in part["vis"]:
            continue
        for grp in part["groups"]:
            pts2 = []
            for (p, r) in grp:
                x, y = _proj(view, p)
                if r:
                    for ang in range(0, 360, 45):
                        pts2.append((x + r * math.cos(math.radians(ang)), y + r * math.sin(math.radians(ang))))
                else:
                    pts2.append((x, y))
            hull = _hull(pts2)
            if len(hull) < 3:
                continue
            d = sum(_depth(view, p) for p, _ in grp) / len(grp)
            polys.append((d, hull, part["cls"]))
    polys.sort(key=lambda t: t[0])
    return "".join(
        '<polygon points="%s" class="%s"/>' % (" ".join(f"{x * k:.1f},{y * k:.1f}" for x, y in h), c) for _, h, c in polys)


def _frame(model, inner, kind):
    rl = model["rules_levels"]
    ch = rl * LEVEL
    cw = 40 * rl if kind != "side" else 116
    card = (f'<rect x="{-cw / 2}" y="{-ch}" width="{cw}" height="{ch}" class="card"/>'
            f'<line x1="{-cw / 2}" x2="{cw / 2}" y1="{-LEVEL}" y2="{-LEVEL}" class="lvl"/>')
    if rl >= 3:
        card += f'<line x1="{-cw / 2}" x2="{cw / 2}" y1="{-2 * LEVEL}" y2="{-2 * LEVEL}" class="lvl"/>'
    base = f'<ellipse cx="0" cy="3" rx="{cw * 0.42}" ry="6" class="base"/>'
    return (f'<svg class="{kind}" viewBox="-85 {-3 * LEVEL - 6} 170 {3 * LEVEL + 18}" width="170" '
            f'height="{3 * LEVEL + 18}" role="img" aria-label="{model["name"]} {kind}">'
            f'{base}{card}<g class="fig">{inner}</g></svg>')


def _groups(model, zone):
    return [g for g in model["hardpoints"] if g["zone"] == zone]


def _view_svg(model, view):
    b, k = _views(model, model["drawn_levels"] * LEVEL)
    return _frame(model, _render(b, k, view), view if view != "front" else "front")


def card_svg(model):
    return _view_svg(model, "front")


def rear_svg(model):
    return _view_svg(model, "rear")


def side_svg(model):
    return _view_svg(model, "side")


def top_svg(model):
    """Top-down token on a flat-topped hex, facing up: the same parts, seen from above."""
    R = 52
    b, k = _views(model, model["drawn_levels"] * LEVEL)
    hexp = " ".join(f"{R * math.cos(math.radians(a)):.1f},{R * math.sin(math.radians(a)):.1f}" for a in range(0, 360, 60))
    inner = _render(b, k, "top")
    return (f'<svg class="top" viewBox="-60 -60 120 120" width="120" height="120" role="img" aria-label="{model["name"]} top">'
            f'<polygon points="{hexp}" class="hex"/><g class="fig">{inner}</g>'
            f'<polygon points="0,{-R + 1} -5,{-R + 9} 5,{-R + 9}" class="hl"/></svg>')


def lineup_figure(model, height_px):
    b, k = _views(model, height_px)
    return f'<g class="fig">{_render(b, k, "front")}</g>'
