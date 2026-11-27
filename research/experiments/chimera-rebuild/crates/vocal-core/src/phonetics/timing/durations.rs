//! Klattの文脈規則で、展開前の各音素に秒単位の長さを与える。

use super::super::{
    Manner, Segment,
    catalog::{self, TIMING},
};

#[derive(Clone, Copy)]
struct Sound {
    manner: Option<Manner>,
    voiced: bool,
}

impl Sound {
    fn from_ipa(ipa: &str) -> Self {
        if catalog::is_calibrated_vowel(ipa) || TIMING.expansions.contains_key(ipa) {
            Self {
                manner: Some(Manner::Vowel),
                voiced: false,
            }
        } else {
            let entry = catalog::consonant(ipa);
            Self {
                manner: entry.map(|value| value.manner),
                voiced: entry.is_some_and(|value| value.voiced),
            }
        }
    }

    fn vowel(self) -> bool {
        self.manner == Some(Manner::Vowel)
    }

    fn preceding_vowel_factor(self) -> f64 {
        match self.manner {
            Some(Manner::Fricative) if self.voiced => 1.6,
            Some(Manner::Stop | Manner::Affricate) if self.voiced => 1.2,
            Some(Manner::Stop | Manner::Affricate) => 0.7,
            Some(Manner::Nasal) => 0.85,
            _ => 1.0,
        }
    }
}

struct Word {
    start: usize,
    vowel_count: usize,
    last_vowel: Option<usize>,
}

pub(super) fn estimate(input: &[Segment]) -> Vec<f64> {
    let sounds: Vec<_> = input
        .iter()
        .map(|segment| Sound::from_ipa(&segment.ipa))
        .collect();
    let mut words = Vec::<Word>::new();
    let mut word_ids = Vec::with_capacity(input.len());
    for (i, sound) in sounds.iter().enumerate() {
        if i == 0 || input[i - 1].word_end == Some(true) {
            words.push(Word {
                start: i,
                vowel_count: 0,
                last_vowel: None,
            });
        }
        let id = words.len() - 1;
        word_ids.push(id);
        if sound.vowel() {
            words[id].vowel_count += 1;
            words[id].last_vowel = Some(i);
        }
    }
    let phrase_last_vowel = sounds.iter().rposition(|sound| sound.vowel());
    let mut durations: Vec<_> = input
        .iter()
        .enumerate()
        .map(|(i, segment)| {
            if let Some(seconds) = segment.duration_seconds {
                return seconds;
            }
            let ipa = segment.ipa.as_str();
            let fallback = TIMING.fallback_seconds.get(ipa).copied().unwrap_or(0.08);
            let [inherent, mut minimum] = TIMING
                .klatt_milliseconds
                .get(ipa)
                .copied()
                .unwrap_or([1000.0 * fallback, 600.0 * fallback]);
            let word = &words[word_ids[i]];
            let previous = i.checked_sub(1).map(|j| sounds[j]);
            let next = sounds.get(i + 1).copied();
            let mut factor = 1.0;
            let mut onset_ms = 0.0;
            if sounds[i].vowel() {
                let phrase_final = phrase_last_vowel == Some(i);
                let stressed = segment.stress.unwrap_or(0) > 0;
                factor *= if phrase_final { 1.4 } else { 0.6 };
                if word.last_vowel != Some(i) {
                    factor *= 0.85;
                }
                if word.vowel_count > 1 {
                    factor *= 0.8;
                }
                if !stressed {
                    minimum *= 0.5;
                    factor *= 0.7;
                }
                if let Some(consonant) =
                    next.filter(|s| !s.vowel() && word_ids[i + 1] == word_ids[i])
                {
                    let f = consonant.preceding_vowel_factor();
                    factor *= if phrase_final { f } else { 0.7 + 0.3 * f };
                }
                if next.is_some_and(Sound::vowel) {
                    factor *= 1.2;
                }
                if previous.is_some_and(Sound::vowel) {
                    factor *= 0.7;
                }
                if stressed && previous.is_some_and(|s| s.manner == Some(Manner::Stop) && !s.voiced)
                {
                    onset_ms = 20.0;
                }
            } else {
                if phrase_last_vowel.is_none_or(|last| i > last)
                    && matches!(
                        sounds[i].manner,
                        Some(Manner::Nasal | Manner::Lateral | Manner::Approximant)
                    )
                {
                    factor *= 1.4;
                }
                if i != word.start {
                    factor *= 0.85;
                }
                let neighbors = [previous, next]
                    .into_iter()
                    .flatten()
                    .filter(|s| !s.vowel())
                    .count();
                factor *= [1.0, 0.7, 0.5][neighbors];
            }
            (minimum + (inherent - minimum) * factor + onset_ms) / 1000.0
        })
        .collect();

    for i in 0..input.len().saturating_sub(1) {
        let r = &input[i + 1];
        let in_coda = sounds
            .get(i + 2)
            .is_none_or(|next| word_ids[i + 1] != word_ids[i + 2] || !next.vowel());
        if sounds[i].vowel()
            && r.ipa == "ɹ"
            && word_ids[i] == word_ids[i + 1]
            && in_coda
            && input[i].duration_seconds.is_none()
            && r.duration_seconds.is_none()
        {
            durations[i] = (durations[i] - durations[i + 1]).max(0.04);
        }
    }

    durations
}
