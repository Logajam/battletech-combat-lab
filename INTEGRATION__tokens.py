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


def weapon_fam(name):
    """(family, size 1-3) of a weapon from its name, for its 3D model: laser / ppc / ac / uac / lbx /
    gauss / rotary / mg / flamer (energy and ballistic), srm / lrm / other missile."""
    n = name.lower()
    num = re.search(r"(\d+)", n)
    k = int(num.group(1)) if num else 0
    if "gauss" in n:
        return "gauss", 3 if ("heavy" in n or "hag" in n) else 2
    if "ppc" in n:
        return "ppc", 2 if "light" in n else 3
    if "laser" in n:
        return "laser", 3 if ("large" in n or "heavy" in n) else 1 if ("small" in n or "micro" in n) else 2
    if "flamer" in n:
        return "flamer", 1
    if "machine gun" in n or n.startswith("mg"):
        return "mg", 1
    if "rotary" in n:
        return "rotary", 3 if k >= 4 else 2
    if "lb" in n and "x" in n:
        return "lbx", 3 if k >= 10 else 2
    if "ultra" in n or "uac" in n:
        return "uac", 3 if k >= 10 else 2
    if re.search(r"ac\s*/?\s*\d", n) or "autocannon" in n:
        return "ac", 1 if k <= 2 else 2 if k <= 5 else 3
    if "srm" in n or "streak" in n:
        return "srm", 1 if k <= 2 else 2 if k <= 4 else 3
    if "lrm" in n or "mrm" in n or "atm" in n or "mml" in n:
        return "lrm", 2 if k <= 10 else 3
    return "", 2


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


# Cockpit weight, tons, by type: the standard cockpit is 3 t (Daniel, 2026-11-03: "usually a fixed 3 tons").
# The other weights are the construction rules' (TechManual, NOT in the indexed Core Rulebook): Claude's
# recall, used only to scale the drawn cockpit, never in a battle.
COCKPIT_TONS = {"standard": 3.0, "small": 2.0, "torso-mounted": 4.0, "command console": 3.0, "industrial": 3.0, "primitive": 5.0}


def cockpit_tons(text):
    t = (text or "").lower()
    for k, v in COCKPIT_TONS.items():
        if k in t:
            return v
    return 3.0


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
                "plan", "profile", "hips", "legs", "arm_style", "kit", "feet", "asym", "antennas", "surface", "crouch", "hands")


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
        "profile": ("upright", "sloped", "lean", "wedge_up", "bell", "shoulder", "prow", "dome", "stepped", "sloped", "prow", "hunch")[hc[9] % 12],   # seen from the side
        "hips": "flare" if hc[10] % 4 == 0 else "plain",
        "legs": "", "arm_style": "", "kit": "",      # dictionary terms (data/token_dictionary.json), set by reference tags only
        "feet": "", "asym": "", "antennas": 0, "crouch": False, "hands": "", "vents": 3 + hc[12] % 3,
        "cockpit_tons": cockpit_tons(unit.get("cockpit")),
        "surface": "plated" if (tons >= 60 or hc[11] % 2 == 0) else "smooth",   # panel lines, vents and bolts on the torso
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
        fam_, sz_ = weapon_fam(w["name"])
        if fam_:
            fd = g.setdefault("fam", {})
            fd[fam_] = max(fd.get(fam_, 0), sz_)
        if "pulse" in nm:
            g["pulse"] = True
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


# SIDE PROFILES of a torso (Daniel, 2026-11-03: "you keep using a parallelogram for torsos, so many
# side views look the same"). Each is a convex polygon (u, v): u = -1 (rear) .. +1 (front) along the
# depth, v = 0 (belly) .. 1 (top) along the height; the torso is that polygon extruded across its
# width (B3.extrude), so the side view IS the polygon. "stepped" and "hunch" add a second solid.
PROFILES = {
    "upright":  [(-1, .10), (-.9, 0), (.9, 0), (1, .10), (1, .9), (.9, 1), (-.9, 1), (-1, .9)],
    "sloped":   [(-1, .08), (-.92, 0), (.92, 0), (1, .10), (.30, 1), (-.9, 1), (-1, .92)],          # front face leans back
    "lean":     [(-1, .10), (-.9, 0), (.9, 0), (1, .10), (1, .38), (-.78, 1), (-1, .92)],           # top falls away to the front
    "wedge_up": [(-1, .10), (-.9, 0), (.9, 0), (1, .10), (1, .92), (.9, 1), (-.25, 1), (-1, .30)],  # chest forward, rear low
    "bell":     [(-1, .06), (-.94, 0), (.94, 0), (1, .06), (.52, 1), (-.52, 1)],                    # narrow at the top
    "shoulder": [(-.56, 0), (.56, 0), (1, .46), (1, .94), (.9, 1), (-.9, 1), (-1, .94), (-1, .46)], # narrow belly, deep chest
    "prow":     [(-1, .26), (-.62, 0), (.42, 0), (1, .42), (1, .60), (.42, 1), (-.62, 1), (-1, .74)],   # pointed nose, both faces cut
}
PROFILES["dome"] = [(-1, 0), (1, 0), (1, .42)] + [(math.cos(math.radians(a)), .42 + .58 * math.sin(math.radians(a))) for a in range(22, 160, 22)] + [(-1, .42)]
PROFILES["toe"] = [(-1, 0), (1, 0), (1, .30), (-.2, .85), (-1, 1)]          # a toe: low at the front, rising to the ankle
PROFILES["fin"] = [(-1, 0), (1, 0), (-.15, 1), (-1, .92)]                 # a tail fin: long at the base, swept back to a peak
PROFILES["slung_wedge"] = [(-1, .05), (-.9, 0), (.1, 0), (1, .38), (1, .64), (.3, .74), (-.7, 1), (-1, .95)]     # long, low, belly rising to the nose
PROFILES["tall_slab"] = PROFILES["upright"]                                                                # narrow and tall (size changes in _build)
PROFILES["hunch"] = PROFILES["stepped"] = PROFILES["upright"]


def profile_span(prof, v):
    """(u_min, u_max) of a convex profile polygon at height v (0..1)."""
    us = []
    n = len(prof)
    for i in range(n):
        (u0, v0), (u1, v1) = prof[i], prof[(i + 1) % n]
        if (v0 - v) * (v1 - v) <= 0 and v0 != v1:
            us.append(u0 + (u1 - u0) * (v - v0) / (v1 - v0))
        elif v0 == v1 == v:
            us += [u0, u1]
    return (min(us), max(us)) if us else (-1.0, 1.0)


class B3:
    """Collects parts. `f` scales x and y (the mass fit); `k` is px per raw unit."""

    def __init__(self, f=1.0, k=100.0):
        self.parts, self.f, self.k = [], f, k
        self.chamfer = 0.007                                   # BLOCK RULE: every body box has cut corners (the MWO look)

    def px(self, v):
        return v / self.k

    def box(self, c, s, tone, tilt=0.0, tx=1.0, ty=1.0, vis=None, tag="b", cls=None, plan=None, ch=None):
        """`plan` = (fw, y_back, y_front[, x_centre]): x is scaled (about x_centre, default the figure's
        centre line: use the part's own x for an off-centre part such as an arm pod) from 1 at y_back to fw at y_front, so a
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
            fw, yb, yf = plan[:3]
            px0 = (plan[3] * f) if len(plan) > 3 else 0.0           # the taper is about this x: 0 = the figure's centre line
            pts = [(px0 + (x - px0) * (1 + (fw - 1) * max(0.0, min(1.0, (y / f - yb) / (yf - yb)))), y, z) for x, y, z in pts]
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

    def extrude(self, cx, z0, w, d, h, prof, tone, wtop=1.0, fw=1.0, vis=None, tag="b", cls=None, cy=0.0, bulge=0.0):
        """A solid whose SIDE view is `prof` (PROFILES): the polygon extruded across width w. wtop = the
        width at the top against the belly; fw = the width at the front against the rear (the plan)."""
        f = self.f
        pts = []
        for u, v in prof:
            hx = w / 2 * (1 - (1 - wtop) * v)
            plan_k = (1 + (fw - 1) * (u + 1) / 2) * (1 - bulge * u * u)   # the plan scales the whole torso about its centre line,
            for sx in (-1, 1):                                     # so the three sections stay joined
                pts.append(((cx + sx * hx) * plan_k * f, (cy + u * d / 2) * f, z0 + v * h))
        self.parts.append({"groups": [[(p, 0.0) for p in pts]], "cls": cls or TONE[tone], "vis": vis, "tag": tag,
                           "vol": w * d * h * f * f * 0.8})

    def blob(self, ellipsoids, tone, vis=None, tag="b", cls=None, n=64):
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
    """One weapon's 3D model, by family (read from its name; Timber Wolf / Atlas kit studies, 2026-11-03).
    The receiver / housing is buried in the part it mounts on (`embed`), so nothing floats.
    laser = housing with heat-fin plate and a lens in the class color (pulse: a second lens);
    PPC = long barrel with coil rings and a forked muzzle; AC = receiver, side ammo feed, barrel, muzzle
    brake (by size); Ultra AC = twin barrels; LB-X = thick barrel with an underside rail; Gauss =
    triangular tube with coil rings; machine gun = small housing, twin barrels, ammo box; flamer =
    tank and nozzle; rotary = a drum and three barrels. Sizes are in pixels (weapons keep their own scale)."""
    x, y, z = c
    if embed:                                           # start inside the part it is mounted on: no gap
        y -= embed
        length_px += embed * b.k
    U = lambda v: b.px(v) / b.f                         # a size across or along the figure (x, y), in model units
    W = b.px                                            # a size in height
    cls = WCLS[gr["cls"]]
    fams = gr.get("fam") or {}
    fam = next((f for f in ("gauss", "lbx", "uac", "rotary", "ac", "ppc", "laser", "mg", "flamer") if f in fams), None)
    sz = fams.get(fam, 2)
    subs = gr.get("subs") or set()

    def rbox(y0, rl, rw, rh, tone="3", dz=0.0, dx=0.0):
        b.box((x + U(dx), y + U(y0 + rl / 2), z + W(dz)), (U(rw), U(rl), W(rh)), tone, tag="w", ch=0.003)

    if fam == "laser":
        r = (1.0, 1.45, 1.9)[sz - 1]
        H = (6, 8, 11)[sz - 1]
        rbox(0, H, r * 2.4, r * 2.2)                                          # housing
        rbox(H * 0.12, H * 0.62, r * 1.7, r * 0.5, "4", dz=r * 1.25)         # heat-fin plate on top
        if gr.get("pulse"):
            for d in (-1, 1):
                b.barrel((x + U(d * r * 0.55), y + U(H * 0.9), z), max(2.0, length_px - H * 0.9 + 1.0), r * 0.55, cls, vis)
        else:
            b.barrel((x, y + U(H * 0.9), z), max(2.0, length_px - H * 0.9 + 1.0), r * 0.9, cls, vis)      # the lens
    elif fam == "ppc":
        r = 1.5 + 0.35 * sz
        b.barrel((x, y, z), length_px, r, cls, vis)
        for t in (0.22, 0.42, 0.62):                                          # coil rings
            b.barrel((x, y + U(length_px * t), z), 2.2, r * 1.5, cls, vis)
        for d in (-1, 1):                                                     # the forked muzzle
            b.barrel((x + U(d * r * 0.95), y + U(length_px * 0.92), z), 4.0, r * 0.5, cls, vis)
    elif fam in ("ac", "lbx", "uac"):
        r = (1.2, 1.6, 2.1)[sz - 1] + (0.3 if fam == "lbx" else 0.0)
        rl = length_px * 0.40
        rbox(0, rl, r * 2.8, r * 2.5)                                         # receiver
        rbox(rl * 0.2, rl * 0.55, r * 1.1, r * 1.5, "4", dx=r * 1.8)          # side ammo feed
        if fam == "uac":
            for d in (-1, 1):
                b.barrel((x + U(d * r * 0.85), y + U(rl * 0.6), z), length_px - rl * 0.6, r * 0.62, cls, vis)
        else:
            b.barrel((x, y + U(rl * 0.6), z), length_px - rl * 0.6, r, cls, vis)
            b.barrel((x, y + U(length_px * 0.92), z), length_px * 0.12, r * 1.4, cls, vis)       # muzzle brake
            if fam == "lbx":
                rbox(rl, length_px * 0.5, r * 0.8, r * 0.8, "3", dz=-r * 1.5)                  # underside rail
    elif fam == "gauss":
        b.prism((x, y, z), length_px, r_px * 1.3, 3, cls, vis)
        for t in (0.3, 0.55, 0.8):                                            # coil rings
            b.prism((x, y + U(length_px * t), z), 2.2, r_px * 1.7, 3, cls, vis)
    elif fam == "mg":
        rbox(0, 4.5, 2.6, 2.4)
        for d in (-1, 1):
            b.barrel((x + U(d * 0.7), y + U(3.0), z), max(3.0, length_px - 3.0), 0.5, cls, vis)
        rbox(0.5, 3.0, 1.8, 2.0, "4", dz=-2.0)                                # ammo box
    elif fam == "flamer":
        b.barrel((x, y + U(2.0), z), 4.5, 1.6, cls, vis)                      # fuel tank
        b.barrel((x, y + U(5.0), z), max(3.0, length_px - 5.0), 0.7, cls, vis)
    elif fam == "rotary":
        b.barrel((x, y, z), length_px * 0.3, r_px * 1.9, cls, vis)            # drum
        for ang in (90, 210, 330):
            dx = b.px(r_px * 0.8) * math.cos(math.radians(ang)) / b.f
            dz = b.px(r_px * 0.8) * math.sin(math.radians(ang))
            b.barrel((x + dx, y + U(length_px * 0.2), z + dz), length_px * 0.85, r_px * 0.5, cls, vis)
    else:
        b.barrel((x, y, z), length_px, r_px, cls, vis)


def _pod(b, c, tubes, tone="3"):
    """A missile launcher, sized from the tube count (real masses are small: a cube-root law with a fudge so
    it never disappears): a chamfered frame, a lid line across the top, and the tubes as dark recesses with a
    colored rim on the front face, a stripe on top and on the side."""
    n = max(2, min(tubes, 30))
    w = b.px(5 + 2.4 * n ** (1 / 3))
    h = w * (0.9 if n <= 6 else 1.1)
    d = w * 1.4
    x, y, z = c
    b.box((x, y, z), (w, d, h), tone, tag="w", ch=0.004)
    cols = max(2, math.ceil(math.sqrt(n)))
    rows = math.ceil(n / cols)
    cell = w / (cols + 0.6)
    for i in range(min(n, 30)):
        r, cc = divmod(i, cols)
        cx_, cz_ = x + (cc - (cols - 1) / 2) * cell, z + ((rows - 1) / 2 - r) * cell * 0.9
        b.box((cx_, y + d / 2 + 0.001, cz_), (cell * 0.80, 0.003, cell * 0.80), "1", tag="w", cls="wm")           # colored rim
        b.box((cx_, y + d / 2 + 0.003, cz_), (cell * 0.52, 0.005, cell * 0.52), "1", tag="w", cls="ln")           # the dark tube mouth
    b.box((x, y + d / 2 - d * 0.18, z + h / 2 + 0.0015), (w * 0.9, d * 0.18, 0.003), "1", tag="w", cls="ln")      # lid line
    b.box((x, y, z + h / 2 + 0.002), (w * 0.6, d * 0.9, 0.004), "1", vis={"top"}, tag="w", cls="wm")
    b.box((x + w / 2 + 0.002, y, z), (0.004, d * 0.8, h * 0.2), "1", vis={"side"}, tag="w", cls="wm")
    return w, h, d


def _build(model, f, k):
    """All the parts of one unit. Returns a B3."""
    b = B3(f, k)
    arche = model["archetype"]
    A = dict(TRIPOD3 if model["tripod"] else ARCH3[arche])
    wf = (0.92 + 0.14 * min(model["tons"], 100) / 100.0) * model["bulk"]
    A["tw"] *= wf * {"box": 1.0, "ovoid": 0.95, "narrow": 0.82, "slab": 1.12, "canopy": 1.05, "dome": 1.08}[model["torso"]]
    A["hw"] *= wf
    A["lr"] *= wf * (1.0 + 0.0)
    if model.get("hips") == "flare" and not model["tripod"]:
        A["hw"] *= 1.35
    lh, hw, hd, tw, td, th, lr = A["lh"], A["hw"], A["hd"], A["tw"], A["td"], A["th"], A["lr"]
    thin = model.get("thin") or {}

    def slim(zone):                                            # under-armored locations are drawn thinner, never thicker
        return thin.get(zone, 1.0)
    tilt = 0.0                                                     # (the old shear that made every torso a parallelogram is gone)
    profile = model.get("profile", "upright")
    plan = model.get("plan", "block")
    prof = PROFILES.get(profile, PROFILES["upright"])
    if plan == "arrow":
        td *= 1.28                                                 # a long pointed nose
    if profile == "slung_wedge":
        td *= 1.2
        th *= 0.9
    if profile == "tall_slab":
        tw *= 0.84
        th *= 1.12
        td *= 0.92

    def front_y(v):                                                # the torso's front face at height v (0..1), for mounting things on it
        return profile_span(prof, v)[1] * td / 2
    quad = model["quad"]
    if model.get("crouch"):
        lh *= 0.84                                                 # a crouched stance: legs shorter, knees pushed forward
    kc = 0.04 if model.get("crouch") else 0.0
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
        # a foot: a heel block, a sole plate and two toe wedges (low at the front), not one slab
        b.box((x, y - 0.012, z0 + 0.022), (lr * 2.3 * big, 0.05 * big, 0.044), "4", ch=0.008)
        for dx in (-1, 1):
            b.extrude(x + dx * lr * 0.62 * big, z0, lr * 1.05 * big, 0.085 * big, 0.04, PROFILES["toe"], "4", cy=y + 0.055 * big)
        if model.get("feet") == "thrusters":                       # heel thrusters (jump jets on the feet)
            b.box((x, y - 0.035, z0 + 0.04), (lr * 1.4, 0.035, 0.05), "3", ch=0.006)
            b.box((x, y - 0.058, z0 + 0.04), (lr * 1.0, 0.012, 0.035), "4", cls="hl")

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
            if arche == "bird":
                # CHICKEN LEG (chart + kits, 2026-11-03): thigh angled forward-down to the knee, shin angled
                # back-down to a HIGH hock, then the long foot forward-down to a claw of three toes
                hip, knee = (x, 0.0, lh), (x + fx * 0.010, 0.07 + st * 0.3 + kc, lh * 0.60)
                hock, ank = (x + fx * 0.006, -0.055 + st * 0.3, lh * 0.27), (x, 0.045 + st, 0.045)
                b.seg([hip, knee], [lr * 1.55, lr * 1.25], "2")
                b.seg([knee, hock], [lr * 1.25, lr * 0.95], "2")
                b.seg([hock, ank], [lr * 0.85, lr * 0.62], "2")
                b.ball(knee, lr * 1.2, "2")
                b.seg([(knee[0] - 0.016, knee[1], knee[2]), (knee[0] + 0.016, knee[1], knee[2])], [lr * 1.45] * 2, "3")           # knee disc cover
                b.box((hock[0], hock[1] - 0.012, hock[2]), (lr * 2.0, lr * 1.8, lr * 2.0), "3", ch=0.008)                          # hock block
                for tdx, tlen in ((-lr * 0.9, 0.11), (lr * 0.9, 0.11), (0.0, -0.07)):                                              # claw toes: two forward, one back
                    b.box((x + tdx, ank[1] + tlen * 0.5, 0.02), (lr * 0.8, abs(tlen), 0.03), "4", ch=0.006)
                b.box((x, ank[1] - 0.005, 0.03), (lr * 1.6, 0.05, 0.05), "4", ch=0.008)
                if model.get("feet") == "thrusters":
                    b.box((x, ank[1] - 0.04, 0.05), (lr * 1.0, 0.03, 0.05), "3")
            elif arche == "martian":                                 # long legs, knees splayed out
                pts = [(x, 0, lh), (x + fx * 0.09, 0.03 + st * 0.4, lh * 0.55), (x + fx * 0.12, st, 0.05)]
                b.seg(pts, [lr * 1.4, lr, lr * 0.8], "2")
                b.ball(pts[1], lr * 1.1, "2")
                foot(pts[2][0], pts[2][1] - 0.04, 0.0)
            elif model.get("legs") == "pillar":                      # thick straight columns, little knee bend, wide block feet
                pts = [(x * 1.08, 0, lh), (x * 1.08, 0.022 + st * 0.3, lh * 0.5), (x * 1.08, st * 0.5, 0.05)]
                b.seg(pts, [lr * 1.9, lr * 1.75, lr * 1.55], "2")
                b.ball(pts[1], lr * 1.95, "2")
                b.seg([(pts[1][0] - 0.02, pts[1][1], pts[1][2]), (pts[1][0] + 0.02, pts[1][1], pts[1][2])], [lr * 2.0] * 2, "3")
                foot(x * 1.08, st * 0.5 - 0.04, 0.0, big=1.5)
            elif model.get("legs") == "slab":                        # stacked chamfered slabs: two on the thigh, three on the shin, a clamshell knee
                pts = [(x, 0, lh), (x + fx * 0.006, 0.045 + st * 0.5 + kc, lh * 0.5), (x, st, 0.05)]
                for a_, b_, w0, w1_, n_ in ((pts[0], pts[1], 2.8, 2.5, 2), (pts[1], pts[2], 2.5, 1.8, 3)):
                    for i_ in range(n_):
                        t0, t1 = i_ / n_, (i_ + 1) / n_
                        tm_ = (t0 + t1) / 2
                        c_ = tuple(a_[k] + (b_[k] - a_[k]) * tm_ for k in range(3))
                        wd_ = lr * (w0 + (w1_ - w0) * tm_)
                        b.box(c_, (wd_, wd_ * 0.95, abs(a_[2] - b_[2]) / n_ * 0.97), "2" if i_ % 2 == 0 else "3", ch=0.01)
                b.box(pts[1], (lr * 3.0, lr * 3.0, 0.05), "3", ch=0.014)
                foot(x, st - 0.04, 0.0, big=1.3)
            elif model.get("legs") == "reverse":                     # lower leg angled back, with a big heel
                pts = [(x, 0, lh), (x + fx * 0.006, 0.05 + st * 0.5 + kc, lh * 0.5), (x, -0.025 + st * 0.5, 0.06)]
                b.seg(pts, [lr * 1.5, lr * 1.25, lr * 1.0], "2")
                b.ball(pts[1], lr * 1.25, "2")
                b.box((x, pts[2][1] - 0.05, 0.035), (lr * 2.0, 0.07, 0.06), "3", ch=0.008)       # the heel
                foot(x, pts[2][1] - 0.01, 0.0)
            elif model.get("legs") == "barrel":                      # a fat barrel-shaped shin under a normal thigh
                pts = [(x, 0, lh), (x + fx * 0.006, 0.045 + st * 0.5, lh * 0.5), (x, st, 0.05)]
                b.seg(pts[:2], [lr * 1.5, lr * 1.2], "2")
                b.seg([pts[1], (x, st * 0.9, 0.07)], [lr * 1.9, lr * 2.1], "2")
                b.ball(pts[1], lr * 1.3, "2")
                foot(x, st - 0.04, 0.0, big=1.25)
            elif model.get("legs") == "heavy":                       # very thick thighs, short shins
                pts = [(x, 0, lh), (x + fx * 0.006, 0.045 + st * 0.5, lh * 0.5), (x, st, 0.05)]
                b.seg(pts, [lr * 2.3, lr * 1.5, lr * 1.0], "2")
                b.ball(pts[1], lr * 1.4, "2")
                foot(x, st - 0.04, 0.0, big=1.2)
            else:                                                    # humanoid: knee forward
                pts = [(x, 0, lh), (x + fx * 0.006, 0.045 + st * 0.5 + kc, lh * 0.5), (x, st, 0.05)]
                b.seg(pts, [lr * 1.5, lr * 1.2, lr * 0.95], "2")
                for a_, b_, r_ in ((pts[0], pts[1], lr * 1.5), (pts[1], pts[2], lr * 1.15)):      # a panel line down the front of thigh and shin
                    mid_ = ((a_[0] + b_[0]) / 2, (a_[1] + b_[1]) / 2 + r_ * 1.0, (a_[2] + b_[2]) / 2)
                    b.box(mid_, (0.005, 0.004, abs(a_[2] - b_[2]) * 0.6), "1", cls="ln", ch=0.0)
                for tt, ra in ((0.42, 1.55), (0.52, 1.25)):          # armor bands across thigh and shin: thin plates
                    a0 = (pts[0][0] + (pts[1][0] - pts[0][0]) * tt, pts[0][1] + (pts[1][1] - pts[0][1]) * tt, pts[0][2] + (pts[1][2] - pts[0][2]) * tt)
                    b.box(a0, (lr * ra * 2.1, lr * ra * 2.1, 0.009), "3", ch=0.003)
                    a1 = (pts[1][0] + (pts[2][0] - pts[1][0]) * tt, pts[1][1] + (pts[2][1] - pts[1][1]) * tt, pts[1][2] + (pts[2][2] - pts[1][2]) * tt)
                    b.box(a1, (lr * (ra - 0.3) * 2.1, lr * (ra - 0.3) * 2.1, 0.009), "3", ch=0.003)
                b.ball(pts[1], lr * 1.2, "2")
                b.seg([(pts[1][0] - 0.016, pts[1][1], pts[1][2]), (pts[1][0] + 0.016, pts[1][1], pts[1][2])], [lr * 1.5] * 2, "3")    # knee disc cover
                foot(x, st - 0.04, 0.0)

    n_lower = len(b.parts)                                         # every part after this is the upper body (torso, head, arms, weapons)

    # ---- torso: centre + two side torsos, seams between them
    z0 = hips_z + 0.035
    ztop = z0 + th
    cw = tw * 0.46
    sw = (tw - cw) / 2
    shape = model["torso"]
    tx, ty = {"box": (0.94, 0.9), "ovoid": (0.72, 0.72), "narrow": (1.22, 1.0), "slab": (1.0, 1.0), "canopy": (1.0, 1.0), "dome": (1.0, 1.0)}[shape]
    step = 0.03 if model["panels"] == "stepped" else 0.0
    flare = 1.12 if model["panels"] == "wings" else 1.0
    # PLAN (top view): "wedge" narrows to the front, "flare" widens to it, both drawn from the back
    fw = {"block": 1.0, "wedge": 0.70, "flare": 1.18, "arrow": 0.30, "oval": 1.0}[plan]
    pl = (fw, -td / 2, td / 2) if fw != 1.0 else None
    bulge = 0.2 if plan == "oval" else 0.0                         # an oval disc plan: widest in the middle, narrowing at both ends
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
                  "x_arm": tw * 0.5 + 0.052, "y_arm": -td * 0.02, "z_arm": zc + th * 0.06, "y_rear": -td * 0.40,
                  "visor": (0, td * 0.22, zc + th * 0.30)}
        tw_eff = tw
    elif shape == "dome":
        # ROUND DOME TORSO (chart re-read, 2026-11-03: Vindicator, Cataphract, Wolverine, Urbanmech, Archer,
        # Trebuchet): torso and head one broad rounded mass, seams between the three sections, the cockpit
        # glass on the front of the dome. One convex hull of two ellipsoids.
        zc = z0 + th * 0.5
        b.blob([((0, 0, zc), (tw * 0.5, td * 0.5, th * 0.55)), ((0, td * 0.06, zc + th * 0.06), (tw * 0.38, td * 0.46, th * 0.52))], "1")
        for fx in (-1, 1):
            b.box((fx * tw * 0.17, td * 0.04, zc + th * 0.12), (0.007, td * 0.74, th * 0.62), "1", vis={"front", "rear", "top"}, cls="ln")
        canopy = {"y_flank": td * 0.26, "z_flank": zc - th * 0.02, "y_nose": td * 0.44, "z_nose": zc - th * 0.04,
                  "x_arm": tw * 0.5 + 0.052, "y_arm": 0.0, "z_arm": zc + th * 0.10, "y_rear": -td * 0.46,
                  "visor": (0, td * 0.22, zc + th * 0.34)}
        tw_eff = tw
    else:
        # three sections, each the side profile extruded across its width (see PROFILES)
        if profile == "stepped":                                   # a low full-depth base and a smaller, set-back upper body
            b.extrude(0, z0, cw, td, th * 0.55, PROFILES["upright"], "1", wtop=tx, fw=fw)
            b.extrude(0, z0 + th * 0.55, cw * 0.92, td * 0.62, th * 0.45, PROFILES["upright"], "1", wtop=tx, fw=fw, cy=-td * 0.2)
        else:
            b.extrude(0, z0, cw, td, th + step, prof, "1", wtop=tx, fw=fw, bulge=bulge)
        for fx in (-1, 1):
            zone_t = "Left Torso" if fx < 0 else "Right Torso"
            sw_f = sw * slim(zone_t)                               # a thin side torso is narrower on that side only
            cxx = fx * (cw / 2 + sw_f / 2)
            if profile == "stepped":
                b.extrude(cxx, z0, sw_f, td * 0.96, th * 0.55, PROFILES["upright"], "2", wtop=tx * flare, fw=fw)
                b.extrude(cxx, z0 + th * 0.55, sw_f, td * 0.55, th * 0.45, PROFILES["upright"], "2", wtop=tx * flare, fw=fw, cy=-td * 0.2)
            else:
                b.extrude(cxx, z0, sw_f, td * 0.96, th * (1.06 if flare > 1 else 1.0), prof, "2", wtop=tx * flare, fw=fw, bulge=bulge)
            b.extrude(fx * cw / 2, z0 + th * 0.02, 0.006, td * 0.98, th * 0.96, prof, "1", fw=fw, vis={"front", "rear", "top"}, cls="ln")   # seam between the thirds
    ftop = 0.0

    # ---- head
    # COCKPIT SIZE: a cockpit weighs a fixed ~3 t, so it is a bigger share of a light 'Mech than of an
    # assault 'Mech: head and glass scale with the cube root of cockpit tons over total tons (1.0 at the
    # reference 3 t in 50 t; 1.36 at 20 t, 0.79 at 100 t, 0.64 at 200 t)
    hkf = max(0.55, min(1.5, (model.get("cockpit_tons", 3.0) / max(10.0, model["tons"])) ** (1 / 3) / (3.0 / 50.0) ** (1 / 3)))
    mount, shape_h = model["head_mount"], model["head_shape"]
    if shape in ("canopy", "dome"):
        mount = "built_in"                                          # the cockpit is the dome
    hoff = model["head_offset"] * tw * 0.16
    hs = slim("Head")
    if mount == "built_in" and canopy:                              # the glass sits on the dome of the nose
        b.box((canopy["visor"][0] + hoff, canopy["visor"][1], canopy["visor"][2]), (tw * 0.18 * hkf, td * 0.30 * hkf, 0.03), "4", tilt=-0.12, cls="hl")
    elif mount == "built_in":
        b.box((hoff, max(0.0, front_y(0.9)) * 0.5, ztop - 0.07), (0.09 * hkf, td * 0.5, 0.035), "4", vis={"front", "side"}, cls="hl")
    else:
        big = mount in ("full", "boom")
        hw_, hh_ = ((0.15, 0.115) if big else (0.105, 0.085))
        hw_, hh_ = hw_ * hs * hkf, hh_ * hs * hkf
        if mount == "boom":                                        # head in the centre torso, out front on a neck
            hz = ztop - 0.06
            hy = td / 2 + 0.12
            b.seg([(hoff, td / 4, hz), (hoff, hy - 0.04, hz)], [0.04, 0.035], "3")
        elif mount == "front":
            hz, hy = ztop - 0.03, front_y(0.95) + 0.005
        elif mount == "notch":                                     # seated in a notch at the top front of the torso, standing proud
            hz, hy = ztop + 0.005, front_y(0.95) - 0.035
        else:
            hz, hy = ztop + 0.035 + hh_ / 2, ftop * 0.7 + (td * 0.18 if profile == "hunch" else 0.0)
            b.seg([(hoff, hy, ztop - 0.01), (hoff, hy, ztop + 0.045)], [0.06 * hkf, 0.05 * hkf], "3")
        if shape_h == "skull":
            # SKULL HEAD (the Atlas only, from the Atlas kit study; named-unit tag, never from the hash): a
            # faceted dome, a brow ridge, two glowing eye slits, a nose bridge and a mask plate for the jaw
            b.blob([((hoff, hy, hz), (hw_ * 0.60, hw_ * 0.54, hh_ * 0.66))], "1")
            b.box((hoff, hy + hw_ * 0.40, hz + hh_ * 0.12), (hw_ * 0.98, 0.022, 0.018), "3", ch=0.004)
            for ex in (-1, 1):
                b.box((hoff + ex * hw_ * 0.22, hy + hw_ * 0.47, hz - hh_ * 0.02), (hw_ * 0.22, 0.006, hh_ * 0.16), "4", cls="hl")
            b.box((hoff, hy + hw_ * 0.42, hz - hh_ * 0.36), (hw_ * 0.58, 0.02, hh_ * 0.30), "3", ch=0.004)
            b.box((hoff, hy + hw_ * 0.49, hz - hh_ * 0.16), (hw_ * 0.10, 0.006, hh_ * 0.22), "1", cls="ln", ch=0.0)
        else:
            if shape_h == "dome":
                b.blob([((hoff, hy, hz), (hw_ * 0.52, hw_ * 0.46, hh_ * 0.58))], "1")
            else:                                                  # box / wedge / visor: the side profile extruded
                hprof = {"box": PROFILES["upright"], "wedge": PROFILES["prow"], "visor": PROFILES["sloped"]}[shape_h]
                b.extrude(hoff, hz - hh_ / 2, hw_, hw_ * 0.85, hh_, hprof, "1", wtop=0.85)
            b.box((hoff, hy + hw_ * 0.43 + 0.002, hz), (hw_ * (0.9 if shape_h == "visor" else 0.6), 0.004, 0.022), "4", vis={"front"}, cls="hl")
            b.box((hoff, hy + hw_ * 0.3, hz), (hw_ * 0.5, hw_ * 0.5, 0.02), "4", vis={"top"}, cls="hl")

    # ANTENNAS: one to three thin masts rising from the top of the torso, leaning slightly back
    n_ant = model.get("antennas") or (1 if model.get("antenna") else 0)
    for i in range(int(n_ant)):
        ax = (i - (n_ant - 1) / 2) * 0.055
        b.seg([(ax, -td * 0.10, ztop - 0.005), (ax, -td * 0.10 - 0.025, ztop + (0.13 if i % 2 == 0 else 0.17))], [0.006, 0.0035], "3")

    # SURFACE DETAIL (option surface = plated / smooth): vents across the lower front, bolts at the chest
    # corners and two panel lines along the top; thin dark or light parts laid on the real front face
    if model.get("surface") == "plated" and not canopy:
        nv = model.get("vents", 4)
        for i in range(nv):
            v = 0.14 + 0.085 * i
            b.box((0, front_y(v) + 0.0012, z0 + th * v), (cw * 0.62, 0.004, 0.007), "1", cls="ln", ch=0.0)
        for fxx in (-1, 1):
            for vv in (0.88, 0.5):
                b.box((fxx * cw * 0.40, front_y(vv) + 0.002, z0 + th * vv), (0.011, 0.005, 0.011), "4", ch=0.0)
            b.box((fxx * cw * 0.22, -td * 0.1, ztop + 0.0012), (0.005, td * 0.62, 0.003), "1", cls="ln", ch=0.0)

    # TEAM ACCENTS (class "tm": the viewer paints them in the team color): a chest stripe and plates on the shoulders
    if not canopy:
        b.box((0, front_y(0.80) + 0.0015, z0 + th * 0.80), (cw * 0.85, 0.004, 0.02), "1", cls="tm", ch=0.0)
        for fx in (-1, 1):
            b.box((fx * (cw / 2 + sw * slim("Left Torso" if fx < 0 else "Right Torso") / 2), -td * 0.15, ztop + 0.0012), (sw * 0.7, td * 0.4, 0.004), "1", cls="tm", ch=0.0)
    elif shape == "canopy":
        for fx in (-1, 1):
            bx_, by_, bz_, bw_, bd_, bh_ = bays[fx]
            b.box((bx_, by_ - bd_ * 0.22, bz_ + bh_ / 2 + 0.0015), (bw_ * 0.6, bd_ * 0.3, 0.004), "1", cls="tm", ch=0.0)

    # SHOULDER KITS (dictionary: shoulders / details): add-ons seen on the chart silhouettes
    for kit in [k_ for k_ in (model.get("kit") or "").split(",") if k_]:          # several kits may be named: "shoulder_guns,spar"
        htop = (tw * 0.36 if shape == "dome" else tw / 2) if canopy else tw_eff / 2 * tx * flare       # the torso's half-width at its top edge
        zk = ztop - 0.045 if shape == "dome" else ztop                # a dome is lower at its edges: kits sit on it, not above it
        for fx in (-1, 1):
            if kit == "corner_pods":                                  # box pods at the upper outer corners
                b.box((fx * (htop + 0.014), -td * 0.05, zk - 0.035), (0.05, td * 0.72, 0.13), "2", ch=0.014)
            elif kit == "fins":                                       # fins / horns swept outward and up from the shoulders
                b.seg([(fx * (htop - 0.01), -0.03, zk - 0.01), (fx * (htop + 0.10), -0.03, zk + 0.15)], [0.016, 0.008], "3")
            elif kit == "ears":                                       # tall box pods standing above the shoulders
                b.box((fx * (htop - 0.015), -0.01, zk + 0.10), (0.07, 0.10, 0.17), "2", tx=0.9, ch=0.012)
                b.box((fx * (htop - 0.015), -0.01, zk + 0.01), (0.04, 0.06, 0.05), "3")
            elif kit == "tall_launchers":                             # two tall upright launcher boxes at the back (Archer): a cell grid on the front face
                tcx, tcy, tw_, td_, th_ = fx * htop * 0.50, -td * 0.18, 0.085, 0.12, 0.27
                b.extrude(tcx, zk - 0.01, tw_, td_, th_, PROFILES["upright"], "2", wtop=0.95, cy=tcy)
                for rr in range(5):
                    for cc in range(3):
                        cxx_ = tcx + (cc - 1) * tw_ * 0.27
                        czz_ = zk - 0.01 + th_ * (0.12 + 0.18 * rr)
                        b.box((cxx_, tcy + td_ / 2 + 0.0015, czz_), (tw_ * 0.21, 0.004, th_ * 0.12), "1", tag="w", cls="wm")
                        b.box((cxx_, tcy + td_ / 2 + 0.003, czz_), (tw_ * 0.13, 0.004, th_ * 0.07), "1", tag="w", cls="ln")
            elif kit == "shoulder_guns":                              # gun pods on the shoulders with long twin barrels forward (JagerMech, Rifleman)
                gx = fx * (htop + 0.012)
                b.box((gx, 0.0, zk - 0.035), (0.05, 0.14, 0.07), "3", ch=0.008)
                for dd in (-1, 1):
                    b.barrel((gx + dd * 0.014, 0.05, zk - 0.035), 0.28 * b.k, 1.9, "wb")
                b.box((gx, 0.12, zk - 0.035), (0.062, 0.025, 0.084), "4", ch=0.004)                 # muzzle brake block
            elif kit == "launchers":                                  # huge slanted-top missile boxes on the shoulders (Mauler): a cell grid forward, a tall rear wing
                lcx, lcy, lw, ld, lh = fx * (htop - 0.005), -0.04, 0.115, 0.14, 0.21
                b.extrude(lcx, zk - 0.02, lw, ld, lh, PROFILES["sloped"], "2", wtop=0.95, cy=lcy)
                for rr in range(3):
                    vv = 0.20 + 0.25 * rr
                    fy_ = lcy + profile_span(PROFILES["sloped"], vv)[1] * ld / 2 + 0.0015
                    for cc in range(4):
                        cxx_ = lcx + (cc - 1.5) * lw * 0.21
                        b.box((cxx_, fy_, zk - 0.02 + lh * vv), (lw * 0.17, 0.004, lh * 0.15), "1", tag="w", cls="wm")
                        b.box((cxx_, fy_ + 0.0015, zk - 0.02 + lh * vv), (lw * 0.11, 0.004, lh * 0.09), "1", tag="w", cls="ln")
                b.box((fx * (htop + 0.03), -0.12, zk + 0.10), (0.012, 0.09, 0.25), "3", ch=0.004)
            elif kit == "round_blocks":                               # big rounded blocks where the arms start
                b.blob([((fx * (htop + 0.035), 0.0, zk - 0.07), (0.07, 0.075, 0.065))], "2")
            elif kit == "pauldrons":                                  # a faceted dome over each shoulder with a rim flange under it
                b.blob([((fx * (htop + 0.045), 0.0, zk - 0.01), (0.075, 0.075, 0.055))], "2")
                b.box((fx * (htop + 0.045), 0.0, zk - 0.058), (0.17, 0.17, 0.014), "3", ch=0.006)
            elif kit == "posts":                                      # tall slab posts at both shoulders
                b.box((fx * (htop + 0.004), -0.02, zk + 0.05), (0.03, 0.11, 0.22), "3", ch=0.01)
            elif kit == "humps":                                      # a hump over each shoulder, the head between them (three humps on top)
                b.blob([((fx * htop * 0.62, -0.01, zk + 0.01), (0.06, 0.08, 0.05))], "2")
            elif kit == "pylons":                                     # two tall pylons rising behind the shoulders (jump jets)
                b.box((fx * htop * 0.45, -td * 0.36, zk + 0.11), (0.024, 0.04, 0.23), "3", ch=0.006)
        if kit == "spar":                                             # a very wide thin bar across the shoulders, round pods at its ends
            b.box((0, -0.01, zk + 0.012), (htop * 2 + 0.34, 0.035, 0.022), "3", ch=0.006)
            for fx in (-1, 1):
                b.blob([((fx * (htop + 0.17), 0.0, zk - 0.01), (0.028, 0.03, 0.03))], "4")
        elif kit == "tail_fin":                                       # a raised fin at the rear of the hull (Raven): a tall swept fin and two small ones
            b.extrude(0, ztop - 0.01, 0.014, td * 0.36, 0.17, PROFILES["fin"], "3", cy=-td * 0.28)
            for fx in (-1, 1):
                b.extrude(fx * tw_eff * 0.30, ztop - 0.01, 0.010, td * 0.26, 0.08, PROFILES["fin"], "3", cy=-td * 0.30)
        elif kit == "grille":                                         # a recessed grille chest (Awesome): a frame and dark slats
            gy = front_y(0.55) + 0.0012
            b.box((0, gy, z0 + th * 0.55), (cw * 0.72, 0.004, th * 0.46), "4", ch=0.0)
            for gi in range(7):
                b.box((0, gy + 0.0022, z0 + th * (0.36 + 0.055 * gi)), (cw * 0.62, 0.003, th * 0.026), "1", cls="ln", ch=0.0)
        elif kit == "tent":                                           # a mast with three guy wires down to the shoulders and the head
            b.seg([(0, 0.0, zk), (0, 0.0, zk + 0.20)], [0.007, 0.005], "3")
            for tx_, ty_ in ((-htop, 0.0), (htop, 0.0), (0.0, td * 0.3)):
                b.seg([(0, 0.0, zk + 0.19), (tx_, ty_, zk)], [0.003, 0.003], "3")
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
        # The arm hangs OUTSIDE the torso: the torso's real half-width (taper and flare included) at the
        # shoulder and at the lowest point the arm reaches beside the torso, plus the arm's own half-width
        # (Daniel, 2026-11-03: JagerMech arms clipped into the torso).
        zt = "Left Torso" if fx < 0 else "Right Torso"
        half = cw / 2 + sw * slim(zt)
        vs, vl = min(1.0, (zs_ - z0) / th), max(0.0, min(1.0, (zs_ - 0.26 - z0) / th))
        top_k = tx * flare
        half_arm = max(half * (1 - (1 - top_k) * vs), half * (1 - (1 - top_k) * vl)) * (1 + (fw - 1) * 0.5)
        sx = fx * canopy["x_arm"] if canopy else fx * (half_arm + 0.058 + boom)
        b.seg([(fx * (canopy and tw_eff / 2 * 0.80 or half_arm * 0.92), ay, zs_), (sx, ay, zs_)], [0.038 * sl, 0.034 * sl], "3")           # connective tissue: torso edge to shoulder joint only
        b.blob([((sx, ay, zs_), (0.040, 0.046, 0.040))], "3")                                         # shoulder cap, not a ball
        small = bool(gs) and not any(x["big"] for x in gs)
        up = model.get("arms_up")
        astyle = model.get("arm_style", "")
        asz = 1.0 if not model.get("asym") else (1.32 if model["asym"] == name else 0.80)     # asymmetric arms: one bigger, one smaller
        if astyle == "shoulder_pod":
            kind = "pod"                                               # a gun pod on the shoulder instead of an arm (Rifleman)
        blen = 2.4 if astyle in ("long_barrel", "shoulder_pod") else 1.0   # long barrels pass the front of the body
        muz = None
        if kind == "pod" or (kind != "hand" and small and kind != "forearm"):               # upper actuator only: a turret
            n_w = max(1, sum(x["count"] for x in gs))
            pw = (0.05 + 0.014 * min(n_w, 4)) * asz
            pz = zs_ - 0.07 if not up else ztop + 0.08
            if astyle == "shoulder_pod":
                pz = zs_ + 0.03
            # POD ARM (block from the kit study): a lozenge - leaf-shaped in plan (narrows to the muzzle),
            # chamfered, with a raised spine on top and a stub underneath
            b.box((sx + fx * 0.012, ay + 0.03, pz), (pw * sl, 0.18, 0.10), "1", tx=0.85,
                  plan=(0.55, ay + 0.03 - 0.09, ay + 0.03 + 0.09, sx + fx * 0.012), ch=0.012)     # tapers about ITS OWN centre line
            b.box((sx + fx * 0.012, ay + 0.02, pz + 0.06), (pw * sl * 0.4, 0.14, 0.025), "3")
            b.box((sx + fx * 0.012, ay - 0.03, pz - 0.06), (pw * sl * 0.3, 0.05, 0.03), "3")
            muz = (sx + fx * 0.012, ay + 0.03 + 0.08, pz)
        else:
            if up:
                el, wr = (sx + fx * 0.02, ay + 0.02, zs_ + 0.12), (sx + fx * 0.01, ay + 0.04, zs_ + 0.24)
            elif astyle == "long_barrel":                                  # forearm raised and pointing forward
                el, wr = (sx + fx * 0.012, ay + 0.03, zs_ - 0.10), (sx + fx * 0.006, ay + 0.13, zs_ - 0.15)
            elif astyle == "claw":                                         # bowed outward and down, like a crab's claw
                el, wr = (sx + fx * 0.085, ay + 0.04, zs_ - 0.10), (sx + fx * 0.045, ay + 0.11, zs_ - 0.22)
            elif astyle == "a_frame":                                      # angled outward and down from the shoulder
                el, wr = (sx + fx * 0.07, ay + 0.02, zs_ - 0.11), (sx + fx * 0.15, ay + 0.04, zs_ - 0.21)
            elif astyle == "tiny":
                el, wr = (sx + fx * 0.008, ay + 0.015, zs_ - 0.07), (sx + fx * 0.004, ay + 0.045, zs_ - 0.13)
            else:
                el, wr = (sx + fx * 0.012, ay + 0.02, zs_ - 0.13), (sx + fx * 0.006, ay + 0.075, zs_ - 0.25)
            w1 = (0.042 if kind == "hand" else 0.037) * sl * (0.62 if astyle == "tiny" else 1.0) * asz
            b.seg([(sx, ay, zs_), el, wr], [w1 * 1.3, w1 * 1.1, w1], "2")
            b.box(((el[0] + wr[0]) / 2 + fx * w1 * 1.0, (el[1] + wr[1]) / 2, (el[2] + wr[2]) / 2), (0.004, 0.005, abs(el[2] - wr[2]) * 0.55), "1", cls="ln", ch=0.0)   # forearm panel line
            b.ball(el, w1 * 1.15, "2")
            hstyle = model.get("hands") or ("ball" if astyle == "ball" else "")
            if hstyle == "pincer":                                         # two jaws and a palm: a pincer
                for jd in (-1, 1):
                    b.box((wr[0] + jd * 0.024, wr[1] + 0.045, wr[2] - 0.03), (0.016, 0.085, 0.045), "3", ch=0.004)
                    b.box((wr[0] + jd * 0.014, wr[1] + 0.095, wr[2] - 0.03), (0.012, 0.03, 0.04), "4", ch=0.003)     # the jaw tips, angled in
                b.box((wr[0], wr[1] + 0.008, wr[2] - 0.03), (0.06, 0.035, 0.06), "4", ch=0.006)
            elif hstyle == "ball":                                         # a huge round ball fist
                b.blob([((wr[0], wr[1] + 0.01, wr[2] - 0.035), (0.075, 0.075, 0.075))], "2")
            elif kind == "hand":
                hz_ = wr[2] - (0.03 if not up else -0.03)
                b.box((wr[0], wr[1] + 0.012, hz_), (0.05, 0.04, 0.055), "4", ch=0.006)                      # palm
                for fi in (-1, 0, 1):                                                                       # three finger plates
                    b.box((wr[0], wr[1] + 0.04, hz_ + fi * 0.017), (0.046, 0.022, 0.014), "3", ch=0.002)
                b.box((wr[0] - fx * 0.03, wr[1] + 0.03, hz_ + 0.012), (0.012, 0.03, 0.018), "3", ch=0.002)  # thumb
            muz = (wr[0], wr[1] + 0.03, wr[2])
        for gr in gs:                                          # weapons in line with the forearm / pod
            if gr["cls"] == "missile":
                _pod(b, (muz[0], muz[1] - 0.01, muz[2] - 0.06), gr["tubes"])
            else:
                nn = min(gr["count"], 3)
                for i in range(nn):
                    dx = (i - (nn - 1) / 2) * b.px(5) * f
                    weapon_barrel(b, (muz[0] + dx / f, muz[1], muz[2]), gr,
                                  blen * (22 if (gr["big"] and gr["cls"] == "ballistic") else 12 if gr["cls"] == "ballistic" else 7),
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
                fy = canopy["y_flank"] if canopy else front_y(0.62) + 0.002
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
            b.box(((i - (min(gr["count"], 4) - 1) / 2) * b.px(6), front_y(0.3) + 0.002, z0 + th * 0.3),
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
            b.box((x, y, z), (0.034, 0.045, 0.05), "4", tx=1.3, ty=1.3, ch=0.006)                          # nozzle: wider at the mouth
            b.box((x, y - 0.024, z - 0.018), (0.02, 0.004, 0.02), "4", cls="hl", ch=0.0)                  # glow
    if model.get("crouch"):                                        # a crouch pitches the whole upper body forward about the hips
        psi = math.radians(20)
        zp = z0                                                    # the hip pivot (belly of the torso)
        cps, sps = math.cos(psi), math.sin(psi)
        for part in b.parts[n_lower:]:
            part["groups"] = [[((p[0], p[1] * cps + (p[2] - zp) * sps, zp - p[1] * sps + (p[2] - zp) * cps), r) for p, r in grp] for grp in part["groups"]]
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
    f = _mass_factor(model) * (0.90 + 0.24 * min(model["tons"], 100) / 100.0)     # width follows the weight class (chart W/H 0.63 .. 0.81)
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
