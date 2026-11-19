"""The four-bot benchmark battery (session 30, Daniel 2026-11-19): every bot against every bot, itself included, on the
website's maps and 'Mechs only.

    python tools/benchmark_bots.py 4v4 [MIRROR] [--per-axis 20] [--only=MAP_PREFIX] [--skip BOT,BOT]      (stage 2, below; --stitched plays the STITCHED boards, for mixed12)
    python tools/benchmark_bots.py 1v1 [MATCHUP ...] [--battles 80] [--data-root DIR] [--records DIR] [--threads N] [--list]

Stage 1 (this file): ONE-ON-ONE. A matchup is two 'Mechs (MATCHUPS below). For each of the 10 bot pairings (4 bots: 6 cross
pairs + 4 bots against themselves) the set is `--battles` battles (80), spread over six maps and both axes:

  * the two seatings (each bot flies each 'Mech half the time: Red always holds 'Mech 1, Blue 'Mech 2, so swapping which
    bot sits where swaps the 'Mechs);
  * North v South and East v West (HOME_EDGE_CHOICE "N" / "E"; the deployment roll still decides WHICH team takes the
    edge, so the edge each team actually got is read back from the battle log and kept with the result);
  * six maps (MAPS), the extra battles of an uneven split rotating from one pairing to the next.

Every battle is one line in `trial_records/benchmark_1v1_<matchup>.jsonl`: matchup, bots, 'Mechs, map, axis, the edge each
team started on, winner (team, bot, 'Mech), turns, cap, hit-point shares left. A re-run plays only the cells missing from
that file (the set can be stopped and resumed). `--list` prints the plan and stops.

Same-bot pairings are also the first edge-bias data (tools/map_bias.py reads these files): in a one-on-one the two 'Mechs
differ, so that bias is only a hint; the 4 v 4 mirrors (stage 2) are the real test.
"""
import itertools, json, os, re, subprocess, sys, tempfile, zipfile, zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BTSIM = os.path.join(ROOT, "engine", "target", "release", "btsim")

BOTS = ["gladiator", "princess", "hydra", "caspar"]
# Only boards and units the website build carries (tools/build_web_lab.py: 16x17, no bridges / fuel tanks / elevators;
# units with no unmodeled equipment). Checked 2026-11-19 against the Lab's own unit and board lists.
MAPS = ["16x17_Grassland_1.board", "16x17_Grasslands_Rolling_Hills_1.board", "16x17_Scattered_Woods.board",
        "16x17_Large_Lakes_1.board", "16x17_Military_Base_1.board", "16x17_Desert_Hills.board"]
AXES = {"NS": "N", "EW": "E"}          # HOME_EDGE_CHOICE for each axis
MATCHUPS = {                          # name: ('Mech 1 (Red), 'Mech 2 (Blue))
    "whm_jvn": ("meks/3039u/Warhammer WHM-6R.mtf", "meks/3039u/Javelin JVN-10N.mtf"),         # Daniel's example
    "hbk_grf": ("Hunchback HBK-4G.mtf", "Griffin GRF-1N.mtf"),
    "rfl_wvr": ("meks/3039u/Rifleman RFL-3N.mtf", "meks/3039u/Wolverine WVR-6R.mtf"),
    "mad_cplt": ("meks/3039u/Marauder MAD-3R.mtf", "Catapult CPLT-C1.mtf"),
    "aws_jr7": ("Awesome AWS-8Q.mtf", "Jenner JR7-D.mtf"),
    "tdr_shd": ("meks/3039u/Thunderbolt TDR-5S.mtf", "meks/3039u/Shadow Hawk SHD-2H.mtf"),
}


def pairings():
    """(A, B) for every unordered pair of bots, A = B included: 10 of them."""
    return [(BOTS[i], BOTS[j]) for i in range(len(BOTS)) for j in range(i, len(BOTS))]


def split_runs(pair_index, total):
    """The cells of one pairing: [(seat, axis, map, battles)], `total` battles over 2 seats x 2 axes x 6 maps (each seat/axis
    cell gets total/4, split over the maps; the maps that get the odd battles rotate with the pairing)."""
    per_cell = total // 4
    base, extra = divmod(per_cell, len(MAPS))
    runs = []
    for c, (seat, axis) in enumerate(itertools.product((0, 1), AXES)):
        for m, board in enumerate(MAPS):
            n = base + (1 if (m - pair_index - c) % len(MAPS) < extra else 0)
            if n:
                runs.append((seat, axis, board, n))
    return runs


def data_root(path):
    """A folder with data/ (the project's own files plus data/meks.zip and data/maps.zip unpacked) for btsim to read."""
    if not os.path.isdir(os.path.join(path, "data", "meks")):
        os.makedirs(os.path.join(path, "data"), exist_ok=True)
        src = os.path.join(ROOT, "data")
        for f in os.listdir(src):
            if f.endswith((".mtf", ".board")):
                with open(os.path.join(src, f), "rb") as a, open(os.path.join(path, "data", f), "wb") as b:
                    b.write(a.read())
        for z in ("meks.zip", "maps.zip"):
            zipfile.ZipFile(os.path.join(src, z)).extractall(os.path.join(path, "data"))
    link = os.path.join(path, "engine")
    if not os.path.exists(link):
        os.symlink(os.path.join(ROOT, "engine"), link)
    return path


EDGE = re.compile(r"Deployment: (Red|Blue)\b.*? home edge ([NESW])")   # "Red", or "Red 2" in a team of several


def play(root, red_mtfs, blue_mtfs, red_bot, blue_bot, board, axis, battles, seed, threads):
    """One run: `battles` battles of Red (red_mtfs, red_bot) v Blue (blue_mtfs, blue_bot). Returns btsim's results with each
    battle's start edges added ('edges': {team: edge})."""
    settings = {"FORCES": [{"team": t, "mtf": m, "count": 1, "bot": bot} for t, ms, bot in (("Red", red_mtfs, red_bot), ("Blue", blue_mtfs, blue_bot)) for m in ms],
                "HOME_EDGE_CHOICE": AXES[axis]}
    if board in STITCHED:                      # boards joined in a grid (STITCH_MAPS, as the Lab does)
        ids, cols, rows = STITCHED[board]
        settings.update({"STITCH_MAPS": True, "STITCH_BOARDS": ids, "STITCH_GRID_COLS": cols, "STITCH_GRID_ROWS": rows})
    else:
        settings["DEFAULT_BOARD_PATH"] = board
    with tempfile.TemporaryDirectory() as tmp:
        sfile, out = os.path.join(tmp, "settings.json"), os.path.join(tmp, "out.json")
        json.dump(settings, open(sfile, "w"))
        cmd = [BTSIM, "--setup", sfile, "--battles", str(battles), "--seed", str(seed), "--log", str(battles), "--out", out]
        if threads:
            cmd += ["--threads", str(threads)]
        subprocess.run(cmd, env={**os.environ, "BTSIM_ROOT": root}, capture_output=True, text=True, check=True)
        res = json.load(open(out))
    logs = {x["sim"]: x["lines"] for x in res.get("logs", [])}
    for r in res["results"]:
        r["edges"] = {}
        for l in logs.get(r["sim"], []):
            m = EDGE.match(l.strip())
            if m:
                r["edges"].setdefault(m.group(1), m.group(2))
    res.pop("logs", None)
    return res


def done_cells(path):
    keys = set()
    if os.path.exists(path):
        for line in open(path):
            keys.add(json.loads(line)["cell"])
    return keys


def run_matchup(name, battles, root, records, threads):
    mtfs = MATCHUPS[name]
    path = os.path.join(records, f"benchmark_1v1_{name}.jsonl")
    have = done_cells(path)
    nm = [m.split("/")[-1][:-4] for m in mtfs]
    print(f"\n=== {name}: {nm[0]} (Red) v {nm[1]} (Blue), {battles} battles a pairing ===", flush=True)
    tally = {}                                           # bot -> [wins, losses, draws] over the whole matchup so far
    for p, (a, b) in enumerate(pairings()):
        w = {a: 0, b: 0, "none": 0} if a != b else {a: 0, "none": 0}
        mech_wins = {0: 0, 1: 0}
        edge_wins = {}
        for seat, axis, board, n in split_runs(p, battles):
            red, blue = (a, b) if seat == 0 else (b, a)  # seat 0: A flies 'Mech 1; seat 1: A flies 'Mech 2
            cell = f"{name}|{a}|{b}|{seat}|{axis}|{board}"
            if cell in have:
                continue
            seed = 1 + 1000 * (zlib.crc32(f"{axis}{board}{seat}".encode()) % 997)   # same dice for every pairing of a cell
            res = play(root, [mtfs[0]], [mtfs[1]], red, blue, board, axis, n, seed, threads)
            with open(path, "a") as f:
                f.write(json.dumps({"cell": cell, "matchup": name, "mechs": mtfs, "bots": {"Red": red, "Blue": blue}, "map": board,
                                    "axis": axis, "seat": seat, "seed": seed, "results": res["results"], "seconds": res["seconds"]}) + "\n")
        for line in open(path) if os.path.exists(path) else []:
            r = json.loads(line)
            if r["matchup"] != name or r["cell"].split("|")[1:3] != [a, b]:
                continue
            for x in r["results"]:
                win = x["winner"]
                if win in ("Red", "Blue"):
                    w[r["bots"][win]] += 1
                    mech_wins[0 if win == "Red" else 1] += 1
                    e = x["edges"].get(win)
                    edge_wins[e] = edge_wins.get(e, 0) + 1
                else:
                    w["none"] += 1
        if a == b:
            print(f"  {a:9s} v itself   : {nm[0]} {mech_wins[0]:3d} - {mech_wins[1]:3d} {nm[1]}   none {w['none']}   edge wins {dict(sorted(edge_wins.items()))}", flush=True)
        else:
            print(f"  {a:9s} v {b:9s}: {a} {w[a]:3d} - {w[b]:3d} {b}   none {w['none']}   ({nm[0]} won {mech_wins[0]}, {nm[1]} {mech_wins[1]})   edge wins {dict(sorted(edge_wins.items()))}", flush=True)
            for bot, wins, losses in ((a, w[a], w[b]), (b, w[b], w[a])):
                t = tally.setdefault(bot, [0, 0, 0])
                t[0] += wins; t[1] += losses; t[2] += w["none"]
    print(f"  cross-pair totals for {name} (wins - losses): " + ", ".join(f"{k} {v[0]}-{v[1]}" for k, v in tally.items()), flush=True)


STITCHED = {     # name: (board ids, grid columns, grid rows); Daniel 2026-11-19: "Use grassland 1 twice" for 12 v 12
    "Grassland_1_x2_wide.board": (["16x17_Grassland_1.board"] * 2, 2, 1),      # 32 wide, 17 high
}
MIRRORS = {      # name: the 'Mechs of ONE side (both sides field them: the pilot is the only difference)
    "mixed12": ["Atlas AS7-K.mtf", "Awesome AWS-8Q.mtf", "Archer ARC-2R.mtf", "Hunchback HBK-4G.mtf", "Griffin GRF-1N.mtf", "Dervish DV-6M.mtf",
                "Jenner JR7-D.mtf", "Commando COM-2D.mtf", "Locust LCT-1V.mtf", "Catapult CPLT-C1.mtf", "Cataphract CTF-3D.mtf", "Kintaro KTO-19.mtf"],   # tools/hydra_scenarios.py MIXED
    "lance4": ["Atlas AS7-K.mtf", "Hunchback HBK-4G.mtf", "Griffin GRF-1N.mtf", "Jenner JR7-D.mtf"],   # tools/hydra_scenarios.py LANCE
}


def run_mirror(name, per_axis, root, records, threads, maps, skip=()):
    """Stage 2: the mirror `name` on each map, every pairing, `per_axis` battles on each axis (a cross pair splits them over the
    two seatings; a same-bot pair plays them all in one). Prints, per map, the score of each pairing and, for same-bot
    pairings, the wins by starting edge: the edge-bias record (tools/benchmark_report.py reads it)."""
    mech = MIRRORS[name]
    path = os.path.join(records, f"benchmark_4v4_{name}.jsonl")
    have = done_cells(path)
    for board in maps:
        print(f"\n=== {name} on {board[:-6]}: {per_axis} battles an axis, per pairing ===", flush=True)
        for a, b in pairings():
            if (a in skip or b in skip) and not any(c.startswith(f"{name}|{a}|{b}|") and c.endswith(board) for c in have):
                print(f"  {a:9s} v {b:9s}: skipped (not played yet; --skip {','.join(skip)})", flush=True)
                continue
            seats = (0, 1) if a != b else (0,)
            score, edges = {a: 0, b: 0, "none": 0}, {}
            for axis in AXES:
                for seat in seats:
                    n = per_axis // len(seats)
                    red, blue = (a, b) if seat == 0 else (b, a)
                    cell = f"{name}|{a}|{b}|{seat}|{axis}|{board}"
                    if cell not in have:
                        seed = 1 + 1000 * (zlib.crc32(f"{axis}{board}{seat}".encode()) % 997)
                        res = play(root, mech, mech, red, blue, board, axis, n, seed, threads)
                        with open(path, "a") as f:
                            f.write(json.dumps({"cell": cell, "matchup": name, "mechs": mech, "bots": {"Red": red, "Blue": blue}, "map": board,
                                                "axis": axis, "seat": seat, "seed": seed, "results": res["results"], "seconds": res["seconds"]}) + "\n")
            for line in open(path):
                r = json.loads(line)
                if r["map"] != board or r["cell"].split("|")[1:3] != [a, b] or r["matchup"] != name:
                    continue
                for x in r["results"]:
                    win = x["winner"]
                    if win in ("Red", "Blue"):
                        score[r["bots"][win]] += (1 if a != b else 0)
                        e = x["edges"].get(win)
                        edges[(r["axis"], e)] = edges.get((r["axis"], e), 0) + 1
                    else:
                        score["none"] += 1
            if a == b:
                ns = [edges.get(("NS", "N"), 0), edges.get(("NS", "S"), 0)]
                ew = [edges.get(("EW", "W"), 0), edges.get(("EW", "E"), 0)]
                print(f"  {a:9s} v itself   : N {ns[0]:2d} - S {ns[1]:2d}   W {ew[0]:2d} - E {ew[1]:2d}   none {score['none']}", flush=True)
            else:
                print(f"  {a:9s} v {b:9s}: {score[a]:3d} - {score[b]:3d}   none {score['none']}", flush=True)


def main(argv):
    def opt(name, default):
        return argv[argv.index(name) + 1] if name in argv else default
    if argv and argv[0] == "4v4":
        root = data_root(opt("--data-root", os.path.join(os.path.dirname(ROOT), "btroot")))
        maps = [m for m in MAPS if not [a for a in argv if a.startswith("--only=")] or m.startswith(argv[[a.startswith("--only=") for a in argv].index(True)][7:])]
        if "--stitched" in argv:
            maps = list(STITCHED)
        for n in ([a for a in argv[1:] if a in MIRRORS] or ["lance4"]):
            run_mirror(n, int(opt("--per-axis", "20")), root, opt("--records", os.path.join(ROOT, "trial_records")), opt("--threads", None), maps, tuple(opt("--skip", "").split(",")) if "--skip" in argv else ())
        return
    if not argv or argv[0] != "1v1":
        raise SystemExit(__doc__)
    battles = int(opt("--battles", "80"))
    names = [a for i, a in enumerate(argv[1:], 1) if not a.startswith("--") and argv[i - 1] not in ("--battles", "--data-root", "--records", "--threads")] or list(MATCHUPS)
    if "--list" in argv:
        for n in names:
            print(n, MATCHUPS[n], f"{battles * len(pairings())} battles")
        return
    root = data_root(opt("--data-root", os.path.join(os.path.dirname(ROOT), "btroot")))
    records = opt("--records", os.path.join(ROOT, "trial_records"))
    for n in names:
        run_matchup(n, battles, root, records, opt("--threads", None))


if __name__ == "__main__":
    main(sys.argv[1:])
