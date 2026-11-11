// Translated from pathfinder/hex_geometry.py (commit f574c5b..., session 22).
//! Doubled-coordinate hex grid, facing, and BT hex-label conversion. Nothing here knows about terrain.

use crate::pyfmt::{py_floordiv, py_mod, py_repr_str, py_strip};

/// Doubled-coordinate movement vector for each of the 6 facings (0 = N, clockwise).
pub const FACING_DELTAS: [(i64, i64); 6] = [(0, 2), (1, 1), (1, -1), (0, -2), (-1, -1), (-1, 1)];

/// Compass label of each facing.
pub const COMPASS_BY_FACING: [&str; 6] = ["N", "NE", "SE", "S", "SW", "NW"];

/// Internal x is 0-indexed; x odd <-> BT column is even.
pub const ODD_INTERNAL_X_IS_SHIFTED: bool = true;

/// (x, y, facing) - Python's `State`.
pub type State = (i64, i64, i64);

pub fn row_parity_offset(x: i64) -> i64 {
    let is_shifted = if ODD_INTERNAL_X_IS_SHIFTED { py_mod(x, 2) == 1 } else { py_mod(x, 2) == 0 };
    if is_shifted {
        -1
    } else {
        0
    }
}

/// Internal doubled coords -> BT-style 'CCRR' hex label. Err = Python's ValueError message.
pub fn hex_label(x: i64, y: i64) -> Result<String, String> {
    let offset = row_parity_offset(x);
    if py_mod(y - offset, 2) != 0 {
        return Err(format!(
            "({}, {}) is not a valid hex center under the current offset convention (ODD_INTERNAL_X_IS_SHIFTED={}) \u{2014} check for a coordinate bug.",
            x,
            y,
            if ODD_INTERNAL_X_IS_SHIFTED { "True" } else { "False" }
        ));
    }
    let col = x + 1;
    let row = 1 - py_floordiv(y - offset, 2);
    if col < 1 || row < 1 {
        return Err(format!("({}, {}) maps to non-positive col/row ({}, {})", x, y, col, row));
    }
    if col < 100 && row < 100 {
        // the usual case, written without the formatter (this is called millions of times a battle)
        let d = |n: i64| (b'0' + n as u8) as char;
        let mut out = String::with_capacity(4);
        out.push(d(col / 10));
        out.push(d(col % 10));
        out.push(d(row / 10));
        out.push(d(row % 10));
        return Ok(out);
    }
    Ok(format!("{:02}{:02}", col, row))
}

/// (column, row) of the hex at doubled coordinates, None where `hex_label` would be an error.
pub fn col_row(x: i64, y: i64) -> Option<(i64, i64)> {
    let offset = row_parity_offset(x);
    if py_mod(y - offset, 2) != 0 {
        return None;
    }
    let col = x + 1;
    let row = 1 - py_floordiv(y - offset, 2);
    if col < 1 || row < 1 {
        return None;
    }
    Some((col, row))
}

/// BT-style 'CCRR' hex label -> internal doubled coords (x, y).
pub fn parse_hex_label(label: &str) -> Result<(i64, i64), String> {
    let label = py_strip(label);
    if label.chars().count() != 4 || !label.chars().all(|c| c.is_ascii_digit()) {
        return Err(format!("Expected a 4-digit 'CCRR' hex label, got {}", py_repr_str(label)));
    }
    let col: i64 = label[..2].parse().unwrap();
    let row: i64 = label[2..].parse().unwrap();
    let x = col - 1;
    let offset = row_parity_offset(x);
    let y = 2 * (1 - row) + offset;
    Ok((x, y))
}

pub fn facing_to_compass(facing: i64) -> Result<&'static str, String> {
    if !(0..=5).contains(&facing) {
        return Err(format!("facing must be 0-5, got {}", facing));
    }
    Ok(COMPASS_BY_FACING[facing as usize])
}

pub fn compass_to_facing(compass: &str) -> Result<i64, String> {
    let c = py_strip(compass).to_uppercase();
    match COMPASS_BY_FACING.iter().position(|n| *n == c) {
        Some(i) => Ok(i as i64),
        None => Err(format!(
            "compass must be one of ['N', 'NE', 'NW', 'S', 'SE', 'SW'], got {}",
            py_repr_str(&c)
        )),
    }
}

/// Human-readable 'hex label + facing' for a state, e.g. '0508 facing NE'.
pub fn describe_state(x: i64, y: i64, facing: i64) -> Result<String, String> {
    Ok(format!("{} facing {}", hex_label(x, y)?, facing_to_compass(facing)?))
}

/// 'CCRR' + compass string -> internal (x, y, facing) State.
pub fn state_from_label(hex_label_str: &str, compass: &str) -> Result<State, String> {
    let (x, y) = parse_hex_label(hex_label_str)?;
    Ok((x, y, compass_to_facing(compass)?))
}
