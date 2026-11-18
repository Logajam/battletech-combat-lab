#!/usr/bin/env python3
"""THE CHECKLIST: every correction Daniel has made on the HD models, as checks (Claude, 2026-11-18).

Daniel, 2026-11-18: "I suppose we should make a checklist of everything I've bitched about for all the mechs, and run the ones that
apply to the atlas." Each item is one of his corrections (the numbers are reference_art/blocks/ASSEMBLY_PRINCIPLES.md's, where
each is written out WITH his words and the reason), with:
  applies  which models it concerns (a bird-legged 'Mech, one with jump jets, one with a head ...)
  check    AUTOMATIC (a test on the model: floating parts, lines of fire, the measuring test, the articulation test, painted lines,
           large flat faces, weapon symmetry, balance, the pose camera) or BY EYE (a verdict written down for each model, with its
           reason, in reference_art/checklist/<unit>.json - Claude's when it builds, Daniel's word overrides).

    python -I tools/lowpoly_checklist.py "Atlas AS7-D"          # run it: reference_art/checklist/<unit> report.md
    python -I tools/lowpoly_checklist.py "Atlas AS7-D" --quick  # without the articulation sweeps (about 2 minutes saved)

The legs are not swept by the articulation test (Daniel, 2026-11-18: "the legs are fused in place and can't move. Don't actually test
that. They look fine"). PRIVATE (reference_art/).
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lowpoly_ref as L  # noqa: E402
import lowpoly_hd as HD  # noqa: E402

CHECK_DIR = os.path.join(L.REF, "checklist")
VENT_WORDS = ("vent", "louvre", "grille", "slat", "stripe", "gap", "bore", "grin", "tooth", "split", "cooling", "throat", "eye", "nasal",
              "hatch", "socket", "hub")


def _name(sid):
    return re.sub(r"_\d+.*$", "", sid)


def has(model, *names):
    return any(any(_name(p["id"]).startswith(n) for n in names) for p in model["parts"])


# (number, Daniel's correction in short, applies(model) -> bool, "auto" or "eye")
ITEMS = [
    (1, "every block connects to its bone (sockets)", lambda m: True, "eye"),
    (2, "blocks sit flush to the surface they are on", lambda m: True, "eye"),
    (3, "the silhouette from above matters as much as front and back", lambda m: True, "eye"),
    (4, "the record sheet says what a part IS and where its weapons are", lambda m: True, "auto"),
    (5, "bird legs bend backward", lambda m: m["unit"] in ("Catapult",), "eye"),
    (6, "proportion of legs, hip, lower and upper torso", lambda m: True, "auto"),
    (7, "arm weapons in line with the limb", lambda m: has(m, "laser_barrel", "srm4_pod", "rack"), "eye"),
    (8, "the centre of gravity over the legs", lambda m: True, "auto"),
    (9, "every shape on the art is something: find what it houses", lambda m: True, "eye"),
    (10, "joints built out where the muscles go (ankles)", lambda m: True, "eye"),
    (12, "built as if it must articulate (pivots recorded)", lambda m: True, "auto"),
    (13, "bevels are bold", lambda m: True, "eye"),
    (14, "the legs splay a little, the feet flat", lambda m: True, "auto"),
    (15, "a joint's root stays inside whatever angle it takes (waist)", lambda m: True, "eye"),
    (16, "the cockpit wraps or cuts into the structure", lambda m: True, "eye"),
    (17, "jump jets thrust through the centre of mass", lambda m: any(p.get("role", "").startswith("jumpjet") for p in m["parts"]), "auto"),
    (18, "shown in the five-view format", lambda m: True, "auto"),
    (20, "no floating bits", lambda m: True, "auto"),
    (21, "every weapon's line of fire is clear (its hole)", lambda m: True, "auto"),
    (22, "unexplained art is a reserved bay, not a guess", lambda m: True, "eye"),
    (23, "a plan to mount weapons up to each location's slot limit", lambda m: True, "auto"),
    (24, "keep a recognisable feature even when it does not work", lambda m: True, "eye"),
    (25, "a forearm can carry a pod AND end in a hand", lambda m: has(m, "fist"), "eye"),
    (26, "a mounted block sits on a flat face, never an edge", lambda m: True, "eye"),
    (27, "a bulge is the body's own shape, not a plate laid on it", lambda m: True, "eye"),
    (28, "a joint housing reaches into the block it stands on (ankle into foot)", lambda m: True, "eye"),
    (29, "a head is a designed piece, not a bare dome", lambda m: has(m, "dome", "cranium", "head_shell"), "eye"),
    (30, "a head that turns has a gap under it", lambda m: HD._pivot(m, "neck") is not None, "auto"),
    (32, "a box is the last resort for a body section", lambda m: True, "eye"),
    (33, "not every joint shows its drum (covers on some)", lambda m: True, "auto"),
    (34, "no large flat space (front, back, underside)", lambda m: True, "auto"),
    (35, "torso weapons flat on the sections, grouped, sized to their mount", lambda m: True, "eye"),
    (36, "a dynamic pose", lambda m: True, "auto"),
    (37, "weapon layouts are symmetric", lambda m: True, "auto"),
    (39, "a hole cut by a weapon's fire must be meant", lambda m: True, "auto"),
    (40, "measured against the drawing (the standard test)", lambda m: True, "auto"),
    (41, "the dynamic pose copies the TRO drawing", lambda m: True, "eye"),
    (42, "a forearm offers several mount slots, the built weapons symmetric", lambda m: has(m, "forearm"), "auto"),
    (43, "the bigger weapon takes the bigger flat space", lambda m: True, "eye"),
    (44, "the pose camera stays above the floor", lambda m: True, "auto"),
    (45, "every detail is for something; an arm does not read as a leg", lambda m: True, "eye"),
    (46, "a death's head must frighten", lambda m: m["unit"] == "Atlas", "eye"),
    (49, "compared section by section, differences listed", lambda m: True, "eye"),
    (50, "a head is one shell, not a dome with a face stuck on", lambda m: has(m, "head_shell", "cranium", "dome", "face"), "eye"),
    (51, "every joint moves through its range without clipping (legs excepted)", lambda m: True, "auto"),
    (52, "no painted-on lines", lambda m: True, "auto"),
    (53, "the head sits over the neck, the neck over the spine", lambda m: HD._pivot(m, "neck") is not None, "auto"),
    (54, "an assault torso is built up in depth", lambda m: m.get("mass", 0) >= 80, "eye"),
]


# ---------------------------------------------------------------------------- the automatic checks: (ok, detail)
def auto(n, unit, model, sol, quick):
    import numpy as np
    if n in (4, 20, 21, 39):
        errors, _ = L.check_model(model)
        want = {4: ("weapon", "jump", "record", "assembl"), 20: ("floating",), 21: ("blocked",), 39: ("cuts through",)}[n]
        bad = [e for e in errors if any(w in e for w in want)]
        return not bad, "; ".join(bad[:3]) or "clean"
    if n in (6, 40):
        import lowpoly_measure as M
        try:
            res = M.compare(unit)
        except Exception as ex:                                   # noqa: BLE001
            return None, "no sheet measured (%s)" % ex
        flags = res["flags"]
        expl = res.get("explained", [])
        if flags:
            return False, "%d landmark(s) off: " % len(flags) + "; ".join(flags[:4])
        return True, "every landmark within 6 %" + (" but %d EXPLAINED: %s" % (len(expl), "; ".join(expl)) if expl else "")
    if n == 8:
        com = model.get("centre_of_mass") or HD.centre_of_mass(model["parts"])
        feet = [s_ for s_ in sol if s_["assembly"].startswith("leg_") and min(v[1] for v in s_["verts"]) < 0.05]
        pts = np.array([v for s_ in feet for v in s_["verts"]])
        lo, hi = pts.min(0), pts.max(0)
        inside = lo[0] <= com[0] <= hi[0] and lo[2] <= com[2] <= hi[2]
        return inside, "centre of mass (%.2f, %.2f) %s the feet's span x %.2f..%.2f, z %.2f..%.2f" % (
            com[0], com[2], "inside" if inside else "OUTSIDE", lo[0], hi[0], lo[2], hi[2])
    if n == 12:
        need = [k for k in ("hip_L", "knee_L", "ankle_L") if k not in model.get("pivots", {})]
        return not need, "pivots: %d recorded" % len(model.get("pivots", {})) + (", missing " + ", ".join(need) if need else "")
    if n == 14:
        pv = model.get("pivots", {})
        ok = "hip_L" in pv and "ankle_L" in pv and pv["ankle_L"]["centre"][0] > pv["hip_L"]["centre"][0] + 0.01
        return ok, "ankle %s the hip's x" % ("outside" if ok else "NOT outside")
    if n == 17:
        com = model.get("centre_of_mass") or HD.centre_of_mass(model["parts"])
        jj = [s_["centroid"] for s_ in sol if s_.get("role", "").startswith("jumpjet")]
        if not jj:
            return None, "no jets"
        zc = sum(c[2] for c in jj) / len(jj)
        return abs(zc - com[2]) < 0.3, "jets' mean z %.2f v centre of mass %.2f" % (zc, com[2])
    if n == 18:
        path = os.path.join(L.SHEETS, unit + " HD turnaround.png")
        return os.path.exists(path), "turnaround " + ("present" if os.path.exists(path) else "MISSING")
    if n == 23:
        mt = L.read_mtf(unit)
        crits = mt["crits"]
        fixed = ("Shoulder", "Upper Arm Actuator", "Lower Arm Actuator", "Hand Actuator", "Hip", "Upper Leg Actuator", "Lower Leg Actuator",
                 "Foot Actuator", "Fusion Engine", "Gyro", "Life Support", "Sensors", "Cockpit")
        planned = {mt_.get("location") for mt_ in model.get("mounts", [])} | {re.sub(r"\.\w+$", "", mt_.get("id", ""))[:2]
                                                                              for mt_ in model.get("mounts", [])}
        # SPARE weapon slots (the location's slots, less the fixed equipment, less what its weapons take) need a planned mount;
        # the head and legs are left for later (the HD review, F2)
        wslots = {}
        for loc, c in crits.items():
            for x in c:
                if x and x not in fixed and x != "-Empty-" and not any(k in x.lower() for k in ("heat sink", "ammo", "jump jet", "case")):
                    wslots[loc] = wslots.get(loc, 0) + 1
        missing = []
        for loc, c in crits.items():
            if loc in ("LL", "RL", "HD"):
                continue
            spare = 12 - sum(1 for x in c if x in fixed) - wslots.get(loc, 0)
            if spare > 0 and loc not in planned:
                missing.append("%s (%d spare)" % (loc, spare))
        return not missing, ("spare slots with no planned mount: " + ", ".join(missing)) if missing else "every arm and torso location's spare slots have a planned mount"
    if n == 30:
        head = [s_ for s_ in sol if s_["assembly"] == "head" and _name(s_["id"]) not in ("neck",)]
        torso = [s_ for s_ in sol if s_["assembly"] == "torso"]
        arrs = [(L._solid_arrays(a), _name(a["id"])) for a in head]
        tarr = [(L._solid_arrays(b), _name(b["id"])) for b in torso]
        touching = sorted({(x, y) for a, x in arrs for b, y in tarr if not L.separated(a, b, 0.03)})
        return not touching, "head touches the torso: " + ", ".join("%s x %s" % t for t in touching[:4]) if touching else "a gap all round"
    if n == 33:
        covers = [p for p in model["parts"] if _name(p["id"]).endswith("_cover")]
        return bool(covers), "%d joint cover(s)" % len(covers)
    if n == 34:
        # the EXPOSED area of each big flat face: points sampled over it, a hair off it along its outward normal, are tested against every
        # other solid; a face buried under other parts (the chest's top under the collar) is not a large flat space
        planes = []
        for s_ in sol:
            vs = np.array(s_["verts"])
            c = vs.mean(0)
            pl = []
            for f in s_["faces"]:
                nrm = np.cross(vs[f[1]] - vs[f[0]], vs[f[2]] - vs[f[0]])
                ln = np.linalg.norm(nrm)
                if ln < 1e-12:
                    continue
                nrm = nrm / ln
                if np.dot(nrm, vs[f[0]] - c) < 0:
                    nrm = -nrm
                pl.append((nrm, np.dot(nrm, vs[f[0]])))
            planes.append((np.array([q[0] for q in pl]), np.array([q[1] for q in pl]), vs.min(0), vs.max(0)))

        def covered(pt, own):
            for k, (N, D, lo, hi) in enumerate(planes):
                if k == own or np.any(pt < lo - 1e-6) or np.any(pt > hi + 1e-6):
                    continue
                if np.all(N @ pt <= D + 1e-6):
                    return True
            return False
        worst = []
        for si, s_ in enumerate(sol):
            vs = np.array(s_["verts"])
            c = vs.mean(0)
            for f in s_["faces"]:
                a = np.zeros(3)
                for k in range(1, len(f) - 1):
                    a += np.cross(vs[f[k]] - vs[f[0]], vs[f[k + 1]] - vs[f[0]])
                area = np.linalg.norm(a) / 2
                if area <= 1.6:
                    continue
                nrm = a / np.linalg.norm(a)
                if np.dot(nrm, vs[f[0]] - c) < 0:
                    nrm = -nrm
                fc = vs[list(f)].mean(0)
                if nrm[1] < -0.9 and fc[1] < 0.05:         # a sole on the ground is not a flat space anyone sees
                    continue
                samples = [fc] + [fc + (vs[v] - fc) * t for v in f for t in (0.4, 0.8)]
                # open to view only if nothing stands within 0.4 above it (the head 0.12 over the chest's top hides it)
                free = [p_ for p_ in samples if not any(covered(p_ + nrm * t, si) for t in (0.04, 0.15, 0.4))]
                exposed = area * len(free) / len(samples)
                if exposed > 1.6:
                    facing = "front" if nrm[2] > 0.7 else "back" if nrm[2] < -0.7 else "top" if nrm[1] > 0.7 else "underside" if nrm[1] < -0.7 \
                        else "side"
                    worst.append((round(exposed, 2), "%s (%s)" % (_name(s_["id"]), facing)))
        worst.sort(reverse=True)
        return not worst, ("exposed flat faces over 1.6 (the model is 10 tall): " + ", ".join("%s %.2f" % (n_, a) for a, n_ in worst[:5])) \
            if worst else "no exposed flat face over 1.6"
    if n in (36, 44):
        poses = model.get("poses", {})
        if n == 36:
            return bool(poses.get("dynamic")), "dynamic pose " + ("present" if poses.get("dynamic") else "MISSING")
        cam = poses.get("dynamic_camera", [-30, 14])
        return cam[1] >= 0, "pose camera pitch %.0f" % cam[1]
    if n in (37, 42):
        ws = [(s_["role"].split(":")[1], s_["role"].split(":")[2], s_["centroid"]) for s_ in sol if s_.get("role", "").startswith("weapon:")]
        pairs, bad = 0, []
        for loc, name, c in ws:
            twin = {"LA": "RA", "RA": "LA", "LT": "RT", "RT": "LT"}.get(loc)
            mates = [c2 for l2, n2, c2 in ws if l2 == twin and n2 == name]
            if mates:
                pairs += 1
                if not any(max(abs(c[0] + c2[0]), abs(c[1] - c2[1]), abs(c[2] - c2[2])) < 0.05 for c2 in mates):
                    bad.append("%s %s" % (loc, name))
        if n == 42:
            slots = [mt_ for mt_ in model.get("mounts", []) if mt_.get("kind") == "arm_face"]
            return bool(slots) and not bad, "%d forearm mount slot(s); arm weapons %s" % (len(slots), "mirror" if not bad else "NOT mirrored: " + ", ".join(bad))
        return not bad, ("%d paired weapon(s) mirror each other" % pairs) if not bad else "NOT mirrored: " + ", ".join(bad)
    if n == 51:
        if quick:
            return None, "skipped (--quick)"
        import lowpoly_articulate as A
        out = []
        for j, a0, a1, st in A.SWEEPS:
            pv = HD._pivot(model, j)
            if not pv:
                continue
            r = pv.get("range") or [a0, a1]
            rep = A.sweep(model, j, r[0], r[1], st)
            if rep:
                out.append("%s clips at %s" % (j, ", ".join("%+.0f" % a for a in sorted(rep))))
        return not out, "; ".join(out) or "every joint clear through its range (legs not swept)"
    if n == 52:
        lines = []
        for s_ in sol:
            if (s_.get("tone") or 1) > 0.3 or any(w in _name(s_["id"]) for w in VENT_WORDS):
                continue
            ext = np.ptp(np.array(s_["verts"]), axis=0)
            if ext.min() < 0.07 and ext.max() > 0.6:
                lines.append(_name(s_["id"]))
        lines = sorted(set(lines))
        return not lines, ("thin dark parts that may be painted lines: " + ", ".join(lines)) if lines else "none"
    if n == 53:
        pv = HD._pivot(model, "neck")
        core = [s_ for s_ in sol if s_["assembly"] == "torso" and _name(s_["id"]) in ("chest", "body")]   # the torso's own body, no guns
        torso = np.array([v for s_ in (core or [s_ for s_ in sol if s_["assembly"] == "torso"]) for v in s_["verts"]])
        zc = (torso[:, 2].min() + torso[:, 2].max()) / 2
        head = np.array([v for s_ in sol if s_["assembly"] == "head" for v in s_["verts"]])
        hz = (head[:, 2].min() + head[:, 2].max()) / 2
        ok = abs(pv["centre"][2] - zc) < 0.3 and abs(hz - pv["centre"][2]) < 0.3
        return ok, "neck z %.2f, the torso's middle %.2f, the head's middle %.2f" % (pv["centre"][2], zc, hz)
    return None, "no automatic test"


def run(unit, quick=False):
    model = json.load(open(os.path.join(HD.HD_DIR, unit + ".json")))
    sol = L.expand_parts(model)
    os.makedirs(CHECK_DIR, exist_ok=True)
    vpath = os.path.join(CHECK_DIR, unit + ".json")
    verdicts = json.load(open(vpath)) if os.path.exists(vpath) else {}
    rows = []
    for n, text, applies, kind in ITEMS:
        if not applies(model):
            rows.append((n, text, "n/a", "", kind))
            continue
        if kind == "auto":
            ok, detail = auto(n, unit, model, sol, quick)
            rows.append((n, text, "PASS" if ok else ("FAIL" if ok is False else "-"), detail, kind))
        else:
            v = verdicts.get(str(n), {})
            rows.append((n, text, v.get("verdict", "TO LOOK").upper(), v.get("note", ""), kind))
    out = ["# Checklist: %s (`python -I tools/lowpoly_checklist.py \"%s\"`)" % (unit, unit), "",
           "| # | Daniel's correction | check | result | detail |", "|---|---|---|---|---|"]
    for n, text, res, detail, kind in rows:
        out.append("| %d | %s | %s | %s | %s |" % (n, text, "auto" if kind == "auto" else "eye", res, detail.replace("|", "/")))
    with open(os.path.join(CHECK_DIR, unit + " report.md"), "w") as f:
        f.write("\n".join(out) + "\n")
    return rows


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    rows = run(argv[0], "--quick" in argv)
    for n, text, res, detail, kind in rows:
        print("%3d %-5s %-8s %-62s %s" % (n, "auto" if kind == "auto" else "eye", res, text[:62], detail[:150]))
    bad = [r for r in rows if r[2] in ("FAIL", "TO LOOK")]
    print("%d item(s) FAIL or still to look at" % len(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
