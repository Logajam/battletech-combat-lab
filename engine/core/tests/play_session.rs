// BattleROM E2-E6 (core/src/play_session.rs): a scripted player plays a whole battle through the same ask / answer
// interface the page uses. Every kind of question must come up and be answerable, and the battle must end.
// Uses the 2 v 2 mirror from engine/reference/scenarios.zip.
use btsim_core::dice::PcgDice;
use btsim_core::play_session::{play_blocking, Game, ReplayLink};
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
    let game = Game::start(Arc::new(sc), 3, vec![team], serde_json::Value::Null, None);
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
            "deploy" => json!({"hex": r["hexes"][0], "facing": "N"}),
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
            "stand_up" => json!({"stand": true}),
            "boost" => json!({"use": false}),
            "spot" | "tag" => json!({"target": null}),
            "end_phase" => json!({}),
            k => panic!("unknown kind {}", k),
        };
        game.answer(seq, ans).unwrap();
    }
    panic!("the battle did not end");
}

/// P15 step 2: a game played through the page's interface is written down ("orders"), and the list played back gives the SAME
/// battle: the same end, and the same history record (every step of every unit) as the original.
#[test]
fn a_recorded_game_replays_to_the_same_battle() {
    let sc = Arc::new(two_v_two("record"));
    let team = sc.battle(Box::new(PcgDice::new(1))).units[0].team.clone().unwrap();
    let game = Game::start(sc.clone(), 5, vec![team.clone()], json!({}), None);
    let end = play_scripted(&game);
    let orders = end["orders"].clone();
    assert_eq!(orders["order_format"], 1);
    assert!(orders["events"].as_array().unwrap().len() > 20, "the orders hold the game");
    eprintln!("SAVE SIZE: {} events, {} bytes of JSON for a {}-turn game", orders["events"].as_array().unwrap().len(), orders.to_string().len(), end["turns"]);
    // play the list back, on a thread with the engine's stack, and compare
    let (sc2, human, orders2) = (sc.clone(), vec![team], orders.clone());
    let again = std::thread::Builder::new().stack_size(64 << 20).spawn(move || {
        let link = ReplayLink::new(&orders2).unwrap();
        play_blocking(Arc::new(link), &sc2, 5, &human, &json!({}), None)
    }).unwrap().join().unwrap();
    for k in ["winner", "turns", "destroyed", "units", "decisions", "replay", "orders"] {
        assert_eq!(end[k], again[k], "the replayed game differs in '{}'", k);
    }
}

#[test]
fn a_replay_with_the_wrong_format_is_refused() {
    assert!(ReplayLink::new(&json!({"order_format": 99, "events": []})).is_err());
}

/// The scripted player's answers to whatever is asked, until the game is done; returns the end.
fn play_scripted(game: &Game) -> Value {
    let mut first_board: Option<bool> = None;
    let mut asked: Vec<Value> = Vec::new();
    loop {
        let p = game.poll(Duration::from_secs(60));
        match p["state"].as_str().unwrap() {
            "done" => {
                let mut end = p["end"].clone();
                end["first_request_had_board"] = json!(first_board);
                end["asked"] = json!(asked);
                return end;
            }
            "failed" => panic!("the engine stopped: {}", p["error"]),
            "waiting" => continue,
            _ => {}
        }
        let seq = p["seq"].as_u64().unwrap();
        let r = &p["request"];
        first_board.get_or_insert(r["board"].is_object());
        let team_of = |id: &Value| r["units"].as_array().and_then(|u| u.iter().find(|x| x["id"] == *id)).map(|x| x["team"].clone());
        asked.push(json!({"kind": r["kind"], "unit": r["unit"], "team": team_of(&r["unit"])}));
        let ans: Value = match r["kind"].as_str().unwrap() {
            "deploy" => json!({"hex": r["hexes"][0], "facing": "N"}),
            "move_order" => json!({"unit": r["candidates"][0]}),
            "movement" => match r["options"].as_array().unwrap().iter().max_by_key(|o| o["mp"].as_i64().unwrap()) {
                Some(o) => json!({"hex": o["hex"], "facing": o["facing"], "mode": o["mode"]}),
                None => json!({"stay": true}),
            },
            "target" => json!({"target": r["enemies"][0]["id"]}),
            "declaration" => json!({"weapons": r["weapons"].as_array().unwrap().iter().filter(|w| w["in_range"] == true && w["needs_twist"] == false).map(|w| w["id"].clone()).collect::<Vec<_>>()}),
            "physical" => json!({"kind": r["kinds"][0]["kind"]}),
            "stand_up" => json!({"stand": true}),
            "boost" => json!({"use": false}),
            "spot" | "tag" => json!({"target": null}),
            "end_phase" => json!({}),
            k => panic!("unknown kind {}", k),
        };
        game.answer(seq, ans).unwrap();
    }
}

/// P15: a game saved part-way (its order list cut anywhere: just after an answer, or while a question waits) and continued from
/// the save finishes as the uninterrupted game did: same end, same history record, same full order list.
#[test]
fn a_saved_game_continues_to_the_same_end() {
    let sc = Arc::new(two_v_two("resume"));
    let team = sc.battle(Box::new(PcgDice::new(1))).units[0].team.clone().unwrap();
    let whole = play_scripted(&Game::start(sc.clone(), 7, vec![team.clone()], json!({}), None));
    let events = whole["orders"]["events"].as_array().unwrap().clone();
    let n = events.len();
    assert!(n > 40);
    let mut cuts = vec![n / 4, n / 2, 3 * n / 4];
    // one cut at an answer and one at a post, so both kinds of save are tried
    cuts.push((n / 3..n).find(|&i| events[i].get("answer").is_some()).unwrap() + 1);
    cuts.push((n / 3..n).find(|&i| events[i].get("post").is_some()).unwrap() + 1);
    for cut in cuts {
        let mut saved = whole["orders"].clone();
        saved["events"] = json!(events[..cut]);
        let end = play_scripted(&Game::start(sc.clone(), 7, vec![team.clone()], json!({}), Some(saved)));
        for k in ["winner", "turns", "destroyed", "units", "decisions", "replay", "orders"] {
            assert_eq!(whole[k], end[k], "cut at event {} of {}: '{}' differs", cut, n, k);
        }
        // the first question the person sees after a resume carries the board (the page has none yet) as the first question of a new game does
        assert_eq!(end["first_request_had_board"], json!(true), "cut at event {}: the first live request lacks the board", cut);
    }
}

/// P4 / P15 step 3: a NEW TIMELINE. The list is cut just before a question and `{"reseed": n}` put there; played on from that save the
/// game keeps everything before the cut (same list), has the reseed in its list, and is itself a game that replays exactly (the
/// branch's own list, played back with no one at the keyboard, gives the same battle). Two branches on different seeds differ.
#[test]
fn a_branched_timeline_keeps_its_past_and_replays_exactly() {
    let sc = Arc::new(two_v_two("branch"));
    let team = sc.battle(Box::new(PcgDice::new(1))).units[0].team.clone().unwrap();
    let whole = play_scripted(&Game::start(sc.clone(), 7, vec![team.clone()], json!({}), None));
    let events = whole["orders"]["events"].as_array().unwrap().clone();
    // a question about a third of the way in: the cut goes just before its post
    let cut = (events.len() / 3..events.len()).find(|&i| events[i].get("post").is_some() && events[i]["post"]["kind"] == "movement").unwrap();
    let branch = |seed: u64| -> Value {
        let mut saved = whole["orders"].clone();
        let mut ev: Vec<Value> = events[..cut].to_vec();
        ev.push(json!({"reseed": seed.to_string()}));
        saved["events"] = json!(ev);
        play_scripted(&Game::start(sc.clone(), 7, vec![team.clone()], json!({}), Some(saved)))
    };
    let (a, a2, b) = (branch(1234), branch(1234), branch(98765));
    assert_eq!(a["orders"], a2["orders"], "the same branch twice is the same game");
    assert_eq!(a["first_request_had_board"], json!(true));
    let ev_a = a["orders"]["events"].as_array().unwrap();
    assert_eq!(&ev_a[..cut], &events[..cut], "the past before the cut is kept word for word");
    assert_eq!(ev_a[cut], json!({"reseed": "1234"}), "the new seed is in the list, where the timeline starts");
    assert_ne!(a["replay"], whole["replay"], "new dice give another battle");
    assert_ne!(a["replay"], b["replay"], "another seed gives another timeline");
    // the branch's own list, played back alone, is the same battle
    let (sc2, human, orders) = (sc.clone(), vec![team], a["orders"].clone());
    let again = std::thread::Builder::new().stack_size(64 << 20).spawn(move || {
        play_blocking(Arc::new(ReplayLink::new(&orders).unwrap()), &sc2, 7, &human, &json!({}), None)
    }).unwrap().join().unwrap();
    for k in ["winner", "turns", "destroyed", "units", "decisions", "replay", "orders"] {
        assert_eq!(a[k], again[k], "the branch replayed differs in '{}'", k);
    }
}

/// The step list of a finished game and a branch cut BEFORE step `j` (0-based): the flow events recorded when step j-1 was marked, and the number of
/// steps done. (INTEGRATION__ORDER_FORMAT.md "Branches by step".)
fn cut_before(whole: &Value, j: usize) -> (Vec<Value>, usize) {
    let events = whole["orders"]["events"].as_array().unwrap();
    let n = if j == 0 { 0 } else { whole["replay"]["steps"][j - 1]["orders"].as_u64().unwrap() as usize };
    (events[..n].to_vec(), j)
}

fn branch_event(after_step: usize, reseed: u64, control: Value, meddle: Value) -> Value {
    json!({"branch": {"after_step": after_step, "reseed": reseed.to_string(), "control": control, "meddle": meddle}})
}

fn team_of_unit(whole: &Value, label: &str) -> String {
    whole["replay"]["teams"][label].as_str().unwrap().to_string()
}

/// REC layer, Phase A: every replay step says what it is about and where in the order list it stands; each attacker's resolved fire is its own
/// step; a look at the record while the game waits changes nothing (the same game ends the same, the look is not in the list).
#[test]
fn steps_say_what_they_are_and_the_record_can_be_read_while_parked() {
    let sc = Arc::new(two_v_two("steps"));
    let team = sc.battle(Box::new(PcgDice::new(1))).units[0].team.clone().unwrap();
    let plain = play_scripted(&Game::start(sc.clone(), 7, vec![team.clone()], json!({}), None));
    let steps = plain["replay"]["steps"].as_array().unwrap();
    assert!(steps.iter().all(|s| s["k"].is_string() && s["orders"].is_u64()), "every step has a kind and an order count");
    let mut last = 0;
    for s in steps {
        let o = s["orders"].as_u64().unwrap();
        assert!(o >= last, "the order count never goes back");
        last = o;
    }
    let kinds: BTreeSet<&str> = steps.iter().map(|s| s["k"].as_str().unwrap()).collect();
    for k in ["deploy", "move", "fire", "fire_end", "heat"] {
        assert!(kinds.contains(k), "no '{}' step in {:?}", k, kinds);
    }
    assert!(steps.iter().filter(|s| s["k"] == "fire").all(|s| s["unit"].is_string() && s["target"].is_string()), "a fire step names the attacker and the target");
    // look at the record while the game is parked, a few times, then play on: the same game
    let game = Game::start(sc.clone(), 7, vec![team], json!({}), None);
    let mut looked = 0;
    let end = loop {
        let p = game.poll(Duration::from_secs(60));
        match p["state"].as_str().unwrap() {
            "done" => break p["end"].clone(),
            "failed" => panic!("the engine stopped: {}", p["error"]),
            "waiting" => continue,
            _ => {}
        }
        if looked < 3 && p["request"]["kind"] == "movement" {
            let h = game.query(json!({"q": "history"}), Duration::from_secs(60));
            assert_eq!(h["history"]["partial"], json!(true));
            assert!(h["history"]["steps"].as_array().unwrap().len() >= 1);
            looked += 1;
        }
        let seq = p["seq"].as_u64().unwrap();
        let r = &p["request"];
        let ans: Value = match r["kind"].as_str().unwrap() {
            "deploy" => json!({"hex": r["hexes"][0], "facing": "N"}),
            "move_order" => json!({"unit": r["candidates"][0]}),
            "movement" => match r["options"].as_array().unwrap().iter().max_by_key(|o| o["mp"].as_i64().unwrap()) {
                Some(o) => json!({"hex": o["hex"], "facing": o["facing"], "mode": o["mode"]}),
                None => json!({"stay": true}),
            },
            "target" => json!({"target": r["enemies"][0]["id"]}),
            "declaration" => json!({"weapons": r["weapons"].as_array().unwrap().iter().filter(|w| w["in_range"] == true && w["needs_twist"] == false).map(|w| w["id"].clone()).collect::<Vec<_>>()}),
            "physical" => json!({"kind": r["kinds"][0]["kind"]}),
            "stand_up" => json!({"stand": true}),
            "boost" => json!({"use": false}),
            "spot" | "tag" => json!({"target": null}),
            "end_phase" => json!({}),
            k => panic!("unknown kind {}", k),
        };
        game.answer(seq, ans).unwrap();
    };
    assert_eq!(looked, 3);
    for k in ["winner", "turns", "units", "replay", "orders"] {
        assert_eq!(plain[k], end[k], "looking at the record changed '{}'", k);
    }
}

/// A branch by step with only a reseed (nothing else changes): the past up to the cut is the same, the game after it is another, and the whole
/// list (flow + the branch event), played back, is the same game again.
#[test]
fn a_branch_by_step_keeps_its_past_and_replays_exactly() {
    let sc = Arc::new(two_v_two("bystep"));
    let team = sc.battle(Box::new(PcgDice::new(1))).units[0].team.clone().unwrap();
    let whole = play_scripted(&Game::start(sc.clone(), 7, vec![team.clone()], json!({}), None));
    let steps = whole["replay"]["steps"].as_array().unwrap();
    // cut before the first fire step of turn 2 or later: bots have moved, dice have been thrown
    let j = steps.iter().position(|s| s["k"] == "fire" && s["turn"].as_i64().unwrap() >= 2).unwrap();
    let (prefix, after) = cut_before(&whole, j);
    let mut saved = whole["orders"].clone();
    let mut ev = prefix.clone();
    ev.push(branch_event(after, 4242, json!([]), Value::Null));
    saved["events"] = json!(ev);
    let a = play_scripted(&Game::start(sc.clone(), 7, vec![team.clone()], json!({}), Some(saved.clone())));
    assert_eq!(&a["replay"]["steps"].as_array().unwrap()[..j], &steps[..j], "the steps before the cut are the same");
    assert_ne!(a["replay"], whole["replay"], "new dice from the cut on: the game after the cut is another");
    assert!(a["orders"]["events"].as_array().unwrap().iter().any(|e| e.get("branch").is_some()), "the branch is kept in the list");
    // the whole list again: the same game, nothing asked
    let again = play_scripted(&Game::start(sc.clone(), 7, vec![team], json!({}), Some(a["orders"].clone())));
    for k in ["winner", "turns", "units", "replay", "orders"] {
        assert_eq!(a[k], again[k], "the branch played back differs in '{}'", k);
    }
    assert_eq!(again["asked"], json!([]), "a complete list asks nothing");
}

/// CONTROL: the person's team handed to a bot plays the rest of the game by itself; a bot team handed to the person waits at that team's question.
#[test]
fn control_changes_hand_a_team_to_a_bot_or_to_the_person() {
    let sc = Arc::new(two_v_two("control"));
    let team = sc.battle(Box::new(PcgDice::new(1))).units[0].team.clone().unwrap();
    let whole = play_scripted(&Game::start(sc.clone(), 7, vec![team.clone()], json!({}), None));
    let steps = whole["replay"]["steps"].as_array().unwrap();
    let human_label = steps.iter().find(|s| s["k"] == "move").map(|s| s["unit"].as_str().unwrap().to_string()).unwrap();
    // find a step of the other team to cut before
    let other_team = whole["replay"]["team_order"].as_array().unwrap().iter().map(|t| t.as_str().unwrap().to_string()).find(|t| *t != team).unwrap();
    let j = steps.iter().position(|s| s["k"] == "fire" && s["turn"].as_i64().unwrap() >= 2).unwrap();
    let (prefix, after) = cut_before(&whole, j);
    let _ = human_label;

    // human -> bot: nothing is asked after the cut
    let mut saved = whole["orders"].clone();
    let mut ev = prefix.clone();
    ev.push(branch_event(after, 11, json!([{"team": team, "by": "gladiator"}]), Value::Null));
    saved["events"] = json!(ev);
    let a = play_scripted(&Game::start(sc.clone(), 7, vec![team.clone()], json!({}), Some(saved.clone())));
    let a2 = play_scripted(&Game::start(sc.clone(), 7, vec![team.clone()], json!({}), Some(saved)));
    assert_eq!(a["asked"], json!([]), "the team is a bot after the cut: nobody is asked");
    assert_eq!(a["replay"], a2["replay"], "the same branch is the same game");

    // bot -> human: the other team's questions come to the person after the cut
    let mut saved = whole["orders"].clone();
    let mut ev = prefix.clone();
    ev.push(branch_event(after, 12, json!([{"team": other_team, "by": "human"}]), Value::Null));
    saved["events"] = json!(ev);
    let b = play_scripted(&Game::start(sc.clone(), 7, vec![team.clone()], json!({}), Some(saved)));
    let asked = b["asked"].as_array().unwrap();
    assert!(asked.iter().any(|q| q["team"] == json!(other_team)), "the other team now asks the person: {:?}", asked);
    assert!(a["replay"] != b["replay"]);
}

/// MEDDLE: one decision of a bot team in one phase is the person's, whoever owns the team; then the team is the bot's again.
#[test]
fn a_meddle_asks_once_and_gives_the_team_back() {
    let sc = Arc::new(two_v_two("meddle"));
    let team = sc.battle(Box::new(PcgDice::new(1))).units[0].team.clone().unwrap();
    let whole = play_scripted(&Game::start(sc.clone(), 7, vec![team.clone()], json!({}), None));
    let steps = whole["replay"]["steps"].as_array().unwrap();
    let other_team = whole["replay"]["team_order"].as_array().unwrap().iter().map(|t| t.as_str().unwrap().to_string()).find(|t| *t != team).unwrap();
    // the bot team's own move in turn 2
    let j = steps.iter().position(|s| s["k"] == "move" && s["turn"].as_i64().unwrap() == 2 && team_of_unit(&whole, s["unit"].as_str().unwrap()) == other_team).unwrap();
    let (prefix, after) = cut_before(&whole, j);
    let mut saved = whole["orders"].clone();
    let mut ev = prefix;
    ev.push(branch_event(after, 77, json!([]), json!({"team": other_team, "phase": "move"})));
    saved["events"] = json!(ev);
    let m = play_scripted(&Game::start(sc.clone(), 7, vec![team.clone()], json!({}), Some(saved.clone())));
    let asked = m["asked"].as_array().unwrap();
    let other_moves = asked.iter().filter(|q| q["team"] == json!(other_team) && q["kind"] == "movement").count();
    assert_eq!(other_moves, 1, "the meddled move is asked once, then the bot has the team back: {:?}", asked);
    let other_later = asked.iter().skip_while(|q| q["team"] != json!(other_team)).filter(|q| q["team"] == json!(other_team)).count();
    assert!(other_later <= 3, "only that decision (and its unit choice) was the person's: {:?}", asked);
    // and it replays exactly
    let again = play_scripted(&Game::start(sc.clone(), 7, vec![team], json!({}), Some(m["orders"].clone())));
    assert_eq!(m["replay"], again["replay"]);
    assert_eq!(again["asked"], json!([]));
}

/// MEDDLE with a unit, at the start of the Fire phase (all declarations are made before any resolves, so the cut is before the phase's first fire
/// step and the person takes over ONE unit's declaration): only that unit is asked, and the team is the bot's again afterwards.
#[test]
fn a_meddle_with_a_unit_takes_over_that_units_fire_only() {
    let sc = Arc::new(two_v_two("meddle_unit"));
    let team = sc.battle(Box::new(PcgDice::new(1))).units[0].team.clone().unwrap();
    let whole = play_scripted(&Game::start(sc.clone(), 7, vec![team.clone()], json!({}), None));
    let steps = whole["replay"]["steps"].as_array().unwrap();
    let other_team = whole["replay"]["team_order"].as_array().unwrap().iter().map(|t| t.as_str().unwrap().to_string()).find(|t| *t != team).unwrap();
    // an attacker of the bot team, in a turn after the first: cut before the first fire step of that turn
    let s_i = steps.iter().position(|s| s["k"] == "fire" && s["turn"].as_i64().unwrap() >= 2 && team_of_unit(&whole, s["unit"].as_str().unwrap()) == other_team).unwrap();
    let (turn, unit) = (steps[s_i]["turn"].clone(), steps[s_i]["unit"].as_str().unwrap().to_string());
    let j = steps.iter().position(|s| s["turn"] == turn && s["k"] == "fire").unwrap();
    let (prefix, after) = cut_before(&whole, j);
    let mut saved = whole["orders"].clone();
    let mut ev = prefix;
    ev.push(branch_event(after, 5, json!([]), json!({"team": other_team, "phase": "fire", "unit": unit})));
    saved["events"] = json!(ev);
    let m = play_scripted(&Game::start(sc.clone(), 7, vec![team.clone()], json!({}), Some(saved)));
    let asked = m["asked"].as_array().unwrap();
    let theirs: Vec<&Value> = asked.iter().filter(|q| q["team"] == json!(other_team)).collect();
    assert!(!theirs.is_empty() && theirs.iter().all(|q| q["unit"] == theirs[0]["unit"]), "only one bot unit is asked: {:?}", asked);
    assert!(theirs.len() <= 3, "target / declaration of that one unit: {:?}", asked);
    let again = play_scripted(&Game::start(sc.clone(), 7, vec![team], json!({}), Some(m["orders"].clone())));
    assert_eq!(m["replay"], again["replay"]);
}
