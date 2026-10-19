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

EXPLOSION_CAP = 20   # p.96 (without CASE)

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
    for location, slots in mech.crits.items():
        for slot in slots:
            if isinstance(slot, Equipment) and slot.category == "ammo" and not hasattr(slot, "feeds"):
                entry = weapon_entry_for_ammo(slot.name)
                slot.feeds = entry["canonical_name"] if entry else None
                shots = entry.get("shots_per_ton") if entry else None
                slot.shots_left = shots if isinstance(shots, int) else None     # None = unknown: unlimited
                slot.missiles_per_shot = (entry.get("rack_size") or 1) if entry and entry.get("damage_type") == "Missile" else 1
                slot.shot_damage = damage_per_shot(entry)
                _update_explosion(slot)
    for w in get_weapons(mech):
        entry = _entry(w.name)
        w.ammo_key = entry["canonical_name"] if entry else None
        w.one_shot = is_one_shot(w)
        w.fired_once = False
        shots = entry.get("shots_per_ton") if entry else None
        w.needs_ammo = not w.one_shot and isinstance(shots, int)
        w.ammo_unknown = (not w.one_shot and shots is None and w.damage_type in ("Ballistic", "Missile")
                          and (w.damage_per_shot or 0) > 0)


def _update_explosion(bin_):
    """Explosion damage = shots left x damage per shot, capped at 20 (p.96);
    an empty bin isn't explosive (p.180). Unknown shots keep the 20 default."""
    if bin_.shots_left is None:
        return
    if bin_.shots_left <= 0:
        bin_.is_explosive = False
        bin_.explosion_damage = 0
    elif bin_.shot_damage is not None:
        bin_.explosion_damage = min(EXPLOSION_CAP, bin_.shots_left * bin_.shot_damage)


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


def spend(mech, weapon):
    """One firing's ammo: marks a one-shot fired, or takes a shot from the
    bin with the fewest shots left. Returns a log note."""
    if getattr(weapon, "one_shot", False):
        weapon.fired_once = True
        return "one-shot: now spent"
    if getattr(weapon, "ammo_unknown", False):
        stubs.stub_ammo_data(mech.side_name, weapon)
        return ""
    if not getattr(weapon, "needs_ammo", False):
        return ""
    bins = bins_for(mech, weapon)
    if not bins:
        return "no ammo"
    counted = [b for b in bins if b.shots_left is not None]
    if not counted:
        return ""
    b = min(counted, key=lambda b: b.shots_left)
    b.shots_left -= 1
    _update_explosion(b)
    return f"{b.name}: {b.shots_left} shots left"


def inferno_heat(bin_):
    """2 heat per missile left in an exploding inferno bin, max 30 (p.192)."""
    if bin_.shots_left is None:
        return 30
    return min(30, 2 * bin_.shots_left * bin_.missiles_per_shot)
