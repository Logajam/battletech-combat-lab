// BattleROM E1 (core/src/human_bots.rs): a person's units answered by a controller that passes every question to the
// normal bot play the same battle as the plain bots (same log), and every question to the person is in the decision list.
// Uses the 2 v 2 mirror from engine/reference/scenarios.zip (unzipped into a temp folder, as tests/playout.rs does).
use btsim_core::gladiator_bots::GladiatorBots;
use btsim_core::human_bots::{Decision, HumanBots, PassThrough};
use btsim_core::scenario::Scenario;
use std::path::PathBuf;

fn two_v_two(test: &str) -> Scenario {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("reference").join("scenarios.zip");
    let dir = std::env::temp_dir().join(format!("human_bots_test_{}_{}", std::process::id(), test));
    let ok = std::process::Command::new("unzip").args(["-qo", root.to_str().unwrap(), "hy_2v2_grass/*", "-d", dir.to_str().unwrap()]).status().unwrap().success();
    assert!(ok, "unzip of the reference scenarios failed");
    Scenario::load(&dir.join("hy_2v2_grass"))
}

#[test]
fn a_pass_through_person_plays_the_plain_battle() {
    let sc = two_v_two("same");
    let (plain, plain_log) = sc.run_with(7, &mut GladiatorBots, true);
    let mut human = HumanBots::new(PassThrough, [0usize, 2]);
    let (res, log) = sc.run_with(7, &mut human, true);
    assert_eq!(plain_log, log, "the battle must not change when a person's units pass every question on");
    assert_eq!(plain.turns_taken, res.turns_taken);
    let moves = human.log.iter().filter(|d| matches!(d, Decision::Movement { .. })).count();
    let orders = human.log.iter().filter(|d| matches!(d, Decision::MoveOrder { .. })).count();
    assert!(moves > 0 && orders > 0, "the person's units were never asked ({} moves, {} orders)", moves, orders);
    assert!(human.log.iter().all(|d| match d {
        Decision::Movement { unit, .. } | Decision::Target { unit, .. } | Decision::Declaration { unit, .. } | Decision::Physical { unit, .. } => human.human.contains(unit),
        Decision::MoveOrder { chosen } => chosen < &4,
    }));
}
