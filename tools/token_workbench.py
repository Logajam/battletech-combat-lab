"""Combat Lab art: the WORKBENCH (2026-11-04, Claude). A small web server around the faceted builder, so every combination can be set
by hand and looked at (Daniel, 2026-11-04: "a viewer that lets me manually set what blocks are being used. Sliders for tonnage and
mobility, and drop down menus for weapon loadouts with the ability to control which mounts they use. Basically full control over
any combination. Which will let me systematically do testing.").

    python -I tools/token_workbench.py [--port 8765] [--meks <unzipped data/meks.zip folder>]

then open http://localhost:8765 (in a cloud session: the app's preview of that port). The page (tools/token_workbench.html) sends
its settings; the server builds the 'Mech with the real builder (INTEGRATION__shell_facet) and sends back the meshes, the blocks
it used, where every item went, the mounting brackets and, on request, the checks (volume by location against its budget,
floating parts, clipping, blocked muzzles). A published Artifact cannot do this: the builder is Python and a page cannot run it.

A unit is built from scratch (tonnage, walk / jump MP, armor level, engine and cockpit type, arm actuators, items by location) or
loaded from a unit file and then changed. Art tools only: numpy, scipy, trimesh (python-fcl for the checks).
"""
import json
import os
import sys
import tempfile
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

import INTEGRATION__tokens as T
import INTEGRATION__token_mesh as M
import INTEGRATION__shell as SH
import INTEGRATION__shell_items as I
import INTEGRATION__shell_facet as F

ZONES = ("Head", "Center Torso", "Left Torso", "Right Torso", "Left Arm", "Right Arm", "Left Leg", "Right Leg")
SLOTS_N = {"Head": 6, "Left Leg": 6, "Right Leg": 6}
REF = json.load(open(os.path.join(HERE, "..", "data", "token_reference_tags.json"), encoding="utf-8"))
MEKS = None                                   # the unzipped unit library (set from --meks or data/meks.zip at start)


# ------------------------------------------------------------------------------------------------------------ options

def equipment_list():
    """Every item a location can take, for the page's menus: (name, kind, slots, tons, tech)."""
    out = []
    for key, e in I.ENTRIES.items():
        name = e.get("canonical_name") or key
        kind, _fam = I._classify(name, e)
        if kind is None or kind == "structure_slot":
            continue
        out.append({"name": name, "kind": kind, "slots": int(e.get("slots") or 1), "tons": e.get("tonnage"), "tech": e.get("tech_base", "")})
    for extra, kind in (("Heat Sink", "heatsink_single"), ("Double Heat Sink", "heatsink_double"), ("Jump Jet", "jumpjet"), ("CASE", "case")):
        if not any(x["name"] == extra for x in out):
            out.append({"name": extra, "kind": kind, "slots": 3 if extra == "Double Heat Sink" else 1, "tons": None, "tech": "IS"})
    out.sort(key=lambda x: (x["kind"], x["name"]))
    return out


def options():
    units = []
    if MEKS:
        for d, _s, fs in os.walk(MEKS):
            units += [f[:-4] for f in fs if f.endswith(".mtf")]
    return {"blocks": {k: list(v) for k, v in F.BLOCKS.items()}, "head_mounts": ["top", "notch", "built_in", "front"],
            "archetypes": ["humanoid", "bird"], "zones": list(ZONES), "rails": {z: I.rail_count(z) for z in ZONES},
            "equipment": equipment_list(), "units": sorted(set(units)),
            "range": ["Atlas AS7-D", "Mad Cat (Timber Wolf) Prime", "Locust LCT-1V", "Hunchback HBK-4G", "Archer ARC-2R", "JagerMech JM6-S",
                      "UrbanMech UM-R60", "Wendigo (Prime)"]}


# ------------------------------------------------------------------------------------------------------- a unit by hand

def make_unit(cfg):
    """A unit dict like INTEGRATION__tokens.read_unit's, built from the page's settings. Returns (unit, errors)."""
    tons = int(cfg.get("tons", 50))
    walk = int(cfg.get("walk", 5))
    eng = cfg.get("engine", "Fusion")
    cockpit = cfg.get("cockpit", "Standard Cockpit")
    torso_cp = "torso" in cockpit.lower()
    errors = []
    rating = max(10, min(400, tons * walk))
    slots = {}
    # the body's own lines (actuators, engine, gyro, cockpit): what INTEGRATION__shell_items treats as structure
    slots["Head"] = (["Sensors", "Sensors"] if torso_cp else ["Life Support", "Sensors", "Cockpit", "Sensors", "Life Support"])   # one slot free
    ct = ["Fusion Engine"] * 3 + ["Gyro"] * 4 + ([] if eng == "Compact" else ["Fusion Engine"] * 3)
    if torso_cp:
        ct.append("Cockpit")
    slots["Center Torso"] = ct
    side_eng = {"XL": 3, "Light": 2}.get(eng, 0)
    for z in ("Left Torso", "Right Torso"):
        slots[z] = ["Fusion Engine"] * side_eng + (["Life Support"] if torso_cp else [])
    arms = cfg.get("arms") or {}
    for side, z in (("L", "Left Arm"), ("R", "Right Arm")):
        a = arms.get(side) or {}
        lower = a.get("lower", True)
        hand = a.get("hand", True) and lower
        slots[z] = ["Shoulder", "Upper Arm Actuator"] + (["Lower Arm Actuator"] if lower else []) + (["Hand Actuator"] if hand else [])
    for z in ("Left Leg", "Right Leg"):
        slots[z] = ["Hip", "Upper Leg Actuator", "Lower Leg Actuator", "Foot Actuator"]
    # the items, in each location's order (that order is also the index the rail pins use)
    weapons, force, jets_by, jets = [], {}, {}, 0
    idx = {z: 0 for z in ZONES}
    for row in cfg.get("items") or []:
        z, name = row.get("zone"), row.get("name")
        if z not in slots or not name:
            continue
        e = I.lookup(name)
        n = int((e or {}).get("slots") or (3 if name == "Double Heat Sink" else 1))
        slots[z] += [name] * n
        kind, _f = I._classify(name, e)
        if (e or {}).get("category") == "weapon":
            weapons.append({"name": T.clean_weapon_name(name), "zone": z, "rear": bool(row.get("rear")), "count": 1})
        if kind == "jumpjet":
            jets += 1
            jets_by[z] = jets_by.get(z, 0) + 1
        r = row.get("rail", "auto")
        if r not in ("auto", None, ""):
            force.setdefault(z, {})[idx[z]] = int(r)
        idx[z] += 1
    for z in ZONES:
        cap = SLOTS_N.get(z, 12)
        if len(slots[z]) > cap:
            errors.append(f"{z}: {len(slots[z])} critical slots used, it has {cap}")
        slots[z] = slots[z] + ["-Empty-"] * max(0, cap - len(slots[z]))
    pts = I.structure_tons({"tons": tons})                      # just to validate the tonnage against the structure table
    import mech_state
    sp = mech_state.structure_for_tonnage(tons, "biped")
    af = float(cfg.get("armor", 0.8))
    armor_by = {z: int(round(af * (9 if z == "Head" else 2 * sp[z]))) for z in ZONES}
    name = (cfg.get("name") or "Workbench").strip() or "Workbench"
    chassis, _sp, model = name.partition(" ")
    unit = {"chassis": chassis, "model": model, "tons": tons, "config": "Biped", "walk": walk, "jump_mp": int(cfg.get("jump", 0)),
            "engine": f"{rating} {eng if eng != 'Fusion' else ''} Fusion Engine".replace("  ", " "), "cockpit": cockpit,
            "slots": slots, "weapons": weapons, "jets": jets if int(cfg.get("jump", 0)) else 0, "jets_by": jets_by,
            "heat_sinks": 10, "armor_by": armor_by, "armor": sum(armor_by.values()), "armor_type": "Standard",
            "electronics": [], "physical": {}, "force_rails": force}
    _ = pts
    return unit, errors


def unit_to_cfg(path):
    """The page's settings for a unit file, so it can be loaded and then changed."""
    u = T.read_unit(path)
    items = I.parse_items(u)
    rows = []
    for z in ZONES:
        for it in items.get(z, []):
            if it["kind"] == "structure_slot":
                continue
            rows.append({"name": it["name"], "zone": z, "rail": "auto", "rear": it.get("rear", False)})
    eng = u.get("engine", "")
    low = eng.lower()
    caps = {}
    import mech_state
    sp = mech_state.structure_for_tonnage(u["tons"], "biped")
    tot_cap = sum(9 if z == "Head" else 2 * sp[z] for z in ZONES)
    arms = {}
    for side, z in (("L", "Left Arm"), ("R", "Right Arm")):
        s = " ".join(u["slots"].get(z, []))
        arms[side] = {"lower": "Lower Arm Actuator" in s, "hand": "Hand Actuator" in s}
    _ = caps
    return {"name": f'{u.get("chassis", "")} {u.get("model", "")}'.strip(), "tons": u["tons"], "walk": u.get("walk", 4) or 4,
            "jump": u.get("jump_mp", 0), "armor": round(min(1.0, u.get("armor", 0) / max(1, tot_cap)), 2),
            "engine": "XL" if "xl" in low else "Light" if "light" in low else "Compact" if "compact" in low else "Fusion",
            "cockpit": u.get("cockpit") or "Standard Cockpit", "arms": arms, "items": rows, "file": os.path.basename(path)[:-4],
            "use_tags": bool({u.get("chassis", "").lower(), u.get("clanname", "").lower()} & set(REF))}


# ------------------------------------------------------------------------------------------------------------- build

def build(cfg, checks=False):
    unit, errors = make_unit(cfg)
    use_tags = bool(cfg.get("use_tags"))
    m = T.build_model(unit, overrides=REF if use_tags else None, hash_only=not use_tags)
    m.update({"shell": True, "style": "facet", "_unit": unit, "nocap": True})
    if cfg.get("archetype") in ("humanoid", "bird"):
        m["archetype"] = cfg["archetype"]
    if cfg.get("head_mount") in ("top", "notch", "built_in", "front"):
        m["head_mount"] = cfg["head_mount"]
    m["force_blocks"] = {k: v for k, v in (cfg.get("blocks") or {}).items() if v and v != "auto"}
    mesh = M.unit_mesh(m)
    P = m["_shell"]
    placed = []
    for z, lst in P["plan"].items():
        order = {id(it): i for i, it in enumerate(P["items"].get(z, []))}
        for it, r, c in lst:
            placed.append({"zone": z, "index": order.get(id(it), -1), "name": it["name"], "kind": it["kind"], "slots": it["slots"],
                           "visible": it["visible"], "rail": r, "cell": c})
    out = {"mesh": mesh, "blocks": {k: list(v) for k, v in (m.get("blocks") or {}).items()}, "placed": placed,
           "brackets": m.get("_brackets") or {"joints": [], "rails": []}, "errors": errors,
           "budget": {k: round(v, 2) for k, v in P["budget"].items()}, "blocked_muzzles": m.get("blocked_muzzles", 0),
           "height_m": round(6 * m["drawn_levels"], 2)}
    if checks:
        out["checks"] = run_checks(m)
    return out


def run_checks(m):
    """The art checks on this one build: each location's drawn volume against its budget, floating parts, parts below the ground,
    arm / torso and leg / leg clipping, blocked muzzles."""
    res = {}
    parts = M._raw_parts(m, with_src=True)
    by = {}
    for _c, _t, _s, v, _f, loc, role in parts:
        if role not in ("bone", "muscle"):
            by.setdefault(loc, []).append(v)
    res["volume"] = {z: {"drawn": round(M.union_volume(by.get(z, [])) * 216, 2) if by.get(z) else 0.0, "budget": round(b, 2)}
                     for z, b in m["_shell"]["budget"].items()}
    try:
        import token_audit as A
        r = A.audit(m)
        res["floating"] = sum(len(c) for c in r["floating"])
        res["below_ground"] = len(r["ground"])
        res["clip_m"] = round(r["clip"][0] * 6, 3)
        res["clip_between"] = r["clip"][1]
    except Exception as e:                                   # python-fcl missing: say so
        res["audit_error"] = str(e)
    res["blocked_muzzles"] = m.get("blocked_muzzles", 0)
    return res


# ------------------------------------------------------------------------------------------------------------- server

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, separators=(",", ":")).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, open(os.path.join(HERE, "token_workbench.html"), "rb").read(), "text/html; charset=utf-8")
        elif self.path == "/api/options":
            self._send(200, options())
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/api/build":
                self._send(200, build(req.get("cfg") or {}, checks=bool(req.get("checks"))))
            elif self.path == "/api/load":
                name = req.get("unit", "")
                path = None
                for d, _s, fs in os.walk(MEKS or ""):
                    if name + ".mtf" in fs:
                        path = os.path.join(d, name + ".mtf")
                        break
                if not path:
                    self._send(404, {"error": f"no unit file {name}"})
                else:
                    self._send(200, unit_to_cfg(path))
            else:
                self._send(404, {"error": "not found"})
        except Exception as e:
            self._send(500, {"error": str(e), "trace": traceback.format_exc()[-1500:]})


def main(argv):
    global MEKS
    port = int(argv[argv.index("--port") + 1]) if "--port" in argv else 8765
    if "--meks" in argv:
        MEKS = argv[argv.index("--meks") + 1]
    else:                                                  # unzip the library once, beside the system temp files
        import zipfile
        MEKS = os.path.join(tempfile.gettempdir(), "workbench_meks")
        if not os.path.isdir(MEKS):
            zipfile.ZipFile(os.path.join(HERE, "..", "data", "meks.zip")).extractall(MEKS)
    for sub in ("mechsim", "pathfinder"):
        p = os.path.join(HERE, "..", sub)
        if p not in sys.path:
            sys.path.append(p)
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"workbench on http://localhost:{port}  (units from {MEKS})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main(sys.argv[1:])
