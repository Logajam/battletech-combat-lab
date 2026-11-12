"""Plays a trial's undecided battles on with a higher turn cap (session 25; Daniel, 2026-11-12: "take the draws and play
them out", "we should only be running the undecided games").

    python tools/replay_undecided.py RECORDS.jsonl [--max-turns 150] [--fixtures engine/fixtures] [--btsim PATH]
                                     [--threads N] [--label NAME | --records OUT.jsonl]

RECORDS.jsonl is a file of tools/trial_records.py. For every batch in it, the battles that reached the turn cap are
played again ALONE (btsim --sims), same scenario, seats, Hydra teams, settings and seed, with the higher cap: up to the old
cap each is the same battle (same dice), so only its ending is new. The replays are recorded like any trial (tool
"replay_undecided"; label default "<input name>_to<cap>"), and the input's head-to-head is printed again with the
undecided battles' new endings: Hydra v house bot for hydra_trial batches, Red v Blue per seating for round_robin ones.
"""
import json, os, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trial_records  # noqa: E402
from round_robin import seat  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
option = trial_records.option


def main(argv):
    path = argv[0]
    cap = int(option(argv, "--max-turns", "150"))
    fixtures = option(argv, "--fixtures", os.path.join(ROOT, "engine", "fixtures"))
    btsim = option(argv, "--btsim", os.path.join(ROOT, "engine", "target", "release", "btsim"))
    threads = option(argv, "--threads", None)
    if "--label" not in argv and "--records" not in argv:
        argv = argv + ["--label", os.path.splitext(os.path.basename(path))[0] + f"_to{cap}"]
    out_path = trial_records.records_path(argv, "replay_undecided")
    batches = [json.loads(l) for l in open(path) if l.strip()]
    # per (scenario, kind) -> [first side wins, second side wins, undecided] before and after
    table = {}
    with tempfile.TemporaryDirectory() as tmp:
        for k, bt in enumerate(batches):
            folder = os.path.join(fixtures, bt["scenario"])
            if bt["tool"] == "round_robin":
                folder = seat(folder, os.path.join(tmp, f"{k}"), bt["red"], bt["blue"])
            undecided = [r["sim"] for r in bt["results"] if r["capped"]]
            new = {}
            if undecided:
                cmd = [btsim, folder, "--battles", str(bt["battles"]), "--seed", str(bt["seed"]), "--max-turns", str(cap),
                       "--sims", ",".join(map(str, undecided))]
                if threads:
                    cmd += ["--threads", threads]
                if bt.get("hydra"):
                    cmd += ["--hydra", bt["hydra"]]
                for kv in bt["settings"]:
                    cmd += ["--set", kv]
                out = json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)
                trial_records.append(out_path, "replay_undecided", bt["scenario"], bt["red"], bt["blue"], bt.get("hydra"),
                                     sum((["--set", kv] for kv in bt["settings"]), []), cap, bt["seed"], bt["battles"], out)
                new = {r["sim"]: r for r in out["results"]}
            # who counts as "first" / "second": Hydra and the house bot, or Red and Blue
            if bt.get("hydra"):
                key, first = (bt["scenario"], "Hydra v house bot"), lambda w: w == bt["hydra"]
            else:
                key, first = (bt["scenario"], f"{bt['red']} (Red) v {bt['blue']} (Blue)"), lambda w: w == "Red"
            row = table.setdefault(key, [[0, 0, 0], [0, 0, 0], []])
            for r in bt["results"]:
                for slot, w in ((0, r["winner"]), (1, new.get(r["sim"], r)["winner"])):
                    row[slot][0 if first(w) else (2 if w == "Draw" else 1)] += 1
                if r["sim"] in new:
                    row[2].append(new[r["sim"]]["turns"])
    print(f"Undecided battles of {os.path.basename(path)} played on to turn {cap} (records: {out_path}):")
    tot = [[0, 0, 0], [0, 0, 0]]
    for (scenario, kind), (before, after, turns) in table.items():
        ends = f"; replayed {len(turns)}, ended by turn " + (f"{sorted(turns)[len(turns) // 2]} (median)" if turns else "-")
        print(f"  {scenario:34s} {kind:32s} {before[0]:4d} - {before[1]:4d} - {before[2]:3d} undecided  ->  {after[0]:4d} - {after[1]:4d} - {after[2]:3d}{ends}")
        for s in (0, 1):
            for j in range(3):
                tot[s][j] += (before, after)[s][j]
    print(f"  ALL: {tot[0][0]} - {tot[0][1]} - {tot[0][2]} undecided  ->  {tot[1][0]} - {tot[1][1]} - {tot[1][2]}")


if __name__ == "__main__":
    main(sys.argv[1:])
