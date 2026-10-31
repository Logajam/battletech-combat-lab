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


def mount_style(zone, cls, big, n_zone, classes_in_zone):
    """Pick how a weapon group is drawn from its zone, class and size."""
    arm = zone.endswith("Arm")
    side = zone in ("Left Torso", "Right Torso")
    if cls == "missile":
        return "arm_rack" if arm else ("shoulder_rack" if side else "chest_rack")
    if cls == "ballistic":
        if arm:
            return "arm_barrel"
        return "shoulder_barrel" if (side and big) else "port"
    if side and n_zone >= 3 and len(classes_in_zone) >= 2:
        return "turret"
    if arm:
        return "aperture"
    return "head_port" if zone == "Head" else "port"


def build_model(unit):
    """The part model: a plain dict a renderer (or a person) can read and edit."""
    tons = unit["tons"]
    chassis = unit.get("clanname") or unit.get("chassis", "?")
    names = {unit.get("chassis", "").lower(), unit.get("clanname", "").lower()}
    hc = _hash(unit.get("chassis", "?"))
    hm = _hash(unit.get("chassis", "?") + " " + unit.get("model", ""))
    config = unit.get("config", "Biped")
    quad = "Quad" in config

    # armor per ton against a typical 3.0: a bulk hint (armor and loadout add bulk)
    armor_ratio = unit["armor"] / max(tons, 1) / 3.0 if unit["armor"] else 1.0
    bulk = max(0.88, min(1.22, 0.9 + 0.12 * armor_ratio + (0.05 if tons >= 80 else 0)))

    model = {
        "name": f'{unit.get("chassis", "?")} {unit.get("model", "")}'.strip(),
        "chassis": chassis, "tons": tons, "config": config, "quad": quad,
        "rules_levels": rules_levels(tons), "drawn_levels": round(drawn_levels(tons), 3),
        "bulk": round(bulk, 3),
        "legs": ("straight", "digitigrade", "thick")[hc[0] % 3],
        "torso": ("box", "ovoid", "narrow", "slab")[hc[1] % 4],
        "head": ("top", "top", "low")[hc[2] % 3],
        "lean": 0.04 + 0.05 * (hc[3] % 4),                 # side view: torso lean
        "antenna": hm[0] % 3 == 0,
        "jets": min(unit["jets"], 6), "fins": min(unit["heat_sinks"] // 6, 6),
        "overridden": [],
    }
    head_slots = unit["slots"].get("Head")
    if head_slots and not any("Cockpit" in x for x in head_slots):
        model["head"] = "sunk"                              # cockpit not in the head

    # arms from the actuators in each arm's slots (data, not the hash)
    arms = {}
    for side, zone in (("L", "Left Arm"), ("R", "Right Arm")):
        s = " ".join(unit["slots"].get(zone, []))
        arms[side] = "hand" if "Hand Actuator" in s else "forearm" if "Lower Arm Actuator" in s \
            else "pod" if s else "none"
    model["arms"] = None if quad else arms

    # hardpoints: one group per zone and class
    groups = {}
    for w in unit["weapons"]:
        cls = weapon_class(w["name"])
        if cls == "other":
            continue
        g = groups.setdefault((w["zone"], cls), {"zone": w["zone"], "cls": cls, "count": 0, "big": False})
        g["count"] += 1
        g["big"] = g["big"] or weapon_is_big(w["name"])
    per_zone = {}
    for (zone, cls), g in groups.items():
        per_zone.setdefault(zone, []).append(g)
    for zone, gs in per_zone.items():
        n_zone = sum(g["count"] for g in gs)
        for g in gs:
            g["mount"] = mount_style(zone, g["cls"], g["big"], n_zone, {x["cls"] for x in gs})
    model["hardpoints"] = [g for gs in per_zone.values() for g in gs]

    # named-unit overrides beat the hash
    ov = _overrides()
    for n in names:
        if n and n in ov:
            for k, v in ov[n].items():
                if k != "note":
                    model[k] = v
                    model["overridden"].append(k)
    return model


# --------------------------------------------------------------------- drawing

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


WCLS = {"energy": "we", "ballistic": "wb", "missile": "wm"}


def _groups(model, zone):
    return [g for g in model["hardpoints"] if g["zone"] == zone]


def _dots(g, cx, cy, n, size, cls, cols=4, gap=1.6):
    """A small grid of `n` dots (a rack's cells or a bank of ports)."""
    n = min(n, 12)
    rows = math.ceil(n / cols)
    for i in range(n):
        r, c = divmod(i, cols)
        row_n = min(cols, n - r * cols)
        x = cx + (c - (row_n - 1) / 2) * size * gap
        y = cy - (r - (rows - 1) / 2) * size * gap
        g.ell(x, y, size / 2, size / 2, cls)


def _figure_dims(model):
    b = model["bulk"]
    d = {"b": b}
    quad = model["quad"]
    d["leg_h"] = 0.50 if quad else 0.44
    d["torso_h"] = 0.26 if quad else 0.34
    tmod = {"box": 1.0, "ovoid": 0.95, "narrow": 0.78, "slab": 1.15}[model["torso"]]
    d["tw"] = (0.60 if quad else 0.40) * b * tmod
    d["y0"] = d["leg_h"] - 0.03
    d["ytop"] = d["y0"] + d["torso_h"]
    d["thick"] = 1.3 if model["legs"] == "thick" else 1.0
    return d


def _legs_front(g, model, d):
    b, lh = d["b"], d["leg_h"]
    lw = 0.13 * d["thick"] * b
    for s in (-1, 1):
        sets = ((s * 0.17 * b, lh), (s * 0.30 * b, lh - 0.04)) if model["quad"] else ((s * 0.16 * b, lh),)
        for x, h in sets:
            g.rect(x - lw / 2, 0, lw, h, "g")
            g.rect(x - lw * 0.7, 0, lw * 1.4, 0.04, "f")        # foot


def _torso_front(g, model, d):
    tw, y0, th = d["tw"], d["y0"], d["torso_h"]
    t = model["torso"]
    if t == "ovoid":
        g.ell(0, y0 + th / 2, tw / 2, th / 2 + 0.015, "f")
    elif t == "narrow":
        g.poly([(-tw * 0.32, y0), (tw * 0.32, y0), (tw / 2, y0 + th), (-tw / 2, y0 + th)], "f")
    elif t == "slab":
        g.rect(-tw / 2, y0, tw, th, "f")
    else:
        c = th * 0.12
        g.poly([(-tw / 2, y0), (tw / 2, y0), (tw / 2, y0 + th - c), (tw / 2 - c, y0 + th),
                (-tw / 2 + c, y0 + th), (-tw / 2, y0 + th - c)], "f")
    g.rect(-tw * 0.22, y0 - 0.01, tw * 0.44, 0.05, "g")          # pelvis


def _head_front(g, model, d, rear=False):
    style, y = model["head"], d["ytop"]
    if style == "sunk":
        g.rect(-0.05, y - 0.07, 0.10, 0.045, "hl" if not rear else "g")      # window on the chest
        return
    cy = y + (0.07 if style == "top" else -0.005)
    g.rect(-0.055, cy - 0.045, 0.11, 0.09, "f")
    if not rear:
        g.rect(-0.04, cy - 0.005, 0.08, 0.022, "hl")
    if model.get("antenna"):
        g.rect(0.035, cy + 0.04, 0.008, 0.07, "g")
    for gr in _groups(model, "Head"):
        g.ell(0, cy - 0.03, 0.012, 0.012, WCLS[gr["cls"]])


def _arm_front(g, model, d, side, kind, rear=False):
    s = -1 if side == "L" else 1
    tw, b = d["tw"], d["b"]
    sy = d["ytop"] - 0.04
    aw = (0.14 if kind == "pod" else 0.10) * b
    ln = {"hand": 0.36, "forearm": 0.34, "pod": 0.32, "none": 0.2}[kind]
    x = s * (tw / 2 + aw / 2 - 0.01)
    flex = model.get("arms_flex")
    if flex:
        g.poly([(x - aw / 2, sy), (x + aw / 2, sy), (x + aw / 2 + s * 0.04, sy - ln * 0.55),
                (x + aw / 2 + s * 0.02, sy - ln), (x - aw / 2 + s * 0.02, sy - ln),
                (x - aw / 2 + s * 0.04, sy - ln * 0.55)], "g")
    else:
        g.rect(x - aw / 2, sy - ln, aw, ln, "g")
    g.rect(x - aw * 0.6, sy - 0.03, aw * 1.2, 0.06, "f")        # shoulder joint
    if kind == "hand":
        g.rect(x - aw * 0.6, sy - ln - 0.05, aw * 1.2, 0.06, "f")
    zone = "Left Arm" if side == "L" else "Right Arm"
    if rear:
        return
    by = sy - ln + 0.035
    for gr in _groups(model, zone):
        n = gr["count"]
        c = WCLS[gr["cls"]]
        if gr["mount"] == "arm_barrel":
            g.ell(x, by + 0.02, 0.032 if gr["big"] else 0.022, 0.032 if gr["big"] else 0.022, c)
        elif gr["mount"] == "arm_rack":
            _dots(g, x, by + 0.045, n, 0.016, c, cols=3)
        else:
            _dots(g, x, by, n, 0.014, c, cols=3)


def _rack_front(g, model, d, side):
    s = -1 if side == "L" else 1
    zone = "Left Torso" if side == "L" else "Right Torso"
    tw, yt = d["tw"], d["ytop"]
    x = s * (tw / 2 - 0.07)
    for gr in _groups(model, zone):
        n, c, m = gr["count"], WCLS[gr["cls"]], gr["mount"]
        if m == "shoulder_rack":
            w = min(0.22, 0.10 + 0.012 * n)
            h = 0.07 + 0.016 * math.ceil(min(n, 12) / 4)
            g.rect(x - w / 2, yt - 0.01, w, h, "g")
            _dots(g, x, yt - 0.01 + h / 2, n, 0.017, c)
        elif m == "shoulder_barrel":
            g.rect(x - 0.035, yt - 0.01, 0.07, 0.07, "g")
            g.ell(x, yt + 0.025, 0.026, 0.026, c)
        elif m == "turret":
            g.ell(x, yt + 0.025, 0.07, 0.045, "g")
            _dots(g, x, yt + 0.025, n, 0.016, c, cols=4)
        else:
            _dots(g, s * tw * 0.28, d["y0"] + d["torso_h"] * 0.55, n, 0.014, c, cols=3)
    for gr in _groups(model, "Center Torso"):
        _dots(g, 0, d["y0"] + d["torso_h"] * 0.35, gr["count"], 0.014, WCLS[gr["cls"]], cols=4)


def _figure_front(model, height_px, rear=False):
    d = _figure_dims(model)
    g = G()
    _legs_front(g, model, d)
    _torso_front(g, model, d)
    if not model["quad"]:
        arms = model["arms"] or {"L": "hand", "R": "hand"}
        for side in ("L", "R"):
            _arm_front(g, model, d, side, arms[side], rear)
    if not rear:
        _rack_front(g, model, d, "L")
        _rack_front(g, model, d, "R")
    _head_front(g, model, d, rear)
    if rear:
        for i in range(model["jets"]):                          # jump jet pods
            x = (i - (model["jets"] - 1) / 2) * 0.065
            g.rect(x - 0.025, d["y0"] + 0.01, 0.05, 0.08, "hl")
        for i in range(model["fins"]):                          # heat sink fins
            x = (i - (model["fins"] - 1) / 2) * 0.05
            g.rect(x - 0.012, d["y0"] + d["torso_h"] * 0.45, 0.024, d["torso_h"] * 0.4, "hl")
    return g.svg(height_px)


def _frame(model, inner, kind):
    """Wrap a drawing in the standee: a card of the RULES height on a base."""
    rl = model["rules_levels"]
    ch = rl * LEVEL
    cw = 40 * rl
    card = (f'<rect x="{-cw / 2}" y="{-ch}" width="{cw}" height="{ch}" class="card"/>'
            f'<line x1="{-cw / 2}" x2="{cw / 2}" y1="{-LEVEL}" y2="{-LEVEL}" class="lvl"/>')
    if rl >= 2:
        card += f'<line x1="{-cw / 2}" x2="{cw / 2}" y1="{-2 * LEVEL}" y2="{-2 * LEVEL}" class="lvl"/>'
    base = f'<ellipse cx="0" cy="3" rx="{cw * 0.42}" ry="6" class="base"/>'
    return (f'<svg class="{kind}" viewBox="-85 {-3 * LEVEL - 6} 170 {3 * LEVEL + 18}" '
            f'width="170" height="{3 * LEVEL + 18}" role="img" aria-label="{model["name"]} {kind}">'
            f'{base}{card}{inner}</svg>')


def card_svg(model):
    return _frame(model, _figure_front(model, model["drawn_levels"] * LEVEL), "front")


def rear_svg(model):
    return _frame(model, _figure_front(model, model["drawn_levels"] * LEVEL, rear=True), "rear")


def _legs_side(g, model, d):
    b, lh, th = d["b"], d["leg_h"], d["thick"]
    w = 0.14 * th * b
    for off, cls in ((0.02, "g"), (0.0, "f")):
        if model["legs"] == "digitigrade" and not model["quad"]:
            g.poly([(off - w / 2, lh), (off + w / 2, lh), (off - 0.07 + w / 2, 0.27), (off + 0.07, 0.12),
                    (off + 0.05 + w / 2, 0.04), (off + 0.16, 0.0), (off - 0.02, 0.0), (off + 0.00 - w / 2, 0.12),
                    (off - 0.13, 0.27)], cls)
        else:
            g.poly([(off - w / 2, lh), (off + w / 2, lh), (off + w / 2, 0.04), (off + w * 0.9, 0.0),
                    (off - w * 0.9, 0.0), (off - w / 2, 0.04)], cls)
        if model["quad"]:
            g.rect(off + 0.30 - w / 2, 0, w, lh, cls)
            g.rect(off - 0.30 - w / 2, 0, w, lh, cls)


def side_svg(model):
    d = _figure_dims(model)
    b, y0, th = d["b"], d["y0"], d["torso_h"]
    td = (0.55 if model["quad"] else 0.30) * b * ({"slab": 1.15, "narrow": 0.8}.get(model["torso"], 1.0))
    lean = model["lean"] * th
    g = G()
    _legs_side(g, model, d)
    g.poly([(-td / 2, y0), (td / 2, y0), (td / 2 + lean, y0 + th), (-td / 2 + lean, y0 + th)], "f")
    for i in range(model["jets"]):
        g.rect(-td / 2 - 0.035, y0 + 0.02 + i * 0.035, 0.04, 0.03, "hl")
    if model["head"] != "sunk":
        cy = d["ytop"] + (0.07 if model["head"] == "top" else -0.005)
        g.rect(lean + 0.0, cy - 0.045, 0.13, 0.09, "f")
        g.rect(lean + 0.08, cy - 0.005, 0.05, 0.02, "hl")
    sy = d["ytop"] - 0.05
    sx = lean * 0.9
    for side in ("L", "R"):
        zone = "Left Arm" if side == "L" else "Right Arm"
        kind = (model["arms"] or {"L": "hand", "R": "hand"})[side]
        ln = {"hand": 0.36, "forearm": 0.34, "pod": 0.32}.get(kind, 0.2)
        if side == "L":
            continue                                           # one arm shown (the near arm), the other is hidden
        aw = (0.14 if kind == "pod" else 0.10) * b
        g.poly([(sx - aw / 2, sy), (sx + aw / 2, sy), (sx + aw / 2 + 0.06, sy - ln), (sx - aw / 2 + 0.06, sy - ln)], "g")
        for gr in _groups(model, zone):
            L = 0.30 if gr["big"] and gr["cls"] == "ballistic" else 0.12
            t = 0.04 if gr["big"] else 0.025
            for i in range(min(gr["count"], 3)):
                g.rect(sx + 0.06, sy - ln + 0.02 + i * (t + 0.012), L, t, WCLS[gr["cls"]])
    for zone in ("Right Torso",):
        for gr in _groups(model, zone):
            n, m = gr["count"], gr["mount"]
            c = WCLS[gr["cls"]]
            if m == "shoulder_rack":
                g.rect(lean * 0.9 - 0.08, d["ytop"] - 0.01, 0.16, 0.07 + 0.012 * math.ceil(min(n, 12) / 4), "g")
                g.rect(lean * 0.9 - 0.08, d["ytop"] + 0.02, 0.16, 0.012, c)
            elif m == "shoulder_barrel":
                g.rect(lean * 0.9 - 0.04, d["ytop"] + 0.005, 0.30, 0.035, c)
            elif m == "turret":
                g.ell(lean * 0.9, d["ytop"] + 0.025, 0.09, 0.045, "g")
                g.rect(lean * 0.9, d["ytop"] + 0.02, 0.14, 0.015, c)
    return _frame_side(model, g.svg(model["drawn_levels"] * LEVEL))


def _frame_side(model, inner):
    rl, ch = model["rules_levels"], model["rules_levels"] * LEVEL
    card = (f'<rect x="-58" y="{-ch}" width="116" height="{ch}" class="card"/>'
            f'<line x1="-58" x2="58" y1="{-LEVEL}" y2="{-LEVEL}" class="lvl"/>')
    if rl >= 2:
        card += f'<line x1="-58" x2="58" y1="{-2 * LEVEL}" y2="{-2 * LEVEL}" class="lvl"/>'
    return (f'<svg class="side" viewBox="-85 {-3 * LEVEL - 6} 170 {3 * LEVEL + 18}" width="170" '
            f'height="{3 * LEVEL + 18}" role="img" aria-label="{model["name"]} side">'
            f'<ellipse cx="0" cy="3" rx="50" ry="6" class="base"/>{card}{inner}</svg>')


def top_svg(model):
    """Top-down token on a flat-topped hex, facing up (the top of the picture)."""
    R = 52
    s = (model["tons"] / 100.0) ** (1.0 / 3.0)
    b = model["bulk"]
    tmod = {"box": 1.0, "ovoid": 0.95, "narrow": 0.8, "slab": 1.15}[model["torso"]]
    tw = R * 0.78 * s * b * tmod
    td = tw * (1.5 if model["quad"] else 0.95)
    hexp = " ".join(f"{R * math.cos(math.radians(a)):.1f},{R * math.sin(math.radians(a)):.1f}" for a in range(0, 360, 60))
    out = [f'<polygon points="{hexp}" class="hex"/>']
    arms = model["arms"] or {"L": "none", "R": "none"}
    for side, sgn in (("L", -1), ("R", 1)):
        kind = arms[side]
        aw = tw * (0.34 if kind == "pod" else 0.24)
        al = td * 0.9
        x = sgn * (tw / 2 + aw / 2 - 1)
        out.append(f'<rect x="{x - aw / 2:.1f}" y="{-al * 0.55:.1f}" width="{aw:.1f}" height="{al:.1f}" rx="2" class="g"/>')
        zone = "Left Arm" if side == "L" else "Right Arm"
        for gr in _groups(model, zone):
            L = R * 0.42 if gr["big"] and gr["cls"] == "ballistic" else R * 0.16
            for i in range(min(gr["count"], 3)):
                bx = x + (i - (min(gr["count"], 3) - 1) / 2) * 5
                out.append(f'<rect x="{bx - 2:.1f}" y="{-al * 0.55 - L:.1f}" width="4" height="{L:.1f}" class="{WCLS[gr["cls"]]}"/>')
    out.append(f'<rect x="{-tw / 2:.1f}" y="{-td / 2:.1f}" width="{tw:.1f}" height="{td:.1f}" rx="{(9 if model["torso"] == "ovoid" else 3)}" class="f"/>')
    for side, sgn in (("L", -1), ("R", 1)):
        zone = "Left Torso" if side == "L" else "Right Torso"
        for gr in _groups(model, zone):
            n, c, m = gr["count"], WCLS[gr["cls"]], gr["mount"]
            if m in ("shoulder_rack", "turret"):
                w = min(tw * 0.42, 8 + n * 1.4)
                out.append(f'<rect x="{sgn * tw * 0.3 - w / 2:.1f}" y="{-td * 0.42:.1f}" width="{w:.1f}" height="{td * 0.5:.1f}" rx="2" class="g"/>')
                out.append(f'<rect x="{sgn * tw * 0.3 - w / 2 + 2:.1f}" y="{-td * 0.42 + 2:.1f}" width="{w - 4:.1f}" height="3" class="{c}"/>')
            elif m == "shoulder_barrel":
                out.append(f'<rect x="{sgn * tw * 0.3 - 2:.1f}" y="{-td / 2 - R * 0.3:.1f}" width="4" height="{R * 0.3 + td * 0.3:.1f}" class="{c}"/>')
            else:
                out.append(f'<circle cx="{sgn * tw * 0.25:.1f}" cy="{-td * 0.15:.1f}" r="2.2" class="{c}"/>')
    if model["head"] != "sunk":
        out.append(f'<circle cx="0" cy="{-td * 0.34:.1f}" r="{R * 0.1:.1f}" class="g"/>')
        out.append(f'<circle cx="0" cy="{-td * 0.38:.1f}" r="{R * 0.04:.1f}" class="hl"/>')
    out.append(f'<polygon points="0,{-R + 1} -5,{-R + 9} 5,{-R + 9}" class="hl"/>')   # facing arrow
    return (f'<svg class="top" viewBox="-60 -60 120 120" width="120" height="120" role="img" '
            f'aria-label="{model["name"]} top">{"".join(out)}</svg>')
