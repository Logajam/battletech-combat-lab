"""
INTEGRATION__replay.py  (NEW 2026-10-20, Claude - Pile 1, output only)

Battle replays: a battle recorded step by step and written as one
self-contained HTML page (INTEGRATION__replay_viewer.html with the battle's
data inside) - a hex map you step through, both mechs' armor / structure per
location, heat and status, and the log text of each step. Daniel: "build
outputs both text and visual you can share from battles you run so I can see
whats going on without me having to download the current version and run it
myself." Open the file in any browser; Claude can also publish one as a link.

    config.REPLAY_BATTLES = 3        # record battles 1-3 of the next run
    config.REPLAY_DIR = "replays"    # where the pages go (under the repo)

A step is one point in the turn (INTEGRATION__orchestrator.run_battle calls
mark()): deployment, each mech's movement, ranged attacks, physical attacks,
then heat and the end phase. Each step holds both mechs' state at that moment
and every log line written since the previous step (config.log sends a copy
here while recording, VERBOSE or not).

Recording changes nothing in the battle: it only reads the mechs and copies
the log, so a recorded battle plays out exactly like an unrecorded one.
"""

import html
import json
import os
import re

import INTEGRATION__config as config
import INTEGRATION__arcs as arcs
from INTEGRATION__attack_resolution import total_hp
from mech_state import is_destroyed

VIEWER_TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "INTEGRATION__replay_viewer.html")
DATA_PLACEHOLDER = "__REPLAY_JSON__"

# The recording in progress in this process (one battle at a time per process;
# parallel batches record in each worker).
_active = None


class _Recording:
    def __init__(self, units, terrain_map, seed, sim):
        self.mechs = {m.side_name: m for m in units}
        self.lines = []
        self.steps = []
        self.data = {
            "sim": sim,
            "seed": None if seed is None else str(seed),   # text: seeds pass JavaScript's exact-integer limit
            "mechs": {side: _mech_header(m) for side, m in self.mechs.items()},
            "board": _board(terrain_map),
            "steps": self.steps,
        }

    def log(self, msg):
        """config.log's copy of each line, kept for the step in progress."""
        self.lines.append(msg)

    def mark(self, turn, phase):
        self.steps.append({
            "turn": turn,
            "phase": phase,
            "state": {side: _mech_state(m) for side, m in self.mechs.items()},
            "log": self.lines,
        })
        self.lines = []


def start(units, terrain_map, seed, sim):
    """Begin recording a battle (call before run_skirmish); `units` are its
    mechs, each shown under its label (side_name)."""
    global _active
    _active = _Recording(units, terrain_map, seed, sim)
    config.set_log_sink(_active.log)


def mark(turn, phase):
    """Close the current step (no-op when nothing is recording)."""
    if _active is not None:
        _active.mark(turn, phase)


def finish(result):
    """Stop recording and return the battle's replay data (a dict)."""
    global _active
    rec, _active = _active, None
    config.set_log_sink(None)
    if rec is None:
        return None
    if rec.lines:
        rec.mark(result.turns_taken, "Battle over")
    rec.data["result"] = {
        "winner": result.winner,
        "turns": result.turns_taken,
        "causes": {label: stats.cause_of_death for label, stats in result.units.items()},
    }
    return rec.data


def _mech_header(m):
    return {
        "name": f"{m.chassis} {m.model}".strip(),
        "bot": getattr(m, "bot", "gladiator"),          # which bot drove it (INTEGRATION__bots, 2026-10-27)
        "tons": m.mass,
        "max_hp": total_hp(m),
        "locations": list(m.locations),
        "max": {loc: [m.max_armor.get(loc, 0), m.max_rear_armor.get(loc, 0), m.max_structure.get(loc, 0)]
                for loc in m.locations},
    }


def _mech_state(m):
    return {
        "hex": m.hex,
        "facing": m.facing,
        "twist": arcs.current_action(m).twist,
        "prone": bool(getattr(m, "prone", False)),
        "shutdown": bool(getattr(m, "shutdown", False)),
        "destroyed": bool(is_destroyed(m)),
        "heat": getattr(m, "current_heat", 0),
        "hp": total_hp(m),
        "pilot_hits": getattr(m, "pilot_hits", 0),
        "locs": {loc: [v.get("armor", 0), v.get("rear_armor", 0), v.get("structure", 0), bool(v.get("destroyed"))]
                 for loc, v in m.locations.items()},
    }


def _board(terrain_map):
    """Width, height and each hex's level and terrain features."""
    hexes = {}
    for label, info in terrain_map["hexes"].items():
        feats = {k: v[0] if isinstance(v, list) and v else v for k, v in info.get("features", {}).items()
                 if k != "foliage_elev"}
        # A water hex's "level" is its floor (terrain_rules.prepare_board); the map shows the surface.
        hexes[label] = {"l": info.get("surface_level", info.get("level", 0)), "f": feats}
        if info.get("building"):
            hexes[label]["b"] = 1          # a passive building: "l" is its roof level
    return {"width": terrain_map["width"], "height": terrain_map["height"], "hexes": hexes}


# =============================================================================
# ==========================  WRITING THE PAGE  ===============================
# =============================================================================
def file_name(data):
    red, blue = data["mechs"]["Red"]["name"], data["mechs"]["Blue"]["name"]
    stem = f"{red}_vs_{blue}_battle{data['sim']}_seed{data['seed']}"
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", stem) + ".html"


def render(data):
    """The viewer page with this battle's data inside it."""
    with open(VIEWER_TEMPLATE, encoding="utf-8") as f:
        page = f.read()
    # "</" would end the <script> holding the data early.
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    title = html.escape(f"{data['mechs']['Red']['name']} vs {data['mechs']['Blue']['name']}, battle {data['sim']}")
    page = page.replace("<title>Battle Replay</title>", f"<title>{title}</title>", 1)
    return page.replace(DATA_PLACEHOLDER, payload, 1)


def write(data, directory=None):
    """Write one replay page; returns its path."""
    directory = directory or config.REPLAY_DIR
    if not os.path.isabs(directory):            # relative = under the repo root
        directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), directory)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, file_name(data))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(render(data))
    return path
