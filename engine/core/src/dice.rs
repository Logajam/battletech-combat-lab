//! Stage 9: the engine's own dice. `PcgDice` is PCG-XSL-RR 128/64 (O'Neill's pcg64), seeded through SplitMix64: fast, no
//! outside crate, the same stream on every platform. (It is not NumPy's stream, so a Rust battle on a seed is not the
//! Python battle on that seed: the two engines are compared on their statistics, INTEGRATION__RUST_PORT.md Stage 9.)
use crate::battle::Dice;

const MULT: u128 = 0x2360_ED05_1FC6_5DA4_4385_DF64_9FCC_F645;

fn splitmix(x: &mut u64) -> u64 {
    *x = x.wrapping_add(0x9E37_79B9_7F4A_7C15);
    let mut z = *x;
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^ (z >> 31)
}

pub struct PcgDice {
    state: u128,
    inc: u128,
    used: usize,
}

impl PcgDice {
    pub fn new(seed: u64) -> PcgDice {
        let mut s = seed;
        let (a, b, c, d) = (splitmix(&mut s), splitmix(&mut s), splitmix(&mut s), splitmix(&mut s));
        let init = ((a as u128) << 64) | b as u128;
        let inc = ((((c as u128) << 64) | d as u128) << 1) | 1;
        let mut g = PcgDice { state: 0, inc, used: 0 };
        g.state = g.state.wrapping_mul(MULT).wrapping_add(g.inc);
        g.state = g.state.wrapping_add(init);
        g.state = g.state.wrapping_mul(MULT).wrapping_add(g.inc);
        g
    }

    /// The seed of battle `sim` (1-based) of a batch seeded `seed`: battle 1 uses the seed itself, later ones a mixed number.
    pub fn battle_seed(seed: u64, sim: u64) -> u64 {
        if sim == 1 {
            return seed;
        }
        let mut s = seed ^ sim.wrapping_mul(0xD1B5_4A32_D192_ED03);
        splitmix(&mut s) >> 1
    }

    fn next_u64(&mut self) -> u64 {
        self.state = self.state.wrapping_mul(MULT).wrapping_add(self.inc);
        let rot = (self.state >> 122) as u32;
        let xored = ((self.state >> 64) as u64) ^ (self.state as u64);
        xored.rotate_right(rot)
    }

    /// Uniform 0..n (Lemire's unbiased multiply-shift).
    fn below(&mut self, n: u64) -> u64 {
        let mut m = (self.next_u64() as u128) * n as u128;
        let mut low = m as u64;
        if low < n {
            let t = n.wrapping_neg() % n;
            while low < t {
                m = (self.next_u64() as u128) * n as u128;
                low = m as u64;
            }
        }
        (m >> 64) as u64
    }
}

impl Dice for PcgDice {
    fn roll_2d6(&mut self) -> i64 {
        self.used += 1;
        (self.below(6) + self.below(6) + 2) as i64
    }
    fn pick_number(&mut self, n: i64) -> i64 {
        assert!(n >= 1, "pick_number(n) needs n >= 1, got {}", n);
        self.used += 1;
        self.below(n as u64) as i64 + 1
    }
    fn used(&self) -> usize {
        self.used
    }
    fn save(&self) -> Option<serde_json::Value> {
        Some(serde_json::json!({"state": self.state.to_string(), "inc": self.inc.to_string(), "used": self.used}))
    }
}

impl PcgDice {
    /// Dice at the exact place `Dice::save` recorded (MegaMek bridge, `bridge.rs`).
    pub fn restore(v: &serde_json::Value) -> PcgDice {
        let big = |k: &str| v[k].as_str().unwrap_or_else(|| panic!("dice state: no {}", k)).parse::<u128>().unwrap();
        PcgDice { state: big("state"), inc: big("inc"), used: v["used"].as_u64().unwrap() as usize }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn two_d6_is_triangular_and_seeds_differ() {
        let mut d = PcgDice::new(1);
        let mut counts = [0usize; 13];
        for _ in 0..360_000 {
            counts[d.roll_2d6() as usize] += 1;
        }
        for (sum, ways) in [(2, 1.0), (7, 6.0), (12, 1.0)] {
            let want = 360_000.0 * ways / 36.0;
            assert!((counts[sum] as f64 - want).abs() < 0.04 * want, "sum {} count {}", sum, counts[sum]);
        }
        assert_ne!(PcgDice::new(1).roll_2d6() as u64 + PcgDice::new(1).pick_number(1000) as u64, 0);
        let (mut a, mut b) = (PcgDice::new(5), PcgDice::new(6));
        assert!((0..20).any(|_| a.pick_number(1_000_000) != b.pick_number(1_000_000)));
    }
}
