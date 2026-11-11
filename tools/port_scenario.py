"""
tools/port_scenario.py - RUST PORT stage 9: write a scenario the Rust engine (`btsim`) can run in batches.

    python tools/port_scenario.py OUT_DIR [--overrides FILE.json | --fixture NAME] [--max-turns N]

Applies the config overrides (a JSON list of statements like "config.SEED = 1", as tools/port_record.py takes), loads the
roster and board exactly as a battle does, and stops where the battle would start. Writes config.json, units.json,
board.json and meta.json into OUT_DIR. Then:

    engine/target/release/btsim OUT_DIR --battles 200 --seed 1 [--threads 8] [--out results.json]

This only READS the Python engine (the same recorder hook the fixtures use); nothing in it is changed.
"""
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
sys.path.insert(0, os.path.join(REPO_ROOT, "tests"))
os.chdir(REPO_ROOT)
os.environ.setdefault("INTEGRATION_DATA_DIR", "./data")


class _AtStart(Exception):
    pass


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    out_dir = argv[0]
    statements, max_turns = [], 50
    if "--overrides" in argv:
        with open(argv[argv.index("--overrides") + 1], encoding="utf-8") as f:
            statements = json.load(f)
    if "--fixture" in argv:
        with open(os.path.join(REPO_ROOT, "engine", "fixtures", argv[argv.index("--fixture") + 1], "overrides.json"),
                  encoding="utf-8") as f:
            meta = json.load(f)
        statements, max_turns = meta["overrides"], meta["max_turns"]
    if "--max-turns" in argv:
        max_turns = int(argv[argv.index("--max-turns") + 1])
    import port_record as pr
    rec = pr.Recorder()
    rec.install()
    import INTEGRATION__orchestrator as orchestrator
    inner = orchestrator._start_battle

    def stop(battle):
        inner(battle)                       # the recorder's hook has taken the units and the board
        raise _AtStart()
    orchestrator._start_battle = stop
    try:
        pr.run_battle(statements, rec, max_turns)
    except _AtStart:
        pass
    finally:
        rec.uninstall()
    if not rec.start:
        raise SystemExit("the battle never started")
    os.makedirs(out_dir, exist_ok=True)

    def put(name, data):
        with open(os.path.join(out_dir, name), "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=1)
    put("config.json", pr.dump_config())
    put("units.json", rec.start["units"])
    put("board.json", rec.start["board"])
    put("meta.json", {"max_turns": max_turns, "overrides": statements})
    print(f"scenario written to {out_dir}")


if __name__ == "__main__":
    main(sys.argv[1:])
