"""
tests/test_bots.py - checks the per-unit bot choice (INTEGRATION__bots, added
2026-10-27) and the Princess clone (INTEGRATION__princess,
INTEGRATION__princess_fire):
  - each side's MECH_*_CONFIG["bot"] (else config.BOT) names its bot,
    "gladiator" is the default, an unknown bot is refused;
  - the MegaMek hex geometry port (Coords distance, ConvexBoardArea);
  - Princess's firing-plan utility and heat handling on a hand-built case;
  - Princess's fire control is only active inside its own context (Gladiator's
    weapon choice is untouched outside it);
  - a Princess vs Gladiator battle runs to the end and is repeatable.

    python tests/test_bots.py
"""

import io
import math
import os
import sys
import traceback
from contextlib import redirect_stdout, redirect_stderr

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

import INTEGRATION__config as config  # noqa: E402 - registers bare "config" first
config.STATS = False  # event log + report off: not part of a test or battery (2026-11-06)
import INTEGRATION__orchestrator as orchestrator  # noqa: E402
import INTEGRATION__bots as bots  # noqa: E402
import INTEGRATION__princess as princess  # noqa: E402
import INTEGRATION__princess_fire as princess_fire  # noqa: E402
import INTEGRATION__weapon_selection as weapon_selection  # noqa: E402
import hex_geometry  # noqa: E402 - PATHFINDER
from los import hex_distance  # noqa: E402 - PATHFINDER


def _refused(cfg, error):
    try:
        bots.bot_for(cfg)
    except error:
        return True
    return False


def bot_names():
    assert config.BOT == bots.GLADIATOR, config.BOT
    assert bots.bot_for({}) == bots.GLADIATOR
    assert bots.bot_for({"bot": "Princess"}) == bots.PRINCESS          # case-insensitive
    assert _refused({"bot": "nobody"}, ValueError)


def megamek_geometry():
    # Coords.distance matches the project's on every pair of a 16x17 board.
    labels = [f"{c:02d}{r:02d}" for c in range(1, 17) for r in range(1, 18)]
    for a in labels[::7]:
        for b in labels[::5]:
            pa, pb = hex_geometry.parse_hex_label(a), hex_geometry.parse_hex_label(b)
            assert princess.mm_distance(princess.mm(pa), princess.mm(pb)) == hex_distance(pa, pb), (a, b)
    # The convex area of a hex block: a hex inside is its own closest point; one outside
    # is as far from the area as from the nearest hex of the block.
    block = [princess.mm(hex_geometry.parse_hex_label(f"{c:02d}{r:02d}")) for c in range(5, 9) for r in range(5, 9)]
    area = princess.ConvexBoardArea(block)
    inside = princess.mm(hex_geometry.parse_hex_label("0606"))
    assert area.closest_to(inside) == inside
    outside = princess.mm(hex_geometry.parse_hex_label("1206"))
    assert princess.mm_distance(area.closest_to(outside), outside) == min(
        princess.mm_distance(c, outside) for c in block)


class _W:
    def __init__(self, name, heat):
        self.name, self.heat = name, heat


class _Version:
    """config.PRINCESS_VERSION set for a block."""

    def __init__(self, version):
        self.version = version

    def __enter__(self):
        self.saved, config.PRINCESS_VERSION = config.PRINCESS_VERSION, self.version

    def __exit__(self, *exc):
        config.PRINCESS_VERSION = self.saved


def fire_control_utility():
    with _Version("0.50.07"):
        _fire_control_utility()


def _fire_control_utility():
    # A fresh Kontio as target: utility = (ED + 10 crits + 50 kill) x log10(2 x its
    # damage at range 1 + 10) - 5 x heat over the tolerance.
    red, blue = _mechs()
    fc = princess_fire.FireControl(guess=False)
    mult = math.log10(2 * princess_fire.max_damage_at_range(blue, 1) + 10)
    w1, w2 = _W("a", 4), _W("b", 30)
    planner = type("P", (), {"target": blue})()
    red.current_heat = 0
    # Tolerance = 10 dissipation - 0 heat - 0 other + 5 = 15: the 30-heat weapon costs
    # 5 x 15 = 75 for 5 expected damage - not worth it.
    weapons, u, heat = fc(red, [(w1, 3.0, 4, 7), (w2, 5.0, 30, 7)], 10, 0, planner, "front")
    p = 21 / 36
    crits = princess_fire.ROLL_TWO * princess_fire.EXPECTED_CRITICAL_HIT_COUNT * p
    assert heat == 4 and abs(u - (3.0 + 10 * crits) * mult) < 1e-9, (heat, u)
    # A guess takes the alpha strike when its heat is within the tolerance.
    guess = princess_fire.FireControl(guess=True)
    _, u2, heat2 = guess(red, [(w1, 3.0, 4, 7), (w2, 5.0, 10, 7)], 10, 0, planner, "front")
    assert heat2 == 14, heat2
    # Nothing worth firing (an impossible shot) -> the empty plan.
    _, u3, heat3 = fc(red, [(w1, 3.0, 4, 13)], 10, 0, planner, "front")
    assert u3 == 0 and heat3 == 0


def modern_fire_control():
    # The Kontio (Red) carries TSM: modern tolerance = 10 sinks - 0 heat + 13 (the TSM
    # ceiling) = 23, so a 20-heat plan isn't penalised; the firing choice adds the TSM
    # incentive 20 x (projected heat 10 ... the band 9-13).
    red, blue = _mechs()
    assert getattr(red, "has_tsm", False)
    red.current_heat = 0
    planner = type("P", (), {"target": blue})()
    mult = math.log10(2 * princess_fire.max_damage_at_range(blue, 1) + 10)
    w1 = _W("a", 20)
    with _Version("modern"):
        weapons, u, heat = princess_fire.FireControl(guess=False)(red, [(w1, 3.0, 20, 7)], 10, 0, planner, "front")
        p = 21 / 36
        crits, kill = princess_fire.weapon_crits_and_kill(blue, "front", p, 3.0, on_hit=3.0 / p)
        bonus = princess_fire.tsm_heat_bonus(red, 10, 0, 20)
        assert abs(bonus - 20.0 * (1 - (10 - 9) / 4)) < 1e-9, bonus
        assert heat == 20 and abs(u - ((3.0 + 10 * crits + 50 * kill) * mult + bonus)) < 1e-9, (heat, u)
        # Its own guess while ranking a move counts the move's heat: 18 + 6 movement > 23 + ...
        guess = princess_fire.FireControl(guess=True, self_mech=red)
        _, _, h_still = guess(red, [(w1, 3.0, 20, 7)], 10, 0, planner, "front", 0)
        assert h_still == 20                       # within 23: the alpha strike
        _, _, h_ran = guess(red, [(w1, 3.0, 20, 7)], 10, 0, planner, "front", 6)
        assert h_ran in (0, 20)                    # over 17 now: a plan by utility (penalty 5 x 3)


def modern_posture():
    import INTEGRATION__princess_modern as modern
    red, blue = _mechs()
    red.hex, blue.hex = "0101", "0115"            # 14 apart
    for turn, blue_hex, want in ((1, "0115", "ATTACK"), (2, "0113", "DEFEND"), (3, "0113", "DEFEND"),
                                 (4, "0113", "DEFEND"), (5, "0113", "ATTACK")):   # the window is 3 rounds
        red.turn_number, blue.hex = turn, blue_hex
        assert modern.posture(red, blue) == want, (turn, modern.posture(red, blue))


def fire_control_scoped():
    red, blue = _mechs()
    before = weapon_selection.select_weapons_to_fire(red, 3, 6, 0, 30, dissipation=20, movement_heat=0)
    with weapon_selection.fire_control(princess_fire.FireControl(guess=False)):
        assert weapon_selection._FIRE_CONTROL is not None
    assert weapon_selection._FIRE_CONTROL is None
    after = weapon_selection.select_weapons_to_fire(red, 3, 6, 0, 30, dissipation=20, movement_heat=0)
    assert [id(w) for w in before[0]] == [id(w) for w in after[0]] and before[1:] == after[1:]


def _mechs():
    """Fresh Red / Blue mechs from config's files, with their scenario settings."""
    from mtf_parser import parse_mtf
    with redirect_stdout(io.StringIO()):
        red = parse_mtf(os.path.join(config.DATA_DIR, config.MECH_RED_MTF))
        blue = parse_mtf(os.path.join(config.DATA_DIR, config.MECH_BLUE_MTF))
        orchestrator._attach_mech_config(red, config.MECH_RED_CONFIG, "Red")
        orchestrator._attach_mech_config(blue, config.MECH_BLUE_CONFIG, "Blue")
    return red, blue


def _battle(seed):
    saved = (dict(config.MECH_RED_CONFIG), config.WORKERS, config.MAX_TURNS, config.TIMING)
    config.MECH_RED_CONFIG["bot"] = "princess"
    config.WORKERS, config.MAX_TURNS, config.TIMING = 1, 30, False
    try:
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            result = orchestrator.run_batch(num_simulations=1, seed=seed)[0]
        return result, out.getvalue()
    finally:
        config.MECH_RED_CONFIG.clear()
        config.MECH_RED_CONFIG.update(saved[0])
        config.WORKERS, config.MAX_TURNS, config.TIMING = saved[1:]


def princess_battle():
    for version, note in (("modern", "Princess (modern, "), ("0.50.07", "Princess: utility")):
        with _Version(version):
            first, log = _battle(12345)
            again, log2 = _battle(12345)
        assert note in log, f"{version}: Princess never picked a move"
        assert "Princess plan utility" in log, f"{version}: Princess never chose its weapons"
        assert log == log2, f"{version}: the same seed gave a different battle"
        assert first.turns_taken >= 1


CHECKS = [bot_names, megamek_geometry, fire_control_utility, modern_fire_control, modern_posture,
          fire_control_scoped, princess_battle]


def main():
    failures = 0
    for check in CHECKS:
        try:
            check()
            print(f"  ok    {check.__name__}")
        except Exception:
            failures += 1
            print(f"  FAIL  {check.__name__}")
            traceback.print_exc()
    print("test_bots:", "OK" if not failures else f"{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
