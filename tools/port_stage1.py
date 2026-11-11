"""
tools/port_stage1.py - RUST PORT stage 1 fixtures: geometry, board parser, terrain rules (INTEGRATION__RUST_PORT.md).

    python tools/port_stage1.py [OUT_DIR]        # default engine/fixtures/stage1

Writes, from the Python answer key:
  geometry.json      100,000 random hexes (x, y) -> label -> back; compass names; 100,000 hex_distance pairs
  boards.json        EVERY .board of data/maps.zip, plus the boards in data/: parse + prepare_board with
                     passive buildings on and off - the board as JSON (same shape as a fixture's board.json) or the
                     refusal's message - and the parser's stdout warnings. Files are named by their path in the zip.
  stitched.json      stitch_boards on a set of grids (and the refusals)
  terrain.json       terrain_rules on thousands of hex pairs taken from real boards: terrain_cost, step_cost, step_psrs,
                     step_psr_causes, turn_psrs, step_hazard, has_*_terrain
"""
import contextlib
import io
import json
import os
import random
import sys
import zipfile

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
import terrain_rules  # noqa: E402
from port_record import dump  # noqa: E402


def geometry(rng):
    cases = []
    for _ in range(100000):
        x = rng.randrange(0, 99)
        col = x + 1
        row = rng.randrange(1, 100)
        label = f"{col:02d}{row:02d}"
        xx, yy = hex_geometry.parse_hex_label(label)
        cases.append([label, xx, yy, hex_geometry.hex_label(xx, yy)])
    bad = []
    for label in ["", "12", "12345", "ab12", " 0101 ", "0000", "0100", "0001", "-101"]:
        try:
            bad.append([label, list(hex_geometry.parse_hex_label(label))])
        except ValueError as e:
            bad.append([label, "ValueError: " + str(e)])
    bad_xy = []
    for x, y in [(0, 1), (1, 0), (0, 3), (-1, 0), (5, 40), (98, 200), (3, 3)]:
        try:
            bad_xy.append([x, y, hex_geometry.hex_label(x, y)])
        except ValueError as e:
            bad_xy.append([x, y, "ValueError: " + str(e)])
    compass = []
    for c in ["N", "ne", " SE ", "S", "SW", "NW", "X", "", "north"]:
        try:
            compass.append([c, hex_geometry.compass_to_facing(c)])
        except ValueError as e:
            compass.append([c, "ValueError: " + str(e)])
    facings = []
    for f in [0, 1, 2, 3, 4, 5, 6, -1]:
        try:
            facings.append([f, hex_geometry.facing_to_compass(f)])
        except ValueError as e:
            facings.append([f, "ValueError: " + str(e)])
    dist = []
    for _ in range(100000):
        a = (rng.randrange(-5, 120), rng.randrange(-10, 240))
        b = (rng.randrange(-5, 120), rng.randrange(-10, 240))
        dist.append([a[0], a[1], b[0], b[1], los.hex_distance(a, b)])
    return {"labels": cases, "bad_labels": bad, "bad_xy": bad_xy, "compass": compass, "facings": facings,
            "distance": dist}


def load_board(path, passive):
    out = io.StringIO()
    result = {"stdout": ""}
    with contextlib.redirect_stdout(out):
        try:
            board = board_parser.parse_board_file(path)
            terrain_rules.prepare_board(board, passive_buildings=passive)
            result["board"] = dump(board, {}, {})
        except (ValueError, FileNotFoundError, KeyError) as e:
            result["error"] = f"{type(e).__name__}: {e}"
    result["stdout"] = out.getvalue()
    return result


def boards():
    out = {}
    names = []
    with zipfile.ZipFile("data/maps.zip") as z:
        for n in sorted(z.namelist()):
            if n.endswith(".board"):
                names.append((n, z.read(n)))
    for fn in sorted(os.listdir("data")):
        if fn.endswith(".board"):
            with open(os.path.join("data", fn), "rb") as f:
                names.append(("data/" + fn, f.read()))
    tmp = os.path.join("engine", "fixtures", "_boards")      # relative: error messages quote the path
    os.makedirs(tmp, exist_ok=True)
    for name, raw in names:
        path = os.path.join(tmp, name.replace("/", "__"))
        with open(path, "wb") as f:
            f.write(raw)
        out[name] = {"file": os.path.basename(path), "passive": load_board(path, True),
                     "full": load_board(path, False)}
    return out


def stitched(rng):
    with zipfile.ZipFile("data/maps.zip") as z:
        names = [n for n in sorted(z.namelist()) if n.endswith(".board")]
    tmp = os.path.join("engine", "fixtures", "_boards")      # relative: error messages quote the path
    sizes = {}
    for n in names:
        b = board_parser.parse_board_file(os.path.join(tmp, n.replace("/", "__")))
        sizes.setdefault((b["width"], b["height"]), []).append(n)
    cases = []
    grids = [(1, 1), (2, 1), (1, 2), (2, 2), (3, 1), (2, 3)]
    for (w, h), group in sorted(sizes.items()):
        if len(group) < 2:
            continue
        for cols, rows in grids:
            if cols * rows > 6:
                continue
            for _ in range(2):
                picks = [rng.choice(group) for _ in range(cols * rows)]
                cases.append((picks, cols, rows))
    odd = [g for (w, h), g in sorted(sizes.items()) if w % 2 == 1]
    if odd:
        for g in odd[:2]:
            cases.append(([g[0], g[0]], 2, 1))
    # mismatches and a wrong count
    biggest = sorted(sizes.items(), key=lambda kv: -len(kv[1]))
    if len(biggest) > 1:
        cases.append(([biggest[0][1][0], biggest[1][1][0]], 2, 1))
        cases.append(([biggest[0][1][0], biggest[1][1][0]], 1, 2))
    cases.append(([names[0]], 2, 1))
    out = []
    for picks, cols, rows in cases:
        paths = [os.path.join(tmp, n.replace("/", "__")) for n in picks]
        buf = io.StringIO()
        entry = {"files": [os.path.basename(p) for p in paths], "cols": cols, "rows": rows}
        with contextlib.redirect_stdout(buf):
            try:
                entry["board"] = dump(board_parser.stitch_boards(paths, cols, rows), {}, {})
            except (ValueError, FileNotFoundError, KeyError) as e:
                entry["error"] = f"{type(e).__name__}: {e}"
        entry["stdout"] = buf.getvalue()
        out.append(entry)
    return out


def terrain(rng, boards_out):
    cases = {"cost": [], "step": [], "psr": [], "hazard": [], "flags": []}
    playable = [(n, b["passive"]["board"]) for n, b in boards_out.items() if "board" in b["passive"]]
    rng.shuffle(playable)
    for name, bjson in playable[:60]:
        path = os.path.join("engine", "fixtures", "_boards", boards_out[name]["file"])
        with contextlib.redirect_stdout(io.StringIO()):
            board = board_parser.parse_board_file(path)
            terrain_rules.prepare_board(board, True)
        hexes = board["hexes"]
        labels = list(hexes)
        cases["flags"].append([name, terrain_rules.has_hazard_terrain(board), terrain_rules.has_psr_terrain(board)])
        for label in rng.sample(labels, min(40, len(labels))):
            info = hexes[label]
            for sh in (False, True):
                cases["cost"].append([name, label, sh, terrain_rules.terrain_cost(info["features"], sh)])
            cases["hazard"].append([name, label, [terrain_rules.step_hazard(info, legs) for legs in (1, 2, 3, 4)]])
            cases["psr"].append([name, label, list(terrain_rules.turn_psrs(info))])
        for _ in range(400):
            a, b = rng.choice(labels), rng.choice(labels)
            # prefer neighbours: take b near a half the time
            if rng.random() < 0.7:
                ax, ay = hex_geometry.parse_hex_label(a)
                dx, dy = hex_geometry.FACING_DELTAS[rng.randrange(6)]
                try:
                    cand = hex_geometry.hex_label(ax + dx, ay + dy)
                    if cand in hexes:
                        b = cand
                except ValueError:
                    pass
            for limit, sh in ((2, False), (1, False), (2, True)):
                for backward in (False, True):
                    lim = terrain_rules.GroundLimit(limit, sh)
                    cases["step"].append([name, a, b, limit, sh, backward,
                                          terrain_rules.step_cost(hexes[a], hexes[b], lim, backward)])
            cases["step"].append([name, None, b, 2, False, False, terrain_rules.step_cost(None, hexes[b])])
            cases["psr"].append([name, a, b, [list(terrain_rules.step_psrs(hexes[a], hexes[b], bw)) for bw in (False, True)],
                                 [terrain_rules.step_psr_causes(hexes[a], hexes[b], bw, run)
                                  for bw in (False, True) for run in (False, True)]])
    return cases


def main(argv):
    out = argv[0] if argv else os.path.join(REPO_ROOT, "engine", "fixtures", "stage1")
    os.makedirs(out, exist_ok=True)
    rng = random.Random(1)
    b = boards()

    def put(name, data):
        with open(os.path.join(out, name), "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f)
    put("geometry.json", geometry(rng))
    put("boards.json", b)
    put("stitched.json", stitched(rng))
    put("terrain.json", terrain(rng, b))
    n_ok = sum(1 for v in b.values() if "board" in v["passive"])
    print(f"{len(b)} boards ({n_ok} play with passive buildings); fixtures in {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
