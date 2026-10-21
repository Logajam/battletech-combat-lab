"""
tests/test_los.py - line of sight as the Core Rulebook has it (pp.56-58, 66;
rebuilt 2026-10-21, Daniel: "make sure the LOS rules match those in the rules
and fix prone mechs"): LOS levels with 'Mech heights (standing 2, prone 1),
when terrain intervenes, hills / buildings blocking, woods points, partial
cover, prone targets, and lines on a hex border.

    python tests/test_los.py

The checks rebuild the rulebook's own examples (the Intervening Terrain
Diagram, p.58; the Line of Sight Diagram, p.59; Partial Cover, p.66) on a
small board: the line runs straight up one column from the attacker.
"""

import os
import sys
import traceback

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "pathfinder"))

from hex_geometry import parse_hex_label, hex_label  # noqa: E402
from los import trace_los_path, has_los, hex_line, STANDING_HEIGHT, PRONE_HEIGHT  # noqa: E402

CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


def board(**hexes):
    """A 16x17 level-0 board; keyword hexes (h0805=dict(level=..., woods="1"))
    override single hexes."""
    out = {f"{c:02d}{r:02d}": {"level": 0, "features": {}, "impassable": False}
           for c in range(1, 17) for r in range(1, 18)}
    for key, spec in hexes.items():
        label = key[1:]
        info = {"level": spec.get("level", 0), "features": {}, "impassable": False}
        for feature in ("woods", "jungle"):
            if feature in spec:
                info["features"][feature] = [spec[feature]]
        if "depth" in spec:
            info["depth"] = spec["depth"]
        out[label] = info
    return {"width": 16, "height": 17, "hexes": out}


A, T = parse_hex_label("0808"), parse_hex_label("0804")    # 4 hexes apart: 0807 next to A, 0805 next to T


def line(tm, a_height=STANDING_HEIGHT, t_height=STANDING_HEIGHT, a=A, t=T):
    return trace_los_path(a, t, tm, a_height, t_height)


@check
def intervening_terrain_diagram():
    """p.58, panels 1-5: attacker LOS level 4 (a level 2 hex), defender LOS
    level 2 (level 0). Woods count when their level (hex + 2) is >= both, or
    >= the LOS level of the 'Mech they are next to."""
    def woods_points(where, hex_level):
        tm = board(h0808=dict(level=2), **{f"h{where}": dict(level=hex_level, woods="1")})
        return line(tm).result.modifier
    assert woods_points("0806", 1) == 0        # 1. woods level 3, not adjacent: not >= 4
    assert woods_points("0806", 2) == 1        # 2. woods level 4, not adjacent: >= both
    assert woods_points("0805", 0) == 1        # 3. woods level 2 next to the defender: >= its 2
    assert woods_points("0807", 2) == 1        # 4. woods level 4 next to the attacker: >= its 4
    assert woods_points("0807", 1) == 0        # 5. woods level 3 next to the attacker: not >= 4


@check
def a_hill_next_to_the_target_hides_it():
    """p.57 TACTICS: a target in a level 0 hex next to a level 2 hill on the
    line is hidden even from a much higher attacker; a level 2 hill in the
    middle doesn't stop that attacker. One intervening hex of a sufficient
    level blocks (p.58)."""
    assert not line(board(h0808=dict(level=10), h0805=dict(level=2))).result.los
    assert line(board(h0808=dict(level=10), h0806=dict(level=2))).result.los
    assert not line(board(h0806=dict(level=2))).result.los              # level 0 to level 0: blocks
    assert line(board(h0806=dict(level=1))).result.los                  # level 1 < both LOS levels (2)


@check
def woods_points_block_at_three():
    """p.58: light 1, heavy 2 per intervening hex; 3 or more block. The
    target's own hex never counts for LOS, but adds its to-hit modifier
    (p.66). Jungle works like woods."""
    assert line(board(h0806=dict(woods="2"))).result.modifier == 2
    assert not line(board(h0806=dict(woods="2"), h0805=dict(woods="1"))).result.los
    assert not line(board(h0806=dict(jungle="2"), h0805=dict(jungle="1"))).result.los
    r = line(board(h0806=dict(woods="1"), h0804=dict(woods="2"))).result
    assert r.los and r.modifier == 1 + 2                                # 1 intervening + 2 in the target's hex
    assert line(board(h0808=dict(woods="2"))).result.modifier == 0      # the attacker's own woods: nothing


@check
def prone_mechs_are_one_level_tall():
    """p.57: prone 'Mechs are 1 level tall. p.66: a prone 'Mech gets no
    partial cover - next to a level 1 hex along the LOS it can't be seen at
    all. p.59, the Rakshasa: prone in a level 4 hex (LOS level 5), woods in
    level 3 hexes (level 5) intervene; standing (LOS level 6) they wouldn't."""
    cover = board(h0805=dict(level=1))
    standing, prone = line(cover), line(cover, t_height=PRONE_HEIGHT)
    assert standing.result.los and standing.steps[-1].partial_cover == 1
    assert not prone.result.los
    assert not line(cover, a_height=PRONE_HEIGHT, a=T, t=A).result.los      # mutual: the prone 'Mech can't see out
    rak = board(h0804=dict(level=4), h0806=dict(level=3, woods="1"))
    assert line(rak, t_height=PRONE_HEIGHT).result.modifier == 1
    assert line(rak).result.modifier == 0


@check
def partial_cover():
    """p.66: a standing target next to a hex one level higher along the LOS
    has partial cover (+1) - not if the attacker's LOS level is higher, not
    from woods, not at range 1. Standing in depth 1 water: cover even from
    higher attackers, but not from a fully submerged attacker (p.67)."""
    assert line(board(h0805=dict(level=1))).result.modifier == 1
    assert line(board(h0805=dict(level=1), h0808=dict(level=1))).steps[-1].partial_cover == 0   # LOS 3 > 2
    assert line(board(h0805=dict(woods="1"))).steps[-1].partial_cover == 0
    assert trace_los_path(parse_hex_label("0805"), T, board()).steps[-1].partial_cover == 0
    wet = board(h0804=dict(level=-1, depth=1), h0808=dict(level=3))
    assert line(wet).steps[-1].partial_cover == 1
    deep = board(h0804=dict(level=-1, depth=1), h0808=dict(level=-2, depth=2))
    assert line(deep).steps[-1].partial_cover == 0


@check
def adjacent_mechs_always_see_each_other():
    """p.56."""
    tm = board(h0807=dict(level=5))
    assert line(tm, t=parse_hex_label("0807")).result.los


@check
def a_border_line_is_one_side_or_the_other():
    """p.56: a line exactly between two hexes runs along ONE side, the
    target's choice, for the whole line - here the side worse for the
    attacker. Light woods on one side and light woods on the other don't add
    up: the line passes only one of them."""
    a, t = parse_hex_label("0808"), parse_hex_label("0605")
    # Its two border steps: 0807 | 0708, then 0706 | 0606 - one side runs 0807, 0707, 0706,
    # the other 0708, 0707, 0606.
    assert [[hex_label(*h) for h in s] for s in hex_line(a, t) if len(s) == 2] == [["0807", "0708"], ["0706", "0606"]]
    tm = board(h0807=dict(woods="1"), h0606=dict(woods="1"))
    assert trace_los_path(a, t, tm).result.modifier == 1        # one side's woods, not both (was 2)
    heavy = board(h0807=dict(woods="2"), h0606=dict(woods="1"))
    assert trace_los_path(a, t, heavy).result.modifier == 2     # the target picks the heavy side
    blocked_one_side = board(h0807=dict(woods="2"), h0706=dict(woods="1"))
    assert not has_los(a, t, blocked_one_side).los               # it may pick the side that blocks


def run_all():
    failed = 0
    for fn in CHECKS:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print()
    print(f"All {len(CHECKS)} LOS checks passed." if not failed else f"{failed} of {len(CHECKS)} LOS checks FAILED.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_all())
