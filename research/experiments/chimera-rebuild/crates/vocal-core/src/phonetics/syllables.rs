//! 固定版CHIMERA（MIT）の歌詞の音節化。英語の歌唱用には語の完全形を使う。

use super::{Segment, catalog, korean, mandarin, russian};
use serde::{Deserialize, Serialize};

const ENGLISH_ONSETS: &str = "p b t d k g f v θ ð s z ʃ ʒ h m n l ɹ w j tʃ dʒ pl bl kl gl fl sl pɹ bɹ tɹ dɹ kɹ gɹ fɹ θɹ ʃɹ sp st sk sm sn sw sf tw kw dw gw θw pj bj kj gj mj nj fj vj hj lj spl spɹ stɹ skɹ skw skj spj";

#[derive(Clone, Debug, PartialEq, Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct SyllableParts {
    pub onset: Vec<Segment>,
    pub nucleus: Segment,
    pub coda: Vec<Segment>,
}

#[derive(Clone, Debug, Default, PartialEq, Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Syllable {
    pub text: String,
    pub onset: Vec<Segment>,
    pub nucleus: Segment,
    pub coda: Vec<Segment>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub melisma: Option<bool>,
    #[serde(default)]
    pub word_end: bool,
    #[serde(default)]
    pub phrase_end: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub nasal_lead: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub closing: Option<f64>,
}

pub(super) fn is_nucleus(ipa: &str) -> bool {
    catalog::is_calibrated_vowel(ipa) || catalog::TIMING.expansions.contains_key(ipa)
}

pub fn syllabify(segments: &[Segment]) -> Vec<SyllableParts> {
    syllabify_with(segments, is_english_onset)
}

pub(super) fn is_english_onset(cluster: &[Segment]) -> bool {
    let onset: String = cluster.iter().map(|s| s.ipa.as_str()).collect();
    ENGLISH_ONSETS
        .split_ascii_whitespace()
        .any(|valid| valid == onset)
}

pub(super) fn syllabify_with(
    segments: &[Segment],
    onset_allowed: impl Fn(&[Segment]) -> bool,
) -> Vec<SyllableParts> {
    let nuclei: Vec<_> = segments
        .iter()
        .enumerate()
        .filter_map(|(i, s)| is_nucleus(&s.ipa).then_some(i))
        .collect();
    let mut result = Vec::with_capacity(nuclei.len());
    let mut start = 0;
    for (i, &center) in nuclei.iter().enumerate() {
        let end = nuclei.get(i + 1).map_or(segments.len(), |&next| {
            (center + 1..next)
                .find(|&split| onset_allowed(&segments[split..next]))
                .unwrap_or(next)
        });
        result.push(SyllableParts {
            onset: segments[start..center].to_vec(),
            nucleus: segments[center].clone(),
            coda: segments[center + 1..end].to_vec(),
        });
        start = end;
    }
    result
}

fn lower_ascii(unit: u16) -> u16 {
    if (b'A' as u16..=b'Z' as u16).contains(&unit) {
        unit + 32
    } else {
        unit
    }
}

fn spelling_vowel(unit: u16) -> bool {
    b"aeiouy".iter().any(|&v| u16::from(v) == lower_ascii(unit))
}

pub fn split_spelling(word: &str, count: usize) -> Vec<String> {
    if count <= 1 {
        return vec![word.to_owned()];
    }
    let original: Vec<_> = word.encode_utf16().collect();
    let lower: Vec<_> = word.to_lowercase().encode_utf16().collect();
    let mut groups = Vec::new();
    let mut end = 0;
    while end < lower.len() {
        if !spelling_vowel(lower[end]) {
            end += 1;
            continue;
        }
        let start = end;
        while end < lower.len() && spelling_vowel(lower[end]) {
            end += 1;
        }
        groups.push((start, end));
    }
    let len = original.len();
    let ends_in_silent_e = match original.as_slice() {
        [.., a, e] if lower_ascii(*e) == u16::from(b'e') && !spelling_vowel(*a) => {
            !matches!(original.as_slice(), [.., c, l, _] if lower_ascii(*l)==u16::from(b'l')
                && !spelling_vowel(*c) && lower_ascii(*c)!=u16::from(b'l'))
        }
        _ => false,
    };
    if ends_in_silent_e && groups.len() > 1 && groups.last().unwrap().0 + 1 == len {
        groups.pop();
    }
    if groups.len() < count {
        let mut parts = vec![word.to_owned()];
        parts.resize(count, "~".to_owned());
        return parts;
    }
    groups.truncate(count);
    let mut cuts = vec![0];
    for pair in groups.windows(2) {
        let start = pair[0].1;
        let end = pair[1].0;
        let gap = end - start;
        let digraph = gap >= 2
            && original.get(end - 2..end).is_some_and(|units| {
                [b"th", b"sh", b"ch", b"ph", b"wh", b"ck", b"gh"]
                    .iter()
                    .any(|pair| {
                        units
                            .iter()
                            .map(|&u| lower_ascii(u))
                            .eq(pair.iter().map(|&b| u16::from(b)))
                    })
            });
        cuts.push(if digraph { end - 2 } else { start + gap / 2 });
    }
    cuts.push(len);
    cuts.windows(2)
        .map(|range| {
            let a = range[0].min(len);
            let b = range[1].min(len).max(a);
            String::from_utf16_lossy(&original[a..b])
        })
        .collect()
}

fn lyric_space(c: char) -> bool {
    matches!(c, '\t'..='\r' | ' ' | '\u{00a0}' | '\u{1680}' | '\u{2000}'..='\u{200a}' |
        '\u{2028}' | '\u{2029}' | '\u{202f}' | '\u{205f}' | '\u{3000}' | '\u{feff}')
}

fn starts_english(c: char) -> bool {
    c.is_ascii_alphabetic() || c == '\''
}

fn read_word(chars: &[char], index: &mut usize, continues: impl Fn(char) -> bool) -> String {
    let start = *index;
    *index += 1;
    while chars.get(*index).is_some_and(|&c| continues(c)) {
        *index += 1;
    }
    chars[start..*index].iter().collect()
}

fn english_word(word: &str, pronounce: &impl Fn(&str) -> Vec<Segment>) -> Vec<Syllable> {
    let mut output = Vec::new();
    let parts: Vec<_> = word.split('-').filter(|s| !s.is_empty()).collect();
    for part in &parts {
        let sounds = syllabify(&pronounce(&part.to_lowercase()));
        let labels = if parts.len() > 1 {
            let mut labels = vec![(*part).to_owned()];
            labels.resize(sounds.len(), "~".to_owned());
            labels
        } else {
            split_spelling(part, sounds.len())
        };
        output.extend(sounds.into_iter().zip(labels).map(|(s, text)| Syllable {
            text,
            onset: s.onset,
            nucleus: s.nucleus,
            coda: s.coda,
            ..Syllable::default()
        }));
    }
    output
}

pub fn read_lyrics(text: &str, pronounce: impl Fn(&str) -> Vec<Segment>) -> Vec<Syllable> {
    let normalized = text.replace('’', "'");
    let chars: Vec<_> = normalized.chars().collect();
    let mut output = Vec::<Syllable>::new();
    let mut previous_russian = None::<String>;
    let mut pinyin_barred_until = 0;
    let mut i = 0;
    while i < chars.len() {
        let c = chars[i];
        let typed = if i >= pinyin_barred_until && mandarin::starts_pinyin(c) {
            let mut end = i;
            let word = read_word(&chars, &mut end, mandarin::continues_pinyin);
            let syllables = mandarin::typed_syllables(&word);
            if syllables.is_some() {
                i = end;
            } else {
                // 同じ語の途中を改めてピンインとして受理しない。
                pinyin_barred_until = end;
            }
            syllables
        } else {
            None
        };
        let word_syllables = if let Some(syllables) = typed {
            previous_russian = None;
            Some(syllables)
        } else if starts_english(c) {
            let word = read_word(&chars, &mut i, |ch| starts_english(ch) || ch == '-');
            previous_russian = None;
            Some(english_word(&word, &pronounce))
        } else if korean::starts_word(c) {
            let word = read_word(&chars, &mut i, korean::continues_word);
            previous_russian = None;
            Some(korean::word_syllables(&word))
        } else if russian::starts_word(c) {
            let word = read_word(&chars, &mut i, russian::continues_word);
            let syllables = russian::word_syllables(&word, previous_russian.as_deref());
            previous_russian = Some(word);
            Some(syllables)
        } else if mandarin::is_han(c) {
            let word = read_word(&chars, &mut i, mandarin::is_han);
            previous_russian = None;
            Some(mandarin::fixed_lexicon().syllables(&word))
        } else {
            None
        };
        if let Some(mut syllables) = word_syllables {
            if let Some(last) = syllables.last_mut() {
                last.word_end = true;
            }
            output.append(&mut syllables);
            continue;
        }
        if ".,;:!?\n，。！？；：、".contains(c) {
            previous_russian = None;
            if let Some(last) = output.last_mut() {
                last.phrase_end = true;
            }
        } else if matches!(c, '~' | '-')
            && (i == 0 || lyric_space(chars[i - 1]))
            && chars.get(i + 1).is_none_or(|&s| lyric_space(s))
            && let Some(last) = output.last()
        {
            output.push(Syllable {
                text: "~".to_owned(),
                onset: Vec::new(),
                nucleus: last.nucleus.clone(),
                coda: Vec::new(),
                melisma: Some(true),
                word_end: last.word_end,
                ..Syllable::default()
            });
        }
        i += 1;
    }
    output
}
