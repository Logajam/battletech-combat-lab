"""
tools/event_coverage.py - how often each EVENT TYPE (and a few sub-kinds) happens in each battle of a set
(INTEGRATION__EVENTS.md; the coverage table behind the dense reference list, 2026-11-24).

    python tools/event_coverage.py --reference                       # the saved events of engine/reference/events
    python tools/event_coverage.py --reference-dir POOL              # another folder: the pool of check_rust_reference.py --all --out POOL
    python tools/event_coverage.py --answer-key                      # plays every answer-key scenario (engine/fixtures) with events on
    python tools/event_coverage.py --reference --answer-key --tsv out.tsv
    python tools/event_coverage.py --reference --min 3               # also lists the types below 3

Rows are battles, columns are event kinds ("KIND") and sub-kind keys ("KIND:sub", see SUBKEYS: informational, not a requirement).
`--tsv FILE` keeps the whole table (source, name, events, turns, then one count a column). The answer key's battles are the
scenarios only: their old Python logs do not matter, so each is played by btsim on seed 1 with its own bots.
`load(...)` / `counts_of(...)` are used by tools/choose_reference_set.py and tests/check_rust_reference.py.
"""
import gzip
import json
import os
import subprocess
import sys
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BTSIM = os.path.join(ROOT, "engine", "target", "release", "btsim")
REFERENCE_EVENTS = os.path.join(ROOT, "engine", "reference", "events")
FIXTURES = os.path.join(ROOT, "engine", "fixtures")


def kinds():
    out = subprocess.run([BTSIM, "--events-list"], capture_output=True, text=True, check=True).stdout
    return [k["kind"] for k in json.loads(out)["kinds"]]


def keys_of(ev):
    """The coverage keys one event counts toward: its kind, plus a sub-kind key for the kinds in SUBKEYS."""
    k = ev["k"]
    yield k
    if k == "ATTACK" and ev.get("w"):
        yield f"WEAPON:{ev['w']}"   # every distinct weapon fired: the cov_ battles exist for these, a dense set must still fire each
    sub = SUBKEYS.get(k)
    if sub:
        v = sub(ev)
        if v is not None:
            yield f"{k}:{v}"


# sub-kind keys: coverage of the cases inside a kind (a kind is covered by its count; these say which cases; the set chooser
# wants each seen case at least once, WEAPON:<name> included)
SUBKEYS = {
    "CRIT": lambda e: e.get("s"),
    "COMPONENT_DESTROYED": lambda e: e.get("s"),
    "AMMO_EXPLOSION": lambda e: e.get("s"),
    "ATTACK": lambda e: e.get("s"),
    "HIT": lambda e: e.get("s"),
    "TAG_DESIGNATE": lambda e: e.get("s") + ("-hit" if e.get("ok") else "-miss"),
    "HOMING_HIT": lambda e: e.get("s"),
    "STAND_ATTEMPT": lambda e: "pass" if e.get("ok") else "fail",
    "CONSCIOUSNESS": lambda e: "pass" if e.get("ok") else "fail",
    "RESTART": lambda e: "pass" if e.get("ok") else "fail",
    "INITIATIVE_ROLL": lambda e: "tie-reroll" if e.get("n", 1) > 1 else None,
    "MOVE": lambda e: e.get("s"),
    "HAZARD": lambda e: e.get("s"),
    "SPOT": lambda e: e.get("s"),
    "FALL": lambda e: (e.get("s") or "").split(" ")[0],
    "PILOT_HIT": lambda e: e.get("s"),
}


def counts_of(events):
    c = Counter()
    for ev in events:
        c.update(keys_of(ev))
    return c


def read_events_file(path):
    """(teams, events) of a reference event file (header line, then one event a line)."""
    lines = gzip.open(path, "rt").read().splitlines()
    return json.loads(lines[0]).get("teams", {}), [json.loads(l) for l in lines[1:] if l.strip()]


def gear_keys(units_json):
    """GEAR:<name> keys for what a scenario's units field: every piece of equipment by name, and the engine / gyro / cockpit /
    armor / structure / myomer kinds. A dense set must still field each (the cov_ battles exist for these: events alone do not
    show that a Taser, a capacitor, a turret, an ICE engine or a partial wing was in the battle)."""
    keys = set()
    for u in json.load(open(units_json)).values():
        for slots in u.get("crits", {}).values():
            for s in slots:
                if isinstance(s, dict) and s.get("name") and s.get("category") != "ammo":
                    keys.add("GEAR:" + s["name"])
        keys.add("GEAR:engine " + "".join(c for c in str(u.get("engine_desc", "")) if not c.isdigit()).strip())
        for f in ("gyro_type", "cockpit_type", "armor_desc", "structure_desc", "myomer"):
            if u.get(f):
                keys.add(f"GEAR:{f.split('_')[0]} {u[f]}")
    return keys


def load_reference(events_dir=None):
    """{name: (counts, turns)} for the saved reference events (+ GEAR keys from the scenarios in the reference zip). `events_dir`:
    another folder of events (the pool `check_rust_reference.py --all --out DIR` writes), default the reference list's own."""
    events_dir = events_dir or REFERENCE_EVENTS
    import zipfile
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    import check_rust_reference as ref
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(ref.SCENARIOS_ZIP) as z:
            z.extractall(tmp)
        folder_of = {name: folder for name, folder, _ in ref.battles(tmp)}
        for f in sorted(os.listdir(events_dir)):
            if f.endswith(".events.jsonl.gz"):
                name = f[:-len(".events.jsonl.gz")]
                _, ev = read_events_file(os.path.join(events_dir, f))
                c = counts_of(ev)
                units = os.path.join(tmp, folder_of.get(name, name), "units.json")
                if os.path.exists(units):
                    c.update({k: 1 for k in gear_keys(units)})
                out[name] = (c, max((e["t"] for e in ev), default=0))
    return out


def play_answer_key(name):
    """One answer-key scenario played by btsim on seed 1 with events on: (counts, turns)."""
    folder = os.path.join(FIXTURES, name)
    with tempfile.TemporaryDirectory() as tmp:
        evf = os.path.join(tmp, "e.jsonl")
        t0 = time.perf_counter()
        p = subprocess.run([BTSIM, folder, "--battles", "1", "--seed", "1", "--threads", "1", "--events", "--events-out", evf],
                           capture_output=True, text=True)
        TIMES["key:" + name] = time.perf_counter() - t0
        if p.returncode != 0 or not os.path.exists(evf):
            return None
        row = json.loads(open(evf).readline())
        c = counts_of(row["events"])
        c.update({k: 1 for k in gear_keys(os.path.join(folder, "units.json"))})
        return c, max((e["t"] for e in row["events"]), default=0)


TIMES = {}   # answer-key scenario -> seconds it took (--times FILE)


def answer_key_names():
    return sorted(d for d in os.listdir(FIXTURES) if not d.startswith(("_", "stage")) and os.path.exists(os.path.join(FIXTURES, d, "units.json")))


def load_answer_key():
    if not os.path.isdir(FIXTURES):
        subprocess.run([sys.executable, os.path.join(ROOT, "tools", "unpack_answer_key.py")], check=True)
    names = answer_key_names()
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        played = list(pool.map(play_answer_key, names))
    out = {}
    for n, p in zip(names, played):
        if p is None:
            print(f"(answer key {n}: btsim failed)", file=sys.stderr)
        else:
            out[n] = p
    return out


def table(sets, all_kinds):
    """The columns: every kind first, then every sub-kind key seen."""
    sub = sorted({k for rows in sets.values() for c, _ in rows.values() for k in c if ":" in k})
    return list(all_kinds) + sub


def main(argv):
    all_kinds = kinds()
    sets = {}
    if "--reference" in argv or "--reference-dir" in argv:
        sets["reference"] = load_reference(argv[argv.index("--reference-dir") + 1] if "--reference-dir" in argv else None)
    if "--answer-key" in argv:
        sets["answer-key"] = load_answer_key()
    if not sets:
        raise SystemExit(__doc__)
    if "--times" in argv and TIMES:
        with open(argv[argv.index("--times") + 1], "w") as f:
            f.writelines(f"{n}\t{s:.2f}\n" for n, s in sorted(TIMES.items()))
    cols = table(sets, all_kinds)
    n = int(argv[argv.index("--min") + 1]) if "--min" in argv else 3
    print(f"{'event kind':22s} " + " ".join(f"{s + ' events':>16s} {s + ' battles':>16s}" for s in sets) + f" {'battles total':>14s}")
    for k in cols:
        if k.startswith("GEAR:") and "--gear" not in argv:
            continue   # a hundred equipment names: --gear prints them
        row, total_battles = [], 0
        for s, rows in sets.items():
            ev = sum(c[k] for c, _ in rows.values())
            b = sum(1 for c, _ in rows.values() if c[k] > 0)
            total_battles += b
            row.append(f"{ev:16d} {b:16d}")
        print(f"{k:22s} " + " ".join(row) + f" {total_battles:14d}" + ("   <-- below %d" % n if total_battles < n and ":" not in k else ""))
    if "--tsv" in argv:
        path = argv[argv.index("--tsv") + 1]
        with open(path, "w") as f:
            f.write("\t".join(["source", "battle", "turns", "events"] + cols) + "\n")
            for s, rows in sets.items():
                for name, (c, turns) in rows.items():
                    name = name if s == "reference" else "key:" + name   # an answer-key scenario may share a name with a reference battle
                    f.write("\t".join([s, name, str(turns), str(sum(v for k, v in c.items() if ":" not in k))] + [str(c[k]) for k in cols]) + "\n")
        print(f"table written to {path}")
    low = [k for k in all_kinds if sum(1 for rows in sets.values() for c, _ in rows.values() if c[k] > 0) < n]
    print(f"\n{len(low)} event kinds in fewer than {n} battles: {', '.join(low) if low else 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
