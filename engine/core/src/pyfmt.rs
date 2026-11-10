//! Python behaviours the translation must copy exactly (RUST_PORT traps 3-5): round half to even, floor division
//! and modulo, `repr` of a str, `int()` of a str, and `str(float)`.

/// Python's `round(x)` for a float: half to even. (Rust's `f64::round` rounds half away from zero.)
pub fn py_round(x: f64) -> i64 {
    let f = x.floor();
    let diff = x - f;
    if diff < 0.5 {
        f as i64
    } else if diff > 0.5 {
        f as i64 + 1
    } else if (f as i64) % 2 == 0 {
        f as i64
    } else {
        f as i64 + 1
    }
}

/// Python's `a // b` for ints (floors toward negative infinity).
pub fn py_floordiv(a: i64, b: i64) -> i64 {
    let q = a / b;
    if (a % b != 0) && ((a < 0) != (b < 0)) {
        q - 1
    } else {
        q
    }
}

/// Python's `a % b` for ints (the result has the sign of b).
pub fn py_mod(a: i64, b: i64) -> i64 {
    let r = a % b;
    if r != 0 && ((r < 0) != (b < 0)) {
        r + b
    } else {
        r
    }
}

/// Python's `repr(str)`: single quotes unless the text holds a single quote and no double quote.
pub fn py_repr_str(s: &str) -> String {
    let quote = if s.contains('\'') && !s.contains('"') { '"' } else { '\'' };
    let mut out = String::new();
    out.push(quote);
    for c in s.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c == quote => {
                out.push('\\');
                out.push(c);
            }
            c if (c as u32) < 0x20 || c as u32 == 0x7f => out.push_str(&format!("\\x{:02x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push(quote);
    out
}

/// Python whitespace as `str.strip()` / `str.split()` see it (Unicode White_Space plus the ASCII separators).
pub fn py_is_space(c: char) -> bool {
    c.is_whitespace() || ('\x1c'..='\x1f').contains(&c)
}

pub fn py_strip(s: &str) -> &str {
    s.trim_matches(py_is_space)
}

/// Python's `int(s)` for a str, base 10: optional whitespace, sign, digits with single underscores between.
/// Err carries Python's ValueError message.
pub fn py_int(s: &str) -> Result<i64, String> {
    let bad = || format!("invalid literal for int() with base 10: {}", py_repr_str(s));
    let t = py_strip(s);
    let (neg, digits) = match t.strip_prefix('-') {
        Some(rest) => (true, rest),
        None => (false, t.strip_prefix('+').unwrap_or(t)),
    };
    if digits.is_empty() || digits.starts_with('_') || digits.ends_with('_') || digits.contains("__") {
        return Err(bad());
    }
    let mut value: i64 = 0;
    for c in digits.chars() {
        if c == '_' {
            continue;
        }
        let d = c.to_digit(10).ok_or_else(bad)?;
        value = value.checked_mul(10).and_then(|v| v.checked_add(d as i64)).ok_or_else(bad)?;
    }
    Ok(if neg { -value } else { value })
}

/// Python's `str(float)` / `repr(float)`: shortest round-trip digits, `1.0`, exponent form outside 1e-4 <= |x| < 1e16.
pub fn py_float_str(x: f64) -> String {
    if x.is_nan() {
        return "nan".to_string();
    }
    if x.is_infinite() {
        return if x > 0.0 { "inf" } else { "-inf" }.to_string();
    }
    if x == 0.0 {
        return if x.is_sign_negative() { "-0.0" } else { "0.0" }.to_string();
    }
    let mut buf = ryu::Buffer::new();
    let shortest = buf.format_finite(x).to_string();
    // ryu gives "1.0", "1e-5", "1.2345e20" or plain; re-derive digits and exponent to apply Python's thresholds
    let (neg, body) = match shortest.strip_prefix('-') {
        Some(b) => (true, b.to_string()),
        None => (false, shortest.clone()),
    };
    let (mantissa, exp) = match body.split_once('e') {
        Some((m, e)) => (m.to_string(), e.parse::<i32>().unwrap()),
        None => (body.clone(), 0),
    };
    let (int_part, frac_part) = match mantissa.split_once('.') {
        Some((i, f)) => (i.to_string(), f.to_string()),
        None => (mantissa.clone(), String::new()),
    };
    let mut digits = format!("{}{}", int_part, frac_part);
    let mut point = int_part.len() as i32 + exp; // decimal point position within `digits`
    let lead = digits.len() - digits.trim_start_matches('0').len();
    digits = digits.trim_start_matches('0').to_string();
    point -= lead as i32;
    let digits = digits.trim_end_matches('0').to_string();
    let digits = if digits.is_empty() { "0".to_string() } else { digits };
    let decimal_exp = point - 1; // x = d.ddd * 10^decimal_exp
    let n = digits.len() as i32;
    let mut out = String::new();
    if neg {
        out.push('-');
    }
    if (-4..16).contains(&decimal_exp) {
        if point <= 0 {
            out.push_str("0.");
            out.push_str(&"0".repeat((-point) as usize));
            out.push_str(&digits);
        } else if point >= n {
            out.push_str(&digits);
            out.push_str(&"0".repeat((point - n) as usize));
            out.push_str(".0");
        } else {
            out.push_str(&digits[..point as usize]);
            out.push('.');
            out.push_str(&digits[point as usize..]);
        }
    } else {
        out.push_str(&digits[..1]);
        if n > 1 {
            out.push('.');
            out.push_str(&digits[1..]);
        }
        out.push('e');
        out.push(if decimal_exp < 0 { '-' } else { '+' });
        out.push_str(&format!("{:02}", decimal_exp.abs()));
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rounding_is_half_to_even() {
        assert_eq!(py_round(0.5), 0);
        assert_eq!(py_round(1.5), 2);
        assert_eq!(py_round(2.5), 2);
        assert_eq!(py_round(-0.5), 0);
        assert_eq!(py_round(-1.5), -2);
        assert_eq!(py_round(2.4999), 2);
        assert_eq!(py_round(-2.6), -3);
    }

    #[test]
    fn floor_division_and_modulo_follow_python() {
        assert_eq!(py_floordiv(-7, 2), -4);
        assert_eq!(py_floordiv(7, -2), -4);
        assert_eq!(py_floordiv(7, 2), 3);
        assert_eq!(py_mod(-7, 2), 1);
        assert_eq!(py_mod(7, -2), -1);
    }

    #[test]
    fn float_text_matches_python() {
        assert_eq!(py_float_str(1.0), "1.0");
        assert_eq!(py_float_str(0.1), "0.1");
        assert_eq!(py_float_str(1e-5), "1e-05");
        assert_eq!(py_float_str(0.0001), "0.0001");
        assert_eq!(py_float_str(1e16), "1e+16");
        assert_eq!(py_float_str(123456789012345.0), "123456789012345.0");
        assert_eq!(py_float_str(1.5e-7), "1.5e-07");
        assert_eq!(py_float_str(-2.5), "-2.5");
        assert_eq!(py_float_str(5.347222222222222), "5.347222222222222");
        assert_eq!(py_float_str(100.0), "100.0");
        assert_eq!(py_float_str(1e22), "1e+22");
    }

    #[test]
    fn int_parsing() {
        assert_eq!(py_int(" 12 "), Ok(12));
        assert_eq!(py_int("-3"), Ok(-3));
        assert_eq!(py_int("1_0"), Ok(10));
        assert!(py_int("1.5").is_err());
        assert_eq!(py_int("x").unwrap_err(), "invalid literal for int() with base 10: 'x'");
    }
}
