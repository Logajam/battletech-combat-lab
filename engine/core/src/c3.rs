//! C3 NETWORKS (backlog N6; Daniel, 2026-11-20: "C3 Networks. I think we can wire this in. ... setting up the network will
//! have to be part of that configuration window. Note that connecting to a network increases a units BV."). Rust only.
//!
//! THE RULES (Core Rulebook):
//!   p.198 C3 COMPUTER: a networked 'Mech takes its RANGE MODIFIER from the distance between the target and the closest
//!     network member that can see it (levels ignored). Only the range modifier changes: minimum and maximum range, line of
//!     sight and everything else that reads the attacker's own distance stay as they are. Only units on the board count;
//!     a network needs its Master: when the Master is destroyed the network it runs is disabled. C3 does not help indirect
//!     fire (p.70). A unit belongs to one network.
//!   p.198 DESIGNATING: a Master controls one to three Slaves, or one to three Masters (never both): a lance network of up to
//!     4, and a company Master over up to three lance Masters, at most 12 'Mechs. Slaves may all be Masters instead.
//!   p.199 ECM: if the attacker, the closest member or that unit's Master stands within 6 hexes (p.200) of hostile ECM, an
//!     attack whose range bracket C3 improved by one (two) brackets takes +1 (+2); a network uses an undegraded member when
//!     it can; a Master in hostile ECM degrades all its Slaves. STEALTH: a unit with an active stealth system other than the
//!     Chameleon LPS is cut off from its network. C3 BOOSTED: only Angel ECM degrades it. C3i: no Master; up to six
//!     'Mechs, every one alike; for ECM every member counts as a Slave.
//!   p.220 BATTLE VALUE: each unit of a network costs +10% for a two-unit network, +5% for each unit beyond (at most +40%),
//!     and a Boosted member +5% more.
//! HOW IT RUNS HERE. The setup names each unit's link (a FORCES entry's "c3": {"parent": "<side name>"} for C3 Master /
//! Slave, {"net": "<name>"} for C3i; the Combat Lab's Configure team window writes them). A link the rules do not allow is
//! dropped with a log line when the battle starts (`check_networks`). An attack asks `best` for the closest member's
//! distance (attack_resolution's Adjuster turns it into the range change and the ECM penalty). NOT BUILT: the C3 Master's
//! TAG function (p.199), the C3 Emergency Master and the remote sensors (TO:AUE).
use crate::battle::{Battle, UnitId};
use crate::los::hex_distance;

/// Hostile ECM's effect radius (p.200).
pub const ECM_RADIUS: i64 = 6;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    Master { boosted: bool },
    Slave { boosted: bool },
    C3i,
}

fn norm(s: &str) -> String {
    s.to_uppercase().replace([' ', '-', '_'], "")
}

/// The working C3 a 'Mech carries (destroyed equipment drops out). A 'Mech with both a Master and a Slave uses the Master
/// when the setup gives it Slaves, else the Slave (p.198: one of them is designated at the start).
pub fn kind_of(b: &Battle, u: UnitId) -> Option<Kind> {
    let m = &b.units[u];
    let dead = crate::electronics::dead(m);
    let mut master = None;
    let mut slave = None;
    let mut c3i = false;
    for (id, e) in m.items.iter().enumerate() {
        if dead.contains(&id) {
            continue;
        }
        let n = norm(e.canonical.as_deref().unwrap_or(&e.name));
        if n.contains("C3I") || n.contains("IMPROVEDC3") {
            c3i = true;
        } else if n.contains("C3MASTER") || n.contains("C3COMPUTER[MASTER]") {
            master = Some(n.contains("BOOSTED"));
        } else if n.contains("C3SLAVE") || n.contains("C3BOOSTEDSYSTEMSLAVE") || n.contains("C3COMPUTER[SLAVE]") {
            slave = Some(n.contains("BOOSTED"));
        }
    }
    if c3i {
        return Some(Kind::C3i);
    }
    let name = m.side_name.clone();
    let has_children = name.is_some() && b.units.iter().any(|o| o.team == m.team && o.c3_parent == name);
    match (master, slave) {
        (Some(bm), Some(_)) if has_children => Some(Kind::Master { boosted: bm }),
        (Some(bm), None) => Some(Kind::Master { boosted: bm }),
        (_, Some(bs)) => Some(Kind::Slave { boosted: bs }),
        _ => None,
    }
}

fn unit_named(b: &Battle, team: &Option<String>, name: &str) -> Option<UnitId> {
    (0..b.units.len()).find(|&o| b.units[o].team == *team && b.units[o].side_name.as_deref() == Some(name))
}

/// The battle start: every link the rules do not allow is dropped, with the reason in the log (p.198).
pub fn check_networks(b: &mut Battle) {
    for u in 0..b.units.len() {
        let name = b.units[u].side_name.clone().unwrap_or_default();
        if let Some(parent) = b.units[u].c3_parent.clone() {
            let why = match (kind_of(b, u), unit_named(b, &b.units[u].team.clone(), &parent)) {
                (None, _) | (Some(Kind::C3i), _) => Some("it carries no C3 Master or Slave".to_string()),
                (_, None) => Some(format!("there is no {} on its team", parent)),
                (_, Some(p)) if p == u => Some("a unit cannot link to itself".to_string()),
                (Some(k), Some(p)) => match kind_of(b, p) {
                    Some(Kind::Master { .. }) => {
                        let siblings: Vec<UnitId> = (0..b.units.len()).filter(|&o| b.units[o].team == b.units[u].team && b.units[o].c3_parent.as_deref() == Some(parent.as_str())).collect();
                        let masters = siblings.iter().filter(|&&o| matches!(kind_of(b, o), Some(Kind::Master { .. }))).count();
                        if siblings.len() > 3 {
                            Some(format!("{} already controls three units", parent))
                        } else if masters > 0 && masters < siblings.len() {
                            Some(format!("{} cannot control Masters and Slaves at once", parent))
                        } else if matches!(k, Kind::Master { .. }) && b.units[p].c3_parent.is_some() {
                            Some("a company network has only two levels".to_string())
                        } else {
                            None
                        }
                    }
                    _ => Some(format!("{} carries no C3 Master", parent)),
                },
            };
            if let Some(why) = why {
                b.log(format!("  [C3] {}: link to {} dropped - {} (p.198).", name, parent, why));
                b.units[u].c3_parent = None;
            }
        }
        if b.units[u].c3_net.is_some() && kind_of(b, u) != Some(Kind::C3i) {
            b.log(format!("  [C3] {}: C3i network dropped - it carries no C3i computer (p.199).", name));
            b.units[u].c3_net = None;
        }
    }
    // a C3i network holds at most six (p.199): the seventh and later are left out
    let mut counts: Vec<(Option<String>, String, usize)> = Vec::new();
    for u in 0..b.units.len() {
        let Some(net) = b.units[u].c3_net.clone() else { continue };
        let team = b.units[u].team.clone();
        let n = match counts.iter_mut().find(|(t, x, _)| *t == team && *x == net) {
            Some(c) => {
                c.2 += 1;
                c.2
            }
            None => {
                counts.push((team, net, 1));
                1
            }
        };
        if n > 6 {
            let name = b.units[u].side_name.clone().unwrap_or_default();
            b.log(format!("  [C3] {}: left out of C3i network {} - a C3i network holds six (p.199).", name, b.units[u].c3_net.clone().unwrap()));
            b.units[u].c3_net = None;
        }
    }
}

/// The units of `u`'s configured network (whatever their state): the tree its C3 links make, or its C3i network.
pub fn configured_network(b: &Battle, u: UnitId) -> Vec<UnitId> {
    let team = &b.units[u].team;
    if let Some(net) = &b.units[u].c3_net {
        return (0..b.units.len()).filter(|&o| b.units[o].team == *team && b.units[o].c3_net.as_ref() == Some(net)).collect();
    }
    // the top of the tree, then everything under it
    let mut top = u;
    for _ in 0..3 {
        match b.units[top].c3_parent.as_deref().and_then(|p| unit_named(b, team, p)) {
            Some(p) => top = p,
            None => break,
        }
    }
    let mut out = vec![top];
    let mut i = 0;
    while i < out.len() {
        let name = b.units[out[i]].side_name.clone();
        for o in 0..b.units.len() {
            if b.units[o].team == *team && b.units[o].c3_parent.is_some() && b.units[o].c3_parent == name && !out.contains(&o) {
                out.push(o);
            }
        }
        i += 1;
    }
    if out.len() < 2 { vec![u] } else { out }
}

/// The battle-value increase of `u`'s network (p.220): +10% for two units, +5% for each more, at most +40%; +5% more
/// for a Boosted member. 0 for a unit in no network.
pub fn bv_increase(b: &Battle, u: UnitId) -> f64 {
    let n = configured_network(b, u).len();
    if n < 2 {
        return 0.0;
    }
    let mut pct = (0.10 + 0.05 * (n as f64 - 2.0)).min(0.40);
    if matches!(kind_of(b, u), Some(Kind::Master { boosted: true }) | Some(Kind::Slave { boosted: true })) {
        pct += 0.05;
    }
    pct
}

fn xy(b: &Battle, u: UnitId) -> Option<(i64, i64)> {
    b.units[u].hex.as_deref().and_then(|h| crate::hex_geometry::parse_hex_label(h).ok())
}

/// Can this unit take part in its network now? On the board, standing, powered, its C3 working, not cut off by stealth.
fn live(b: &mut Battle, u: UnitId) -> bool {
    if b.units[u].hex.is_none() || b.units[u].shutdown || b.is_destroyed(u) || kind_of(b, u).is_none() {
        return false;
    }
    !crate::equipment_systems::active_stealth(&b.units[u]).iter().any(|k| *k != "chameleon")
}

/// The members of `u`'s network that are linked to it now (a Slave or lance cut off from a lost Master drops out).
pub fn active_network(b: &mut Battle, u: UnitId) -> Vec<UnitId> {
    if !live(b, u) {
        return vec![u];
    }
    let all = configured_network(b, u);
    if all.len() < 2 {
        return vec![u];
    }
    if b.units[u].c3_net.is_some() {
        return all.into_iter().filter(|&o| o == u || live(b, o)).collect();
    }
    // the links that work: both ends live; then everything joined to u by working links
    let team = b.units[u].team.clone();
    let mut linked = vec![u];
    let mut i = 0;
    while i < linked.len() {
        let x = linked[i];
        for o in all.clone() {
            if linked.contains(&o) || !live(b, o) {
                continue;
            }
            let up = b.units[x].c3_parent.as_deref().and_then(|p| unit_named(b, &team, p)) == Some(o);
            let down = b.units[o].c3_parent.as_deref().and_then(|p| unit_named(b, &team, p)) == Some(x);
            if up || down {
                linked.push(o);
            }
        }
        i += 1;
    }
    linked
}

/// Is this unit within the radius of ECM hostile to it (p.200)? `boosted`: only Angel ECM counts (p.199).
fn in_hostile_ecm(b: &mut Battle, u: UnitId, boosted: bool) -> bool {
    let Some(at) = xy(b, u) else { return false };
    let team = b.units[u].team.clone();
    for e in 0..b.units.len() {
        if b.units[e].team == team || b.is_destroyed(e) {
            continue;
        }
        let field = if boosted { crate::electronics::angel_field(&b.units[e]) } else { crate::electronics::hostile_field(&b.units[e]) };
        if field && xy(b, e).is_some_and(|p| hex_distance(p, at) <= ECM_RADIUS) {
            return true;
        }
    }
    false
}

/// Is this member's network link degraded by hostile ECM (it, or its Master, in the radius; p.199)?
fn degraded(b: &mut Battle, u: UnitId) -> bool {
    let boosted = matches!(kind_of(b, u), Some(Kind::Master { boosted: true }) | Some(Kind::Slave { boosted: true }));
    if in_hostile_ecm(b, u, boosted) {
        return true;
    }
    if matches!(kind_of(b, u), Some(Kind::Slave { .. })) {
        let team = b.units[u].team.clone();
        if let Some(m) = b.units[u].c3_parent.as_deref().and_then(|p| unit_named(b, &team, p)) {
            let mb = matches!(kind_of(b, m), Some(Kind::Master { boosted: true }));
            return in_hostile_ecm(b, m, mb);
        }
    }
    false
}

/// A unit's network partners as a movement estimate uses them (Hydra, 2026-11-21): where each partner stands, its line
/// of sight height, and whether its link is degraded, plus whether the unit's own link is. The estimate asks about hexes
/// the unit or its target might stand in, so the members are taken once and the lines traced per hex (`distance_to`).
/// Partners that have not moved yet are taken where they stand (an estimate, as the rest of the move scoring is).
pub struct Partners {
    members: Vec<((i64, i64), crate::los::Height, bool)>,
    own_degraded: bool,
}

impl Partners {
    /// `u`'s partners now; None when it is in no working network.
    pub fn of(b: &mut Battle, u: UnitId) -> Option<Partners> {
        // the same cheap test as `best`: most units are in no network
        if b.units[u].c3_parent.is_none() && b.units[u].c3_net.is_none() {
            let name = b.units[u].side_name.as_deref();
            if name.is_none() || !b.units.iter().any(|o| o.c3_parent.as_deref() == name && o.team == b.units[u].team) {
                return None;
            }
        }
        let net = active_network(b, u);
        let mut members = Vec::new();
        for m in net {
            if m == u {
                continue;
            }
            let Some(p) = xy(b, m) else { continue };
            let h = crate::attack_resolution::los_height(&b.units[m]);
            let deg = degraded(b, m);
            members.push((p, h, deg));
        }
        if members.is_empty() {
            return None;
        }
        let own_degraded = degraded(b, u);
        Some(Partners { members, own_degraded })
    }

    /// The closest partner's distance to a target standing at `t` (height `th`) among those that would see it, and
    /// whether the link used is degraded: the figure `best` gives an actual attack. The range-modifier rule itself
    /// (only a better bracket counts, p.198) is applied by the Adjuster, as for a real attack.
    pub fn distance_to(&self, b: &Battle, t: (i64, i64), th: crate::los::Height) -> Option<(i64, bool)> {
        let mut found: Option<(i64, bool)> = None;
        for &(p, ph, deg) in &self.members {
            if p == t {
                continue;
            }
            let d = hex_distance(p, t);
            if found.is_some_and(|(fd, fdeg)| d > fd || (d == fd && (!fdeg || deg))) {
                continue;
            }
            if !crate::move_eval::pair_info(b, p, t, ph, th).is_some_and(|i| i.los.los) {
                continue;
            }
            found = Some((d, deg));
        }
        found.map(|(d, deg)| (d, deg || self.own_degraded))
    }
}

/// What C3 offers `attacker` against `target` now: the closest distance from a linked member that can see the target,
/// and whether that member's (or the attacker's) link is degraded by hostile ECM. None: no network, or no member closer
/// than the attacker itself. Among members at the same distance one that is not degraded is used.
pub fn best(b: &mut Battle, attacker: UnitId, target: UnitId) -> Option<(i64, bool)> {
    // the common case first, cheaply: a unit nobody linked into a network (speed: this is asked for every attack priced)
    if b.units[attacker].c3_parent.is_none() && b.units[attacker].c3_net.is_none() {
        let name = b.units[attacker].side_name.as_deref();
        if name.is_none() || !b.units.iter().any(|o| o.c3_parent.as_deref() == name && o.team == b.units[attacker].team) {
            return None;
        }
    }
    let net = active_network(b, attacker);
    if net.len() < 2 {
        return None;
    }
    let t = xy(b, target)?;
    let own = hex_distance(xy(b, attacker)?, t);
    let mut found: Option<(i64, bool)> = None;
    for m in net {
        if m == attacker {
            continue;
        }
        let Some(p) = xy(b, m) else { continue };
        let d = hex_distance(p, t);
        if d >= own {
            continue;
        }
        let Some((true, _)) = crate::spotting::sight(b, m, target) else { continue };
        let deg = degraded(b, m);
        if found.map_or(true, |(fd, fdeg)| d < fd || (d == fd && fdeg && !deg)) {
            found = Some((d, deg));
        }
    }
    let attacker_degraded = degraded(b, attacker);
    found.map(|(d, deg)| (d, deg || attacker_degraded))
}
