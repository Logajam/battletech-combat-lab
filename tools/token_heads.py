"""Combat Lab art: a LINEUP of one block library slot (2026-11-04, Claude): every block of the slot on the same 'Mech, rendered
close up from the 3/4 front, plus the joined / ground / clip / clear-muzzle checks for each.

Usage: python -I tools/token_heads.py <unzipped data/meks.zip folder> <out.png> [slot] [unit file name]
       (slot default "head", unit default "Atlas AS7-D")
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


def main(root, out, slot="head", unit="Atlas AS7-D", show_body=False):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import trimesh
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    ref = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "token_reference_tags.json"), encoding="utf-8"))
    u = T.read_unit(find(root, unit))
    blocks = F.BLOCKS[slot]
    views = ((10, -60), (8, -150))                      # 3/4 front, 3/4 rear
    fig = plt.figure(figsize=(3.2 * len(blocks), 6.4))
    L = np.array([0.35, -0.6, 0.72]); L /= np.linalg.norm(L)
    for i, b in enumerate(blocks):
        m = T.build_model(u, overrides=ref, style="facet")
        m["force_blocks"] = {slot: b}
        if slot == "head":
            m["head_mount"] = "top"                      # shown on top so the whole head reads
        r = A.audit(m)
        locs = {"head": ("Head",)}.get(slot)
        parts = [(c, v, f, l) for c, tg, s_, v, f, l, ro in M._raw_parts(m, with_src=True) if ro not in ("bone", "muscle", "internal")]
        hv = [np.stack([v[:, 0], -v[:, 2], v[:, 1]], 1) * 6 for c, v, f, l in parts]        # metres, z up, front to -y
        sel = [k for k, p in enumerate(parts) if locs is None or p[3] in locs]
        allh = np.vstack([hv[k] for k in sel])
        cen, R = (allh.max(0) + allh.min(0)) / 2, np.ptp(allh, 0).max() / 2 * 1.25
        nf = sum(len(c) for c in r["floating"])
        ok = "ok" if not (nf or r["ground"] or r["clip"][0] > 0.001 or m.get("blocked_muzzles")) else f"float {nf} clip {r['clip'][0] * 6:.2f} blocked {m.get('blocked_muzzles')}"
        print(b, ok)
        for j, (el, az) in enumerate(views):
            ax = fig.add_subplot(2, len(blocks), j * len(blocks) + i + 1, projection="3d")
            polys, cols = [], []                          # one collection: matplotlib then sorts face by face (glass stays on top)
            for k, ((c, v, f, l), h) in enumerate(zip(parts, hv)):
                if k not in sel and not show_body:
                    continue
                if np.any(h.max(0) < cen - R * 1.6) or np.any(h.min(0) > cen + R * 1.6):
                    continue
                tm = trimesh.Trimesh(h, f, process=False)
                sh = np.clip(tm.face_normals @ L, 0, 1) * 0.7 + 0.25
                if c == "ck":
                    fc = [(0.3 * q, 0.55 * q, 0.95 * q) for q in sh]
                elif k in sel:
                    fc = plt.cm.gray(sh * 0.9 + 0.1)
                else:
                    fc = [(0.75 * q, 0.72 * q, 0.68 * q) for q in sh]        # the body under the head, warm grey
                polys += list(h[f])
                cols += list(fc)
            ax.add_collection3d(Poly3DCollection(polys, facecolors=cols, edgecolor=(0.1, 0.1, 0.1, 0.35), linewidths=0.3))
            ax.set_xlim(cen[0] - R, cen[0] + R); ax.set_ylim(cen[1] - R, cen[1] + R); ax.set_zlim(cen[2] - R * 0.8, cen[2] + R * 1.2)
            ax.view_init(el, az); ax.set_proj_type("ortho"); ax.set_axis_off()
            if j == 0:
                ax.set_title(f"{b}  ({ok})", fontsize=13)
    plt.tight_layout()
    plt.savefig(out, dpi=60)


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1], *(a[2:4]))
