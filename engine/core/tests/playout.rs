// Hydra's S5a groundwork (session 25, core/src/playout.rs): a pose is undone exactly, and the witness sees any change.
// Uses the 2 v 2 mirror from engine/reference/scenarios.zip (unpacked with the `unzip` command into a temp folder).
use btsim_core::dice::PcgDice;
use btsim_core::playout::{Pose, Poses, Witness};
use btsim_core::scenario::Scenario;
use std::path::PathBuf;

fn two_v_two(test: &str) -> btsim_core::battle::Battle {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("reference").join("scenarios.zip");
    let dir = std::env::temp_dir().join(format!("playout_test_{}_{}", std::process::id(), test));
    let ok = std::process::Command::new("unzip").args(["-qo", root.to_str().unwrap(), "hy_2v2_grass/*", "-d", dir.to_str().unwrap()]).status().unwrap().success();
    assert!(ok, "unzip of the reference scenarios failed");
    let mut b = Scenario::load(&dir.join("hy_2v2_grass")).battle(Box::new(PcgDice::new(1)));
    // stand the four units on the board, as after deployment
    for (u, hex) in ["0305", "0309", "1305", "1309"].iter().enumerate() {
        b.units[u].hex = Some(hex.to_string());
    }
    b
}

#[test]
fn a_pose_is_undone_exactly_and_the_witness_agrees() {
    let mut b = two_v_two("pose");
    let before = Witness::now(&b);
    let mut poses = Poses::new();
    let moved = Pose { hex: Some("0707".into()), facing: "SE".into(), move_mode: "Run".into(), move_fc: 5, mp_spent: 6, movement_heat: 2, moved_this_turn: true };
    poses.pose(&mut b, 0, &moved);
    assert_eq!(Pose::of(&b, 0), moved);
    assert!(poses.holds_hex(&b, "0707"));
    // the witness sees a posed unit as a change
    assert!(before.difference(&b).is_some());
    let jumped = Pose { hex: Some("1107".into()), facing: "NW".into(), move_mode: "Jump".into(), move_fc: 4, mp_spent: 4, movement_heat: 4, moved_this_turn: true };
    poses.pose(&mut b, 2, &jumped);
    poses.pose(&mut b, 0, &jumped); // the same unit twice: restore must still reach the first pose's original
    assert_eq!(poses.len(), 3);
    poses.restore(&mut b);
    assert!(poses.is_empty());
    assert_eq!(before.difference(&b), None);
}

#[test]
fn the_witness_sees_dice_and_log_lines() {
    let mut b = two_v_two("witness");
    let w = Witness::now(&b);
    b.roll_2d6();
    assert!(w.difference(&b).unwrap().contains("dice"));
    let w = Witness::now(&b);
    b.log("a line");
    assert!(w.difference(&b).unwrap().contains("log"));
}

#[test]
#[should_panic(expected = "still in place")]
fn dropping_poses_without_restore_is_loud() {
    let mut b = two_v_two("drop");
    let mut poses = Poses::new();
    let p = Pose::of(&b, 1);
    poses.pose(&mut b, 1, &p);
    drop(poses);
}
