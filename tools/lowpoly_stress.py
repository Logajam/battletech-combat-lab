#!/usr/bin/env python3
"""WEAPON STRESS TEST for an HD model's mounts (Claude, 2026-11-18).

Daniel, 2026-11-18: "Lets do 3 more checks on the commando. Render 3 comandos. One with 28 Machine guns in the torso, one with 28
IS SRM-2s, and finally 14 Rocket Launcher 10s in the torso. Include 8 of each type of weapon on each arm too. Stacking weapon pods is
a legitimate strategy. This is a stress test for a light mech. Heavy and assaults might have to deal with 28 SRM-6's in the torso's
as a possibility."

A VISUAL test of the mount plan (principle 35: torso weapons flat on the torso's sections, grouped, sized to their mount; the arms'
pods on the forearm's flat face, principle 26, stacked): it does not ask whether the load is legal under the construction rules.

    python -I tools/lowpoly_stress.py            # the three Commando loads -> reference_art/sheets/Commando stress *.png + a report

The model's own weapons come off (the SRM 6, the SRM 4 pod, the laser); then every torso mount is filled (the six hidden quads in
PAIRS, left and right alike, and the round belly, the centre torso's mount, takes the rest), and each forearm carries pods on its
SIX FLAT FACES (Daniel, 2026-11-18: "for the commando there are 6 potential flat surfaces around the hand that could be used as
mounting spots"), placed by a search that keeps them off the fist and the fist out of their fire, stacked when a face cannot be
used. Layouts are SYMMETRIC (Daniel: "the symmetry breaks down in some of those examples": four weapons had been laid three over
one). For each load the report gives: weapons placed, floating parts, blocked lines of fire, triangles, the smallest tube bore (how
readable the weapons stay), the use of each forearm face, and a mirror check. PRIVATE.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lowpoly_ref as L  # noqa: E402
import lowpoly_hd as HD  # noqa: E402

UNIT = "Commando COM-2D"
LOADS = [  # (name, weapon kind, torso count, per-arm count, launchers per torso mount, launchers per arm layer)
    ("28 Machine Guns", "mg", 28, 8, 4, 4),
    ("28 SRM 2s", "srm2", 28, 8, 4, 4),
    ("14 Rocket Launcher 10s", "rl10", 14, 8, 2, 2),
]
OWN_WEAPON_PARTS = ("srm6_bay", "srm4_pod", "srm4_tube", "srm4_bore", "pod_strap", "laser_housing", "laser_barrel", "laser_bore")
TUBES = {"mg": (1, 1), "srm2": (1, 2), "rl10": (2, 5)}       # (rows, cols) of tube mouths in ONE launcher


class Frame:
    """A mount's frame: origin on the mounting face, R across, U up, F forward (the line of fire)."""
    def __init__(self, o, R, U, F):
        self.o, self.R, self.U, self.F = o, R, U, F

    def p(self, u, v, w):
        return tuple(self.o[i] + u * self.R[i] + v * self.U[i] + w * self.F[i] for i in range(3))


def grid(n, w, h):
    """cols, rows for n launchers in a w x h face: the most square cells, a FULL grid preferred (an incomplete last row is centred
    by `cells`, but a full one is never lopsided)."""
    best = None
    for cols in range(1, n + 1):
        rows = math.ceil(n / cols)
        cw, ch = w / cols, h / rows
        score = max(cw, ch) / min(cw, ch) + (0.0 if rows * cols == n else 1.5)
        if best is None or score < best[0]:
            best = (score, cols, rows)
    return best[1], best[2]


def cells(n, w, h):
    """The (u, v, cell w, cell h) of n launchers in a w x h face, every row centred (SYMMETRY, Daniel 2026-11-18)."""
    cols, rows = grid(n, w, h)
    cw, ch = w / cols, h / rows
    out = []
    for r_ in range(rows):
        k = min(cols, n - r_ * cols)
        for c in range(k):
            out.append((-(k - 1) * cw / 2 + c * cw, h / 2 - ch * (r_ + 0.5), cw, ch))
    return out


def cluster(m, asm, fr, w, h, depth, kind, n, role, stats):
    """A mount filled with n launchers of one kind: a housing (w x h face, `depth` deep along F, its face at w = 0) with each
    launcher in its own cell; machine guns as jacketed barrels standing out of the face, missile launchers as boxes with their tubes
    flush. The line of fire starts in front of whatever stands out furthest."""
    m.hull("stress_housing", asm, [fr.p(su * w / 2, sv * h / 2, sw) for su in (-1, 1) for sv in (-1, 1) for sw in (-depth, 0.0)],
           tone=HD.PLATE)
    lead = 0.0
    placed = 0
    for u, v, cw, ch in cells(n, w, h):
        small = min(cw, ch)
        if kind == "mg":
            jd, bd = small * 0.62, small * 0.32
            ln = max(0.12, small * 0.9)
            m.tube("mg_jacket", asm, fr.p(u, v, -0.02), fr.p(u, v, ln * 0.45), jd, n=10, tone=0.5)
            m.tube("mg_barrel", asm, fr.p(u, v, ln * 0.45 - 0.01), fr.p(u, v, ln), bd, n=10, tone=HD.METAL)
            m.tube("mg_bore", asm, fr.p(u, v, ln), fr.p(u, v, ln + 0.01), bd * 0.5, n=10, tone=HD.DARK)
            lead = max(lead, ln + 0.01)
            stats["min_bore"] = min(stats["min_bore"], bd * 0.5)
        else:
            tr, tc = TUBES[kind]
            if ch > cw and tc > tr:                      # turn the tube grid to the cell
                tr, tc = tc, tr
            bw, bh = cw * 0.92, ch * 0.92
            m.hull("launcher_box", asm, [fr.p(u + su * bw / 2, v + sv * bh / 2, sw) for su in (-1, 1) for sv in (-1, 1)
                                         for sw in (-0.04, 0.05)], tone=0.66)
            td = min(bw / tc, bh / tr) * 0.78
            for a in range(tc):
                for b in range(tr):
                    x = u + (a - (tc - 1) / 2) * (bw * 0.9 / tc)
                    y = v + ((tr - 1) / 2 - b) * (bh * 0.9 / tr)
                    m.tube("tube", asm, fr.p(x, y, 0.0), fr.p(x, y, 0.06), td, n=10, tone=0.72)
                    m.tube("bore", asm, fr.p(x, y, 0.06), fr.p(x, y, 0.07), td * 0.63, n=10, tone=0.1)
            lead = max(lead, 0.07)
            stats["min_bore"] = min(stats["min_bore"], td * 0.63)
        placed += 1
    # the housing carries the role and the line of fire for the whole cluster
    hp = next(p for p in reversed(m.parts) if p["id"].startswith("stress_housing"))
    hp["role"] = role
    hp["fire"] = {"from": list(fr.p(0, 0, lead + 0.03)), "dir": list(fr.F), "r": round(min(w, h) / 2 * 0.9, 3)}
    return placed


FACES = ("upper_outer", "outer", "lower_outer", "lower_inner", "inner", "upper_inner")
FACE_PLAN = {"upper_outer": 2, "upper_inner": 2, "outer": 1, "inner": 1, "lower_outer": 1, "lower_inner": 1}    # 8 a forearm
FIST = ("fist", "knuckles", "thumb", "finger_gap", "wrist")
POD_W, POD_H = 0.5, 0.36


def forearm_faces(model, side, t_=0.62):
    """The six flat faces of the hexagonal forearm (lowpoly_hd.commando: limb sections with 6 sides) at t along it: name ->
    (middle point, along-face direction, outward normal, forward). The corners in (outward, up): top (0, d/2), upper outer
    (0.866 w/2, d/4), lower outer (0.866 w/2, -d/4), bottom (0, -d/2), and the inner two mirrored."""
    s = 1 if side == "L" else -1
    el, wr = model["pivots"]["elbow_" + side]["centre"], model["pivots"]["wrist_" + side]["centre"]
    fu = [wr[i] - el[i] for i in range(3)]
    fl = math.sqrt(sum(c * c for c in fu))
    fu = [c / fl for c in fu]
    w_ = 1.25 + (1.15 - 1.25) * t_
    d_ = (1.2 + (1.08 - 1.2) * t_) * (1 - 0.08 * (2 * t_ - 1) ** 2)
    up_ = (0.0, fu[2], -fu[1])
    lat = (s, 0.0, 0.0)
    axis = [el[i] + fu[i] * fl * t_ for i in range(3)]
    a, b = 0.866 * w_ / 2, d_ / 4
    corners = [(0, d_ / 2), (a, b), (a, -b), (0, -d_ / 2), (-a, -b), (-a, b)]
    to3 = lambda o, u: tuple(lat[i] * o + up_[i] * u for i in range(3))
    out = {}
    for k, nm in enumerate(FACES):
        P, Q = corners[k], corners[(k + 1) % 6]
        mid = ((P[0] + Q[0]) / 2, (P[1] + Q[1]) / 2)
        e = (Q[0] - P[0], Q[1] - P[1])
        el_ = math.hypot(*e)
        e = (e[0] / el_, e[1] / el_)
        n = (e[1], -e[0])
        if n[0] * mid[0] + n[1] * mid[1] < 0:
            n = (-n[0], -n[1])
        out[nm] = (tuple(axis[i] + to3(*mid)[i] for i in range(3)), to3(*e), to3(*n), tuple(fu), fl, wr, el_)
    return out


def _solid(pts):
    import lowpoly_ref as L_
    v, f = L_.build_part({"kind": "hull", "pts": [list(p) for p in pts], "id": "probe"})
    return L_._solid_arrays({"verts": v, "faces": f})


def place_arm(m, model, side, kind, name, per_face, stats, fist_solids, limb_solids=()):
    """Pods on the forearm's faces: for each face, a search over where along the face it sits and how long it is (short, ending
    before the wrist; or a GAUNTLET running past the knuckles) for a pod that touches neither the fist nor another pod and whose
    fire clears the fist. A face with no such place is reported, and its weapons go on a second layer on the upper faces."""
    faces = forearm_faces(model, side)
    asm = "arm_" + side
    placed, taken, report, spill, used = 0, [], {}, 0, []
    order = list(FACES)
    for nm in order:
        n = per_face.get(nm, 0)
        if not n:
            continue
        mid, E, N, F, fl, wr, face_w = faces[nm]
        ok = None
        lead = 0.3 if kind == "mg" else 0.1                       # how far the muzzles stand out (the fire starts beyond them)
        r_fire = min(POD_W, POD_H) / 2 * 0.9                      # as `cluster` gives the pod's line of fire
        # short (ending at the wrist), or a gauntlet (further back AND past the knuckles); flat on the face, or on a RISER (a
        # pedestal under the pod) high enough for its fire to pass over the fist
        for length, back, lift in ((1.0, 0.07, 0.0), (1.0, 0.07, 0.12), (1.0, 0.07, 0.24), (1.9, -0.48, 0.0)):
            for off in (0.0, 0.06, -0.06, 0.12, -0.12):
                c0 = [mid[i] + E[i] * off + N[i] * (POD_H / 2 - 0.06 + lift) + F[i] * back for i in range(3)]
                front = [c0[i] + F[i] * length / 2 for i in range(3)]
                fr = Frame(front, E, N, F)
                box = [fr.p(su * POD_W / 2, sv * POD_H / 2, sw) for su in (-1, 1) for sv in (-1, 1) for sw in (-length, 0.0)]
                bs = _solid(box)
                cor = L.corridor_solid(dict(L.corridor(fr.p(0, 0, 0.04), F, r_fire), r=r_fire + 0.02))      # the full corridor and a margin
                ls = L._solid_arrays(cor)
                clash = any(not L.separated(bs, f_, -0.002) for f_ in fist_solids) or any(not L.separated(bs, t_, -0.002) for t_ in taken)
                blocked = any(not L.separated(ls, f_, -0.002) for f_ in fist_solids + limb_solids + taken)
                if not clash and not blocked:
                    ok = (fr, length, bs, off, back, lift)
                    break
            if ok:
                break
        if not ok:
            report[nm] = "unusable (the fist)"
            spill += n
            continue
        fr, length, bs, off, back, lift = ok
        report[nm] = "%d, %s" % (n, "gauntlet past the fist" if length > 1.5 else "short") + (", on a %.2f riser" % lift if lift else "") + \
            (", moved %.2f along the face" % off if off else "")
        if lift:                                                  # the riser: from the face up to the pod's underside
            m.hull("pod_riser", asm, [fr.p(su * POD_W / 2 * 0.8, sv, sw) for su in (-1, 1) for sv in (-POD_H / 2 + 0.01, -POD_H / 2 - lift - 0.06)
                                      for sw in (-length * 0.85, -length * 0.15)], tone=HD.JOINT)
        placed += cluster(m, asm, fr, POD_W, POD_H, length, kind, n, "weapon:%sA:%s" % (side, name), stats)
        taken.append(bs)
        used.append((nm, fr, length))
    # what found no face is STACKED on the pods that did, a layer at a time, the upper faces first (each layer on the one below)
    used.sort(key=lambda u: FACES.index(u[0]) if u[0].startswith("upper") else 10 + FACES.index(u[0]))
    layer = 1
    while spill > 0 and used:
        for nm, fr0, length in used:
            if spill <= 0:
                break
            n = min(2, spill)
            lift = (POD_H - 0.02) * layer
            fr = Frame(tuple(fr0.o[i] + fr0.U[i] * lift for i in range(3)), fr0.R, fr0.U, fr0.F)
            placed += cluster(m, asm, fr, POD_W, POD_H, length, kind, n, "weapon:%sA:%s" % (side, name), stats)
            report[nm] = report.get(nm, "") + " + %d stacked" % n
            spill -= n
        layer += 1
    stats[asm] = placed
    stats["faces_" + side] = report


def stress_model(model, load):
    name, kind, torso_n, arm_n, per_mount, per_layer = load
    out = dict(model, parts=[p for p in model["parts"] if not any(p["id"].startswith(k + "_") for k in OWN_WEAPON_PARTS)])
    m = HD.Model()
    m.parts = out["parts"]
    m.n = 100000
    stats = {"min_bore": 9.9, "torso": 0, "arm_L": 0, "arm_R": 0}
    # ---- the torso: the side quads in mirrored PAIRS, the round belly (the centre torso's mount) takes the rest
    mounts = {mt["id"]: mt for mt in model["mounts"] if mt.get("kind") in ("weapon_quad", "weapon_bay")}
    pairs = [("LT.quad_" + lv, "RT.quad_" + lv) for lv in ("upper_chest", "middle_chest", "lower_belly")]
    fill = {}
    left = torso_n
    for a, b in pairs:
        if left >= 2 * per_mount:
            fill[a] = fill[b] = per_mount
            left -= 2 * per_mount
    fill["CT.belly"] = left
    for mid, n in fill.items():
        if not n:
            continue
        mt = mounts[mid]
        x, y, z = mt["pos"]
        w, h = mt["envelope"][0], mt["envelope"][1]
        fr = Frame((x, y, z + 0.15), (1, 0, 0), (0, 1, 0), (0, 0, 1))          # the face 0.15 proud of the torso, as bay_grid
        stats["torso"] += cluster(m, "torso", fr, w, h, 0.3, kind, n, "weapon:%s:%s" % (mt["location"], name), stats)
    stats["torso_unplaced"] = 0
    stats["torso_fill"] = fill
    # ---- the arms: the six faces of each forearm
    # the fist as it stands WITHOUT the model's own weapons (the original right fist carries a channel cut by the SRM 4's line of
    # fire: read from the original, the two arms came out different)
    base = L.expand_parts(dict(model, parts=[p for p in model["parts"] if not any(p["id"].startswith(k + "_") for k in OWN_WEAPON_PARTS)]))
    import re
    for side in ("L", "R"):
        fist = [L._solid_arrays(s_) for s_ in base if s_["assembly"] == "arm_" + side and re.sub(r"_\d+.*$", "", s_["id"]) in FIST]
        limb = [L._solid_arrays(s_) for s_ in base if s_["assembly"] == "arm_" + side and re.sub(r"_\d+.*$", "", s_["id"]) in
                ("forearm", "forearm_band", "elbow")]
        plan = dict(FACE_PLAN) if arm_n == 8 else {"upper_outer": arm_n}
        place_arm(m, model, side, kind, name, plan, stats, fist, limb)
    out["parts"] = m.parts
    return out, stats


def mirror_check(model):
    """Weapons with no mirror image across the centre line (the 'Mech's own asymmetric parts aside)."""
    import re
    sol = [s_ for s_ in L.expand_parts(model) if re.match(r"(mg_|tube_|bore_|launcher_box|stress_housing)", s_["id"])
           and int(re.search(r"_(\d+)", s_["id"]).group(1)) >= 100000]
    cs = [(s_["id"].split("_")[0], s_["centroid"]) for s_ in sol]
    return sum(1 for k, c in cs if not any(k2 == k and max(abs(a - b) for a, b in zip(c2, (-c[0], c[1], c[2]))) < 0.02 for k2, c2 in cs))


def render(model, load, stats, path):
    import lowpoly_blocks as B
    from PIL import Image, ImageDraw
    sol = L.expand_parts(model)
    loose = L.floating_parts(sol)
    corr = [c for p in model["parts"] for c in L.part_corridors(p)]
    blocked = L.blocked_lines_of_fire(sol, corr)
    tris = sum(s_["tris"] for s_ in sol)
    stats.update({"floating": loose, "blocked": len(blocked), "blockers": sorted({b for _, b in blocked})[:8], "triangles": tris,
                  "unmirrored": mirror_check(model),
                  "cut_by_fire": sorted({s_["id"].split("~")[0] for s_ in sol if "~cut" in s_["id"]})})
    H = 560
    cube = HD._box_solid(sol)
    views = [("FRONT", lambda q: q, cube), ("LEFT SIDE", lambda q: (-q[2], q[1], q[0]), cube), ("3/4 FRONT", B.camera(-35, 12), None),
             ("CLOSE: RIGHT FOREARM FROM AHEAD AND BELOW", B.camera(-28, -12), [{"verts": [(x, y, z) for x in (-3.3, -0.9)
                                                                                        for y in (5.6, 8.4) for z in (0.0, 3.2)], "faces": []}])]
    out = Image.new("RGB", (H * len(views), H + 70), "white")
    d = ImageDraw.Draw(out)
    d.text((10, 8), "COMMANDO COM-2D STRESS TEST: %s in the torso + %d per arm (stacked pods)" % (load[0], load[3]), fill="black")
    d.text((10, 26), "placed: torso %d, left arm %d, right arm %d | %s | %d triangles | smallest bore %.3f (the model is 10 tall) | %s | %s" % (
        stats["torso"], stats["arm_L"], stats["arm_R"], "mirror-symmetric" if not stats["unmirrored"] else "%d NOT MIRRORED" % stats["unmirrored"],
        tris, stats["min_bore"],
        "no floating parts" if not loose else "FLOATING: %d" % len(loose),
        ("every line of fire clear" if not blocked else "LINES OF FIRE BLOCKED: %d" % len(blocked)) +
        (" | nothing cut by fire" if not stats["cut_by_fire"] else " | CUT BY FIRE: %s" % ", ".join(stats["cut_by_fire"][:4]))),
        fill="black" if not (loose or blocked or stats["cut_by_fire"]) else "red")
    for i, (n, f, fit) in enumerate(views):
        out.paste(B.render(sol, f, (H, H), fit_solids=fit) if fit else B.render(sol, f, (H, H)), (i * H, 60))
        d.text((i * H + 8, 46), n, fill="black")
    out.save(path)


def main():
    base = json.load(open(os.path.join(HD.HD_DIR, UNIT + ".json")))
    report = {}
    for load in LOADS:
        model, stats = stress_model(base, load)
        path = os.path.join(L.SHEETS, "%s stress %s.png" % (UNIT, load[0]))
        render(model, load, stats, path)
        report[load[0]] = {k: v for k, v in stats.items()}
        print(load[0], json.dumps(report[load[0]]))
    with open(os.path.join(L.REF, "measure", UNIT + " stress.json"), "w") as f:
        json.dump(report, f, indent=1)


if __name__ == "__main__":
    main()
