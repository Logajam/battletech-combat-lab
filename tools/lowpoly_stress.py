#!/usr/bin/env python3
"""WEAPON STRESS TEST for an HD model's mounts (Claude, 2026-11-18).

Daniel, 2026-11-18: "Lets do 3 more checks on the commando. Render 3 comandos. One with 28 Machine guns in the torso, one with 28
IS SRM-2s, and finally 14 Rocket Launcher 10s in the torso. Include 8 of each type of weapon on each arm too. Stacking weapon pods is
a legitimate strategy. This is a stress test for a light mech. Heavy and assaults might have to deal with 28 SRM-6's in the torso's
as a possibility."

A VISUAL test of the mount plan (principle 35: torso weapons flat on the torso's sections, grouped, sized to their mount; the arms'
pods on the forearm's flat face, principle 26, stacked): it does not ask whether the load is legal under the construction rules.

    python -I tools/lowpoly_stress.py            # the three Commando loads -> reference_art/sheets/Commando stress *.png + a report

The model's own weapons come off (the SRM 6, the SRM 4 pod, the laser); then every torso mount (the six hidden quads and the
upper-belly bay, which takes four here) is filled, and each forearm carries a STACK of pods. For each load the report gives: weapons
placed, floating parts, blocked lines of fire, triangles, and the smallest tube bore (how readable the weapons stay). PRIVATE.
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
    """cols, rows for n launchers in a w x h face: the most square cells."""
    best = None
    for cols in range(1, n + 1):
        rows = math.ceil(n / cols)
        cw, ch = w / cols, h / rows
        score = max(cw, ch) / min(cw, ch)
        if best is None or score < best[0]:
            best = (score, cols, rows)
    return best[1], best[2]


def cluster(m, asm, fr, w, h, depth, kind, n, role, stats):
    """A mount filled with n launchers of one kind: a housing (w x h face, `depth` deep along F, its face at w = 0) with each
    launcher in its own cell; machine guns as jacketed barrels standing out of the face, missile launchers as boxes with their tubes
    flush. The line of fire starts in front of whatever stands out furthest."""
    m.hull("stress_housing", asm, [fr.p(su * w / 2, sv * h / 2, sw) for su in (-1, 1) for sv in (-1, 1) for sw in (-depth, 0.0)],
           tone=HD.PLATE)
    cols, rows = grid(n, w, h)
    cw, ch = w / cols, h / rows
    lead = 0.0
    placed = 0
    for k in range(n):
        c, r_ = k % cols, k // cols
        u = -w / 2 + cw * (c + 0.5)
        v = h / 2 - ch * (r_ + 0.5)
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
    m.parts[-1 - 0] if False else None
    hp = next(p for p in reversed(m.parts) if p["id"].startswith("stress_housing"))
    hp["role"] = role
    hp["fire"] = {"from": list(fr.p(0, 0, lead + 0.03)), "dir": list(fr.F), "r": round(min(w, h) / 2 * 0.9, 3)}
    return placed


def forearm_face_frame(model, side, layer_h):
    """The frame of the forearm's upper OUTER face (as the SRM 4 pod, principle 26): origin on the face at the pod's middle."""
    s = 1 if side == "L" else -1
    el, wr = model["pivots"]["elbow_" + side]["centre"], model["pivots"]["wrist_" + side]["centre"]
    fu = [wr[i] - el[i] for i in range(3)]
    fl = math.sqrt(sum(c * c for c in fu))
    fu = [c / fl for c in fu]
    t_ = 0.62
    w_ = 1.25 + (1.15 - 1.25) * t_
    d_ = (1.2 + (1.08 - 1.2) * t_) * (1 - 0.08 * (2 * t_ - 1) ** 2)
    up_ = (0.0, fu[2], -fu[1])
    lat = (s, 0.0, 0.0)
    mid2 = (0.433 * w_ / 2, 0.75 * d_ / 2)
    nrm = (d_ / 4, 0.866 * w_ / 2)
    nl_ = math.hypot(*nrm)
    nrm = (nrm[0] / nl_, nrm[1] / nl_)
    N = tuple(lat[i] * nrm[0] + up_[i] * nrm[1] for i in range(3))
    S_ = tuple(lat[i] * nrm[1] - up_[i] * nrm[0] for i in range(3))
    base = [el[i] + fu[i] * fl * t_ + lat[i] * mid2[0] + up_[i] * mid2[1] for i in range(3)]
    return base, S_, N, tuple(fu)


def stress_model(model, load):
    name, kind, torso_n, arm_n, per_mount, per_layer = load
    out = dict(model, parts=[p for p in model["parts"] if not any(p["id"].startswith(k + "_") for k in OWN_WEAPON_PARTS)])
    m = HD.Model()
    m.parts = out["parts"]
    m.n = 100000
    stats = {"min_bore": 9.9, "torso": 0, "arm_L": 0, "arm_R": 0}
    # ---- the torso: the six hidden quads and the upper-belly bay
    mounts = [mt for mt in model["mounts"] if mt.get("kind") in ("weapon_quad", "weapon_bay")]
    left = torso_n
    for mt in mounts:
        if left <= 0:
            break
        n = min(per_mount, left)
        x, y, z = mt["pos"]
        w, h = mt["envelope"][0], mt["envelope"][1]
        fr = Frame((x, y, z + 0.15), (1, 0, 0), (0, 1, 0), (0, 0, 1))          # the face 0.15 proud of the torso, as bay_grid
        loc = mt.get("location", "CT")
        stats["torso"] += cluster(m, "torso", fr, w, h, 0.3, kind, n, "weapon:%s:%s" % (loc, name), stats)
        left -= n
    stats["torso_unplaced"] = left
    # ---- the arms: a STACK of pods on the forearm's upper outer face, each layer on the one below
    layers = math.ceil(arm_n / per_layer)
    pod_w, pod_len, layer_h = 0.82, 1.0, 0.42
    for side in ("L", "R"):
        base, S_, N, F = forearm_face_frame(model, side, layer_h)
        asm = "arm_" + side
        placed = 0
        for k in range(layers):
            lift = -0.08 + layer_h * (k + 0.5) - 0.02 * k                 # the first sunk into the forearm, each on the last
            mid = [base[i] + N[i] * lift for i in range(3)]
            front = [mid[i] + F[i] * pod_len / 2 for i in range(3)]
            fr = Frame(front, S_, N, F)
            n = min(per_layer, arm_n - placed)
            placed += cluster(m, asm, fr, pod_w, layer_h, pod_len, kind, n, "weapon:%sA:%s" % (side, name), stats)
        stats[asm] = placed
    out["parts"] = m.parts
    return out, stats


def render(model, load, stats, path):
    import lowpoly_blocks as B
    from PIL import Image, ImageDraw
    sol = L.expand_parts(model)
    loose = L.floating_parts(sol)
    corr = [c for p in model["parts"] for c in L.part_corridors(p)]
    blocked = L.blocked_lines_of_fire(sol, corr)
    tris = sum(s_["tris"] for s_ in sol)
    stats.update({"floating": loose, "blocked": len(blocked), "blockers": sorted({b for _, b in blocked})[:8], "triangles": tris})
    H = 560
    cube = HD._box_solid(sol)
    views = [("FRONT", lambda q: q, cube), ("LEFT SIDE", lambda q: (-q[2], q[1], q[0]), cube), ("3/4 FRONT", B.camera(-35, 12), None),
             ("CLOSE: CHEST AND RIGHT ARM", B.camera(-25, 18), [{"verts": [(x, y, z) for x in (-3.0, 1.4) for y in (5.4, 9.6)
                                                                           for z in (-0.5, 2.6)], "faces": []}])]
    out = Image.new("RGB", (H * len(views), H + 70), "white")
    d = ImageDraw.Draw(out)
    d.text((10, 8), "COMMANDO COM-2D STRESS TEST: %s in the torso + %d per arm (stacked pods)" % (load[0], load[3]), fill="black")
    d.text((10, 26), "placed: torso %d, left arm %d, right arm %d | %d triangles | smallest bore %.3f (the model is 10 tall) | %s | %s" % (
        stats["torso"], stats["arm_L"], stats["arm_R"], tris, stats["min_bore"],
        "no floating parts" if not loose else "FLOATING: %d" % len(loose),
        "every line of fire clear" if not blocked else "LINES OF FIRE BLOCKED: %d" % len(blocked)),
        fill="black" if not (loose or blocked) else "red")
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
