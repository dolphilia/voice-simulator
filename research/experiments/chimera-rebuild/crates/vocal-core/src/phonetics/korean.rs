//! 韓国語歌詞の音節化。発音規則とIPA対応は固定版CHIMERA由来（MIT）。

use super::{Segment, syllables::Syllable};

const BLOCK_BASE: u32 = 0xac00;
const INITIAL_BASE: u32 = 0x1100;
const MEDIAL_BASE: u32 = 0x1161;
const FINAL_BASE: u32 = 0x11a7;
const INITIALS: [char; 19] = [
    'ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ',
    'ㅌ', 'ㅍ', 'ㅎ',
];
const MEDIALS: [(&str, &str); 21] = [
    ("", "a"),
    ("", "ɛ"),
    ("j", "a"),
    ("j", "ɛ"),
    ("", "ʌ"),
    ("", "e"),
    ("j", "ʌ"),
    ("j", "e"),
    ("", "o"),
    ("w", "a"),
    ("w", "ɛ"),
    ("w", "e"),
    ("j", "o"),
    ("", "u"),
    ("w", "ʌ"),
    ("w", "e"),
    ("w", "i"),
    ("j", "u"),
    ("", "ɯ"),
    ("ɰ", "i"),
    ("", "i"),
];
const FINALS: [&str; 28] = [
    "", "ㄱ", "ㄲ", "ㄱㅅ", "ㄴ", "ㄴㅈ", "ㄴㅎ", "ㄷ", "ㄹ", "ㄹㄱ", "ㄹㅁ", "ㄹㅂ", "ㄹㅅ",
    "ㄹㅌ", "ㄹㅍ", "ㄹㅎ", "ㅁ", "ㅂ", "ㅂㅅ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ",
    "ㅎ",
];
const MEDIAL_COUNT: u32 = MEDIALS.len() as u32;
const FINAL_COUNT: u32 = FINALS.len() as u32;
const LAX_VOT_SECONDS: f64 = 0.045;
const ASPIRATED_VOT_SECONDS: f64 = 0.09;

fn block_index(code: u32) -> Option<u32> {
    code.checked_sub(BLOCK_BASE)
        .filter(|&i| i < INITIALS.len() as u32 * MEDIAL_COUNT * FINAL_COUNT)
}

fn initial_code(code: u32) -> bool {
    (INITIAL_BASE..INITIAL_BASE + INITIALS.len() as u32).contains(&code)
}

pub(super) fn starts_word(c: char) -> bool {
    block_index(c as u32).is_some() || initial_code(c as u32)
}

pub(super) fn continues_word(c: char) -> bool {
    let code = c as u32;
    starts_word(c)
        || (MEDIAL_BASE..MEDIAL_BASE + MEDIAL_COUNT).contains(&code)
        || (FINAL_BASE + 1..FINAL_BASE + FINAL_COUNT).contains(&code)
}

fn combine(left: char, right: char) -> Option<char> {
    let (left, right) = (left as u32, right as u32);
    let code = if initial_code(left) && (MEDIAL_BASE..MEDIAL_BASE + MEDIAL_COUNT).contains(&right) {
        BLOCK_BASE + ((left - INITIAL_BASE) * MEDIAL_COUNT + right - MEDIAL_BASE) * FINAL_COUNT
    } else if block_index(left).is_some_and(|i| i % FINAL_COUNT == 0)
        && (FINAL_BASE + 1..FINAL_BASE + FINAL_COUNT).contains(&right)
    {
        left + right - FINAL_BASE
    } else {
        return None;
    };
    char::from_u32(code)
}

struct Block {
    spelling: char,
    onset: Option<char>,
    glide: &'static str,
    vowel: &'static str,
    coda: Vec<char>,
}

impl Block {
    fn parse(spelling: char) -> Option<Self> {
        let i = block_index(spelling as u32)?;
        let initial = INITIALS[(i / (MEDIAL_COUNT * FINAL_COUNT)) as usize];
        let (glide, vowel) = MEDIALS[(i / FINAL_COUNT % MEDIAL_COUNT) as usize];
        let coda = FINALS[(i % FINAL_COUNT) as usize].chars().collect();
        Some(Self {
            spelling,
            onset: (initial != 'ㅇ').then_some(initial),
            glide,
            vowel,
            coda,
        })
    }

    fn set_final(&mut self, value: char) {
        self.coda.clear();
        self.coda.push(value);
    }

    fn reduce_final(&mut self) -> Option<char> {
        let chosen = match self.coda.as_slice() {
            [] => return None,
            ['ㄹ', tail @ ('ㄱ' | 'ㅁ' | 'ㅍ')] => *tail,
            [first, ..] => *first,
        };
        let neutral = match chosen {
            'ㄲ' | 'ㅋ' => 'ㄱ',
            'ㅅ' | 'ㅆ' | 'ㅈ' | 'ㅊ' | 'ㅌ' | 'ㅎ' => 'ㄷ',
            'ㅍ' => 'ㅂ',
            other => other,
        };
        self.set_final(neutral);
        Some(neutral)
    }
}

fn aspirated(letter: char) -> Option<char> {
    match letter {
        'ㄱ' => Some('ㅋ'),
        'ㄷ' => Some('ㅌ'),
        'ㅂ' => Some('ㅍ'),
        'ㅈ' => Some('ㅊ'),
        _ => None,
    }
}

fn tense(letter: char) -> char {
    match letter {
        'ㄱ' => 'ㄲ',
        'ㄷ' => 'ㄸ',
        'ㅂ' => 'ㅃ',
        'ㅅ' => 'ㅆ',
        'ㅈ' => 'ㅉ',
        _ => letter,
    }
}

fn link(left: &mut Block, right: &mut Block) {
    let Some(mut onset) = right.onset else {
        if left.coda.last() == Some(&'ㅎ') {
            left.coda.pop();
        }
        if left.coda.last().is_some_and(|&letter| letter != 'ㅇ') {
            let plain_i = right.vowel == "i" && right.glide.is_empty();
            right.onset = left.coda.pop().map(|letter| match (letter, plain_i) {
                ('ㄷ', true) => 'ㅈ',
                ('ㅌ', true) => 'ㅊ',
                _ => letter,
            });
        }
        return;
    };

    if left.coda.last() == Some(&'ㅎ') {
        left.coda.pop();
        onset = match onset {
            'ㅅ' => 'ㅆ',
            'ㄴ' if left.coda == ['ㄹ'] => 'ㄹ',
            'ㄴ' => {
                left.set_final('ㄴ');
                'ㄴ'
            }
            _ => aspirated(onset).unwrap_or(onset),
        };
        right.onset = Some(onset);
    }
    // 固定上流が扱う「踏む」の語幹。後続のㅎではㄹを残してㅂを帯気化する。
    if left.spelling == '밟' && left.coda == ['ㄹ', 'ㅂ'] {
        if onset == 'ㅎ' {
            left.set_final('ㄹ');
            right.onset = Some('ㅍ');
            return;
        }
        left.set_final('ㅂ');
    }
    let Some(final_letter) = left.reduce_final() else {
        return;
    };
    let nasal = match final_letter {
        'ㄱ' => Some('ㅇ'),
        'ㄷ' => Some('ㄴ'),
        'ㅂ' => Some('ㅁ'),
        _ => None,
    };
    if onset == 'ㅎ' && nasal.is_some() {
        left.coda.clear();
        right.onset = aspirated(final_letter);
        return;
    }
    onset = match (final_letter, onset) {
        ('ㄹ', 'ㄴ') | ('ㄴ', 'ㄹ') => {
            left.set_final('ㄹ');
            'ㄹ'
        }
        (letter, 'ㄹ') if letter != 'ㄹ' => 'ㄴ',
        (_, letter) => letter,
    };
    if let Some(nasal) = nasal {
        if matches!(onset, 'ㄴ' | 'ㅁ') {
            left.set_final(nasal);
        } else {
            onset = tense(onset);
        }
    }
    right.onset = Some(onset);
}

fn segment(ipa: &str) -> Segment {
    Segment {
        ipa: ipa.to_owned(),
        ..Segment::default()
    }
}

fn initial_segment(letter: char, block: &Block, previous: Option<&Block>) -> Segment {
    let prev_final = previous.and_then(|prev| prev.coda.last().copied());
    let voicing =
        previous.is_some() && prev_final.is_none_or(|c| matches!(c, 'ㄴ' | 'ㄹ' | 'ㅁ' | 'ㅇ'));
    let front = (block.vowel == "i" && block.glide != "w") || block.glide == "j";
    let (ipa, aspirated, vot_seconds) = match letter {
        'ㄱ' if voicing => ("g", None, None),
        'ㄷ' if voicing => ("d", None, None),
        'ㅂ' if voicing => ("b", None, None),
        'ㅈ' if voicing => ("dʑ", None, None),
        'ㄱ' => ("k", Some(true), Some(LAX_VOT_SECONDS)),
        'ㄷ' => ("t", Some(true), Some(LAX_VOT_SECONDS)),
        'ㅂ' => ("p", Some(true), Some(LAX_VOT_SECONDS)),
        'ㅈ' => ("tɕ", Some(true), Some(LAX_VOT_SECONDS)),
        'ㅋ' => ("k", Some(true), Some(ASPIRATED_VOT_SECONDS)),
        'ㅌ' => ("t", Some(true), Some(ASPIRATED_VOT_SECONDS)),
        'ㅍ' => ("p", Some(true), Some(ASPIRATED_VOT_SECONDS)),
        'ㅊ' => ("tɕ", Some(true), Some(ASPIRATED_VOT_SECONDS)),
        'ㄲ' => ("k", Some(false), None),
        'ㄸ' => ("t", Some(false), None),
        'ㅃ' => ("p", Some(false), None),
        'ㅉ' => ("tɕ", Some(false), None),
        'ㅅ' | 'ㅆ' => (if front { "ɕ" } else { "s" }, None, None),
        'ㅎ' => (if voicing { "ɦ" } else { "h" }, None, None),
        'ㄴ' => ("n", None, None),
        'ㅁ' => ("m", None, None),
        'ㄹ' => (if prev_final == Some('ㄹ') { "l" } else { "ɾ" }, None, None),
        _ => unreachable!("未定義の初声 {letter}"),
    };
    Segment {
        aspirated,
        vot_seconds,
        ..segment(ipa)
    }
}

fn final_segment(letter: char) -> Segment {
    segment(match letter {
        'ㄱ' => "k",
        'ㄴ' => "n",
        'ㄷ' => "t",
        'ㄹ' => "l",
        'ㅁ' => "m",
        'ㅂ' => "p",
        'ㅇ' => "ŋ",
        _ => unreachable!("中和されていない終声 {letter}"),
    })
}

pub(super) fn word_syllables(word: &str) -> Vec<Syllable> {
    let mut blocks = Vec::new();
    let mut pending = None;
    for letter in word.chars() {
        if let Some(block) = pending.and_then(|left| combine(left, letter)) {
            pending = Some(block);
        } else {
            blocks.extend(pending.replace(letter).and_then(Block::parse));
        }
    }
    blocks.extend(pending.and_then(Block::parse));
    for right in 1..blocks.len() {
        let (left, right) = blocks.split_at_mut(right);
        link(left.last_mut().expect("左の音節"), &mut right[0]);
    }
    if let Some(last) = blocks.last_mut() {
        last.reduce_final();
    }
    blocks
        .iter()
        .enumerate()
        .map(|(i, block)| {
            let previous = i.checked_sub(1).map(|previous| &blocks[previous]);
            let mut onset: Vec<_> = block
                .onset
                .map(|c| initial_segment(c, block, previous))
                .into_iter()
                .collect();
            if !block.glide.is_empty() && (block.glide != "ɰ" || block.onset.is_none()) {
                onset.push(segment(block.glide));
            }
            Syllable {
                text: block.spelling.to_string(),
                onset,
                nucleus: segment(block.vowel),
                coda: block.coda.iter().copied().map(final_segment).collect(),
                ..Syllable::default()
            }
        })
        .collect()
}
