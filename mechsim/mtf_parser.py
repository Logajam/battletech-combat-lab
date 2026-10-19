"""
.mtf file parser. Reads front AND rear torso armor (plus, as of the
Patchwork investigation in ARCHITECTURE_PROPOSAL.md section 4, per-location
armor TYPE - not yet wired into mech_state.BattleMech, parsing-only so far
is unaffected), derives internal structure from tonnage via
mech_state.STRUCTURE_TABLE (mtf files don't include structure numbers
directly), and reconstructs crit-slot lists using the external equipment
database so multi-slot weapons group into one shared Equipment instance
instead of colliding on name alone. Currently supports Biped, Tripod, and
Quad; LAM/etc. raise a clear error rather than silently producing wrong
results.

IMPORTANT PARSING RULE (confirmed via Test_Rig_Problem_Child.mtf, a
deliberately adversarial test file - see ARCHITECTURE_PROPOSAL.md section
4): never infer a location's armor type from what armor-type-flavored
equipment sits in that location's own critical slots. A location's armor-
type crit slots can end up allocated to a DIFFERENT location than the one
being protected (observed directly: Head's own crit list contained an
"IS Reflective" slot that actually belongs to Right Torso's armor type) -
likely a MegaMek export quirk. The header line (e.g. `LA armor:IS Anti-
Penetrative Ablation(Inner Sphere):34`) is the only reliable source of
truth for a location's armor type, once that gets wired in.

STAGE 3 (2026-07-12, Claude): now also parses the mech-wide "structure:"
header line (e.g. "structure:IS Reinforced") into BattleMech.structure_type -
confirmed shape via Test_Rig_Armor.mtf. Unlike armor type this is a single
top-level value, no per-location/Patchwork equivalent. Unrecognized text
(Endo Steel, Endo-Composite, etc.) prints a WARNING and defaults to Standard
rather than guessing - those types have no combat-math difference from
Standard in this sim regardless.

TMM (2026-07-12, Claude): now also parses "walk mp:"/"jump mp:" header
lines into BattleMech.base_walk_mp/base_jump_mp - confirmed shape via
Asymptote_iJ_mpulse.mtf ("walk mp:3" / "jump mp:5"). walk mp missing prints
a WARNING and defaults to 1 (a real gap, not a benign one - see
damage_resolution.compute_tmm); jump mp missing defaults to 0 silently,
since the large majority of real mechs have no jump jets at all. See
mech_state.compute_walk_mp/compute_jump_mp for how these combine with
crit-slot damage (leg actuators, jump jet destruction) into the mech's
CURRENT effective MP each round.
"""

import re

import config
from equipment import lookup_equipment, ANATOMY_COMPONENTS, ENGINE_NAMES, Equipment
from mech_state import ArmorType, StructureType, BattleMech, structure_for_tonnage, snapshot_round_capability
from damage_resolution import is_partial_wing


# Normalized (lowercase, whitespace/hyphens stripped) substrings -> ArmorType,
# matched against .mtf armor-type text after stripping the trailing tech-base
# parenthetical (e.g. "(Inner Sphere)") and any leading IS/Clan/CL prefix.
# Order doesn't matter for these keys - none are substrings of each other.
# "Ferro-Fibrous" (all variants - Light/Heavy/etc.) maps to STANDARD per
# ArmorType's own docstring in mech_state.py.
ARMOR_TYPE_NAME_MAP = {
    "standard": ArmorType.STANDARD,
    "ferrofibrous": ArmorType.STANDARD,
    "antipenetrativeablation": ArmorType.ANTI_PENETRATIVE_ABLATION,
    "impactresistant": ArmorType.IMPACT_RESISTANT,
    "reflective": ArmorType.REFLECTIVE,
    "reactive": ArmorType.REACTIVE,
    "hardened": ArmorType.HARDENED,
    "ferrolamellor": ArmorType.FERRO_LAMELLOR,
    "ballisticreinforced": ArmorType.BALLISTIC_REINFORCED,
    "heatdissipating": ArmorType.HEAT_DISSIPATING,
}

# HELP(structure_type.endo_aliases)
# Mech-wide "structure:" header line (e.g. "structure:IS Reinforced",
# "structure:Standard") - confirmed shape via Test_Rig_Armor.mtf. Unlike
# armor, this is a single top-level line, never per-location. Endo Steel and
# Endo-Composite are explicit, silent aliases for STANDARD here (2026-07-16,
# Daniel confirmed) - same "known type, no combat-math difference" treatment
# ARMOR_TYPE_NAME_MAP already gives Ferro-Fibrous above, not a fallback.
# Anything else not listed here still falls to the "unrecognized" WARNING
# path below rather than silently assuming Standard, per project convention
# (never silently guess on genuinely unknown text).
STRUCTURE_TYPE_NAME_MAP = {
    "standard": StructureType.STANDARD,
    "endosteel": StructureType.STANDARD,
    "endocomposite": StructureType.STANDARD,
    "reinforced": StructureType.REINFORCED,
    "composite": StructureType.COMPOSITE,
}


def map_structure_type_name(name_text):
    """Same stripping approach as map_armor_type_name (reuses
    strip_armor_type_tech_base - the text-stripping logic is generic, not
    armor-specific, despite the function's name). Returns None if
    unrecognized - caller decides how to handle it."""
    normalized = re.sub(r"[\s\-]", "", strip_armor_type_tech_base(name_text)).lower()
    return STRUCTURE_TYPE_NAME_MAP.get(normalized)


def strip_armor_type_tech_base(name_text):
    """Strip a trailing tech-base parenthetical (e.g. "(Inner Sphere)",
    "(Clan)") and a leading IS/Clan/CL prefix baked into the name itself.
    Confirmed against Test_Rig_Problem_Child.mtf's real header-line text,
    e.g. "IS Anti-Penetrative Ablation(Inner Sphere)" -> "Anti-Penetrative
    Ablation"."""
    text = re.sub(r"\([^)]*\)", "", name_text).strip()
    for prefix in ("IS ", "Clan ", "CL "):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    return text


def map_armor_type_name(name_text):
    """Returns an ArmorType, or None if name_text doesn't match anything in
    ARMOR_TYPE_NAME_MAP - caller decides how to handle an unrecognized type
    (this function never guesses or defaults on its own)."""
    normalized = re.sub(r"[\s\-]", "", strip_armor_type_tech_base(name_text)).lower()
    return ARMOR_TYPE_NAME_MAP.get(normalized)


def armor_key_map(mech_type):
    """Confirmed against a real Quad .mtf export: Quad does NOT reuse the
    LA/RA/LL/RL abbreviations at all. It has its own four: FLL/FRL (front
    legs) and RLL/RRL (rear legs - which are ALSO a distinct location from
    Biped's plain "Left Leg"/"Right Leg", see mech_state.BattleMech.__init__
    and KNOWN_LOCATIONS below). Kept as a function rather than a static dict
    since biped/tripod and quad need entirely different key sets, not just
    different targets for the same keys."""
    if mech_type in ("quad", "quadvee"):
        return {
            "FLL armor": ("Front Left Leg", "front"), "FRL armor": ("Front Right Leg", "front"),
            "LT armor": ("Left Torso", "front"), "RT armor": ("Right Torso", "front"),
            "CT armor": ("Center Torso", "front"), "HD armor": ("Head", "front"),
            "RLL armor": ("Rear Left Leg", "front"), "RRL armor": ("Rear Right Leg", "front"),
            "RTL armor": ("Left Torso", "rear"), "RTR armor": ("Right Torso", "rear"),
            "RTC armor": ("Center Torso", "rear"),
        }
    return {
        "LA armor": ("Left Arm", "front"), "RA armor": ("Right Arm", "front"),
        "LT armor": ("Left Torso", "front"), "RT armor": ("Right Torso", "front"),
        "CT armor": ("Center Torso", "front"), "HD armor": ("Head", "front"),
        "LL armor": ("Left Leg", "front"), "RL armor": ("Right Leg", "front"),
        "CL armor": ("Center Leg", "front"),
        "RTL armor": ("Left Torso", "rear"), "RTR armor": ("Right Torso", "rear"),
        "RTC armor": ("Center Torso", "rear"),
    }


def determine_mech_type(config_str, cockpit_str=""):
    """Substring match, not exact match - MegaMek's Config field routinely has
    extra words tacked on ("Biped Omnimech", "Quad Omnimech", etc.), and an
    exact-equality check broke on any real Omnimech chassis.

    QuadVee (Daniel, 2026-07-17): Config alone can't tell a QuadVee apart
    from a plain Quad - both just say "Quad" (or "Quad Omnimech" etc.).
    Distinguished instead by the top-level cockpit: line, which reads
    "QuadVee Cockpit" on a real QuadVee export. Mechanically a QuadVee is
    identical to a Quad everywhere in this sim EXCEPT crew count (2
    separately-tracked crew - Pilot + Gunner - vs. a Quad's 1), so every
    existing `mech_type == "quad"` geometry/locomotion check elsewhere
    (armor_key_map above, mech_state.py location/crit/leg-locations setup,
    leg_kill_threshold, walk MP quad offset, hit_location's quad limb
    remap, piloting_rolls' quad PSR modifier) was extended to also match
    "quadvee" rather than rewritten - not independently confirmed beyond
    the crew-count difference itself, flagging in case any of those turn
    out not to apply to a QuadVee's actual locomotion chassis."""
    cfg = config_str.strip().lower()
    cockpit = cockpit_str.strip().lower()
    if "quad" in cfg:
        return "quadvee" if "quadvee" in cockpit else "quad"
    elif "tripod" in cfg:
        return "tripod"
    elif "biped" in cfg:
        return "biped"
    raise ValueError(f"Config '{config_str}' is not yet supported by this simulator "
                      f"(only Biped, Tripod, Quad, and QuadVee are implemented - LAM/etc. still on the backlog).")


KNOWN_LOCATIONS = ["Left Arm", "Right Arm", "Left Torso", "Right Torso",
                   "Center Torso", "Head", "Left Leg", "Right Leg", "Center Leg",
                   "Front Left Leg", "Front Right Leg", "Rear Left Leg", "Rear Right Leg"]


def strip_cosmetic_suffixes(name):
    """Strip MegaMek's cosmetic mounting/variant tags - "(R)" (rear-mounted),
    "(OMNIPOD)" (Omnimech pod-mounted), "(T)" (turret-mounted) - none of which
    change the underlying item's slots/explosive/damage_type. Loops because
    tags can stack in either order ("Foo (T) (OMNIPOD)"). Used both to resolve
    a raw .mtf name against equipment.json AND to decide whether consecutive
    raw lines are the same multi-slot item.

    CASE-INSENSITIVE MATCH (2026-07-13, Claude - bug found while chasing the
    jump-jet MP bug): MegaMek exports these tags in varying case - confirmed
    real examples include "(omnipod)" lowercase, not just "(OMNIPOD)". The
    match against name.upper() is case-insensitive, but the slice below still
    cuts the ORIGINAL-CASE string (name[:-len(suffix)]), so the item's real
    name text is preserved unchanged - only the tag itself is removed. See
    DESIGN_NOTES_mech.md#cosmetic_suffix.case_insensitive_match."""
    changed = True
    while changed:
        changed = False
        for suffix in ("(R)", "(OMNIPOD)", "(T)"):
            if name.upper().endswith(suffix):
                name = name[:-len(suffix)].strip()
                changed = True
    return name


def build_crit_list(raw_lines, special_rules_seen=None):
    """special_rules_seen: optional set, mutated in place with (name, ref) pairs
    for any equipment.json entry flagged special_rules=True that gets used here.
    parse_mtf() collects this across all locations and prints one summary note
    per mech build."""
    if special_rules_seen is None:
        special_rules_seen = set()

    result = []
    i = 0
    n = len(raw_lines)
    while i < n:
        raw = raw_lines[i]
        name = raw.strip()

        if name == "-Empty-":
            result.append("-Empty-")
            i += 1
            continue

        base_name = strip_cosmetic_suffixes(name)

        if base_name in ENGINE_NAMES:
            result.append("Engine")
            i += 1
            continue

        if base_name == "Gyro":
            result.append("Gyro")
            i += 1
            continue

        if base_name == "Cockpit":
            result.append("Cockpit")
            i += 1
            continue

        if base_name.upper().startswith("MECHANICALJUMPBOOSTER:SIZE:"):
            # Bypasses equipment.json entirely - the SIZE value is per-mech data
            # embedded in the crit-slot text itself, not a static named property a
            # lookup table can hold (see the SIZE pre-scan in parse_mtf, above).
            # Still produces a real crit-targetable Equipment instance so a hit
            # can be detected and flip the mech-wide disable flag - see
            # damage_resolution.is_mechanical_jump_booster.
            result.append(Equipment("Mechanical Jump Booster", slots_occupied=1,
                                     is_explosive=False, crit_eligible=True))
            i += 1
            continue

        entry = lookup_equipment(base_name)

        if entry is not None:
            slots_needed = entry["slots"]
            group = [raw_lines[i]]
            j = i + 1
            while len(group) < slots_needed and j < n:
                next_base = strip_cosmetic_suffixes(raw_lines[j].strip())
                if next_base == base_name:
                    group.append(raw_lines[j])
                    j += 1
                else:
                    break
            actual_slots = len(group)
            if actual_slots < slots_needed:
                # Real data-integrity issue, not benign fallback noise - stays visible.
                print(f"WARNING: expected {slots_needed} slots for {base_name} but only found "
                      f"{actual_slots} consecutive matching lines - treating as a {actual_slots}-slot item.")

            # Ammo's flat house-rule explosion default (20) only applies to ammo;
            # non-ammo explosive gear falls through to Equipment's own 2/slot default
            # when explosion_damage is None. Either way, an explicit value in
            # equipment.json (once someone fills one in) always wins.
            if entry["category"] == "ammo" and entry["explosive"] and entry["explosion_damage"] is None:
                explosion_damage = 20
            else:
                explosion_damage = entry["explosion_damage"]

            equip = Equipment(
                base_name, slots_occupied=actual_slots, is_explosive=entry["explosive"],
                explosion_damage=explosion_damage, crit_eligible=entry["crit_eligible"],
                damage_type=entry["damage_type"], special_rules=entry["special_rules"],
                special_rules_ref=entry["special_rules_ref"],
                # Weapon-stat fields (2026-08-05, INTEGRATION Part A) - populated for
                # every entry.json row regardless of category, so non-weapon gear just
                # carries None through unused. entry.get(...) rather than entry[...]
                # since older/thinner equipment.json rows (pre this pass) may not have
                # every key - fails soft to None rather than a KeyError.
                category=entry.get("category"), weapon_range=entry.get("range"),
                damage_per_shot=entry.get("damage_per_shot"), heat=entry.get("heat"),
                battle_value=entry.get("battle_value"), tonnage=entry.get("tonnage"),
                rack_size=entry.get("rack_size"),
            )
            result.extend([equip] * actual_slots)
            if entry["special_rules"]:
                special_rules_seen.add((entry["canonical_name"], entry["special_rules_ref"]))
            i = j
            continue

        # Not in the database at all. Ammo gets one more safety-net check before
        # falling all the way to generic padding, since "ammo" mtf lines that
        # somehow don't resolve via the alias map would otherwise silently stop
        # exploding - a much bigger correctness problem than a cosmetic label.
        lower = base_name.lower()
        if lower.startswith("is ammo") or lower.startswith("clan ammo") or lower.startswith("ammo"):
            config.log(f"  NOTE: ammo item '{base_name}' not found in equipment.json - "
                f"falling back to explosive/20-damage default rather than silently "
                f"treating it as inert. Add it to equipment.json to get its real value.")
            result.append(Equipment(base_name, slots_occupied=1, is_explosive=True, explosion_damage=20))
            i += 1
            continue

        if base_name not in ANATOMY_COMPONENTS:
            # Genuinely unrecognized, benign-fallback case - gated behind VERBOSE
            # per Daniel's instruction (this isn't a data problem worth seeing by
            # default, just an untagged item running as inert padding).
            config.log(f"  NOTE: unrecognized component '{base_name}' - treating as a plain "
                f"1-slot component with no special effect. Add it to equipment.json "
                f"if it needs real properties.")
        result.append(base_name)
        i += 1

    return result


def parse_mtf(filepath):
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        raw_lines = [l.rstrip("\n") for l in f]

    # Pre-scan for Config specifically, BEFORE the main parsing pass below - we
    # need mech_type known up front so armor-line abbreviations (LA/RA) resolve
    # to the right location (Left Arm vs Front Left Leg) as they're read, not
    # after the fact. Cheap: just another pass over lines already in memory.
    config_str = "Biped"
    cockpit_str = ""
    for raw in raw_lines:
        line = raw.strip()
        if ":" in line:
            key, _, value = line.partition(":")
            key_lower = key.strip().lower()
            if key_lower == "config":
                config_str = value.strip()
            elif key_lower == "cockpit":
                cockpit_str = value.strip()

    mech_type = determine_mech_type(config_str, cockpit_str)
    armor_keys = armor_key_map(mech_type)

    # Pre-scan for the top-level "armor:" line (e.g. "armor:Patchwork" or
    # "armor:Standard") - this is the FALLBACK armor type for any per-location
    # armor line that has no type text of its own (the normal case on a
    # non-Patchwork mech - confirmed via Test_Rig_Problem_Child.mtf, where
    # this file's own Patchwork case is the one WITH type text on every line,
    # and its rear-armor lines, which never carry type text at all, are the
    # confirmed shape a plain front-armor line takes on a uniform mech).
    # global_armor_type is None specifically when the top-level line says
    # "Patchwork" - that's a signal, not a real type, meaning every
    # per-location line is expected to carry its own explicit type text with
    # no fallback available.
    # HELP(armor_type.patchwork_fallback)
    global_armor_text = None
    for raw in raw_lines:
        line = raw.strip()
        if ":" in line:
            key, _, value = line.partition(":")
            if key.strip().lower() == "armor":
                global_armor_text = value.strip()
                break

    if global_armor_text is None:
        print("WARNING: no top-level 'armor:' line found in .mtf file - assuming Standard as the "
              "fallback type for any location armor line with no type text of its own.")
        global_armor_type = ArmorType.STANDARD
    elif global_armor_text.strip().lower() == "patchwork":
        global_armor_type = None
    else:
        global_armor_type = map_armor_type_name(global_armor_text)
        if global_armor_type is None:
            print(f"WARNING: unrecognized global armor type '{global_armor_text}' - defaulting to "
                  f"Standard as the fallback type for any location armor line with no type text of its own.")
            global_armor_type = ArmorType.STANDARD

    # Pre-scan for the mech-wide "structure:" line (Stage 3 - confirmed shape
    # via Test_Rig_Armor.mtf's "structure:IS Reinforced"). Single line, no
    # per-location equivalent - unlike armor there's no Patchwork-style
    # sentinel to handle here.
    # HELP(structure_type.parsing)
    structure_text = None
    for raw in raw_lines:
        line = raw.strip()
        if ":" in line:
            key, _, value = line.partition(":")
            if key.strip().lower() == "structure":
                structure_text = value.strip()
                break

    if structure_text is None:
        print("WARNING: no top-level 'structure:' line found in .mtf file - defaulting to Standard.")
        structure_type = StructureType.STANDARD
    else:
        structure_type = map_structure_type_name(structure_text)
        if structure_type is None:
            print(f"WARNING: unrecognized structure type '{structure_text}' - defaulting to Standard "
                  f"(no combat-math difference in this sim for types like Endo Steel/Endo-Composite).")
            structure_type = StructureType.STANDARD

    # HELP(mechanical_jump_booster.size_parsing)
    # Pre-scan for Mechanical Jump Booster's embedded SIZE value - confirmed
    # shape via Test_Rig_Problem_Child.mtf: "MechanicalJumpBooster:SIZE:6.0",
    # one line per crit slot (2 slots/leg location). The SIZE number IS the
    # jump MP granted directly (Daniel, 2026-07-13 - no lookup table, no
    # scaling math). Not a single header line like armor:/structure: - it's
    # repeated across every one of this system's crit-slot lines instead, so
    # all found values are collected and checked for agreement (fail loudly
    # if they disagree, rather than silently trusting the first one found -
    # same "fail loudly, don't guess" convention as the rest of this parser).
    mech_jump_booster_size = 0
    booster_size_pattern = re.compile(r"MechanicalJumpBooster:SIZE:([\d.]+)", re.IGNORECASE)
    found_booster_sizes = set()
    for raw in raw_lines:
        match = booster_size_pattern.search(raw.strip())
        if match:
            try:
                found_booster_sizes.add(int(float(match.group(1))))
            except ValueError:
                pass
    if len(found_booster_sizes) > 1:
        print(f"WARNING: Mechanical Jump Booster SIZE values disagree across crit lines "
              f"({sorted(found_booster_sizes)}) - using {max(found_booster_sizes)}. "
              f"Check the .mtf file for a data error.")
        mech_jump_booster_size = max(found_booster_sizes)
    elif found_booster_sizes:
        mech_jump_booster_size = found_booster_sizes.pop()

    # Real MegaMek .mtf files don't use "chassis:"/"model:" keys at all - the
    # actual format is: "Version:X.X", then chassis as a BARE line (no colon),
    # then model as another bare line. Pre-scan for the first two bare
    # (non-"key:value") lines, skipping the Version line specifically. Explicit
    # "chassis:"/"model:" keys (if some other tool ever emits that style) still
    # work too and take priority - see the main loop below.
    bare_names = []
    for raw in raw_lines:
        s = raw.strip()
        if not s:
            continue
        if s.lower().startswith("version:"):
            continue
        if ":" not in s:
            bare_names.append(s)
            if len(bare_names) == 2:
                break
        else:
            break  # hit a real key:value field before collecting 2 bare names
    chassis = bare_names[0] if len(bare_names) >= 1 else ""
    model = bare_names[1] if len(bare_names) >= 2 else ""

    mass, engine_line = None, ""
    walk_mp, jump_mp = None, None
    heat_sink_count, heat_sink_type = None, None
    front_armor, rear_armor = {}, {}
    location_armor_type = {}
    location_lines = {}

    i = 0
    n = len(raw_lines)
    while i < n:
        line = raw_lines[i].strip()
        if not line or line.startswith("#"):
            i += 1
            continue

        if line.endswith(":") and line[:-1] in KNOWN_LOCATIONS:
            loc_name = line[:-1]
            slots = []
            i += 1
            while i < n and raw_lines[i].strip() != "":
                slots.append(raw_lines[i].strip())
                i += 1
            location_lines[loc_name] = slots
            continue

        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip().lower()          # CASE INSENSITIVE
            value = value.strip()
            if key == "chassis":
                chassis = value or chassis
            elif key == "model":
                model = value or model
            elif key == "mass":
                try:
                    mass = int(value)
                except ValueError:
                    pass
            elif key == "engine":
                engine_line = value
            elif key == "walk mp":
                try:
                    walk_mp = int(value)
                except ValueError:
                    pass
            elif key == "jump mp":
                try:
                    jump_mp = int(value)
                except ValueError:
                    pass
            elif key == "heat sinks":
                # Value shape is "N Type", e.g. "20 Single" / "10 Double" -
                # count and type in one field, unlike walk/jump mp's bare
                # int. Split on whitespace rather than a fixed delimiter
                # since real files vary in spacing; type is whatever text
                # follows the count verbatim (Single/Double/Compact/Laser -
                # Radical Heat Sink System is equipment, not a heat sink
                # type, and would not legitimately appear here).
                parts = value.split(None, 1)
                if parts:
                    try:
                        heat_sink_count = int(parts[0])
                    except ValueError:
                        pass
                    else:
                        heat_sink_type = parts[1].strip() if len(parts) > 1 else "Single"
            elif any(key == k.lower() for k in armor_keys):
                orig_key = next((k for k in armor_keys if k.lower() == key), None)
                if orig_key:
                    loc, side = armor_keys[orig_key]
                    if side == "front":
                        # Front-armor lines are "type:points" when the mech
                        # carries per-location type text (Patchwork, or any
                        # mech where MegaMek chose to write it out), or just
                        # "points" with no type text at all (the normal case
                        # on a uniform mech - confirmed via this file's own
                        # rear-armor lines, which are always this shape).
                        # HELP(armor_type.never_infer_from_crits)
                        type_text, sep, points_text = value.rpartition(":")
                        if sep:
                            armor_type = map_armor_type_name(type_text)
                            if armor_type is None:
                                print(f"WARNING: unrecognized armor type '{type_text}' for {loc} - "
                                      f"defaulting to Standard.")
                                armor_type = ArmorType.STANDARD
                        else:
                            points_text = value
                            if global_armor_type is None:
                                print(f"WARNING: {loc} armor line has no type text and the mech's "
                                      f"top-level armor line is 'Patchwork' (no fallback type "
                                      f"available) - defaulting to Standard.")
                                armor_type = ArmorType.STANDARD
                            else:
                                armor_type = global_armor_type
                        location_armor_type[loc] = armor_type
                    else:
                        points_text = value
                    try:
                        val = int(points_text)
                    except ValueError:
                        val = 0
                    if side == "front":
                        front_armor[loc] = val
                    else:
                        rear_armor[loc] = val
        i += 1

    if mass is None:
        raise ValueError(f"Could not find mass. Check file. First 20 keys: {[l.strip() for l in raw_lines if ':' in l][:20]}")

    structure = structure_for_tonnage(mass, mech_type)

    mech = BattleMech(mech_type=mech_type)
    mech.chassis, mech.model, mech.mass, mech.engine_desc = chassis, model, mass, engine_line
    mech.structure_type = structure_type

    if walk_mp is None:
        print("WARNING: no 'walk mp:' line found in .mtf file - defaulting to 1 "
              "(TMM/walk-MP calculations will be degenerate for this mech).")
        walk_mp = 1
    mech.base_walk_mp = walk_mp
    # jump mp is legitimately absent for the large majority of real mechs (no
    # jump jets) - 0 is the correct default here, not a WARNING-worthy gap,
    # same as jump_mp's own default in the hardcoded fixture.
    mech.base_jump_mp = jump_mp if jump_mp is not None else 0
    mech.base_mechanical_jump_booster_mp = mech_jump_booster_size

    if heat_sink_count is None:
        # Unlike jump mp, a real mech is never legitimately without a
        # "heat sinks:" line - treat a missing/unparsed line as a real gap
        # (WARNING, same as walk mp) rather than silently assuming a count.
        # Defaulting to 0/None instead of a guessed BT minimum since that
        # minimum is a rules number, not something to invent here.
        print("WARNING: no 'heat sinks:' line found (or it didn't parse) in .mtf "
              "file - defaulting to 0 (heat dissipation will be degenerate for "
              "this mech).")
        heat_sink_count = 0
    mech.base_heat_sinks = heat_sink_count
    mech.heat_sink_type = heat_sink_type or "Single"

    for loc in mech.locations:
        if loc not in front_armor:
            print(f"WARNING: no armor value found for {loc} in .mtf file - defaulting to 0.")
        mech.locations[loc]["armor"] = front_armor.get(loc, 0)
        if "rear_armor" in mech.locations[loc]:
            mech.locations[loc]["rear_armor"] = rear_armor.get(loc, 0)
        mech.locations[loc]["structure"] = structure[loc]
        if loc not in location_armor_type:
            print(f"WARNING: no armor type found for {loc} in .mtf file - defaulting to Standard.")
        mech.armor_type[loc] = location_armor_type.get(loc, ArmorType.STANDARD)

    special_rules_seen = set()
    for loc in mech.locations:
        if loc in location_lines:
            mech.crits[loc] = build_crit_list(location_lines[loc], special_rules_seen)
        else:
            print(f"WARNING: no critical slot section found for {loc} in .mtf file.")

    # HELP(partial_wing.detection)
    # Presence detection (Daniel, 2026-07-14): Partial Wing resolves through
    # the normal equipment.json lookup path in build_crit_list (1 slot each,
    # no special-casing needed there), so its presence can only be confirmed
    # by scanning the built crit lists afterward - same as how
    # mech.initial_sensor_slots is derived below, not computed inline during
    # the build. mech.partial_wing_active starts True here if any matching
    # slot exists; damage_resolution.resolve_slot_hit/mark_all_crits_destroyed
    # flip it False (all-or-nothing) the moment any slot is hit.
    mech.partial_wing_active = any(
        isinstance(slot, Equipment) and is_partial_wing(slot)
        for crit_list in mech.crits.values()
        for slot in crit_list
    )

    mech.max_armor = {l: v["armor"] for l, v in mech.locations.items()}
    mech.max_rear_armor = {l: v["rear_armor"] for l, v in mech.locations.items() if "rear_armor" in v}
    mech.max_structure = {l: v["structure"] for l, v in mech.locations.items()}
    # Recompute AFTER real crit data is in place - the __init__ value reflects the
    # generic fixture's Head, not this mech's.
    mech.initial_sensor_slots = sum(1 for s in mech.crits.get("Head", []) if s == "Sensors")
    snapshot_round_capability(mech)

    if special_rules_seen:
        # Always visible (not VERBOSE-gated) - this is "here's a real rule this sim
        # doesn't fully model yet," not benign padding-fallback noise.
        print("\nNOTE: this unit has equipment with special rules not yet fully "
              "modeled by this sim (see FOR LATER in main.py's header docstring):")
        for name, ref in sorted(special_rules_seen):
            print(f"  - {name} (ref: {ref})")
        print()

    return mech
