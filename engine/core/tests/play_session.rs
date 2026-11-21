// BattleROM E2-E6 (core/src/play_session.rs): a scripted player plays a whole battle through the same ask / answer
// interface the page uses. Every kind of question must come up and be answerable, and the battle must end.
// Uses the 2 v 2 mirror from engine/reference/scenarios.zip.
use btsim_core::dice::PcgDice;
use btsim_core::play_session::Game;
use btsim_core::scenario::Scenario;
use serde_json::{json, Value};
use std::collections::BTreeSet;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

fn two_v_two(test: &str) -> Scenario {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("reference").join("scenarios.zip");
    let dir = std::env::temp_dir().join(format!("play_session_test_{}_{}", std::process::id(), test));
    let ok = std::process::Command::new("unzip").args(["-qo", root.to_str().unwrap(), "hy_2v2_grass/*", "-d", dir.to_str().unwrap()]).status().unwrap().success();
    assert!(ok, "unzip of the reference scenarios failed");
    Scenario::load(&dir.join("hy_2v2_grass"))
}

#[test]
fn a_scripted_player_plays_a_battle_to_its_end() {
    let sc = two_v_two("play");
    let team = sc.battle(Box::new(PcgDice::new(1))).units[0].team.clone().unwrap();
    let game = Game::start(Arc::new(sc), 3, vec![team]);
    let mut kinds: BTreeSet<String> = BTreeSet::new();
    let mut wrong_once = false;
    let mut turns_seen = 0;
    for _ in 0..20000 {
        let p = game.poll(Duration::from_secs(60));
        match p["state"].as_str().unwrap() {
            "done" => {
                assert!(p["end"]["decisions"].as_u64().unwrap() > 10);
                eprintln!("kinds asked: {:?}; turns {}; winner {}", kinds, p["end"]["turns"], p["end"]["winner"]);
                for k in ["move_order", "movement", "target", "declaration"] {
                    assert!(kinds.contains(k), "never asked {}", k);
                }
                assert!(wrong_once, "the illegal-answer path was not exercised");
                return;
            }
            "failed" => panic!("the engine stopped: {}", p["error"]),
            "waiting" => continue,
            _ => {}
        }
        let seq = p["seq"].as_u64().unwrap();
        let r = &p["request"];
        let kind = r["kind"].as_str().unwrap().to_string();
        kinds.insert(kind.clone());
        if r["units"].as_array().map_or(0, |u| u.len()) == 0 {
            panic!("no units in the request");
        }
        if turns_seen == 0 {
            assert!(r["board"].is_object(), "the first request carries the board");
            turns_seen = 1;
        }
        // answer one question wrongly, once, to see it asked again with an error
        if !wrong_once && kind == "target" {
            game.answer(seq, json!({"target": 9999})).unwrap();
            let again = game.poll(Duration::from_secs(60));
            assert_eq!(again["request"]["kind"], "target");
            assert!(again["request"]["error"].is_string());
            wrong_once = true;
            let seq2 = again["seq"].as_u64().unwrap();
            let first = again["request"]["enemies"][0]["id"].clone();
            game.answer(seq2, json!({"target": first})).unwrap();
            continue;
        }
        let ans: Value = match kind.as_str() {
            "move_order" => json!({"unit": r["candidates"][0]}),
            "movement" => {
                // the farthest-forward legal state this unit can reach, by MP spent: any legal option will do
                let o = r["options"].as_array().unwrap().iter().max_by_key(|o| o["mp"].as_i64().unwrap()).cloned();
                match o {
                    Some(o) => json!({"hex": o["hex"], "facing": o["facing"], "mode": o["mode"]}),
                    None => json!({"stay": true}),
                }
            }
            "target" => json!({"target": r["enemies"][0]["id"]}),
            "declaration" => {
                let ids: Vec<Value> = r["weapons"].as_array().unwrap().iter().filter(|w| w["in_range"] == true && w["needs_twist"] == false).map(|w| w["id"].clone()).collect();
                json!({"weapons": ids})
            }
            "physical" => json!({"kind": r["kinds"][0]["kind"]}),
            k => panic!("unknown kind {}", k),
        };
        game.answer(seq, ans).unwrap();
    }
    panic!("the battle did not end");
}
