//! 中国語歌詞の読みと音節化。音素表・発音規則の出典は固定版CHIMERA
//! （Copyright Jameson Hodge、MIT）。辞書の通知は data/MANDARIN-PINYIN-LICENSE.txt。

use super::{Segment, catalog::TIMING, syllables::Syllable};
use flate2::read::GzDecoder;
use std::{collections::HashMap, io::Read, sync::LazyLock};

const DICTIONARY: &[u8] = include_bytes!("../../../../data/mandarin.txt.gz");
static FIXED_LEXICON: LazyLock<MandarinLexicon> = LazyLock::new(|| {
    let mut text = String::new();
    GzDecoder::new(DICTIONARY)
        .read_to_string(&mut text)
        .expect("固定の中国語発音辞書");
    MandarinLexicon::from_text(&text)
});

pub fn fixed_lexicon() -> &'static MandarinLexicon {
    &FIXED_LEXICON
}

pub(super) fn is_han(c: char) -> bool {
    matches!(c, '\u{3400}'..='\u{4dbf}' | '\u{4e00}'..='\u{9fff}' | '\u{f900}'..='\u{faff}')
}

#[derive(Default)]
pub struct MandarinLexicon {
    characters: HashMap<char, String>,
    phrases: HashMap<String, Vec<String>>,
    longest_phrase: usize,
}

impl MandarinLexicon {
    fn from_text(text: &str) -> Self {
        let mut lexicon = Self::default();
        for line in text.lines() {
            let Some((word, reading)) = line.split_once('\t') else {
                continue;
            };
            let readings: Vec<_> = reading.split(' ').filter(|s| !s.is_empty()).collect();
            let width = word.chars().count();
            match readings.as_slice() {
                [single] if width == 1 => {
                    lexicon
                        .characters
                        .insert(word.chars().next().unwrap(), (*single).to_owned());
                }
                _ if width > 1 && width == readings.len() => {
                    lexicon.longest_phrase = lexicon.longest_phrase.max(width);
                    lexicon.phrases.insert(
                        word.to_owned(),
                        readings.into_iter().map(str::to_owned).collect(),
                    );
                }
                _ => {}
            }
        }
        lexicon
    }

    /// 漢字と同じ順に声調変化後の読みを返す。未知字は空文字列。
    pub fn read(&self, text: &str) -> Vec<String> {
        self.read_sources(&text.chars().collect::<Vec<_>>()).0
    }

    fn read_sources(&self, chars: &[char]) -> (Vec<String>, Vec<bool>) {
        let mut readings = Vec::with_capacity(chars.len());
        let mut phrase_source = Vec::with_capacity(chars.len());
        while readings.len() < chars.len() {
            let i = readings.len();
            let longest = self.longest_phrase.min(chars.len() - i);
            let phrase = (2..=longest).rev().find_map(|len| {
                let key: String = chars[i..i + len].iter().collect();
                self.phrases.get(&key)
            });
            if let Some(phrase) = phrase {
                readings.extend(phrase.iter().cloned());
                phrase_source.extend(std::iter::repeat_n(true, phrase.len()));
            } else {
                readings.push(self.characters.get(&chars[i]).cloned().unwrap_or_default());
                phrase_source.push(false);
            }
        }
        for (i, c) in chars.iter().enumerate() {
            let target = match (c, readings.get(i + 1).map(|s| tone(s))) {
                ('不' | '一', Some(4)) => 2,
                ('一', Some(1..=3)) => 4,
                _ => continue,
            };
            set_tone(&mut readings[i], target);
        }
        third_tones(&mut readings);
        (readings, phrase_source)
    }

    pub(super) fn syllables(&self, text: &str) -> Vec<Syllable> {
        let chars: Vec<_> = text.chars().collect();
        let (readings, phrase_source) = self.read_sources(&chars);
        let mut result: Vec<Syllable> = Vec::with_capacity(chars.len());
        for (i, (c, pinyin)) in chars.iter().zip(&readings).enumerate() {
            let previous = i.checked_sub(1).map(|j| chars[j]);
            if *c == '儿'
                && previous.is_some_and(|p| {
                    "哪这那".contains(p)
                        || (!"女婴孤幼男健宠胎孙侄托".contains(p)
                            && (pinyin == "er5" || !phrase_source[i]))
                })
                && let Some(last) = result.last_mut()
            {
                rhotic_ending(last);
                last.text.push('儿');
            } else {
                result.extend(pinyin_syllable(pinyin, &c.to_string()));
            }
        }
        result
    }
}

fn tone(reading: &str) -> u8 {
    reading
        .as_bytes()
        .last()
        .filter(|b| b.is_ascii_digit())
        .map_or(5, |b| b - b'0')
}

fn set_tone(reading: &mut String, number: u8) {
    if reading.as_bytes().last().is_some_and(u8::is_ascii_digit) {
        reading.pop();
        reading.push(char::from(b'0' + number));
    }
}

fn third_tones(readings: &mut [String]) {
    for i in 0..readings.len().saturating_sub(1) {
        if tone(&readings[i]) == 3 && tone(&readings[i + 1]) == 3 {
            set_tone(&mut readings[i], 2);
        }
    }
}

fn segment(ipa: &str) -> Segment {
    Segment {
        ipa: ipa.to_owned(),
        ..Segment::default()
    }
}

// 声母と韻母の対応表は固定上流の発音データ。
fn initial(i: &str) -> Option<(&'static str, Option<bool>)> {
    Some(match i {
        "b" => ("p", Some(false)),
        "p" => ("p", Some(true)),
        "m" => ("m", None),
        "f" => ("f", None),
        "d" => ("t", Some(false)),
        "t" => ("t", Some(true)),
        "n" => ("n", None),
        "l" => ("l", None),
        "g" => ("k", Some(false)),
        "k" => ("k", Some(true)),
        "h" => ("x", None),
        "j" => ("tɕ", Some(false)),
        "q" => ("tɕ", Some(true)),
        "x" => ("ɕ", None),
        "zh" => ("tʂ", Some(false)),
        "ch" => ("tʂ", Some(true)),
        "sh" => ("ʂ", None),
        "r" => ("ɻ", None),
        "z" => ("ts", Some(false)),
        "c" => ("ts", Some(true)),
        "s" => ("s", None),
        _ => return None,
    })
}

fn final_parts(
    f: &str,
) -> Option<(
    &'static [&'static str],
    &'static str,
    &'static [&'static str],
)> {
    const N: &[&str] = &[];
    Some(match f {
        "a" => (N, "a", N),
        "o" => (&["w"], "ɔ", N),
        "e" => (N, "ɤ", N),
        "i" => (N, "i", N),
        "u" => (N, "u̠", N),
        "v" => (N, "y", N),
        "er" => (N, "ɝ", N),
        "ai" => (N, "aɪ", N),
        "ei" => (N, "eɪ", N),
        "ao" => (N, "aʊ̠", N),
        "ou" => (N, "əʊ̠", N),
        "an" => (N, "a", &["n"]),
        "en" => (N, "ə", &["n"]),
        "ang" => (N, "ɑ", &["ŋ"]),
        "eng" => (N, "ɤ", &["ŋ"]),
        "ong" => (N, "ʊ̠", &["ŋ"]),
        "ia" => (&["j"], "a", N),
        // 間投詞の yo（哟・唷）は [jɔ]。
        "io" => (&["j"], "ɔ", N),
        "ie" => (&["j"], "ɛ", N),
        "iao" => (&["j"], "aʊ̠", N),
        "iu" | "iou" => (&["j"], "əʊ̠", N),
        "ian" => (&["j"], "ɛ", &["n"]),
        "in" => (N, "i", &["n"]),
        "iang" => (&["j"], "ɑ", &["ŋ"]),
        "ing" => (N, "i", &["ŋ"]),
        "iong" => (&["j"], "ʊ̠", &["ŋ"]),
        "ua" => (&["w"], "a", N),
        "uo" => (&["w"], "ɔ", N),
        "uai" => (&["w"], "aɪ", N),
        "ui" | "uei" => (&["w"], "eɪ", N),
        "uan" => (&["w"], "a", &["n"]),
        "un" | "uen" => (&["w"], "ə", &["n"]),
        "uang" => (&["w"], "ɑ", &["ŋ"]),
        "ueng" => (&["w"], "ə", &["ŋ"]),
        "ve" | "ue" => (&["ɥ"], "ɛ", N),
        "van" => (&["ɥ"], "ɛ", &["n"]),
        "vn" => (N, "y", &["n"]),
        // 音節を成す鼻音（嗯、n、ng、m）。
        "n" | "ng" | "m" | "hm" | "hng" => (N, "ə", &["n"]),
        _ => return None,
    })
}

#[rustfmt::skip]
const SYLLABLES: &[&str] = &[
    "a", "ai", "an", "ang", "ao", "ba", "bai", "ban", "bang", "bao", "bei", "ben", "beng", "bi",
    "bian", "biao", "bie", "bin", "bing", "bo", "bu", "ca", "cai", "can", "cang", "cao", "ce",
    "cen", "ceng", "cha", "chai", "chan", "chang", "chao", "che", "chen", "cheng", "chi", "chong",
    "chou", "chu", "chua", "chuai", "chuan", "chuang", "chui", "chun", "chuo", "ci", "cong", "cou",
    "cu", "cuan", "cui", "cun", "cuo", "da", "dai", "dan", "dang", "dao", "de", "dei", "den",
    "deng", "di", "dia", "dian", "diao", "die", "ding", "diu", "dong", "dou", "du", "duan", "dui",
    "dun", "duo", "e", "ei", "en", "eng", "er", "fa", "fan", "fang", "fei", "fen", "feng", "fiao",
    "fo", "fou", "fu", "ga", "gai", "gan", "gang", "gao", "ge", "gei", "gen", "geng", "gong", "gou",
    "gu", "gua", "guai", "guan", "guang", "gui", "gun", "guo", "ha", "hai", "han", "hang", "hao",
    "he", "hei", "hen", "heng", "hong", "hou", "hu", "hua", "huai", "huan", "huang", "hui", "hun",
    "huo", "ji", "jia", "jian", "jiang", "jiao", "jie", "jin", "jing", "jiong", "jiu", "ju", "juan",
    "jue", "jun", "ka", "kai", "kan", "kang", "kao", "ke", "ken", "keng", "kong", "kou", "ku",
    "kua", "kuai", "kuan", "kuang", "kui", "kun", "kuo", "la", "lai", "lan", "lang", "lao", "le",
    "lei", "leng", "li", "lia", "lian", "liang", "liao", "lie", "lin", "ling", "liu", "long", "lou",
    "lu", "luan", "lun", "luo", "lv", "lve", "m", "ma", "mai", "man", "mang", "mao", "me", "mei",
    "men", "meng", "mi", "mian", "miao", "mie", "min", "ming", "miu", "mo", "mou", "mu", "n", "na",
    "nai", "nan", "nang", "nao", "ne", "nei", "nen", "neng", "ni", "nian", "niang", "niao", "nie",
    "nin", "ning", "niu", "nong", "nou", "nu", "nuan", "nun", "nuo", "nv", "nve", "o", "ou", "pa",
    "pai", "pan", "pang", "pao", "pei", "pen", "peng", "pi", "pian", "piao", "pie", "pin", "ping",
    "po", "pou", "pu", "qi", "qia", "qian", "qiang", "qiao", "qie", "qin", "qing", "qiong", "qiu",
    "qu", "quan", "que", "qun", "ran", "rang", "rao", "re", "ren", "reng", "ri", "rong", "rou",
    "ru", "rua", "ruan", "rui", "run", "ruo", "sa", "sai", "san", "sang", "sao", "se", "sen",
    "seng", "sha", "shai", "shan", "shang", "shao", "she", "shei", "shen", "sheng", "shi", "shou",
    "shu", "shua", "shuai", "shuan", "shuang", "shui", "shun", "shuo", "si", "song", "sou", "su",
    "suan", "sui", "sun", "suo", "ta", "tai", "tan", "tang", "tao", "te", "teng", "ti", "tian",
    "tiao", "tie", "ting", "tong", "tou", "tu", "tuan", "tui", "tun", "tuo", "wa", "wai",
    "wan", "wang", "wei", "wen", "weng", "wo", "wu", "xi", "xia", "xian", "xiang", "xiao", "xie",
    "xin", "xing", "xiong", "xiu", "xu", "xuan", "xue", "xun", "ya", "yan", "yang", "yao", "ye",
    "yi", "yin", "ying", "yo", "yong", "you", "yu", "yuan", "yue", "yun", "za", "zai", "zan",
    "zang", "zao", "ze", "zei", "zen", "zeng", "zha", "zhai", "zhan", "zhang", "zhao", "zhe",
    "zhen", "zheng", "zhi", "zhong", "zhou", "zhu", "zhua", "zhuai", "zhuan", "zhuang", "zhui",
    "zhun", "zhuo", "zi", "zong", "zou", "zu", "zuan", "zui", "zun", "zuo",
];

fn rhotic_ending(syllable: &mut Syllable) {
    if let Some(expansion) = TIMING.expansions.get(&syllable.nucleus.ipa) {
        match expansion.parts.as_slice() {
            [held, _] if !expansion.rising => syllable.nucleus = segment(held),
            [medial, held, _] => {
                let together = format!("{medial}{held}");
                if TIMING
                    .expansions
                    .get(&together)
                    .is_some_and(|parts| parts.rising)
                {
                    syllable.nucleus = segment(&together);
                } else {
                    syllable.onset.push(segment(match medial.as_str() {
                        "i" => "j",
                        "y" => "ɥ",
                        _ => "w",
                    }));
                    syllable.nucleus = segment(held);
                }
            }
            _ => {}
        }
    }
    syllable.coda = vec![segment("ɻ")];
    syllable.nasal_lead = None;
}

pub fn pinyin_syllable(reading: &str, label: &str) -> Option<Syllable> {
    let number = tone(reading);
    let body = reading.trim_end_matches(|c: char| c.is_ascii_digit());
    if let Some(stem) = body
        .strip_suffix('r')
        .filter(|stem| !stem.is_empty() && body != "er")
    {
        let mut syllable = pinyin_syllable(&format!("{stem}{number}"), label)?;
        rhotic_ending(&mut syllable);
        return Some(syllable);
    }
    let first = body.chars().next()?;
    let single = &body[..first.len_utf8()];
    let prefix = ["zh", "ch", "sh"]
        .into_iter()
        .find(|p| body.starts_with(p))
        .or_else(|| (initial(single).is_some() || matches!(single, "y" | "w")).then_some(single));
    let (ini, rest) = prefix
        .filter(|p| p.len() < body.len())
        .map_or(("", body), |p| (p, &body[p.len()..]));
    let final_spelling = match (ini, rest) {
        ("y", "i" | "in" | "ing") | ("w", "u") => rest.to_owned(),
        ("y" | "j" | "q" | "x", rest) if rest.starts_with('u') => format!("v{}", &rest[1..]),
        ("y", rest) if !rest.starts_with('i') => format!("i{rest}"),
        ("w", "o") => "uo".to_owned(),
        ("w", rest) => format!("u{rest}"),
        _ => rest.to_owned(),
    };
    let final_text = final_spelling.as_str();
    let (mut glide, mut nucleus, coda) = match (ini, final_text) {
        ("z" | "c" | "s", "i") => (&[][..], "ɿ", &[][..]),
        ("zh" | "ch" | "sh" | "r", "i") => (&[][..], "ʅ", &[][..]),
        (_, f) => final_parts(f)?,
    };
    if final_text == "er" {
        nucleus = if number == 4 { "aɝ" } else { "əɝ" };
    } else if number == 5 && nucleus == "ɤ" {
        nucleus = "ə";
    }
    let rising = match (glide, nucleus) {
        (["j"], "a") => "ia",
        (["j"], "ɛ") => "iɛ",
        (["j"], "ɑ") => "iɑ",
        (["j"], "ʊ̠") => "iʊ̠",
        (["j"], "aʊ̠") => "iaʊ̠",
        (["j"], "əʊ̠") => "iəʊ̠",
        (["w"], "a") => "u̠a",
        (["w"], "ɔ") => "u̠ɔ",
        (["w"], "ɑ") => "u̠ɑ",
        (["w"], "ə") => "u̠ə",
        (["w"], "aɪ") => "u̠aɪ",
        (["w"], "eɪ") => "u̠eɪ",
        (["ɥ"], "ɛ") => "yɛ",
        _ => "",
    };
    if !rising.is_empty() {
        nucleus = rising;
        glide = &[];
    }
    let mut onset = Vec::new();
    if ini.is_empty() && !matches!(final_text, "n" | "ng" | "m" | "hm" | "hng") {
        onset.push(segment("ʔ"));
    }
    if let Some((ipa, aspirated)) = initial(ini) {
        let duration_seconds = match (ipa, aspirated) {
            ("tɕ" | "tʂ" | "ts", Some(false)) => Some(0.08),
            ("n" | "m", _) => Some(0.09),
            ("f", _) => Some(0.13),
            _ => None,
        };
        onset.push(Segment {
            aspirated,
            duration_seconds,
            vot_seconds: (aspirated == Some(true)).then_some(0.09),
            ..segment(ipa)
        });
    }
    onset.extend(glide.iter().map(|ipa| segment(ipa)));
    Some(Syllable {
        text: label.to_owned(),
        onset,
        nucleus: segment(nucleus),
        coda: coda
            .iter()
            .map(|ipa| Segment {
                duration_seconds: match *ipa {
                    "n" => Some(0.07),
                    "ŋ" => Some(0.08),
                    _ => None,
                },
                ..segment(ipa)
            })
            .collect(),
        nasal_lead: (!coda.is_empty()).then_some(0.6),
        closing: Some(0.2),
        ..Syllable::default()
    })
}

fn tone_mark(c: char) -> Option<(char, u8)> {
    [
        ('a', "āáǎà"),
        ('e', "ēéěè"),
        ('i', "īíǐì"),
        ('o', "ōóǒò"),
        ('u', "ūúǔù"),
        ('v', "ǖǘǚǜ"),
    ]
    .into_iter()
    .find_map(|(base, marks)| {
        marks
            .chars()
            .position(|mark| mark == c)
            .map(|i| (base, i as u8 + 1))
    })
}

pub(super) fn starts_pinyin(c: char) -> bool {
    c.is_ascii_alphabetic() || c.to_lowercase().any(|c| c == 'ü' || tone_mark(c).is_some())
}

pub(super) fn continues_pinyin(c: char) -> bool {
    starts_pinyin(c) || c.is_ascii_digit() || c == '\''
}

fn valid_syllable(candidate: &str) -> bool {
    let stem = candidate
        .strip_suffix('r')
        .filter(|s| !s.is_empty() && candidate != "er");
    let known = SYLLABLES.binary_search(&candidate).is_ok()
        || stem.is_some_and(|s| SYLLABLES.binary_search(&s).is_ok());
    known && pinyin_syllable(&format!("{candidate}1"), "").is_some()
}

/// 各位置から末尾まで届く最長の切れ目を後ろから求める。
fn split_piece(base: &str) -> Option<Vec<usize>> {
    let length = base.len();
    let mut next = vec![None; length + 1];
    next[length] = Some(length);
    for start in (0..length).rev() {
        if start > 0 && matches!(base.as_bytes()[start], b'a' | b'o' | b'e') {
            continue;
        }
        next[start] = (start + 1..=length.min(start + 6)).rev().find(|&end| {
            let part = &base[start..end];
            let nasal = matches!(part.trim_end_matches('r'), "n" | "ng" | "m" | "hm" | "hng");
            let rhotic = part.len() > 1 && part != "er" && part.ends_with('r');
            next[end].is_some()
                && (!nasal || (start == 0 && end == length))
                && (!rhotic || end == length)
                && valid_syllable(part)
        });
    }
    let mut ends = Vec::new();
    let mut start = 0;
    while start < length {
        start = next[start]?;
        ends.push(start);
    }
    Some(ends)
}

const INTERNAL_NEUTRALS: &[&str] = &[
    "ba", "bian", "bu", "de", "fu", "ge", "guo", "hou", "huan", "lai", "le", "li", "ma", "me",
    "men", "mian", "ne", "qu", "shang", "shi", "tou", "xi", "xia", "yi", "you", "zhe", "zi",
];

struct Letter {
    shown: char,
    base: char,
    mark: Option<u8>,
}

#[derive(Default)]
struct Piece {
    letters: Vec<Letter>,
    number: Option<u8>,
}

pub(super) fn typed_syllables(word: &str) -> Option<Vec<Syllable>> {
    if word.chars().filter(|c| c.is_alphabetic()).count() < 2 {
        return None;
    }
    let mut current = Piece::default();
    let mut pieces = Vec::new();
    for shown in word.chars() {
        let c = shown.to_lowercase().next()?;
        if let Some(value) = c.to_digit(10) {
            if value > 5 || current.letters.is_empty() {
                return None;
            }
            current.number = Some(if value == 0 { 5 } else { value as u8 });
            pieces.push(std::mem::take(&mut current));
        } else if c == '\'' {
            pieces.push(std::mem::take(&mut current));
        } else {
            let (base, mark) = if let Some((base, number)) = tone_mark(c) {
                (base, Some(number))
            } else if c == 'ü' || c.is_ascii_lowercase() {
                (if c == 'ü' { 'v' } else { c }, None)
            } else {
                return None;
            };
            current.letters.push(Letter { shown, base, mark });
        }
    }
    pieces.push(current);
    if !pieces.iter().any(|piece| {
        piece.number.is_some() || piece.letters.iter().any(|letter| letter.mark.is_some())
    }) {
        return None;
    }
    let mut labels = Vec::new();
    let mut readings = Vec::new();
    let mut written = Vec::new();
    for piece in pieces.into_iter().filter(|piece| !piece.letters.is_empty()) {
        let base: String = piece.letters.iter().map(|l| l.base).collect();
        let mut start = 0;
        for end in split_piece(&base)? {
            let letters = &piece.letters[start..end];
            let mut marks = letters.iter().filter_map(|l| l.mark);
            let mark = marks.next();
            if marks.next().is_some() {
                return None;
            }
            let number = piece.number.filter(|_| end == base.len());
            let explicit = mark.or(number);
            let stem = &base[start..end];
            let mut label: String = letters.iter().map(|l| l.shown).collect();
            let t = explicit.unwrap_or(5);
            if number.is_some() && mark.is_none() {
                label.push(char::from(b'0' + t));
            }
            labels.push(label);
            readings.push(format!("{stem}{t}"));
            written.push((explicit.is_some(), INTERNAL_NEUTRALS.contains(&stem)));
            start = end;
        }
    }
    if !written.first()?.0
        || written
            .iter()
            .enumerate()
            .any(|(i, &(marked, neutral))| i + 1 < written.len() && !marked && !neutral)
    {
        return None;
    }
    third_tones(&mut readings);
    labels
        .iter()
        .zip(&readings)
        .map(|(label, reading)| pinyin_syllable(reading, label))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fixed_dictionary_readings_all_split_into_syllables() {
        let mut text = String::new();
        GzDecoder::new(DICTIONARY)
            .read_to_string(&mut text)
            .unwrap();
        let mut count = 0;
        for line in text.lines() {
            let (word, readings) = line.split_once('\t').unwrap();
            for reading in readings.split(' ') {
                count += 1;
                assert!(pinyin_syllable(reading, word).is_some(), "{word} {reading}");
            }
        }
        assert!(count > 40_000);
    }

    #[test]
    fn long_invalid_pinyin_returns_without_recursive_search() {
        assert!(typed_syllables(&("xīnr".repeat(200) + "q")).is_none());
        assert!(typed_syllables("xīnr").is_some());
    }
}
