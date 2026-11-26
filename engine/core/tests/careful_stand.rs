//! Careful stand (TO:AR p.22): one attempt, the whole Movement Phase, -2 with more than 2 Walking MP.
use btsim_core::dice::PcgDice;
use btsim_core::piloting_rolls as pr;
use btsim_core::scenario::Scenario;
use std::path::PathBuf;

fn battle(test: &str, seed: u64) -> btsim_core::battle::Battle {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("reference").join("scenarios.zip");
    let dir = std::env::temp_dir().join(format!("careful_stand_test_{}_{}", std::process::id(), test));
    let ok = std::process::Command::new("unzip").args(["-qo", root.to_str().unwrap(), "hy_2v2_grass/*", "-d", dir.to_str().unwrap()]).status().unwrap().success();
    assert!(ok, "unzip of the reference scenarios failed");
    Scenario::load(&dir.join("hy_2v2_grass")).battle(Box::new(PcgDice::new(seed)))
}

/// The target number printed for a careful stand against the normal stand's, same unit: 2 lower (it has more than 2 Walking MP).
#[test]
fn careful_stand_is_two_easier_and_one_attempt() {
    let tn = |careful: bool| -> i64 {
        let mut b = battle(if careful { "c" } else { "n" }, 7);
        b.units[0].prone = true;
        assert!(btsim_core::mech_state::compute_walk_mp(&b.units[0]) > 2, "the test unit needs more than 2 Walking MP");
        if careful {
            b.with_piloting(0, |b| pr::resolve_careful_stand(b, 0));
        } else {
            b.with_piloting(0, |b| pr::resolve_stand_up(b, 0, None));
        }
        let line = b.log.lines.iter().find(|l| l.contains("needs ")).expect("a stand roll line").clone();
        let after = line.split("needs ").nth(1).unwrap();
        after.split_whitespace().next().unwrap().parse().unwrap()
    };
    assert_eq!(tn(false) - tn(true), 2, "careful stand with more than 2 Walking MP is -2");
    // many seeds: one attempt only, so at most one "needs" line, and never any remaining MP
    for seed in 0..40 {
        let mut b = battle("seeds", seed);
        b.units[0].prone = true;
        b.with_piloting(0, |b| pr::resolve_careful_stand(b, 0));
        let attempts = b.log.lines.iter().filter(|l| l.contains("needs ")).count();
        assert_eq!(attempts, 1, "a careful stand is one attempt (seed {})", seed);
    }
}
