"""
tools/make_event_scenarios.py - the short, purpose-built reference scenarios (ev_*) that cover event types no battle of the
old reference list reached often enough (INTEGRATION__EVENTS.md; Daniel, 2026-11-24, "for any event type nothing covers, write a
short purpose-built scenario, as the cov_* ones were").

    python tools/make_event_scenarios.py --out DIR            # writes ev_*/ (config.json, units.json, board.json) into DIR
    python tools/make_event_scenarios.py --add-to-zip         # ... and adds them to engine/reference/scenarios.zip

Each scenario is a handful of 'Mechs on fixed hexes (the "cov_" way), found by trying positions with tools/event_coverage.py's
counts: the layouts below are the ones whose battle (seed 1, the reference check's seed) shows the event the scenario is for.
  ev_tag_homing_a/b/c   a Patriot (TAG) and a Legionnaire (Arrow IV with homing rounds) against two 'Mechs: TAG designation,
                        spotting, a homing missile hit (STUB_FIRE_TAG "always": the Patriot has no homing rounds of its own)
  ev_dfa_a/b            two Hydra-driven teams of jump 'Mechs (Cataphract, Catapult): a death-from-above (rare: ~1 battle in 50)
  ev_building_a/b/c     a Cataphract and a Black Hawk across the Military Base's buildings: a move that ends in / leaves a building
The 'Mechs come from data/ (the flat folder) and the answer key's engine/fixtures/_units (the Patriot and Legionnaire there carry the
ammunition these tests need); the finished scenario folders hold everything (units.json, board.json), so neither is needed to play them.
"""
import json
import os
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BTSIM = os.path.join(ROOT, "engine", "target", "release", "btsim")
DATA = os.path.join(ROOT, "data")
FIXTURE_UNITS = os.path.join(ROOT, "engine", "fixtures", "_units")


def mech(name):
    """Path of a 'Mech file: data/ first, then the answer key's _units."""
    for d in (DATA, FIXTURE_UNITS):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    raise SystemExit(f"{name}: not in data/ or engine/fixtures/_units (python tools/unpack_answer_key.py)")


def force(team, name, hexl, facing, bot="gladiator"):
    return {"team": team, "mtf": mech(name), "hex": hexl, "facing": facing, "bot": bot, "max_heat": 30}


def tag_homing(dist, target):
    return [force("Red", "Patriot PKM-2C.mtf", "0808", "SE"), force("Red", "Legionnaire LGN-2XA.mtf", "0710", "SE"),
            force("Blue", target, f"{8 + dist:02d}09", "NW"), force("Blue", "Hunchback HBK-4G.mtf", f"{8 + dist:02d}10", "NW")]


def dfa(dist, target):
    return [force("Red", "Cataphract CTF-3D.mtf", "0807", "SE"), force("Red", "Catapult CPLT-C1.mtf", "0810", "SE"),
            force("Blue", target, f"{8 + dist:02d}08", "NW"), force("Blue", "Catapult CPLT-C1.mtf", f"{8 + dist:02d}11", "NW")]


def building(red_hex, blue_hex):
    return [force("Red", "Cataphract CTF-3D.mtf", red_hex, "SE"), force("Blue", "Black Hawk (Nova) F.mtf", blue_hex, "NW")]


# name -> (forces, board, extra settings, how the reference check plays it: None = the scenario's own bots, "Red,Blue" = Hydra drives these)
SCENARIOS = {
    "ev_tag_homing_a": (tag_homing(4, "Atlas AS7-K.mtf"), "16x17_Grassland_1.board", {"STUB_FIRE_TAG": "always"}, None),
    "ev_tag_homing_b": (tag_homing(3, "Awesome AWS-8Q.mtf"), "16x17_Grassland_1.board", {"STUB_FIRE_TAG": "always"}, None),
    "ev_tag_homing_c": (tag_homing(5, "Awesome AWS-8Q.mtf"), "16x17_Grassland_1.board", {"STUB_FIRE_TAG": "always"}, None),
    "ev_dfa_a": (dfa(4, "Awesome AWS-8Q.mtf"), "16x17_Grassland_1.board", {}, "Red,Blue"),
    "ev_dfa_b": (dfa(5, "Atlas AS7-K.mtf"), "16x17_Grassland_1.board", {}, "Red,Blue"),
    "ev_building_a": (building("0610", "1010"), "16x17_Military_Base_1.board", {}, None),
    "ev_building_b": (building("0714", "1007"), "16x17_Military_Base_1.board", {}, None),
    "ev_building_c": (building("0904", "0911"), "16x17_Military_Base_1.board", {}, None),
}


def build(out_dir):
    """Writes every scenario folder into out_dir (through `btsim --setup`, the way tools/hydra_scenarios.py does)."""
    for name, (forces, board, extra, _) in SCENARIOS.items():
        folder = os.path.join(out_dir, name)
        os.makedirs(folder, exist_ok=True)
        settings = {"FORCES": forces, "DEFAULT_BOARD_PATH": board, "SEED": 1, "DEPLOYMENT": "fixed_hexes", "MAX_TURNS": 30}
        settings.update(extra)
        spec = os.path.join(folder, "settings.json")
        with open(spec, "w") as f:
            json.dump(settings, f)
        subprocess.run([BTSIM, "--setup", spec, "--write-scenario", folder, "--battles", "0"], check=True, stdout=subprocess.DEVNULL)
        os.remove(spec)
        # the folder must hold only what the reference zip keeps: config, units, board (+ meta)
        print(f"built {name}")


def main(argv):
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    if "--add-to-zip" in argv:
        out = out or tempfile.mkdtemp()
    if not out:
        raise SystemExit(__doc__)
    build(out)
    if "--add-to-zip" in argv:
        zpath = os.path.join(ROOT, "engine", "reference", "scenarios.zip")
        with zipfile.ZipFile(zpath) as z:
            keep = {n: z.read(n) for n in z.namelist() if n.split("/")[0] not in SCENARIOS}
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            for n in sorted(keep):
                z.writestr(n, keep[n])
            for name in SCENARIOS:
                for f in sorted(os.listdir(os.path.join(out, name))):
                    if f == "meta.json":
                        continue   # the reference zip holds config, units and board only
                    z.write(os.path.join(out, name, f), f"{name}/{f}")
        print(f"added {len(SCENARIOS)} scenarios to {zpath}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
