//! ASCII数字の正規化と未知語の綴り規則。規則表はCHIMERA由来（MIT）。

use super::{Segment, english_vowel, segment};
use std::sync::LazyLock;

type Rule<'a> = (&'a str, &'a str, &'a str, &'a str);
static RULES: LazyLock<Vec<Rule<'static>>> = LazyLock::new(|| {
    serde_json::from_str(include_str!("lts.generated.json")).expect("固定版の綴り規則")
});

const ONES: [&str; 20] = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
];
const TENS: [&str; 10] = [
    "", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety",
];

pub(super) fn normalize(text: &str) -> String {
    let mut output = String::with_capacity(text.len());
    let mut digits = None;
    for (offset, c) in text.char_indices() {
        if c.is_ascii_digit() {
            digits.get_or_insert(offset);
        } else {
            if let Some(start) = digits.take() {
                spell_digits(&text[start..offset], &mut output);
            }
            output.push(if c == '’' { '\'' } else { c });
        }
    }
    if let Some(start) = digits {
        spell_digits(&text[start..], &mut output);
    }
    output
}

fn spell_digits(digits: &str, out: &mut String) {
    let number: f64 = digits.parse().expect("ASCIIの数字列");
    out.push(' ');
    if number < 1_000_000.0 {
        cardinal(number as usize, out);
    } else if number.is_finite() {
        let shown = if number < 1e21 {
            format!("{number}")
        } else {
            format!("{number:e}")
        };
        for digit in shown.bytes().filter(u8::is_ascii_digit) {
            out.push_str(ONES[(digit - b'0') as usize]);
            out.push(' ');
        }
    }
    out.push(' ');
}

fn cardinal(number: usize, out: &mut String) {
    let (place, label) = match number {
        0..=19 => {
            out.push_str(ONES[number]);
            return;
        }
        20..=99 => {
            out.push_str(TENS[number / 10]);
            (10, "")
        }
        100..=999 => (100, " hundred"),
        _ => (1000, " thousand"),
    };
    if place >= 100 {
        cardinal(number / place, out);
        out.push_str(label);
    }
    let rest = number % place;
    if rest != 0 {
        out.push(' ');
        cardinal(rest, out);
    }
}

pub fn letter_to_sound(word: &str) -> Vec<Segment> {
    let units: Vec<_> = word.encode_utf16().collect();
    let mut output = Vec::new();
    let mut first_vowel = true;
    let mut offset = 0;
    while offset < units.len() {
        if let Some((_, grapheme, _, phones)) =
            RULES.iter().find(|&&(before, grapheme, after, _)| {
                let end = offset + grapheme.len();
                units
                    .get(offset..end)
                    .is_some_and(|run| run.iter().copied().eq(grapheme.bytes().map(u16::from)))
                    && context(before.bytes().rev(), units[..offset].iter().rev().copied())
                    && context(after.bytes(), units[end..].iter().copied())
            })
        {
            for phone in phones.split_ascii_whitespace() {
                let vowel = english_vowel(phone);
                output.push(segment(phone, u8::from(first_vowel && vowel)));
                first_vowel &= !vowel;
            }
            offset += grapheme.len();
        } else {
            offset += 1;
        }
    }
    output
}

fn context(pattern: impl Iterator<Item = u8>, mut letters: impl Iterator<Item = u16>) -> bool {
    let vowel = |c| "aeiouy".bytes().any(|letter| c == u16::from(letter));
    for class in pattern {
        let letter = letters.next();
        let matches = match class {
            b'#' => letter.is_none(),
            b'V' => letter.is_some_and(vowel),
            b'C' => letter.is_some_and(|c| !vowel(c)),
            byte => letter == Some(u16::from(byte)),
        };
        if !matches {
            return false;
        }
    }
    true
}
