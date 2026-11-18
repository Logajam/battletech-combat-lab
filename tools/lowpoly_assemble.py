#!/usr/bin/env python3
"""Whole 'Mechs from the block library, on a skeleton with sockets (Claude, 2026-11-17, session 28).

Daniel, 2026-11-17, after the connected groups: "the Catapult render you showed has disconnected pieces. Any final render must
have a socket system so that every block connects to the correct 'Bone'. Also blocks must sit flush to the surface they're on.
For example the Catapult's cockpit needs to be tangent to the surface it sits on." Then: "steal the unit viewer from the original
art project and render the mechs from this pass, plus their hashed appearance."

THE SKELETON. Bones between joints: hip -> knee -> ankle (each leg), shoulder socket -> elbow -> wrist (each arm), waist -> neck.
The joints come from the blocks' own sockets (anchors) where a block owns them (the pelvis's hip_L / hip_R, the chest's waist /
neck / shoulder_L / shoulder_R, the shoulder block's arm, the foot's ankle) and from bone lengths where nothing owns them (knee,
elbow, wrist). Two poses: STRAIGHT legs, and BIRD legs (the knee forward, the shin leaning back) when the shin is a bird shin.

THREE WAYS A BLOCK IS PLACED, all by sockets, never by hand-set coordinates:
  fit    a LIMB block (two anchors: thigh hip -> knee, shin knee -> ankle, upper arm shoulder -> elbow, forearm elbow -> wrist)
         is turned so its anchor-to-anchor line lies on the bone and scaled uniformly so its second anchor lands on the next
         joint: limbs always meet at their joints.
  plug   a block with one socket (a foot on the ankle, a hand on the wrist, the pelvis on the hips, the chest on the waist, a
         forward-pointing gun arm on the elbow) puts that anchor on the joint.
  seat   a block that sits ON a surface (a canopy, a head, a shoulder block, a knee disc, a launcher bay, a jump-jet pack, a
         rack, an antenna, a fin, the belly plate, an arm gun) is placed by casting a ray at the host block: its anchor goes on
         the hit point and, where it should, its mounting face is turned to the surface's normal, so it sits FLUSH and TANGENT
         (Daniel's canopy example). A ray that misses is an error, never a floating part.
THE CHECK (`check`): every 'Mech is ONE connected piece (every solid touches another, all joined), stands on y = 0, and every
seat found its surface. tests/test_lowpoly_ref.py runs it.

TWO BUILDS PER UNIT, both from the same blocks and the same rules:
  drawings   each slot's block is the taxonomy type whose `seen_on` lists the unit (reference_art/block_taxonomy.json, read off
             the TRO drawings); a slot the drawings do not settle falls back to the name hash.
  name hash  every slot (and the leg pose, through the shin) picked by a byte of sha256(chassis model | slot), as the earlier
             art project picked its blocks (INTEGRATION__shell_facet.pick): what an untagged unit would get.
The unit file adds what it fixes: a jump-jet pack when the unit can jump.

    python -I tools/lowpoly_assemble.py check
    python -I tools/lowpoly_assemble.py viewer OUT.html     # the old art project's 3D viewer (tools/lowpoly_viewer_template.html)
PRIVATE (reference_art/ is), like the blocks.
"""
import hashlib
import re
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lowpoly_blocks as B  # noqa: E402
import lowpoly_ref as L  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- the skeleton's bone lengths (models' units, a 'Mech about 10 tall)
# ITERATION 1 (2026-11-18, the model-v-drawing comparison, reference_art/blocks/comparison_pass1.md): the legs were too long and
# the bodies too small on every unit (legs about 2.1 x the chest's height; the drawings show 1.3 - 1.8, heavier = stockier).
# The legs now follow the chest: hip height = LEG_RATIO(tons) x chest height, the thigh THIGH_SHARE of the leg above the foot.
def leg_ratio(mass):
    return 1.8 - 0.45 * (min(100, max(20, mass)) - 20) / 80.0


THIGH_SHARE = 0.47
BIRD_SHIN_SHARE = 0.58                  # a bird leg's shin is the longer part
BIRD_KNEE_FWD, BIRD_SHIN_BACK = 35.0, 22.0   # degrees from vertical: the thigh forward to the knee, the shin back to the ankle
UPPER_ARM, FOREARM = 1.5, 1.7         # fractions of nothing: scaled by the chest height below (ARM_PER_CHEST)
ARM_PER_CHEST = 0.62                  # upper arm = this x chest height; forearm a little longer (ITERATION 1)
FORWARD_ARM_PITCH = 20.0              # a forward gun or pod arm points this far below horizontal (ITERATION 1: drawings hold them low)
HEAD_PER_CHEST = 0.34                 # ITERATION 2: a head (not a canopy) is at most this x the chest's height (the Victor's dome was huge)
GUN_ARM_PER_FOREARM = 1.35            # ITERATION 2: a forward gun / pod arm is at most this x the forearm's length (JagerMech, Dragon)
SHOULDER_PER_CHEST = 0.45             # a shoulder block is at most this x the chest's height (ITERATION 1: discs were bigger than heads)
ARM_SPLAY = 0.18                        # the A-stance: the elbow this far out from the shoulder socket
# uniform scale of each block's default size, by part (a first calibration by eye, as the groups' SCALE: blocks are measured on
# different units); limbs are scaled by their fit instead
PART_SCALE = {"foot": 1.15, "hand": 1.35, "lower_arm": 1.25, "shoulder": 1.05, "pelvis": 1.1, "head": 1.0, "knee": 0.8,
              "hip": 0.75, "ankle": 0.8, "side_torso": 0.9, "back_deck": 0.9, "weapon_mount": 0.9, "antenna": 1.0,
              "fins_spars_wings": 0.9, "neck_collar": 0.75, "waist": 1.0, "lower_torso": 0.8, "upper_torso": 1.0}
CONTACT_EPS = 0.04                      # two solids touch when their boxes overlap within this
JOINT_OVERLAP = 0.08                    # a limb reaches this far past each joint into its neighbour
MAX_LIMB_THICKEN = 1.25                 # a limb's thickness follows its length stretch up to this


# ---------------------------------------------------------------- small vector and rotation helpers
def add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def mul(a, k): return (a[0] * k, a[1] * k, a[2] * k)
def dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def norm(a): return math.sqrt(dot(a, a))
def unit(a):
    n = norm(a)
    return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-12 else (0.0, 0.0, 0.0)


IDENTITY = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def rot_apply(R, p):
    return (dot(R[0], p), dot(R[1], p), dot(R[2], p))


def rot_align(a, b):
    """The smallest rotation taking direction a onto direction b (Rodrigues)."""
    a, b = unit(a), unit(b)
    v, c = cross(a, b), dot(a, b)
    if c > 1 - 1e-9:
        return IDENTITY
    if c < -1 + 1e-9:                                   # opposite: half a turn about any axis square to a
        ax = unit(cross(a, (1.0, 0.0, 0.0) if abs(a[0]) < 0.9 else (0.0, 1.0, 0.0)))
        x, y, z = ax
        return ((2 * x * x - 1, 2 * x * y, 2 * x * z), (2 * x * y, 2 * y * y - 1, 2 * y * z), (2 * x * z, 2 * y * z, 2 * z * z - 1))
    k = 1.0 / (1.0 + c)
    x, y, z = v
    return ((1 - k * (y * y + z * z), k * x * y - z, k * x * z + y),
            (k * x * y + z, 1 - k * (x * x + z * z), k * y * z - x),
            (k * x * z - y, k * y * z + x, 1 - k * (x * x + y * y)))


# ---------------------------------------------------------------- one placed block
_CACHE = {}


def generated(block_id, lod, params, lib):
    """B.generate, remembered (a 'Mech asks for the same block many times; building is the slow part)."""
    key = (block_id, lod, json.dumps(params, sort_keys=True))
    if key not in _CACHE:
        _CACHE[key] = B.generate(block_id, lod, params, lib=lib)
    return _CACHE[key]


class Piece:
    """A generated block (its solids and anchors, in its own frame, scaled and maybe mirrored), then moved by `place`."""

    def __init__(self, block_id, lod, lib, scale=1.0, mirror=False, params=None, slot=""):
        g = generated(block_id, lod, params, lib)
        sx = -1.0 if mirror else 1.0
        f = lambda p: (sx * p[0] * scale, p[1] * scale, p[2] * scale)
        self.block, self.slot, self.mirror = block_id, slot, mirror
        self.solids = [dict(s, verts=[f(v) for v in s["verts"]], centroid=f(s["centroid"])) for s in g["solids"]]
        self.anchors = {k: f(v) for k, v in g["anchors"].items()}
        self.tris = g["tris"]

    def place(self, anchor, at, R=IDENTITY, about=None):
        """Turn by R about `anchor` (or the point `about`), then move `anchor` onto the world point `at`."""
        a = self.anchors[anchor] if about is None else about
        a0 = self.anchors[anchor]
        move = lambda p: add(at, rot_apply(R, sub(p, a0)))
        for s in self.solids:
            s["verts"] = [move(v) for v in s["verts"]]
            s["centroid"] = move(s["centroid"])
        self.anchors = {k: move(v) for k, v in self.anchors.items()}
        return self


# ---------------------------------------------------------------- ray casting onto host blocks (for seating)
def _ray_box(o, d, vs):
    t0, t1 = -1e18, 1e18
    for i in range(3):
        lo, hi = min(v[i] for v in vs), max(v[i] for v in vs)
        if abs(d[i]) < 1e-12:
            if o[i] < lo or o[i] > hi:
                return False
            continue
        a, b = (lo - o[i]) / d[i], (hi - o[i]) / d[i]
        if a > b:
            a, b = b, a
        t0, t1 = max(t0, a), min(t1, b)
        if t0 > t1:
            return False
    return t1 > 0


def raycast(pieces, origin, direction):
    """(point, outward normal) of the first face of any solid of `pieces` hit by the ray, or None."""
    d = unit(direction)
    best = None
    for pc in pieces:
        for s in pc.solids:
            vs = s["verts"]
            if not _ray_box(origin, d, vs):              # quick reject: the ray misses the solid's box
                continue
            for f in s["faces"]:
                for k in range(1, len(f) - 1):                     # fan triangles, Moller-Trumbore
                    p0, p1, p2 = vs[f[0]], vs[f[k]], vs[f[k + 1]]
                    e1, e2 = sub(p1, p0), sub(p2, p0)
                    h = cross(d, e2)
                    det = dot(e1, h)
                    if abs(det) < 1e-12:
                        continue
                    inv = 1.0 / det
                    sv = sub(origin, p0)
                    u = inv * dot(sv, h)
                    if u < -1e-9 or u > 1 + 1e-9:
                        continue
                    q = cross(sv, e1)
                    v = inv * dot(d, q)
                    if v < -1e-9 or u + v > 1 + 1e-9:
                        continue
                    t = inv * dot(e2, q)
                    if t > 1e-6 and (best is None or t < best[0]):
                        best = (t, f, s)
    if best is None:
        return None
    t, f, s = best
    return add(origin, mul(d, t)), L._face_normal(s["verts"], f, s["centroid"])


def bounds(pieces):
    pts = [v for pc in pieces for s in pc.solids for v in s["verts"]]
    return [min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)]


# ---------------------------------------------------------------- the builder
class Mech:
    def __init__(self, lod, lib, bulk=1.0):
        self.lod, self.lib, self.bulk = lod, lib, bulk
        self.pieces, self.errors = [], []
        self.by_slot = {}
        self.bones = []                                 # (joint, joint): the skeleton, for the viewer's Skeleton layer

    def make(self, block_id, slot, mirror=False, scale=None, params=None):
        part = block_id.split("/")[0]
        s = (PART_SCALE.get(part, 1.0) if scale is None else scale) * self.bulk
        pc = Piece(block_id, self.lod, self.lib, s, mirror, params, slot)
        self.pieces.append(pc)
        self.by_slot.setdefault(slot, []).append(pc)
        return pc

    def fit(self, block_id, slot, j1, j2, mirror=False, bulk=None):
        """A limb on its bone: its first two anchors (top, bottom) give its axis; its SOLID extent along that axis is scaled
        (uniformly) to span the bone from j1 to j2 plus JOINT_OVERLAP into each neighbour, so limbs always meet at a joint
        (a block's ends stop short of its anchors, and the first assembly left gaps at the knees)."""
        probe = Piece(block_id, self.lod, self.lib, 1.0, mirror)
        names = list(probe.anchors)[:2]
        a, b = probe.anchors[names[0]], probe.anchors[names[1]]
        u = unit(sub(b, a))
        ts = [dot(sub(v, a), u) for s in probe.solids for v in s["verts"]]
        t0, t1 = min(ts), max(ts)
        bone = norm(sub(j2, j1))
        s_len = (bone + 2 * JOINT_OVERLAP) / max(1e-9, t1 - t0)
        # thickness grows with the stretch but no more than MAX_LIMB_THICKEN (a short fat barrel on a long bone otherwise
        # swelled into a drum, 2026-11-17), times the 'Mech's bulk
        # ITERATION 1: heavy legs were matchsticks (an 80-ton Awesome on a Commando's legs): thickness is clamped from below too,
        # and follows the limb's own bulk (legs grow with tonnage faster than the rest)
        s_cross = max(0.85, min(s_len, MAX_LIMB_THICKEN)) * (self.bulk if bulk is None else bulk)
        pc = probe
        start = add(a, mul(u, t0))                                  # the solid's top end, on the axis
        wu = unit(sub(j2, j1))
        R = rot_align(u, wu)
        top = sub(j1, mul(wu, JOINT_OVERLAP))

        def move(p):
            r = sub(p, start)
            along = dot(r, u)
            perp = sub(r, mul(u, along))
            return add(top, rot_apply(R, add(mul(u, along * s_len), mul(perp, s_cross))))
        for sd in pc.solids:
            sd["verts"] = [move(v) for v in sd["verts"]]
            sd["centroid"] = move(sd["centroid"])
        pc.anchors = {k: move(v) for k, v in pc.anchors.items()}
        pc.slot = slot
        self.pieces.append(pc)
        self.by_slot.setdefault(slot, []).append(pc)
        return pc

    def seat(self, block_id, slot, anchor, hosts, origin, direction, axis=None, offset=0.0, mirror=False, params=None, scale=None):
        """A block ON a surface: cast the ray at the hosts; the anchor goes on the hit point (plus `offset` along the normal),
        and the block's `axis` (its mounting face's outward direction) is turned onto the surface normal, so it sits flush."""
        hit = raycast(hosts, origin, direction)
        if hit is None:
            self.errors.append("%s (%s): its seating ray found no surface" % (block_id, slot))
            return None
        p, n = hit
        pc = self.make(block_id, slot, mirror, scale, params)
        R = rot_align(axis, n) if axis is not None else IDENTITY
        pc.place(anchor, add(p, mul(n, offset)), R)
        return pc


def settle(upper, lower, at, overlap=0.03):
    """A block stacked on a socket SITS on the block below: measured on the vertical through the socket, its underside is moved
    to the lower block's top surface (less a small overlap), up or down. Sockets that sit a little off a block's real surface
    (one did: the skirt pelvis) can then never leave a gap or a deep overlap."""
    top = raycast([lower], (at[0], at[1] + 50.0, at[2]), (0, -1, 0))
    under = raycast([upper], (at[0], at[1] - 50.0, at[2]), (0, 1, 0))
    if top is None or under is None:
        return
    dy = top[0][1] - under[0][1] - overlap
    upper.place(next(iter(upper.anchors)), add(upper.anchors[next(iter(upper.anchors))], (0.0, dy, 0.0)))


def slot_hosts(m, *slots):
    return [pc for s in slots for pc in m.by_slot.get(s, [])]


def build(choice, lod, lib, mass=50, jump=0):
    """One 'Mech from a slot -> block choice (None = no block in that slot). Returns the Mech (pieces, errors)."""
    m = Mech(lod, lib, bulk=(max(20, mass) / 50.0) ** 0.22)
    leg_bulk, arm_bulk = (max(20, mass) / 50.0) ** 0.45, (max(20, mass) / 50.0) ** 0.3
    bird = choice.get("lower_leg") == "lower_leg/bird_shin"
    probe = Piece(choice["upper_torso"], lod, lib, PART_SCALE["upper_torso"] * m.bulk)
    pl, ph = bounds([probe])
    chest_h = ph[1] - pl[1]

    # --- legs: the foot on the ground fixes the ankle; the pelvis's hip sockets fix the hips
    foot = Piece(choice["foot"], lod, lib, PART_SCALE["foot"] * m.bulk)
    ankle_y = foot.anchors["ankle"][1] - min(v[1] for s in foot.solids for v in s["verts"])
    rise = max(1.5, leg_ratio(mass) * chest_h - ankle_y)        # hip above the ankle
    if bird:
        kf, sb = math.radians(BIRD_KNEE_FWD), math.radians(BIRD_SHIN_BACK)
        th = rise * (1 - BIRD_SHIN_SHARE) / math.cos(kf)
        sh = rise * BIRD_SHIN_SHARE / math.cos(sb)
        knee_rel = (0.0, -th * math.cos(kf), th * math.sin(kf))
        ankle_rel = add(knee_rel, (0.0, -sh * math.cos(sb), -sh * math.sin(sb)))
    else:
        knee_rel = (0.0, -rise * THIGH_SHARE, 0.12)
        ankle_rel = add(knee_rel, (0.0, -rise * (1 - THIGH_SHARE), -0.12))
    hip_y = ankle_y - ankle_rel[1]
    pel = m.make(choice["pelvis"], "pelvis")
    pel.place("hip_L", (pel.anchors["hip_L"][0], hip_y, -ankle_rel[2]))
    joints = {}
    for side, mirror, hk in (("L", False, "hip_L"), ("R", True, "hip_R")):
        hip = pel.anchors[hk]
        sx = 1 if side == "L" else -1
        if choice.get("hip"):                           # the hip drum on the pelvis's side; the hip joint moves into it
            d = m.seat(choice["hip"], "hip", "joint", [pel], (sx * 20.0, hip[1], hip[2]), (-sx, 0, 0), axis=(sx, 0, 0), mirror=mirror)
            if d is not None:
                dl, dh = bounds([d])                    # the joint sits in the middle of whatever hip block was seated
                hip = ((dl[0] + dh[0]) / 2, hip[1], hip[2])
        knee, ankle = add(hip, knee_rel), add(hip, ankle_rel)
        joints[side] = (hip, knee, ankle)
        m.bones += [(hip, knee), (knee, ankle), (hip, (0.0, hip[1], hip[2]))]
        m.fit(choice["upper_leg"], "upper_leg", hip, knee, mirror, bulk=leg_bulk)
        m.fit(choice["lower_leg"], "lower_leg", knee, ankle, mirror, bulk=leg_bulk)
        ft = m.make(choice["foot"], "foot", mirror)
        ft.place("ankle", ankle)
    legs = slot_hosts(m, "upper_leg", "lower_leg")
    for side, mirror in (("L", False), ("R", True)):
        sx = 1 if side == "L" else -1
        hip, knee, ankle = joints[side]
        leg = [pc for pc in legs if pc.mirror == mirror]
        k = choice.get("knee")
        if k == "knee/ball_joint":
            m.make(k, "knee", mirror).place("joint", knee)
        elif k == "knee/guard_plate":
            m.seat(k, "knee", "knee", leg, (knee[0], knee[1], knee[2] + 20.0), (0, 0, -1), axis=(0, 0, 1), mirror=mirror)
        elif k:
            # the ray aims a little up the thigh, then a little down the shin, if it slips past the joint itself
            for q in (knee, add(knee, mul(sub(hip, knee), 0.1)), add(knee, mul(sub(ankle, knee), 0.1))):
                if raycast(leg, (q[0] + sx * 20.0, q[1], q[2]), (-sx, 0, 0)):
                    m.seat(k, "knee", "joint", leg, (q[0] + sx * 20.0, q[1], q[2]), (-sx, 0, 0), axis=(sx, 0, 0), mirror=mirror)
                    break
            else:
                m.errors.append("%s (knee): no leg surface at the knee" % k)
        a = choice.get("ankle")
        if a == "ankle/cuff":
            m.make(a, "ankle", mirror).place("foot", ankle)
        elif a:
            y = ankle[1] + 0.25
            m.seat(a, "ankle", "joint", leg, (ankle[0] + sx * 20.0, y, ankle[2]), (-sx, 0, 0), axis=(sx, 0, 0), mirror=mirror,
                   params={"pair": False, "gap": 0.0})

    # --- the waist and the chest stack on the pelvis's waist socket
    base = pel.anchors["waist"]
    if choice.get("waist"):
        w = m.make(choice["waist"], "waist")
        names = list(w.anchors)[:2]
        w.place(names[0], base)
        settle(w, pel, base)
        base = w.anchors[names[1]]
    below = m.pieces[-1] if choice.get("waist") else pel
    chest = m.make(choice["upper_torso"], "upper_torso")
    ca = chest.anchors
    if "waist" in ca:
        chest.place("waist", base)
    elif "hips" in ca:
        chest.place("hips", base)
    else:                                              # an upright barrel (the UrbanMech): its bottom on the base
        chest.place("bottom", base)
    settle(chest, below, base)
    lo, hi = bounds([chest])
    ch_h, ch_w, ch_d = hi[1] - lo[1], hi[0] - lo[0], hi[2] - lo[2]
    spine_top = chest.anchors.get("neck") or chest.anchors.get("cockpit") or chest.anchors.get("top") or ((lo[0] + hi[0]) / 2, hi[1], 0.0)
    m.bones.append(((0.0, pel.anchors["hip_L"][1], pel.anchors["hip_L"][2]), spine_top))
    cx, cz = (lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2
    ca = chest.anchors
    lozenge = "cockpit" in ca
    sockets = {}
    for side, sx in (("L", 1), ("R", -1)):
        key = "shoulder_" + side
        sockets[side] = ca[key] if key in ca else (sx * ch_w / 2, lo[1] + ch_h * 0.78, cz)

    # --- the head: seated on the chest's top at the neck (a canopy turned tangent to the surface it sits on)
    hd = choice.get("head")
    if hd:
        nk = ca.get("cockpit") or ca.get("neck") or ca.get("top") or (cx, hi[1], cz)
        host = [chest]
        aim = (nk[0], hi[1] + 20.0, nk[2])
        if choice.get("neck_collar") and not lozenge:
            col = m.seat(choice["neck_collar"], "neck_collar", "base", host, aim, (0, -1, 0))
            if col is not None:
                m.make(hd, "head").place("neck", col.anchors["top"])
        elif hd == "head/fighter_canopy":
            m.seat(hd, "head", "seat", host, aim, (0, -1, 0), axis=(0, 1, 0))
        else:
            hp = Piece(hd, lod, lib, 1.0)
            hl_, hh_ = bounds([hp])
            cap = HEAD_PER_CHEST * ch_h / max(1e-6, (hh_[1] - hl_[1]) * m.bulk)
            m.seat(hd, "head", "neck", host, aim, (0, -1, 0), offset=-0.05, scale=min(PART_SCALE["head"], cap))

    # --- shoulders, arms and hands; or, on a slung body with no arms, the racks are the arms
    for side, sx, mirror in (("L", 1, False), ("R", -1, True)):
        sk = sockets[side]
        top = None
        if choice.get("shoulder"):
            sp = Piece(choice["shoulder"], lod, lib, 1.0)
            spl, sph = bounds([sp])
            cap = SHOULDER_PER_CHEST * ch_h / max(1e-6, (sph[1] - spl[1]) * m.bulk)
            sh = m.seat(choice["shoulder"], "shoulder", "torso", [chest], (sk[0] + sx * 20.0, sk[1], sk[2]), (-sx, 0, 0),
                        axis=(sx, 0, 0), mirror=mirror, scale=min(PART_SCALE["shoulder"], cap))
            if sh is not None:
                top = sh.anchors["arm"]
        elif choice.get("upper_arm") or choice.get("lower_arm_" + side):
            hit = raycast([chest], (sk[0] + sx * 20.0, sk[1], sk[2]), (-sx, 0, 0))
            top = hit[0] if hit else None
            if hit is None:
                m.errors.append("arm %s: no chest side to hang from" % side)
        la = choice.get("lower_arm_" + side)
        if top is None or not la:
            continue
        ua_len, fa_len = ARM_PER_CHEST * ch_h, ARM_PER_CHEST * ch_h * 1.12
        elbow = add(top, (sx * ARM_SPLAY, -ua_len, 0.0))
        m.bones += [(top, elbow), (top, (0.0, top[1], top[2]))]
        if choice.get("upper_arm"):
            m.fit(choice["upper_arm"], "upper_arm", top, elbow, mirror, bulk=arm_bulk)
        else:
            elbow = top
        if la in ("lower_arm/fist_arm", "upper_arm/heavy_sleeve"):
            wrist = add(elbow, (sx * 0.05, -fa_len, 0.1))
            m.bones.append((elbow, wrist))
            fa = m.fit(la, "lower_arm", elbow, wrist, mirror, bulk=arm_bulk)
            if choice.get("hand"):
                m.make(choice["hand"], "hand", mirror).place("wrist", wrist)
            gun = choice.get("arm_gun_" + side)
            if gun:
                mid = add(elbow, mul(sub(wrist, elbow), 0.5))
                r = lib["blocks"][gun]["params"]["diameter"] * 0.8 * PART_SCALE["weapon_mount"] * m.bulk
                m.seat(gun, "arm_gun", "mount", [fa], (mid[0] + sx * 20.0, mid[1], mid[2]), (-sx, 0, 0), offset=r, mirror=mirror)
        else:                                          # a forward gun or pod: its elbow socket on the elbow
            a = math.radians(FORWARD_ARM_PITCH)
            down = (0.0, -math.sin(a), math.cos(a))
            gp = Piece(la, lod, lib, 1.0)
            gl, gh = bounds([gp])
            cap = GUN_ARM_PER_FOREARM * fa_len / max(1e-6, (gh[2] - gl[2]) * m.bulk)
            m.make(la, "lower_arm", mirror, scale=min(PART_SCALE["lower_arm"], cap)).place("elbow", elbow, rot_align((0.0, 0.0, 1.0), down))
            m.bones.append((elbow, add(elbow, mul(down, fa_len))))

    # --- on the chest: bays, humps, racks, the belly plate, the back, antennas and fins (all seated)
    st = choice.get("side_torso")
    # ITERATION 1: the side (and size) of a torso weapon comes from the unit file (choice["side_torso_plan"]: side -> params);
    # before, a bay went on both sides and the Hunchback's hump on the wrong one
    plan = choice.get("side_torso_plan") or {"L": {}, "R": {}}
    for side, sx, mirror in (("L", 1, False), ("R", -1, True), ("C", 0, False)):
        if side not in plan or not st:
            continue
        prm = dict(plan[side])
        sc = prm.pop("_scale", None)
        sc = None if sc is None else sc * PART_SCALE["side_torso"]
        if st == "side_torso/launcher_bay":
            m.seat(st, "side_torso", "torso", [chest], (sx * ch_w * 0.22 + cx, lo[1] + ch_h * 0.66, hi[2] + 20.0), (0, 0, -1),
                   axis=(0, 0, 1), mirror=mirror, params=prm or None, scale=sc)
        elif st == "side_torso/side_wing_rack":
            m.seat(st, "side_torso", "pivot", [chest], (cx + (sx or 1) * ch_w * 0.36, hi[1] + 20.0, sockets.get(side, sockets["L"])[2]),
                   (0, -1, 0), axis=(0, 1, 0), mirror=mirror, params=prm or None, scale=sc)
        elif st == "side_torso/cannon_hump" and side in "LR":
            m.seat(st, "side_torso", "torso", [chest], (cx + sx * ch_w * 0.3, hi[1] + 20.0, cz), (0, -1, 0), axis=(0, 1, 0),
                   mirror=mirror, scale=sc)
    if choice.get("belly") and not lozenge:
        m.seat(choice["belly"], "belly", "joint", [chest], (cx, lo[1] + ch_h * 0.28, hi[2] + 20.0), (0, 0, -1), axis=(0, 0, 1))
    deck = choice.get("back_deck") or ("back_deck/jump_jet_pack" if jump > 0 else None)
    if deck == "back_deck/jump_jet_pack":
        m.seat(deck, "back_deck", "back", [chest], (cx, lo[1] + ch_h * 0.5, lo[2] - 20.0), (0, 0, 1), axis=(0, 0, -1))
    elif deck:
        dz = ca["deck"][2] if "deck" in ca else lo[2] + ch_d * 0.25
        m.seat(deck, "back_deck", "deck", [chest], (cx, hi[1] + 20.0, dz), (0, -1, 0), axis=(0, 1, 0))
    if choice.get("antenna"):
        heads = slot_hosts(m, "head") or [chest]
        hl, hh = bounds(heads)
        m.seat(choice["antenna"], "antenna", "base", heads, ((hl[0] + hh[0]) / 2 + (hh[0] - hl[0]) * 0.25, hh[1] + 20.0,
                                                             (hl[2] + hh[2]) / 2 - (hh[2] - hl[2]) * 0.15), (0, -1, 0), axis=(0, 1, 0))
    if choice.get("fins"):
        for sx, mirror in ((1, False), (-1, True)):
            m.seat(choice["fins"], "fins", "root", [chest], (cx + sx * ch_w * 0.2, hi[1] + 20.0, lo[2] + ch_d * 0.3), (0, -1, 0),
                   axis=(0, 1, 0), mirror=mirror)
    return m


# ---------------------------------------------------------------- the checks
def check_mech(m):
    """Problems with one built 'Mech: seat misses, more than one connected piece, not standing on the ground."""
    errs = list(m.errors)
    solids = [s for pc in m.pieces for s in pc.solids]
    boxes = []
    for s in solids:
        vs = s["verts"]
        boxes.append(([min(v[i] for v in vs) - CONTACT_EPS for i in range(3)], [max(v[i] for v in vs) + CONTACT_EPS for i in range(3)]))
    owner = []
    for pc in m.pieces:
        owner += [pc] * len(pc.solids)
    parent = list(range(len(solids)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(len(solids)):                       # the solids of one block belong together (a block is one part)
        if i and owner[i] is owner[i - 1]:
            parent[find(i)] = find(i - 1)
    for i in range(len(solids)):
        for j in range(i + 1, len(solids)):
            (a0, a1), (b0, b1) = boxes[i], boxes[j]
            if all(a0[k] <= b1[k] and b0[k] <= a1[k] for k in range(3)):
                parent[find(i)] = find(j)
    groups = {}
    for i in range(len(solids)):
        groups.setdefault(find(i), set()).add(owner[i].block + " (" + owner[i].slot + ")")
    if len(groups) > 1:
        main = max(groups.values(), key=len)
        loose = sorted(set().union(*[g for g in groups.values() if g is not main]))
        errs.append("not one piece: loose " + ", ".join(loose))
    low = min(v[1] for s in solids for v in s["verts"])
    if abs(low) > 0.03:
        errs.append("does not stand on the ground (lowest point %.3f)" % low)
    return errs


# ---------------------------------------------------------------- the two builds of a unit
SLOTS = ["foot", "lower_leg", "upper_leg", "knee", "hip", "ankle", "pelvis", "waist", "upper_torso", "head", "neck_collar",
         "shoulder", "upper_arm", "lower_arm_L", "lower_arm_R", "hand", "side_torso", "belly", "back_deck", "antenna", "fins",
         "arm_gun_L", "arm_gun_R"]
TAX_PART = {"lower_arm_L": "lower_arm", "lower_arm_R": "lower_arm", "belly": "lower_torso", "fins": "fins_spars_wings",
            "arm_gun_L": "weapon_mount", "arm_gun_R": "weapon_mount"}
OPTIONAL_NONE = {"knee": 2, "hip": 2, "ankle": 2, "waist": 1, "neck_collar": 2, "side_torso": 2, "belly": 3, "back_deck": 3,
                 "antenna": 1, "fins": 4, "arm_gun_L": 4, "arm_gun_R": 4}
WAIST_FROM_LOWER = ("lower_torso/faceted_belly_band",)          # a belly band stands between pelvis and chest, like a waist


def options(lib, slot):
    """The library's blocks for a slot (what the name hash picks among), plus 'none' entries for an optional slot."""
    part = TAX_PART.get(slot, slot)
    blocks = sorted(b for b in lib["blocks"] if b.split("/")[0] == part)
    if slot == "waist":
        blocks += list(WAIST_FROM_LOWER)
    if slot == "belly":
        blocks = ["lower_torso/round_belly_plate"]
    if slot.startswith("lower_arm"):
        blocks += ["upper_arm/heavy_sleeve"]                    # the trunk arm (prune_1: the sleeve over the whole arm)
    if slot.startswith("arm_gun"):
        blocks = [b for b in blocks if b in ("weapon_mount/long_barrel", "weapon_mount/twin_barrel_cluster")]
    if slot == "upper_torso":
        blocks = [b for b in blocks if b != "lower_torso/transverse_cylinder"]
    return blocks + [None] * OPTIONAL_NONE.get(slot, 0)


def hash_pick(unit, slot, opts):
    key = (unit["chassis"] + " " + unit["model"] + "|" + slot).lower().encode()
    return opts[hashlib.sha256(key).digest()[0] % len(opts)]


def make_consistent(choice, lib):
    """The rules that keep a build buildable: a slung body takes the fighter canopy and the canopy only goes on a slung body;
    a hand only on a fist arm; no hump and no racks on a slung body's front..."""
    if choice["upper_torso"] == "upper_torso/slung_lozenge":
        choice["head"] = "head/fighter_canopy"
        choice["neck_collar"] = None
        choice["belly"] = None
    elif choice.get("head") == "head/fighter_canopy":
        choice["head"] = "head/box_canopy"
    if not any(choice.get("lower_arm_" + s) in ("lower_arm/fist_arm", "upper_arm/heavy_sleeve") for s in "LR"):
        choice["hand"] = None
    elif not choice.get("hand"):
        choice["hand"] = "hand/fist"
    for s in "LR":
        if choice.get("lower_arm_" + s) not in ("lower_arm/fist_arm", "upper_arm/heavy_sleeve"):
            choice["arm_gun_" + s] = None
    if choice.get("waist") in ("waist/turret_ring",) and choice["upper_torso"] == "upper_torso/slung_lozenge":
        choice["waist"] = None
    return choice


# ---------------------------------------------------------------- what the unit file fixes (ITERATION 1)
ARM_KIND = {"lower_arm/barrel_arm": "gun", "lower_arm/gun_arm": "gun", "lower_arm/pod_arm": "missile",
            "lower_arm/fist_arm": "fist", "upper_arm/heavy_sleeve": "fist"}
KIND_DEFAULT = {"gun": "lower_arm/barrel_arm", "missile": "lower_arm/pod_arm", "fist": "lower_arm/fist_arm"}


def weapon_kind(name):
    n = name.lower()
    if any(k in n for k in ("lrm", "srm", "mrm", "streak", "atm", "mml", "rocket", "thunderbolt")):
        return "missile"
    if any(k in n for k in ("ac/", "autocannon", "ppc", "gauss", "large laser", "lb ", "ultra", "rotary", "rifle")):
        return "gun"
    return "small"


def arm_kind(unit, side):
    """What the unit file puts in an arm: a gun (an autocannon, PPC, Gauss rifle or large laser) -> a gun arm; missiles -> a pod
    arm; small weapons or none -> a fist arm (ITERATION 1: the Clint, Hermes II, Vindicator, Hunchback... carried two gun arms
    where the unit file has one big gun, or none)."""
    kinds = [weapon_kind(w) for loc, w in unit.get("weapons", []) if loc == ("LA" if side == "L" else "RA")]
    return "gun" if "gun" in kinds else "missile" if "missile" in kinds else "fist"


def launcher_grid(name):
    """(rows, cols) of tube mouths for a missile launcher, from the number in its name."""
    digits = re.findall(r"(\d+)", name)
    n = int(digits[-1]) if digits else 4
    if "lrm" in name.lower():
        return max(1, min(4, (n + 4) // 5)), 5
    return {1: (1, 1), 2: (1, 2), 3: (1, 3), 4: (2, 2), 5: (1, 5), 6: (2, 3)}.get(n, (2, min(5, (n + 1) // 2)))


def side_torso_plan(unit, block):
    """Which torso sides carry the side-torso block, and its size, from the unit file's LT / RT / CT weapons."""
    if not block:
        return None
    side_of = {"LT": "L", "RT": "R", "CT": "C"}
    plan = {}
    if block in ("side_torso/launcher_bay", "side_torso/side_wing_rack"):
        for loc, w in unit.get("weapons", []):
            if loc in side_of and weapon_kind(w) == "missile":
                rows, cols = launcher_grid(w)
                old = plan.get(side_of[loc])
                if not old or rows * cols > old["rows"] * old["cols"]:
                    plan[side_of[loc]] = {"rows": rows, "cols": cols, "width": 0.24 * cols + 0.28, "height": 0.26 * rows + 0.3} \
                        if block == "side_torso/launcher_bay" else {"rows": max(rows, 2), "cols": cols}
        if "C" in plan and block == "side_torso/side_wing_rack":       # racks stand on the shoulders, never in the middle
            plan.setdefault("L", plan.pop("C"))
    else:                                                              # the cannon hump: on the side of the big gun
        for loc, w in unit.get("weapons", []):
            if loc in ("LT", "RT") and weapon_kind(w) == "gun":
                n = w.lower()
                plan[side_of[loc]] = {"_scale": 1.9 if ("ac/20" in n or "gauss" in n) else 1.45 if ("ac/10" in n or "ppc" in n) else 1.15}
    return plan or ({"L": {}, "R": {}} if block != "side_torso/cannon_hump" else {"R": {}})


def apply_unit_file(c, unit, lib, pick):
    """The unit file's say: each arm's kind from its weapons (pick(slot, candidates) chooses among the blocks of that kind), the
    side-torso block's sides and size."""
    for side in "LR":
        slot = "lower_arm_" + side
        if not c.get(slot):
            continue
        kind = arm_kind(unit, side)
        if ARM_KIND.get(c[slot]) != kind:
            c[slot] = pick(slot, [b for b in options(lib, slot) if ARM_KIND.get(b) == kind]) or KIND_DEFAULT[kind]
    c["side_torso_plan"] = side_torso_plan(unit, c.get("side_torso"))
    return c


def hash_build(unit, lib):
    c = {s: hash_pick(unit, s, options(lib, s)) for s in SLOTS}
    if c["upper_torso"] == "upper_torso/slung_lozenge":            # a slung body mostly has no arms
        if hash_pick(unit, "slung_arms", [0, 0, 1]) == 0:
            c.update({"shoulder": None, "upper_arm": None, "lower_arm_L": None, "lower_arm_R": None})
    c = apply_unit_file(c, unit, lib, lambda slot, cands: hash_pick(unit, slot + "|kind", cands) if cands else None)
    return make_consistent(c, lib), {s: "name hash" for s in SLOTS}


def default_block(lib, slot):
    """The most common block for a slot (seen on the most units): what the drawings build uses where its drawing is silent
    (ITERATION 1: the name hash filled silent slots with rare body plans - a slung body on the Orion, a barrel torso on the
    Grasshopper, bird legs on the Whitworth)."""
    cands = [b for b in options(lib, slot) if b]
    return max(cands, key=lambda b: SEEN_COUNT.get(b, 0)) if cands else None


def _resolve(lib, tax, part, typ):
    """A taxonomy type -> the library block that builds it (following prune_1's merged_into), or None."""
    key = part + "/" + typ
    if key in lib["blocks"]:
        return key
    t = tax["parts"][part]["types"][typ]
    into = (t.get("merged_into") or "").split(" ")[0]
    return into if into in lib["blocks"] else None


SEEN_COUNT = {}


def drawings_build(unit, lib, tax):
    """Each slot from the taxonomy's seen_on lists (the drawings); the name hash where the drawings say nothing."""
    chassis = unit["chassis"].lower()
    for part, body in tax["parts"].items():
        for typ, t in body["types"].items():
            blk = _resolve(lib, tax, part, typ)
            if blk and part + "/" + typ == blk:
                SEEN_COUNT[blk] = t.get("units_seen", len(t.get("seen_on", [])))
    seen = {}                                             # taxonomy part -> [(block, side note)]
    for part, body in tax["parts"].items():
        for typ, t in body["types"].items():
            for s in t.get("seen_on", []):
                name, _, note = s.partition("(")
                if name.strip().lower() != chassis or "(no)" in s.replace(" ", ""):
                    continue
                blk = _resolve(lib, tax, part, typ)
                if blk:
                    seen.setdefault(part, []).append((blk, note.lower()))
    c, why = {}, {}
    for slot in SLOTS:
        part = TAX_PART.get(slot, slot)
        found = seen.get(part, [])
        if slot == "waist":
            found = found + [x for x in seen.get("lower_torso", []) if x[0] in WAIST_FROM_LOWER]
        if slot == "belly":
            found = [x for x in seen.get("lower_torso", []) if x[0] == "lower_torso/round_belly_plate"]
        if slot.startswith("lower_arm"):
            side = "left" if slot.endswith("L") else "right"
            sided = [x for x in found if side in x[1]]
            found = sided or [x for x in found if "left" not in x[1] and "right" not in x[1]]
        if slot.startswith("arm_gun"):
            found = [x for x in found if x[0] in ("weapon_mount/long_barrel", "weapon_mount/twin_barrel_cluster")]
        if slot == "upper_torso":
            found = [x for x in found if x[0].startswith("upper_torso/")]
        allowed = set(options(lib, slot))               # a merge can lead outside the slot (a shoulder fin -> the fin plate)
        found = [x for x in found if x[0] in allowed]
        slung = any(x[0] == "upper_torso/slung_lozenge" for x in seen.get("upper_torso", []))
        if slot in ("upper_arm", "lower_arm_L", "lower_arm_R") and "lower_arm" not in seen and slung:
            found = []                                  # no forearm in the drawing = no arms (the Catapult: its racks are its arms;
                                                        # the survey's 'thin rod' and 'claw' there were its raised foot)
        if found:                                       # several: the most distinctive (seen on the fewest units)
            found.sort(key=lambda x: SEEN_COUNT.get(x[0], 99))
            c[slot], why[slot] = found[0][0], "drawing"
        elif slot in OPTIONAL_NONE:
            c[slot], why[slot] = None, "drawing (none)"
        elif slot in ("upper_arm", "lower_arm_L", "lower_arm_R") and "lower_arm" not in seen and \
                any(x[0] == "upper_torso/slung_lozenge" for x in seen.get("upper_torso", [])):
            c[slot], why[slot] = None, "drawing (no arms: a slung body)"
        else:
            c[slot], why[slot] = default_block(lib, slot), "the commonest (drawing silent)"
    arms_before = {s: c.get("lower_arm_" + s) for s in "LR"}

    def pick(slot, cands):                          # the drawing's own blocks of the right kind first, the most distinctive
        side = "left" if slot.endswith("L") else "right"
        drawn = [x[0] for x in seen.get("lower_arm", []) if x[0] in cands]
        drawn.sort(key=lambda b: SEEN_COUNT.get(b, 99))
        return drawn[0] if drawn else None
    sided = {s: any(("left" if s == "L" else "right") in x[1] for x in seen.get("lower_arm", [])) for s in "LR"}
    keep = {s: c.get("lower_arm_" + s) for s in "LR" if sided[s]}
    c = apply_unit_file(c, unit, lib, pick)
    for s in "LR":
        if s in keep:                               # a side the drawing names stays as drawn
            c["lower_arm_" + s] = keep[s]
        elif c.get("lower_arm_" + s) != arms_before[s]:
            why["lower_arm_" + s] = "the unit file (%s in the arm)" % arm_kind(unit, s)
    return make_consistent(c, lib), why


# ---------------------------------------------------------------- the viewer (the earlier art project's, tools/token_3d_template.html)
def mesh_for_viewer(m, k):
    """The viewer's mesh: parts with flat vertex and triangle lists (outward winding) and a paint class."""
    parts = []
    for pc in m.pieces:
        part = pc.block.split("/")[0]
        for s in pc.solids:
            vs = [mul(v, k) for v in s["verts"]]
            cen = mul(s["centroid"], k)
            tris = []
            for f in s["faces"]:
                for j in range(1, len(f) - 1):
                    a, b, c = f[0], f[j], f[j + 1]
                    nrm = cross(sub(vs[b], vs[a]), sub(vs[c], vs[a]))
                    fc = mul(add(add(vs[a], vs[b]), vs[c]), 1 / 3)
                    tris += [a, b, c] if dot(nrm, sub(fc, cen)) >= 0 else [a, c, b]
            tone = s.get("tone")
            if tone is not None and tone < 0.3:
                cls = "ck" if part == "head" else "ln"
            elif tone is not None and tone > 0.95:
                cls = "t3"
            elif part in ("knee", "hip", "ankle", "neck_collar", "waist"):
                cls = "t4"
            elif part in ("side_torso", "weapon_mount", "back_deck", "antenna") or pc.block in ("lower_arm/barrel_arm", "lower_arm/gun_arm", "lower_arm/pod_arm"):
                cls = "gm"
            elif part in ("shoulder", "fins_spars_wings"):
                cls = "tm"
            elif part in ("upper_leg", "lower_leg", "upper_arm", "lower_arm", "foot", "hand"):
                cls = "t2"
            else:
                cls = "t1"
            ly = "equipment" if cls == "gm" else "armor"
            parts.append({"v": [round(x, 3) for p in vs for x in p], "f": tris, "cls": cls, "ly": ly})
    for a, b in m.bones:                               # the skeleton: thin bars on the bones, ball joints at the ends
        if norm(sub(b, a)) < 1e-6:
            continue
        for kind, part in (("bone", {"kind": "tube", "id": "bone", "assembly": "bone", "a": list(a), "b": list(b), "w0": [0.14, 0.14],
                                      "w1": [0.14, 0.14], "n": 6}),
                           ("joint", {"kind": "dome", "id": "j", "assembly": "bone", "c": list(a), "r": [0.16, 0.16, 0.16], "n": 6, "rings": 3})):
            for sd in L.expand_parts({"parts": [part]}):
                vs = [mul(v, k) for v in sd["verts"]]
                cen = mul(sd["centroid"], k)
                tris = []
                for f in sd["faces"]:
                    for j in range(1, len(f) - 1):
                        x, y, z = f[0], f[j], f[j + 1]
                        nrm = cross(sub(vs[y], vs[x]), sub(vs[z], vs[x]))
                        fc = mul(add(add(vs[x], vs[y]), vs[z]), 1 / 3)
                        tris += [x, y, z] if dot(nrm, sub(fc, cen)) >= 0 else [x, z, y]
                parts.append({"v": [round(x, 3) for p in vs for x in p], "f": tris, "cls": "bn", "ly": "skeleton"})
    return {"parts": parts}


def viewer_units(lib, tax, lods=("high", "low")):
    units = json.load(open(os.path.join(L.REF, "units.json")))["units"]
    out, problems = [], []
    for u in units:
        try:
            mt = L.read_mtf(u["unit"])
            mass, jump = mt.get("mass") or 50, mt.get("jump") or 0
        except Exception:                                  # noqa: BLE001 - the viewer still shows the unit
            mass, jump = u.get("mass") or 50, u.get("jump") or 0
        builds = {"ref": drawings_build(u, lib, tax), "hash": hash_build(u, lib)}
        levels = 1.65 + 0.6 * (min(100, max(20, mass)) - 20) / 80.0
        e = {"id": u["unit"].lower().replace(" ", "-"), "name": u["unit"], "chassis": u["chassis"], "tons": mass,
             "rules": 2, "config": "Biped", "source": "block library", "confidence": "", "stealth": False, "tags": {}}
        for key, (choice, why) in builds.items():
            for lod in lods:
                m = build(choice, lod, lib, mass, jump)
                errs = check_mech(m)
                problems += ["%s %s %s: %s" % (u["unit"], key, lod, x) for x in errs]
                lo, hi = bounds(m.pieces)
                kscale = levels / max(1e-6, hi[1])
                vkey = key if lod == "high" else key + "_low"
                e[vkey] = mesh_for_viewer(m, kscale)
                tris = sum(pc.tris for pc in m.pieces)
                rows = [("build", "from the drawings (taxonomy seen_on)" if key == "ref" else "name hash only"),
                        ("detail", "%s, %d triangles" % (lod.upper(), tris))]
                rows += [(s.replace("_", " "), (choice[s].split("/")[1].replace("_", " ") if choice.get(s) else "none")
                          + ("" if key == "hash" else "  (" + why[s] + ")")) for s in SLOTS if choice.get(s) or key == "ref"]
                if jump and not choice.get("back_deck"):
                    rows.append(("back deck", "jump jet pack (the unit file: jumps %d)" % jump))
                e["tags"][vkey] = rows
                if lod == "high":
                    e["levels"] = levels
        e["note"] = ("Built from the block library on a socket skeleton. 'From the drawings' takes each slot from the TRO drawings "
                     "(the block taxonomy); 'Name hash' is what an untagged unit would get.")
        out.append(e)
    out.sort(key=lambda x: (x["tons"], x["name"]))
    return out, problems


VIEWER_JS_INFO = r'''function renderInfo() {
  const u = state.unit;
  document.querySelectorAll("#list button").forEach(b => b.setAttribute("aria-pressed", b.id === "u-" + u.id));
  document.getElementById("uname").textContent = u.name;
  document.getElementById("umeta").replaceChildren(...[u.tons + " t", "drawn " + u.levels.toFixed(2) + " lv", "block library"].map(t => mk("span", { textContent: t })));
  const V = [["ref", "From the drawings"], ["hash", "Name hash"], ["ref_low", "Drawings, LOW"], ["hash_low", "Name hash, LOW"]];
  if (!u[state.variant]) state.variant = "ref";
  document.getElementById("variant").replaceChildren(...V.map(([k, n]) => { const b = mk("button", { type: "button", textContent: n, onclick: () => { state.variant = k; refresh(); } }); b.setAttribute("aria-pressed", state.variant === k); return b; }));
  document.getElementById("unote").textContent = u.note;
  const dl = document.getElementById("utags"); dl.replaceChildren();
  (u.tags[state.variant] || []).forEach(([k, v]) => { dl.append(mk("dt", { textContent: k }), mk("dd", { textContent: v })); });
  document.getElementById("badge").textContent = u.name + " · " + (V.find(x => x[0] === state.variant) || ["", ""])[1];
}'''


def write_viewer(out, lods=("high", "low")):
    lib, tax = B.library(), json.load(open(os.path.join(L.REF, "block_taxonomy.json")))
    units, problems = viewer_units(lib, tax, lods)
    page = open(os.path.join(HERE, "lowpoly_viewer_template.html"), encoding="utf-8").read()
    page = page.replace("/*__DATA__*/null", json.dumps(units, separators=(",", ":")))
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    return units, problems


def make_template():
    """tools/lowpoly_viewer_template.html from the earlier art project's viewer (tools/token_3d_template.html), with the variant
    buttons and the readout changed for the block library. Run once; the template is committed."""
    src = open(os.path.join(HERE, "token_3d_template.html"), encoding="utf-8").read()
    i = src.index("function renderInfo() {")
    j = src.index("\nfunction renderTeam()", i)
    src = src[:i] + VIEWER_JS_INFO + "\n" + src[j:]
    src = src.replace('UNITS.find(u => u.id === "timber-wolf") || UNITS.find(u => u.id === "stalker") || UNITS[0]',
                      'UNITS.find(u => u.chassis === "Catapult") || UNITS[0]')
    src = src.replace('state.variant = saved.variant === "hash" ? "hash" : "ref";',
                      'state.variant = ["ref", "hash", "ref_low", "hash_low"].includes(saved.variant) ? saved.variant : "ref";')
    src = src.replace("<title>Combat Lab Model Viewer</title>", "<title>Block Mech Viewer</title>")
    src = src.replace("<h1>Combat Lab Model Viewer</h1>", "<h1>Block Mech Viewer</h1>")
    i = src.index('<p class="lede">')
    j = src.index("</p>", i)
    src = src[:i] + ('<p class="lede">The 34 TRO 3025 \'Mechs built from the low-poly block library on a skeleton with sockets: every block '
                     'joins its bone, and every block that sits on a surface is seated flush on it. <b>From the drawings</b> takes each '
                     'body part from the block survey of the TRO drawings; <b>Name hash</b> is what an unlisted unit would get. Both at '
                     'HIGH detail and at the LOW reference level. Drag to turn, scroll or pinch to zoom.') + src[j:]
    i = src.index('<div class="legend">')
    j = src.index("</div>", i)
    src = src[:i] + ('<div class="legend"><span><i style="background:var(--m-ck)"></i>cockpit glass</span><span><i style="background:var(--m-gm)">'
                     '</i>weapons and racks</span><span><i style="background:var(--m-tm)"></i>shoulders and fins (team colour)</span>'
                     '<span><i style="background:var(--m-t4)"></i>joints</span>') + src[j:]
    with open(os.path.join(HERE, "lowpoly_viewer_template.html"), "w", encoding="utf-8") as f:
        f.write(src)


def check_all(lods=("high", "low")):
    lib, tax = B.library(), json.load(open(os.path.join(L.REF, "block_taxonomy.json")))
    _, problems = viewer_units(lib, tax, lods)
    return problems


def main(argv):
    if argv[:1] == ["check"]:
        problems = check_all()
        for p in problems:
            print("FAIL", p)
        print("%s: 34 units x 2 builds x 2 levels" % ("FAIL" if problems else "OK"))
        return 1 if problems else 0
    if argv[:1] == ["template"]:
        make_template()
        return 0
    if argv[:1] == ["viewer"]:
        units, problems = write_viewer(argv[1])
        for p in problems:
            print("FAIL", p)
        print(len(units), "units;", os.path.getsize(argv[1]) // 1024, "KB")
        return 1 if problems else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
