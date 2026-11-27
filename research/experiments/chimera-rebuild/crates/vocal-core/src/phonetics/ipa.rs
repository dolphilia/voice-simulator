//! IPAの音素と修飾記号を読み、原文位置と診断を残す。記号表はCHIMERA由来（MIT）。

use super::{Manner, Segment, catalog};
use serde::Serialize;
use std::collections::BTreeSet;
use std::sync::LazyLock;

mod normalization;
use normalization::{Unit, normalize, replace};

const VOWELS: &str = "iyɨʉɯuɪʏʊeøɘɵɤoəɛœɜɞʌɔæɐaɶɑɒɝɚɿʅ";
const MULTI: [&str; 14] = [
    "tʃ", "dʒ", "ts", "dz", "pf", "tɕ", "dʑ", "tʂ", "dʐ", "aɪ", "aʊ", "ɔɪ", "eɪ", "oʊ",
];
const ALIASES: [(&str, &str); 9] = [
    ("t͡ʃ", "tʃ"),
    ("d͡ʒ", "dʒ"),
    ("t͡s", "ts"),
    ("d͡z", "dz"),
    ("ɡ", "g"),
    ("ʧ", "tʃ"),
    ("ʤ", "dʒ"),
    ("r̥", "r"),
    ("ɐ̯", "ɐ"),
];
const NASAL: char = '\u{303}';
const BREATHY: char = '\u{324}';
const SYLLABIC: char = '\u{329}';
const NON_SYLLABIC: char = '\u{32f}';
const VOWEL_FORMS: [(&str, &str); 7] = [
    ("ã", "a\u{303}"),
    ("õ", "o\u{303}"),
    ("ẽ", "e\u{303}"),
    ("ĩ", "i\u{303}"),
    ("ũ", "u\u{303}"),
    ("ỹ", "y\u{303}"),
    ("ṳ", "u\u{324}"),
];

static KNOWN: LazyLock<BTreeSet<&'static str>> = LazyLock::new(|| {
    catalog::consonant_symbols()
        .chain(
            VOWELS
                .char_indices()
                .map(|(i, c)| &VOWELS[i..i + c.len_utf8()]),
        )
        .chain(MULTI)
        .collect()
});

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
pub struct SourceSpan {
    pub start_byte: usize,
    pub end_byte: usize,
}

impl SourceSpan {
    fn join(self, other: Self) -> Self {
        Self {
            start_byte: self.start_byte.min(other.start_byte),
            end_byte: self.end_byte.max(other.end_byte),
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum DiagnosticKind {
    Unknown,
    NoSound,
    IgnoredMark,
}

#[derive(Debug, Serialize)]
pub struct Diagnostic {
    pub kind: DiagnosticKind,
    pub symbol: String,
    pub span: SourceSpan,
}

#[derive(Debug, Default, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SkippedIpa {
    pub unknown: Vec<String>,
    pub no_sound: Vec<String>,
    pub ignored_marks: Vec<String>,
}

#[derive(Debug, Default, Serialize)]
pub struct Analysis {
    pub segments: Vec<Segment>,
    pub segment_spans: Vec<SourceSpan>,
    pub skipped: SkippedIpa,
    pub diagnostics: Vec<Diagnostic>,
}

impl Analysis {
    fn push(&mut self, segment: Segment, span: SourceSpan) {
        self.segments.push(segment);
        self.segment_spans.push(span);
    }

    fn report(&mut self, kind: DiagnosticKind, symbol: String, span: SourceSpan) {
        let group = match kind {
            DiagnosticKind::Unknown => &mut self.skipped.unknown,
            DiagnosticKind::NoSound => &mut self.skipped.no_sound,
            DiagnosticKind::IgnoredMark => &mut self.skipped.ignored_marks,
        };
        if !group.contains(&symbol) {
            group.push(symbol.clone());
        }
        self.diagnostics.push(Diagnostic { kind, symbol, span });
    }

    fn ignore_mark(&mut self, unit: Unit) {
        let mark = unit.letter;
        let symbol = match self.segments.last().filter(|last| last.ipa != "_") {
            Some(last) => format!("{}{mark}", last.ipa),
            None => shown(mark),
        };
        self.report(DiagnosticKind::IgnoredMark, symbol, unit.span);
    }
}

pub fn known_symbols() -> impl Iterator<Item = &'static str> {
    KNOWN.iter().copied()
}

/// 観測用の原文位置を付けて字句解析する。スラッシュ自身は字句の境界を作らない。
pub fn analyze(input: &str) -> Analysis {
    analyze_at(input, 0)
}

/// 発話CLIと同じスラッシュ区切り。返す範囲は空白を除いた原文上のバイト位置。
fn utterance_spans(input: &str) -> impl Iterator<Item = SourceSpan> + '_ {
    let mut offset = 0;
    input.split('/').filter_map(move |part| {
        let left = part.trim_start();
        let trimmed = left.trim_end();
        let start_byte = offset + part.len() - left.len();
        offset += part.len() + 1;
        (!trimmed.is_empty()).then_some(SourceSpan {
            start_byte,
            end_byte: start_byte + trimmed.len(),
        })
    })
}

/// 発話ごとに解析し、すべての範囲を入力全体のバイト位置で返す。
pub fn analyze_utterances(input: &str) -> impl Iterator<Item = (SourceSpan, Analysis)> + '_ {
    utterance_spans(input).map(move |span| {
        let text = &input[span.start_byte..span.end_byte];
        (span, analyze_at(text, span.start_byte))
    })
}

fn analyze_at(input: &str, start_byte: usize) -> Analysis {
    let mut units = normalize(input, start_byte);
    for (from, to) in ALIASES.into_iter().chain(VOWEL_FORMS) {
        replace(&mut units, from, to);
    }
    units.retain(|unit| !matches!(unit.letter, '\u{35c}' | '\u{361}'));

    let mut out = Analysis::default();
    let mut stress = 0;
    let mut position = 0;
    while let Some(&unit) = units.get(position) {
        position += 1;
        match unit.letter {
            'ˈ' | '\'' => stress = 1,
            'ˌ' => stress = 2,
            ' ' | '.' | ',' | '|' => {
                if let Some(last) = out.segments.last_mut() {
                    last.word_end = Some(true);
                }
                if matches!(unit.letter, ',' | '|') {
                    out.push(
                        Segment {
                            ipa: "_".into(),
                            duration_seconds: Some(0.16),
                            ..Segment::default()
                        },
                        unit.span,
                    );
                }
            }
            'ʰ' | '˭' => {
                if let Some(last) = out.segments.last_mut() {
                    last.aspirated = Some(unit.letter == 'ʰ');
                }
            }
            'ʲ' | 'ʱ' => apply_consonant_mark(&mut out, unit),
            NASAL | BREATHY if position >= 2 && length_mark(units[position - 2].letter) => {
                match out.segments.last_mut().filter(|last| is_vowel(&last.ipa)) {
                    Some(last) if unit.letter == NASAL => last.nasalized = Some(true),
                    Some(last) => last.breathy = Some(true),
                    None => out.ignore_mark(unit),
                }
            }
            ch if length_mark(ch) => {
                if let Some(last) = out.segments.last_mut() {
                    let base = if starts_with_vowel_letter(&last.ipa) {
                        0.15
                    } else {
                        0.09
                    };
                    last.duration_seconds = Some(last.duration_seconds.unwrap_or(base) * 1.7);
                }
            }
            SYLLABIC | NON_SYLLABIC => {}
            _ => read_symbol(&units, &mut position, unit, &mut stress, &mut out),
        }
    }
    out.diagnostics
        .sort_by_key(|entry| (entry.span.start_byte, entry.span.end_byte));
    out
}

fn apply_consonant_mark(out: &mut Analysis, unit: Unit) {
    if let Some(last) = out.segments.last_mut()
        && let Some(consonant) = catalog::consonant(&last.ipa)
    {
        match unit.letter {
            'ʲ' if consonant.manner != Manner::Glottal => {
                last.palatalized = Some(true);
                return;
            }
            'ʱ' if consonant.voiced
                && matches!(consonant.manner, Manner::Stop | Manner::Affricate) =>
            {
                last.breathy = Some(true);
                return;
            }
            _ => {}
        }
    }
    out.ignore_mark(unit);
}

fn read_symbol(
    units: &[Unit],
    position: &mut usize,
    first: Unit,
    stress: &mut u8,
    out: &mut Analysis,
) {
    let pair = units.get(*position).and_then(|second| {
        let mut buffer = [0; 8];
        let mut len = first.letter.encode_utf8(&mut buffer).len();
        len += second.letter.encode_utf8(&mut buffer[len..]).len();
        let text = std::str::from_utf8(&buffer[..len]).expect("Unicodeスカラー値2個");
        MULTI
            .into_iter()
            .find(|symbol| *symbol == text)
            .map(|symbol| (symbol, second.span))
    });
    let (ipa, base_span) = if let Some((symbol, span)) = pair {
        *position += 1;
        (symbol.to_owned(), first.span.join(span))
    } else {
        (first.letter.to_string(), first.span)
    };
    let start = *position;
    while units
        .get(*position)
        .is_some_and(|unit| combines(unit.letter))
    {
        *position += 1;
    }
    if !KNOWN.contains(ipa.as_str()) {
        if !first.letter.is_whitespace() && !matches!(first.letter, '/' | '[' | ']') {
            out.report(DiagnosticKind::Unknown, shown(first.letter), base_span);
        }
        return;
    }

    let vowel = is_vowel(&ipa);
    let mut segment = Segment {
        stress: Some(if vowel { std::mem::take(stress) } else { 0 }),
        ipa,
        ..Segment::default()
    };
    let mut unread = String::new();
    let mut unread_span: Option<SourceSpan> = None;
    let mut span = base_span;
    for &mark in &units[start..*position] {
        span = span.join(mark.span);
        match mark.letter {
            NASAL if vowel => segment.nasalized = Some(true),
            BREATHY if vowel => segment.breathy = Some(true),
            SYLLABIC | NON_SYLLABIC => {}
            letter => {
                unread.push(letter);
                unread_span =
                    Some(unread_span.map_or(mark.span, |previous| previous.join(mark.span)));
            }
        }
    }
    if let Some(ignored) = unread_span {
        out.report(
            DiagnosticKind::IgnoredMark,
            format!("{}{unread}", segment.ipa),
            ignored,
        );
    }
    if !catalog::has_sound(&segment.ipa) {
        out.report(DiagnosticKind::NoSound, segment.ipa.clone(), base_span);
    }
    out.push(segment, span);
}

fn is_vowel(ipa: &str) -> bool {
    starts_with_vowel_letter(ipa) && catalog::consonant(ipa).is_none()
}

fn starts_with_vowel_letter(ipa: &str) -> bool {
    ipa.chars()
        .next()
        .is_some_and(|letter| VOWELS.contains(letter))
}

fn length_mark(letter: char) -> bool {
    matches!(letter, 'ː' | ':')
}

fn combines(letter: char) -> bool {
    ('\u{300}'..='\u{36f}').contains(&letter)
}

fn shown(letter: char) -> String {
    if combines(letter) {
        format!("◌{letter}")
    } else {
        letter.to_string()
    }
}
