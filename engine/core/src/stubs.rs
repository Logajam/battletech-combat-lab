// Translated from INTEGRATION__stubs.py (session 22): the placeholder decisions, loud and counted. Stage 4 part: those
// that do not need the weapon-profile / fire-mode types (munition choice, rate of fire come with stage 5).
use crate::battle::Battle;

/// Start the battle with this PPC's capacitor charged? Knob: STUB_CAPACITOR_START.
pub fn stub_capacitor_start(b: &mut Battle, mech_name: &str, ppc_name: &str) -> bool {
    let on = b.cfg.s("STUB_CAPACITOR_START") == "charged";
    b.warn_stub("capacitor_start", &format!("{}: {} capacitor starts {}", mech_name, ppc_name, if on { "charged" } else { "empty" }));
    on
}

/// Charge this PPC's capacitor instead of firing it this turn? Knob: STUB_CAPACITOR_CHARGE.
pub fn stub_capacitor_charge(b: &mut Battle, mech_name: &str, ppc_name: &str) -> bool {
    let on = b.cfg.s("STUB_CAPACITOR_CHARGE") == "when_idle";
    b.warn_stub("capacitor_charge", &format!("{}: {} the {} capacitor", mech_name, if on { "charge" } else { "leave empty" }, ppc_name));
    on
}

/// Use MASC / supercharger / radical heat sinks this turn? Knob: STUB_ESCALATING_USE.
pub fn stub_escalating_use(b: &mut Battle, mech_name: &str, label: &str, cycle_on: bool, warn: bool) -> bool {
    let policy = b.cfg.s("STUB_ESCALATING_USE").to_string();
    let used = if policy == "cycle" { cycle_on } else { policy == "always" };
    if warn {
        b.warn_stub("escalating_use", &format!("{}'s {}: {} this turn (policy {})", mech_name, label, if used { "used" } else { "not used" }, policy));
    }
    used
}

/// Declare torso spikes for a charge? Knob: STUB_CHARGE_SPIKES.
pub fn stub_charge_spikes(b: &mut Battle, mech_name: &str, clusters: i64) -> bool {
    let used = b.cfg.b("STUB_CHARGE_SPIKES");
    b.warn_stub("charge_spikes", &format!("{}'s {} torso spike cluster(s): {} in the charge", mech_name, clusters, if used { "used" } else { "not used" }));
    used
}

/// Activate a vibroblade for this attack? Knob: STUB_VIBROBLADE.
pub fn stub_vibroblade(b: &mut Battle, mech_name: &str, blade: &str, warn: bool) -> bool {
    let on = b.cfg.s("STUB_VIBROBLADE") == "on";
    if warn {
        b.warn_stub("vibroblade", &format!("{}'s {}: {}", mech_name, blade, if on { "activated" } else { "not activated" }));
    }
    on
}

/// Raise a shield this phase? Returns the arm to raise, or None. Knob: STUB_RAISE_SHIELD.
pub fn stub_raise_shield(b: &mut Battle, mech_name: &str, phase: &str, arms: &[String]) -> Option<String> {
    let arm = if b.cfg.s("STUB_RAISE_SHIELD") == "always" && !arms.is_empty() { Some(arms[0].clone()) } else { None };
    let what = match &arm {
        Some(a) => format!("raises its {} shield", a),
        None => "keeps its shield lowered".to_string(),
    };
    b.warn_stub("raise_shield", &format!("{} ({}): {}", mech_name, phase, what));
    arm
}

/// End Phase: swap the pilot and the command console's warrior? Knob: STUB_CONSOLE_SWAP.
pub fn stub_console_swap(b: &mut Battle, mech_name: &str, pilot_hits: i64, secondary_hits: i64, pilot_out: bool) -> bool {
    let swap = b.cfg.s("STUB_CONSOLE_SWAP") == "when_needed" && (pilot_out || pilot_hits > secondary_hits) && secondary_hits < 6;
    b.warn_stub(
        "console_swap",
        &format!("{}: pilot {} hits{}, console {} - {}", mech_name, pilot_hits, if pilot_out { " (out)" } else { "" }, secondary_hits, if swap { "swap" } else { "no swap" }),
    );
    swap
}

/// Switch the Blue Shield on? Asked at the start and each End Phase. Knob: STUB_BLUE_SHIELD.
pub fn stub_blue_shield(b: &mut Battle, mech_name: &str, when: &str) -> bool {
    let on = b.cfg.s("STUB_BLUE_SHIELD") == "on";
    b.warn_stub("blue_shield", &format!("{} ({}): Blue Shield {}", mech_name, when, if on { "on" } else { "off" }));
    on
}

/// Fire TAG at the enemy this turn? Knob: STUB_FIRE_TAG.
pub fn stub_fire_tag(b: &mut Battle, mech_name: &str, useful: bool) -> bool {
    let policy = b.cfg.s("STUB_FIRE_TAG").to_string();
    let fire = policy == "always" || (policy == "when_useful" && useful);
    b.warn_stub("fire_tag", &format!("{}: {} TAG ({})", mech_name, if fire { "fires" } else { "holds" }, if useful { "useful" } else { "nothing uses it" }));
    fire
}

/// TAG the enemy 'Mech or the ground it stands on? Knob: STUB_TAG_AIM. Returns "mech" or "hex".
pub fn stub_tag_aim(b: &mut Battle, mech_name: &str, tn_mech: Option<i64>, tn_hex: Option<i64>) -> &'static str {
    let policy = b.cfg.s("STUB_TAG_AIM").to_string();
    let aim = if tn_mech.is_none() || (policy == "hex" && tn_hex.is_some()) {
        "hex"
    } else if policy == "easier" && tn_hex.is_some() && tn_hex.unwrap() < tn_mech.unwrap() {
        "hex"
    } else {
        "mech"
    };
    let opt = |o: Option<i64>| o.map_or("None".to_string(), |n| n.to_string());
    b.warn_stub("tag_aim", &format!("{}: TAG the {} (needs mech {}, hex {}; policy {})", mech_name, if aim == "hex" { "ground" } else { "Mech" }, opt(tn_mech), opt(tn_hex), policy));
    aim
}

/// This weapon's shots per ton isn't in equipment.json: its ammo is unlimited. Warns each time it fires.
pub fn stub_ammo_data(b: &mut Battle, mech_name: &str, weapon_name: &str) {
    b.warn_stub("ammo_data", &format!("{}'s {} fired with unlimited ammo (no shots-per-ton data)", mech_name, weapon_name));
}

/// Which ammo bin explodes from heat among the tied ones: a seeded random pick. `tied`: (location, bin name) pairs;
/// returns the index picked.
pub fn stub_heat_explosion_bin(b: &mut Battle, mech_name: &str, tied: &[(String, String)], damage_value: i64, unknown_names: &[String]) -> usize {
    let pick = (b.pick_number(tied.len() as i64) - 1) as usize;
    let mut notes: Vec<String> = Vec::new();
    if !unknown_names.is_empty() {
        let mut names: Vec<String> = unknown_names.to_vec();
        names.sort();
        names.dedup();
        notes.push(format!("unknown damage value for {} (counted as 0)", crate::damage_resolution::py_str_list(&names)));
    }
    if tied.len() > 1 {
        notes.push(format!("{} bins tie at damage value {} and shots left; controller's choice made at random", tied.len(), damage_value));
    }
    b.warn_stub("heat_explosion_bin", &format!("{}: {} -> {} in {}", mech_name, notes.join("; "), tied[pick].1, tied[pick].0));
    pick
}
