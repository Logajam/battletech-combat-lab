"""
tests/test_peril.py - checks the visibility table and the Peril field (2026-11-07, INTEGRATION__vision / _peril;
Daniel's peril heat map design, PROJECT_MAP Pick up here 000000).

    python tests/test_peril.py
"""
import io
import os
import random
import sys
import traceback
from contextlib import redirect_stdout, redirect_stderr

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tests"))
os.chdir(REPO_ROOT)

import numpy as np  # noqa: E402
import INTEGRATION__config as config  # noqa: E402
config.STATS = False
import INTEGRATION__los_cache as los_cache  # noqa: E402
import INTEGRATION__future_damage as future_damage  # noqa: E402
import INTEGRATION__peril as peril  # noqa: E402
import INTEGRATION__vision as vision  # noqa: E402
import hex_geometry  # noqa: E402
from test_multi_unit import fresh, TERRAIN, ATLAS, COMMANDO  # noqa: E402
from test_heat import ScriptedDice  # noqa: E402

config.VERBOSE = False
CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


@check
def the_table_agrees_with_the_line_of_sight_code_pair_by_pair():
    vt = vision.table(TERRAIN)
    assert vision.table(TERRAIN) is vt                                  # built once, remembered
    rng, n = random.Random(7), len(vt.hexes)
    for _ in range(300):
        i, j = rng.randrange(n), rng.randrange(n)
        if i == j:
            continue
        res, _, dist, _ = los_cache.pair_info(vt.hexes[i], vt.hexes[j], TERRAIN)
        assert bool(vt.seen[i, j]) == res.los and vt.dist[i, j] == dist
        if res.los:
            assert vt.mod[i, j] == max(0, min(vision.MOD_CLASSES - 1, res.modifier))
    assert vt.seen.diagonal().all()
    assert 0 <= vt.mod.min() and vt.mod.max() < vision.MOD_CLASSES


@check
def line_of_sight_itself_is_symmetric():
    assert vision.asymmetric_sample.__doc__
    vt = vision.table(TERRAIN)
    assert (vt.seen == vt.seen.T).all()


@check
def a_unit_that_stands_on_one_spot_gives_exactly_its_range_profile_where_it_sees():
    a = fresh(ATLAS, "0808", "N", "A 1", "A")
    t = fresh(COMMANDO, "0812", "S", "B 1", "B")
    vt = vision.table(TERRAIN)
    spot = hex_geometry.parse_hex_label("0808")
    f = peril.unit_field(a, t, TERRAIN, spots=[spot], vt=vt)
    base = future_damage.range_profile(a, t)
    i = vt.index[spot]
    checked = 0
    for j, h in enumerate(vt.hexes):
        d = int(vt.dist[i, j])
        if vt.seen[i, j] and vt.mod[i, j] == 0 and d < len(base):
            assert abs(f.peak[j] - base[d]) < 1e-9 and abs(f.mean[j] - base[d]) < 1e-9, (h, d)
            checked += 1
        if not vt.seen[i, j]:
            assert f.peak[j] == 0.0
        if d >= len(base):
            assert f.peak[j] == 0.0                                        # out of every weapon's range
    assert checked > 10


@check
def peak_is_never_below_mean_and_more_spots_never_lower_the_peak():
    a = fresh(COMMANDO, "0808", "N", "A 1", "A")
    t = fresh(ATLAS, "0812", "S", "B 1", "B")
    vt = vision.table(TERRAIN)
    one = peril.unit_field(a, t, TERRAIN, spots=[hex_geometry.parse_hex_label("0808")], vt=vt)
    full = peril.unit_field(a, t, TERRAIN, vt=vt)
    assert (full.peak >= full.mean - 1e-12).all()
    assert (full.peak >= one.peak - 1e-12).all()
    assert full.peak.max() > 0


@check
def a_unit_that_cannot_fire_and_a_team_sum():
    a = fresh(COMMANDO, "0808", "N", "A 1", "A")
    b = fresh(COMMANDO, "0408", "N", "A 2", "A")
    t = fresh(ATLAS, "0812", "S", "B 1", "B")
    vt = vision.table(TERRAIN)
    a.shutdown = True
    assert peril.unit_field(a, t, TERRAIN, vt=vt).peak.max() == 0.0
    a.shutdown = False
    fa, fb = peril.unit_field(a, t, TERRAIN, vt=vt), peril.unit_field(b, t, TERRAIN, vt=vt)
    both = peril.team_field([a, b], t, TERRAIN, vt=vt)
    assert np.allclose(both.peak, fa.peak + fb.peak) and np.allclose(both.mean, fa.mean + fb.mean)


def run_all():
    failed = 0
    for fn in CHECKS:
        try:
            with ScriptedDice([], default=7), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                fn()
            print(f"PASS  {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print()
    if failed:
        print(f"{failed} of {len(CHECKS)} peril checks FAILED.")
        sys.exit(1)
    print(f"All {len(CHECKS)} peril checks passed.")


if __name__ == "__main__":
    run_all()
