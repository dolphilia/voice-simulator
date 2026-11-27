//! 英語の正規化、CMUdictの照合、発音規則と句の計画。

mod spelling;

use super::{
    Intonation, Segment,
    speech::{pitch_gestures, speech_gestures_with_intonation, supported_speech_symbol},
    timing::{self, Timing},
};
use crate::anatomy::{BodyMix, BodyName};
use crate::score::Gesture;
use serde::Serialize;
use std::collections::HashMap;

const FUNCTION_WORDS: &str = "a an the of to in on at by for from with as and or but nor so if is am are was were be been do does did has have had will would can could should shall may might must it its i you he she we they me him her us them my your his our their this that than then there not no";

#[derive(Default)]
pub struct English<'a> {
    dictionary: HashMap<&'a str, &'a str>,
}

#[derive(Clone, Copy, Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum WordSource {
    Homograph,
    Dictionary,
    Hyphenated,
    Rules,
}

#[derive(Serialize)]
pub struct Pronunciation {
    pub source: WordSource,
    pub segments: Vec<Segment>,
}

#[derive(Serialize)]
pub struct Phrase {
    pub words: Vec<String>,
    pub sources: Vec<WordSource>,
    pub segments: Vec<Segment>,
    pub intonation: Intonation,
    pub pause: f64,
}

impl<'a> English<'a> {
    pub fn with_dictionary(tsv: &'a str) -> Self {
        let dictionary = tsv
            .split('\n')
            .filter_map(|line| line.split_once('\t').filter(|(word, _)| !word.is_empty()))
            .collect();
        Self { dictionary }
    }

    pub fn dictionary_entries(&self) -> usize {
        self.dictionary.len()
    }

    pub fn pronounce(&self, word: &str, reduce: bool) -> Pronunciation {
        let lower = word.to_lowercase();
        self.normalized_word(lower.trim_matches('\''), reduce)
    }

    fn normalized_word(&self, word: &str, reduce: bool) -> Pronunciation {
        let exception = match word {
            "wind" => Some("W IH1 N D"),
            "read" => Some("R IY1 D"),
            "live" => Some("L IH1 V"),
            "lead" => Some("L IY1 D"),
            "close" => Some("K L OW1 Z"),
            "wound" => Some("W UW1 N D"),
            _ => None,
        };
        let entry = exception
            .map(|arpabet| (arpabet, WordSource::Homograph))
            .or_else(|| {
                self.dictionary
                    .get(word)
                    .filter(|e| !e.is_empty())
                    .map(|&e| (e, WordSource::Dictionary))
            });
        let (source, segments) = if let Some((entry, source)) = entry {
            let mut segments = arpabet(entry);
            if reduce && FUNCTION_WORDS.split_ascii_whitespace().any(|w| w == word) {
                let schwa = segments.iter().filter(|s| english_vowel(&s.ipa)).count() == 1
                    && !matches!(word, "you" | "do" | "to" | "who" | "not" | "no");
                for segment in &mut segments {
                    segment.stress = Some(0);
                    if schwa
                        && matches!(
                            segment.ipa.as_str(),
                            "ʌ" | "æ" | "ɑ" | "ɛ" | "ɔ" | "u" | "ʊ"
                        )
                    {
                        segment.ipa = "ə".into();
                    }
                }
            }
            (source, segments)
        } else if word.contains('-') {
            (
                WordSource::Hyphenated,
                word.split('-')
                    .flat_map(|part| {
                        self.normalized_word(part.trim_matches('\''), reduce)
                            .segments
                    })
                    .collect(),
            )
        } else {
            (WordSource::Rules, letter_to_sound(word))
        };
        Pronunciation { source, segments }
    }

    pub fn phrases(&self, text: &str) -> Vec<Phrase> {
        let text = spelling::normalize(text);
        let mut result = Vec::new();
        let mut iter = text.char_indices().peekable();
        let mut from = 0;
        while let Some((idx, ch)) = iter.next() {
            if !is_punctuation(ch) {
                continue;
            }
            let mut until = idx + 1;
            while let Some(&(pos, next)) = iter.peek() {
                if !is_punctuation(next) {
                    break;
                }
                iter.next();
                until = pos + 1;
            }
            result.extend(self.phrase(&text[from..idx], &text[idx..until]));
            from = until;
        }
        result.extend(self.phrase(&text[from..], ""));
        result
    }

    fn phrase(&self, before: &str, punctuation: &str) -> Option<Phrase> {
        let mut words = Vec::new();
        let mut sources = Vec::new();
        let mut segments = Vec::new();
        let lower = before.to_lowercase();
        for word in lower.split(|c: char| !c.is_ascii_lowercase() && c != '\'' && c != '-') {
            if word.is_empty() {
                continue;
            }
            let mut pronunciation = self.normalized_word(word.trim_matches('\''), true);
            let Some(last) = pronunciation.segments.last_mut() else {
                continue;
            };
            last.word_end = Some(true);
            segments.append(&mut pronunciation.segments);
            words.push(word.to_owned());
            sources.push(pronunciation.source);
        }
        if segments.is_empty() {
            return None;
        }
        allophones(&mut segments);
        let intonation = if punctuation.contains('?') {
            Intonation::Question
        } else {
            Intonation::Statement
        };
        let pause = if punctuation.contains(['.', '!', '?']) {
            0.35
        } else if punctuation.is_empty() {
            0.30
        } else {
            0.18
        };
        Some(Phrase {
            words,
            sources,
            segments,
            intonation,
            pause,
        })
    }
}

fn is_punctuation(c: char) -> bool {
    matches!(c, '.' | '!' | '?' | ';' | ':' | ',')
}

fn allophones(segments: &mut [Segment]) {
    for index in 1..segments.len().saturating_sub(1) {
        let previous = &segments[index - 1];
        let next = &segments[index + 1];
        if matches!(segments[index].ipa.as_str(), "t" | "d")
            && (english_vowel(&previous.ipa) || previous.ipa == "ɹ")
            && previous.word_end != Some(true)
            && english_vowel(&next.ipa)
            && next.stress.unwrap_or(0) == 0
        {
            segments[index].ipa = "ɾ".into();
        }
    }
    for index in 0..segments.len() {
        if segments[index].ipa == "l"
            && (segments[index].word_end == Some(true)
                || segments
                    .get(index + 1)
                    .is_none_or(|s| !english_vowel(&s.ipa)))
        {
            segments[index].ipa = "ɫ".into();
        }
    }
}

fn english_vowel(ipa: &str) -> bool {
    matches!(
        ipa,
        "ɑ" | "æ"
            | "ʌ"
            | "ə"
            | "ɔ"
            | "aʊ"
            | "aɪ"
            | "ɛ"
            | "ɝ"
            | "ɚ"
            | "eɪ"
            | "ɪ"
            | "i"
            | "oʊ"
            | "ɔɪ"
            | "ʊ"
            | "u"
    )
}

fn segment(ipa: &str, stress: u8) -> Segment {
    Segment {
        ipa: ipa.to_owned(),
        stress: Some(if english_vowel(ipa) { stress } else { 0 }),
        ..Segment::default()
    }
}

pub fn arpabet(input: &str) -> Vec<Segment> {
    input.split(|c: char| matches!(c, '\t'..='\r'|' '|'\u{a0}'|'\u{1680}'|'\u{2000}'..='\u{200a}'|'\u{2028}'|'\u{2029}'|'\u{202f}'|'\u{205f}'|'\u{3000}'|'\u{feff}'))
        .filter_map(|phone| {
            let (symbol, stress) = match phone.as_bytes().last() {
                Some(d @ b'0'..=b'2') => (&phone[..phone.len()-1], d - b'0'),
                _ => (phone, 0),
            };
            let ipa = match symbol {
                "AA" => "ɑ", "AE" => "æ",
                "AH" if stress == 0 => "ə", "AH" => "ʌ",
                "AO" => "ɔ", "AW" => "aʊ", "AY" => "aɪ", "EH" => "ɛ",
                "ER" if stress == 0 => "ɚ", "ER" => "ɝ",
                "EY" => "eɪ", "IH" => "ɪ", "IY" => "i", "OW" => "oʊ", "OY" => "ɔɪ", "UH" => "ʊ", "UW" => "u",
                "B" => "b", "CH" => "tʃ", "D" => "d", "DH" => "ð", "F" => "f", "G" => "g", "HH" => "h",
                "JH" => "dʒ", "K" => "k", "L" => "l", "M" => "m", "N" => "n", "NG" => "ŋ", "P" => "p",
                "R" => "ɹ", "S" => "s", "SH" => "ʃ", "T" => "t", "TH" => "θ", "V" => "v", "W" => "w",
                "Y" => "j", "Z" => "z", "ZH" => "ʒ",
                _ => return None,
            };
            Some(segment(ipa, stress))
        }).collect()
}

pub use spelling::letter_to_sound;

#[derive(Serialize)]
pub struct PlannedPhrase {
    #[serde(flatten)]
    pub phrase: Phrase,
    pub start_seconds: f64,
    pub end_seconds: f64,
    pub shown: String,
    pub timing: Timing,
    pub pitch: Vec<Gesture>,
}

#[derive(Serialize)]
pub struct TextPlan {
    pub phrases: Vec<PlannedPhrase>,
    pub shown: String,
    pub end_seconds: f64,
    pub render_end_seconds: f64,
    pub unavailable_speech_symbols: Vec<String>,
}

pub const MALE_F0_HZ: f64 = 112.0;
pub const INITIAL_VOICE_F0_HZ: f64 = 110.0;
pub const START_SECONDS: f64 = 0.05;
const TAIL_SECONDS: f64 = 0.30;

/// 上流の英語テキスト発話の基準F0を、混合時は対数空間で補間する。
pub fn default_f0_hz(body: BodyMix) -> f64 {
    body.interpolate_pitch_hz(|preset| match preset {
        BodyName::Male => MALE_F0_HZ,
        BodyName::Female => 205.0,
        BodyName::Child => 250.0,
    })
}

pub fn plan_phrases(
    phrases: Vec<Phrase>,
    start: f64,
    rate: f64,
    f0: f64,
) -> Result<TextPlan, &'static str> {
    if !start.is_finite() || !rate.is_finite() || rate <= 0.0 || !f0.is_finite() || f0 <= 0.0 {
        return Err("英語発話の開始時刻、話速または基準F0を確認してください");
    }
    let mut next = start;
    let mut end = start;
    let mut rows = Vec::new();
    for phrase in phrases {
        let timing = timing::plan(&phrase.segments, next, rate)?;
        let mut shown = String::new();
        for s in &phrase.segments {
            if s.stress == Some(1) {
                shown.push('ˈ');
            }
            shown.push_str(&s.ipa);
        }
        if phrase.intonation == Intonation::Question {
            shown.push('?');
        }
        let pitch = pitch_gestures(&timing, next, f0, phrase.intonation);
        end = timing.end_seconds;
        let pause = phrase.pause;
        rows.push(PlannedPhrase {
            start_seconds: next,
            end_seconds: end,
            phrase,
            shown,
            timing,
            pitch,
        });
        next = end + pause;
    }
    let shown = rows
        .iter()
        .map(|row| row.shown.as_str())
        .collect::<Vec<_>>()
        .join(" | ");
    let unavailable_speech_symbols = rows
        .iter()
        .flat_map(|row| &row.timing.segments)
        .filter(|part| !supported_speech_symbol(part))
        .map(|part| part.segment.ipa.clone())
        .collect::<std::collections::BTreeSet<_>>()
        .into_iter()
        .collect();
    Ok(TextPlan {
        phrases: rows,
        shown,
        end_seconds: end,
        render_end_seconds: end + TAIL_SECONDS,
        unavailable_speech_symbols,
    })
}

/// 英語テキストから、CLIとブラウザで共有する計画と成人男性の調音スコアを作る。
pub fn plan_voice(
    lexicon: &English<'_>,
    text: &str,
    start: f64,
    rate: f64,
    f0: f64,
) -> Result<(TextPlan, Vec<Gesture>), String> {
    plan_voice_with_body(lexicon, text, start, rate, f0, BodyName::Male.into())
}

/// 英語の各句から、選択した体型の調音スコアを作る。
pub fn plan_voice_with_body(
    lexicon: &English<'_>,
    text: &str,
    start: f64,
    rate: f64,
    f0: f64,
    body: BodyMix,
) -> Result<(TextPlan, Vec<Gesture>), String> {
    let plan = plan_phrases(lexicon.phrases(text), start, rate, f0)?;
    if !plan.unavailable_speech_symbols.is_empty() {
        return Err(format!(
            "英語発話に未対応の音素があります ({})",
            plan.unavailable_speech_symbols.join(" ")
        ));
    }
    let mut gestures = Vec::new();
    for row in &plan.phrases {
        gestures.extend(speech_gestures_with_intonation(
            &row.timing,
            row.start_seconds,
            f0,
            row.phrase.intonation,
            body,
        )?);
    }
    Ok((plan, gestures))
}
