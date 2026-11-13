//! Charge / DFA targets (Core p.78): a 'Mech that has declared its own charge or DFA has not finished moving, so it
//! can't be charged or DFA'd. Combat Lab crash, 2026-11-13: two 'Mechs charged each other; the first charge resolved
//! moved its attacker into the other's hex, and the second charge then had no direction (both in one hex) - a panic in
//! attack_resolution::attack_side. The rule stops the mutual charge from being declared at all.
use btsim_core::dice::PcgDice;
use btsim_core::move_attacks::can_be_attacked;
use btsim_core::scenario::Scenario;
use std::path::PathBuf;

fn two_v_two(test: &str) -> btsim_core::battle::Battle {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("reference").join("scenarios.zip");
    let dir = std::env::temp_dir().join(format!("charge_targets_test_{}_{}", std::process::id(), test));
    let ok = std::process::Command::new("unzip").args(["-qo", root.to_str().unwrap(), "hy_2v2_grass/*", "-d", dir.to_str().unwrap()]).status().unwrap().success();
    assert!(ok, "unzip of the reference scenarios failed");
    let mut b = Scenario::load(&dir.join("hy_2v2_grass")).battle(Box::new(PcgDice::new(1)));
    for (u, hex) in ["0305", "0309", "1305", "1309"].iter().enumerate() {
        b.units[u].hex = Some(hex.to_string());
    }
    b
}

#[test]
fn a_mech_mid_charge_or_dfa_is_not_a_charge_target() {
    let mut b = two_v_two("targets");
    let (charger, target) = (0, 2);
    // a 'Mech that has finished moving can be charged
    assert!(can_be_attacked(&mut b, target, true));
    // one that has declared a charge has not finished moving (p.78)
    b.units[target].charging = Some(charger);
    assert!(!can_be_attacked(&mut b, target, true));
    b.units[target].charging = None;
    // nor one making a death from above
    b.units[target].dfa = Some(charger);
    assert!(!can_be_attacked(&mut b, target, true));
}

/// Core p.76: a charge's damage is dealt from where both 'Mechs stood, and its displacement waits for the end of the
/// phase. Then a target already moved by an earlier displacement is not displaced again; the charger advances into the
/// hex it charged.
#[test]
fn a_charge_displaces_after_all_attacks_and_skips_a_mech_already_moved() {
    use btsim_core::charge;
    // the plain case: the target is pushed one hex on, the charger advances into its hex
    let mut b = two_v_two("plain");
    b.units[2].hex = Some("0306".into());
    let h = charge::resolve_damage(&mut b, 0, 2);
    assert_eq!(b.units[2].hex.as_deref(), Some("0306"), "damage alone moves nobody");
    charge::resolve_displacement(&mut b, &h);
    assert_eq!(b.units[2].hex.as_deref(), Some("0307"));
    assert_eq!(b.units[0].hex.as_deref(), Some("0306"));
    // the target was displaced elsewhere between the damage and this charge's displacement
    let mut b = two_v_two("moved");
    b.units[2].hex = Some("0306".into());
    let h = charge::resolve_damage(&mut b, 0, 2);
    b.units[2].hex = Some("0408".into());
    let triggers = charge::resolve_displacement(&mut b, &h);
    assert_eq!(b.units[2].hex.as_deref(), Some("0408"), "not displaced a second time");
    assert_eq!(b.units[0].hex.as_deref(), Some("0306"), "the charger advances into the hex it charged");
    let t_name = b.units[2].side_name.clone().unwrap();
    assert!(triggers[&t_name].iter().any(|(why, _)| why == "charged"), "the target still makes its PSR");
}
