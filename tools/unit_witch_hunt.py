"""
tools/unit_witch_hunt.py - hunt for the small things in the unit files that the engine mistakes (Daniel, 2026-11-15: "random
spaces, or capitalization"): every complaint the engine makes while reading each of the library's unit files, grouped, and the
spellings of the same armor / structure type.

    python tools/unit_witch_hunt.py [--top 15]

Starts engine/target/release/combatlab on a free port (build it first), asks it for the unit list (each unit carries the
engine's own `warnings`, see engine/lab/src/describe.rs) and prints:
  * how many units warn, and the commonest warnings with an example unit;
  * the armor / structure texts the engine does not recognise (they read as Standard);
  * the armor / structure / tech texts that are the same apart from spaces, hyphens or capitals.
"""
import collections
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAB = os.path.join(ROOT, "engine", "target", "release", "combatlab")


def main(argv):
    top = int(argv[argv.index("--top") + 1]) if "--top" in argv else 15
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    proc = subprocess.Popen([LAB, "--no-browser", "--port", str(port)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=dict(os.environ, BTSIM_ROOT=ROOT))
    try:
        proc.stdout.readline()
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/list_units", data=b"{}", method="POST")
        units = json.loads(urllib.request.urlopen(req, timeout=600).read())["units"]
    finally:
        proc.terminate()
    warned = [u for u in units if u.get("warnings")]
    print(f"{len(units)} units; {len(warned)} with warnings; {sum(1 for u in units if not u.get('ok'))} the engine cannot play\n")
    shape = lambda w: re.sub(r"\d+", "N", re.sub(r"'[^']*'", "'X'", w))[:140]
    count, example = collections.Counter(), {}
    for u in units:
        for w in u.get("warnings", []):
            count[shape(w)] += 1; example.setdefault(shape(w), (u["name"], w))
    print("COMMONEST WARNINGS")
    for k, n in count.most_common(top):
        print(f"  {n:5d}  {k}\n         e.g. {example[k][0]}: {example[k][1][:150]}")
    for kind in ("global armor type", "structure type", "armor type"):
        c = collections.Counter(m.group(1) for u in units for w in u.get("warnings", []) for m in [re.search(r"unrecognized " + kind + r" '([^']*)'", w)] if m)
        if c:
            print(f"\nUNRECOGNISED {kind.upper()} TEXTS ({sum(c.values())} units; each reads as Standard)")
            for t, n in c.most_common(top): print(f"  {n:5d}  {t}")
    for field in ("armor_type", "structure", "tech", "role", "config"):
        groups = collections.defaultdict(collections.Counter)
        for u in units:
            if u.get(field): groups[re.sub(r"[\s\-_]+", "", str(u[field]).lower())][u[field]] += 1
        same = [dict(v) for v in groups.values() if len(v) > 1]
        print(f"\nSPELLINGS OF THE SAME {field.upper()} ({len(same)} groups)")
        for g in same[:top]: print("  ", g)


if __name__ == "__main__":
    main(sys.argv[1:])
