"""
tests/test_token_volume.py - the Combat Lab art follows the scaling law: equal mass, equal volume
(Daniel, 2026-11-03: two 'Mechs of one mass looked different in volume).

    python tests/test_token_volume.py

Each generated 'Mech's body volume (every part but weapons, the union of the convex solids on a grid) must equal
INTEGRATION__token_mesh.DENSITY x tonnage, within 8 percent; and its drawn height must be the rules curve
(2 x (tons/100)^(1/3) levels, 3 x (tons/200)^(1/3) for a superheavy). Needs numpy, scipy and trimesh (art tools);
without them the check says so and passes. Uses the unit files in data/meks.zip.
"""

import io
import os
import sys
import zipfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

try:
    import numpy  # noqa: F401
    import scipy  # noqa: F401
    import trimesh  # noqa: F401
    HAVE = True
except ImportError:
    HAVE = False

UNITS = ["Flea FLE-4", "Locust LCT-1V", "Awesome AWS-8Q", "Victor VTR-9B", "Atlas AS7-D", "King Crab KGC-000", "Urbanmech UM-R60"]


def main():
    if not HAVE:
        print("PASS  numpy / scipy / trimesh not installed: token volume check skipped (art tools only)")
        return 0
    import tempfile
    import INTEGRATION__tokens as T
    import INTEGRATION__token_mesh as M
    z = zipfile.ZipFile(os.path.join(REPO_ROOT, "data", "meks.zip"))
    names = {os.path.basename(n).lower(): n for n in z.namelist() if n.lower().endswith(".mtf")}
    bad, seen = [], 0
    for u in UNITS:
        key = (u + ".mtf").lower()
        if key not in names:
            continue
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, os.path.basename(names[key]))
            open(path, "wb").write(z.read(names[key]))
            model = T.build_model(T.read_unit(path))
        M.calibrate(model)
        vol = M.body_volume(model)
        want = M.DENSITY * model["tons"]
        parts = M._raw_parts(model)
        import numpy as np
        height = np.vstack([v for _, v, _f, _t in parts])[:, 1].max()
        seen += 1
        if abs(vol / want - 1) > 0.08:
            bad.append(f"{u}: volume {vol:.3f} v {want:.3f}")
        if abs(height / model["drawn_levels"] - 1) > 0.06:
            bad.append(f"{u}: height {height:.2f} v rules curve {model['drawn_levels']:.2f}")
    if bad or not seen:
        print("FAIL  " + ("; ".join(bad) or "no unit files found"))
        return 1
    print(f"PASS  {seen} units: body volume = density x tons (within 8 percent) and height on the rules curve")
    return 0


if __name__ == "__main__":
    sys.exit(main())
