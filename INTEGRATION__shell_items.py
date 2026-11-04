"""
INTEGRATION__shell_items.py  (NEW 2026-11-04, Claude - Combat Lab art, output only)

The data half of the skeleton-and-shell builder (spec: INTEGRATION__COMBAT_LAB_SKELETON.md sections 3 and 4):
what a unit's critical slots hold, how heavy and how big each item is, how many hardpoints each location has, and
which hardpoint cells each item takes. No geometry here (INTEGRATION__shell.py draws it) and no battle code.

    items = parse_items(unit)            # {location: [item, ...]}: every crit-holding item of the unit
    plan  = place_items(unit, items)     # {location: [(item, rail, first cell)]}, shuffled by the unit's name hash
    check = hardpoint_report(unit)       # the numbers the acceptance test reads

An ITEM is a dict: name, kind (a key of data/token_densities.json), fam (weapon family), slots, tons, vol (m3 =
tons / density), zone, visible (has a face that is drawn), rear. Masses come from mechsim/equipment.json
(`tonnage`); where it has none, the fallback table in data/token_densities.json is used and the item is recorded in
FALLBACKS so a report can list it. These are ART values: nothing in a battle reads them.
"""

import hashlib
import json
import math
import os
import random
import re

import INTEGRATION__tokens as T

HERE = os.path.dirname(os.path.abspath(__file__))
DENS = json.load(open(os.path.join(HERE, "data", "token_densities.json"), encoding="utf-8"))
_EQ = json.load(open(os.path.join(HERE, "mechsim", "equipment.json"), encoding="utf-8"))
ENTRIES, ALIASES = _EQ["entries"], _EQ["alias_map"]
SLOT_M = DENS["slot_length_m"]
FALLBACKS = {}                                   # item name -> how many times its mass came from the fallback table

# the crit table's size per location (Core: 12 for torsos and arms, 6 for the head and legs)
SLOTS_IN = {"Head": 6, "Left Leg": 6, "Right Leg": 6, "Center Leg": 6, "Front Left Leg": 6, "Front Right Leg": 6,
            "Rear Left Leg": 6, "Rear Right Leg": 6}
# everything on these lines is the body itself, never a mountable item (spec section 3)
STRUCTURAL = {"shoulder", "hip", "upper arm actuator", "lower arm actuator", "hand actuator", "upper leg actuator",
              "lower leg actuator", "foot actuator", "engine", "fusion engine", "gyro", "cockpit", "life support", "sensors",
              "-empty-"}
FILLER_WORDS = ("endo", "ferro", "stealth", "reactive", "reflective", "ballistic-reinforced", "ballisticreinforced")
VISIBLE_KINDS = {"laser", "ppc", "ac", "lbx", "uac", "rotary", "gauss", "mg", "flamer", "plasma", "missile", "jumpjet",
                 "ecm", "probe", "c3", "ams", "heatsink_single", "heatsink_double"}
WEAPON_FAMS = {"laser": "laser", "ppc": "ppc", "ac": "ac", "uac": "uac", "lbx": "lbx", "gauss": "gauss", "rotary": "rotary",
               "mg": "mg", "flamer": "flamer", "plasma": "plasma", "srm": "missile", "lrm": "missile", "mrm": "missile"}


def _strip(raw):
    n = raw.strip()
    changed = True
    while changed:
        changed = False
        for suf in ("(R)", "(OMNIPOD)", "(T)", "(SPLIT)", "(ARMORED)"):
            if n.upper().endswith(suf):
                n = n[:-len(suf)].strip()
                changed = True
    return n


def lookup(raw):
    return ENTRIES.get(ALIASES.get(re.sub(r"\s+", "", _strip(raw).lower())))


def _norm(raw):
    return re.sub(r"\s+", "", _strip(raw).lower())


def engine_tons(unit):
    """Art estimate of the engine's mass from its rating and type (data/token_densities.json)."""
    text = unit.get("engine", "")
    m = re.match(r"\s*(\d+)", text)
    rating = int(m.group(1)) if m else 4 * unit["tons"]
    tbl = sorted((int(k), v) for k, v in DENS["engine_tons"].items() if k.isdigit())
    lo = max([r for r in tbl if r[0] <= rating] or [tbl[0]])
    hi = min([r for r in tbl if r[0] >= rating] or [tbl[-1]])
    t = lo[1] if lo[0] == hi[0] else lo[1] * (hi[1] / lo[1]) ** ((rating - lo[0]) / (hi[0] - lo[0]))
    low = text.lower()
    return t * (0.5 if "xl" in low else 0.75 if "light" in low else 1.5 if "compact" in low else 1.0), rating


def _jj_tons(unit):
    t = unit["tons"]
    return 0.5 if t <= 55 else 1.0 if t <= 85 else 2.0


def _classify(raw, entry):
    """(kind, fam) of a crit line, or (None, None) for the body's own parts."""
    low = _strip(raw).lower()
    if low in STRUCTURAL or low.startswith("fusion engine") or low.startswith("-empty"):
        return None, None
    if ":" in low:                                                       # a stray header line the unit reader kept
        return None, None
    cname = (entry or {}).get("canonical_name") or T.clean_weapon_name(_strip(raw))
    cat = (entry or {}).get("category", "")
    nm = cname.lower()
    if "jump jet" in nm or "jumpjet" in nm:
        return "jumpjet", ""
    if "heat sink" in nm or "heatsink" in nm:
        return ("heatsink_double" if "double" in nm or "laser" in nm else "heatsink_single"), ""
    if cat == "ammo" or "ammo" in nm:
        return "ammo", ""
    if cat == "weapon":
        if "anti-missile" in nm or nm.startswith("ams") or "ams" in nm.split():
            return "ams", ""
        fam, _sz = T.weapon_fam(T.clean_weapon_name(cname))           # "CLMG" -> "MG": the tech-base prefix hid the family
        if fam in WEAPON_FAMS:
            return WEAPON_FAMS[fam], fam
        return "misc", ""
    if any(w in nm for w in FILLER_WORDS):
        return "structure_slot", ""
    if "ecm" in nm or "guardian" in nm or "angel" in nm:
        return "ecm", ""
    if "probe" in nm or "beagle" in nm or "bloodhound" in nm:
        return "probe", ""
    if re.search(r"\bc3\b|c3i|improved c3|^c3", nm):
        return "c3", ""
    if "case" in nm:
        return "case", ""
    return "misc", ""


def _tons(unit, raw, entry, kind, slots, cname):
    if entry and entry.get("tonnage") is not None:
        return float(entry["tonnage"])
    fb = DENS["fallback_tons"]
    FALLBACKS[cname] = FALLBACKS.get(cname, 0) + 1
    if kind in ("heatsink_single", "heatsink_double"):
        return fb["heatsink"]
    if kind == "ammo":
        return fb["ammo_per_slot"] * slots
    if kind == "jumpjet":
        return _jj_tons(unit)
    if kind == "structure_slot":
        return 0.0
    if kind in WEAPON_FAMS.values() and kind != "missile":
        return T.weapon_tons(cname)
    if kind == "missile":
        return T.weapon_tons(cname)
    return fb["per_slot"] * slots


def parse_items(unit):
    """{location: [item, ...]} for every crit location of the unit, plus unit-wide "_cap": {location: hardpoints}.
    A multi-slot item shows as that many identical lines: they are joined using the item's own slot count from
    mechsim/equipment.json (an unknown item is 1 slot a line)."""
    out, cap = {}, {}
    for zone, lines in unit["slots"].items():
        lines = [l for l in lines[:SLOTS_IN.get(zone, 12)] if ":" not in l]
        n_cap = sum(1 for l in lines if _strip(l).lower() not in STRUCTURAL - {"-empty-"} and not _strip(l).lower().startswith("fusion engine"))
        cap[zone] = n_cap
        items, i = [], 0
        while i < len(lines):
            raw = lines[i]
            entry = lookup(raw)
            kind, fam = _classify(raw, entry)
            if kind is None:
                i += 1
                continue
            slots = int(entry["slots"]) if entry and entry.get("slots") else 1
            j = i + 1
            while j < len(lines) and j - i < slots and _norm(lines[j]) == _norm(raw):
                j += 1
            n = j - i
            cname = (entry or {}).get("canonical_name") or T.clean_weapon_name(_strip(raw))
            tons = _tons(unit, raw, entry, kind, n, cname) if kind != "structure_slot" else 0.0
            rho = DENS["density"][kind]["t_per_m3"]
            gr = {}
            if kind in WEAPON_FAMS.values():
                _f, sz = T.weapon_fam(T.clean_weapon_name(cname))
                gr = {"fam": _f, "size": sz, "er": bool(re.search(r"\ber\b|extended", cname.lower())), "pulse": "pulse" in cname.lower(),
                      "tubes": int(re.search(r"(\d+)", cname).group(1)) if kind == "missile" and re.search(r"(\d+)", cname) else 0,
                      "name": cname}
            items.append({"name": cname, "kind": kind, "slots": n, "tons": tons, "vol": max(tons, 0.02) / rho if kind != "structure_slot" else 0.0,
                          "zone": zone, "visible": kind in VISIBLE_KINDS, "rear": "(R)" in raw.upper(), "gr": gr})
            i = j
        out[zone] = items
    out["_cap"] = cap
    return out


# ----------------------------------------------------------------------------------------------- rails and the shuffle

def name_hash(unit):
    return int.from_bytes(hashlib.sha256((unit.get("chassis", "") + " " + unit.get("model", "")).lower().encode()).digest()[:8], "big")


def rail_count(zone):
    """How many mounting rails a location has (INTEGRATION__shell lays them out on the shell). Each rail is as long as the
    location has hardpoints, so any combination the critical slots allow fits (spec section 3)."""
    return {"Left Arm": 3, "Right Arm": 3, "Left Torso": 4, "Right Torso": 4, "Center Torso": 3, "Head": 2,
            "Left Leg": 2, "Right Leg": 2}.get(zone, 2)


def place_items(unit, items):
    """{zone: [(item, rail index, first cell)]}. The file's order and any heaviest-first rule are ignored: the order is a
    shuffle seeded by the unit's name hash (Daniel, 2026-11-04), and each item starts its search on a shuffled rail. Cells
    along a rail are consecutive, an item takes `slots` of them, and no cell is used twice."""
    rng = random.Random(name_hash(unit))
    plan = {}
    for zone, lst in items.items():
        if zone == "_cap":
            continue
        cap = items["_cap"].get(zone, 12)
        nr = rail_count(zone)
        used = [0] * nr
        order = list(lst)
        rng.shuffle(order)
        start = rng.randrange(nr)
        placed = []
        for idx, it in enumerate(order):
            r0 = (start + idx) % nr
            for step in range(nr):
                r = (r0 + step) % nr
                if used[r] + it["slots"] <= max(cap, it["slots"]):
                    placed.append((it, r, used[r]))
                    used[r] += it["slots"]
                    break
            else:                                                # cannot happen while the items fit the location; kept loud
                raise RuntimeError(f"no rail has {it['slots']} free cells in {zone}")
        plan[zone] = placed
    return plan


def hardpoint_report(unit):
    """What tests/test_token_shell.py checks for one unit: {"placed": n, "items": n, "dupes": n, "over": [zone...],
    "stable": bool, "cap": {zone: n}}."""
    items = parse_items(unit)
    plan = place_items(unit, items)
    seen, dupes, over, n_items, n_placed = set(), 0, [], 0, 0
    for zone, lst in items.items():
        if zone == "_cap":
            continue
        n_items += len(lst)
        cells = sum(i["slots"] for i in lst)
        if cells > items["_cap"].get(zone, 12):
            over.append(zone)
    for zone, placed in plan.items():
        occ = {}
        for it, r, c in placed:
            n_placed += 1
            if id(it) in seen:
                dupes += 1
            seen.add(id(it))
            for k in range(c, c + it["slots"]):
                if (r, k) in occ:
                    dupes += 1
                occ[(r, k)] = True
            if c + it["slots"] > max(items["_cap"].get(zone, 12), it["slots"]):
                over.append(zone)
    again = place_items(unit, parse_items(unit))
    stable = [[(i["name"], r, c) for i, r, c in v] for v in plan.values()] == [[(i["name"], r, c) for i, r, c in v] for v in again.values()]
    return {"items": n_items, "placed": n_placed, "dupes": dupes, "over": sorted(set(over)), "stable": stable, "cap": items["_cap"]}


# --------------------------------------------------------------------------------------------------------- budgets

def structure_tons(unit):
    """The 'Mech's structure mass (a tenth of its tonnage), spread over the locations by their internal structure points."""
    import sys
    for sub in ("mechsim", "pathfinder"):
        p = os.path.join(HERE, sub)
        if p not in sys.path:
            sys.path.append(p)
    from mech_state import structure_for_tonnage
    pts = structure_for_tonnage(unit["tons"], "biped")
    names = ("Head", "Center Torso", "Left Torso", "Right Torso", "Left Arm", "Right Arm", "Left Leg", "Right Leg")
    tot = sum(pts[n] for n in names)
    return {n: unit["tons"] * 0.10 * pts[n] / tot for n in names}


def armor_ratio(unit, zone):
    """0..1: the location's armor against what it could carry (twice its structure; the head 9). Core 'Armor Diagram'."""
    import sys
    for sub in ("mechsim", "pathfinder"):
        p = os.path.join(HERE, sub)
        if p not in sys.path:
            sys.path.append(p)
    from mech_state import structure_for_tonnage
    pts = structure_for_tonnage(unit["tons"], "biped")
    cap = 9 if zone == "Head" else 2 * pts.get(zone, 10)
    return min(1.0, (unit.get("armor_by") or {}).get(zone, 0) / (0.8 * cap)) if cap else 0.5


def budgets(unit, items):
    """{zone: volume in m3 the location must hold}: its items (tons / density), its share of the structure, its armor
    (points / 16 a ton, density `armor`), and the engine, gyro and cockpit in the locations that carry them. Also returns the
    list of (zone, what) pieces for a report. Spec section 4: a sanity check, not a calibration."""
    st = structure_tons(unit)
    d = DENS["density"]
    out, parts = {}, {}
    et, rating = engine_tons(unit)
    xl = "xl" in unit.get("engine", "").lower() or "light" in unit.get("engine", "").lower()
    gyro_t = math.ceil(rating / 100.0)
    cock = T.cockpit_tons(unit.get("cockpit"))
    torso_cockpit = "torso" in (unit.get("cockpit") or "").lower()
    for zone in ("Head", "Center Torso", "Left Torso", "Right Torso", "Left Arm", "Right Arm", "Left Leg", "Right Leg"):
        v = {"structure": st[zone] / d["structure"]["t_per_m3"],
             "armor": (unit.get("armor_by") or {}).get(zone, 0) / 16.0 / d["armor"]["t_per_m3"],
             "items": sum(i["vol"] for i in items.get(zone, []))}
        acts = DENS["actuator_tons"]
        for line in unit["slots"].get(zone, [])[:SLOTS_IN.get(zone, 12)]:     # actuators give the limbs their bulk (art mass)
            key = _strip(line).lower()
            if key in acts and not key.startswith("_"):
                v["hip" if key == "hip" else "actuators"] = v.get("hip" if key == "hip" else "actuators", 0.0) + \
                    unit["tons"] * acts[key] / d["actuator"]["t_per_m3"]
        if zone == "Center Torso":
            v["engine"] = et * (0.5 if xl else 1.0) / d["engine"]["t_per_m3"]
            v["gyro"] = gyro_t / d["gyro"]["t_per_m3"]
            if torso_cockpit:
                v["cockpit"] = cock / d["cockpit"]["t_per_m3"]
        elif zone in ("Left Torso", "Right Torso") and xl:
            v["engine"] = et * 0.25 / d["engine"]["t_per_m3"]
        elif zone == "Head":
            if not torso_cockpit:
                v["cockpit"] = cock / d["cockpit"]["t_per_m3"]
            v["sensors"] = 0.5 / d["cockpit"]["t_per_m3"]
        parts[zone] = v
        out[zone] = sum(v.values())
    rule = DENS.get("bulk_rule", {})
    if rule.get("rule") == "structure_points":
        # Daniel's rule: the base bulk (everything but the location's weapons and equipment) follows the structure points, the
        # head's counted 1.5 times; the whole 'Mech's base volume is kept. Each part's share inside a location is kept in
        # proportion (the hip still builds the pelvis, the engine still fills the centre torso), only rescaled.
        import sys
        for sub in ("mechsim", "pathfinder"):
            pth = os.path.join(HERE, sub)
            if pth not in sys.path:
                sys.path.append(pth)
        from mech_state import structure_for_tonnage
        pts = structure_for_tonnage(unit["tons"], "biped")
        w = {z: pts[z] * (rule.get("head_factor", 1.5) if z == "Head" else rule.get("leg_factor", 1.0) if z.endswith("Leg") else 1.0) for z in parts}
        base = {z: out[z] - parts[z]["items"] for z in parts}
        total = sum(base.values())
        for z, v in parts.items():
            want = total * w[z] / sum(w.values())
            k = want / max(base[z], 1e-9)
            for key in v:
                if key != "items":
                    v[key] *= k
            out[z] = want + v["items"]
    return out, parts
