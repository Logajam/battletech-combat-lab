// Translated from pathfinder/board_parser.py (session 22).
//! Parses MegaMek `.board` files into a per-hex lookup structure, and stitches boards. Schema only: costs are
//! terrain_rules', pathfinding is pathfinder's. Text the Python PRINTS (parser warnings) is appended to `out`.

use indexmap::IndexMap;
use serde_json::{json, Map, Value};

use crate::pyfmt::{py_is_space, py_repr_str, py_strip};

/// Feature names this parser has seen and won't warn about.
pub const KNOWN_FEATURE_NAMES: [&str; 36] = [
    "woods", "jungle", "rough", "rubble", "sand", "mud", "swamp", "water", "road", "pavement", "building",
    "bldg_elev", "bldg_cf", "bldg_class", "bldg_armor", "bldg_basement_type", "bridge", "bridge_cf", "bridge_elev",
    "fuel_tank", "fuel_tank_cf", "fuel_tank_elev", "fuel_tank_magn", "magma", "hazardous_liquid", "fortified",
    "impassable", "elevator", "planted_fields", "arms", "legs", "ground_fluff", "foliage_elev", "fluff",
    "bldg_fluff", "road_fluff",
];

/// {name: [params]} in file order; a repeated name overwrites in place (a Python dict).
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Features(pub IndexMap<String, Vec<String>>);

impl Features {
    pub fn has(&self, name: &str) -> bool {
        self.0.contains_key(name)
    }
    pub fn get(&self, name: &str) -> Option<&Vec<String>> {
        self.0.get(name)
    }
    /// `features[name][:1]` as the first param, if any.
    pub fn first_param(&self, name: &str) -> Option<&str> {
        self.0.get(name).and_then(|p| p.first()).map(|s| s.as_str())
    }
}

/// One hex: the parser's keys (level, features, impassable) and what prepare_board adds.
#[derive(Clone, Debug, PartialEq)]
pub struct Hex {
    pub level: i64,
    pub features: Features,
    pub impassable: bool,
    /// water of depth 1+: the surface level (prepare_board)
    pub surface_level: Option<i64>,
    /// water of depth 1+: the depth (prepare_board)
    pub depth: Option<i64>,
    /// a passive building: the ground level under the roof (prepare_board)
    pub ground_level: Option<i64>,
    /// a passive building: set True by prepare_board
    pub building: bool,
    /// smoke in the hex (INTEGRATION__smoke): density "1" light / "2" heavy, and the turn it lasts to
    pub smoke: Option<Smoke>,
}

/// info["smoke"]: {"density": "1" | "2", "until": turn}
#[derive(Clone, Debug, PartialEq)]
pub struct Smoke {
    pub density: String,
    pub until: i64,
}

impl Hex {
    pub fn new(level: i64, features: Features) -> Hex {
        Hex { level, features, impassable: false, surface_level: None, depth: None, ground_level: None, building: false, smoke: None }
    }

    /// The hex as the Python's dict, key order included (level, features, impassable, surface_level, depth,
    /// ground_level, building).
    pub fn to_json(&self) -> Value {
        let mut m = Map::new();
        m.insert("level".into(), json!(self.level));
        let mut f = Map::new();
        for (k, v) in &self.features.0 {
            f.insert(k.clone(), json!(v));
        }
        m.insert("features".into(), Value::Object(f));
        m.insert("impassable".into(), json!(self.impassable));
        if let Some(v) = self.surface_level {
            m.insert("surface_level".into(), json!(v));
        }
        if let Some(v) = self.depth {
            m.insert("depth".into(), json!(v));
        }
        if let Some(v) = self.ground_level {
            m.insert("ground_level".into(), json!(v));
        }
        if self.building {
            m.insert("building".into(), json!(true));
        }
        if let Some(sm) = &self.smoke {
            m.insert("smoke".into(), json!({"density": sm.density, "until": sm.until}));
        }
        Value::Object(m)
    }
}

/// The terrain map: {"width", "height", "hexes": {"CCRR": Hex}} - hexes in insertion order.
#[derive(Clone, Debug)]
pub struct Board {
    pub width: i64,
    pub height: i64,
    pub hexes: IndexMap<String, Hex>,
}

impl Board {
    pub fn to_json(&self) -> Value {
        let mut hexes = Map::new();
        for (k, h) in &self.hexes {
            hexes.insert(k.clone(), h.to_json());
        }
        let mut m = Map::new();
        m.insert("width".into(), json!(self.width));
        m.insert("height".into(), json!(self.height));
        m.insert("hexes".into(), Value::Object(hexes));
        Value::Object(m)
    }
}

/// Python's `str(list_of_str)`: ['1', '36']
fn py_list_repr(items: &[String]) -> String {
    format!("[{}]", items.iter().map(|s| py_repr_str(s)).collect::<Vec<_>>().join(", "))
}

fn parse_features(features_str: &str, out: &mut String) -> Features {
    let mut features = Features::default();
    if features_str.is_empty() {
        return features;
    }
    for chunk in features_str.split(';') {
        let chunk = py_strip(chunk);
        if chunk.is_empty() {
            continue;
        }
        let mut parts = chunk.split(':');
        let name = parts.next().unwrap().to_string();
        let params: Vec<String> = parts.map(|s| s.to_string()).collect();
        if !KNOWN_FEATURE_NAMES.contains(&name.as_str()) {
            out.push_str(&format!(
                "WARNING: unrecognized terrain feature '{}' in .board file (params={}) \u{2014} stored as-is, but no cost/rules logic currently recognizes it.\n",
                name,
                py_list_repr(&params)
            ));
        }
        features.0.insert(name, params);
    }
    features
}

/// `^size\s+(\d+)\s+(\d+)\s*$`
fn match_size(line: &str) -> Option<(i64, i64)> {
    let rest = line.strip_prefix("size")?;
    let (a, rest) = take_ws_then_digits(rest)?;
    let (b, rest) = take_ws_then_digits(rest)?;
    if rest.chars().all(py_is_space) {
        Some((a.parse().ok()?, b.parse().ok()?))
    } else {
        None
    }
}

fn take_ws_then_digits(s: &str) -> Option<(&str, &str)> {
    let t = s.trim_start_matches(py_is_space);
    if t.len() == s.len() {
        return None; // \s+ needs at least one
    }
    let n = t.chars().take_while(|c| c.is_ascii_digit()).count();
    if n == 0 {
        return None;
    }
    Some((&t[..n], &t[n..]))
}

/// `^hex\s+(\d{4})\s+(-?\d+)\s+"([^"]*)"\s+"([^"]*)"\s*$` -> (label, level, features, theme)
fn match_hex(line: &str) -> Option<(&str, i64, &str, &str)> {
    let rest = line.strip_prefix("hex")?;
    let t = rest.trim_start_matches(py_is_space);
    if t.len() == rest.len() {
        return None;
    }
    let label = t.get(..4)?;
    if !label.chars().all(|c| c.is_ascii_digit()) {
        return None;
    }
    let rest = &t[4..];
    let t = rest.trim_start_matches(py_is_space);
    if t.len() == rest.len() {
        return None;
    }
    let neg = t.starts_with('-');
    let digits_from = if neg { &t[1..] } else { t };
    let n = digits_from.chars().take_while(|c| c.is_ascii_digit()).count();
    if n == 0 {
        return None;
    }
    let level_text = &t[..(neg as usize) + n];
    let rest = &t[(neg as usize) + n..];
    let t = rest.trim_start_matches(py_is_space);
    if t.len() == rest.len() {
        return None;
    }
    let t = t.strip_prefix('"')?;
    let q = t.find('"')?;
    let features = &t[..q];
    let rest = &t[q + 1..];
    let t = rest.trim_start_matches(py_is_space);
    if t.len() == rest.len() {
        return None;
    }
    let t = t.strip_prefix('"')?;
    let q = t.find('"')?;
    let theme = &t[..q];
    if !t[q + 1..].chars().all(py_is_space) {
        return None;
    }
    Some((label, level_text.parse().ok()?, features, theme))
}

/// Python reads a text file with universal newlines: \r\n and lone \r become \n.
fn universal_lines(text: &str) -> Vec<String> {
    text.replace("\r\n", "\n").replace('\r', "\n").split_inclusive('\n').map(|s| s.to_string()).collect()
}

/// Parse a .board file's TEXT. `path` is only for messages (Python's `filepath`). Err = the ValueError message.
pub fn parse_board_file(path: &str, text: &str, out: &mut String) -> Result<Board, String> {
    let mut width: Option<i64> = None;
    let mut height: Option<i64> = None;
    let mut hexes: IndexMap<String, Hex> = IndexMap::new();
    let mut seen_end = false;

    for (i, raw_line) in universal_lines(text).iter().enumerate() {
        let line_num = i + 1;
        let line = py_strip(raw_line);
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        if line.starts_with("tag ") || line.starts_with("option ") {
            continue;
        }
        if line == "end" {
            seen_end = true;
            break;
        }
        if let Some((w, h)) = match_size(line) {
            width = Some(w);
            height = Some(h);
            continue;
        }
        if let Some((label, level, features_str, _theme)) = match_hex(line) {
            if hexes.contains_key(label) {
                out.push_str(&format!(
                    "WARNING: duplicate hex '{}' at line {} \u{2014} overwriting previous entry.\n",
                    label, line_num
                ));
            }
            let features = parse_features(features_str, out);
            hexes.insert(label.to_string(), Hex::new(level, features));
            continue;
        }
        return Err(format!(
            "Unrecognized line {} in board file {}: {} \u{2014} does not match 'size W H', 'hex CCRR LEVEL \"features\" \"theme\"', a comment, a tag or option line, or 'end'. Out of scope for this parser as written; extend _HEX_LINE_RE/_SIZE_LINE_RE deliberately if this is a new valid format, don't silently skip it.",
            line_num,
            py_repr_str(path),
            py_repr_str(raw_line)
        ));
    }
    let (width, height) = match (width, height) {
        (Some(w), Some(h)) => (w, h),
        _ => return Err(format!("Board file {} never had a 'size W H' line.", py_repr_str(path))),
    };
    if !seen_end {
        return Err(format!("Board file {} never had a terminating 'end' line.", py_repr_str(path)));
    }
    Ok(Board { width, height, hexes })
}

/// MegaMek's columnPaddingWidth default: the blank columns after an odd-width board.
pub const ODD_WIDTH_PADDING: i64 = 1;

/// Combine boards (path, text) into one terrain map arranged in a cols x rows grid, row-major.
pub fn stitch_boards(boards: &[(String, String)], cols: i64, rows: i64, out: &mut String) -> Result<Board, String> {
    if boards.len() as i64 != cols * rows {
        return Err(format!(
            "stitch_boards got {} board path(s) but cols*rows = {}*{} = {} -- these must match exactly.",
            boards.len(),
            cols,
            rows,
            cols * rows
        ));
    }
    let mut parsed = Vec::new();
    for (path, text) in boards {
        parsed.push(parse_board_file(path, text, out)?);
    }
    let grid = |r: i64, c: i64| &parsed[(r * cols + c) as usize];

    let mut row_heights: Vec<i64> = Vec::new();
    for grid_row in 0..rows {
        let mut set: Vec<i64> = (0..cols).map(|c| grid(grid_row, c).height).collect();
        set.sort();
        set.dedup();
        if set.len() > 1 {
            return Err(format!(
                "Grid row {} has mismatched board heights {} -- all boards in the same grid row must share the same height. Padding is not supported; use same-sized maps.",
                grid_row,
                py_int_list(&set)
            ));
        }
        row_heights.push(set[0]);
    }
    let mut col_widths: Vec<i64> = Vec::new();
    for grid_col in 0..cols {
        let mut set: Vec<i64> = (0..rows).map(|r| grid(r, grid_col).width).collect();
        set.sort();
        set.dedup();
        if set.len() > 1 {
            return Err(format!(
                "Grid column {} has mismatched board widths {} -- all boards in the same grid column must share the same width. Padding is not supported; use same-sized maps.",
                grid_col,
                py_int_list(&set)
            ));
        }
        col_widths.push(set[0]);
    }
    let pad_after = |grid_col: i64| -> i64 {
        if grid_col == cols - 1 {
            0
        } else if col_widths[grid_col as usize] % 2 != 0 {
            ODD_WIDTH_PADDING
        } else {
            0
        }
    };
    let mut col_offset = Vec::new();
    let mut running = 0;
    for grid_col in 0..cols {
        col_offset.push(running);
        running += col_widths[grid_col as usize] + pad_after(grid_col);
    }
    let total_width = running;
    let mut row_offset = Vec::new();
    running = 0;
    for grid_row in 0..rows {
        row_offset.push(running);
        running += row_heights[grid_row as usize];
    }
    let total_height = running;

    if total_width > 99 || total_height > 99 {
        out.push_str(&format!(
            "WARNING: stitched board is {}x{}, exceeding the 2-digit CCRR convention (max 99x99) -- resulting hex labels will be 5+ characters and won't round-trip through hex_geometry.parse_hex_label().\n",
            total_width, total_height
        ));
    }
    let mut hexes: IndexMap<String, Hex> = IndexMap::new();
    for col in 1..=total_width {
        for row in 1..=total_height {
            hexes.insert(format!("{:02}{:02}", col, row), Hex::new(0, Features::default()));
        }
    }
    for grid_row in 0..rows {
        for grid_col in 0..cols {
            let board = grid(grid_row, grid_col);
            let c_off = col_offset[grid_col as usize];
            let r_off = row_offset[grid_row as usize];
            for (label, info) in &board.hexes {
                let local_col: i64 = label[..2].parse().unwrap();
                let local_row: i64 = label[2..].parse().unwrap();
                let new_label = format!("{:02}{:02}", c_off + local_col, r_off + local_row);
                hexes.insert(new_label, info.clone());
            }
        }
    }
    Ok(Board { width: total_width, height: total_height, hexes })
}

/// Python's `str(sorted(set_of_ints))`: [15, 16]
fn py_int_list(v: &[i64]) -> String {
    format!("[{}]", v.iter().map(|n| n.to_string()).collect::<Vec<_>>().join(", "))
}

impl Board {
    /// The hex at doubled coordinates (x, y), None if off the board or not a hex center (Python's
    /// `hexes.get(hex_label(x, y))` with a ValueError read as "not there").
    pub fn info_xy(&self, x: i64, y: i64) -> Option<&Hex> {
        match crate::hex_geometry::hex_label(x, y) {
            Ok(label) => self.hexes.get(&label),
            Err(_) => None,
        }
    }
}
