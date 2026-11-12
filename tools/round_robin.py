"""Every bot against every bot, itself included, on the same match-ups and seeds (session 25).

    python tools/round_robin.py SCENARIO_DIR [SCENARIO_DIR ...] [--bots gladiator,princess,hydra] [--battles 40]
                                [--seed 1] [--threads N] [--btsim PATH] [--json OUT.json]

Each scenario folder (config.json, units.json, board.json; a mirror match-up from tools/hydra_scenarios.py is best: the
same 'Mechs on both sides, so the pilot is the only difference) is played once per SEATING: bot A drives Red and bot B
drives Blue, for every ordered pair (A, B), A = B included. The bots are set by rewriting each unit's "bot" in a copy of
units.json; nothing else changes, so the dice are the same for every seating of a scenario (btsim --seed).

Printed: per scenario, one line per seating; then the round-robin table summed over the scenarios - for each pair, A's
wins, B's wins and no-winner battles over both seatings (sides swapped, so the 'Mechs and the edge cancel out), and A's
mean strength-left margin (A's surviving armor + structure share minus B's). A bot against itself shows Red - Blue - none:
how much the seat alone is worth on that match-up.
"""
import itertools, json, os, shutil, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trial_records  # noqa: E402  every battle's result is kept in trial_records/ (--label NAME / --records FILE / --no-records)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BTSIM = os.path.join(ROOT, "engine", "target", "release", "btsim")


def option(argv, name, default):
    return argv[argv.index(name) + 1] if name in argv else default


def seat(folder, out_dir, red_bot, blue_bot):
    """A copy of the scenario with Red driven by red_bot and Blue by blue_bot."""
    os.makedirs(out_dir, exist_ok=True)
    for f in ("config.json", "board.json"):
        shutil.copy(os.path.join(folder, f), out_dir)
    units = json.load(open(os.path.join(folder, "units.json")))
    for u in units.values():
        u["bot"] = red_bot if u["team"] == "Red" else blue_bot
    json.dump(units, open(os.path.join(out_dir, "units.json"), "w"))
    return out_dir


def play(btsim, folder, battles, seed, threads, scenario=None, red=None, blue=None):
    cmd = [btsim, folder, "--battles", str(battles), "--seed", str(seed)]
    if threads:
        cmd += ["--threads", threads]
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a == "--set":  # --set KEY=VALUE (any number), passed to btsim
            cmd += ["--set", argv[i + 1]]
    if "--max-turns" in argv:
        cmd += ["--max-turns", option(argv, "--max-turns", "50")]
    out = json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)
    trial_records.append(trial_records.records_path(argv, "round_robin"), "round_robin", scenario, red, blue, None, argv,
                         int(option(argv, "--max-turns", "50")), seed, battles, out)
    left = {t: sum(r["teams"][t]["final_hp"] / max(r["teams"][t]["max_hp"], 1) for r in out["results"]) / battles for t in ("Red", "Blue")}
    return out["wins"].get("Red", 0), out["wins"].get("Blue", 0), out["mean_turns"], out["seconds"] / battles, left["Red"] - left["Blue"]


def main(argv):
    bots = option(argv, "--bots", "gladiator,princess,hydra").split(",")
    battles = int(option(argv, "--battles", "40"))
    seed = int(option(argv, "--seed", "1"))
    threads = option(argv, "--threads", None)
    btsim = option(argv, "--btsim", BTSIM)
    json_out = option(argv, "--json", None)
    folders = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or not argv[i - 1].startswith("--") or argv[i - 1] == "--no-records")]
    # totals[(A, B)] = [A wins, B wins, no winner, margin sum, seatings] over both seatings; A = B: [Red, Blue, none, ...]
    totals = {}
    record = []
    with tempfile.TemporaryDirectory() as tmp:
        for folder in folders:
            name = os.path.basename(folder.rstrip("/"))
            print(f"{name}: {battles} battles a seating", flush=True)
            for red, blue in itertools.product(bots, bots):
                red_wins, blue_wins, turns, secs, margin = play(btsim, seat(folder, os.path.join(tmp, f"{name}_{red}_{blue}"), red, blue), battles, seed, threads, name, red, blue)
                none = battles - red_wins - blue_wins
                print(f"  Red {red:9s} v Blue {blue:9s}  {red_wins:3d} - {blue_wins:3d} - {none:3d}   mean turns {turns:5.1f}   {secs:.2f} s/battle   Red margin {margin:+.3f}", flush=True)
                record.append({"scenario": name, "red": red, "blue": blue, "red_wins": red_wins, "blue_wins": blue_wins, "none": none, "turns": turns, "red_margin": margin})
                key = (red, blue) if (red, blue) in totals or red == blue or (blue, red) not in totals else (blue, red)
                t = totals.setdefault(key, [0, 0, 0, 0.0, 0])
                if key == (red, blue):
                    t[0] += red_wins; t[1] += blue_wins; t[3] += margin
                else:
                    t[0] += blue_wins; t[1] += red_wins; t[3] -= margin
                t[2] += none
                t[4] += 1
    print(f"\nROUND ROBIN over {len(folders)} match-ups (both seatings each):")
    for (a, b), (wa, wb, none, msum, n) in totals.items():
        if a == b:
            print(f"  {a:9s} v itself     Red {wa:4d} - Blue {wb:4d} - none {none:4d}   (Red margin {msum / n:+.3f})")
        else:
            print(f"  {a:9s} v {b:9s}  {wa:4d} - {wb:4d} - none {none:4d}   {a} wins {wa / max(wa + wb, 1):.0%} of decided; {a}'s margin {msum / n:+.3f}")
    if json_out:
        json.dump(record, open(json_out, "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1:])
