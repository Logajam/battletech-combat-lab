// Translated from the geometry section of INTEGRATION__princess.py: MegaMek's Coords, HexLine and ConvexBoardArea, ported as
// written (Java integer division included).
use crate::hex_geometry;

/// Java integer division (truncates toward zero).
pub fn jdiv(a: i64, b: i64) -> i64 {
    let q = a.abs() / b.abs();
    if (a >= 0) == (b >= 0) { q } else { -q }
}

/// Project internal (x, y) -> MegaMek Coords (x, y), on or off the board.
pub fn mm(xy: (i64, i64)) -> (i64, i64) {
    (xy.0, -jdiv(xy.1 - hex_geometry::row_parity_offset(xy.0), 2))
}

/// Coords.distance (cube distance, odd columns shifted down).
pub fn mm_distance(a: (i64, i64), b: (i64, i64)) -> i64 {
    let cube = |c: (i64, i64)| -> (i64, i64, i64) {
        let q = c.0;
        let r = c.1 - (c.0 - (c.0 & 1)).div_euclid(2);
        (q, r, -q - r)
    };
    let ((q1, r1, s1), (q2, r2, s2)) = (cube(a), cube(b));
    (q1 - q2).abs().max((r1 - r2).abs()).max((s1 - s2).abs())
}

pub fn neighbor(xy: (i64, i64), direction: i64) -> (i64, i64) {
    let (dx, dy) = hex_geometry::FACING_DELTAS[direction.rem_euclid(6) as usize];
    (xy.0 + dx, xy.1 + dy)
}

fn intercept(c: (i64, i64), d: i64) -> i64 {
    let (x, y) = c;
    if d == 0 || d == 3 {
        x
    } else if d == 1 || d == 4 {
        y + jdiv(x + 1, 2)
    } else {
        y - jdiv(x, 2)
    }
}

#[derive(Clone, Copy, Debug)]
pub struct HexLine {
    pub d: i64,
    pub i: i64,
}

impl HexLine {
    pub fn new(c: (i64, i64), d: i64) -> HexLine {
        HexLine { d, i: intercept(c, d) }
    }

    pub fn judge_point(&self, c: (i64, i64)) -> i64 {
        let other = intercept(c, self.d);
        if other < self.i {
            if self.d < 3 { -1 } else { 1 }
        } else if other > self.i {
            if self.d < 3 { 1 } else { -1 }
        } else {
            0
        }
    }

    pub fn judge_area(&self, area: &ConvexBoardArea) -> i64 {
        let flip = self.d > 2;
        let (one, two) = (area.edges[self.d as usize], area.edges[((self.d + 3) % 6) as usize]);
        let (Some(one), Some(two)) = (one, two) else { return 0 };
        if one.i == self.i || two.i == self.i {
            return 0;
        }
        let edge_one = (one.i < self.i) ^ flip;
        let edge_two = (two.i < self.i) ^ flip;
        if edge_one && edge_two {
            1
        } else if !edge_one && !edge_two {
            -1
        } else {
            0
        }
    }

    pub fn y_from_x(&self, x: i64) -> i64 {
        if self.d == 0 || self.d == 3 {
            0
        } else if self.d == 1 || self.d == 4 {
            self.i - jdiv(x + 1, 2)
        } else {
            self.i + jdiv(x, 2)
        }
    }

    pub fn intersection(&self, other: &HexLine) -> Option<(i64, i64)> {
        if other.d % 3 == self.d % 3 {
            return None;
        }
        if other.d == 0 || self.d == 2 {
            return other.intersection(self);
        }
        if self.d == 0 || self.d == 3 {
            return Some((self.i, other.y_from_x(self.i)));
        }
        let x = self.i - other.i;
        Some((x, self.y_from_x(x)))
    }

    pub fn closest_point(&self, c: (i64, i64)) -> (i64, i64) {
        if self.d == 0 || self.d == 3 {
            return (self.i, c.1);
        }
        let x = if self.d == 1 || self.d == 4 {
            ((-2.0 / 3.0) * (self.i as f64 - 0.5 - c.1 as f64 - 2.0 * c.0 as f64)) as i64
        } else {
            ((-5.0 / 3.0) * (self.i as f64 - c.1 as f64 - 2.0 * c.0 as f64)) as i64
        };
        (x, self.y_from_x(x))
    }
}

/// The convex hull of a unit's reachable hexes (PathEnumerator's unitMovableAreas).
pub struct ConvexBoardArea {
    pub edges: [Option<HexLine>; 6],
}

impl ConvexBoardArea {
    pub fn new(coords: &[(i64, i64)]) -> ConvexBoardArea {
        let mut edges: [Option<HexLine>; 6] = [None; 6];
        for c in coords {
            for i in 0..6 {
                if edges[i].map_or(true, |e| e.judge_point(*c) > 0) {
                    edges[i] = Some(HexLine::new(*c, i as i64));
                }
            }
        }
        ConvexBoardArea { edges }
    }

    pub fn contains(&self, c: (i64, i64)) -> bool {
        self.edges[0].is_some() && self.edges.iter().all(|e| e.map_or(false, |e| e.judge_point(c) <= 0))
    }

    fn vertex(&self, i: usize) -> Option<(i64, i64)> {
        self.edges[i].unwrap().intersection(&self.edges[(i + 1) % 6].unwrap())
    }

    pub fn closest_to(&self, c: (i64, i64)) -> (i64, i64) {
        let mut closest: Option<(i64, i64)> = None;
        let mut best = 0;
        for i in 0..6 {
            let Some(edge) = self.edges[i] else { continue };
            if edge.judge_point(c) <= 0 {
                continue;
            }
            if let Some(vert) = self.vertex(i) {
                let dist = mm_distance(vert, c);
                if closest.is_none() || dist < best {
                    closest = Some(vert);
                    best = dist;
                }
            }
            let online = edge.closest_point(c);
            if self.contains(online) {
                let dist = mm_distance(online, c);
                if dist < best {
                    closest = Some(online);
                    best = dist;
                }
            }
        }
        closest.unwrap_or(c)
    }
}
