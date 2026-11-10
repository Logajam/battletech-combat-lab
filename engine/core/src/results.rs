// Translated from INTEGRATION__results.py (session 22): one battle's outcome. (The batch summary's printing is
// reporting, not rules: it comes with the batch driver, stage 9.)
use indexmap::IndexMap;

#[derive(Clone, Debug, Default)]
pub struct SideStats {
    pub name: String,
    pub max_hp: f64,
    pub final_hp: f64,
    pub destroyed: bool,
    pub cause_of_death: Option<String>,
    pub crippled_at: Option<i64>,
    pub attacks: i64,
    pub hits: i64,
    pub damage_dealt: f64,
    pub final_hex: Option<String>,
    pub units: i64,
    pub units_lost: i64,
}

impl SideStats {
    pub fn new(name: String, max_hp: f64) -> SideStats {
        SideStats { name, max_hp, units: 1, ..Default::default() }
    }
}

#[derive(Clone, Debug)]
pub struct BattleResult {
    pub turns_taken: i64,
    pub destroyed: Option<String>,
    pub winner: String,
    pub teams: IndexMap<String, SideStats>,
    pub units: IndexMap<String, SideStats>,
    pub turn_cap: Option<i64>,
}

impl BattleResult {
    pub fn new(turn_cap: Option<i64>) -> BattleResult {
        BattleResult { turns_taken: 0, destroyed: None, winner: "Draw".into(), teams: IndexMap::new(), units: IndexMap::new(), turn_cap }
    }
}

/// One team's stats from its units' (a single unit's own stats come back as they are).
pub fn team_totals(team: &str, members: &[SideStats]) -> SideStats {
    if members.len() == 1 {
        return members[0].clone();
    }
    let crippled: Vec<i64> = members.iter().filter_map(|m| m.crippled_at).collect();
    SideStats {
        name: format!("{} ({} units)", team, members.len()),
        max_hp: members.iter().map(|m| m.max_hp).sum(),
        final_hp: members.iter().map(|m| m.final_hp).sum(),
        destroyed: members.iter().all(|m| m.destroyed),
        crippled_at: crippled.into_iter().min(),
        attacks: members.iter().map(|m| m.attacks).sum(),
        hits: members.iter().map(|m| m.hits).sum(),
        damage_dealt: members.iter().map(|m| m.damage_dealt).sum(),
        units: members.len() as i64,
        units_lost: members.iter().filter(|m| m.destroyed).count() as i64,
        ..Default::default()
    }
}
