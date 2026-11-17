#!/usr/bin/env python3
"""Connected groups of blocks: the block library's pieces snapped together at their anchors (Claude, 2026-11-17, session 28).

Daniel, 2026-11-17: "So far I like the art. Can you take the separate pieces and show examples of connected groups of them?"

A group is built by `Assembly.add(block_id, anchor, at, mirror)`: the block's named anchor is put at the world point `at`
(mirror=True makes the right-hand copy: x flipped), and the call returns the block's anchors in world coordinates, so the next
block chains on (thigh `knee` -> shin `knee`, shin `ankle` -> boot `ankle`). Two pieces have no block yet, the UPPER ARM and
the PELVIS (both later in the T15a list): `Assembly.stand_in` draws them as plain, very light boxes, named on the sheet as
stand-ins, never as library blocks. Nothing here changes a block; the sizes are each block's defaults (its reference unit's).

    python -I tools/lowpoly_groups.py            # every group's sheet into reference_art/blocks/groups/
    python -I tools/lowpoly_groups.py page OUT   # the block page (lowpoly_blocks page) with the groups added at the top
PRIVATE, like the rest of reference_art/.
"""
import base64
import html
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lowpoly_blocks as B  # noqa: E402
import lowpoly_ref as L  # noqa: E402

GROUPS_DIR = os.path.join(B.BLOCKS, "groups")
STAND_IN_TONE = 0.99


class Assembly:
    def __init__(self, lod, lib):
        self.lod, self.lib = lod, lib
        self.solids = []
        self.used = []                      # block ids, in the order added
        self.stand_ins = []

    def add(self, block_id, anchor, at, mirror=False, params=None, scale=None):
        """scale: multiply the block's size params (not counts or styles) so pieces from different reference units fit."""
        scale = scale if scale is not None else SCALE.get(block_id.split("/")[0], 1.0)
        if scale != 1.0:
            base = dict(self.lib["blocks"][block_id]["params"])
            base.update(params or {})
            params = {k: (v * scale if isinstance(v, float) else v) for k, v in base.items()}
        blk = B.generate(block_id, self.lod, params, lib=self.lib)
        ax, ay, az = blk["anchors"][anchor]
        sx = -1.0 if mirror else 1.0

        def move(p):
            return (sx * (p[0] - ax) + at[0], p[1] - ay + at[1], p[2] - az + at[2])
        for s in blk["solids"]:
            faces = [list(reversed(f)) for f in s["faces"]] if mirror else s["faces"]   # keep the winding outward
            self.solids.append(dict(s, verts=[move(v) for v in s["verts"]], centroid=move(s["centroid"]), faces=faces))
        self.used.append(block_id + (" (right, mirrored)" if mirror else ""))
        return {k: move(v) for k, v in blk["anchors"].items()}

    def stand_in(self, name, top, bottom, width, depth):
        """A plain light box from `top` to `bottom` (two points on its axis): a piece with no library block yet."""
        part = {"kind": "bar", "id": name, "assembly": "stand_in", "a": list(top), "b": list(bottom),
                "w0": [width, depth], "w1": [width, depth], "tone": STAND_IN_TONE}
        self.solids += L.expand_parts({"parts": [part]})
        self.stand_ins.append(name)

    def tris(self):
        return sum(s["tris"] for s in self.solids if s["assembly"] != "stand_in")


# ---------------------------------------------------------------- the groups
UPPER_ARM = 1.2          # stand-in upper arm length (models' units)
# Each block's default size is its reference unit's, measured on its own; put together, the Commando's limbs came out spindly
# next to its chest. Group-level scales by body part (a first guess by eye against the Commando drawing, not a rule):
SCALE = {"upper_leg": 1.3, "lower_leg": 1.3, "foot": 1.2, "lower_arm": 1.4, "hand": 1.4, "shoulder": 1.1}


def leg(a, hip=(0.0, 0.0, 0.0), mirror=False):
    """thigh -> shin -> boot, hip at `hip`."""
    t = a.add("upper_leg/tapered_slab_thigh", "hip", hip, mirror)
    s = a.add("lower_leg/tapered_slab_shin", "knee", t["knee"], mirror)
    a.add("foot/slab_boot", "ankle", s["ankle"], mirror)
    return s


def fist_arm(a, elbow, mirror=False):
    f = a.add("lower_arm/fist_arm", "elbow", elbow, mirror)
    a.add("hand/fist", "wrist", f["wrist"], mirror)


def shoulder_with_upper_arm(a, at, block="shoulder/shoulder_pod", mirror=False):
    """A shoulder drum on the torso's shoulder anchor, and the stand-in upper arm hanging from its arm anchor; returns the
    elbow point."""
    sh = a.add(block, "torso", at, mirror)
    top = sh["arm"]
    elbow = (top[0], top[1] - UPPER_ARM, top[2])
    a.stand_in("upper arm" + (" R" if mirror else " L"), top, elbow, 0.5, 0.55)
    return elbow


def g_leg(a):
    leg(a)


def g_fist_arm(a):
    elbow = shoulder_with_upper_arm(a, (0.0, 0.0, 0.0))
    fist_arm(a, elbow)


def g_gun_arm(a):
    elbow = shoulder_with_upper_arm(a, (0.0, 0.0, 0.0), block="shoulder/shoulder_disc")
    a.add("lower_arm/barrel_arm", "elbow", elbow)


def upper_body(a, head, base=(0.0, 0.0, 0.0), right_gun=False, bays=False):
    c = a.add("upper_torso/boxy_chest_sloped_shoulders", "waist", base)
    a.add(head, "neck", c["neck"])
    for side, mirror in (("shoulder_L", False), ("shoulder_R", True)):
        elbow = shoulder_with_upper_arm(a, c[side], mirror=mirror)
        if mirror and right_gun:
            a.add("lower_arm/barrel_arm", "elbow", elbow, mirror=True)
        else:
            fist_arm(a, elbow, mirror)
    if bays:                                  # two launcher bays on the chest front, over the V plate (Javelin-style)
        lib = a.lib["blocks"]["upper_torso/boxy_chest_sloped_shoulders"]["params"]
        W, H, D = lib["width"], lib["height"], lib["depth"]
        for x in (-0.58, 0.58):
            a.add("side_torso/launcher_bay", "torso", (base[0] + x, base[1] + H * 0.72, base[2] + D * 0.2))
    return c


def g_commando_upper(a):
    upper_body(a, "head/dome_helmet")


def g_javelin_upper(a):
    upper_body(a, "head/bubble_canopy", right_gun=True, bays=True)


def leg_length(lib):
    return (lib["upper_leg/tapered_slab_thigh"]["params"]["length"] * SCALE["upper_leg"]
            + lib["lower_leg/tapered_slab_shin"]["params"]["length"] * SCALE["lower_leg"]
            + lib["foot/slab_boot"]["params"]["height"] * SCALE["foot"])


def g_figure(a):
    """A whole figure from the dozen: legs, a stand-in pelvis, the Commando-kit upper body."""
    lib = a.lib["blocks"]
    leg_len = leg_length(lib)
    hip_y, hip_x = leg_len, 0.72
    for x, m in ((hip_x, False), (-hip_x, True)):
        leg(a, (x, hip_y, 0.0), m)
    pelvis_top = hip_y + 0.75
    a.stand_in("pelvis", (0.0, pelvis_top, 0.0), (0.0, hip_y - 0.15, 0.0), 2.1, 1.3)
    upper_body(a, "head/dome_helmet", base=(0.0, pelvis_top, 0.0))


def g_figure_javelin(a):
    """The same legs and pelvis with the Javelin-kit upper body: one gun arm, two launcher bays, the bubble canopy."""
    lib = a.lib["blocks"]
    leg_len = leg_length(lib)
    for x, m in ((0.72, False), (-0.72, True)):
        leg(a, (x, leg_len, 0.0), m)
    a.stand_in("pelvis", (0.0, leg_len + 0.75, 0.0), (0.0, leg_len - 0.15, 0.0), 2.1, 1.3)
    upper_body(a, "head/bubble_canopy", base=(0.0, leg_len + 0.75, 0.0), right_gun=True, bays=True)


GROUPS = [
    ("leg", "Leg: thigh, shin, boot", g_leg, {"yaw": 30, "pitch": 10}),
    ("fist_arm", "Arm: shoulder pod, (upper arm), fist arm, fist", g_fist_arm, {"yaw": 35, "pitch": 10}),
    ("gun_arm", "Gun arm: shoulder disc, (upper arm), barrel arm", g_gun_arm, {"yaw": 40, "pitch": 12}),
    ("commando_upper", "Upper body, Commando kit: chest, dome helmet, pods, fist arms", g_commando_upper, {"yaw": 25, "pitch": 12}),
    ("javelin_upper", "Upper body, Javelin kit: chest, bubble canopy, launcher bays, pods, fist arm and barrel arm", g_javelin_upper,
     {"yaw": -25, "pitch": 12}),
    ("figure", "Whole figure from the dozen (Commando kit on the legs)", g_figure, {"yaw": 25, "pitch": 8}),
    ("figure_javelin", "Whole figure, Javelin kit (same legs)", g_figure_javelin, {"yaw": -25, "pitch": 8}),
]


def make_group_sheet(key, title, build, cam, lib):
    from PIL import Image, ImageDraw, ImageFont
    hi, lo = Assembly("high", lib), Assembly("low", lib)
    build(hi)
    build(lo)
    fmap = B.camera(cam["yaw"], cam["pitch"])
    big = (520, 520)
    small = (250, 250)
    try:
        font, tiny = ImageFont.load_default(size=18), ImageFont.load_default(size=13)
    except TypeError:
        font = tiny = ImageFont.load_default()
    W = 2 * big[0] + 30
    sheet = Image.new("RGB", (W, 44 + big[1] + 26 + small[1] + 60), "white")
    dr = ImageDraw.Draw(sheet)
    dr.text((10, 10), "%s   |   HIGH %d triangles, LOW %d (blocks only)" % (title, hi.tris(), lo.tris()), fill="black", font=font)
    y = 44
    sheet.paste(B.render(hi.solids, fmap, big), (10, y))
    sheet.paste(B.render(lo.solids, fmap, big, fit_solids=hi.solids), (20 + big[0], y))
    dr.text((14, y + big[1] + 4), "HIGH", fill="black", font=tiny)
    dr.text((24 + big[0], y + big[1] + 4), "LOW (same camera)", fill="black", font=tiny)
    y += big[1] + 26
    for j, (vname, vmap) in enumerate(B.ORTHO.items()):
        x = 10 + j * (small[0] + 10)
        sheet.paste(B.render(hi.solids, vmap, small), (x, y))
        dr.text((x + 4, y + 4), "HIGH " + vname, fill="black", font=tiny)
    notes = ["blocks: " + ", ".join(dict.fromkeys(u.split(" (")[0] for u in hi.used))]
    if hi.stand_ins:
        notes.append("STAND-INS (no block yet, plain light boxes): " + ", ".join(sorted(set(n.split(" ")[0] + " " + n.split(" ")[1]
                     if " " in n else n for n in hi.stand_ins))))
    import textwrap
    lines = []
    for n in notes:
        lines += textwrap.wrap(n, 150)
    for i, line in enumerate(lines):
        dr.text((10, y + small[1] + 8 + i * 16), line, fill="black", font=tiny)
    os.makedirs(GROUPS_DIR, exist_ok=True)
    path = os.path.join(GROUPS_DIR, key + ".png")
    sheet.save(path)
    return path, hi, lo


def page(lib, out):
    """lowpoly_blocks' page with a 'Connected groups' part before the single blocks."""
    B.page(lib, out)
    items = []
    for key, title, _, _ in GROUPS:
        path = os.path.join(GROUPS_DIR, key + ".png")
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        items.append('<section><h2>%s</h2><img alt="%s" src="data:image/png;base64,%s"></section>' % (
            html.escape(title), html.escape(title), data))
    intro = ('<h1>Connected groups</h1><p>The blocks snapped together at their anchor points (hip, knee, ankle, shoulder, elbow, '
             'wrist, neck). The upper arm and the pelvis have no block yet: they are drawn as plain, very light boxes and named '
             'as stand-ins on each sheet. Sizes are each block\'s defaults, so the Commando and Javelin pieces mix at their own '
             'scales.</p>')
    with open(out) as f:
        s = f.read()
    s = s.replace("<main><h1>Block library, first pass: the common dozen</h1>",
                  "<main>" + intro + "\n".join(items) + "<h1>The single blocks</h1>")
    s = s.replace("<title>Block Library Pass One</title>", "<title>Block Library Pass One</title>")
    with open(out, "w") as f:
        f.write(s)


def main(argv):
    lib = B.library()
    for key, title, build, cam in GROUPS:
        path, hi, lo = make_group_sheet(key, title, build, cam, lib)
        print("%-16s HIGH %5d  LOW %4d  -> %s" % (key, hi.tris(), lo.tris(), os.path.relpath(path, L.ROOT)))
    if argv[:1] == ["page"]:
        page(lib, argv[1])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
