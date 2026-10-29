"""
INTEGRATION__kill_curve.py  (NEW 2026-10-29, Claude - Gladiator's fire director)

"How much damage a 'Mech can take", as a curve (Daniel, 2026-10-29):

    f(N) = the chance the 'Mech is mission-killed by N more points of damage,
           from its CURRENT state, landing on one side's hit location table

"I'd still want a function that takes incoming damage and converts it into a %
chance of mission kill. Because splitting fire to wreck 2 units is better then
hard killing 1 and grazing the other ... If we were to rule of thumb it,
estimate the destruction curve using 5 point clusters and use those resulting
values when assigning damage allocation."

How it is estimated: a small Monte Carlo on the engine's own damage code, so
the curve can't disagree with the rules the battle uses. Each trial copies the
'Mech and pours damage into it in config.KILL_CURVE_GROUP-point groups through
attack_resolution._resolve_hit (hit location roll, head hits wound the pilot
p.117, through-armor criticals, damage transfer, critical hits, ammunition
explosions) until it is mission-killed or config.KILL_CURVE_MAX_DAMAGE has
gone in. f(N) is the share of trials killed by N (linear between groups).
Left out, as in a single attack: damage PSRs (falls), consciousness rolls,
heat.

Mission kill (Daniel, 2026-10-29): "no longer able to support its teams
combat operations. Which means an immobile, weaponless torso with a leg on
the ground is still dangerous, if it can spot" - not the book's Crippled
(Core p.228: when a pilot should run). Under the default rules an immobile
'Mech is already destroyed (legs or gyro gone, config.FIGHT_TO_THE_DEATH
off), so the open case is a 'Mech that can still move, kick and spot but has
no gun left. Spotting has no worth yet ("the weight for spotting has not been
evaluated yet"; spotting for indirect fire isn't built), so the choice is a
stub, config.STUB_MISSION_KILL:
  "destroyed"          - mech_state.is_destroyed only (default: a 'Mech that
                         can still move or spot is in the fight).
  "no_ranged_weapons"  - also killed once no ranged weapon is left that can
                         fire (destroyed weapons, or bins gone).

The trials use their own dice (a private INTEGRATION__rng.BattleRNG seeded by
the design, side and state, standing in for config.roll_2d6 / pick_number
while they run), so building a curve never moves the battle's dice
and the same state always gives the same curve. Curves are cached per unit,
side and damage state: a 'Mech that wasn't hit keeps its curves.
"""

import copy
import pickle
import zlib
from bisect import bisect_right

import INTEGRATION__config as config
import INTEGRATION__rng as rng
from mech_state import is_destroyed, DamageType
from damage_resolution import get_weapons
import INTEGRATION__stubs as stubs
import INTEGRATION__timing as timing

_CACHE = {}          # (id(mech), side, state signature, settings) -> sorted damage-at-kill list
_CACHE_LIMIT = 20000     # entries (about 100 numbers each); emptied when full


def clear_cache():
    _CACHE.clear()


def _signature(mech):
    """Everything the damage code reads and changes: armor, structure and destroyed per location,
    the critical slots and the rounds in each bin, and the hit counters. Names only (no ids), so
    the same state seeds the same trials in every run."""
    locs = tuple((name, v.get("armor", 0), v.get("rear_armor", 0), v.get("structure", 0), v.get("destroyed", False))
                 for name, v in mech.locations.items())
    crits = tuple((loc, tuple((str(s), getattr(s, "shots_left", None)) for s in slots))
                  for loc, slots in mech.crits.items())         # rounds left: a bin's blast, and empty guns
    return (locs, crits, mech.pilot_hits, mech.engine_hits, mech.gyro_hits, getattr(mech, "cockpit_hit", False))


def _no_ranged_weapon(mech):
    import INTEGRATION__ammo as ammo
    out = ammo.unavailable_weapons(mech)
    return not any(id(w) not in out for w in get_weapons(mech))


def mission_killed(mech):
    if is_destroyed(mech):
        return True
    policy = config.STUB_MISSION_KILL
    if policy == "destroyed":
        return False
    if policy == "no_ranged_weapons":
        return _no_ranged_weapon(mech)
    raise ValueError(f"Unknown STUB_MISSION_KILL {policy!r} ('destroyed' or 'no_ranged_weapons')")


def _settings():
    return (config.KILL_CURVE_GROUP, config.KILL_CURVE_TRIALS, config.KILL_CURVE_MAX_DAMAGE, config.STUB_MISSION_KILL)


def kills_at(mech, side):
    """Sorted list, one entry per trial: the damage that mission-killed the 'Mech (a trial that
    reached KILL_CURVE_MAX_DAMAGE alive is left out). Cached."""
    import INTEGRATION__attack_resolution as attack_resolution     # attack_resolution imports the bots
    sig = _signature(mech)
    key = (id(mech), side, sig, _settings())
    got = _CACHE.get(key)
    if got is not None:
        return got
    group, trials, cap, _ = _settings()
    stubs.stub_mission_kill(getattr(mech, "side_name", getattr(mech, "name", "?")))
    seed = zlib.crc32(repr((getattr(mech, "name", ""), side, sig)).encode())
    # Own dice: config's roll functions themselves are swapped, so manual rolls (MANUAL_ROLLS) and a
    # test's scripted dice are neither asked nor used up by the trials.
    dice = rng.BattleRNG(seed)
    saved = config.roll_2d6, config.pick_number
    config.roll_2d6 = lambda prompt="": dice.roll_2d6()
    config.pick_number = lambda n, prompt="": dice.pick_number(n)
    try:                    # a trial's copy: unpickling is ~5x faster than copy.deepcopy
        frozen = pickle.dumps(mech, pickle.HIGHEST_PROTOCOL)
        fresh = lambda: pickle.loads(frozen)
    except (pickle.PicklingError, TypeError, AttributeError):
        base = copy.deepcopy(mech)
        fresh = lambda: copy.deepcopy(base)
    killed = []
    try:
        with config.quiet(), timing.section("kill curves"):
            for _ in range(trials):
                m = fresh()
                dealt = 0
                while True:
                    if mission_killed(m):
                        killed.append(dealt)
                        break
                    if dealt >= cap:
                        break
                    attack_resolution._resolve_hit(m, group, DamageType.BALLISTIC, side)
                    dealt += group
    finally:
        config.roll_2d6, config.pick_number = saved
    killed.sort()
    if len(_CACHE) > _CACHE_LIMIT:
        _CACHE.clear()
    _CACHE[key] = killed
    return killed


def chance(mech, side, damage):
    """f(damage): the chance `damage` more points mission-kill the 'Mech (0..1)."""
    killed = kills_at(mech, side)
    trials, group = config.KILL_CURVE_TRIALS, config.KILL_CURVE_GROUP
    if damage <= 0:
        return bisect_right(killed, 0) / trials
    lo = (damage // group) * group
    p_lo = bisect_right(killed, lo) / trials
    p_hi = bisect_right(killed, lo + group) / trials
    return p_lo + (p_hi - p_lo) * (damage - lo) / group


def expected_damage_to_kill(mech, side):
    """The area above the curve up to KILL_CURVE_MAX_DAMAGE: the average damage still needed
    (a trial alive at the cap counts as the cap)."""
    killed = kills_at(mech, side)
    trials, cap = config.KILL_CURVE_TRIALS, config.KILL_CURVE_MAX_DAMAGE
    return (sum(killed) + cap * (trials - len(killed))) / trials


# =============================================================================
# ===========================  THE FIRE DIRECTOR  =============================
# =============================================================================
def worth(target, attacker):
    """config.KILL_CURVE_WEIGHT: what killing `target` is worth - its damage a turn against this
    attacker (INTEGRATION__future_damage, the lifetime objective's rate), or 1."""
    if config.KILL_CURVE_WEIGHT == "none":
        return 1.0
    if config.KILL_CURVE_WEIGHT != "output":
        raise ValueError(f"Unknown KILL_CURVE_WEIGHT {config.KILL_CURVE_WEIGHT!r} ('output' or 'none')")
    import INTEGRATION__future_damage as future_damage
    return max(future_damage.future_damage(target, attacker), 0.0)


def choose_target(attacker, units, terrain_map):
    """Gladiator's fire director (config.STUB_GLADIATOR_TARGET "kill_curve"): the enemy where this
    unit's expected damage (at its real to-hit numbers - the dry run of its own weapon choice) does
    the most, counting what its teammates already declared at it this phase (princess_fire's damage
    map), times the enemy's worth:
        gain = worth x ( f(declared + mine) - f(declared)
                         + KILL_CURVE_PROGRESS_WEIGHT x useful / need )
    f: the enemy's kill curve on the side this unit hits; need: the damage it still needs
    (expected_damage_to_kill); useful: the part of mine within need - declared (overkill pays
    nothing). worth x useful / need is Daniel's "Expected damage output from the target / its
    vulnerability": a fresh Locust needs ~40, a fresh Atlas ~190. The first term is the kill chance added THIS turn: summed over a
    team's sequential picks it favors two 60% kills (120%) over one 100% and a graze (105%). The
    second is softening (Daniel, 2026-10-29: "applying stronger damage vs a unit that needs to be
    softened first"): the share of a kill this damage pays toward later turns - without it a long
    shot adding 1% on a hurt unit beat a full volley into a fresh one. None if nothing can be fired at."""
    import INTEGRATION__attack_resolution as attack_resolution
    import INTEGRATION__princess_fire as princess_fire
    import INTEGRATION__princess_group as princess_group
    best, notes = None, []
    for foe in princess_group.candidates(attacker, units):
        got = attack_resolution.declare_attacks(attacker, foe, terrain_map, attack_resolution.SideReport(), dry=True)
        if got is None:
            continue
        _, mine, side = got
        declared = princess_fire.assigned_damage(attacker.team, foe)
        w = worth(foe, attacker)
        before, after = chance(foe, side, declared), chance(foe, side, declared + mine)
        need = expected_damage_to_kill(foe, side)
        progress = min(mine, max(need - declared, 0.0)) / max(need, config.KILL_CURVE_GROUP)
        score = w * (after - before + config.KILL_CURVE_PROGRESS_WEIGHT * progress)
        notes.append(f"{foe.side_name} ({side}, +{mine:.1f} on {declared:.1f}) kill {before:.0%}->{after:.0%}, "
                     f"softening {progress:.0%} x worth {w:.1f} = {score:.3f}")
        if best is None or score > best[0] + 1e-12:
            best = (score, foe)
    if best is None:
        return None
    config.log(f"  [Ranged] {attacker.side_name} fire director (mission-kill chance, friends' declared "
               f"fire counted): {'; '.join(notes)} -> {best[1].side_name}.")
    return best[1]
