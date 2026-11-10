"""
tools/port_stage2.py - RUST PORT stage 2 fixtures: sight and movement (INTEGRATION__RUST_PORT.md).

    python tools/port_stage2.py [OUT_DIR]        # default engine/fixtures/stage2

Needs engine/fixtures/_boards (python tools/port_stage1.py makes it). Writes, from the Python answer key:
  pathfinder.json  build_movement_table: flat, terrain, terrain + PSR/hazard, with parents - starts, budgets, backward
               MP, level limits, blocked hexes, refusals
  los.json     hex_line on 30k pairs; trace_los_path on ~30k (pair, heights) cases over 14 boards, each also with a
               random smoke layer; target_hex_modifier; the refusals for off-board hexes
"""
import contextlib
import io
import json
import os
import random
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
os.chdir(REPO_ROOT)
os.environ.setdefault("INTEGRATION_DATA_DIR", "./data")
import INTEGRATION__config as config  # noqa: E402,F401
import INTEGRATION__orchestrator  # noqa: E402,F401 - puts MECHSIM and PATHFINDER on the path
import board_parser  # noqa: E402
import hex_geometry  # noqa: E402
import los  # noqa: E402
import pathfinder  # noqa: E402
import terrain_rules  # noqa: E402

BOARDS_DIR = os.path.join("engine", "fixtures", "_boards")


def load(name, passive=True):
    path = os.path.join(BOARDS_DIR, name)
    with contextlib.redirect_stdout(io.StringIO()):
        b = board_parser.parse_board_file(path)
        terrain_rules.prepare_board(b, passive_buildings=passive)
    return b


def step_row(s):
    return [s.index, list(s.hex), None if s.other_candidate is None else list(s.other_candidate), s.level,
            s.is_endpoint, s.blocked, s.woods_contrib, s.partial_cover, s.cumulative_modifier, s.smoke_contrib,
            s.after_block]


def heights():
    return [(p, sh) for p in (False, True) for sh in (False, True)]


def interesting_boards(rng):
    """Boards with woods, buildings, water, planted fields, magma, ultra-heavy woods, hills - 14 of the playable."""
    want = ["woods", "building", "water", "planted_fields", "magma", "rough", "road"]
    chosen, seen = [], set()
    names = sorted(os.listdir(BOARDS_DIR))
    rng.shuffle(names)
    for n in names:
        try:
            b = load(n)
        except Exception:
            continue
        feats = {f for h in b["hexes"].values() for f in h["features"]}
        levels = {h["level"] for h in b["hexes"].values()}
        score = sum(1 for w in want if w in feats and w not in seen) + (1 if len(levels) > 3 and "hills" not in seen else 0)
        if score:
            chosen.append(n)
            seen |= feats
            if len(levels) > 3:
                seen.add("hills")
        if len(chosen) >= 14:
            break
    for n in names:                      # fill up with other playable boards
        if len(chosen) >= 14:
            break
        if n not in chosen:
            try:
                load(n)
            except Exception:
                continue
            chosen.append(n)
    for must in ("data__16x17_Large_Lakes_1.board", "data__16x17_Military_Base_1.board", "data__16x17_Scattered_Woods.board"):
        if must not in chosen:
            chosen.append(must)
    return chosen


def table_json(t):
    out = {"entries": [[list(st), [[mp, fc] for mp, fc in col.items()]] for st, col in t.items()]}
    if hasattr(t, "psrs"):
        out["psrs"] = [[list(st), [[mp, list(v)] for mp, v in col.items()]] for st, col in t.psrs.items()]
        out["hazards"] = [[list(st), [[mp, v] for mp, v in col.items()]] for st, col in t.hazards.items()]
    return out


def pathfinder_cases(rng):
    names = ["data__32x17_Caustic_Valley_Lava.board", "data__16x17_Badlands_2_Hazardous_Liquid.board",
             "data__16x17_Large_Lakes_1.board", "data__16x17_Military_Base_1.board", "data__16x17_Grassland_1.board",
             "data__16x17_Scattered_Woods.board", "data__16x17_Desert_Hills.board",
             "data__16x17_Grasslands_Rolling_Hills_1.board", "data__16x17_Hilltops_1.board"]
    names += [n for n in interesting_boards(rng)[:5] if n not in names]
    cases = []
    flat = []
    for _ in range(25):
        st = (rng.randrange(0, 10), rng.randrange(0, 10), rng.randrange(6))
        budget = rng.randrange(0, 7)
        flat.append([list(st), budget, table_json(pathfinder.build_movement_table(*st[:2], st[2], budget))])
    cases.append(["flat", flat])
    for name in names:
        board = load(name)
        labels = list(board["hexes"])
        rows = []
        for k in range(70):
            label = rng.choice(labels) if k % 25 else "9999"
            try:
                x, y = hex_geometry.parse_hex_label(label)
            except ValueError:
                x, y = 200, 200
            facing = rng.randrange(6)
            budget = rng.randrange(1, 11)
            backward = rng.choice([None, None, budget, max(0, budget - 2)])
            limit = rng.choice([(2, False), (2, False), (1, False), (2, True)])
            blocked = []
            for _ in range(rng.choice([0, 0, 1, 2, 4])):
                dx, dy = rng.randrange(-4, 5), rng.randrange(-8, 9)
                blocked.append((x + dx, y + dy))
            keep = rng.random() < 0.3
            lim = terrain_rules.GroundLimit(limit[0], limit[1])
            args = {"start": [x, y, facing], "budget": budget, "backward": backward, "limit": list(limit),
                    "blocked": [list(b) for b in blocked], "keep": keep}
            try:
                t = pathfinder.build_movement_table(x, y, facing, budget, board, backward, lim, keep,
                                                    blocked if blocked else None)
                args["table"] = table_json(t)
                if keep:
                    samples = []
                    for st in rng.sample(list(t), min(12, len(t))):
                        for mp in list(t[st])[:2]:
                            samples.append([list(st), mp, [[step, list(s2), m] for step, s2, m in t.path(st, mp)]])
                    args["paths"] = samples
            except ValueError as e:
                args["error"] = "ValueError: " + str(e)
            rows.append(args)
        cases.append([name, rows])
    return cases


def main(argv):
    out = argv[0] if argv else os.path.join(REPO_ROOT, "engine", "fixtures", "stage2")
    os.makedirs(out, exist_ok=True)
    rng = random.Random(2)
    result = {"lines": [], "los": [], "target_mod": [], "boards": []}

    # hex_line over all kinds of offsets
    for _ in range(30000):
        a = (rng.randrange(0, 40), rng.randrange(0, 60))
        b = (a[0] + rng.randrange(-20, 21), a[1] + rng.randrange(-40, 41))
        result["lines"].append([list(a), list(b), [[list(h) for h in step] for step in los.hex_line(a, b)]])

    for name in interesting_boards(rng):
        board = load(name)
        labels = list(board["hexes"])
        smoke = {}
        for label in rng.sample(labels, max(3, len(labels) // 7)):
            smoke[label] = {"density": rng.choice(["1", "2"]), "until": 5}
        result["boards"].append([name, smoke])
        for with_smoke in (False, True):
            b = load(name)
            if with_smoke:
                for label, sm in smoke.items():
                    b["hexes"][label]["smoke"] = dict(sm)
            hexes = b["hexes"]
            for _ in range(75):
                a_label = rng.choice(labels)
                ax, ay = hex_geometry.parse_hex_label(a_label)
                if rng.random() < 0.15:
                    t_label = rng.choice(labels)
                else:
                    t_label = None
                    for _try in range(30):
                        bx, by = ax + rng.randrange(-14, 15), ay + rng.randrange(-28, 29)
                        try:
                            cand = hex_geometry.hex_label(bx, by)
                        except ValueError:
                            continue
                        if cand in hexes:
                            t_label = cand
                            break
                    if t_label is None:
                        t_label = rng.choice(labels)
                a = hex_geometry.parse_hex_label(a_label)
                t = hex_geometry.parse_hex_label(t_label)
                for ah in heights():
                    for th in heights():
                        h1, h2 = los.mech_height(*ah), los.mech_height(*th)
                        try:
                            tr = los.trace_los_path(a, t, b, h1, h2)
                            res = {"ok": [[tr.result.los, tr.result.modifier, tr.result.distance],
                                          [step_row(s) for s in tr.steps]]}
                        except ValueError as e:
                            res = {"error": "ValueError: " + str(e)}
                        result["los"].append([name, with_smoke, list(a), list(t), list(ah), list(th), res])
            for label in rng.sample(labels, min(30, len(labels))):
                result["target_mod"].append([name, with_smoke, label,
                                             los.target_hex_modifier(hex_geometry.parse_hex_label(label), b)])
    # off-board hexes
    b = load("data__16x17_Grassland_1.board")
    for a, t in [((0, 1), (3, 3)), ((0, 0), (500, 0)), ((0, 0), (0, 200)), ((-3, 0), (4, 0)), ((14, 0), (20, 0))]:
        for p in (False,):
            try:
                tr = los.trace_los_path(a, t, b)
                res = {"ok": tr.result.los}
            except ValueError as e:
                res = {"error": "ValueError: " + str(e)}
            result["los"].append(["data__16x17_Grassland_1.board", False, list(a), list(t), [False, False], [False, False], res])

    with open(os.path.join(out, "pathfinder.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(pathfinder_cases(random.Random(3)), f)
    with open(os.path.join(out, "los.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(result, f)
    print(f"{len(result['lines'])} lines, {len(result['los'])} los cases on {len(result['boards'])} boards")


if __name__ == "__main__":
    main(sys.argv[1:])
