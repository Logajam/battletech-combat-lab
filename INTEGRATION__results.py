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
    "Shoulder / head turrets (not Core equipment: their (T) weapons fire forward); the twist / flip a TAG "
    "designation would use up (TAG doesn't fire yet). Firing arcs, torso twists (both attack phases, tripods "
    "any hexside), tripod leg arcs, reversing arms and Quad Turrets are applied",
    "Variable-damage weapons (heavy Gauss, HAG, VSP...) can't fire (no damage data); munitions not modeled: AC "
    "armor-piercing / caseless / flak / precision rounds (fired as standard), iNarc ECM / haywire / Nemesis pods; "
    "Apollo saturation mode; a Narc homing pod is valued for one turn and not in movement scoring",
    "Heat sources/sinks with no terrain model yet: water, snow, fire, extreme temperatures; "
    "inferno missiles (inferno bins aren't fired from; they can still explode)",
    "Heat decisions (bot logic, later): cooldown (a mech at max_heat stays there), voluntary "
    "shutdown; equipment uses Daniel's defaults (stealth always on, 1-on/1-off radical/MASC/"
    "supercharger, coolant pod when above min_heat, aimed shots at config.AIMED_SHOT_LOCATION)",
    "Torso-mounted cockpit PSR rules",
    "Physical attacks: all seven types are built; not priced in movement scoring: the PSRs a hit forces (only "
    "Movement-phase PSRs count), picking up a club as part of the plan; domino effects (no third mech)",
    "Tripod leg sub-roll uses Python's random module (seeded from SEED, not the BattleRNG stream)",
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
    active_stubs: Dict[str, int] = field(default_factory=dict)
    seed: Optional[int] = None   # this battle's own seed: SEED = seed, NUM_SIMULATIONS = 1 replays it

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
