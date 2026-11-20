"""Builds the mirror match-ups Hydra is judged on (INTEGRATION__HYDRA.md, Section 4) into engine/fixtures/hy_*.

    python tools/hydra_scenarios.py [--house gladiator|princess]

A mirror match-up has the same 'Mechs on both sides, so the pilot is the only difference. Each folder is a scenario for
btsim / tools/hydra_trial.py. Built by the Rust engine (`btsim --setup SETTINGS.json --write-scenario DIR`, the same
setup the Combat Lab uses, checked equal to the Python's by cl1_setup); until 2026-11-20 by the retired Python's
tools/port_scenario.py.
"""
import json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANCE = ["Atlas AS7-K.mtf", "Hunchback HBK-4G.mtf", "Griffin GRF-1N.mtf", "Jenner JR7-D.mtf"]
HEAVY = ["Awesome AWS-8Q.mtf", "Archer ARC-2R.mtf", "Cataphract CTF-3D.mtf", "Catapult CPLT-C1.mtf"]
MIXED = ["Atlas AS7-K.mtf", "Awesome AWS-8Q.mtf", "Archer ARC-2R.mtf", "Hunchback HBK-4G.mtf", "Griffin GRF-1N.mtf", "Dervish DV-6M.mtf",
         "Jenner JR7-D.mtf", "Commando COM-2D.mtf", "Locust LCT-1V.mtf", "Catapult CPLT-C1.mtf", "Cataphract CTF-3D.mtf", "Kintaro KTO-19.mtf"]
SETS = {
    # name: (the 'Mechs of ONE side, the board, the seed that places them)
    "duel_griffin": (["Griffin GRF-1N.mtf"], "16x17_Grassland_1.board", 3),
    "duel_hunchback_woods": (["Hunchback HBK-4G.mtf"], "16x17_Scattered_Woods.board", 4),
    "duel_awesome_hills": (["Awesome AWS-8Q.mtf"], "16x17_Desert_Hills.board", 5),
    "2v2_grass": (["Griffin GRF-1N.mtf", "Hunchback HBK-4G.mtf"], "16x17_Grassland_1.board", 6),
    "4v4_lance_grass": (LANCE, "16x17_Grassland_1.board", 7),
    "4v4_lance_woods": (LANCE, "16x17_Scattered_Woods.board", 8),
    "4v4_heavy_hills": (HEAVY, "16x17_Grasslands_Rolling_Hills_1.board", 9),
    "8v8_valley": (LANCE + HEAVY, "32x17_Caustic_Valley_Lava.board", 10),
    "12v12_valley": (MIXED, "32x17_Caustic_Valley_Lava.board", 11),
}


def main(argv):
    house = argv[argv.index("--house") + 1] if "--house" in argv else "gladiator"
    for name, (mechs, board, seed) in SETS.items():
        forces = [{"team": t, "mtf": m, "count": 1, "bot": house} for t in ("Red", "Blue") for m in mechs]
        settings = {"FORCES": forces, "DEFAULT_BOARD_PATH": board, "SEED": seed}
        out = os.path.join(ROOT, "engine", "fixtures", f"hy_{name}" + ("" if house == "gladiator" else f"_{house}"))
        os.makedirs(out, exist_ok=True)
        spec = os.path.join(out, "settings.json")
        with open(spec, "w") as f:
            json.dump(settings, f)
        btsim = os.path.join(ROOT, "engine", "target", "release", "btsim")
        subprocess.run([btsim, "--setup", spec, "--write-scenario", out, "--battles", "0"], check=True, stdout=subprocess.DEVNULL)

if __name__ == "__main__":
    main(sys.argv[1:])
