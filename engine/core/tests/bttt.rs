//! BTTT's re-implemented bot (`bttt.rs`): it plays whole battles, walks the routes it picks, never moves backward, is deterministic, and
//! is a different player from Gladiator (its answers differ). Uses the duel and the 4 v 4 from engine/reference/scenarios.zip.
use btsim_core::scenario::Scenario;
use std::path::PathBuf;

fn scenario(test: &str, name: &str) -> Scenario {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("reference").join("scenarios.zip");
    let dir = std::env::temp_dir().join(format!("bttt_test_{}_{}", std::process::id(), test));
    let ok = std::process::Command::new("unzip").args(["-qo", root.to_str().unwrap(), &format!("{}/*", name), "-d", dir.to_str().unwrap()]).status().unwrap().success();
    assert!(ok, "unzip of the reference scenarios failed");
    Scenario::load(&dir.join(name))
}

#[test]
fn a_bttt_team_plays_a_whole_battle_and_walks_the_routes_it_picks() {
    let mut sc = scenario("route", "hy_4v4_heavy_hills");
    sc.bttt_teams = vec!["Red".to_string()];
    let (res, log, ev) = sc.run_events(5, true);
    assert!(res.turns_taken > 1, "the battle played");
    assert!(log.iter().any(|l| l.contains("[Movement select] Red") && l.contains("BTTT:")), "BTTT's own notes are in the log");
    let events = ev["events"].as_array().unwrap();
    let red_paths: Vec<_> = events.iter().filter(|e| e["k"] == "MOVE_PATH" && e["u"].as_str().is_some_and(|u| u.starts_with("Red"))).collect();
    assert!(red_paths.len() > 5, "BTTT's moves have routes ({})", red_paths.len());
    for p in &red_paths {
        let steps: Vec<&str> = p["w"].as_str().unwrap().split(' ').collect();
        assert!(steps.iter().all(|s| !s.contains("/B/")), "BTTT never moves backward: {}", p["w"]);
        assert_eq!(p["n"].as_u64().unwrap() as usize, steps.len());
    }
    // every MOVE_PATH ends at its MOVE's hex having spent its MP (the route walked is the route picked)
    for (i, e) in events.iter().enumerate().filter(|(_, e)| e["k"] == "MOVE_PATH") {
        let mv = &events[i - 1];
        let last: Vec<&str> = e["w"].as_str().unwrap().rsplit(' ').next().unwrap().split('/').collect();
        assert_eq!((mv["k"].as_str(), mv["w"].as_str(), mv["n"].as_i64()), (Some("MOVE"), Some(last[0]), Some(last[2].parse().unwrap())));
    }
}

#[test]
fn the_same_seed_gives_the_same_bttt_battle_and_it_is_not_gladiators_battle() {
    let mut a = scenario("same", "hy_duel_griffin");
    a.bttt_teams = vec!["Red".to_string()];
    let (r1, l1) = a.run(9, true);
    let (r2, l2) = a.run(9, true);
    assert_eq!(l1, l2, "deterministic: its 'random' unit order is a hash of the turn and the candidates, and nothing draws dice");
    assert_eq!(r1.turns_taken, r2.turns_taken);
    let plain = scenario("plain", "hy_duel_griffin");
    let (_, lp) = plain.run(9, true);
    assert_ne!(l1, lp, "a BTTT team does not play like a Gladiator team");
}

#[test]
fn weapons_are_dropped_by_damage_per_heat_until_the_shot_is_cool_enough_but_never_the_last() {
    use btsim_core::bttt::{choose_weapons, W};
    use btsim_core::dice::PcgDice;
    let sc = scenario("heat", "hy_duel_griffin");
    let mut b = sc.battle(Box::new(PcgDice::new(1)));
    let dissipation = btsim_core::mech_state::compute_heat_dissipation(&b.units[0]);
    // damage / heat per hit: 0 = 10 per 10 (1.0), 1 = 9 per 3 (3.0), 2 = 4 per 1 (4.0), 3 = 2 per 0 (free: never dropped), all hitting on a 2
    let ws: Vec<W> = [(10.0, 10), (9.0, 3), (4.0, 1), (2.0, 0)].iter().enumerate().map(|(i, &(dmg, heat))| W::simple(i, dmg, 2, heat)).collect();
    // cool unit, shot heat 14: net heat - 14 + 0 < 5 is false at once only if heat is high; with net heat 0 the 14 heat is over the cap, so drop the worst (1.0) -> 4 heat, under 5
    b.units[0].current_heat = dissipation;
    assert_eq!(choose_weapons(&b, 0, &ws), vec![1, 2, 3], "the least damage per heat goes first");
    // a unit already at its cap sheds more: net heat 3 - the 4 heat left is over 5-3 -> drops weapon 1 (3.0) next
    b.units[0].current_heat = dissipation + 3;
    assert_eq!(choose_weapons(&b, 0, &ws), vec![2, 3]);
    // hot enough that nothing helps: the free weapon and the best ratio stay, the last firing weapon is never dropped
    b.units[0].current_heat = dissipation + 40;
    let kept = choose_weapons(&b, 0, &ws);
    assert!(kept.contains(&3) && !kept.is_empty(), "{:?}", kept);
    // a lone hot weapon is kept whatever the heat
    assert_eq!(choose_weapons(&b, 0, &ws[..1]), vec![0]);
    // a cool shot drops nothing
    b.units[0].current_heat = 0;
    let cool: Vec<W> = vec![W::simple(0, 5.0, 4, 1), W::simple(1, 5.0, 4, 1)];
    assert_eq!(choose_weapons(&b, 0, &cool), vec![0, 1]);
}

#[test]
fn a_unit_whose_jets_outrun_its_legs_jumps_where_the_walk_ends_and_lands_within_its_jump_mp() {
    let mut sc = scenario("jump", "ref_Asymptote_vs_HeatGear_maxheat30_seed2");
    sc.bttt_teams = vec!["Red".to_string()];
    let (_, log, ev) = sc.run_events(1, true);
    let jumps: Vec<&String> = log.iter().filter(|l| l.contains("[Movement] Red:") && l.contains(", Jump (")).collect();
    assert!(!jumps.is_empty(), "BTTT jumped (its jump MP is above its running MP)");
    for l in &jumps {
        // "... Jump (5 MP, 5 hexes, 3 heat; budget walk 3 / run 4 / jump 5)": the jump costs its distance, within the jump MP, which is over the run MP
        let at = l.find("Jump (").unwrap();
        let tail: Vec<i64> = l[at..].split(|c: char| !c.is_ascii_digit()).filter(|x| !x.is_empty()).map(|x| x.parse().unwrap()).collect();
        let (mp, hexes, _heat, _walk, run, jump) = (tail[0], tail[1], tail[2], tail[3], tail[4], tail[5]);
        assert!(mp == hexes && mp <= jump && jump > run && mp > 0, "{}", l);
    }
    // a jump has no route: its MOVE is not followed by a MOVE_PATH
    let events = ev["events"].as_array().unwrap();
    for (i, e) in events.iter().enumerate().filter(|(_, e)| e["k"] == "MOVE" && e["s"] == "jump") {
        assert!(events.get(i + 1).map_or(true, |n| n["k"] != "MOVE_PATH" || n["u"] != e["u"]), "a jump carries no route");
    }
}

#[test]
fn a_step_refused_by_terrain_or_a_unit_can_be_jumped_over_even_when_the_jets_are_no_stronger_than_the_legs() {
    // Daniel, 2026-11-25: "If it walks the path, jump should happen if terrain gets in the way" (not in BTTT: it walks round). On the 8 v 8 valley a
    // BTTT unit whose jump MP does NOT exceed its run MP still jumps now and then: it can only be an obstruction.
    let mut sc = scenario("over", "hy_8v8_valley");
    sc.bttt_teams = vec!["Red".to_string()];
    let mut over = 0;
    for seed in 1..=3 {
        let (_, log) = sc.run(seed, true);
        for l in log.iter().filter(|l| l.contains("[Movement] Red") && l.contains(", Jump (")) {
            let at = l.find("Jump (").unwrap();
            let n: Vec<i64> = l[at..].split(|c: char| !c.is_ascii_digit()).filter(|x| !x.is_empty()).map(|x| x.parse().unwrap()).collect();
            let (mp, hexes, _heat, _walk, run, jump) = (n[0], n[1], n[2], n[3], n[4], n[5]);
            assert!(mp == hexes && mp <= jump && mp > 0, "a jump costs its distance within the jump MP: {}", l);
            if jump <= run {
                over += 1;
            }
        }
    }
    assert!(over > 0, "no jump over an obstruction was seen");
}

#[test]
fn bttts_piloting_modifiers_and_the_two_penalty_counts_on_a_real_unit() {
    use btsim_core::bttt::{psr_counts, psr_modifiers};
    use btsim_core::dice::PcgDice;
    let sc = scenario("psr", "hy_duel_griffin");
    let mut b = sc.battle(Box::new(PcgDice::new(1)));
    let legs = b.units[0].leg_locations.clone();
    assert_eq!(legs.len(), 2, "a biped");
    assert_eq!((psr_modifiers(&b.units[0]), psr_counts(&b.units[0])), (0, (0, 0)), "undamaged");
    // a damaged gyro: +3 (two hits: +6); it counts once for running
    b.units[0].gyro_hits = 1;
    assert_eq!((psr_modifiers(&b.units[0]), psr_counts(&b.units[0])), (3, (1, 1)));
    b.units[0].gyro_hits = 2;
    assert_eq!(psr_modifiers(&b.units[0]), 6);
    b.units[0].gyro_hits = 1;
    // a damaged hip: +2 and one more for running; a leg actuator on the OTHER leg: +1 each, and counts only for jumping
    b.units[0].destroyed_hip_locations.insert(legs[0].clone());
    b.units[0].destroyed_leg_actuators.insert(legs[1].clone(), 2);
    assert_eq!(psr_modifiers(&b.units[0]), 3 + 2 + 2);
    assert_eq!(psr_counts(&b.units[0]), (2, 4), "running: gyro + hip; jumping: and the two actuators");
    // an actuator on the leg with the bad hip is not counted (BTTT counts them on a leg with a good hip)
    b.units[0].destroyed_leg_actuators.insert(legs[0].clone(), 1);
    assert_eq!(psr_modifiers(&b.units[0]), 3 + 2 + 2);
    // a leg gone: half the legs or more is +5, and that leg's hip and actuators no longer count in the modifiers
    b.units[0].locations.get_mut(&legs[0]).unwrap().destroyed = true;
    assert_eq!(psr_modifiers(&b.units[0]), 3 + 2 + 5);
}

#[test]
fn a_bttt_unit_with_a_masc_switches_it_on_when_the_path_needs_it_and_the_engine_rolls_it() {
    let mut sc = scenario("masc", "cov_masc_always");
    sc.bttt_teams = vec!["Red".to_string(), "Blue".to_string()];
    let (_, log) = sc.run(1, true);
    assert!(log.iter().any(|l| l.contains("MASC (turn")), "the engine rolled a MASC for a BTTT unit: the bot asked for it");
}
