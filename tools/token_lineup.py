"""Combat Lab art: a LINEUP of one block-library slot (2026-11-04, Claude). Every block of the slot is built on the same 'Mech, and the
locations that slot shapes are drawn on their own, 3/4 front and 3/4 rear, with their MOUNTING BRACKETS marked (Daniel,
2026-11-04: "Parts that have mounting brackets should indicate where those are"):
  green dots   joint sockets (shoulder, elbow, wrist, hip, knee, hock, ankle, waist, neck): where this part holds the next
  orange       hardpoint rails: a face rail as a short arrow out of its face, a line rail as a line along the part, a post / bay as a
               square, each numbered as INTEGRATION__shell_items.rail_count numbers them
Each block also gets the checks: joined, above ground, no clipping, every muzzle clear.

Usage: python -I tools/token_lineup.py <unzipped data/meks.zip folder> <out.png> <slot> [unit file name] [--body]
       slot: a key of INTEGRATION__shell_facet.BLOCKS; unit default "Atlas AS7-D"; --body also draws the rest of the 'Mech in a warm grey.
Art tools only: numpy, scipy, trimesh, matplotlib, python-fcl."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

import INTEGRATION__tokens as T
import INTEGRATION__token_mesh as M
import INTEGRATION__shell_facet as F
import token_audit as A
from token_sheet import find

# which locations a slot shapes (what the lineup draws)
SLOT_LOCS = {"head": ("Head",), "torso": ("Center Torso", "Left Torso", "Right Torso", "Left Arm", "Right Arm"), "housing": ("Left Torso", "Right Torso", "Center Torso"),
             "missiles": ("Left Torso", "Right Torso", "Center Torso", "Head", "Left Arm", "Right Arm"), "arm": ("Right Arm",), "pauldron": ("Right Arm",),
             "forearm": ("Right Arm",), "hand": ("Right Arm",), "leg": ("Right Leg",), "knee": ("Right Leg",), "foot": ("Right Leg",),
             "pose": ("Left Leg", "Right Leg", "Center Torso", "Left Torso", "Right Torso"), "waist": ("Center Torso", "Left Leg", "Right Leg"),
             "pelvis": ("Left Leg", "Right Leg")}


def main(root, out, slot="head", unit="Atlas AS7-D", show_body=False):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import trimesh
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    ref = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "token_reference_tags.json"), encoding="utf-8"))
    u = T.read_unit(find(root, unit))
    blocks = F.BLOCKS[slot]
    locs = SLOT_LOCS.get(slot)
    views = ((10, -60), (8, -150))
    fig = plt.figure(figsize=(4.0 * len(blocks), 8.0))
    L = np.array([0.35, -0.6, 0.72]); L /= np.linalg.norm(L)

    def to_plot(p):                                        # model metres (x right, y fwd, z up) -> the plot's frame (front to -y)
        p = np.asarray(p, float)
        return np.array([-p[0], -p[1], p[2]])
    for i, b in enumerate(blocks):
        m = T.build_model(u, overrides=ref, style="facet")
        m["force_blocks"] = {slot: b}
        if slot == "head":
            m["head_mount"] = "top"                      # shown on top so the whole head reads
        r = A.audit(m)
        parts = [(c, v, f, l) for c, tg, s_, v, f, l, ro in M._raw_parts(m, with_src=True) if ro not in ("bone", "muscle", "internal")]
        hv = [np.stack([v[:, 0], -v[:, 2], v[:, 1]], 1) * 6 for c, v, f, l in parts]        # metres, z up, front to -y
        sel = [k for k, p in enumerate(parts) if locs is None or p[3] in locs]
        allh = np.vstack([hv[k] for k in sel])
        cen, R = (allh.max(0) + allh.min(0)) / 2, np.ptp(allh, 0).max() / 2 * 0.95
        nf = sum(len(c) for c in r["floating"])
        bad = nf or r["ground"] or r["clip"][0] > 0.001 or m.get("blocked_muzzles")
        ok = "ok" if not bad else f"float {nf} clip {r['clip'][0] * 6:.2f} blocked {m.get('blocked_muzzles')}"
        print(b, ok)
        br = m.get("_brackets") or {"joints": [], "rails": []}
        for j, (el, az) in enumerate(views):
            ax = fig.add_subplot(2, len(blocks), j * len(blocks) + i + 1, projection="3d")
            ax.computed_zorder = False                    # the brackets are drawn over the parts (a socket sits inside its joint)
            polys, cols = [], []                          # one collection: matplotlib then sorts face by face
            for k, ((c, v, f, l), h) in enumerate(zip(parts, hv)):
                if k not in sel and not show_body:
                    continue
                tm = trimesh.Trimesh(h, f, process=False)
                sh = np.clip(tm.face_normals @ L, 0, 1) * 0.7 + 0.25
                if c == "ck":
                    fc = [(0.3 * q, 0.55 * q, 0.95 * q) for q in sh]
                elif k in sel:
                    fc = plt.cm.gray(sh * 0.9 + 0.1)
                else:
                    fc = [(0.75 * q, 0.72 * q, 0.68 * q) for q in sh]
                polys += list(h[f])
                cols += list(fc)
            pc = Poly3DCollection(polys, facecolors=cols, edgecolor=(0.1, 0.1, 0.1, 0.3), linewidths=0.25)
            pc.set_zorder(1)
            ax.add_collection3d(pc)
            for zone, name, p in br["joints"]:            # joint sockets
                if locs is None or zone in locs:
                    q = to_plot(p)
                    ax.scatter([q[0]], [q[1]], [q[2]], s=70, c="#1faa4a", depthshade=False, edgecolors="k", linewidths=0.4, zorder=10)
            for zone, kind, p, d, idx in br["rails"]:      # hardpoint rails
                if locs is not None and zone not in locs:
                    continue
                q, dv = to_plot(p), to_plot(d) * np.array([1, 1, 1])
                if kind == "face":
                    e = q + dv / np.linalg.norm(dv) * R * 0.18
                    ax.plot([q[0], e[0]], [q[1], e[1]], [q[2], e[2]], color="#e07b16", lw=2.4, zorder=11)
                elif kind == "line":
                    e = q + dv
                    ax.plot([q[0], e[0]], [q[1], e[1]], [q[2], e[2]], color="#e07b16", lw=2.0, ls="--", zorder=11)
                else:
                    ax.scatter([q[0]], [q[1]], [q[2]], s=60, marker="s", c="#e07b16", depthshade=False, zorder=11)
                ax.text(q[0], q[1], q[2], str(idx), color="#b05a08", fontsize=8, zorder=12)
            ax.set_xlim(cen[0] - R, cen[0] + R); ax.set_ylim(cen[1] - R, cen[1] + R); ax.set_zlim(cen[2] - R, cen[2] + R)
            ax.view_init(el, az); ax.set_proj_type("ortho"); ax.set_axis_off()
            if j == 0:
                ax.set_title(f"{slot}: {b}  ({ok})", fontsize=12)
    fig.subplots_adjust(left=0, right=1, bottom=0, top=0.95, wspace=0, hspace=0)
    plt.savefig(out, dpi=70)


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    main(a[0], a[1], *(a[2:4]), show_body="--body" in sys.argv)
