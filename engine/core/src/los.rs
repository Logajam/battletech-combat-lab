// Translated from pathfinder/los.py (stage 1: hex_distance only; the rest is stage 2).
use crate::pyfmt::py_round;

pub type Hex = (i64, i64);

fn to_cube(h: Hex) -> (f64, f64, f64) {
    let (x, y) = h;
    let q = x as f64;
    let r = (y - x) as f64 / 2.0;
    let s = -q - r;
    (q, r, s)
}

/// Straight-line hex distance between two doubled-coordinate hexes.
pub fn hex_distance(a: Hex, b: Hex) -> i64 {
    let (aq, ar, as_) = to_cube(a);
    let (bq, br, bs) = to_cube(b);
    // max() of three floats, first of equals (they are plain numbers: the value is what matters)
    let mut m = (aq - bq).abs();
    let r = (ar - br).abs();
    if r > m {
        m = r;
    }
    let s = (as_ - bs).abs();
    if s > m {
        m = s;
    }
    py_round(m)
}
