"""
INTEGRATION__stats.py  (NEW 2026-11-06, Claude - output only)

Battle statistics, part 1: the COLLECTOR. While a battle runs it keeps a plain
event log - one row per ranged shot, one per physical attack, one snapshot of
every unit at the end of every turn, and the turn and phase each unit died.
INTEGRATION__stats_report turns a batch's logs into the numbers and the HTML
report; nothing is summed up here, so a new statistic is a new query over the
rows, not a new counter in the engine (Daniel, 2026-11-06: sort the stat lists,
"record events, summarize later").

    config.STATS = True        # default: every battle, even a single one, is logged

Recording only READS the battle (it copies numbers out of the mechs and never
rolls a die or changes a mech), so a battle plays out exactly the same with it
on or off. It costs a little time per shot, so the reference-battle checks
(tests/check_reference_logs.py and the speed benchmark) switch it off.

A battle's log is a plain dict (pickles back from a worker process like the
replay data does) and rides on BattleResult.stats:

    units   {label: {team, name, bot, tons, max_hp}}
    teams   {unit label: team}   and   team_order [team, ...]
    shots   [[turn, attacker, target, weapon, range, tn, roll, hit, damage], ...]
    phys    [[turn, attacker, target, attack, hit, damage], ...]
    turns   [{"turn": n, "units": {label: snapshot}}, ...]   (turn 0 = deployment)
    deaths  {label: [turn, phase, cause]}
    killed_by  {victim label: [attacker label, weapon or attack]}  (the blow that destroyed it;
               a unit lost to a fall, heat or an ammo explosion has none)

A snapshot is {hp, hex, heat, prone, shutdown, destroyed, lost (locations
destroyed), engine, gyro, cockpit, explosions, pilot_hits, crippled}.

Damage on a row is the target's armor + structure lost while that one attack
resolved (the same scalar as everywhere else, PROJECT_MAP Section 5). With
config.POOL_CLUSTER_DAMAGE on, a cluster weapon's damage lands later in one
lump, so those rows read 0 and the lump is logged as a "pooled cluster" row.
"""

from mech_state import is_destroyed


def total_hp(mech):
    """INTEGRATION__attack_resolution.total_hp, imported on first use (that module
    imports this one, so a top-level import would loop)."""
    global total_hp
    from INTEGRATION__attack_resolution import total_hp as real
    total_hp = real
    return real(mech)


# The log of the battle in progress in this process (one battle at a time per
# process; parallel batches record in each worker).
_active = None


def enabled():
    return _active is not None


def start(units, sim):
    """Begin logging a battle (call after the units are built, before deployment)."""
    global _active
    _active = {
        "sim": sim,
        "units": {m.side_name: {"team": getattr(m, "team", m.side_name),
                                "name": f"{m.chassis} {m.model}".strip(),
                                "bot": getattr(m, "bot", "gladiator"),
                                "tons": m.mass,
                                "max_hp": total_hp(m)} for m in units},
        "teams": {m.side_name: getattr(m, "team", m.side_name) for m in units},
        "team_order": list(dict.fromkeys(getattr(m, "team", m.side_name) for m in units)),
        "shots": [], "phys": [], "turns": [], "deaths": {}, "killed_by": {},
        "_turn": 0,
    }


def finish():
    """Stop logging and return the battle's log (None when nothing was logging)."""
    global _active
    data, _active = _active, None
    if data is not None:
        data.pop("_turn", None)
    return data


def set_turn(turn):
    if _active is not None:
        _active["_turn"] = turn


def hp_before(target):
    """The target's total HP before an attack, or None when not logging
    (hand it back to shot() / physical())."""
    return total_hp(target) if _active is not None else None


def shot(attacker, target, attack, before, distance):
    """One ranged attack, hit or miss (`attack` is a DeclaredAttack)."""
    if _active is None:
        return
    dmg = before - total_hp(target)
    _active["shots"].append([_active["_turn"], attacker.side_name, target.side_name, attack.weapon.name, distance,
                             attack.tn, attack.roll, bool(attack.hit), dmg])
    _credit_kill(attacker, target, attack.weapon.name, dmg)


def pooled(attacker, target, name, before):
    """Cluster damage that was pooled and applied in one lump (POOL_CLUSTER_DAMAGE)."""
    if _active is None:
        return
    dmg = before - total_hp(target)
    _active["shots"].append([_active["_turn"], attacker.side_name, target.side_name, name, None, None, None,
                             True, dmg])
    _credit_kill(attacker, target, name, dmg)


def physical(attacker, target, name, hit, before):
    """One physical attack (punch, kick, club, charge, DFA, push...), its damage
    the target's HP lost during its resolution."""
    if _active is None:
        return
    dmg = 0 if before is None else before - total_hp(target)
    _active["phys"].append([_active["_turn"], attacker.side_name, target.side_name, name, bool(hit), dmg])
    _credit_kill(attacker, target, name, dmg)


def _credit_kill(attacker, target, name, dmg):
    """The first attack that leaves a target destroyed is its killer."""
    if dmg and target.side_name not in _active["killed_by"] and is_destroyed(target):
        _active["killed_by"][target.side_name] = [attacker.side_name, name]


def note_deaths(units, phase):
    """Record the turn and phase each newly destroyed unit went down, and why."""
    if _active is None:
        return
    for m in units:
        if m.side_name not in _active["deaths"] and is_destroyed(m):
            _active["deaths"][m.side_name] = [_active["_turn"], phase, m.cause_of_death]


def snapshot(turn, units):
    """Every unit's state at a turn's end (turn 0 = after deployment)."""
    if _active is None:
        return
    _active["turns"].append({"turn": turn, "units": {m.side_name: _unit_state(m) for m in units}})


def _unit_state(m):
    return {
        "hp": total_hp(m),
        "hex": m.hex,
        "heat": getattr(m, "current_heat", 0),
        "prone": bool(getattr(m, "prone", False)),
        "shutdown": bool(getattr(m, "shutdown", False)),
        "destroyed": bool(is_destroyed(m)),
        "lost": [loc for loc, v in m.locations.items() if v.get("destroyed")],
        "engine": getattr(m, "engine_hits", 0),
        "gyro": getattr(m, "gyro_hits", 0),
        "cockpit": bool(getattr(m, "cockpit_hit", False)),
        "explosions": getattr(m, "explosions", 0),
        "pilot_hits": getattr(m, "pilot_hits", 0),
        "crippled": bool(getattr(m, "crippled", False)),
    }
