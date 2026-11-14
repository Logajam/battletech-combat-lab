"""
tools/make_availability.py - who fielded which 'Mech, and when: the data behind the Unit Browser's Faction / Year filters
(CL13). Done the way MegaMek's RAT generator does it (megamek/client/ratgenerator/RATGenerator.java:
findChassisAvailabilityRecord / findModelAvailabilityRecord).

    python tools/make_availability.py /path/to/mm-data [--out engine/lab/web/availability.json]

Input: a checkout of github.com/MegaMek/mm-data (public; MegaMek Data, CC BY-NC-SA 4.0) with data/forcegenerator (one
XML per era year: each chassis and model has an availability list like "FS:4,LA:3,IS:2+,CLAN.IS:3-") and
data/universe/factions (one YAML per faction: its tags, years active, and its parent factions, "fallBackFactions").

A faction's rating for a chassis, in an era: its own entry; else its parent's (one parent: that one; several: any of
them); else the "General" entry. A rating of 0 means not available; a trailing + or - only moves the rating by rating
level (not modelled here: any rating above 0 counts as available). A model counts when its chassis does and its own
rating, when it has one, is not 0. Only the factions MegaMek tags PLAYABLE are offered (47). A game year uses the
latest era file at or before it (MegaMek interpolates between files; this does not). An entry's start year
("FS:5:3055") is ignored.

Output: engine/lab/web/availability.json: {"_license", "eras": [years], "factions": [{key, name, start, end, tags}],
"units": {"Chassis Model": [one bit mask per era; bit i = factions[i] could field it]}} (masks fit a JS number).
Credit: CREDITS.md. The file keeps MegaMek's licence header in "_license".
"""
import glob
import json
import os
import sys
import xml.etree.ElementTree as ET

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LICENSE = ("MegaMek Data (C) 2025-2026 by The MegaMek Team is licensed under CC BY-NC-SA 4.0 "
           "(https://creativecommons.org/licenses/by-nc-sa/4.0/). Reduced from data/forcegenerator and data/universe/factions "
           "of github.com/MegaMek/mm-data by tools/make_availability.py. MechWarrior, BattleMech, 'Mech and AeroTech are "
           "registered trademarks of The Topps Company, Inc. Unofficial fan project.")


def parse_codes(text):
    """'FS:4,LA:3-,IS:2+:3055' -> {code: rating}. Rating 0 stays 0."""
    out = {}
    for part in (text or "").split(","):
        bits = part.strip().split(":")
        if len(bits) < 2:
            continue
        digits = "".join(c for c in bits[1] if c.isdigit() or c == "-" and False)
        if digits:
            out[bits[0]] = int(digits)
    return out


def rating_for(codes, faction, factions, depth=0):
    """The rating of `faction` in one availability table (None = nothing listed for it or its parents)."""
    if faction in codes:
        return codes[faction]
    parents = (factions.get(faction) or {}).get("fallBackFactions") or []
    if depth < 8 and parents:
        found = [r for r in (rating_for(codes, p, factions, depth + 1) for p in parents) if r is not None]
        if found:
            return max(found)
    return codes.get("General") if depth == 0 or not parents else None


def main(argv):
    mm = argv[0]
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(ROOT, "engine", "lab", "web", "availability.json")
    factions = {}
    for f in glob.glob(os.path.join(mm, "data", "universe", "factions", "*.yml")):
        d = yaml.safe_load(open(f, encoding="utf-8"))
        factions[d["key"]] = d
    chosen = sorted((d for d in factions.values() if "PLAYABLE" in d.get("tags", [])), key=lambda d: d["name"])
    assert len(chosen) <= 52, "masks must fit a JS number"
    years = sorted(int(os.path.basename(f)[:-4]) for f in glob.glob(os.path.join(mm, "data", "forcegenerator", "[0-9]*.xml")))
    units = {}
    for ei, year in enumerate(years):
        root = ET.parse(os.path.join(mm, "data", "forcegenerator", f"{year}.xml")).getroot()
        for chassis in root.iter("chassis"):
            if chassis.get("unitType") != "Mek":
                continue
            cname = chassis.get("name")
            ccodes = parse_codes((chassis.findtext("availability") or ""))
            for model in chassis.findall("model"):
                key = f"{cname} {model.get('name')}".strip()
                mcodes = model.findtext("availability")
                mcodes = parse_codes(mcodes) if mcodes is not None else None
                mask = 0
                for i, fd in enumerate(chosen):
                    c = rating_for(ccodes, fd["key"], factions)
                    if not c:
                        continue
                    m = rating_for(mcodes, fd["key"], factions) if mcodes else None
                    if m == 0:
                        continue
                    mask |= 1 << i
                if mask:
                    units.setdefault(key, [0] * len(years))[ei] = mask
    data = {"_license": LICENSE, "eras": years,
            "factions": [{"key": d["key"], "name": d["name"], "start": (d.get("yearsActive") or [{}])[0].get("start"),
                          "end": (d.get("yearsActive") or [{}])[-1].get("end"), "tags": d.get("tags", [])} for d in chosen],
            "units": units}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    print(f"{len(chosen)} factions, {len(years)} eras, {len(units)} units -> {out} ({os.path.getsize(out) // 1024} KB)")


if __name__ == "__main__":
    main(sys.argv[1:])
