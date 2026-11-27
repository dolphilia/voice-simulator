//! ロシア語の歌詞を音素と歌唱用の音節に変換する。
//! 発音規則と強勢表は固定版 CHIMERA（Jameson Hodge、MIT。LICENSE-CHIMERA）に準拠する。

use super::{
    Segment,
    catalog::TIMING,
    syllables::{Syllable, is_english_onset, syllabify_with},
};

#[rustfmt::skip]
const UNSTRESSED_WORDS: &[&str] = &[
    "в", "во", "к", "ко", "с", "со", "из", "от", "до", "по", "за", "на", "над", "под", "об", "о", "у",
    "при", "про", "для", "без", "через", "перед", "не", "ни",
];
#[rustfmt::skip]
const STRESS: &[(&str, usize)] = &[
    ("меня", 1), ("тебя", 1), ("себя", 1), ("тебе", 1), ("себе", 1), ("его", 1), ("ему", 1), ("она", 1), ("оно", 1), ("они", 1),
    ("моя", 1), ("твоя", 1), ("своя", 1), ("мои", 1), ("твои", 1), ("свои", 1), ("один", 1), ("одна", 1), ("одни", 1),
    ("когда", 1), ("тогда", 1), ("всегда", 1), ("куда", 1), ("туда", 1), ("сюда", 1), ("сейчас", 1), ("теперь", 1),
    ("зачем", 1), ("потом", 1), ("опять", 1), ("уже", 1), ("пока", 1), ("привет", 1), ("давай", 1), ("прости", 1),
    ("большой", 1), ("какой", 1), ("такой", 1), ("другой", 1), ("домой", 1), ("назад", 1), ("вокруг", 1),
    ("вода", 1), ("зима", 1), ("весна", 1), ("луна", 1), ("рука", 1), ("нога", 1), ("земля", 1), ("любовь", 1),
    ("хочу", 1), ("могу", 1), ("люблю", 1), ("пою", 1), ("иду", 1), ("сегодня", 1), ("спасибо", 1), ("пожалуйста", 1),
    ("хорошо", 2), ("почему", 2), ("потому", 2), ("никогда", 2), ("человек", 2), ("говорит", 2), ("говорю", 2),
    ("молоко", 2), ("голова", 2), ("далеко", 2), ("высоко", 2),
];
const G_EXCEPTIONS: &[&str] = &[
    "много",
    "немного",
    "намного",
    "строго",
    "дорого",
    "недорого",
    "убого",
    "ого",
];
const OBSTRUENT_PAIRS: [(&str, &str); 6] = [
    ("p", "b"),
    ("t", "d"),
    ("k", "g"),
    ("f", "v"),
    ("s", "z"),
    ("ʂ", "ʐ"),
];
const ACUTE: char = '\u{0301}';

pub(super) fn starts_word(c: char) -> bool {
    matches!(c, 'а'..='я' | 'А'..='Я' | 'ё' | 'Ё')
}

pub(super) fn continues_word(c: char) -> bool {
    starts_word(c) || matches!(c, ACUTE | '-')
}

fn is_vowel(c: char) -> bool {
    "аэыоуяеёию".contains(c)
}

fn sound(ipa: &str) -> Segment {
    Segment {
        ipa: ipa.to_owned(),
        ..Segment::default()
    }
}

fn lengthened(ipa: &str) -> Segment {
    Segment {
        duration_seconds: TIMING
            .fallback_seconds
            .get(ipa)
            .map(|duration| duration * 1.5),
        ..sound(ipa)
    }
}

#[derive(Clone, Copy)]
enum Voicing {
    Devoice,
    Voice,
    Keep,
}

fn final_voicing(proclitic: bool, next_word: Option<&str>) -> Voicing {
    if !proclitic {
        return Voicing::Devoice;
    }
    let following = next_word
        .and_then(|word| word.chars().find(|&c| starts_word(c)))
        .and_then(|c| c.to_lowercase().next());
    match following {
        Some(c) if "пткфсшхцчщ".contains(c) => Voicing::Devoice,
        Some(c) if "бдгзж".contains(c) => Voicing::Voice,
        _ => Voicing::Keep,
    }
}

fn assimilate(segments: &mut [Segment], final_state: Voicing) {
    let mut next_state = final_state;
    for segment in segments.iter_mut().rev() {
        let pair = OBSTRUENT_PAIRS
            .iter()
            .find(|(unvoiced, voiced)| segment.ipa == *unvoiced || segment.ipa == *voiced);
        if let Some(&(unvoiced, voiced)) = pair {
            match next_state {
                Voicing::Devoice => unvoiced.clone_into(&mut segment.ipa),
                Voicing::Voice => voiced.clone_into(&mut segment.ipa),
                Voicing::Keep => {}
            }
        }
        next_state = match segment.ipa.as_str() {
            "j" => next_state,
            "p" | "t" | "k" | "f" | "s" | "ʂ" | "ʃ" | "x" | "ts" | "tʃ" => Voicing::Devoice,
            "b" | "d" | "g" | "z" | "ʐ" => Voicing::Voice,
            _ => Voicing::Keep,
        };
    }
}

fn pronounce(input: &str, next_word: Option<&str>) -> Vec<Segment> {
    let lowered = input
        .to_lowercase()
        .replace("е\u{0308}", "ё")
        .replace("и\u{0306}", "й");
    let mut letters = Vec::new();
    let mut explicit_stress = None;
    for letter in lowered.chars() {
        if letter == ACUTE && letters.last().copied().is_some_and(is_vowel) {
            explicit_stress = Some(letters.len() - 1);
        } else if starts_word(letter) {
            letters.push(letter);
        }
    }
    let spelling: String = letters.iter().collect();
    let proclitic = UNSTRESSED_WORDS.contains(&spelling.as_str());
    let stress = explicit_stress
        .or_else(|| letters.iter().position(|&letter| letter == 'ё'))
        .or_else(|| {
            if proclitic {
                return None;
            }
            let vowel_number = STRESS
                .iter()
                .find(|(word, _)| *word == spelling)
                .map_or(0, |(_, index)| *index);
            let mut vowels = letters
                .iter()
                .enumerate()
                .filter(|&(_, &letter)| is_vowel(letter));
            // 登録語の音節数から外れた場合は、同じ語の先頭母音を使う。
            let first = vowels.next();
            (if vowel_number == 0 {
                first
            } else {
                vowels.nth(vowel_number - 1).or(first)
            })
            .map(|(index, _)| index)
        });

    let mut output = Vec::new();
    let mut cursor = 0;
    let mut doubled = false;
    while let Some(&letter) = letters.get(cursor) {
        let index = cursor;
        let previous = index.checked_sub(1).map(|i| letters[i]);
        let remaining = &letters[index..];
        cursor += 1;
        if is_vowel(letter) {
            let iotated = ("яеёю".contains(letter)
                && previous.is_none_or(|p| is_vowel(p) || "ьъ".contains(p)))
                || ("ио".contains(letter) && previous == Some('ь'));
            if iotated {
                output.push(sound("j"));
            }
            let vowel = match letter {
                'а' | 'я' => "a",
                'о' | 'ё' => "o",
                'у' | 'ю' => "u",
                'и' if previous.is_some_and(|p| "жшц".contains(p)) => "ɨ",
                'и' => "i",
                'ы' => "ɨ",
                _ => "e",
            };
            output.push(Segment {
                stress: Some(u8::from(stress == Some(index))),
                ..sound(vowel)
            });
            continue;
        }

        if matches!(remaining, ['т', 'с', 'я'] | ['т', 'ь', 'с', 'я']) {
            output.push(lengthened("ts"));
            output.push(Segment {
                stress: Some(0),
                ..sound("a")
            });
            break;
        }
        if remaining.get(1) == Some(&letter) && !"ьъй".contains(letter) {
            doubled = true;
            continue;
        }
        if matches!(
            (letter, previous, remaining.get(1)),
            ('т', Some('с'), Some('н' | 'л'))
                | ('д', Some('з'), Some('н'))
                | ('д', Some('р'), Some('ц'))
        ) || remaining.starts_with(&['л', 'н', 'ц'])
            || remaining.starts_with(&['в', 'с', 'т', 'в'])
        {
            continue;
        }
        let consonant = if "сзж".contains(letter) && remaining.get(1) == Some(&'ч') {
            cursor += 1;
            'щ'
        } else {
            letter
        };
        let following = letters.get(cursor).copied();
        let hard_ch = consonant == 'ч'
            && match following {
                Some('т') => matches!(spelling.as_str(), "что" | "чтобы" | "чтоб" | "ничто"),
                Some('н') => matches!(spelling.as_str(), "конечно" | "скучно" | "нарочно"),
                _ => false,
            };
        let soft = !hard_ch
            && ("чщ".contains(consonant)
                || (!"жшцй".contains(consonant)
                    && following.is_some_and(|c| "яеёиюь".contains(c))));
        let ipa = match consonant {
            'б' => "b",
            'п' => "p",
            'в' => "v",
            'ф' => "f",
            'г' if g_becomes_v(&spelling, index, letters.len()) => "v",
            'г' => "g",
            'к' => "k",
            'д' => "d",
            'т' => "t",
            'з' => "z",
            'с' => "s",
            'ж' => "ʐ",
            'ш' => "ʂ",
            'х' => "x",
            'ц' => "ts",
            'ч' if hard_ch => "ʂ",
            'ч' => "tʃ",
            'щ' => "ʃ",
            'м' => "m",
            'н' => "n",
            'л' if soft => "l",
            'л' => "ɫ",
            'р' => "ɾ",
            'й' => "j",
            _ => continue,
        };
        let mut segment = if doubled && following.is_some_and(is_vowel) {
            lengthened(ipa)
        } else {
            sound(ipa)
        };
        doubled = false;
        if consonant == 'щ' {
            segment.duration_seconds = Some(0.18);
        }
        output.push(segment);
        if soft {
            output.push(Segment {
                duration_seconds: Some(0.025),
                ..sound("j")
            });
        }
    }
    assimilate(&mut output, final_voicing(proclitic, next_word));
    output
}

fn g_becomes_v(word: &str, index: usize, letter_count: usize) -> bool {
    if word == "сегодня" || word.starts_with("сегодняшн") {
        return index == 2;
    }
    index + 2 == letter_count
        && (word.ends_with("ого") || word.ends_with("его"))
        && !G_EXCEPTIONS.contains(&word)
}

fn onset_allowed(cluster: &[Segment]) -> bool {
    is_english_onset(cluster)
        || cluster.first().is_some_and(|first| {
            cluster[1..].iter().all(|s| s.ipa == "j")
                || !matches!(first.ipa.as_str(), "ɾ" | "ɫ" | "l" | "n" | "m" | "j")
        })
}

fn display_parts(word: &str, count: usize, manual_split: bool) -> Vec<String> {
    if count <= 1 || manual_split {
        let mut parts = vec![word.to_owned()];
        parts.resize(count.max(1), "~".to_owned());
        return parts;
    }
    let letters: Vec<_> = word.chars().collect();
    let vowels: Vec<_> = letters
        .iter()
        .enumerate()
        .filter_map(|(i, c)| c.to_lowercase().any(is_vowel).then_some(i))
        .collect();
    if vowels.len() != count {
        let mut parts = vec![word.to_owned()];
        parts.resize(count, "~".to_owned());
        return parts;
    }
    let lower_at = |i: usize| letters.get(i).and_then(|c| c.to_lowercase().next());
    let mut boundaries = vec![0];
    for &vowel in vowels.iter().take(count - 1) {
        let mut cut = vowel + 1;
        while letters.get(cut) == Some(&ACUTE) {
            cut += 1;
        }
        if lower_at(cut).is_some_and(|c| "рлнмй".contains(c)) {
            let soft = usize::from(lower_at(cut + 1) == Some('ь'));
            if lower_at(cut + 1 + soft)
                .is_some_and(|c| starts_word(c) && !is_vowel(c) && !"ьъ".contains(c))
            {
                cut += 1 + soft;
            }
        }
        boundaries.push(cut);
    }
    boundaries.push(letters.len());
    boundaries
        .windows(2)
        .map(|pair| letters[pair[0]..pair[1]].iter().collect())
        .collect()
}

pub(super) fn word_syllables(word: &str, previous: Option<&str>) -> Vec<Syllable> {
    let parts: Vec<_> = word.split('-').filter(|part| !part.is_empty()).collect();
    let mut syllables = Vec::new();
    for part in &parts {
        let segments = pronounce(part, None);
        let sounds = syllabify_with(&segments, onset_allowed);
        let labels = display_parts(part, sounds.len(), parts.len() > 1);
        syllables.extend(
            sounds
                .into_iter()
                .zip(labels)
                .map(|(sound, text)| Syllable {
                    text,
                    onset: sound.onset,
                    nucleus: sound.nucleus,
                    coda: sound.coda,
                    ..Syllable::default()
                }),
        );
    }
    if let (Some(previous), Some(first)) = (
        previous.filter(|word| !word.chars().any(|c| c.to_lowercase().any(is_vowel))),
        syllables.first_mut(),
    ) {
        let previous_parts: Vec<_> = previous
            .split('-')
            .filter(|part| !part.is_empty())
            .collect();
        let mut onset: Vec<_> = previous_parts
            .iter()
            .enumerate()
            .flat_map(|(i, part)| {
                pronounce(
                    part,
                    previous_parts
                        .get(i + 1)
                        .copied()
                        .or(parts.first().copied()),
                )
            })
            .collect();
        onset.append(&mut first.onset);
        first.onset = onset;
        first.text = format!("{previous} {}", first.text);
    }
    syllables
}
