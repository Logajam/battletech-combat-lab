"""
tools/make_options_registry.py - the Combat Lab's Options tab list (CL15), generated rather than typed twice.

    python tools/make_options_registry.py            # writes engine/lab/web/options.json

Reads every setting of engine/defaults/config.json, takes its words from the comment block above it in
INTEGRATION__config.py (our own wording; the Python file is the frozen answer key and keeps the comments), puts it in a
folder (Game setup > rules / deployment / placeholders / technical, or Bot features > one folder per bot), and marks it
ACTIVE when the Rust engine reads that setting by name. A setting the Rust engine never reads is listed but greyed out
with a "not active yet" tag (Daniel, 2026-11-14). Settings the Lab sets itself (seed, turn cap, board, teams...) are
left out. Run it again after settings are added, then rebuild
combatlab: options.json is built into the program.
"""
import glob
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULTS = os.path.join(ROOT, "engine", "defaults", "config.json")
PYCONFIG = os.path.join(ROOT, "INTEGRATION__config.py")
OUT = os.path.join(ROOT, "engine", "lab", "web", "options.json")

# set by the Lab's own pages, per team, or internal: never listed
LEFT_OUT = {"MECHSIM_DIR", "DATA_DIR", "NUM_SIMULATIONS", "MAX_TURNS", "SEED", "WORKERS", "DEFAULT_BOARD_PATH", "STITCH_MAPS",
            "STITCH_BOARDS", "STITCH_GRID_COLS", "STITCH_GRID_ROWS", "PROMPT_FOR_MAP", "DEPLOYMENT", "FORCES", "FORCE_DEFAULTS",
            "MECH_RED_MTF", "MECH_BLUE_MTF", "MECH_RED_CONFIG", "MECH_BLUE_CONFIG", "MTF_FILETYPES", "BOT", "PILOTING",
            "CLUSTER_HITS_TABLE", "CLUSTER_HITS_TABLE_COLUMNS", "_HERE"}
TECHNICAL = ("VERBOSE", "MANUAL_ROLLS", "TIMING", "PROFILE_FUNCTIONS", "FASTCORE", "USE_FASTCORE", "WEAPONS_CACHE_VERIFY",
             "FIRE_TABLE_VERIFY", "SAVE_STATE", "REPLAY", "STATS", "RENDER", "HEATMAP", "GENERATE_", "LETHALITY", "SAVE_RUN_STATS")
RULES = {"CHARGES", "DFA", "CLUB_PICKUP", "POOL_CLUSTER_DAMAGE", "FLOATING_CRITICALS", "FIGHT_TO_THE_DEATH", "PASSIVE_BUILDINGS",
         "AIMED_SHOT_LOCATION", "DOMINO_DODGE", "ESCALATING_CYCLE_ON_ODD_TURNS", "TSM_MIN_HEAT", "AMS_HEAT_LIMIT", "USE_TMM"}
GLADIATOR = ("MOVEMENT_", "KILL_CURVE", "PERIL", "STACK", "TRIAGE", "MOVE_ORDER", "GLADIATOR_", "STUB_GLADIATOR_TARGET",
             "FOE_CHOICE", "TARGET_HEAT_WORTH", "TASER_EFFECT_WORTH", "TSEMP_EFFECT_WORTH", "IMP_EFFECT_WORTH")


# Typed-in settings that take one of a few words (Daniel, 2026-11-20: "any options that want you to type in something ... should
# be drop down menus"). Each list is what the Rust engine ACCEPTS today (read from its match arms / asserts, 2026-11-20): a word the
# Python config knows but the engine rejects ("if_then", "tiered", "kill_curve") is left out, so the menu never offers a crash.
# A setting listed here with one word has only one working value so far. [value, label] pairs; None value = JSON null.
CHOICES = {
    "HOME_EDGE_CHOICE": [["random", "Random"], ["N", "North"], ["E", "East"], ["S", "South"], ["W", "West"]],
    "STUB_BLUE_SHIELD": [["on", "On"], ["off", "Off"]],
    "STUB_CAPACITOR_CHARGE": [["never", "Never"], ["when_idle", "When the PPC isn't fired"]],
    "STUB_CAPACITOR_START": [["empty", "Empty"], ["charged", "Charged"]],
    "STUB_CONSOLE_SWAP": [["when_needed", "When needed"], ["never", "Never"]],
    "STUB_ESCALATING_USE": [["cycle", "1 turn on, 1 turn off"], ["always", "Always"], ["never", "Never"]],
    "STUB_FIRE_TAG": [["when_useful", "When useful"], ["always", "Always"], ["never", "Never"]],
    "STUB_MUNITION_POLICY": [["greedy", "Most expected damage"], ["standard", "Standard ammunition"], ["random", "Random"]],
    "STUB_RAISE_SHIELD": [["never", "Never"], ["always", "Always"]],
    "STUB_RATE_OF_FIRE": [["max", "Maximum shots"], ["single", "One shot"], ["greedy", "Most expected damage"]],
    "STUB_TAG_AIM": [["mech", "The 'Mech"], ["hex", "The hex"], ["easier", "The easier target number"]],
    "STUB_UNKNOWN_DAMAGE_TYPE": [["BALLISTIC", "Ballistic"], ["ENERGY", "Energy"], ["MISSILE", "Missile"], ["AREA_EFFECT", "Area effect"],
                                 ["PHYSICAL", "Physical"], ["REENGINEERED", "Reengineered"]],
    "STUB_VIBROBLADE": [["on", "On"], ["off", "Off"]],
    "AIMED_SHOT_LOCATION": [[None, "None (no aimed shots)"], ["Head", "Head"], ["Center Torso", "Center Torso"], ["Left Torso", "Left Torso"],
                            ["Right Torso", "Right Torso"], ["Left Arm", "Left Arm"], ["Right Arm", "Right Arm"], ["Left Leg", "Left Leg"],
                            ["Right Leg", "Right Leg"]],
    "FOE_CHOICE": [["nearest", "Nearest enemy"]],
    "GLADIATOR_FIRE_ORDER": [["big_guns_first", "Big guns first"], ["roster", "Roster order"]],
    "MOVEMENT_ASSUMED_ENEMY_SEARCH": [["short_list", "Short list"], ["grid", "Grid"]],
    "MOVEMENT_GRID_SPIN": [["clockwise", "Clockwise"], ["counterclockwise", "Counter-clockwise"]],
    "MOVEMENT_LIFETIME_ATTACKER_MODE": [["Stand Still", "Stand still"], ["Walk", "Walk"], ["Run", "Run"], ["Jump", "Jump"]],
    "MOVEMENT_OBJECTIVE": [["lifetime", "Lifetime"], ["ratio", "Ratio"]],
    "MOVEMENT_SEARCH": [["grid", "Short Grid"], ["short_list", "Short list"]],
    "MOVE_ORDER": [["index", "List order"]],
    "PERIL": [["off", "Off"]],
    "STUB_GLADIATOR_TARGET": [["princess_plan", "Princess's firing plan"], ["nearest", "Nearest"]],
    "LEGATE_FIRE_SPLIT": [["proportional", "Proportional"], ["none", "None"]],
    "PRINCESS_VERSION": [["modern", "Modern (MegaMek main)"]],
}


def folder(key):
    """(top tab, folder) of a setting."""
    if key.startswith("PRINCESS_"):
        return "Bot features", "Princess"
    if key == "LEGATE" or key.startswith("LEGATE_"):
        return "Bot features", "Legate"
    if key.startswith("HYDRA_"):
        return "Bot features", "Hydra"
    if key.startswith(GLADIATOR):
        return "Bot features", "Gladiator"
    if key in RULES:
        return "Game setup", "Rules"
    if key.startswith("STUB_"):
        return "Game setup", "Placeholders (stubs)"
    if key in ("HOME_EDGE_CHOICE", "DEPLOYMENT_DEPTH", "DEPLOYMENT_STUCK_DEPTH", "DEPLOYMENT_PLACED"):
        return "Game setup", "Deployment"
    if key.startswith(TECHNICAL):
        return "Game setup", "Technical and debugging"
    return "Game setup", "Other"


def comments():
    """setting name -> the comment block above it (or its end-of-line comment)."""
    lines = open(PYCONFIG, encoding="utf-8").read().split("\n")
    out, block = {}, []
    for line in lines:
        s = line.strip()
        if s.startswith("#"):
            text = s.lstrip("#").strip()
            if set(text) <= set("= ") or text.isupper() or re.match(r"^=+\s", text):
                block = []          # a section banner, not a description
            else:
                block.append(text)
            continue
        m = re.match(r"^([A-Z][A-Z0-9_]*)\s*=", line)
        if m:
            inline = line.split("  #", 1)[1].strip() if "  #" in line else ""
            out[m.group(1)] = " ".join(block) or inline
        if s == "" and block and not m:
            pass                      # a blank line inside a block keeps it
        elif not s.startswith("#"):
            block = [] if m else block
    return out


# where the comment above a setting is shared with its neighbour, the words are given here instead
OVERRIDES = {
    "PRINCESS_VERSION": "Which Princess plays: 'modern' (MegaMek main as of 2026-10-26) or '0.50.07' (the classic ranker first cloned).",
    "PRINCESS_BEHAVIOR": "Princess's behavior sliders (MegaMek BehaviorSettings, each 0-10); 5 is MegaMek's default behavior.",
}


def humanise(key):
    words = key.lower().split("_")
    return " ".join([words[0].capitalize()] + words[1:])


def short(text):
    text = re.sub(r"\s+", " ", text).strip()
    cut = re.search(r"(?<=[.!?])\s", text)
    first = text[: cut.start()] if cut and cut.start() > 20 else text
    return first if len(first) <= 200 else first[:197].rstrip() + "..."


def main():
    defaults = json.load(open(DEFAULTS, encoding="utf-8"))
    src = "".join(open(f, encoding="utf-8").read() for f in glob.glob(os.path.join(ROOT, "engine", "**", "*.rs"), recursive=True)
                  if "/target/" not in f)
    words = comments()
    registry = []
    for key, value in defaults.items():
        if key in LEFT_OUT or key.startswith("_"):
            continue
        kind = "bool" if isinstance(value, bool) else "int" if isinstance(value, int) else "number" if isinstance(value, float) else \
            "text" if isinstance(value, str) else "json"
        top, sub = folder(key)
        text = OVERRIDES.get(key) or words.get(key, "")
        registry.append({"key": key, "label": humanise(key), "top": top, "folder": sub, "kind": kind, "default": value,
                         "short": short(text) if text else "", "text": text, "active": f'"{key}"' in src})
        if key in CHOICES:
            registry[-1]["choices"] = CHOICES[key]
    # Hydra's switches are Rust constants (INTEGRATION__HYDRA.md; PROJECT_MAP Section 0 REVIEW QUEUE ab-ad), not settings the
    # Lab can send yet: listed so the folder is there, greyed out
    for key, text in (("HYDRA_MOVE_ORDER", "Which unit Hydra moves next: 'stake' orders by what each unit has riding on its move (off by default)."),
                      ("HYDRA_WAITING", "Hydra holds a unit back while friends are coming (off by default)."),
                      ("HYDRA_ATTENTION", "Hydra prices the damage it would draw elsewhere with the Exchange Oracle (off by default)."),
                      ("HYDRA_LIFE_STRUCTURE_WEIGHT", "How much structure counts, against armor, in what a unit has left to lose.")):
        registry.append({"key": key, "label": humanise(key), "top": "Bot features", "folder": "Hydra", "kind": "text", "default": None,
                         "short": text, "text": text, "active": False})
    order = {"Game setup": 0, "Bot features": 1}
    registry.sort(key=lambda r: (order[r["top"]], r["folder"], r["key"]))
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=0)
    folders = {}
    for r in registry:
        k = (r["top"], r["folder"])
        a, n = folders.get(k, (0, 0))
        folders[k] = (a + r["active"], n + 1)
    for (top, sub), (a, n) in sorted(folders.items(), key=lambda kv: (order[kv[0][0]], kv[0][1])):
        print(f"{top:13} {sub:26} {a:3} active of {n}")
    print(f"{len(registry)} settings, {sum(1 for r in registry if not r['short'])} with no description -> {OUT}")


if __name__ == "__main__":
    main()
