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

LEVEL = 60                     # px for one level of height in every drawing
OVERRIDES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "token_overrides.json")

ARCHETYPES = ("humanoid", "humanoid", "bird", "dog", "lizard", "martian")

ZONES = ("Left Arm", "Right Arm", "Left Torso", "Right Torso", "Center Torso", "Head")
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
    unit = {"weapons": [], "slots": {}, "jets": 0}
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
        key = "" if not sep else key if key.endswith(" Armor") else key.lower()      # the files mix "Mass:" and "mass:"
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
        elif key.endswith(" Armor") and key.split()[0].isupper() and not key.startswith("R"):
            unit["armor"] = unit.get("armor", 0) + (int(val) if val.strip().isdigit() else 0)
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


def mount_style(zone, cls, big, n_zone, classes_in_zone, hands, archetype):
    """Pick how a weapon group is drawn from its zone, class and size.
    Daniel's style rule (2026-10-31): units with hands seldom carry over-the-shoulder
    weapons, so they get flank mounts; dogs and lizards carry hip pods. The files
    do not say this (hands do not predict torso weapons): it is art."""
    arm = zone.endswith("Arm")
    side = zone in ("Left Torso", "Right Torso")
    if arm:
        return "arm_rack" if cls == "missile" else "arm_barrel" if cls == "ballistic" else "arm_port"
    if side:
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


FEATURE_KEYS = ("archetype", "torso", "panels", "head_mount", "head_shape", "shoulders", "antenna", "arms_flex")


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

    # armor per ton against a typical 3.0: a bulk hint (armor and loadout add bulk)
    armor_ratio = unit["armor"] / max(tons, 1) / 3.0 if unit["armor"] else 1.0
    bulk = max(0.96, min(1.08, 0.97 + 0.06 * armor_ratio))

    arche = ARCHETYPES[hc[0] % len(ARCHETYPES)]
    if quad:
        arche = ("dog", "lizard")[hc[0] % 2]
    elif "Tripod" in config:
        arche = "martian"
    model = {
        "name": f'{unit.get("chassis", "?")} {unit.get("model", "")}'.strip(),
        "chassis": chassis, "tons": tons, "config": config, "quad": quad, "tripod": "Tripod" in config,
        "rules_levels": rules_levels(tons), "drawn_levels": round(drawn_levels(tons), 3),
        "bulk": round(bulk, 3),
        "archetype": arche,
        "torso": ("box", "ovoid", "narrow", "slab")[hc[1] % 4],
        "panels": ("flush", "wings", "stepped")[hc[5] % 3],
        "head_mount": ("built_in", "front", "top", "full")[hc[2] % 4],
        "head_shape": ("box", "dome", "wedge", "visor")[hc[4] % 4],
        "shoulders": ("flush", "boom")[hc[6] % 2],
        "antenna": hc[7] % 3 == 0,
        "jets": min(unit["jets"], 6),
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
    per_zone = {}
    for (zone, cls), g in groups.items():
        per_zone.setdefault(zone, []).append(g)
    for zone, gs in per_zone.items():
        n_zone = sum(g["count"] for g in gs)
        for g in gs:
            g["mount"] = mount_style(zone, g["cls"], g["big"], n_zone, {x["cls"] for x in gs}, hands, arche)
    model["hardpoints"] = [g for gs in per_zone.values() for g in gs]
    # a large weapon in a side torso pushes the head to the other side (Daniel)
    big_side = [z for z in ("Left Torso", "Right Torso") for g in per_zone.get(z, []) if g["big"]]
    model["head_offset"] = 0 if len(big_side) != 1 else (1 if big_side[0] == "Left Torso" else -1)   # figure's right = +1

    return model


# --------------------------------------------------------------------- drawing
# Figure frame: the figure's RIGHT is +1. Views: front (viewer faces the figure, so
# the figure's right is on the viewer's LEFT), rear (same side as the figure),
# top (facing up, same side), side (facing right, the figure's left is near).
# Weapons are drawn at ABSOLUTE pixel sizes (g.px), so they look larger on a small
# 'Mech and the same in every view.

class G:
    """A tiny SVG builder in a raw frame (y up). `ymax` is the top of the figure."""

    def __init__(self):
        self.items, self.ymax, self.xmax = [], 0.0, 0.0

    def _top(self, y, x=0.0):
        self.ymax = max(self.ymax, y)
        self.xmax = max(self.xmax, abs(x))

    def rect(self, x, y, w, h, c):
        self._top(y + h, max(abs(x), abs(x + w)))
        self.items.append(f'<rect x="{x:.4f}" y="{y:.4f}" width="{w:.4f}" height="{h:.4f}" class="{c}"/>')

    def ell(self, cx, cy, rx, ry, c):
        self._top(cy + ry, abs(cx) + rx)
        self.items.append(f'<ellipse cx="{cx:.4f}" cy="{cy:.4f}" rx="{rx:.4f}" ry="{ry:.4f}" class="{c}"/>')

    def poly(self, pts, c):
        self._top(max(p[1] for p in pts), max(abs(p[0]) for p in pts))
        s = " ".join(f"{x:.4f},{y:.4f}" for x, y in pts)
        self.items.append(f'<polygon points="{s}" class="{c}"/>')

    def svg(self, height_px, extra=""):
        k = height_px / self.ymax
        return f'<g transform="scale({k:.4f},{-k:.4f})">{"".join(self.items)}</g>{extra}'


ARCH = {   # leg_h, torso_h, tw (width), td (depth), leg_w, hip (half spacing), lean, splay, kind
    "humanoid": dict(leg_h=.44, torso_h=.32, tw=.34, td=.22, leg_w=.075, hip=.085, lean=.04, splay=.00, kind="straight"),
    "bird":     dict(leg_h=.50, torso_h=.27, tw=.28, td=.30, leg_w=.060, hip=.075, lean=.11, splay=.01, kind="reverse"),
    "dog":      dict(leg_h=.36, torso_h=.26, tw=.30, td=.40, leg_w=.070, hip=.090, lean=.20, splay=.02, kind="reverse"),
    "lizard":   dict(leg_h=.30, torso_h=.27, tw=.34, td=.38, leg_w=.085, hip=.140, lean=.06, splay=.09, kind="bent"),
    "martian":  dict(leg_h=.58, torso_h=.27, tw=.32, td=.28, leg_w=.058, hip=.095, lean=.00, splay=.02, kind="straight"),
}
WCLS = {"energy": "we", "ballistic": "wb", "missile": "wm"}
SIDE = {"Left": -1, "Right": 1}                      # figure-frame sign of each arm / torso


def _dims(model):
    a = dict(ARCH[model["archetype"]])
    wf = (0.92 + 0.14 * min(model["tons"], 100) / 100.0) * model["bulk"]
    for k in ("tw", "leg_w", "hip"):
        a[k] *= wf
    a["tw"] *= 1.12
    a["leg_w"] *= 1.35
    a["tw"] *= {"box": 1.0, "ovoid": 0.95, "narrow": 0.82, "slab": 1.12}[model["torso"]]
    a["y0"] = a["leg_h"] - 0.03
    a["ytop"] = a["y0"] + a["torso_h"]
    return a


def _vx(view, fx):
    """Figure-frame x to the drawing's x for a view."""
    return -fx if view == "front" else fx


class Canvas(G):
    def __init__(self, k=100.0):
        super().__init__()
        self.k = k

    def px(self, v):
        return v / self.k

    def limb(self, pts, widths, c):
        """A tapered limb through `pts` with a width at each point (a polygon strip)."""
        left, right = [], []
        for i, (x, y) in enumerate(pts):
            x0, y0 = pts[max(i - 1, 0)]
            x1, y1 = pts[min(i + 1, len(pts) - 1)]
            dx, dy = x1 - x0, y1 - y0
            n = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / n, dx / n
            w = widths[i] / 2
            left.append((x + nx * w, y + ny * w))
            right.append((x - nx * w, y - ny * w))
        self.poly(left + right[::-1], c)
        for (x, y), w in zip(pts[1:-1], widths[1:-1]):             # joint caps (knees, elbows)
            self.ell(x, y, w * 0.62, w * 0.62, c)

    def port(self, x, y, cls, big):
        r = self.px((1.5 if cls == "energy" else 2.2) + (1.2 if big else 0))
        if cls == "ballistic":
            self.ell(x, y, r + self.px(1.1), r + self.px(1.1), "g")
        self.ell(x, y, r, r, WCLS[cls])

    def pod(self, cx, cy, tubes, cls="missile"):
        """A missile pod: a box of cells, one cell per tube up to 24 (reads as salvo size)."""
        n = max(2, min(tubes, 24))
        cols = max(2, math.ceil(math.sqrt(n)))
        rows = math.ceil(n / cols)
        cell = self.px(3.2)
        w, h = cols * cell + self.px(1.6), rows * cell + self.px(1.6)
        self.rect(cx - w / 2, cy - h / 2, w, h, "g")
        for i in range(n):
            r, c = divmod(i, cols)
            self.ell(cx + (c - (cols - 1) / 2) * cell, cy + ((rows - 1) / 2 - r) * cell, cell * 0.36, cell * 0.36, "wm")
        return w, h


def _leg_pts(d, kind, fx, stance=0.0, side=False):
    """Hip, knee, ankle(, toe) of one leg. Front: straight down with a knee. Side: the pose."""
    lh = d["leg_h"]
    if not side:
        sp = d["splay"]
        return [(fx * d["hip"], lh), (fx * (d["hip"] + sp * 0.7), lh * 0.5), (fx * (d["hip"] + sp), 0.03)]
    if kind == "reverse":                                    # bird / dog: hock points back, foot forward
        return [(0, lh), (-0.08 + stance * 0.4, lh * 0.50), (0.04 + stance, lh * 0.20), (0.05 + stance, 0.02)]
    if kind == "bent":                                       # lizard: knee out front
        return [(0, lh), (0.09 + stance * 0.4, lh * 0.55), (0.01 + stance, 0.03)]
    return [(0, lh), (0.03 + stance * 0.5, lh * 0.5), (stance, 0.03)]


def _torso_front(g, model, d, view):
    tw, y0, th = d["tw"], d["y0"], d["torso_h"]
    panels, shape = model["panels"], model["torso"]
    cw = tw * 0.46
    step = 0.04 if panels == "stepped" else 0.0
    ch = th * (0.30 if shape == "ovoid" else 0.10)
    g.poly([(-cw / 2, y0), (cw / 2, y0), (cw / 2, y0 + th + step - ch), (cw / 2 - ch, y0 + th + step),
            (-cw / 2 + ch, y0 + th + step), (-cw / 2, y0 + th + step - ch)], "f")
    for sg in (-1, 1):                                       # the two side torsos
        xi, xo = sg * cw / 2 - sg * 0.004, sg * tw / 2
        bot = 0.0 if shape != "narrow" else 0.35 * (tw - cw) / 2
        topc = (tw - cw) / 2 * (0.5 if panels == "wings" else 0.25 if shape == "ovoid" else 0.0)
        tt = y0 + th - (0.02 if panels == "wings" else 0.0)
        g.poly([(xi, y0 + 0.005), (xo - sg * bot, y0 + 0.005), (xo, y0 + th * 0.35), (xo - sg * topc, tt), (xi, tt)], "g" if panels == "stepped" else "f")


def _head_front(g, model, d, view):
    mount, shape = model["head_mount"], model["head_shape"]
    yt = d["ytop"]
    off = _vx(view, model["head_offset"]) * d["tw"] * 0.16
    if mount == "built_in":
        if view != "rear":
            g.rect(off - 0.045, yt - 0.075, 0.09, 0.04, "hl")
        return
    big = mount == "full"
    hw, hh = (0.15, 0.115) if big else (0.105, 0.085)
    cy = yt + (hh / 2 + 0.03 if mount != "front" else hh / 2 - 0.012)
    if mount != "front":
        g.rect(off - 0.022, yt - 0.01, 0.044, 0.04, "g")     # neck
    if shape == "dome":
        g.ell(off, cy, hw / 2, hh / 2, "f")
    elif shape == "wedge":
        g.poly([(off - hw / 2, cy - hh / 2), (off + hw / 2, cy - hh / 2), (off + hw * 0.32, cy + hh / 2), (off - hw * 0.32, cy + hh / 2)], "f")
    else:
        g.rect(off - hw / 2, cy - hh / 2, hw, hh, "f")
    if view != "rear":
        g.rect(off - hw * (0.42 if shape == "visor" else 0.3), cy - 0.004, hw * (0.84 if shape == "visor" else 0.6), 0.02, "hl")
    if model.get("antenna"):
        g.rect(off + hw * 0.3, cy + hh / 2, 0.008, 0.07, "g")


def _jets(g, model, d, view):
    n = model["jets"]
    for i in range(n):
        sg = -1 if i % 2 == 0 else 1
        row = i // 2
        x = sg * d["tw"] * 0.30
        g.rect(x - 0.018, d["y0"] + 0.02 + row * 0.06, 0.036, 0.05, "hl")


def _arm_front(g, model, d, view, name):
    kind = (model["arms"] or {})[name[0]]
    fx = SIDE["Left" if name == "L" else "Right"]
    sx = _vx(view, fx) * (d["tw"] / 2 + 0.01)
    sg = 1 if sx >= 0 else -1
    sy = d["ytop"] - 0.05
    boom = 0.05 if model["shoulders"] == "boom" else 0.0
    if boom:
        g.rect(min(sx, sx + sg * boom), sy - 0.03, boom, 0.06, "f")
    ex = sx + sg * (boom + 0.025)
    zone = "Left Arm" if name == "L" else "Right Arm"
    gs = _groups(model, zone)
    n_w = sum(x["count"] for x in gs)
    small = n_w and not any(x["big"] for x in gs)
    if kind == "pod" or (kind != "hand" and small):          # a weapon-pod arm: stub, then a pod
        pw = 0.05 + 0.012 * min(n_w, 4) + (0.025 if any(x["big"] for x in gs) else 0)
        g.limb([(ex, sy), (ex + sg * 0.01, sy - 0.10)], [0.06, 0.055], "g")
        g.rect(ex + sg * 0.01 - pw / 2, sy - 0.24, pw, 0.15, "f")
        by = sy - 0.24 + 0.02
    else:
        wid = 0.08 if kind == "hand" else 0.07
        g.limb([(ex, sy), (ex + sg * 0.02, sy - 0.17), (ex + sg * 0.01, sy - 0.33)], [wid * 1.2, wid, wid * 0.9], "g")
        if kind == "hand":
            g.rect(ex + sg * 0.01 - 0.03, sy - 0.375, 0.06, 0.05, "f")
        by = sy - 0.30
    g.ell(sx, sy, 0.034, 0.034, "f")                          # shoulder joint
    if view == "rear":
        return
    xx = ex + sg * 0.01
    for gr in gs:
        if gr["cls"] == "missile":
            g.pod(xx, by + 0.03, gr["tubes"], "missile")
        else:
            for i in range(min(gr["count"], 3)):
                g.port(xx + (i - (min(gr["count"], 3) - 1) / 2) * g.px(5), by, gr["cls"], gr["big"])


def _flank_front(g, model, d, view, name):
    """Torso-zone weapons: shoulder rack / barrel / turret, flank mounts, or hip pods."""
    fx = SIDE["Left" if name == "L" else "Right"]
    zone = "Left Torso" if name == "L" else "Right Torso"
    x = _vx(view, fx) * d["tw"] * 0.34
    yt, y0, th = d["ytop"], d["y0"], d["torso_h"]
    for gr in _groups(model, zone):
        m, c, n = gr["mount"], gr["cls"], gr["count"]
        if m == "shoulder_rack":
            w, h = g.pod(x, yt + 0.045, gr["tubes"])
        elif m == "shoulder_barrel":
            g.rect(x - g.px(4), yt - 0.01, g.px(8), 0.05, "g")
            g.port(x, yt + 0.04, "ballistic", True)
        elif m == "turret":
            g.ell(x, yt + 0.03, 0.075, 0.04, "g")
            for i in range(min(n, 4)):
                g.port(x + (i - (min(n, 4) - 1) / 2) * g.px(5), yt + 0.03, c, gr["big"])
        elif m == "hip_pod":
            if c == "missile":
                g.pod(_vx(view, fx) * (d["tw"] / 2 + 0.03), y0 + 0.02, gr["tubes"])
            else:
                g.rect(_vx(view, fx) * (d["tw"] / 2 + 0.01) - g.px(4), y0 - 0.02, g.px(8), 0.07, "g")
                g.port(_vx(view, fx) * (d["tw"] / 2 + 0.01), y0 + 0.02, c, gr["big"])
        else:                                                  # flank mounts, on the torso face
            if view == "rear":
                continue
            if c == "missile":
                g.pod(x, y0 + th * 0.55, gr["tubes"])
            else:
                for i in range(min(n, 3)):
                    g.port(x, y0 + th * 0.78 - i * g.px(5), c, gr["big"])
    if name == "L":
        for gr in _groups(model, "Center Torso"):
            if view != "rear":
                for i in range(min(gr["count"], 4)):
                    g.port((i - (min(gr["count"], 4) - 1) / 2) * g.px(6), y0 + th * 0.3, gr["cls"], gr["big"])


def _legs(g, model, d, view):
    kind = d["kind"]
    lw = d["leg_w"]
    for fx in (-1, 1):
        pts = _leg_pts(d, kind, _vx(view, fx))
        g.limb(pts, [lw * 1.1, lw * 0.85, lw * 0.8], "g")
        g.rect(pts[-1][0] - lw * 0.9, 0, lw * 1.8, 0.035, "f")
    if model["quad"]:
        for fx in (-1, 1):
            x = _vx(view, fx) * (d["hip"] * 1.8)
            g.limb([(x, d["leg_h"] * 0.9), (x, 0.03)], [lw, lw * 0.8], "g")
    if model["tripod"]:
        g.limb([(0, d["leg_h"] * 0.8), (0, 0.03)], [lw, lw * 0.8], "g")


def _figure_front(model, height_px, rear=False):
    view = "rear" if rear else "front"
    d = _dims(model)
    if model["quad"]:
        d["tw"] *= 1.4
    k = 100.0
    for _ in range(3):                                         # the sizes need k, k needs the height
        g = Canvas(k)
        _legs(g, model, d, view)
        _torso_front(g, model, d, view)
        if not model["quad"]:
            for n in ("L", "R"):
                _arm_front(g, model, d, view, n)
        _flank_front(g, model, d, view, "L")
        _flank_front(g, model, d, view, "R")
        _head_front(g, model, d, view)
        if rear:
            _jets(g, model, d, view)
        k = height_px / g.ymax
    return g.svg(height_px)


def _frame(model, inner, kind):
    """Wrap a drawing in the standee: a card of the RULES height on a base."""
    rl = model["rules_levels"]
    ch = rl * LEVEL
    cw = 40 * rl
    card = (f'<rect x="{-cw / 2}" y="{-ch}" width="{cw}" height="{ch}" class="card"/>'
            f'<line x1="{-cw / 2}" x2="{cw / 2}" y1="{-LEVEL}" y2="{-LEVEL}" class="lvl"/>')
    if rl >= 3:
        card += f'<line x1="{-cw / 2}" x2="{cw / 2}" y1="{-2 * LEVEL}" y2="{-2 * LEVEL}" class="lvl"/>'
    base = f'<ellipse cx="0" cy="3" rx="{cw * 0.42}" ry="6" class="base"/>'
    return (f'<svg class="{kind}" viewBox="-85 {-3 * LEVEL - 6} 170 {3 * LEVEL + 18}" '
            f'width="170" height="{3 * LEVEL + 18}" role="img" aria-label="{model["name"]} {kind}">'
            f'{base}{card}{inner}</svg>')


def card_svg(model):
    return _frame(model, _figure_front(model, model["drawn_levels"] * LEVEL), "front")


def rear_svg(model):
    return _frame(model, _figure_front(model, model["drawn_levels"] * LEVEL, rear=True), "rear")


def _groups(model, zone):
    return [g for g in model["hardpoints"] if g["zone"] == zone]


def side_svg(model):
    """Side view (facing right, the figure's left side near): the limbs mid-step, the
    torso balanced over the feet."""
    d = _dims(model)
    height_px = model["drawn_levels"] * LEVEL
    kind, lw = d["kind"], d["leg_w"]
    td = d["td"] * (1.0 if not model["quad"] else 1.9)
    y0, th, lean = d["y0"], d["torso_h"], d["lean"] * d["torso_h"]
    k = 100.0
    for _ in range(3):
        g = Canvas(k)
        pairs = [(0.0, 0.0)] if not model["quad"] else [(0.55 * td, 0.0), (-0.55 * td, 0.0)]
        for hx, _o in pairs:                                    # far leg (back), then near leg (forward)
            for stance, cls in ((-0.06, "g"), (0.06, "f")):
                pts = [(x + hx, y) for x, y in _leg_pts(d, kind, 1, stance, side=True)]
                g.limb(pts, [lw * 1.3] + [lw] * (len(pts) - 2) + [lw * 0.8], cls)
                tx = pts[-1][0]
                g.poly([(tx - lw * 0.7, 0), (tx + 0.10, 0), (tx + 0.08, 0.035), (tx - lw * 0.7, 0.04)], "f")
        if model["tripod"]:
            g.limb([(-0.14, d["leg_h"] * 0.85), (-0.17, 0.03)], [lw, lw * 0.8], "g")
        cx0, cx1 = -lean * 0.5 - td * 0.0, lean * 0.5            # torso centred so its mass stays over the feet
        g.poly([(cx0 - td / 2, y0), (cx0 + td / 2, y0), (cx1 + td / 2, y0 + th), (cx1 - td / 2, y0 + th)], "f")
        for i in range(model["jets"]):
            row = i // 2
            g.rect(cx0 - td / 2 - 0.035, y0 + 0.02 + row * 0.06, 0.04, 0.05, "hl")
        yt = d["ytop"]
        mount = model["head_mount"]
        if mount != "built_in":
            big = mount == "full"
            hh = 0.115 if big else 0.085
            hw = 0.15 if big else 0.105
            cy = yt + (hh / 2 + 0.03 if mount != "front" else hh / 2 - 0.012)
            hx = cx1 + td * 0.12
            if mount != "front":
                g.rect(hx - 0.022, yt - 0.01, 0.044, 0.04, "g")
            g.rect(hx - hw * 0.45, cy - hh / 2, hw, hh, "f")
            g.rect(hx + hw * 0.1, cy - 0.004, hw * 0.4, 0.02, "hl")
        # the near (left) arm: shoulder, elbow, hand, bent forward
        kindA = (model["arms"] or {}).get("L", "hand") if not model["quad"] else None
        sx, sy = cx1 + td * 0.05, yt - 0.05
        if kindA:
            gs = _groups(model, "Left Arm")
            pod = kindA == "pod" or (kindA != "hand" and gs and not any(x["big"] for x in gs))
            if pod:
                g.limb([(sx, sy), (sx + 0.03, sy - 0.10)], [0.045, 0.04], "g")
                pl = 0.07 + 0.015 * min(sum(x["count"] for x in gs), 4)
                g.rect(sx + 0.03 - 0.04, sy - 0.24, pl, 0.15, "f")
                ax, ay = sx + 0.03 - 0.04 + pl, sy - 0.17
            else:
                g.limb([(sx, sy), (sx + 0.03, sy - 0.15), (sx + 0.10, sy - 0.26)], [0.09, 0.075, 0.065], "g")
                if kindA == "hand":
                    g.ell(sx + 0.11, sy - 0.275, 0.032, 0.032, "f")
                ax, ay = sx + 0.12, sy - 0.26
            for gr in gs:
                ln = 22 if (gr["big"] and gr["cls"] == "ballistic") else 12 if gr["cls"] != "energy" else 7
                t = g.px(2.4 + (1.6 if gr["big"] else 0))
                if gr["cls"] == "missile":
                    g.rect(ax - 0.02, ay - g.px(5), g.px(16), g.px(10), "wm")
                else:
                    for i in range(min(gr["count"], 3)):
                        g.rect(ax, ay + g.px(2) * (1 - 2 * i) * 1.2, g.px(ln), t, WCLS[gr["cls"]])
        # torso-zone weapons, near side
        for gr in _groups(model, "Left Torso"):
            m, c = gr["mount"], gr["cls"]
            if m in ("shoulder_rack", "turret"):
                g.pod(cx1, yt + 0.045, gr["tubes"]) if c == "missile" else g.ell(cx1, yt + 0.03, 0.075, 0.04, "g")
            elif m == "shoulder_barrel":
                g.rect(cx1 - 0.03, yt + 0.02, g.px(24), g.px(4), "wb")
            elif m == "hip_pod":
                g.pod(cx0 + td * 0.1, y0 + 0.02, gr["tubes"]) if c == "missile" else g.rect(cx0, y0 - 0.01, g.px(14), g.px(5), WCLS[c])
            else:
                g.pod(cx0, y0 + th * 0.5, gr["tubes"]) if c == "missile" else g.rect(cx0 + td * 0.2, y0 + th * 0.7, g.px(10), g.px(3), WCLS[c])
        k = height_px / g.ymax
    return _frame_side(model, g.svg(height_px))


def _frame_side(model, inner):
    rl, ch = model["rules_levels"], model["rules_levels"] * LEVEL
    card = (f'<rect x="-58" y="{-ch}" width="116" height="{ch}" class="card"/>'
            f'<line x1="-58" x2="58" y1="{-LEVEL}" y2="{-LEVEL}" class="lvl"/>')
    if rl >= 3:
        card += f'<line x1="-58" x2="58" y1="{-2 * LEVEL}" y2="{-2 * LEVEL}" class="lvl"/>'
    return (f'<svg class="side" viewBox="-85 {-3 * LEVEL - 6} 170 {3 * LEVEL + 18}" width="170" '
            f'height="{3 * LEVEL + 18}" role="img" aria-label="{model["name"]} side">'
            f'<ellipse cx="0" cy="3" rx="50" ry="6" class="base"/>{card}{inner}</svg>')


def top_svg(model):
    """Top-down token on a flat-topped hex, facing up. Weapons point forward, the
    figure's right is +x (the same sides as the rear view)."""
    R = 52
    d = _dims(model)
    s = (model["tons"] / 100.0) ** (1.0 / 3.0)
    sc = R * 1.55 * s                                           # raw -> px for this token
    tw, td = d["tw"] * sc, d["td"] * sc * (1.9 if model["quad"] else 1.0) * 1.15
    hexp = " ".join(f"{R * math.cos(math.radians(a)):.1f},{R * math.sin(math.radians(a)):.1f}" for a in range(0, 360, 60))
    out = [f'<polygon points="{hexp}" class="hex"/>']
    lw = d["leg_w"] * sc
    for fx in (-1, 1):                                          # feet peek out under the torso
        out.append(f'<rect x="{fx * d["hip"] * sc - lw:.1f}" y="{td * 0.15:.1f}" width="{lw * 2:.1f}" height="{td * 0.5:.1f}" rx="2" class="g"/>')
    arms = model["arms"] or {"L": "none", "R": "none"}
    for name, fx in (("L", -1), ("R", 1)):
        kind = arms[name]
        zone = "Left Arm" if name == "L" else "Right Arm"
        gs = _groups(model, zone)
        pod = kind == "pod" or (kind not in ("hand", "none") and gs and not any(x["big"] for x in gs))
        aw = (0.06 + 0.012 * min(sum(x["count"] for x in gs), 4)) * sc if pod else 0.062 * sc
        x = fx * (tw / 2 + aw * 0.4)
        out.append(f'<rect x="{x - aw / 2:.1f}" y="{-td * 0.35:.1f}" width="{aw:.1f}" height="{td * 0.8:.1f}" rx="2" class="g"/>')
        for gr in gs:
            L = 22 if (gr["big"] and gr["cls"] == "ballistic") else 11 if gr["cls"] != "energy" else 6
            if gr["cls"] == "missile":
                out.append(f'<rect x="{x - 5:.1f}" y="{-td * 0.35 - 8:.1f}" width="10" height="9" class="wm"/>')
            else:
                for i in range(min(gr["count"], 3)):
                    bx = x + (i - (min(gr["count"], 3) - 1) / 2) * 5
                    out.append(f'<rect x="{bx - 1.2:.1f}" y="{-td * 0.35 - L:.1f}" width="{2.4 + (1.6 if gr["big"] else 0):.1f}" height="{L:.1f}" class="{WCLS[gr["cls"]]}"/>')
    out.append(f'<rect x="{-tw / 2:.1f}" y="{-td / 2:.1f}" width="{tw:.1f}" height="{td:.1f}" rx="{(9 if model["torso"] == "ovoid" else 3)}" class="f"/>')
    for name, fx in (("L", -1), ("R", 1)):
        zone = "Left Torso" if name == "L" else "Right Torso"
        for gr in _groups(model, zone):
            m, c = gr["mount"], gr["cls"]
            x = fx * tw * 0.3
            if c == "missile":
                out.append(f'<rect x="{x - 6:.1f}" y="{-td * 0.45:.1f}" width="12" height="{min(18, 6 + gr["tubes"] * 0.5):.1f}" class="wm"/>')
            else:
                L = 20 if (gr["big"] and c == "ballistic") else 9
                out.append(f'<rect x="{x - 1.6:.1f}" y="{-td / 2 - L:.1f}" width="{3.2 + (1.6 if gr["big"] else 0):.1f}" height="{L + td * 0.25:.1f}" class="{WCLS[c]}"/>')
    for i in range(model["jets"]):                              # jump jets at the back
        out.append(f'<rect x="{(-1 if i % 2 == 0 else 1) * tw * 0.3 - 2.5:.1f}" y="{td / 2 - 3 - (i // 2) * 0:.1f}" width="5" height="4" class="hl"/>')
    if model["head_mount"] != "built_in":
        hx = model["head_offset"] * tw * 0.16
        r = R * (0.12 if model["head_mount"] == "full" else 0.09)
        out.append(f'<circle cx="{hx:.1f}" cy="{-td * 0.30:.1f}" r="{r:.1f}" class="g"/>')
        out.append(f'<rect x="{hx - r * 0.6:.1f}" y="{-td * 0.30 - r * 0.9:.1f}" width="{r * 1.2:.1f}" height="3" class="hl"/>')
    out.append(f'<polygon points="0,{-R + 1} -5,{-R + 9} 5,{-R + 9}" class="hl"/>')
    return (f'<svg class="top" viewBox="-60 -60 120 120" width="120" height="120" role="img" '
            f'aria-label="{model["name"]} top">{"".join(out)}</svg>')
