"""INTEGRATION__smoke.py - smoke on the board, and active probes seeing
through it (NEW 2026-10-27, Claude; RULES_REVIEW G34 - Daniel: "Active probes
and TAG could have a use in a 1 on 1 fight when smoke and homing ammo is
included"). The first smoke source a unit in data/meks.zip carries is the
Hyper-Velocity Autocannon (TO:AUE p.97, INTEGRATION__advanced_weapons).

Smoke (Core p.124; TO:AR p.45):
  - Light or heavy; two light clouds in a hex count as heavy (TO:AR p.45);
    new smoke on heavy smoke adds nothing (Core p.190).
  - Rises 2 levels above the hex's ground (pathfinder/los.py; a water hex's
    surface, not its floor).
  - Light acts as light woods, heavy as heavy woods for LOS and to-hit, but
    smoke never raises a hex's intervening points past 2, nor a target hex's
    modifier past +2, woods included (Core p.124) - los.py.
  - Each cloud lasts as long as its source says (`until`: removed in that
    turn's End Phase). Wind, drift and the TO:AR dissipation roll are
    optional rules (TO:AR pp.45-46) - not built.
Active probes (Core pp.124, 197): a 'Mech with a working active probe
ignores smoke's to-hit modifier (not its LOS effect) in hexes within the
probe's range - Light 3, Beagle 4, Clan 5, Bloodhound 8; the Watchdog as
the Clan probe, 5 (Core p.201 and its table; TO:AUE p.90 says "Light Active
Probes" - the newer Core is followed) - unless the probe is inside a hostile
ECM radius: 6 hexes, the Watchdog's too ("same radius ... as Clan standard
ECM", Core p.201; INTEGRATION__electronics' docstring says 5, which never
mattered there); the Bloodhound is stopped only by Angel ECM. probe_relief() works
it out for an attack; movement scoring doesn't price it.

Smoke lives on the battle's board (info["smoke"]); set_board clears what an
earlier battle left. Changing smoke empties the LOS caches.
"""

import INTEGRATION__config as config
import INTEGRATION__los_cache as geo_cache

LIGHT, HEAVY = "1", "2"           # the woods densities smoke acts as (Core p.124)

_BOARD = None
_SMOKY = set()                    # labels with smoke now


def set_board(terrain_map):
    """The battle's board (orchestrator.run_battle): no smoke yet."""
    global _BOARD
    if _BOARD is not None:
        for label in _SMOKY:
            _BOARD["hexes"][label].pop("smoke", None)
    _SMOKY.clear()
    _BOARD = terrain_map
    geo_cache.invalidate_rust()           # the Rust line of sight reads a snapshot of the board's smoke


def _changed():
    geo_cache.invalidate_rust()
    if _BOARD is not None:
        geo_cache.board(_BOARD).clear()


def add(label, density, until, source):
    """Smoke in `label` until the End Phase of turn `until`."""
    if _BOARD is None or label not in _BOARD["hexes"]:
        return
    info = _BOARD["hexes"][label]
    old = info.get("smoke")
    if old is None:
        new = {"density": density, "until": until}
    else:
        # Two light clouds are heavy (TO:AR p.45); on heavy smoke, more adds nothing (Core p.190).
        new = {"density": HEAVY, "until": max(old["until"], until)}
    info["smoke"] = new
    _SMOKY.add(label)
    if new == old:
        return
    config.log(f"      {'Heavy' if new['density'] == HEAVY else 'Light'} smoke fills {label} "
               f"(from {source}; until the End Phase of turn {new['until']}).")
    _changed()


def end_phase(turn):
    """Clouds whose time is up blow away."""
    gone = [label for label in _SMOKY if _BOARD["hexes"][label]["smoke"]["until"] <= turn]
    for label in gone:
        _BOARD["hexes"][label].pop("smoke")
        _SMOKY.discard(label)
        config.log(f"  [End] The smoke at {label} clears.")
    if gone:
        _changed()


# =============================================================================
# ==========================  ACTIVE PROBES  ==================================
# =============================================================================
PROBE_RANGES = (("BLOODHOUND", 8), ("BEAGLE", 4), ("CLLIGHTACTIVEPROBE", 3), ("LIGHTACTIVEPROBE", 3),
                ("WATCHDOG", 5), ("ACTIVEPROBE", 5))     # first match wins (Core p.197)
ECM_RADIUS = 6                                            # Core pp.200-201 (Watchdog too)


def _norm(name):
    return (name or "").replace(" ", "").replace("-", "").upper()


def probe(mech):
    """(range, is_bloodhound) of the 'Mech's working active probe, or None."""
    from equipment import Equipment
    dead = {info["instance_id"] for info in mech.destroyed_slot_info.values()}
    best = None
    for slots in mech.crits.values():
        for s in slots:
            if not isinstance(s, Equipment) or id(s) in dead or s.category == "ammo":
                continue
            n = _norm(s.name)
            for key, rng in PROBE_RANGES:
                if key in n:
                    if best is None or rng > best[0]:
                        best = (rng, key == "BLOODHOUND")
                    break
    return best


def _jammed(attacker, target, distance, bloodhound):
    """Is the attacker's probe inside the target's hostile ECM radius?"""
    import INTEGRATION__electronics as electronics
    if electronics.as_if_jammed(attacker):
        return True
    if not electronics.hostile_field(target):
        return False
    if bloodhound and not electronics.angel_field(target):
        return False
    return distance <= ECM_RADIUS


def probe_relief(attacker, target, trace, distance):
    """The smoke to-hit points the attacker's probe ignores on this line
    (los.LOSStep.smoke_contrib within the probe's range)."""
    if attacker.shutdown or not trace.result.los:
        return 0
    got = probe(attacker)
    if got is None or not any(step.smoke_contrib for step in trace.steps):
        return 0
    rng, bloodhound = got
    if _jammed(attacker, target, distance, bloodhound):
        return 0
    return sum(step.smoke_contrib for step in trace.steps if 0 < step.index <= rng)
