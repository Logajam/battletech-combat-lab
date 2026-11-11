"""
tools/port_stage3.py - RUST PORT stage 3 fixtures: units (INTEGRATION__RUST_PORT.md).

    python tools/port_stage3.py [OUT_DIR]        # default engine/fixtures/stage3

Unpacks data/meks.zip into engine/fixtures/_mtf/ and parses EVERY .mtf with the Python parse_mtf. Writes units.jsonl,
one line per file: {"file", "stdout"} plus either "unit" (the mech's reflective dump - tools/port_record.dump_unit,
equipment included) or "error" (the refusal's text). The Rust parser must reproduce every line.
"""
import contextlib
import io
import json
import os
import sys
import zipfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
os.chdir(REPO_ROOT)
os.environ.setdefault("INTEGRATION_DATA_DIR", "./data")
import INTEGRATION__config as config  # noqa: E402,F401
import INTEGRATION__orchestrator  # noqa: E402,F401 - puts MECHSIM and PATHFINDER on the path
from mtf_parser import parse_mtf  # noqa: E402
from port_record import dump_unit, id_table  # noqa: E402


def main(argv):
    out = argv[0] if argv else os.path.join(REPO_ROOT, "engine", "fixtures", "stage3")
    os.makedirs(out, exist_ok=True)
    mtf_dir = os.path.join(REPO_ROOT, "engine", "fixtures", "_mtf")
    names = []
    with zipfile.ZipFile("data/meks.zip") as z:
        for n in sorted(z.namelist()):
            if n.endswith(".mtf"):
                target = os.path.join(mtf_dir, n)
                if not os.path.exists(target):
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with open(target, "wb") as f:
                        f.write(z.read(n))
                names.append(n)
    ok = bad = 0
    with open(os.path.join(out, "units.jsonl"), "w", encoding="utf-8", newline="\n") as f:
        for n in names:
            buf = io.StringIO()
            entry = {"file": n}
            with contextlib.redirect_stdout(buf):
                try:
                    mech = parse_mtf(os.path.join(mtf_dir, n))
                    entry["unit"] = dump_unit(mech, {}, id_table(mech))
                    ok += 1
                except Exception as e:                      # ValueError for refusals; anything else is a finding
                    entry["error"] = f"{type(e).__name__}: {e}"
                    bad += 1
            entry["stdout"] = buf.getvalue()
            f.write(json.dumps(entry) + "\n")
    print(f"{len(names)} units: {ok} parsed, {bad} refused; fixtures in {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
