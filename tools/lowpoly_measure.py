#!/usr/bin/env python3
"""Measure a 'Mech's proportions from its AI five-view sheet (T15c step 2; Claude, 2026-11-18).

Daniel, 2026-11-18, after the Catapult: the lessons are to be applied "in a systematic fashion". The Catapult came right only when
it was measured on a grid of its five-view sheet (by eye, about an hour). This tool does the measuring: it takes each view's
outline from the sheet and reads off the landmarks, so a person only confirms the numbers.

    python -I tools/lowpoly_measure.py find "Catapult CPLT-C1"      # number the drawn shapes on the sheet (to pick the views)
    python -I tools/lowpoly_measure.py measure "Catapult CPLT-C1"   # measure the views named in reference_art/views.json

reference_art/views.json says, per unit, which sheet and where each view is: {"front": [l, t, r, b], "side": [...], "top": [...]}
(pixel boxes; `find` proposes them). Output: reference_art/measure/<unit>.json and <unit>.png (each view's outline with the
landmarks drawn, for the person who confirms).

LANDMARKS (all as shares of the standing height, ground = 0, top = 1, from the FRONT view unless said):
  crotch      the top of the gap between the legs (scanning up the middle from the ground) - the hip joints sit just above it
  shoulders   the widest row above the crotch, and its height
  leg width   the narrowest leg run at mid-leg (half the crotch height), each leg
  feet        the width of the ground rows
  body (side) the longest row above the crotch and its height: a slung body's length; the leg's front-to-back reach below
  plan (top)  overall width and length from above
The sheets are art: each view is measured on its own scale (its own height = 1), as the Catapult was (its side view is drawn about
10 % taller than its front). PRIVATE (reference_art/).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lowpoly_ref as L  # noqa: E402

VIEWS = os.path.join(L.REF, "views.json")
OUT = os.path.join(L.REF, "measure")
INK = 200                  # a pixel darker than this (0-255) is line work
OPEN = 2                   # px: lines thinner than about twice this are not part of a silhouette (arrows, leader lines)


def _mask(img):
    """The silhouette: everything not reachable from the crop's border through light pixels (line work encloses the shapes)."""
    import numpy as np
    from scipy import ndimage
    g = np.asarray(img.convert("L"), dtype=float)
    ink = g < INK
    ink = ndimage.binary_dilation(ink, iterations=1)       # close hairline gaps in the line work
    light = ~ink
    lab, _ = ndimage.label(light)
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    outside = np.isin(lab, list(border))
    sil = ~outside
    # an opening removes thin lines touching the figure (caption arrows on annotated sheets, the Commando's) and keeps the body
    sil = ndimage.binary_opening(sil, iterations=OPEN)
    lab2, n = ndimage.label(sil)
    if n == 0:
        return sil
    sizes = ndimage.sum(sil, lab2, range(1, n + 1))
    big = int(np.argmax(sizes)) + 1
    keep = lab2 == big
    rows, cols = np.where(keep)
    t, b, l_, r = rows.min(), rows.max(), cols.min(), cols.max()
    for k in range(1, n + 1):                               # parts drawn apart (a launcher on a gap) within the figure's box
        if k == big or sizes[k - 1] < sizes[big - 1] * 0.03:       # letters of a label are small blobs: never part of a figure
            continue
        rr, cc = np.where(lab2 == k)
        hk, wk = rr.max() - rr.min() + 1, cc.max() - cc.min() + 1
        if hk < 0.2 * (b - t + 1) and wk > 3 * hk:                # a line of text (a view's label): a short, wide strip
            continue
        if rr.min() >= t - 5 and cc.min() >= l_ - 40 and cc.max() <= r + 40 and rr.max() <= b + 5:
            keep |= lab2 == k
    return keep


def _runs(row):
    """(start, end) of each filled run in a row."""
    out, start = [], None
    for i, v in enumerate(row):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append((start, i - 1))
            start = None
    if start is not None:
        out.append((start, len(row) - 1))
    return out


def measure_front(sil):
    import numpy as np
    rows = np.where(sil.any(1))[0]
    top, ground = rows.min(), rows.max()
    h = float(ground - top)
    cols = np.where(sil.any(0))[0]
    mid = int((cols.min() + cols.max()) / 2)
    y = ground                                             # up the middle from the ground to the first filled pixel
    while y > top and not sil[y, max(0, mid - 2):mid + 3].any():
        y -= 1
    crotch = (ground - y) / h
    share = lambda r: (ground - r) / h
    # shoulders: the widest row in the upper part (above 60 % of the way from the crotch to the top); lower down, the widest rows
    # are where the arms (and arm guns) hang, not the shoulders (the Atlas)
    upper = [r for r in range(top, int(y - (y - top) * 0.6))]
    widths = [(int(sil[r].sum()), r) for r in upper]
    sw, sr = max(widths) if widths else (0, top)
    # the torso's own width: the run through the middle, widest between the crotch and 85 % of the height
    torso = []
    for r in range(int(ground - 0.85 * h), y):
        for a, b in _runs(sil[r]):
            if a <= mid <= b:
                torso.append((b - a + 1, r))
    tw, tr = max(torso) if torso else (0, top)
    mid_leg = int(ground - (ground - y) * 0.5)
    leg_runs = _runs(sil[mid_leg])
    feet = _runs(sil[ground - 2])
    return {"height_px": h, "crotch": round(crotch, 3), "shoulder_width": round(sw / h, 3), "shoulder_height": round(share(sr), 3),
            "leg_widths": [round((b - a + 1) / h, 3) for a, b in leg_runs], "leg_count_at_mid": len(leg_runs),
            "feet_width": round(((feet[-1][1] - feet[0][0] + 1) / h) if feet else 0, 3),
            "overall_width": round((cols.max() - cols.min() + 1) / h, 3),
            "torso_width": round(tw / h, 3), "torso_width_height": round(share(tr), 3),
            "_px": {"top": int(top), "ground": int(ground), "crotch_row": int(y), "shoulder_row": int(sr), "mid_leg_row": mid_leg,
                    "torso_row": int(tr)}}


def measure_side(sil, crotch_share):
    import numpy as np
    rows = np.where(sil.any(1))[0]
    top, ground = rows.min(), rows.max()
    h = float(ground - top)
    cr = int(ground - crotch_share * h)
    lengths = [(int(np.ptp(np.where(sil[r])[0])) + 1 if sil[r].any() else 0, r) for r in range(top, cr)]
    bl, br = max(lengths) if lengths else (0, top)
    legs = sil[cr:ground + 1]
    lc = np.where(legs.any(0))[0]
    return {"height_px": h, "body_length": round(bl / h, 3), "body_length_height": round((ground - br) / h, 3),
            "leg_reach": round(((lc.max() - lc.min() + 1) / h) if len(lc) else 0, 3),
            "_px": {"top": int(top), "ground": int(ground), "body_row": int(br)}}


def measure_top(sil):
    import numpy as np
    rows = np.where(sil.any(1))[0]
    cols = np.where(sil.any(0))[0]
    length, width = np.ptp(rows) + 1, np.ptp(cols) + 1
    return {"width_over_length": round(width / length, 3)}


def find(unit):
    """Number the large drawn shapes on the unit's sheet (to choose the view boxes for views.json)."""
    import numpy as np
    from PIL import Image, ImageDraw
    from scipy import ndimage
    sheet = sheet_path(unit)
    img = Image.open(sheet).convert("RGB")
    ink = np.asarray(img.convert("L")) < INK
    lab, n = ndimage.label(ndimage.binary_dilation(ink, iterations=4))
    boxes = [s for s in ndimage.find_objects(lab) if s is not None]
    boxes = [(b[1].start, b[0].start, b[1].stop, b[0].stop) for b in boxes if (b[0].stop - b[0].start) * (b[1].stop - b[1].start) > 4000]
    d = ImageDraw.Draw(img)
    for i, b in enumerate(boxes):
        d.rectangle(b, outline=(255, 0, 0), width=2)
        d.text((b[0] + 3, b[1] + 3), str(i), fill=(255, 0, 0))
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, unit + " find.png")
    img.save(path)
    for i, b in enumerate(boxes):
        print(i, list(b))
    print("wrote", os.path.relpath(path, L.ROOT))


def sheet_path(unit):
    views = json.load(open(VIEWS)) if os.path.exists(VIEWS) else {}
    if unit in views and "sheet" in views[unit]:
        return os.path.join(L.REF, views[unit]["sheet"])
    d = os.path.join(L.REF, "ai_sheets", unit)
    return os.path.join(d, sorted(os.listdir(d))[0])


def measure(unit):
    from PIL import Image, ImageDraw
    import numpy as np
    spec = json.load(open(VIEWS))[unit]
    img = Image.open(sheet_path(unit)).convert("RGB")
    res, pics = {"unit": unit, "sheet": os.path.relpath(sheet_path(unit), L.REF)}, []
    sils = {k: _mask(img.crop(tuple(spec[k]))) for k in ("front", "side", "top") if k in spec}
    if "front" in sils:
        res["front"] = measure_front(sils["front"])
    if "side" in sils:
        res["side"] = measure_side(sils["side"], res.get("front", {}).get("crotch", 0.45))
    if "top" in sils:
        res["top"] = measure_top(sils["top"])
    for k, sil in sils.items():                            # the outline with its landmarks, for the person who confirms
        im = Image.fromarray(np.where(sil, 170, 255).astype("uint8")).convert("RGB")
        d = ImageDraw.Draw(im)
        px = res[k].get("_px", {})
        for name, col in (("ground", (0, 0, 0)), ("top", (0, 0, 0)), ("crotch_row", (220, 0, 0)), ("shoulder_row", (0, 120, 220)),
                          ("mid_leg_row", (0, 160, 0)), ("body_row", (220, 0, 220)),
                          ("torso_row", (230, 140, 0))):
            if name in px:
                d.line([(0, px[name]), (im.width, px[name])], fill=col, width=2)
                d.text((3, px[name] - 12), name.replace("_row", ""), fill=col)
        pics.append(im)
    os.makedirs(OUT, exist_ok=True)
    H = 360
    pics = [p.resize((int(p.width * H / p.height), H)) for p in pics]
    sheet = Image.new("RGB", (sum(p.width for p in pics) + 10 * len(pics), H), "white")
    x = 0
    for p in pics:
        sheet.paste(p, (x, 0))
        x += p.width + 10
    sheet.save(os.path.join(OUT, unit + ".png"))
    with open(os.path.join(OUT, unit + ".json"), "w") as f:
        json.dump(res, f, indent=1)
    return res


def main(argv):
    if len(argv) >= 2 and argv[0] == "find":
        find(argv[1])
        return 0
    if len(argv) >= 2 and argv[0] == "measure":
        print(json.dumps(measure(argv[1]), indent=1))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
