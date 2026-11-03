"""Build the Combat Lab token contact sheet (HTML) from a few unit files.
Usage: python -I tools/token_sheet.py <unzipped data/meks.zip folder> <out.html>
Units are looked up by file name anywhere under the folder."""
import html
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import INTEGRATION__tokens as T

UNITS = ["Flea FLE-4", "Locust LCT-1V", "Commando COM-2D", "Jenner JR7-D", "Raven RVN-3L",
         "Griffin GRF-1N", "Shadow Hawk SHD-2H", "Wolverine WVR-6R", "Hunchback HBK-4G", "Centurion CN9-A",
         "Orion ON1-K", "Warhammer WHM-6R", "Marauder MAD-3R", "Thunderbolt TDR-5S", "Catapult CPLT-C1",
         "Dragon DRG-1N", "Mad Cat (Timber Wolf) Prime", "Awesome AWS-8Q", "Zeus ZEU-6S", "Stalker STK-3F",
         "Banshee BNC-3E", "Cyclops CP-10-Z", "Atlas AS7-D", "King Crab KGC-000", "Scorpion SCP-1N",
         "Ares ARS-V1 Hephaestus"]


def find(root, name):
    for d, _, fs in os.walk(root):
        if name + ".mtf" in fs:
            return os.path.join(d, name + ".mtf")
    return None


def find_chassis(root, chassis):
    """The shortest-named file of a chassis (a model code with a digit follows its name)."""
    import re
    pat = re.compile(r"^" + re.escape(chassis) + r" [A-Za-z0-9\-]*\d[A-Za-z0-9\-]*\.mtf$", re.I)
    best = None
    for d, _, fs in os.walk(root):
        for f in fs:
            if pat.match(f) and (best is None or len(f) < len(os.path.basename(best))):
                best = os.path.join(d, f)
    return best


def main(root, out):
    ref = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "token_reference_tags.json"), encoding="utf-8"))
    paths, missing = [], []
    for n in UNITS:
        p = find(root, n)
        (paths if p else missing).append(p or n)
    for chassis in ref:                                          # every chart unit not already listed
        p = find_chassis(root, chassis)
        if not p:
            missing.append(chassis)
        elif p not in paths:
            paths.append(p)
    pairs = []                                                   # (with reference tags + overrides, name hash only)
    for p in paths:
        u = T.read_unit(p)
        pairs.append((T.build_model(u, overrides=ref), T.build_model(u, hash_only=True)))
    pairs.sort(key=lambda mm: mm[0]["tons"])
    models = [a for a, _ in pairs]
    lineup = lineup_svg(models)
    tiles = []
    for m, h in pairs:
        def tagline(x):
            hp = {}
            for g in x["hardpoints"]:
                hp[g["mount"]] = hp.get(g["mount"], 0) + g["count"]
            t = [x["archetype"], f"torso {x['torso']}/{x['panels']}", f"head {x['head_mount']}/{x['head_shape']}", f"shoulders {x['shoulders']}", f"plan {x['plan']}", f"profile {x['profile']}", f"hips {x['hips']}"]
            if x["arms"]:
                t.append("arms " + "/".join(x["arms"][c] for c in "LR"))
            t += [f"{k.replace('_', ' ')} x{v}" for k, v in sorted(hp.items())]
            return " · ".join(html.escape(i) for i in t)
        tiles.append(f"""<article class="tile"><header><h3>{html.escape(m['name'])}</h3>
<p class="meta"><span>{m['tons']} t</span><span>{m['config']}</span><span>rules {m['rules_levels']} lv</span><span>drawn {m['drawn_levels']:.2f} lv</span></p></header>
<p class="rowlab">Reference tags applied{' (' + ', '.join(m['overridden']) + ')' if m['overridden'] else ': none for this unit'}</p>
<div class="views">{T.top_svg(m)}{T.card_svg(m)}{T.rear_svg(m)}{T.side_svg(m)}</div>
<p class="tags">{tagline(m)}</p>
<p class="rowlab">Name hash only</p>
<div class="views">{T.top_svg(h)}{T.card_svg(h)}{T.rear_svg(h)}{T.side_svg(h)}</div>
<p class="tags">{tagline(h)}</p></article>""")
    page = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "token_sheet_template.html"), encoding="utf-8").read()
    page = page.replace("__LINEUP__", lineup).replace("__TILES__", "\n".join(tiles)).replace("__N__", str(len(models)))
    open(out, "w", encoding="utf-8").write(page)
    print(len(models), "units; missing:", missing)


def lineup_svg(models):
    step, L = 92, T.LEVEL
    w = step * len(models) + 40
    h = 3 * L + 40
    out = [f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" class="lineup" role="img" aria-label="All units at one scale">']
    for lv in (1, 2, 3):
        y = h - 24 - lv * L
        out.append(f'<line x1="26" x2="{w}" y1="{y}" y2="{y}" class="lvl"/><text x="2" y="{y + 4}" class="lab">{lv}</text>')
    for i, m in enumerate(models):
        x = 40 + i * step + step / 2
        out.append(f'<g transform="translate({x},{h - 24})">'
                   f'<rect x="{-20 * m["rules_levels"]}" y="{-m["rules_levels"] * L}" width="{40 * m["rules_levels"]}" height="{m["rules_levels"] * L}" class="card"/>'
                   f'{T.lineup_figure(m, m["drawn_levels"] * L)}'
                   f'<text y="14" text-anchor="middle" class="lab">{m["tons"]}t</text></g>')
    out.append("</svg>")
    return "".join(out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
