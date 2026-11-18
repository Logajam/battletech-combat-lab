#!/usr/bin/env python3
"""Measure a 'Mech's proportions from its AI five-view sheet (T15c step 2; Claude, 2026-11-18).

Daniel, 2026-11-18, after the Catapult: the lessons are to be applied "in a systematic fashion". The Catapult came right only when
it was measured on a grid of its five-view sheet (by eye, about an hour). This tool does the measuring: it takes each view's
outline from the sheet and reads off the landmarks, so a person only confirms the numbers.

    python -I tools/lowpoly_measure.py find "Catapult CPLT-C1"      # number the drawn shapes on the sheet (to pick the views)
    python -I tools/lowpoly_measure.py measure "Catapult CPLT-C1"   # measure the views named in reference_art/views.json
    python -I tools/lowpoly_measure.py compare "Atlas AS7-D"        # THE STANDARD TEST: the HD model measured the same way, v the sheet
    python -I tools/lowpoly_measure.py sections "Atlas AS7-D"       # the sheet and the model cut into the same height bands, one scale

COMPARE (Daniel, 2026-11-18: "measure torso width compared to the drawings ... this should be a standard test"): the HD model's
front and side silhouettes are rendered (the five-view projections) and measured by the SAME code as the sheet, so the two sets of
numbers are like for like; every landmark that differs by more than TOLERANCE is flagged. The arms' pose differs from the sheet's
(a ready pose), so the landmarks the arms touch (overall width, side body length) are reported but not flagged.

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
    # TORSO PROFILE (Daniel, 2026-11-18: "Width in the chest, width in the waist, width of the hips, depth of the back, height of
    # the hips"): the run through the middle, row by row, read in bands between the crotch (c) and the shoulder row (s), as shares of
    # c -> s: HIPS the widest run in 0 .. 0.25 (the thighs' tops and the crotch), BELT the widest in 0.25 .. 0.5, WAIST the narrowest
    # in 0.5 .. 0.9, CHEST the widest in 0.9 .. 1 (with the pads, where they join it); each with its height. Arms that hang apart are
    # separate runs, so only the body is read (the model is measured with its arms hanging as the sheet's: `sheet_pose`).
    prof = {}
    for r in range(int(sr), y + 1):
        for a, b in _runs(sil[r]):
            if a <= mid <= b:
                prof[r] = b - a + 1
    torso_profile = {}

    def band(f0, f1, pick):
        rr = [r for r in prof if y - (y - sr) * f1 <= r <= y - (y - sr) * f0]
        return pick(rr, key=lambda r: prof[r]) if rr else None
    for name, f0, f1, pick in (("hip", 0.0, 0.25, max), ("belt", 0.25, 0.5, max), ("waist", 0.5, 0.9, min), ("chest", 0.9, 1.0, max)):
        r = band(f0, f1, pick)
        if r is not None:
            torso_profile[name + "_width"] = round(prof[r] / h, 3)
            torso_profile[name + "_height"] = round(share(r), 3)
    mid_leg = int(ground - (ground - y) * 0.5)
    leg_runs = _runs(sil[mid_leg])
    feet = _runs(sil[ground - 2])
    return {"height_px": h, "crotch": round(crotch, 3), "shoulder_width": round(sw / h, 3), "shoulder_height": round(share(sr), 3),
            "leg_widths": [round((b - a + 1) / h, 3) for a, b in leg_runs], "leg_count_at_mid": len(leg_runs),
            "feet_width": round(((feet[-1][1] - feet[0][0] + 1) / h) if feet else 0, 3),
            "overall_width": round((cols.max() - cols.min() + 1) / h, 3),
            "torso_width": round(tw / h, 3), "torso_width_height": round(share(tr), 3), **torso_profile,
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
    # BACK DEPTH: how far the back stands behind the leg's axis (the middle of the leg at mid-leg), at the chest (75 % of the height)
    # and at the hips; forward is to the LEFT in a left side view, so the back is the rightmost filled pixel. (The front is not read:
    # the arms stand in front of the chest.)
    ml = int(ground - (ground - cr) * 0.5)
    runs = _runs(sil[ml])
    axis = (runs[0][0] + runs[-1][1]) / 2 if runs else (lc.min() + lc.max()) / 2
    back = {}
    for name, share_ in (("back_depth_chest", 0.75), ("back_depth_hips", crotch_share + 0.08)):
        r = int(ground - share_ * h)
        xs = np.where(sil[r])[0]
        back[name] = round((xs.max() - axis) / h, 3) if len(xs) else 0
    return {"height_px": h, "body_length": round(bl / h, 3), "body_length_height": round((ground - br) / h, 3),
            "leg_reach": round(((lc.max() - lc.min() + 1) / h) if len(lc) else 0, 3), **back,
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


SECTION_BANDS = [("HEAD + COLLAR", 0.76, 1.0), ("SHOULDERS + CHEST", 0.62, 0.82), ("WAIST + SIDE TORSOS", 0.5, 0.66),
                 ("PELVIS + HIPS", 0.36, 0.54), ("THIGHS + KNEES", 0.22, 0.42), ("SHINS", 0.08, 0.28), ("FEET", 0.0, 0.12)]


def sections(unit, H=1100):
    """SECTION BY SECTION (Daniel, 2026-11-18: "compare your version vs the AI drawing section by section, list differences and then
    modify your model based on those differences"; the Catapult's method): the sheet's front and side and the model's (in its `sheet`
    pose) scaled to one standing height and cut into the same height bands, side by side, one row per band, for the list of
    differences. Writes reference_art/measure/<unit> sections.png."""
    import numpy as np
    import lowpoly_blocks as B
    import lowpoly_hd as HD
    from PIL import Image, ImageDraw
    model = json.load(open(os.path.join(HD.HD_DIR, unit + ".json")))
    pose = model.get("poses", {}).get("sheet")
    sol = HD.posed_solids(model, pose) if pose else L.expand_parts(model)
    cube = HD._box_solid(sol)
    V = dict(HD.FIVE_VIEWS)
    spec = json.load(open(VIEWS))[unit]
    sheet = Image.open(sheet_path(unit)).convert("RGB")

    def norm(im):
        g = np.asarray(im.convert("L")) < 245
        rows, cols = np.where(g)
        im = im.crop((cols.min(), rows.min(), cols.max() + 1, rows.max() + 1))
        return im.resize((max(1, int(im.width * H / im.height)), H))
    views = [("sheet front", norm(sheet.crop(tuple(spec["front"])))),
             ("model front", norm(B.render(sol, V["FRONT"], (1400, 1400), fit_solids=cube))),
             ("sheet side", norm(sheet.crop(tuple(spec["side"])))),
             ("model side", norm(B.render(sol, V["LEFT SIDE"], (1400, 1400), fit_solids=cube)))]
    rows = []
    for name, f0, f1 in SECTION_BANDS:
        ims = [(k, im.crop((0, int(H * (1 - f1)), im.width, int(H * (1 - f0))))) for k, im in views]
        r = Image.new("RGB", (sum(i.width for _, i in ims) + 120, max(i.height for _, i in ims) + 22), "white")
        d = ImageDraw.Draw(r)
        x = 0
        for k, i in ims:
            r.paste(i, (x, 22))
            d.text((x + 4, 4), name + " - " + k, fill="black")
            x += i.width + 30
        rows.append(r)
    out = Image.new("RGB", (max(r.width for r in rows), sum(r.height + 14 for r in rows)), "white")
    y = 0
    for r in rows:
        out.paste(r, (0, y))
        y += r.height + 14
    path = os.path.join(OUT, unit + " sections.png")
    out.save(path)
    return path


TOLERANCE = 0.06                        # a landmark more than 6 % off the sheet's is flagged
ARM_TOUCHED = ("overall_width", "body_length", "body_length_height")


def model_silhouettes(unit, px=760):
    """The HD model's FRONT and LEFT SIDE silhouettes as masks (True = the model), in the five-view projections, in the model's
    `sheet` pose when it has one (its arms hanging as the sheet's, so arm-touched landmarks compare like for like)."""
    import numpy as np
    import lowpoly_blocks as B
    import lowpoly_hd as HD
    model = json.load(open(os.path.join(HD.HD_DIR, unit + ".json")))
    pose = model.get("poses", {}).get("sheet")
    sol = HD.posed_solids(model, pose) if pose else L.expand_parts(model)
    cube = HD._box_solid(sol)
    views = dict(HD.FIVE_VIEWS)
    out = {}
    for k, name in (("front", "FRONT"), ("side", "LEFT SIDE")):
        im = B.render(sol, views[name], (px, px), fit_solids=cube).convert("L")
        a = np.asarray(im) < 250
        rows, cols = np.where(a)
        out[k] = a[rows.min():rows.max() + 1, cols.min():cols.max() + 1]
    return out


def compare(unit):
    """The standard test: the model's landmarks v the sheet's (both as shares of their own standing height)."""
    from PIL import Image, ImageDraw
    import numpy as np
    sheet = json.load(open(os.path.join(OUT, unit + ".json")))
    sil = model_silhouettes(unit)
    mod = {"front": measure_front(sil["front"])}
    mod["side"] = measure_side(sil["side"], mod["front"]["crotch"])
    rows, flags = [], []
    for view in ("front", "side"):
        for k, v in sheet.get(view, {}).items():
            if k.startswith("_") or k in ("height_px", "leg_count_at_mid") or k not in mod[view]:
                continue
            a, b = v, mod[view][k]
            if isinstance(a, list):
                a, b = (sum(a) / len(a) if a else 0), (sum(b) / len(b) if b else 0)
                k = k + " (mean)"
            diff = (b - a) / a if a else 0.0
            flag = abs(diff) > TOLERANCE and k not in ARM_TOUCHED
            rows.append((view, k, float(a), float(b), float(diff), bool(flag)))
            if flag:
                flags.append("%s %s: model %.3f v sheet %.3f (%+.0f %%)" % (view, k, b, a, diff * 100))
    res = {"unit": unit, "tolerance": TOLERANCE, "flags": flags,
           "rows": [{"view": v, "landmark": k, "sheet": round(a, 3), "model": round(b, 3), "diff_pct": round(d * 100, 1),
                     "flag": f} for v, k, a, b, d, f in rows]}
    with open(os.path.join(OUT, unit + " compare.json"), "w") as f:
        json.dump(res, f, indent=1)
    # the picture: the sheet's silhouette and the model's side by side, each at its own standing height, landmark lines on both
    spec = json.load(open(VIEWS))[unit]
    img = Image.open(sheet_path(unit)).convert("RGB")
    H = 420
    pics = []
    for view in ("front", "side"):
        for src, m_ in (("sheet", _mask(img.crop(tuple(spec[view])))), ("model", sil[view])):
            rws = np.where(m_.any(1))[0]
            m_ = m_[rws.min():rws.max() + 1]
            im = Image.fromarray(np.where(m_, 150 if src == "sheet" else 90, 255).astype("uint8")).convert("RGB")
            im = im.resize((max(1, int(im.width * H / im.height)), H))
            d = ImageDraw.Draw(im)
            d.text((4, 4), "%s %s" % (src, view), fill=(200, 0, 0))
            pics.append(im)
    W = sum(p.width for p in pics) + 12 * len(pics)
    out = Image.new("RGB", (max(W, 900), H + 22 + 16 * (len(rows) + 1)), "white")
    x = 0
    for p in pics:
        out.paste(p, (x, 0))
        x += p.width + 12
    d = ImageDraw.Draw(out)
    d.text((6, H + 6), "%-6s %-26s %8s %8s %8s" % ("view", "landmark (share of height)", "sheet", "model", "diff"), fill="black")
    for i, (v, k, a, b, dd, f) in enumerate(rows):
        d.text((6, H + 22 + 16 * i), "%-6s %-26s %8.3f %8.3f %+7.0f%%%s" % (v, k, a, b, dd * 100, "   <-- OFF" if f else ""),
               fill="red" if f else "black")
    out.save(os.path.join(OUT, unit + " compare.png"))
    return res


def main(argv):
    if len(argv) >= 2 and argv[0] == "find":
        find(argv[1])
        return 0
    if len(argv) >= 2 and argv[0] == "sections":
        print("wrote", os.path.relpath(sections(argv[1]), L.ROOT))
        return 0
    if len(argv) >= 2 and argv[0] == "compare":
        res = compare(argv[1])
        for r in res["rows"]:
            print("%-6s %-26s sheet %.3f  model %.3f  %+6.1f %%%s" % (r["view"], r["landmark"], r["sheet"], r["model"], r["diff_pct"],
                                                                     "   <-- OFF" if r["flag"] else ""))
        print("%d landmark(s) off by more than %d %%" % (len(res["flags"]), TOLERANCE * 100))
        return 1 if res["flags"] else 0
    if len(argv) >= 2 and argv[0] == "measure":
        print(json.dumps(measure(argv[1]), indent=1))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
