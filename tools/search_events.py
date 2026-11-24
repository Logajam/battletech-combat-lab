"""
tools/search_events.py - search sets of battles for EVENTS (INTEGRATION__EVENTS.md; Daniel, 2026-11-24).

    python tools/search_events.py [SOURCE ...] --example engine-hits-4
    python tools/search_events.py trial_records/2026-11-25_round_robin_x.jsonl --kind CRIT --where s=Engine --group u,t,p --count '>=4'
    python tools/search_events.py --reference --query-file my_query.json --limit 50
    python tools/search_events.py --list-examples | --list-kinds

SOURCE = a trial records file (its event sidecars are followed), a sidecar (*.events.jsonl.gz), a folder of either, or
`--reference` for the reference battles' events (engine/reference/events). No source = every records file in trial_records/.
A battle recorded before events existed simply has none and is skipped (it is counted as "without events").

The QUERY is JSON (the language is documented at the top of engine/lab/web/events_query.js, the one engine the replay tab uses
too: this tool runs that same file under node, so both give the same answer). Flags build the simple queries:
    --kind K[,K]   --where FIELD=VALUE | FIELD'>=3' | FIELD!=V (repeat)   --group F,F   --count '>=4'
and --example NAME / --query JSON / --query-file FILE give anything (sequences: several `steps`, `same`, `$a.u` references).

Output: per match the set, battle number, seed, turn, phase, the events, and the exact command that replays that battle
(`btsim ... --sims N --history N`; the page lands in replays/). Then counts per battle and per set. --json for machine output.
"""
import glob
import gzip
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECORDS = os.path.join(ROOT, "trial_records")
REFERENCE = os.path.join(ROOT, "engine", "reference", "events")
BTSIM = os.path.join(ROOT, "engine", "target", "release", "btsim")
RUNNER = os.path.join(ROOT, "tools", "events_search_runner.js")

# Prepared queries (Daniel's own examples first), kept in engine/lab/web/events_examples.json: the one list, which the replay tab
# shows too. name -> (what it finds, query)
EXAMPLES_FILE = os.path.join(ROOT, "engine", "lab", "web", "events_examples.json")
EXAMPLES = {e["name"]: (e["what"], e["query"]) for e in json.load(open(EXAMPLES_FILE))}


def parse_where(items):
    """--where terms (FIELD=V, FIELD!=V, FIELD>=V, >, <=, <) -> a `where` object. Numbers and true/false are read as such."""
    ops = [("!=", "ne"), (">=", "gte"), ("<=", "lte"), ("=", "eq"), (">", "gt"), ("<", "lt")]
    where = {}
    for item in items:
        for sym, op in ops:
            if sym in item:
                field, value = item.split(sym, 1)
                break
        else:
            raise SystemExit(f"--where {item!r}: use FIELD=VALUE, !=, >=, <=, > or <")
        try:
            value = json.loads(value)
        except ValueError:
            pass
        where.setdefault(field, {})[op] = value
    return {f: (c["eq"] if list(c) == ["eq"] else c) for f, c in where.items()}


def build_query(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default
    if "--example" in argv:
        name = opt("--example")
        if name not in EXAMPLES:
            raise SystemExit(f"no example {name!r}; --list-examples shows them")
        return dict(EXAMPLES[name][1], name=name)
    if "--query" in argv:
        return json.loads(opt("--query"))
    if "--query-file" in argv:
        return json.load(open(opt("--query-file")))
    if "--kind" in argv:
        kinds = opt("--kind").split(",")
        wheres = [argv[i + 1] for i, a in enumerate(argv) if a == "--where"]
        q = {"steps": [{"kind": kinds if len(kinds) > 1 else kinds[0], "where": parse_where(wheres)}]}
        if "--group" in argv:
            q["group"] = opt("--group").split(",")
        if "--count" in argv:
            c = parse_where(["n" + opt("--count")])["n"]
            q["count"] = c if isinstance(c, dict) else {"eq": c}
        return q
    raise SystemExit("give a query: --example NAME, --query JSON, --query-file FILE or --kind KIND [--where ...]")


# ---- the battles ---------------------------------------------------------------------------------------------------------

def sidecars_of(path):
    """Event files a source names: a records file's sidecars, a sidecar itself, or a folder's of either."""
    if os.path.isdir(path):
        out = []
        for p in sorted(glob.glob(os.path.join(path, "**", "*"), recursive=True)):
            if p.endswith(".events.jsonl.gz") or (p.endswith(".jsonl") and os.sep + "progress" + os.sep not in p and os.sep + "events" + os.sep not in p):
                out += sidecars_of(p)
        return out
    if path.endswith(".gz"):
        return [path]
    out = []   # a records file
    base = os.path.dirname(os.path.abspath(path))
    for line in open(path):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict) and rec.get("events"):
            out.append(os.path.join(base, rec["events"]))
    return out


def battles_of(sidecar, counts):
    """Yields one dict per battle in an event file: id, sim, seed, events, teams and the replay command (or a hint)."""
    rows = [json.loads(l) for l in gzip.open(sidecar, "rt") if l.strip()]
    head = rows[0] if rows and rows[0].get("header") else None
    if head:
        rows = rows[1:]
    is_ref = sidecar.startswith(REFERENCE)
    stem = os.path.basename(sidecar).replace(".events.jsonl.gz", "").replace(".jsonl.gz", "")
    if is_ref:
        # a reference battle file: header line {events_version, teams}, then one event per line
        head = rows_head = json.loads(gzip.open(sidecar, "rt").readline())
        events = [json.loads(l) for l in list(gzip.open(sidecar, "rt"))[1:] if l.strip()]
        yield {"id": f"reference/{stem}", "set": "reference", "sim": 1, "seed": 1, "events": events, "teams": head.get("teams", {}),
               "replay": f"python tests/check_rust_reference.py --only {stem} --exact --history replays"}
        return
    for r in rows:
        if "events" not in r:
            counts["without"] += 1
            continue
        yield {"id": f"{stem}#{r['sim']}", "set": stem, "sim": r["sim"], "seed": r.get("seed"), "events": r["events"], "teams": r.get("teams", {}),
               "replay": replay_command(head, r["sim"])}


def replay_command(head, sim):
    """The exact btsim command that plays battle `sim` of a batch again and writes its replay page."""
    cmd = (head or {}).get("cmd")
    if not cmd:
        return f"(no command was kept for this batch: it is battle {sim} of its set; tools/round_robin.py / hydra_trial.py with the same arguments plays it)"
    cmd = list(cmd)
    folder = cmd[1]
    note = "" if os.path.isdir(folder) else f"   # NOTE: {folder} was a temporary folder; remake the scenario first"
    return " ".join(cmd + ["--sims", str(sim), "--history", str(sim), "--history-dir", "replays"]) + note


def all_battles(sources, counts):
    for src in sources:
        for sc in sidecars_of(src):
            if not os.path.exists(sc):
                print(f"(missing event file {sc})", file=sys.stderr)
                continue
            yield from battles_of(sc, counts)


# ---- running the query -------------------------------------------------------------------------------------------------

def search(query, battles, counts):
    """Runs the query over battles with node (the replay tab's own engine); yields (battle, matches, capped)."""
    proc = subprocess.Popen(["node", RUNNER], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
    by_id = {}
    proc.stdin.write(json.dumps(query) + "\n")

    import threading
    def feed():
        try:
            for b in battles:
                by_id[b["id"]] = b
                proc.stdin.write(json.dumps({"id": b["id"], "events": b["events"], "teams": b["teams"]}, separators=(",", ":")) + "\n")
                counts["searched"] += 1
        except BrokenPipeError:
            pass
        finally:
            try:
                proc.stdin.close()
            except BrokenPipeError:
                pass
    t = threading.Thread(target=feed)
    t.start()
    for line in proc.stdout:
        r = json.loads(line)
        if "error" in r:
            raise SystemExit(f"query error: {r['error']}")
        yield by_id.pop(r["id"]), r["matches"], r["capped"]
    t.join()
    proc.wait()
    if proc.returncode not in (0, None):
        raise SystemExit(f"node failed (exit {proc.returncode}); the search needs node")


def describe(ev):
    parts = [ev["k"]]
    if "u" in ev:
        parts.append(ev["u"] + (f" -> {ev['o']}" if "o" in ev else ""))
    elif "o" in ev:
        parts.append(f"-> {ev['o']}")
    for f in ("s", "w", "l"):
        if ev.get(f):
            parts.append(str(ev[f]))
    if "tn" in ev:
        parts.append(f"needs {ev['tn']}")
    if "r" in ev:
        parts.append(f"rolled {ev['r']}")
    if "ok" in ev:
        parts.append("yes" if ev["ok"] else "no")
    if "d" in ev:
        parts.append(f"{ev['d']:g} dmg")
    if "n" in ev:
        parts.append(f"n={ev['n']}")
    return " ".join(parts)


def main(argv):
    if "--list-examples" in argv:
        for name, (what, q) in EXAMPLES.items():
            print(f"{name}\n    {what}\n    {json.dumps(q)}")
        return 0
    if "--list-kinds" in argv:
        out = subprocess.run([BTSIM, "--events-list"], capture_output=True, text=True, check=True).stdout
        data = json.loads(out)
        print(f"event list version {data['version']}; phases: {', '.join(data['phases'])}")
        for k in data["kinds"]:
            print(f"  {k['kind']:20s} {k['fields']}")
        return 0
    flags_with_value = {"--example", "--query", "--query-file", "--kind", "--where", "--group", "--count", "--limit"}
    sources = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] not in flags_with_value)]
    if "--reference" in argv:
        sources.append(REFERENCE)
    if not sources:
        sources = sorted(glob.glob(os.path.join(RECORDS, "*.jsonl")))
    query = build_query(argv)
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else 20
    as_json = "--json" in argv
    counts = {"searched": 0, "without": 0}
    per_set, per_battle, shown, total = {}, [], 0, 0
    out_rows = []
    for b, matches, capped in search(query, all_battles(sources, counts), counts):
        s = per_set.setdefault(b["set"], [0, 0, 0])
        s[0] += 1
        if matches:
            s[1] += 1
            s[2] += len(matches)
            total += len(matches)
            per_battle.append((b["id"], len(matches), capped))
            for m in matches:
                row = {"battle": b["id"], "sim": b["sim"], "seed": b["seed"], "turn": m["t"], "phase": m["p"], "units": m["units"],
                       "events": m["events"], "replay": b["replay"]}
                if "group" in m:
                    row["group"], row["count"] = m["group"], m["count"]
                out_rows.append(row)
    if as_json:
        print(json.dumps({"query": query, "searched": counts["searched"], "without_events": counts["without"], "matches": out_rows}))
        return 0
    name = query.get("name") or json.dumps(query)
    print(f"QUERY {name}")
    for row in out_rows:
        if shown >= limit:
            break
        shown += 1
        extra = f"  (group {row['group']}, {row['count']} events)" if "group" in row else ""
        print(f"\n{row['battle']}  seed {row['seed']}  turn {row['turn']}  phase {row['phase']}  units {', '.join(row['units'])}{extra}")
        for ev in row["events"][:12]:
            print(f"    t{ev['t']} {ev['p']:9s} {describe(ev)}")
        if len(row["events"]) > 12:
            print(f"    ... {len(row['events']) - 12} more")
        print(f"    replay: {row['replay']}")
    if len(out_rows) > shown:
        print(f"\n... {len(out_rows) - shown} more matches (--limit N shows more; --json gives all)")
    print("\nPER BATTLE (battles with a match):")
    for bid, n, capped in per_battle[:40]:
        print(f"    {bid}: {n} match{'es' if n != 1 else ''}{' (capped)' if capped else ''}")
    if len(per_battle) > 40:
        print(f"    ... {len(per_battle) - 40} more battles")
    print("\nPER SET (battles searched, battles with a match, matches):")
    for name, (n, hit, m) in per_set.items():
        print(f"    {name}: {n}, {hit}, {m}")
    print(f"\nTOTAL: {counts['searched']} battles searched, {len(per_battle)} with a match, {total} matches"
          + (f"; {counts['without']} battles without events skipped" if counts["without"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
