"""
INTEGRATION__make_run_dir.py  (NEW 2026-10-18, Claude - tooling, no pile)

Builds a runnable folder from the project's PREFIXED files (the way they're
stored in the claude.ai Project / a download of it):

    python INTEGRATION__make_run_dir.py <folder with prefixed files> <output folder>

Output layout (what the imports expect):

    <out>/INTEGRATION__*.py          integration files, names unchanged
    <out>/mechsim/<name>.py          from MECHSIM__<name>.py
    <out>/mechsim/equipment.json     from MECHSIM__equipment.json (or .mini.json if that's all there is)
    <out>/pathfinder/<name>.py       from PATHFINDER__<name>.py
    <out>/data/*.board               from PATHFINDER__*.board
    <out>/data/*.mtf                 any .mtf files

Then:  cd <out> && python INTEGRATION__main.py

Copies only - never edits or deletes the source files. Skips
MECHSIM__sim_runner.py and PATHFINDER__combat_turn.py/report.py/
validation.py: the battle loop doesn't import them (sim_runner and
validation also import files that aren't in the project and would fail).
"""

import os
import shutil
import sys

SKIP = {"MECHSIM__sim_runner.py", "PATHFINDER__combat_turn.py", "PATHFINDER__report.py",
        "PATHFINDER__validation.py"}


def build(src, out):
    os.makedirs(os.path.join(out, "mechsim"), exist_ok=True)
    os.makedirs(os.path.join(out, "pathfinder"), exist_ok=True)
    os.makedirs(os.path.join(out, "data"), exist_ok=True)
    names = sorted(os.listdir(src))
    copied = []
    full_db = "MECHSIM__equipment.json" in names

    for name in names:
        path = os.path.join(src, name)
        if not os.path.isfile(path) or name in SKIP:
            continue
        dest = None
        if name.startswith("INTEGRATION__") and name.endswith(".py"):
            dest = os.path.join(out, name)
        elif name.startswith("MECHSIM__") and name.endswith(".py"):
            dest = os.path.join(out, "mechsim", name[len("MECHSIM__"):])
        elif name == "MECHSIM__equipment.json" or (name == "MECHSIM__equipment.mini.json" and not full_db):
            dest = os.path.join(out, "mechsim", "equipment.json")
        elif name.startswith("PATHFINDER__") and name.endswith(".py"):
            dest = os.path.join(out, "pathfinder", name[len("PATHFINDER__"):])
        elif name.endswith(".board"):
            base = name[len("PATHFINDER__"):] if name.startswith("PATHFINDER__") else name
            dest = os.path.join(out, "data", base)
        elif name.lower().endswith(".mtf"):
            dest = os.path.join(out, "data", name)
        if dest:
            shutil.copy2(path, dest)
            copied.append((name, os.path.relpath(dest, out)))

    for a, b in copied:
        print(f"  {a:45} -> {b}")
    if not full_db:
        print("NOTE: no MECHSIM__equipment.json found - using the 14-entry mini database. "
              "Most real units will have unrecognized equipment.")
    print(f"\nDone. Run:  cd {out} && python INTEGRATION__main.py")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    build(sys.argv[1], sys.argv[2])
