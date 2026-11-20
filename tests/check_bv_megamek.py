"""
tests/check_bv_megamek.py - our Battle Value against MegaMek's (Daniel, 2026-11-20: "The BV calculator we have built in seems to have
errors ... Mad Cat Mk IV A 2404, Archer C 2 2023, Shadow Cat T 1590: they do not match the results megamek gives").

    python tests/check_bv_megamek.py

`engine/reference/megamek_bv.tsv` holds the BV MegaMek 0.51.01.7's own BVCalculator gives each of the 4,227 units of the unit pack
(pilot 4/5, as built). The Combat Lab's unit list carries our BV for the same files. This check:
  1. the three units Daniel named agree exactly;
  2. no unit differs from MegaMek that is not in `engine/reference/megamek_bv_known_gaps.tsv` (the units still different, 2026-11-20:
     RISC equipment, construction / industrial 'Mechs, a few odd weapons): a NEW gap fails the check; a unit that now matches is
     reported so it can come off the list;
  3. the whole list differs on fewer than 2% of the units.
To remake the table, unpack MegaMek (see megamek_bridge/README.md), load each .mtf with `MekFileParser`, and print
`entity.calculateBattleValue(false, false)`.
Exit code 0 = every check passed.
"""
import json
import os
import socket
import subprocess
import sys
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(REPO_ROOT, "engine")
LAB = os.path.join(ENGINE, "target", "release", "combatlab")
REF = os.path.join(ENGINE, "reference")
NAMED = ["3145/Merc/Mad Cat Mk IV A.mtf", "Force Packs/Wolfs Dragoons/Archer C 2.mtf", "Rec Guides ilClan/Vol 9/Shadow Cat T.mtf"]


def table(name):
    out = {}
    for line in open(os.path.join(REF, name), encoding="utf-8"):
        if line.startswith("#") or not line.strip():
            continue
        parts = line.rstrip("\n").split("\t")
        out[parts[0]] = [int(x) for x in parts[1:]]
    return out


def main():
    subprocess.run(["cargo", "build", "--release", "-q", "-p", "combatlab"], cwd=ENGINE, check=True, capture_output=True)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    # a private copy of the cache folder is not needed: the list's cache key includes the engine's BV version
    proc = subprocess.Popen([LAB, "--no-browser", "--port", str(port)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            env=dict(os.environ, BTSIM_ROOT=REPO_ROOT))
    failures = []
    try:
        if "running" not in proc.stdout.readline():
            raise SystemExit("combatlab did not start: " + proc.stderr.read())
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/list_units", data=b"{}", method="POST")
        with urllib.request.urlopen(req, timeout=600) as r:
            units = json.loads(r.read())["units"]
    finally:
        proc.terminate()
    ours = {}
    for u in units:
        i = u["id"]
        ours[i[len("meks/"):] if i.startswith("meks/") else i] = u
    mm = {k: v[0] for k, v in table("megamek_bv.tsv").items()}
    known = table("megamek_bv_known_gaps.tsv")
    compared, differ = 0, []
    for path, bv in mm.items():
        u = ours.get(path)
        if not u or not str(u.get("bv", "")).lstrip("-").isdigit():
            continue
        compared += 1
        if int(u["bv"]) != bv:
            differ.append((path, int(u["bv"]), bv))

    def check(ok, what):
        print(("  ok    " if ok else "  FAIL  ") + what, flush=True)
        if not ok:
            failures.append(what)

    for n in NAMED:
        check(n in ours and int(ours[n]["bv"]) == mm[n], f"{n}: ours {ours.get(n, {}).get('bv')} v MegaMek {mm[n]}")
    new = [d for d in differ if d[0] not in known]
    check(not new, f"no new gap against MegaMek ({len(new)} new: {new[:5]})")
    fixed = [k for k in known if k in ours and k in mm and int(ours[k]["bv"]) == mm[k]]
    print(f"  note  {len(fixed)} units on the known-gaps list now match: {fixed[:5]}")
    check(compared > 4000 and len(differ) < 0.02 * compared, f"{compared} units compared, {len(differ)} differ ({100 * len(differ) / max(compared, 1):.1f}%)")
    print("FAILED" if failures else "all checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
