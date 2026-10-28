"""
tools/build_equipment_bv.py - reads Battle Value data out of a MegaMek source
checkout and writes mechsim/equipment_bv.json (Daniel, 2026-10-28: "6 requires us
to calculate BV ... As usual use Megamek as source material where needed").

    python tools/build_equipment_bv.py <megamek>/megamek/src/megamek/common

MegaMek keeps each item's BV in its Java class (a weapon class's constructor,
or AmmoType / MiscType's create...() methods). This script only READS the
text (nothing of MegaMek is run): it parses the assignments of each class and
its parents, so a weapon inherits its family's flags (F_DIRECT_FIRE, F_ENERGY,
F_LASER...) and fields (heat, rackSize, ammoType) the way Java does, then
writes one record per item, keyed by every name MegaMek knows it by:

    {"<canonical name>": {"kind": "weapon"|"ammo"|"misc", "name": ..., "internal": ..., "names": [...],
     "bv": number or null (a formula - INTEGRATION__battle_value computes it),
     "heat": ..., "heat_adjust": ..., "ammo_type": ..., "rack_size": ...,
     "shots": ..., "flags": [...]}

The MegaMek commit it was read from is stored in the file's "_meta".
"""

import json
import os
import re
import subprocess
import sys

_CLASS = re.compile(r"public\s+(?:abstract\s+)?class\s+(\w+)(?:<[^>]*>)?\s+extends\s+(\w+)")
_STRING = r'"((?:[^"\\]|\\.)*)"'


def _body(text, start):
    """Text of the braces opening at text[start] ('{')."""
    depth, i = 0, start
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:i]
        i += 1
    return text[start + 1:]


def _statements(body, prefix=""):
    """[(kind, key, value)] from one constructor / create method, in order:
    ("set", field, text), ("flags", "or"|"andNot", [F_...]), ("lookup", None, name),
    ("internal", None, name)."""
    out = []
    p = re.escape(prefix)
    body = re.sub(r"//[^\n]*", "", body)               # a comment after a ';' would glue two statements together
    for line in re.split(r";\s*\n", body):
        line = " ".join(line.split())
        m = re.match(r"(?:this\.)?" + p + r"setInternalName\((.+)\)$", line)
        if m:
            out.append(("internal", None, m.group(1)))
            continue
        m = re.match(r"(?:this\.)?" + p + r'addLookupName\(' + _STRING + r"\)$", line)
        if m:
            out.append(("lookup", None, m.group(1)))
            continue
        m = re.match(r"(?:this\.)?" + p + r"flags\s*=\s*(?:this\.)?" + p + r"flags\s*(.+)$", line)
        if m:
            for op, names in re.findall(r"\.(or|andNot)\(([^)]*)\)", m.group(1)):
                out.append(("flags", op, [n.strip().split(".")[-1] for n in names.split(",") if n.strip()]))
            continue
        m = re.match(r"(?:this\.)?" + p + r"(\w+)\s*=\s*(.+)$", line)
        if m and m.group(1) in ("name", "shortName", "bv", "heat", "damage", "rackSize", "shots", "ammoType",
                                "tonnage", "criticalSlots", "heatAdjustmentForBvCalculation", "explosive",
                                "explosionDamage", "ammoCount", "munitionType", "kgPerShot"):
            out.append(("set", m.group(1), m.group(2)))
    return out


def _literal(text, names):
    text = text.strip()
    if re.fullmatch(_STRING, text):
        return re.fullmatch(_STRING, text).group(1)
    if text in ("name", "this.name"):
        return names.get("name")
    try:
        return float(text.rstrip("fFdD").rstrip("L"))
    except ValueError:
        return text                       # a constant ("BV_VARIABLE", "AmmoTypeEnum.AC", ...)


def _apply(state, statements):
    for kind, key, value in statements:
        if kind == "set":
            state[key] = _literal(value, state)
        elif kind == "lookup":
            state.setdefault("lookups", []).append(value)
        elif kind == "internal":
            state["internal"] = _literal(value, state)
        elif kind == "flags":
            flags = set(state.get("flags", ()))
            if key == "or":
                flags |= set(value)
            else:
                flags -= set(value)
            state["flags"] = sorted(flags)
    return state


def _scan_weapons(root):
    classes = {}
    for dirpath, _, files in os.walk(os.path.join(root, "weapons")):
        for fname in files:
            if not fname.endswith(".java"):
                continue
            text = open(os.path.join(dirpath, fname), encoding="utf-8", errors="replace").read()
            m = _CLASS.search(text)
            if not m:
                continue
            cls, parent = m.groups()
            ctor = re.search(r"public\s+" + cls + r"\s*\([^)]*\)\s*\{", text)
            body = _body(text, ctor.end() - 1) if ctor else ""
            classes[cls] = (parent, _statements(body))
    return classes


def _resolve(classes, cls, cache):
    if cls in cache:
        return cache[cls]
    parent, statements = classes[cls]
    state = {}
    if parent in classes:
        state = json.loads(json.dumps(_resolve(classes, parent, cache)))
    cache[cls] = _apply(state, statements)
    return cache[cls]


def _blocks(path, factory_type):
    """Each create...() method of AmmoType / MiscType as (prefix, body)."""
    text = open(path, encoding="utf-8", errors="replace").read()
    for m in re.finditer(r"(?:public|private|protected)\s+static\s+" + factory_type + r"\s+create\w+\s*\([^)]*\)\s*\{", text):
        body = _body(text, m.end() - 1)
        v = re.search(factory_type + r"\s+(\w+)\s*=\s*new\s+" + factory_type, body)
        yield (v.group(1) if v else None), body


def _record(kind, state):
    names = []
    for n in [state.get("name"), state.get("internal")] + list(state.get("lookups", ())):
        if isinstance(n, str) and n not in names:
            names.append(n)
    bv = state.get("bv")
    return {
        "kind": kind,
        "name": state.get("name"),
        "internal": state.get("internal") if isinstance(state.get("internal"), str) else state.get("name"),
        "names": names,
        "bv": bv if isinstance(bv, float) else None,
        "bv_formula": bv if isinstance(bv, str) else None,
        "heat": state.get("heat") if isinstance(state.get("heat"), float) else None,
        "heat_adjust": state.get("heatAdjustmentForBvCalculation") if isinstance(
            state.get("heatAdjustmentForBvCalculation"), float) else 0.0,
        "damage": state.get("damage") if isinstance(state.get("damage"), float) else None,
        "rack_size": state.get("rackSize") if isinstance(state.get("rackSize"), float) else None,
        "shots": state.get("shots") if isinstance(state.get("shots"), float) else None,
        "ammo_type": str(state.get("ammoType")).split(".")[-1] if state.get("ammoType") else None,
        "tonnage": state.get("tonnage") if isinstance(state.get("tonnage"), float) else None,
        "flags": state.get("flags", []),
    }


def build(root):
    records = []
    classes = _scan_weapons(root)
    cache = {}
    for cls in classes:
        state = _resolve(classes, cls, cache)
        if state.get("name") and ("bv" in state or "internal" in state):
            # Skip abstract families: a concrete weapon has a name and a BV (or a formula for it).
            if "bv" in state:
                records.append(_record("weapon", state))
    for fname, factory, prefix_kind, kind in (("AmmoType.java", "AmmoType", "ammo", "ammo"),
                                                ("MiscType.java", "MiscType", "misc", "misc")):
        path = os.path.join(root, "equipment", fname)
        for var, body in _blocks(path, factory):
            if not var:
                continue
            state = _apply({}, _statements(body, var + "."))
            if state.get("name"):
                state.setdefault("bv", 0.0)               # MegaMek's default for an item with no BV line
                records.append(_record(kind, state))
    return records


def _norm(name):
    return re.sub(r"\s+", "", (name or "").strip().lower())


def by_canonical(records, equipment_json):
    """{equipment.json canonical name: record}: a record whose INTERNAL name is
    the canonical name or one of its aliases wins (internal names are unique;
    display names like "LRM 5" are shared by IS and Clan launchers), else the
    first record any of whose names is one."""
    entries = equipment_json["entries"]
    internal, anyname = {}, {}
    for r in records:
        internal.setdefault(_norm(r["internal"]), r)
        for n in r["names"]:
            anyname.setdefault(_norm(n), r)
    out = {}
    for canon, entry in entries.items():
        keys = [canon] + [_norm(a) for a in entry.get("aliases", ())]
        record = next((internal[k] for k in keys if k in internal), None) \
            or next((anyname[k] for k in keys if k in anyname), None)
        if record is not None:
            out[canon] = record
    return out


def main(root):
    records = build(root)
    equipment_json = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                 "mechsim", "equipment.json")))
    matched = by_canonical(records, equipment_json)
    commit = ""
    try:
        commit = subprocess.check_output(["git", "-C", root, "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        pass
    out = {"_meta": {"source": "MegaMek source (BV fields of weapon classes, AmmoType, MiscType)",
                     "commit": commit, "count": len(matched),
                     "note": "keyed by mechsim/equipment.json canonical name; an item with no record has BV 0",
                     "built_by": "tools/build_equipment_bv.py"},
           "items": matched}
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mechsim", "equipment_bv.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=0, sort_keys=True)
    by_kind = {}
    for r in matched.values():
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
    print(f"{len(matched)} of {len(equipment_json['entries'])} equipment.json entries matched {by_kind} -> {path}")


if __name__ == "__main__":
    main(sys.argv[1])
