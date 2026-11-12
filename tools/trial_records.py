"""Per-battle records of every trial (session 25; Daniel, 2026-11-12: "we need to keep records of results per individual
game seed").

Every batch a trial tool plays (tools/hydra_trial.py, tools/round_robin.py) is appended as ONE JSON LINE to a records file
in `trial_records/` (kept in git; a battle is about 60 bytes):

    {"tool": "hydra_trial", "date": "2026-11-12", "commit": "fede808", "scenario": "hy_8v8_valley",
     "red": "gladiator", "blue": "gladiator", "hydra": "Red", "settings": ["HYDRA_WAITING=true"], "max_turns": 50,
     "seed": 1, "battles": 16,
     "results": [{"sim": 1, "seed": 1234..., "winner": "Red", "turns": 31, "capped": false,
                  "left": {"Red": [612, 1450], "Blue": [0, 1450]}}, ...]}

`sim` is the battle's number in the set and `seed` its own dice seed (`btsim --seed S` battle `sim` always gets the same
one), so any battle can be played again alone: `btsim SCENARIO --seed S --battles N --sims sim`. `left` is each team's
armor + structure left and at the start. tools/replay_undecided.py plays a file's undecided battles on with a higher
turn cap.

The file name: trial_records/<date>_<tool>_<label>.jsonl, label from --label (default "run"). --records FILE overrides it;
--no-records turns recording off.
"""
import datetime, json, os, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECORDS = os.path.join(ROOT, "trial_records")


def option(argv, name, default):
    return argv[argv.index(name) + 1] if name in argv else default


def records_path(argv, tool):
    """Where this run's records go, or None (--no-records)."""
    if "--no-records" in argv:
        return None
    if "--records" in argv:
        return option(argv, "--records", "")
    label = option(argv, "--label", "run")
    return os.path.join(RECORDS, f"{datetime.date.today().isoformat()}_{tool}_{label}.jsonl")


def commit():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    except OSError:
        return ""


def settings(argv):
    """The --set KEY=VALUE pairs of a command line, in order."""
    return [argv[i + 1] for i, a in enumerate(argv) if a == "--set"]


def append(path, tool, scenario, red, blue, hydra, argv, max_turns, seed, battles, out):
    """Appends one batch (btsim's JSON output `out`) to the records file."""
    if not path:
        return
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    max_turns = out.get("max_turns", max_turns)  # btsim says which cap it played to
    results = []
    for r in out["results"]:
        results.append({"sim": r["sim"], "seed": r["seed"], "winner": r["winner"], "turns": r["turns"],
                        "capped": r["winner"] == "Draw" and r["turns"] >= max_turns,
                        "left": {t: [v["final_hp"], v["max_hp"]] for t, v in r["teams"].items()}})
    line = {"tool": tool, "date": datetime.date.today().isoformat(), "commit": commit(), "scenario": scenario,
            "red": red, "blue": blue, "hydra": hydra, "settings": settings(argv), "max_turns": max_turns,
            "seed": seed, "battles": battles, "results": results}
    with open(path, "a") as f:
        f.write(json.dumps(line) + "\n")
