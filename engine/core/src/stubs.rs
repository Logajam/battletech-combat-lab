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

fn round9(x: f64) -> f64 {
    format!("{:.9}", x).parse().unwrap()
}

/// Which ammunition kind / guidance / Apollo mode `weapon` fires. Knob: STUB_MUNITION_POLICY.
pub fn stub_munition_choice(b: &mut Battle, mech_name: &str, weapon: usize, unit: usize, options: &[(crate::fire_modes::ShotPlan, f64)], warn: bool) -> crate::fire_modes::ShotPlan {
    let policy = b.cfg.s("STUB_MUNITION_POLICY").to_string();
    let plain = |p: &crate::fire_modes::ShotPlan| (p.munition() == "standard" || p.munition() == "homing") && (p.kind.is_empty() || p.kind == "standard");
    let plan = if policy == "random" {
        let k = b.pick_number(options.len() as i64) as usize;
        options[k - 1].0.clone()
    } else if policy == "standard" {
        options.iter().find(|(p, _)| plain(p)).map_or(options[0].0.clone(), |(p, _)| p.clone())
    } else {
        let mut best = &options[0];
        for o in &options[1..] {
            let (kb, ko) = ((round9(best.1), plain(&best.0)), (round9(o.1), plain(&o.0)));
            if ko > kb {
                best = o;
            }
        }
        best.0.clone()
    };
    if warn {
        let wname = b.units[unit].items[weapon].name.clone();
        let shown: Vec<String> = options.iter().map(|(p, v)| format!("{} {}", if p.note().is_empty() { p.munition().to_string() } else { p.note() }, crate::pyfmt::Fx(*v, 2))).collect();
        let to = if plan.note().is_empty() { plan.munition().to_string() } else { plan.note() };
        b.warn_stub("munition_choice", &format!("{}'s {}: {} -> {} (policy {})", mech_name, wname, shown.join(", "), to, policy));
    }
    plan
}

/// Shots an Ultra / Rotary AC fires ([(shots, expected damage)]). Knob: STUB_RATE_OF_FIRE.
pub fn stub_rate_of_fire(b: &mut Battle, mech_name: &str, unit: usize, weapon: usize, priced: &[(i64, f64)], warn: bool) -> i64 {
    let policy = b.cfg.s("STUB_RATE_OF_FIRE").to_string();
    let shots = if policy == "single" {
        priced[0].0
    } else if policy == "greedy" {
        let mut best = priced[0];
        for o in &priced[1..] {
            // key (round(value, 9), -shots): the larger wins, first of equals
            if (round9(o.1), -o.0 as f64) > (round9(best.1), -best.0 as f64) {
                best = *o;
            }
        }
        best.0
    } else {
        priced[priced.len() - 1].0
    };
    if warn {
        let wname = b.units[unit].items[weapon].name.clone();
        b.warn_stub("rate_of_fire", &format!("{}'s {}: {} rates possible -> {} shot{} (policy {})", mech_name, wname, priced.len(), shots, if shots > 1 { "s" } else { "" }, policy));
    }
    shots
}

/// Try to unjam a jammed Rotary AC this turn. Knob: STUB_UNJAM (never while prone).
pub fn stub_unjam(b: &mut Battle, mech_name: &str, weapon_name: &str, prone: bool) -> bool {
    let attempt = b.cfg.get("STUB_UNJAM").as_bool().unwrap_or_else(|| b.cfg.get("STUB_UNJAM").as_i64().unwrap_or(0) != 0) && !prone;
    b.warn_stub("unjam", &format!("{}'s {} is jammed -> {}", mech_name, weapon_name, if attempt { "tries to unjam" } else { "stays jammed" }));
    attempt
}

/// Makes weapon_selection's silent skip of weapons with null damage / heat / range loud. They never fire.
pub fn stub_unconfirmed_weapon_data(b: &mut Battle, u: usize) {
    for w in crate::damage_resolution::get_weapons(&b.units[u]) {
        if crate::fire_modes::has_profile(b, u, w) {
            continue;
        }
        let it = &b.units[u].items[w];
        let mut missing: Vec<&str> = Vec::new();
        if it.damage_per_shot.is_none() {
            missing.push("damage_per_shot");
        }
        if it.heat.is_none() {
            missing.push("heat");
        }
        if it.weapon_range.is_none() {
            missing.push("weapon_range");
        }
        if !missing.is_empty() {
            let line = format!("{}'s {} can't fire - null {}", b.units[u].side_name.clone().unwrap_or_default(), it.name, missing.join(", "));
            b.warn_stub("unconfirmed_weapon_data", &line);
        }
    }
}
