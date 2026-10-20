"""
INTEGRATION__electronics.py  (NEW 2026-10-20, Claude - Pile 2 rules, Pile 4 munition choice)

Artemis IV / V fire control, Narc / iNarc missile beacons, and the ECM that
blocks both (Core Rulebook pp.186-188, 191-193, 197, 200, 202, 209).

=== ARTEMIS (p.197; munitions p.192) ===
  - An Artemis FCS is LINKED to one launcher (p.180): it benefits only that
    launcher, and losing the FCS to a critical hit leaves the launcher working
    without it. The .mtf file puts each FCS slot in its launcher's location;
    linking pairs them in slot order within a location (any FCS left over goes
    to a launcher with none). Never a Streak.
  - Artemis IV-equipped missiles (an "Artemis-capable" bin) from a launcher
    with a live Artemis IV FCS: +2 on the Cluster Hits Table. Artemis V
    ("Artemis V-capable", Clan): -1 to-hit and +3. Each kind of missile gets
    nothing from the other kind's FCS.
  - ATMs have Artemis IV built in: +2 (p.186).
  - Blocked by ECM hostile to the attacker when the attacker or the target is
    inside it (p.200): the missiles fire as normal ones.

=== NARC (pp.188, 193) ===
  - A Narc / iNarc beacon (Type M - AMS can engage it, as a single missile)
    that hits attaches a pod in the location struck (hit location roll; a leg
    hit behind partial cover strikes the cover). Homing pods take effect in
    the phase after they hit, last the whole battle, and are lost when their
    location is destroyed. More pods add nothing (p.193).
  - Narc-equipped missiles ("Narc-capable" bins; LRM, SRM, MML, NLRM,
    Thunderbolt) at a target with a working homing pod: -1 to-hit and +2 on
    the Cluster Hits Table (if a Cluster weapon).
  - Lost while the target is inside ECM hostile to the pod's controller: in a
    duel, the target's own ECM (p.200). The beacon itself isn't affected.
  - Explosive pods (Narc 4, iNarc 6 damage, p.193) do damage and attach
    nothing. iNarc ECM / haywire / Nemesis pods aren't modeled (no unit in
    data/meks.zip carries them; INTEGRATION__ammo leaves their bins unlinked).

=== ECM (pp.200-201, 202, 209) ===
  - Guardian / Clan ECM / Angel / Watchdog: an effect radius of 6 (Watchdog
    5) hexes around the mech carrying it, hostile to its enemies. In a duel
    the ECM mech is always inside its own radius, so the radius never
    matters: an enemy's working ECM blocks the attacker's Artemis (target
    inside it) and the attacker's Narc pods on it.
  - Angel ECM also unlocks Streaks fired at a target inside it (or from inside
    it): on a hit they roll on the Cluster Hits Table like standard launchers.
  - No ECM works while shut down (p.104) or while any stealth system other
    than the Chameleon LPS is active (p.209: no hostile ECM field). Active
    stealth armor and Void-Signature systems also put their own mech "as if"
    inside hostile ECM (pp.202, 209): its own Artemis is blocked.
  - ECM is always on (Daniel's default for activated systems, 2026-10-19).

=== BOT CHOICES (pile 4, PROJECT_MAP Section 6) ===
  - Munition per shot (a launcher may have several kinds of bin): a STUB
    decision since 2026-10-20 (Daniel: which ammo to use is still research) -
    INTEGRATION__fire_modes lists the options, stubs.stub_munition_choice
    picks; special missiles fire as normal ones when their bonus is blocked.
  - A homing pod's worth (Daniel, 2026-10-20: "a NARC's 'Damage value' to an
    AMS should probably be considered the expected increase in damage from
    its opponents missile systems if it lands. If one has already landed no
    delta change"): the expected damage the pod's owner's Narc-capable
    launchers gain from it in one turn, judged at this turn's range and to-hit
    numbers (heat ignored) - 0 if a pod from it is already on the target (or
    pending) or the target's ECM would block it. Used to decide whether to
    fire the beacon (x P(hit)) and, for the target, whether its AMS engages
    the pod (x 1/2: the 1D6 4+ kill). One turn only - the pod's later turns
    wait on the future-capability Memo (Section 6).
"""

from typing import NamedTuple

import INTEGRATION__config as config
import INTEGRATION__weapon_rules as weapon_rules
import INTEGRATION__equipment_systems as equip
import INTEGRATION__ammo as ammo
from equipment import Equipment
from damage_resolution import get_weapons

ARTEMIS_BONUS = {4: (0, 2), 5: (-1, 3)}     # FCS kind -> (TN, Cluster Hits Table) - p.197
ATM_CLUSTER = 2                              # built-in Artemis IV, p.186
NARC_TN, NARC_CLUSTER = -1, 2                # homing pod, p.193
SINGLE_MISSILE_KILL_CHANCE = 0.5             # AMS 1D6 4+ (p.206)


class FireControl(NamedTuple):
    munition: str = "standard"
    tn: int = 0                  # to-hit modifier
    cluster: int = 0             # Cluster Hits Table modifier (on top of the weapon's own, e.g. MRM -1)
    streak_lock: bool = True     # False: Angel ECM - a Streak rolls on the table like a standard launcher
    note: str = ""


PLAIN = FireControl()


def _norm(name):
    return (name or "").replace(" ", "").replace("-", "").upper()


def _dead(mech):
    return {info["instance_id"] for info in mech.destroyed_slot_info.values() if info["instance_id"] is not None}


# =============================================================================
# ==========================  SETUP  ==========================================
# =============================================================================
def is_narc(weapon):
    return "NARC" in weapon_rules.canonical_name(weapon)


def is_atm(weapon):
    return "ATM" in weapon_rules.canonical_name(weapon)


def _artemis_kind(slot):
    if not isinstance(slot, Equipment) or slot.category == "ammo":
        return None
    n = _norm(slot.name)
    return 5 if "ARTEMISV" in n else (4 if "ARTEMISIV" in n else None)


def _is_ecm(slot):
    if not isinstance(slot, Equipment) or slot.category == "ammo":
        return False
    n = _norm(slot.name)
    return "ECM" in n or "WATCHDOG" in n


def attach(mech):
    """Once per battle (fresh clone): link Artemis FCS to launchers, find the
    ECM suites, clear the pods."""
    mech.narc_pods = []
    mech.ecm_suites = []
    seen = set()
    fcs_by_loc, launchers_by_loc = {}, {}
    for loc, slots in mech.crits.items():
        for slot in slots:
            if not isinstance(slot, Equipment) or id(slot) in seen:
                continue
            seen.add(id(slot))
            kind = _artemis_kind(slot)
            if kind:
                fcs_by_loc.setdefault(loc, []).append((slot, kind))
            elif _is_ecm(slot):
                mech.ecm_suites.append(slot)
            elif (slot.category == "weapon" and weapon_rules.is_cluster(slot) and not weapon_rules.is_streak(slot)
                  and not is_narc(slot) and not is_atm(slot) and not weapon_rules.is_ams(slot)):
                launchers_by_loc.setdefault(loc, []).append(slot)
    leftover_fcs, leftover_launchers = [], []
    for loc in mech.crits:
        fcs, launchers = fcs_by_loc.get(loc, []), launchers_by_loc.get(loc, [])
        for (slot, kind), w in zip(fcs, launchers):
            w.artemis = (slot, kind)
        leftover_fcs += fcs[len(launchers):]
        leftover_launchers += launchers[len(fcs):]
    for (slot, kind), w in zip(leftover_fcs, leftover_launchers):
        w.artemis = (slot, kind)


def artemis_kind(mech, weapon):
    """4 / 5 for a live linked FCS, else None."""
    link = getattr(weapon, "artemis", None)
    if link is None or id(link[0]) in _dead(mech):
        return None
    return link[1]


# =============================================================================
# ==========================  ECM  ============================================
# =============================================================================
def live_ecm(mech):
    dead = _dead(mech)
    return [s for s in getattr(mech, "ecm_suites", ()) if id(s) not in dead]


def hostile_field(mech):
    """Does this mech's ECM jam its enemies right now? (p.200; p.104 shut
    down; p.209 an active stealth system other than the Chameleon LPS)"""
    if mech.shutdown or not live_ecm(mech):
        return False
    return not any(k != "chameleon" for k in equip.active_stealth(mech))


def angel_field(mech):
    return hostile_field(mech) and any("ANGEL" in _norm(s.name) for s in live_ecm(mech))


def as_if_jammed(mech):
    """Active stealth armor / Void-Signature: the mech suffers hostile-ECM
    effects itself (pp.202, 209)."""
    return any(k in ("stealth_armor", "void_signature") for k in equip.active_stealth(mech))


def artemis_blocked(attacker, target):
    return hostile_field(target) or as_if_jammed(attacker)


def narc_blocked(target):
    """The pod on `target` lies inside ECM hostile to its controller - the
    target's own (p.200)."""
    return hostile_field(target)


# =============================================================================
# ==========================  NARC PODS  ======================================
# =============================================================================
def _live_pods(target, owner_side, effective_only):
    return [p for p in getattr(target, "narc_pods", ())
            if p["owner"] == owner_side and not target.locations[p["location"]]["destroyed"]
            and (p["effective"] or not effective_only)]


def homing_working(attacker, target):
    """A working homing pod from `attacker` on `target` (p.193)."""
    return bool(_live_pods(target, attacker.side_name, True)) and not narc_blocked(target)


def attach_pod(target, location, owner_side):
    target.narc_pods.append({"location": location, "owner": owner_side, "effective": False})


def activate_pods(mech):
    """End of the Ranged phase: pods that hit take effect from the next phase (p.193)."""
    for p in getattr(mech, "narc_pods", ()):
        p["effective"] = True


# =============================================================================
# ==========================  FIRE CONTROL PER SHOT  ==========================
# =============================================================================
def munitions(mech, weapon):
    """Munition kinds the weapon can fire right now (live bins with shots)."""
    if not getattr(weapon, "needs_ammo", False):
        return {"standard"}
    return {getattr(b, "munition", "standard") for b in ammo.bins_for(mech, weapon)}


def control_for(attacker, weapon, target, munition):
    """FireControl of `weapon` firing `munition` at `target` now."""
    if weapon.damage_type != "Missile":
        return PLAIN
    lock = not (weapon_rules.is_streak(weapon) and angel_field(target))
    cluster_weapon = weapon_rules.is_cluster(weapon)
    tn, cluster, note = 0, 0, ""
    if is_atm(weapon):
        if not artemis_blocked(attacker, target):
            cluster, note = ATM_CLUSTER, "ATM Artemis"
    elif munition == "narc" and homing_working(attacker, target):
        tn, cluster, note = NARC_TN, (NARC_CLUSTER if cluster_weapon else 0), "Narc homing"
    elif munition in ("artemis4", "artemis5"):
        kind = int(munition[-1])
        if artemis_kind(attacker, weapon) == kind and not artemis_blocked(attacker, target):
            tn, cluster = ARTEMIS_BONUS[kind]
            note = f"Artemis {'IV' if kind == 4 else 'V'}"
    if not lock:
        note = (note + ", " if note else "") + "Angel ECM: no Streak lock"
    return FireControl(munition, tn, cluster, lock, note)


# =============================================================================
# ==========================  EXPECTED DAMAGE  ================================
# =============================================================================
def pod_value(owner, target, distance, pre_tn, adjust):
    """A homing pod's worth to `owner` (module docstring): the one-turn gain
    of its Narc-capable launchers - for each, the best Narc-homing shot it
    could fire minus the best shot it fires now (INTEGRATION__fire_modes
    prices both; adjust is attack_resolution.tn_adjuster's)."""
    import INTEGRATION__fire_modes as fire_modes                 # fire_modes imports this module
    if narc_blocked(target) or _live_pods(target, owner.side_name, False):
        return 0.0
    planner = fire_modes.Planner(owner, target, adjust)
    blocked = ammo.unavailable_weapons(owner) | fire_modes.jammed_ids(owner)
    total = 0.0
    for w in get_weapons(owner):
        if id(w) in blocked or w.damage_type != "Missile" or is_narc(w):
            continue
        plans = planner.kinds(w)
        narc = [p for p in plans if p.munition == "narc"]
        if not narc:
            continue
        now = max((v[0] for v in (planner.value(w, p, distance, pre_tn) for p in plans) if v), default=0.0)
        homing = narc[0]._replace(guidance=FireControl(
            "narc", NARC_TN, NARC_CLUSTER if weapon_rules.is_cluster(w) else 0, narc[0].guidance.streak_lock, "Narc homing"))
        got = planner.value(w, homing, distance, pre_tn)
        if got is not None:
            total += max(0.0, got[0] - now)
    return total


def log_controls(name, plans, weapons):
    """One log line naming each fired weapon's shot plan, when it isn't plain."""
    notes = sorted({f"{w.name}: {plans[id(w)].note}" for w in weapons if id(w) in plans and plans[id(w)].note})
    if notes:
        config.log(f"    [{name} fire control] {'; '.join(notes)}")
