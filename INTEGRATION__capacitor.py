"""
INTEGRATION__capacitor.py  (NEW 2026-10-21, Claude - Pile 2 rules, Pile 4 choices as stubs)

PPC capacitors (Core Rulebook p.188; linked components p.180). Daniel,
2026-10-21: "PPC charging is a bot logic question that requires its own
session" and "Wire in equipment that requires choice (Like capacitors) but
defer the actual bot decision making for later" - so the rules are built
here and both choices are loud stubs (INTEGRATION__stubs).

=== THE RULE ===
  - Linked (p.180): a capacitor serves the one PPC it is linked to; if that
    PPC is destroyed no other PPC can use it. The record sheet doesn't name
    the link, so each capacitor is linked to a PPC in its own location (the
    nearest one before it in the slot list, else any unlinked one there).
  - Instead of firing the PPC, the 'Mech may charge its capacitor (a choice -
    stubs.stub_capacitor_charge); it may start the game charged (a choice -
    stubs.stub_capacitor_start). Charging takes the turn and makes 5 heat;
    the charge is held as long as needed, 5 heat every turn it is held.
  - A charged PPC can't fire without using the charge: it fires for +5 damage
    and +5 heat (the holding heat isn't added that turn - p.188's example:
    charged turn 1, fired turn 4 = 5, 5, 5, then 15 + 5).
  - Critical hit: a capacitor explodes if it or its PPC takes a critical hit
    while charged - 2 x the combined slots of both (heavy PPC 4 + 1 = 10),
    and every slot of both is destroyed. If the PPC was declared firing in
    the Ranged Attack Phase it is hit in, the capacitor doesn't count as
    charged: only the slot struck is destroyed.

=== HOW IT IS WIRED ===
While a capacitor is charged its PPC's own heat and damage read 5 higher
(set_charged), so weapon selection, the heat report, damage (and a target's
Blue Shield) all see the charged shot with no change of their own. In the
Ranged Attack Phase: after declaration, declare() marks the charged PPCs
that fire and asks the stub about idle ones; after resolution, end_phase()
works out this turn's holding / charging heat (mech.capacitor_heat, added in
the Heat Phase) and spends or stores the charges.

Not modeled (the bot session, Section 6 Memo): weapon selection doesn't see
the 5 holding heat a charged PPC costs if it is not fired, nor plan a charge.
"""

import INTEGRATION__config as config
import INTEGRATION__stubs as stubs
import INTEGRATION__equipment_systems as equip

CHARGE_HEAT = 5             # p.188: charging, each turn held, and on top of the PPC's own heat when fired
CHARGE_DAMAGE = 5           # p.188: added to the PPC's Damage Value


def is_capacitor(slot):
    return "CAPACITOR" in equip._norm(getattr(slot, "name", "") or "")


# =============================================================================
# ==========================  LINKING  (battle start)  ========================
# =============================================================================
def attach(mech):
    """Link every capacitor to a PPC in its own location; start charged or not
    (a stub). Sets mech.capacitors = [capacitor Equipment] (each with
    .linked_ppc) and mech.capacitor_heat = 0."""
    mech.capacitors, mech.capacitor_heat = [], 0
    seen = set()
    for loc, slots in mech.crits.items():
        for i, s in enumerate(slots):
            if not is_capacitor(s) or id(s) in seen:
                continue
            seen.add(id(s))
            ppc = _pick_ppc(mech, slots, i)
            if ppc is None:
                config.log(f"  WARNING: {mech.side_name}'s {s.name} in {loc} has no PPC to link to - unused.")
                continue
            s.linked_ppc, ppc.capacitor = ppc, s
            if not hasattr(ppc, "base_heat"):
                ppc.base_heat, ppc.base_damage = ppc.heat, ppc.damage_per_shot
            s.firing = s.charging = False
            mech.capacitors.append(s)
            set_charged(s, stubs.stub_capacitor_start(mech.side_name, ppc.name))


def _pick_ppc(mech, slots, i):
    taken = {id(c.linked_ppc) for c in mech.capacitors}
    ppcs = [(j, s) for j, s in enumerate(slots)
            if getattr(s, "category", None) == "weapon" and equip.is_ppc(s) and id(s) not in taken]
    if not ppcs:
        return None
    before = [s for j, s in ppcs if j < i]
    return before[-1] if before else ppcs[0][1]


def set_charged(cap, on):
    cap.charged = bool(on)
    ppc = cap.linked_ppc
    ppc.heat = ppc.base_heat + (CHARGE_HEAT if on else 0)
    ppc.damage_per_shot = ppc.base_damage + (CHARGE_DAMAGE if on else 0)


def live(mech, cap):
    dead = equip._destroyed_ids(mech)
    return id(cap) not in dead and id(cap.linked_ppc) not in dead


# =============================================================================
# ==========================  RANGED ATTACK PHASE  ============================
# =============================================================================
def declare(mech, attacks_list, can_act=True):
    """After weapons are declared: a charged PPC that fires uses its charge;
    an idle one with an empty capacitor may charge instead (a stub)."""
    firing = {id(a.weapon) for a in attacks_list}
    for cap in getattr(mech, "capacitors", ()):
        cap.firing = cap.charged and id(cap.linked_ppc) in firing
        cap.charging = False
        if (can_act and not cap.charged and live(mech, cap) and id(cap.linked_ppc) not in firing
                and stubs.stub_capacitor_charge(mech.side_name, cap.linked_ppc.name)):
            cap.charging = True
            config.log(f"  {mech.side_name} charges the {cap.linked_ppc.name}'s capacitor instead of firing "
                       f"it (+{CHARGE_HEAT} heat, p.188).")


def end_phase(mech):
    """End of the Ranged Attack Phase: this turn's capacitor heat (charging or
    holding; a fired charge's +5 is already in the PPC's heat) and the
    charges spent or stored."""
    heat = 0
    for cap in getattr(mech, "capacitors", ()):
        if cap.firing:
            set_charged(cap, False)
        elif cap.charging:
            set_charged(cap, True)
            heat += CHARGE_HEAT
        elif cap.charged and live(mech, cap):
            heat += CHARGE_HEAT
        elif cap.charged:
            set_charged(cap, False)            # destroyed while charged by something other than a crit
        cap.firing = cap.charging = False
    mech.capacitor_heat = heat


# =============================================================================
# ==========================  CRITICAL HITS  ==================================
# =============================================================================
def crit_hit(mech, location, component):
    """A critical hit to a capacitor or a linked PPC (p.188), called once the
    slot is marked destroyed. Charged (and not firing this phase): a component
    explosion for 2 x the combined slots, every slot of both destroyed."""
    cap = component if is_capacitor(component) else getattr(component, "capacitor", None)
    if cap is None or not hasattr(cap, "linked_ppc") or not cap.charged:
        return
    ppc = cap.linked_ppc
    if cap.firing:
        config.log(f"      The {ppc.name} was declared firing this phase - its capacitor doesn't count as "
                   f"charged (p.188).")
        return
    from damage_resolution import apply_explosion
    set_charged(cap, False)
    for loc, slots in mech.crits.items():
        for i, s in enumerate(slots):
            if s is cap or s is ppc:
                mech.destroyed_slot_info[(loc, i)] = {"name": s.name, "instance_id": id(s)}
                slots[i] = "DESTROYED"
    cap.explosion_damage = 2 * (ppc.slots_occupied + cap.slots_occupied)
    config.log(f"      Charged PPC capacitor hit: the {ppc.name} and its capacitor are destroyed (p.188).")
    apply_explosion(mech, cap, location)
