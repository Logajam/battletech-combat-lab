"""
tools/port_diff.py - RUST PORT, STAGE 0: print the FIRST difference between two trace.jsonl files.

    python tools/port_diff.py PYTHON_TRACE RUST_TRACE [--dice PYTHON_DICE_JSON]

Prints turn, phase, then the first unit and field path that differs with both values, and (with --dice) the
dice position the phase had reached. Also exits 1 on a difference, 0 if identical. Compare nothing loosely: a
float differs if its text differs.
"""

import json
import sys


def first_diff(a, b, path=""):
    """(path, a_value, b_value) of the first difference, walking dicts in sorted key order; None if equal."""
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                return f"{path}/{k}", "<missing>", b[k]
            if k not in b:
                return f"{path}/{k}", a[k], "<missing>"
            d = first_diff(a[k], b[k], f"{path}/{k}")
            if d:
                return d
        return None
    if isinstance(a, list) and isinstance(b, list):
        for i, (x, y) in enumerate(zip(a, b)):
            d = first_diff(x, y, f"{path}[{i}]")
            if d:
                return d
        if len(a) != len(b):
            return f"{path} (length)", len(a), len(b)
        return None
    if type(a) is not type(b) or a != b:
        return path, a, b
    return None


def main(argv):
    if len(argv) < 2:
        raise SystemExit(__doc__)
    with open(argv[0], encoding="utf-8") as f:
        py = [json.loads(line) for line in f]
    with open(argv[1], encoding="utf-8") as f:
        other = [json.loads(line) for line in f]
    dice = None
    if "--dice" in argv:
        with open(argv[argv.index("--dice") + 1], encoding="utf-8") as f:
            dice = json.load(f)
    prev = None
    for i, (x, y) in enumerate(zip(py, other)):
        d = first_diff(x, y)
        if d:
            print(f"FIRST DIFFERENCE at trace line {i + 1}: turn {x['turn']}, phase {x['phase']!r}")
            print(f"  field {d[0]}\n  python: {d[1]!r}\n  other:  {d[2]!r}")
            if prev:
                print(f"  (last identical line: turn {prev['turn']}, phase {prev['phase']!r}, "
                      f"dice used {prev['dice_used']})")
            if dice is not None:
                lo = prev["dice_used"] if prev else 0
                print(f"  dice drawn in this phase (python tape): {dice[lo:x['dice_used']][:40]}")
            return 1
        prev = x
    if len(py) != len(other):
        print(f"Traces agree for {min(len(py), len(other))} lines, then one ends: python {len(py)}, other {len(other)}")
        return 1
    print(f"IDENTICAL: {len(py)} trace lines")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
