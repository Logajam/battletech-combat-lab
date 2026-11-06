"""
INTEGRATION__results.py  (NEW 2026-10-18, Claude - Pile 1)

BattleResult (moved here from the orchestrator and extended) and the batch
summary for PROJECT_MAP Section 1's stats: win rate, survivor condition,
attacks-to-kill, cause of death - plus the stub report, which is printed
at the top AND bottom of every summary so a result can't be read without
seeing which placeholders produced it.

HP = armor + rear armor + structure (Daniel, PROJECT_MAP Section 5).
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Rules that are missing with no runtime stub to flag them (either a whole
# deferred phase that IS stubbed elsewhere, or a gap that can't be detected
# per-attack). Printed with every summary.
KNOWN_MISSING_RULES = [
    "The twist / flip a TAG designation would use up (TAG fires as the 'Mech faces). Firing arcs, torso twists "
    "(both attack phases, tripods any hexside), tripod leg arcs, reversing arms, Quad Turrets and shoulder / head "
    "turrets (TO:AUE p.159) are applied",
    "Munitions not modeled: AC armor-piercing / caseless / flak / precision rounds (fired as standard), iNarc ECM / "
    "haywire / Nemesis pods, Arrow IV special rounds but homing; semi-guided missiles; distant (18+ hex) Arrow IV fire, bombast laser "
    "charging, HAG flak; PPC capacitor charging is a stub, off by default; Interstellar Operations (2026-10-28): a TSEMP hit's effect is priced at TSEMP_EFFECT_WORTH and IMP effects at IMP_EFFECT_WORTH (placeholders), the TSEMP's own interference isn't priced, iATM indirect fire (needs a spotter) and IIW / IMP bins in the heat-explosion rolls (as normal ammo) - not built, a nail gun is priced as if hitting the front; 'Mech mortar shells other than armor-piercing, fluid gun / VGL ammo other than water / fragmentation (no unit carries them); a Taser hit's effect is priced at TASER_EFFECT_WORTH (placeholder); mortar indirect fire and active probes against smoke aren't priced in movement scoring; Thumper / Sniper artillery fire as Arrow IV (Daniel); "
    "a Narc homing pod is valued for one turn and not in movement scoring; hex attacks (Arrow IV, Apollo "
    "saturation) aren't priced in movement scoring; outside heat on the target is priced at TARGET_HEAT_WORTH",
    "Movement subphase (G20): mud's -1 isn't priced in movement scoring",
    "TO:AR terrain (2026-10-27): magma eruptions, hazardous pool flow, smoke drift / wind are optional rules - not "
    "built; magma heat and the chance of bogging down aren't priced in movement scoring; bridges, fuel tanks and elevators wait on the full "
    "building rules. Deferred (Daniel, 2026-10-28): 'Mech UMUs (underwater submarine movement), the chain whip's "
    "arm grapple (TO:AR grappling), industrial tools (TechManual / Total Warfare). LAMs don't load. Superheavies "
    "(Core p.240): building rules, foliage and friendly-unit hexes not built; bot LOS estimates outside ranged "
    "movement scoring use standard 'Mech heights",
    "Heat sources/sinks with no terrain model yet: snow, fire, extreme temperatures (water: built 2026-10-21); "
    "inferno missiles setting hexes on fire",
    "Heat decisions (bot logic, later): cooldown (a mech at max_heat stays there), voluntary "
    "shutdown; equipment uses Daniel's defaults (stealth always on, 1-on/1-off radical/MASC/"
    "supercharger, coolant pod when above min_heat, aimed shots at config.AIMED_SHOT_LOCATION)",
    "Physical attacks: all seven types are built; not priced in movement scoring: the PSRs a hit forces (only "
    "Movement-phase PSRs count), picking up a club as part of the plan",
]


@dataclass
class SideStats:
    name: str = ""
    max_hp: float = 0.0
    final_hp: float = 0.0
    destroyed: bool = False
    cause_of_death: Optional[str] = None
    crippled_at: Optional[int] = None
    attacks: int = 0
    hits: int = 0
    damage_dealt: float = 0.0
    final_hex: str = ""
    units: int = 1                 # how many 'Mechs these stats cover (a team's total, 2026-10-28)
    units_lost: int = 0            # ... and how many of them were destroyed


@dataclass
class BattleResult:
    """One battle's outcome. `destroyed` is "Red"/"Blue"/"Both"/None -
    naming WHICH SIDE was destroyed (i.e. "Red" means Red lost), not who
    won. None means max_turns was reached with both mechs still standing.
    `winner` is the surviving side, "Draw" (both destroyed or time-out)."""
    turns_taken: int = 0
    destroyed: Optional[str] = None
    winner: str = "Draw"
    red: SideStats = field(default_factory=SideStats)
    blue: SideStats = field(default_factory=SideStats)
    # Multi-unit battles (2026-10-28, INTEGRATION__forces): totals per team and the stats of each
    # unit by its label. `red` / `blue` are the teams called "Red" / "Blue" (a team's own stats
    # when it has one unit). With several teams `destroyed` names the eliminated ones joined by
    # "+" ("All" when none is left) and `winner` is the one team still standing, else "Draw".
    teams: Dict[str, SideStats] = field(default_factory=dict)
    units: Dict[str, SideStats] = field(default_factory=dict)
    active_stubs: Dict[str, int] = field(default_factory=dict)
    seed: Optional[int] = None   # this battle's own seed: SEED = seed, NUM_SIMULATIONS = 1 replays it
    replay: Optional[dict] = None  # INTEGRATION__replay data when config.REPLAY_BATTLES covered this battle
    stats: Optional[dict] = None   # INTEGRATION__stats event log when config.STATS is on
    timing: Optional[dict] = None  # INTEGRATION__timing section totals (config.TIMING)
    turn_cap: Optional[int] = None  # the max_turns this battle ran under
    profile: Optional[dict] = None  # raw cProfile stats (config.PROFILE_FUNCTIONS > 0)

    # Old field names kept so anything written against the 2026-08-30
    # skeleton still reads.
    @property
    def red_cause_of_death(self):
        return self.red.cause_of_death

    @property
    def blue_cause_of_death(self):
        return self.blue.cause_of_death


def _stub_banner(stub_totals: Counter, stub_battles: Counter, n_battles: int):
    lines = ["!" * 70,
             "!! RESULTS PRODUCED WITH STUBS ACTIVE - NOT RULES-COMPLETE",
             "!! Stubs that ran:"]
    for name, count in sorted(stub_totals.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"!!   {name:<30} {count:>7} runs, in {stub_battles[name]}/{n_battles} battle(s)")
    if not stub_totals:
        lines.append("!!   (none)")
    lines.append("!! Known missing rules with no runtime flag:")
    for r in KNOWN_MISSING_RULES:
        lines.append(f"!!   - {r}")
    lines.append("!" * 70)
    return "\n".join(lines)


def summarize(results: List[BattleResult], red_label: str, blue_label: str) -> dict:
    """Prints the batch summary and returns it as a plain dict."""
    n = len(results)
    stub_totals = Counter()
    stub_battles = Counter()
    for r in results:
        for name, c in r.active_stubs.items():
            stub_totals[name] += c
            stub_battles[name] += 1

    wins = Counter(r.winner for r in results)
    causes = Counter()
    for r in results:
        for s in (r.red, r.blue):
            if s.destroyed:
                causes[f"{s.name}: {s.cause_of_death}"] += 1

    def avg(xs):
        xs = list(xs)
        return sum(xs) / len(xs) if xs else 0.0

    decisive = [r for r in results if r.winner in ("Red", "Blue")]
    attacks_to_kill = []
    for r in decisive:
        killer = r.red if r.winner == "Red" else r.blue
        attacks_to_kill.append(killer.attacks)

    summary = {
        "n": n,
        "wins": dict(wins),
        "avg_turns": avg(r.turns_taken for r in results),
        "avg_turns_decisive": avg(r.turns_taken for r in decisive),
        "causes_of_death": dict(causes),
        "avg_attacks_to_kill": avg(attacks_to_kill),
        "red_avg_final_hp_pct": avg(100 * r.red.final_hp / r.red.max_hp for r in results if r.red.max_hp),
        "blue_avg_final_hp_pct": avg(100 * r.blue.final_hp / r.blue.max_hp for r in results if r.blue.max_hp),
        "red_avg_hit_rate": avg(r.red.hits / r.red.attacks for r in results if r.red.attacks),
        "blue_avg_hit_rate": avg(r.blue.hits / r.blue.attacks for r in results if r.blue.attacks),
        "active_stubs": dict(stub_totals),
        "active_stubs_battles": dict(stub_battles),
    }

    banner = _stub_banner(stub_totals, stub_battles, n)
    print("\n" + banner)
    print("\n" + "#" * 70)
    print(f"BATCH SUMMARY - {n} battle(s): Red = {red_label}, Blue = {blue_label}")
    print("#" * 70)
    print(f"  Wins:  Red {wins.get('Red', 0)}   Blue {wins.get('Blue', 0)}   Draw {wins.get('Draw', 0)}")
    print(f"  Average turns: {summary['avg_turns']:.1f} (decisive battles only: {summary['avg_turns_decisive']:.1f})")
    print(f"  Average attacks fired by the winner before the kill: {summary['avg_attacks_to_kill']:.1f}")
    print(f"  Average remaining HP (armor+structure): Red {summary['red_avg_final_hp_pct']:.0f}%   "
          f"Blue {summary['blue_avg_final_hp_pct']:.0f}%")
    print(f"  Hit rate: Red {100 * summary['red_avg_hit_rate']:.0f}%   Blue {100 * summary['blue_avg_hit_rate']:.0f}%")
    print("  Causes of death:")
    for cause, c in causes.most_common():
        print(f"    {cause}: {c}")
    if not causes:
        print("    (none)")
    # Daniel (2026-10-21): "No real fight should last that long. If it does it
    # deserves to be noted as a possible flaw."
    capped = [r for r in results if r.destroyed is None and r.turn_cap and r.turns_taken >= r.turn_cap]
    if capped:
        print(f"  !! {len(capped)} battle(s) reached the {capped[0].turn_cap}-turn cap with both mechs standing - "
              f"a possible flaw (a stall?)")
    summary["turn_cap_reached"] = len(capped)
    if n <= 10:
        print("  Per battle:")
        for i, r in enumerate(results, start=1):
            print(f"    #{i}: {r.turns_taken} turns, winner {r.winner}; "
                  f"Red {r.red.final_hp:g}/{r.red.max_hp:g} HP ({r.red.hits}/{r.red.attacks} hits, "
                  f"{r.red.damage_dealt:g} dealt){' DESTROYED: ' + r.red.cause_of_death if r.red.destroyed else ''}; "
                  f"Blue {r.blue.final_hp:g}/{r.blue.max_hp:g} HP ({r.blue.hits}/{r.blue.attacks} hits, "
                  f"{r.blue.damage_dealt:g} dealt){' DESTROYED: ' + r.blue.cause_of_death if r.blue.destroyed else ''}")
    print("\n" + banner)
    return summary


# =============================================================================
# ==========================  MULTI-UNIT BATTLES (2026-10-28)  ===============
# =============================================================================
def team_totals(team: str, members: List[SideStats]) -> SideStats:
    """One team's stats from its units' (a single unit's own stats come back
    as they are, so a two-'Mech battle reads exactly as it always did)."""
    if len(members) == 1:
        return members[0]
    crippled = [m.crippled_at for m in members if m.crippled_at is not None]
    return SideStats(
        name=f"{team} ({len(members)} units)",
        max_hp=sum(m.max_hp for m in members),
        final_hp=sum(m.final_hp for m in members),
        destroyed=all(m.destroyed for m in members),
        crippled_at=min(crippled) if crippled else None,
        attacks=sum(m.attacks for m in members),
        hits=sum(m.hits for m in members),
        damage_dealt=sum(m.damage_dealt for m in members),
        units=len(members),
        units_lost=sum(1 for m in members if m.destroyed),
    )


def summarize_teams(results: List[BattleResult], team_labels: Dict[str, str]) -> dict:
    """The batch summary for any number of teams (the two-'Mech Red / Blue
    battle keeps `summarize`'s layout). team_labels: team -> what it fielded."""
    n = len(results)
    teams = list(team_labels)
    stub_totals = Counter()
    stub_battles = Counter()
    for r in results:
        for name, c in r.active_stubs.items():
            stub_totals[name] += c
            stub_battles[name] += 1
    wins = Counter(r.winner for r in results)
    causes = Counter()
    for r in results:
        for s in r.units.values():
            if s.destroyed:
                causes[f"{s.name}: {s.cause_of_death}"] += 1

    def avg(xs):
        xs = list(xs)
        return sum(xs) / len(xs) if xs else 0.0

    decisive = [r for r in results if r.winner in teams]
    summary = {
        "n": n,
        "wins": dict(wins),
        "avg_turns": avg(r.turns_taken for r in results),
        "avg_turns_decisive": avg(r.turns_taken for r in decisive),
        "causes_of_death": dict(causes),
        "avg_units_lost": {t: avg(r.teams[t].units_lost for r in results if t in r.teams) for t in teams},
        "avg_final_hp_pct": {t: avg(100 * r.teams[t].final_hp / r.teams[t].max_hp
                                    for r in results if t in r.teams and r.teams[t].max_hp) for t in teams},
        "avg_hit_rate": {t: avg(r.teams[t].hits / r.teams[t].attacks
                                for r in results if t in r.teams and r.teams[t].attacks) for t in teams},
        "active_stubs": dict(stub_totals),
        "active_stubs_battles": dict(stub_battles),
    }
    banner = _stub_banner(stub_totals, stub_battles, n)
    print("\n" + banner)
    print("\n" + "#" * 70)
    print(f"BATCH SUMMARY - {n} battle(s): " + ", ".join(f"{t} = {label}" for t, label in team_labels.items()))
    print("#" * 70)
    print("  Wins:  " + "   ".join(f"{t} {wins.get(t, 0)}" for t in teams) + f"   Draw {wins.get('Draw', 0)}")
    print(f"  Average turns: {summary['avg_turns']:.1f} (decisive battles only: {summary['avg_turns_decisive']:.1f})")
    first = next((r for r in results if r.teams), None)
    sizes = {t: first.teams[t].units for t in teams if first and t in first.teams} if first else {}
    print("  Average units lost: " + "   ".join(
        f"{t} {summary['avg_units_lost'][t]:.1f} of {sizes.get(t, '?')}" for t in teams))
    print("  Average remaining HP (armor+structure): " + "   ".join(
        f"{t} {summary['avg_final_hp_pct'][t]:.0f}%" for t in teams))
    print("  Hit rate: " + "   ".join(f"{t} {100 * summary['avg_hit_rate'][t]:.0f}%" for t in teams))
    print("  Causes of death:")
    for cause, c in causes.most_common():
        print(f"    {cause}: {c}")
    if not causes:
        print("    (none)")
    capped = [r for r in results if r.destroyed is None and r.turn_cap and r.turns_taken >= r.turn_cap]
    if capped:
        print(f"  !! {len(capped)} battle(s) reached the {capped[0].turn_cap}-turn cap with two or more teams "
              f"standing - a possible flaw (a stall?)")
    summary["turn_cap_reached"] = len(capped)
    if n <= 10:
        print("  Per battle:")
        for i, r in enumerate(results, start=1):
            left = ", ".join(f"{t} {r.teams[t].units - r.teams[t].units_lost}/{r.teams[t].units} left "
                             f"({r.teams[t].final_hp:g}/{r.teams[t].max_hp:g} HP)" for t in teams if t in r.teams)
            print(f"    #{i}: {r.turns_taken} turns, winner {r.winner}; {left}")
    print("\n" + banner)
    return summary
