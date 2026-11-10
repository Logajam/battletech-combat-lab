"""
tools/port_scenarios.py - the fixture battles of the Rust port (INTEGRATION__RUST_PORT.md, stage 0).

SCENARIOS: name -> (config statements, max turns). Three groups:
  REFERENCE  the 15 reference battles of tests/check_reference_logs.py (same statements, 50-turn cap)
  TEAM       team battles: 4 v 4 and 12 v 12; Princess v Gladiator, Gladiator v Gladiator, Princess v Princess; a 3-way
  COVERAGE   short battles picked so that between them every weapon family, equipment module and hazard happens

`python tools/port_record.py --scenario NAME OUT_DIR` records one; `python tools/port_fixtures.py` records them all.
"""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "tests"))
import check_reference_logs  # noqa: E402

SCENARIOS = {}

# --- reference ---------------------------------------------------------------------------------------------------
for _name, _statements in check_reference_logs.SCENARIOS.items():
    SCENARIOS["ref_" + _name.replace(".txt", "")] = (_statements, check_reference_logs.TEST_BATTLE_MAX_TURNS)

# --- team battles ------------------------------------------------------------------------------------------------
LANCE_A = [("Atlas AS7-K.mtf", 1), ("Archer ARC-2R.mtf", 1), ("Cataphract CTF-3D.mtf", 1), ("Hammerhead.mtf", 1)]
LANCE_B = [("Kintaro KTO-19.mtf", 1), ("Black Hawk (Nova) F.mtf", 1), ("Awesome AWS-8Q.mtf", 1), ("Kontio.mtf", 1)]
LIGHTS = [("Jenner JR7-D.mtf", 3), ("Commando COM-2D.mtf", 3), ("Locust LCT-1V.mtf", 3), ("Griffin GRF-1N.mtf", 3)]
MEDIUMS = [("Hunchback HBK-4G.mtf", 3), ("Dervish DV-6M.mtf", 3), ("Catapult CPLT-C1.mtf", 3),
           ("Atlas AS7-S2.mtf", 3)]


def _force(team, bot, roster):
    return [{"team": team, "mtf": mtf, "count": n, "bot": bot} for mtf, n in roster]


def _team(forces, board="16x17_Grassland_1.board"):
    return [f"config.FORCES = {forces!r}", f'config.DEFAULT_BOARD_PATH = "{board}"', "config.SEED = 11"]


def _wide(forces):
    return _team(forces, "32x17_Caustic_Valley_Lava.board")


SCENARIOS["team_4v4_princess_v_gladiator"] = (_team(_force("Red", "princess", LANCE_A) + _force("Blue", "gladiator", LANCE_B)), 20)
SCENARIOS["team_4v4_gladiator_v_gladiator"] = (_team(_force("Red", "gladiator", LANCE_A) + _force("Blue", "gladiator", LANCE_B)), 20)
SCENARIOS["team_4v4_princess_v_princess"] = (_team(_force("Red", "princess", LANCE_A) + _force("Blue", "princess", LANCE_B)), 20)
SCENARIOS["team_12v12_princess_v_gladiator"] = (_wide(_force("Red", "princess", LIGHTS) + _force("Blue", "gladiator", MEDIUMS)), 10)
SCENARIOS["team_12v12_gladiator_v_gladiator"] = (_wide(_force("Red", "gladiator", LIGHTS) + _force("Blue", "gladiator", MEDIUMS)), 10)
SCENARIOS["team_3way_mixed"] = (_wide(_force("Red", "princess", LANCE_A[:3]) + _force("Blue", "gladiator", LANCE_B[:3])
                                      + _force("Green", "princess", MEDIUMS[:1] + LIGHTS[:2])), 15)

# --- coverage ----------------------------------------------------------------------------------------------------
# Short battles (10-12 turns) of units from data/meks.zip picked so that between them every weapon family, equipment
# module and hazard happens at least once. A unit is named by its path in the zip; its .mtf is unpacked into
# engine/fixtures/_units/ (git-ignored) and given to the engine as a path relative to data/, so logs print the same
# path on every machine.
import zipfile  # noqa: E402

UNITS_DIR = os.path.join(REPO_ROOT, "engine", "fixtures", "_units")


def unit(zip_path):
    """'3055U/Hachiwara HCA-6P.mtf' (a path inside data/meks.zip) -> the path config reads, relative to data/."""
    name = os.path.basename(zip_path)
    target = os.path.join(UNITS_DIR, name)
    if not os.path.exists(target):
        os.makedirs(UNITS_DIR, exist_ok=True)
        with zipfile.ZipFile(os.path.join(REPO_ROOT, "data", "meks.zip")) as z:
            member = next(n for n in z.namelist() if n.endswith("/" + zip_path) or n == zip_path)
            with open(target, "wb") as f:
                f.write(z.read(member))
    return "../engine/fixtures/_units/" + name


def _skirmish(units, board="16x17_Grassland_1.board", seed=21, extra=()):
    """units: [(team, zip path, hex, facing, bot)] placed at fixed hexes, so a battle starts where the feature is."""
    forces = [{"team": t, "mtf": unit(z), "hex": h, "facing": f, "bot": b, "max_heat": 30} for t, z, h, f, b in units]
    return [f"config.FORCES = {forces!r}", "config.DEPLOYMENT = 'fixed_hexes'",
            f'config.DEFAULT_BOARD_PATH = "{board}"', f"config.SEED = {seed}"] + list(extra)


def _duel(a, b, board="16x17_Grassland_1.board", seed=21, gap=3, bots=("gladiator", "gladiator"), extra=()):
    """Two units `gap` hexes apart in one column, facing each other."""
    return _skirmish([("Red", a, "0505", "S", bots[0]), ("Blue", b, f"05{5 + gap:02d}", "N", bots[1])],
                     board, seed, extra)


def _add(name, statements, turns=12):
    SCENARIOS["cov_" + name] = (statements, turns)


# physical weapons, claws, spikes, lances, talons: close in and hit
_add("melee_spikes_lance", _duel("3055U/Hachiwara HCA-6P.mtf", "3055U/Porcupine PRC-1N.mtf", gap=2))
_add("melee_hatchet_jump_dfa", _duel("XTRs/Republic I/Hatchetman HCT-7R.mtf", "XTRs/Succession Wars/Super Griffin GRF-2N-X.mtf", gap=2))
_add("melee_vibro", _duel("XTRs/Gladiators/Valiant VAL-NT-JX Hot Knife.mtf", "XTRs/Liao/Dola DOL-1A.mtf", gap=2))
_add("melee_claws_talons", _duel("3058Uu/Kodiak 4.mtf", "3058Uu/Talon TLN-5V.mtf", gap=2))
_add("melee_mace_sword", _duel("3085u/Cutting Edge/Mjolnir MLR-B2.mtf", "3067/No-Dachi NDA-1K.mtf", gap=2))
_add("melee_chain_whip", _duel("3145/Republic/Night Stalker NSR-K7.mtf", "XTRs/Periphery/Trebuchet TBT-XK7.mtf", gap=2))
# Interstellar Operations / TO:AUE weapons
_add("taser_harjel", _duel("3055U/Aquagladius AQS-3.mtf", "TRO Vehicle Annex/Peacemaker PM6 PoliceMech.mtf", gap=3))
_add("tsemp", _duel("3145/NTNU RS/Owens OW-1G.mtf", "3145/NTNU RS/Ebony MEB-12.mtf", gap=4))
_add("hvac", _duel("3085u/ONN/Victor VTR-Cr.mtf", "XTRs/Periphery/Atlas AS-700 Jurn.mtf", gap=5))
_add("nail_guns", _duel("3085u/Cutting Edge/Diomede D-M3D-4 DemolitionMech.mtf", "3075/Jabberwocky ConstructionMech JAW-66D.mtf", gap=2))
_add("imp_blue_shield", _duel("3050U/Imp IMP-3E.mtf", "XTRs/Gladiators/Spatha SP2-X Warlord.mtf", gap=4))
_add("capacitor_charged", _duel("XTRs/Marik/Jackal JA-KL-1579.mtf", "3055U/Colossus CLS-5S.mtf", gap=5,
                                extra=["config.STUB_CAPACITOR_START = 'charged'", "config.STUB_CAPACITOR_CHARGE = 'when_idle'"]))
_add("shield_raised", _duel("3075/Valiant VLN-3T.mtf", "3055U/Colossus CLS-4S.mtf", gap=3,
                            extra=["config.STUB_RAISE_SHIELD = 'always'"]))
# missiles, artillery, electronics
_add("apollo_narc_ecm", _duel("3055U/Apollo APL-1R.mtf", "3058Uu/Owens OW-1D.mtf", gap=5))
_add("arrow_tag", _skirmish([("Red", "3075/Legionnaire LGN-2XA.mtf", "0505", "S", "gladiator"),
                             ("Red", "3050U/Hermes II HER-5S.mtf", "0705", "S", "gladiator"),
                             ("Blue", "3075/Patriot PKM-2C.mtf", "0510", "N", "gladiator")],
                            extra=["config.STUB_FIRE_TAG = 'always'"]))
_add("inferno_mml_atm", _duel("3067 Unabridged/IS Meks/Stiletto STO-4C.mtf", "3085u/Phoenix/Griffin IIC 4.mtf", gap=6))
_add("rotary_ultra_streak", _duel("3050U/JagerMech JM7-G.mtf", "3050U/Sentinel STN-3L.mtf", gap=5))
_add("mortar_indirect", _duel("Golden Century/Minsk 2.mtf", "3058Uu/Crossbow D.mtf", gap=8))
# body plans and engines
_add("quad", _duel("Force Manuals/Mercs/Scorpion SCP-1N (Wendall 2).mtf", "XTRs/Steiner/Barghest BGS-4X.mtf", gap=3))
_add("tripod", _duel("XTRs/Republic III/Triskelion TRK-4V.mtf", "XTRs/RISC/'Battle Tripod' R_H3L-2X.mtf", gap=3))
_add("superheavy", _duel("3145/NTNU RS/NTNU/Omega SHP-5R.mtf", "XTRs/Republic II/Orca OC-1X.mtf", gap=4))
_add("turrets", _duel("3145/NTNU RS/Thunder Fox TFT-F11.mtf", "ISP3/Arana MilitiaMech ARA-S-1.mtf", gap=3))
_add("ice_engines", _duel("TRO Vehicle Annex/ForestryMech ED-X3.mtf", "TRO Irregulars/Exo HMX-1 Haulermech.mtf", gap=3))
_add("partial_wing_masc", _duel("Rec Guides ilClan/Vol 18/Eris ERS-2N.mtf", "3060u/Snow Fox 2.mtf", gap=4))
# terrain
_add("magma_board", _skirmish([("Red", "3050U/Hermes II HER-5S.mtf", "0305", "S", "gladiator"),
                               ("Blue", "3039u/Valkyrie VLK-QF.mtf", "0905", "N", "gladiator")],
                              board="16x17_Badlands_2_Hazardous_Liquid.board"), 15)
_add("woods_smoke", _duel("3055U/Fireball ALM-9D.mtf", "3039u/Valkyrie VLK-QF.mtf", board="16x17_Scattered_Woods.board", gap=4))
_add("hills_desert", _duel("3050U/Falcon FLC-5P.mtf", "3067/Cronus CNS-5M.mtf", board="16x17_Desert_Hills.board", gap=5))

# --- round 2: the rules the first coverage run never reached ------------------------------------------------------
JUMPERS = [("3050U/Falcon FLC-5P.mtf",), ("3039u/Valkyrie VLK-QF.mtf",)]
# magma and hazardous liquid: units that START in the hazard (hazards.start_of_movement, magma_burn, bog down, free_roll)
_add("magma_start", _skirmish([("Red", "3039u/Valkyrie VLK-QF.mtf", "1402", "S", "gladiator"),
                               ("Red", "3050U/Falcon FLC-5P.mtf", "1502", "S", "gladiator"),
                               ("Blue", "3055U/Fireball ALM-9D.mtf", "1409", "N", "gladiator")],
                              board="32x17_Caustic_Valley_Lava.board", seed=5), 12)
_add("pool_start", _skirmish([("Red", "3039u/Valkyrie VLK-QF.mtf", "0808", "S", "princess"),
                              ("Red", "3050U/Falcon FLC-5P.mtf", "0809", "S", "gladiator"),
                              ("Blue", "3055U/Fireball ALM-9D.mtf", "0814", "N", "princess")],
                             board="16x17_Badlands_2_Hazardous_Liquid.board", seed=5), 12)
# a brawl of jumpers and heavies at point-blank range: DFA, charges, pushes, displacement into occupied hexes (domino)
BRAWL_A = ["3050U/Falcon FLC-5P.mtf", "3039u/Valkyrie VLK-QF.mtf", "3055U/Hachiwara HCA-6P.mtf", "3055U/Porcupine PRC-1N.mtf"]
BRAWL_B = ["3067/Cronus CNS-5M.mtf", "3055U/Fireball ALM-9D.mtf", "3058Uu/Talon TLN-5V.mtf", "3058Uu/Kodiak 4.mtf"]
for _seed in (3, 4):
    _add(f"brawl_{_seed}", _skirmish([("Red", z, f"{5 + i:02d}05", "S", "gladiator") for i, z in enumerate(BRAWL_A)]
                                     + [("Blue", z, f"{5 + i:02d}06", "N", "gladiator") for i, z in enumerate(BRAWL_B)],
                                     seed=_seed), 8)
_add("brawl_princess", _skirmish([("Red", z, f"{5 + i:02d}05", "S", "princess") for i, z in enumerate(BRAWL_A)]
                                 + [("Blue", z, f"{5 + i:02d}06", "N", "princess") for i, z in enumerate(BRAWL_B)],
                                 seed=6), 8)
# MASC / supercharger used every turn (a failure roll each time: damage, crits, a PSR)
_add("masc_always", _duel("3050U/Falcon FLC-5P.mtf", "3060u/Snow Fox 2.mtf", gap=6,
                          extra=["config.STUB_ESCALATING_USE = 'always'"]), 25)
_add("supercharger_always", _duel("Shrapnel/Vol 23/Hermes III HER-7K.mtf", "3085u/Cutting Edge/Rook NH-3X.mtf", gap=6,
                                  extra=["config.STUB_ESCALATING_USE = 'always'"]), 25)
# one-shot rare dice events: more turns and a few seeds for the weapons whose special effect fires on a hit
for _seed in (31, 32, 33):
    _add(f"taser_{_seed}", _duel("3055U/Aquagladius AQS-3.mtf", "TRO Vehicle Annex/Peacemaker PM6 PoliceMech.mtf", gap=2, seed=_seed), 20)
    _add(f"hvac_{_seed}", _duel("3085u/ONN/Victor VTR-Cr.mtf", "XTRs/Periphery/Atlas AS-700 Jurn.mtf", gap=4, seed=_seed), 20)
_add("inferno_imp", _duel("Rec Guides ilClan/Vol 9/Inferno INF-NOA.mtf", "3050U/Imp IMP-3E.mtf", gap=3, seed=9), 20)
_add("fusion_ice", _duel("TRO Irregulars/Crosscut ED-X4M-A LoggerMech MOD.mtf", "3055U/Hachiwara HCA-6P.mtf", gap=3, seed=2), 20)
