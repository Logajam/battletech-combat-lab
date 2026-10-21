"""
tests/survey_maps.py - which maps in a MegaMek map pack the simulator can
play, and what stops the rest (added 2026-10-21, Claude, for Daniel's map
pack: "let me know what is still causing problems so I can go hunt down
rules").

    python tests/survey_maps.py                     # data/maps.zip, 16x17 maps only
    python tests/survey_maps.py --all-sizes
    python tests/survey_maps.py path/to/maps.zip    # or a folder of .board files
    python tests/survey_maps.py --list              # one line per map as well

For each map: does it load (board_parser + terrain_rules.prepare_board with
the current config.PASSIVE_BUILDINGS), and if it does, can every
ground-movement step and a sample of LOS lines be worked out without an
error. Prints a tally of what stops the maps that can't be played. Not part
of run_checks.py (it takes ~20 s and depends on the pack, not the code).
"""

import argparse
import collections
import contextlib
import io
import os
import random
import sys
import tempfile
import zipfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "pathfinder"))

import INTEGRATION__config as config  # noqa: E402
import board_parser  # noqa: E402
import terrain_rules  # noqa: E402
from hex_geometry import FACING_DELTAS, hex_label, parse_hex_label  # noqa: E402
from los import trace_los_path  # noqa: E402

LOS_SAMPLES = 500   # random hex pairs traced per map


def board_files(source):
    """(display name, path) of every .board file in a zip or a folder."""
    if zipfile.is_zipfile(source):
        out = tempfile.mkdtemp(prefix="maps_")
        with zipfile.ZipFile(source) as z:
            z.extractall(out)
        source = out
    found = []
    for root, _dirs, files in os.walk(source):
        for name in files:
            if name.endswith(".board"):
                path = os.path.join(root, name)
                found.append((os.path.relpath(path, source), path))
    return sorted(found)


def check_map(path):
    """None if the map plays, else a list of reasons."""
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            tm = board_parser.parse_board_file(path)
            terrain_rules.prepare_board(tm, passive_buildings=config.PASSIVE_BUILDINGS)
        except ValueError as e:
            lines = str(e).splitlines()
            return [line.strip(" -").split(":")[0] for line in lines[1:]] or [lines[0]]
    hexes = tm["hexes"]
    for label, info in hexes.items():
        x, y = parse_hex_label(label)
        for dx, dy in FACING_DELTAS.values():
            try:
                dest = hexes.get(hex_label(x + dx, y + dy))
            except ValueError:
                continue
            if dest is not None:
                try:
                    terrain_rules.step_cost(info, dest)
                except Exception as e:                       # noqa: BLE001 - report, don't stop
                    return [f"movement error: {e}"]
    rnd = random.Random(1)
    labels = list(hexes)
    for _ in range(LOS_SAMPLES):
        a, b = rnd.sample(labels, 2)
        try:
            trace_los_path(parse_hex_label(a), parse_hex_label(b), tm)
        except Exception as e:                               # noqa: BLE001
            return [f"LOS error: {e}"]
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("source", nargs="?", default=os.path.join(REPO_ROOT, "data", "maps.zip"))
    parser.add_argument("--all-sizes", action="store_true", help="every map, not just 16x17")
    parser.add_argument("--list", action="store_true", help="one line per map")
    args = parser.parse_args()

    maps = board_files(args.source)
    if not args.all_sizes:
        def is_16x17(path):
            with open(path) as f:
                return any(line.strip() == "size 16 17" for line in f)
        maps = [(n, p) for n, p in maps if is_16x17(p)]

    playable, reasons, per_reason = 0, {}, collections.defaultdict(list)
    for name, path in maps:
        why = check_map(path)
        reasons[name] = why
        if why is None:
            playable += 1
        else:
            for r in why:
                per_reason[r].append(name)

    print(f"{len(maps)} maps ({'all sizes' if args.all_sizes else '16x17'}), "
          f"PASSIVE_BUILDINGS = {config.PASSIVE_BUILDINGS}: {playable} playable, "
          f"{len(maps) - playable} not.")
    print("\nWhat stops the rest (a map can have several):")
    for r, names in sorted(per_reason.items(), key=lambda kv: -len(kv[1])):
        print(f"  {len(names):4d}  {r}")
    if args.list:
        print()
        for name, why in reasons.items():
            print(f"  {'OK  ' if why is None else 'NO  '} {name}" + ("" if why is None else f"  ({'; '.join(why)})"))


if __name__ == "__main__":
    main()
