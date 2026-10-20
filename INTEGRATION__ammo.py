"""
INTEGRATION__ammo.py  (NEW 2026-10-19, Claude - Pile 2 rules, Pile 4 bin choice)

Ammunition, replacing the unlimited-ammo and one-shot stubs. Core Rulebook:
  - Shots (pp.72-73): every firing uses one shot from an ammo bin that holds
    exactly that weapon's ammunition (an LRM 15 uses LRM 15 ammo, from any
    location; identical weapons share bins). A bin is one ton: it holds the
    weapon's Shots per Ton (Weapons and Equipment Tables, pp.248-254 -
    equipment.json shots_per_ton, filled 2026-10-19).
  - Ammo is marked off at attack declaration, except Streak launchers,
    which only use a shot when they hit (p.187).
  - One-Shot (OS) weapons (p.182) fire once per game and carry no bins;
    rocket launchers are OS too (table: Shots per Ton "OS").
  - Explosions (pp.95-96): a bin explodes for shots left x damage per shot
    (missiles: missiles left x damage each), capped at 20; an empty bin
    doesn't explode (p.180).

Bot choice (pile 4, not a rule): which bin a shot comes from - the bin with
the fewest shots left, so bins run empty (and stop being explosive) sooner.
Inferno bins are never fired from: inferno missiles' effect on a target
(heat, no damage - p.192) isn't modeled, so they stay aboard as a heat
explosion risk only.

A weapon whose ammo has no shots_per_ton in equipment.json (a few Tactical
Operations weapons) keeps firing with unlimited ammo; stubs.stub_ammo_data
says so each time.
"""

import re

import INTEGRATION__config as config
import INTEGRATION__stubs as stubs
import INTEGRATION__weapon_rules as weapon_rules
from equipment import Equipment, lookup_equipment
from damage_resolution import get_weapons


# One-shot launcher names in equipment.json: "LRM 5 (OS)", "CLLRM10 (OS)",
# "ISSRM2OS", "CLOSStreakLRM5", "CLIOSStreakLRM5", "CLNarcBeacon (OS)" - a
# name pattern, checked against every weapon entry 2026-10-19 (45 matches,
# all one-shots). Rocket launchers are caught by shots_per_ton "OS".
_ONE_SHOT_NAME = re.compile(r"\(I?-?OS\)|OS$|^CLI?OS")


def _entry(name):
    return lookup_equipment(name or "")


def weapon_entry_for_ammo(bin_name):
    """equipment.json entry of the weapon a bin feeds, found by name: drop a
    " - Variant" suffix and the words "Ammo"/"Inferno" ("ISLRM15 Ammo" ->
    "ISLRM15"). None if the name doesn't resolve to a weapon."""
    base = bin_name.split(" - ")[0]
    base = " ".join(w for w in base.split() if w.lower() not in ("ammo", "inferno"))
    entry = _entry(base)
    return entry if entry is not None and entry.get("category") == "weapon" else None


# --- Bin names -> (weapon fed, munition)  (2026-10-20, Claude) ------------------
# MegaMek writes a munition variant after the launcher's name ("IS Ammo LRM-20
# Artemis-capable", "Clan Ammo SRM-6 (Clan) Narc-capable"), and many bins name
# the weapon differently from its equipment.json row ("IS Gauss Ammo", "IS Ammo
# AC/10"). Until 2026-10-20 none of those bins fed anything, so their weapons
# never fired (1,541 of the units in data/meks.zip). Munitions (pp.191-193):
#   standard, artemis4 / artemis5 (Artemis IV / V-equipped missiles),
#   narc (Narc-equipped missiles), homing / explosive (Narc / iNarc pods).
# Ammunition KIND (2026-10-20, INTEGRATION__fire_modes): "cluster" (LB-X
# cluster rounds), "er" / "he" (ATM), "lrm" / "srm" (MML), else "".
# Bins whose munition isn't modeled stay unlinked (their weapon can't fire from
# them): Arrow IV, and iNarc ECM / haywire / Nemesis pods (no unit in
# data/meks.zip carries those). A " - Half" bin holds half a ton's shots.
_MUNITION_SUFFIXES = (
    (re.compile(r"\s*Artemis V-capable", re.I), "artemis5"),
    (re.compile(r"\s*Artemis-capable", re.I), "artemis4"),
    (re.compile(r"\s*Narc-capable", re.I), "narc"),
)
_NOT_MODELED = re.compile(r"ArrowIV|ECM Pods|Haywire|Nemesis", re.I)
_LBX_CLUSTER = re.compile(r"\s*Cluster|\sCL(?= Ammo)", re.I)
_ATM_KIND = re.compile(r"(ATM-?\d+)\s+(ER|HE)\b", re.I)
_MML = re.compile(r"MML-?(\d)\s*(LRM|SRM)", re.I)
NARC_POD_DAMAGE = {"ISNarcBeacon": 2, "CLNarcBeacon": 2, "ISImprovedNarc": 3}      # explosion per pod, p.193
EXPLOSIVE_POD_DAMAGE = {"ISNarcBeacon": 4, "CLNarcBeacon": 4, "ISImprovedNarc": 6}  # hit / explosion, p.193


def _strip_is(name):
    return name[3:] if name.startswith("IS ") else name


def parse_bin(bin_name):
    """(equipment.json weapon entry the bin feeds, munition, kind), or
    (None, None, None)."""
    if _NOT_MODELED.search(bin_name or ""):
        return None, None, None
    name, munition, kind = bin_name, "standard", ""
    for pattern, guidance in _MUNITION_SUFFIXES:
        if pattern.search(name):
            name, munition = pattern.sub("", name), guidance
            break
    name = name.replace("(Clan)", "").strip()
    u = _norm_name(name)
    if "NARC" in u and ("POD" in u or u.endswith("NARC")):
        weapon = "ISImprovedNarc" if "INARC" in u else ("CLNarcBeacon" if u.startswith("CL") else "ISNarcBeacon")
        return _entry(weapon), ("explosive" if "EXPLOSIVE" in u else "homing"), ""
    mml = _MML.search(name)
    if mml:
        return _entry(f"ISMML{mml.group(1)}"), munition, mml.group(2).lower()
    atm = _ATM_KIND.search(name)
    if atm:
        name, kind = _ATM_KIND.sub(lambda m: m.group(1), name), atm.group(2).lower()
    own = _entry(bin_name) or _entry(name)                       # the bin's own ammo row, if any
    own = own if own is not None and own.get("category") == "ammo" else None
    if _LBX_CLUSTER.search(name) or (own is not None and "CLUSTER" in own["canonical_name"].upper()):
        kind = "cluster"
    candidates = [name] + ([own["canonical_name"]] + list(own.get("aliases") or []) if own else [])
    for candidate in candidates:
        if kind == "cluster":
            candidate = _LBX_CLUSTER.sub("", candidate)
        candidate = re.sub(r"\((\d+|1/2 ton)\)", "", candidate).strip()   # "(100)" shot counts, "(1/2 ton)"
        for c in (candidate, _strip_is(candidate)):
            entry = weapon_entry_for_ammo(c)
            if entry is not None and (own is None or entry.get("tech_base") == own.get("tech_base")):
                return entry, munition, kind
    return None, None, None


def _norm_name(name):
    return (name or "").replace(" ", "").replace("-", "").upper()


def damage_per_shot(entry):
    """Damage Value of one shot (p.107): missiles x damage each, else damage."""
    if entry is None or entry.get("damage_per_shot") is None:
        return None
    if entry.get("damage_type") == "Missile" and entry.get("rack_size"):
        return entry["damage_per_shot"] * entry["rack_size"]
    return entry["damage_per_shot"]


def is_one_shot(weapon):
    entry = _entry(weapon.name)
    return bool(_ONE_SHOT_NAME.search(weapon.name or "")) or (entry is not None and entry.get("shots_per_ton") == "OS")


# =============================================================================
# ==========================  SETUP  ==========================================
# =============================================================================
def attach_ammo(mech):
    """Once per battle (fresh clone): link bins to weapons and fill them."""
    import INTEGRATION__fire_modes as fire_modes        # fire_modes imports this module
    for location, slots in mech.crits.items():
        for slot in slots:
            if isinstance(slot, Equipment) and slot.category == "ammo" and not hasattr(slot, "feeds"):
                entry, munition, kind = parse_bin(slot.name)
                slot.feeds = entry["canonical_name"] if entry else None
                slot.munition, slot.kind = munition, kind
                shots = entry.get("shots_per_ton") if entry else None
                if kind in fire_modes.MML_KINDS and entry is not None:
                    shots = fire_modes.MML_SHOTS.get(entry.get("rack_size"), {}).get(kind)
                slot.shots_left = shots if isinstance(shots, int) else None     # None = unknown: unlimited
                half = re.search(r"\((\d+)\)\s*$", slot.name)                   # "ISLightMG Ammo (100)": a half-ton bin
                if half and entry is not None:
                    slot.shots_left = int(half.group(1))
                elif re.search(r" - Half\s*$", slot.name) and slot.shots_left is not None:
                    slot.shots_left //= 2
                slot.missiles_per_shot = (entry.get("rack_size") or 1) if entry and entry.get("damage_type") == "Missile" else 1
                slot.shot_damage = damage_per_shot(entry)
                if entry is not None and (kind in fire_modes.MML_KINDS or kind in fire_modes.ATM_KINDS):
                    per = fire_modes.MML_KINDS[kind][0] if kind in fire_modes.MML_KINDS else fire_modes.ATM_KINDS[kind][0]
                    slot.shot_damage = per * (entry.get("rack_size") or 1)
                if munition in ("homing", "explosive"):          # pods: 2 / 3 per pod, explosive 4 / 6 (p.193)
                    table = EXPLOSIVE_POD_DAMAGE if munition == "explosive" else NARC_POD_DAMAGE
                    slot.missiles_per_shot, slot.shot_damage = 1, table[slot.feeds]
                _update_explosion(slot)
    for w in get_weapons(mech):
        entry = _entry(w.name)
        w.ammo_key = entry["canonical_name"] if entry else None
        w.one_shot = is_one_shot(w)
        w.fired_once = False
        shots = entry.get("shots_per_ton") if entry else None
        w.needs_ammo = not w.one_shot and (isinstance(shots, int) or fire_modes.is_mml(w))
        w.ammo_unknown = (not w.one_shot and shots is None and w.damage_type in ("Ballistic", "Missile")
                          and (w.damage_per_shot or 0) > 0)


def _update_explosion(bin_):
    """Explosion BASE damage = shots left x damage per shot (p.95); an empty
    bin isn't explosive (p.180). Unknown shots keep the 20 default. The caps
    (20 without CASE, CASE / CASE II, p.96) are damage_resolution.apply_explosion's
    (since 2026-10-20 - the base over 20 matters there: armor loss, CASE venting)."""
    if bin_.shots_left is None:
        return
    if bin_.shots_left <= 0:
        bin_.is_explosive = False
        bin_.explosion_damage = 0
    elif bin_.shot_damage is not None:
        bin_.explosion_damage = bin_.shots_left * bin_.shot_damage


# =============================================================================
# ==========================  USE  ============================================
# =============================================================================
def _dead_ids(mech):
    return {info["instance_id"] for info in mech.destroyed_slot_info.values() if info["instance_id"] is not None}


def bins_for(mech, weapon):
    """Live bins holding this weapon's ammo, with shots left (unique).
    Inferno bins excluded (see module docstring)."""
    dead = _dead_ids(mech)
    seen, out = set(), []
    for slots in mech.crits.values():
        for s in slots:
            if (isinstance(s, Equipment) and s.category == "ammo" and id(s) not in seen and id(s) not in dead
                    and not s.exploded and getattr(s, "feeds", None) == weapon.ammo_key and weapon.ammo_key
                    and "INFERNO" not in s.name.upper()
                    and (s.shots_left is None or s.shots_left > 0)):
                seen.add(id(s))
                out.append(s)
    return out


def unavailable_weapons(mech):
    """Weapons that can't fire for lack of ammo: spent one-shots, empty or
    destroyed bins. Identical weapons sharing too few shots: the extras."""
    out = set()
    by_key = {}
    for w in get_weapons(mech):
        if getattr(w, "one_shot", False):
            if w.fired_once:
                out.add(id(w))
        elif getattr(w, "needs_ammo", False):
            by_key.setdefault(w.ammo_key, []).append(w)
    for key, ws in by_key.items():
        bins = bins_for(mech, ws[0])
        shots = float("inf") if any(b.shots_left is None for b in bins) else sum(b.shots_left for b in bins)
        for w in ws[int(min(shots, len(ws))):]:
            out.add(id(w))
    return frozenset(out)


def spend(mech, weapon, munition=None, kind=None):
    """One firing's ammo: marks a one-shot fired, or takes a shot from the
    bin with the fewest shots left - among bins of `munition` (and ammunition
    `kind`) first, when given (INTEGRATION__fire_modes' choice). Returns a log note."""
    return take(mech, weapon, munition, kind)[0]


def take(mech, weapon, munition=None, kind=None):
    """spend() that also returns the munition actually fired: (note, munition).
    With `kind` given, only bins of that kind (an LB-X cluster round is never
    fired from a slug bin); returns "no ammo" when there are none."""
    if getattr(weapon, "one_shot", False):
        weapon.fired_once = True
        return "one-shot: now spent", "standard"
    if getattr(weapon, "ammo_unknown", False):
        stubs.stub_ammo_data(mech.side_name, weapon)
        return "", "standard"
    if not getattr(weapon, "needs_ammo", False):
        return "", "standard"
    bins = bins_for(mech, weapon)
    if kind is not None:
        bins = [b for b in bins if getattr(b, "kind", "") == kind]
    if not bins:
        return "no ammo", munition or "standard"
    preferred = [b for b in bins if getattr(b, "munition", "standard") == munition]
    bins = preferred or bins
    counted = [b for b in bins if b.shots_left is not None]
    if not counted:
        return "", getattr(bins[0], "munition", "standard")
    b = min(counted, key=lambda b: b.shots_left)
    b.shots_left -= 1
    _update_explosion(b)
    return f"{b.name}: {b.shots_left} shots left", getattr(b, "munition", "standard")


def inferno_heat(bin_):
    """2 heat per missile left in an exploding inferno bin, max 30 (p.192)."""
    if bin_.shots_left is None:
        return 30
    return min(30, 2 * bin_.shots_left * bin_.missiles_per_shot)
