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

/// A Python number: `int` or `float`, kept apart because the Python mixes them (an armor pool is an int until a hardened
/// point makes it 7.5) and prints them differently. Arithmetic follows Python: int op int is int (except `/`), anything
/// with a float is a float.
#[derive(Clone, Copy, Debug)]
pub enum Num {
    I(i64),
    F(f64),
}

impl Num {
    pub fn f(self) -> f64 {
        match self {
            Num::I(i) => i as f64,
            Num::F(f) => f,
        }
    }
    /// The int inside (panics on a float): for values that are ints by construction, like maximum armor.
    pub fn as_int(self) -> i64 {
        match self {
            Num::I(i) => i,
            Num::F(f) => panic!("expected an int, got {}", f),
        }
    }
    /// the value as an int (an int stays; a float that is a whole number is truncated) - for places the Python keeps a
    /// quantity that is an int whenever its inputs were
    pub fn as_int_or_trunc(self) -> i64 {
        match self {
            Num::I(i) => i,
            Num::F(f) => f as i64,
        }
    }
    pub fn is_int(self) -> bool {
        matches!(self, Num::I(_))
    }
    /// `a / b` (true division: always a float)
    pub fn div(self, o: Num) -> Num {
        Num::F(self.f() / o.f())
    }
    /// `a // b`
    pub fn floordiv(self, o: Num) -> Num {
        match (self, o) {
            (Num::I(a), Num::I(b)) => Num::I(py_floordiv(a, b)),
            _ => Num::F((self.f() / o.f()).floor()),
        }
    }
    pub fn to_json(self) -> serde_json::Value {
        match self {
            Num::I(i) => serde_json::json!(i),
            Num::F(f) => serde_json::json!(f),
        }
    }
    pub fn from_json(v: &serde_json::Value) -> Num {
        if let Some(i) = v.as_i64() {
            if v.is_i64() || v.is_u64() {
                return Num::I(i);
            }
        }
        Num::F(v.as_f64().expect("a number"))
    }
    /// Python's `str(x)`
    pub fn py_str(self) -> String {
        match self {
            Num::I(i) => i.to_string(),
            Num::F(f) => py_float_str(f),
        }
    }
    /// Python's `format(x, "g")`
    pub fn fmt_g(self) -> String {
        py_fmt_g(self.f())
    }
}

impl PartialEq for Num {
    fn eq(&self, o: &Num) -> bool {
        self.f() == o.f()
    }
}
impl PartialOrd for Num {
    fn partial_cmp(&self, o: &Num) -> Option<std::cmp::Ordering> {
        match (self, o) {
            (Num::I(a), Num::I(b)) => a.partial_cmp(b),
            _ => self.f().partial_cmp(&o.f()),
        }
    }
}
impl std::ops::Add for Num {
    type Output = Num;
    fn add(self, o: Num) -> Num {
        match (self, o) {
            (Num::I(a), Num::I(b)) => Num::I(a + b),
            _ => Num::F(self.f() + o.f()),
        }
    }
}
impl std::ops::Sub for Num {
    type Output = Num;
    fn sub(self, o: Num) -> Num {
        match (self, o) {
            (Num::I(a), Num::I(b)) => Num::I(a - b),
            _ => Num::F(self.f() - o.f()),
        }
    }
}
impl std::ops::Mul for Num {
    type Output = Num;
    fn mul(self, o: Num) -> Num {
        match (self, o) {
            (Num::I(a), Num::I(b)) => Num::I(a * b),
            _ => Num::F(self.f() * o.f()),
        }
    }
}
impl From<i64> for Num {
    fn from(i: i64) -> Num {
        Num::I(i)
    }
}

/// Python's `max(a, b)`: the first of equals.
pub fn py_max(a: Num, b: Num) -> Num {
    if b > a {
        b
    } else {
        a
    }
}

/// Python's `min(a, b)`: the first of equals.
pub fn py_min(a: Num, b: Num) -> Num {
    if b < a {
        b
    } else {
        a
    }
}

/// Python's `format(x, "g")` for a float: 6 significant digits, trailing zeros removed, exponent form when the
/// exponent is < -4 or >= 6.
pub fn py_fmt_g(x: f64) -> String {
    if x.is_nan() {
        return "nan".to_string();
    }
    if x.is_infinite() {
        return if x > 0.0 { "inf" } else { "-inf" }.to_string();
    }
    if x == 0.0 {
        return if x.is_sign_negative() { "-0" } else { "0" }.to_string();
    }
    let e = format!("{:.5e}", x); // d.dddddde<exp>, correctly rounded to 6 significant digits
    let (mant, exp) = e.split_once('e').unwrap();
    let exp: i32 = exp.parse().unwrap();
    if (-4..6).contains(&exp) {
        let decimals = (5 - exp).max(0) as usize;
        let s = format!("{:.*}", decimals, x);
        if s.contains('.') {
            s.trim_end_matches('0').trim_end_matches('.').to_string()
        } else {
            s
        }
    } else {
        let m = if mant.contains('.') { mant.trim_end_matches('0').trim_end_matches('.') } else { mant };
        format!("{}e{}{:02}", m, if exp < 0 { '-' } else { '+' }, exp.abs())
    }
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
    fn g_format_matches_python() {
        assert_eq!(py_fmt_g(5.0), "5");
        assert_eq!(py_fmt_g(7.5), "7.5");
        assert_eq!(py_fmt_g(0.1), "0.1");
        assert_eq!(py_fmt_g(123456.0), "123456");
        assert_eq!(py_fmt_g(1234567.0), "1.23457e+06");
        assert_eq!(py_fmt_g(0.0001), "0.0001");
        assert_eq!(py_fmt_g(0.00001), "1e-05");
        assert_eq!(py_fmt_g(3.14159265), "3.14159");
        assert_eq!(py_fmt_g(-2.5), "-2.5");
        assert_eq!(py_fmt_g(100.0), "100");
    }

    #[test]
    fn num_arithmetic_keeps_python_types() {
        assert_eq!((Num::I(5) - Num::I(2)).py_str(), "3");
        assert_eq!((Num::I(5) - Num::F(2.0)).py_str(), "3.0");
        assert_eq!(Num::I(5).div(Num::I(2)).py_str(), "2.5");
        assert_eq!(Num::I(7).floordiv(Num::I(2)).py_str(), "3");
        assert_eq!(py_max(Num::I(0), Num::F(0.0)).py_str(), "0");
        assert_eq!(py_min(Num::F(2.0), Num::I(2)).py_str(), "2.0");
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

/// Python's `f"{x:.{n}f}"`: the exact binary value rounded half to even (Rust's own formatter breaks exact ties the
/// other way: 3.375 prints 3.37 there, 3.38 in Python).
pub fn fixed(x: f64, n: usize) -> String {
    let plain = format!("{:.*}", n, x);
    if !x.is_finite() {
        return plain;
    }
    let long = format!("{:.*}", n + 30, x);
    let (int_part, frac) = long.split_once('.').unwrap();
    let tail = &frac[n..];
    if !(tail.starts_with('5') && tail[1..].chars().all(|c| c == '0')) {
        return plain;
    }
    // an exact tie: round to the even last digit (truncated value keeps its digit when that is even)
    let kept = format!("{}.{}", int_part, &frac[..n]);
    let kept = if n == 0 { int_part.to_string() } else { kept };
    let last = kept.chars().rev().find(|c| c.is_ascii_digit()).unwrap().to_digit(10).unwrap();
    if last % 2 == 0 { kept } else { plain_up(&kept, n) }
}

fn plain_up(kept: &str, n: usize) -> String {
    // add one unit in the last place to a truncated decimal string
    let neg = kept.starts_with('-');
    let digits: Vec<char> = kept.trim_start_matches('-').chars().collect();
    let mut out: Vec<char> = digits.clone();
    let mut i = out.len();
    loop {
        if i == 0 {
            out.insert(0, '1');
            break;
        }
        i -= 1;
        if out[i] == '.' {
            continue;
        }
        if out[i] == '9' {
            out[i] = '0';
        } else {
            out[i] = (out[i] as u8 + 1) as char;
            break;
        }
    }
    let _ = n;
    format!("{}{}", if neg { "-" } else { "" }, out.into_iter().collect::<String>())
}

/// `{}` of Fx(x, n) prints Python's `{x:.nf}`.
pub struct Fx(pub f64, pub usize);
impl std::fmt::Display for Fx {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&fixed(self.0, self.1))
    }
}
