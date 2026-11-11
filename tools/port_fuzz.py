"""
tools/port_fuzz.py - RUST PORT: random battles as a bug hunt for the Rust engine (session 24, 2026-11-11).

    python tools/port_fuzz.py exact START COUNT [--sizes duel,2v2] [--tag a] [--data DIR]
    python tools/port_fuzz.py crash START COUNT [--sizes duel,2v2,3v3] [--tag a] [--data DIR] [--battles 6]

Battle number N (START .. START+COUNT-1) is drawn from random.Random(N): one to four units a side picked from all of
data/meks.zip, each side driven by Gladiator or Princess, on a random 16x17 map of data/maps.zip. So a number names
its battle: the same N gives the same match-up on any machine.

  exact  The strong check. The Python plays the battle and records it (tools/port_record.py); the Rust engine then
         plays it from the same dice with its own bots, and state after every phase, dice used, log and stub warnings
         must be equal (engine/core/tests/stage6_battles.rs, BOTS=rust). A battle that differs keeps its fixture
         folder engine/fixtures/fz<tag>_<N> (re-run it with FIXTURES=fz<tag>_<N> BOTS=rust cargo test --release
         --test stage6_battles -- --nocapture); one that matches is deleted.
  crash  The wide check. The Python only sets the battle up (tools/port_scenario.py); `btsim` plays --battles of it
         on its own dice, twice: a panic is logged with its message, and the two runs must give the same results
         (same seed, same battle - anything else means something reads an unordered map's order).

Results go to engine/fuzz/<mode>_<tag>.log, one line a battle: ok / DIFF / PANIC / NONDETERMINISTIC / SETUP-FAIL
(SETUP-FAIL = the Python refused the match-up: a LAM, a map with bridges... - or the Python itself raised, which is a
Python bug worth reading). Run several at once with different --tag and START to use every core.

The units and maps are unzipped once into --data (default: <system temp>/port_fuzz_data), outside the repo.
"""
import glob
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import zipfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(REPO_ROOT, "engine")
SIZES = {"duel": 1, "2v2": 2, "3v3": 3, "4v4": 4}


def option(argv, name, default):
    return argv[argv.index(name) + 1] if name in argv else default


def unpack(data_dir):
    """data/meks.zip and data/maps.zip, unzipped once: (sorted .mtf paths, sorted 16x17 .board paths)."""
    for name in ("meks", "maps"):
        target = os.path.join(data_dir, name)
        if not os.path.isdir(target):
            os.makedirs(target)
            with zipfile.ZipFile(os.path.join(REPO_ROOT, "data", name + ".zip")) as z:
                z.extractall(target)
    units = sorted(glob.glob(os.path.join(data_dir, "meks", "**", "*.mtf"), recursive=True))
    maps = sorted(m for m in glob.glob(os.path.join(data_dir, "maps", "**", "*.board"), recursive=True)
                  if "16x17" in os.path.basename(m))
    return units, maps


def match_up(n, units, maps, sizes):
    """Battle number n's config statements and its size name."""
    rnd = random.Random(n)
    kind = rnd.choice(sizes)
    forces = []
    for team in ("Red", "Blue"):
        bot = rnd.choice(["gladiator", "princess"])
        for _ in range(SIZES[kind]):
            forces.append({"team": team, "mtf": rnd.choice(units), "count": 1, "bot": bot})
    board = rnd.choice(maps)
    return [f"config.FORCES = {forces!r}", f"config.DEFAULT_BOARD_PATH = {board!r}", f"config.SEED = {n}"], kind


def build(args):
    """Runs cargo quietly; returns its combined output."""
    proc = subprocess.run(["cargo"] + args, cwd=ENGINE, capture_output=True, text=True)
    if proc.returncode:
        raise SystemExit(proc.stderr[-3000:])
    return proc.stdout + proc.stderr


def last_line(text):
    lines = text.strip().splitlines()
    return lines[-1][:200] if lines else ""


def run_exact(n, statements, kind, tag, test_binary, work, out):
    name = f"fz{tag}_{n}"
    folder = os.path.join(ENGINE, "fixtures", name)
    overrides = os.path.join(work, f"overrides_{tag}.json")
    with open(overrides, "w", encoding="utf-8") as f:
        json.dump(statements, f)
    env = dict(os.environ, INTEGRATION_DATA_DIR="./data", PYTHONIOENCODING="utf-8", PYTHONHASHSEED="0")
    try:
        proc = subprocess.run([sys.executable, "tools/port_record.py", "--overrides", overrides, folder],
                              cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired:
        shutil.rmtree(folder, ignore_errors=True)
        return out(f"{n} RECORD-TIMEOUT {kind}")
    if proc.returncode:
        shutil.rmtree(folder, ignore_errors=True)
        return out(f"{n} SETUP-FAIL {kind} {last_line(proc.stderr)}")
    try:
        proc = subprocess.run([test_binary], cwd=os.path.join(ENGINE, "core"),
                              env=dict(os.environ, FIXTURES=name, BOTS="rust"), capture_output=True, text=True,
                              timeout=1800)
    except subprocess.TimeoutExpired:
        return out(f"{n} RUST-TIMEOUT {kind} {json.dumps(statements)}")
    if proc.returncode == 0:
        shutil.rmtree(folder, ignore_errors=True)
        return out(f"{n} ok {kind}")
    why = [line for line in (proc.stderr + proc.stdout).splitlines() if line.startswith("FAIL")][:2]
    out(f"{n} DIFF {kind} {json.dumps(statements)}\n    {' | '.join(why)[:900]}")


def run_crash(n, statements, kind, tag, btsim, battles, work, out):
    scenario = os.path.join(work, f"scenario_{tag}")
    overrides = scenario + ".json"
    with open(overrides, "w", encoding="utf-8") as f:
        json.dump(statements, f)
    proc = subprocess.run([sys.executable, "tools/port_scenario.py", scenario, "--overrides", overrides,
                           "--max-turns", "30"], cwd=REPO_ROOT, capture_output=True, text=True)
    if proc.returncode:
        return out(f"{n} SETUP-FAIL {kind} {last_line(proc.stderr)}")
    results = []
    for run in range(2):
        result_file = f"{scenario}.{run}.json"
        proc = subprocess.run([btsim, scenario, "--battles", str(battles), "--seed", str(n), "--threads", "1",
                               "--out", result_file], capture_output=True, text=True, timeout=3600)
        if proc.returncode:
            why = [line.strip() for line in proc.stderr.splitlines() if line.strip() and not line.startswith("note:")]
            return out(f"{n} PANIC {kind} {json.dumps(statements)}\n    {' | '.join(why[:3])[:700]}")
        with open(result_file, encoding="utf-8") as f:
            results.append(json.load(f))
    if results[0]["results"] != results[1]["results"]:
        return out(f"{n} NONDETERMINISTIC {kind} {json.dumps(statements)}")
    out(f"{n} ok {kind} {results[0]['seconds']:.1f}s wins={results[0]['wins']} cap={results[0]['hit_turn_cap']}")


def main(argv):
    if len(argv) < 3 or argv[0] not in ("exact", "crash"):
        raise SystemExit(__doc__)
    mode, start, count = argv[0], int(argv[1]), int(argv[2])
    tag = option(argv, "--tag", "a")
    sizes = option(argv, "--sizes", "duel,duel,duel,duel,2v2").split(",")
    data_dir = option(argv, "--data", os.path.join(tempfile.gettempdir(), "port_fuzz_data"))
    battles = int(option(argv, "--battles", "6"))
    units, maps = unpack(data_dir)
    work = os.path.join(ENGINE, "fuzz")
    os.makedirs(work, exist_ok=True)
    log = open(os.path.join(work, f"{mode}_{tag}.log"), "a", encoding="utf-8")

    def out(line):
        log.write(line + "\n")
        log.flush()
        print(line.splitlines()[0][:150], flush=True)

    if mode == "exact":
        # a private copy of the test program, so a rebuild while this runs does not pull it out from under us
        text = build(["test", "--release", "--test", "stage6_battles", "--no-run"])
        built = [word.strip("()") for word in text.split() if "stage6_battles-" in word][-1]
        binary = os.path.join(work, f"stage6_battles_{tag}")
        shutil.copy(os.path.join(ENGINE, built) if not os.path.isabs(built) else built, binary)
        for n in range(start, start + count):
            statements, kind = match_up(n, units, maps, sizes)
            run_exact(n, statements, kind, tag, binary, work, out)
    else:
        build(["build", "--release", "-p", "btsim"])
        binary = os.path.join(work, f"btsim_{tag}")
        shutil.copy(os.path.join(ENGINE, "target", "release", "btsim"), binary)
        for n in range(start, start + count):
            statements, kind = match_up(n, units, maps, sizes)
            run_crash(n, statements, kind, tag, binary, battles, work, out)


if __name__ == "__main__":
    main(sys.argv[1:])
