//! 歌詞の音節と音符を、調音に渡す秒単位の区間とF0目標へ変換する。
//! 発音時間の配分は固定版CHIMERAの歌唱計画（MIT）に準拠する。

use super::{
    Manner, Segment,
    catalog::TIMING,
    english::English,
    speech::{
        ALVEOLAR_TIP_X_CM, ALVEOLAR_TIP_Y_CM, BILABIAL_CLOSURE_CM, VELAR_CLOSURE_Y_CM, single,
        sung_phrase_gestures, supported_speech_symbol,
    },
    syllables::{Syllable, is_nucleus, read_lyrics},
    timing::{self, Timing},
    vowels::vowel_targets,
};
use crate::anatomy::{BodyMix, BodyName};
use crate::articulators::Articulator;
use crate::score::{ControlKey, Gesture, Targets};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

const MIN_VOWEL_SECONDS: f64 = 0.050;
const MIN_CONSONANT_SECONDS: f64 = 0.012;
const VOWEL_FLOOR_SECONDS: f64 = 0.020;
const MEDIAL_SECONDS: f64 = 0.050;
const CLOSING_SHARE: f64 = 0.6;

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Note {
    pub midi: f64,
    pub beats: f64,
}

#[derive(Debug, Serialize)]
pub struct NoteTiming {
    pub note: Note,
    pub lyric_index: usize,
    pub beat_seconds: f64,
    pub beat_end_seconds: f64,
    pub f0_hz: f64,
    pub nucleus_start_seconds: f64,
    pub nucleus_end_seconds: f64,
    #[serde(skip)]
    nominal_vowel_seconds: f64,
}

#[derive(Debug, Serialize)]
pub struct SungPhrase {
    pub first_note_index: usize,
    pub last_note_index: usize,
    pub planning_start_seconds: f64,
    pub timing: Timing,
    pub pitch: Vec<Gesture>,
    #[serde(skip)]
    nasal_rhymes: Vec<NasalRhyme>,
    #[serde(skip)]
    final_nasal: Option<FinalNasal>,
}

#[derive(Debug, Serialize)]
pub struct SongPlan {
    pub notes: Vec<NoteTiming>,
    pub phrases: Vec<SungPhrase>,
    pub nominal_end_seconds: f64,
    pub end_seconds: f64,
    pub render_end_seconds: f64,
    pub unavailable_speech_symbols: Vec<String>,
}

/// 歌詞を文字種ごとに読み、音符へ割り当てられる音節にする。
pub fn lyric_syllables(text: &str, lexicon: &English<'_>) -> Vec<Syllable> {
    read_lyrics(text, |word| lexicon.pronounce(word, false).segments)
}

pub fn midi_to_hz(midi: f64) -> f64 {
    440.0 * libm::pow(2.0, (midi - 69.0) / 12.0)
}

struct PlacedNote<'a> {
    note: Note,
    lyric_index: usize,
    syllable: &'a Syllable,
    parent: &'a Syllable,
    beat: f64,
    end: f64,
    hz: f64,
}

struct NoteSegments {
    onset: Vec<Segment>,
    coda: Vec<Segment>,
}

#[derive(Clone, Copy, Debug)]
enum NasalCoda {
    Labial,
    Alveolar,
    Velar,
}

impl NasalCoda {
    fn from_ipa(ipa: &str) -> Option<Self> {
        match ipa {
            "m" => Some(Self::Labial),
            "n" => Some(Self::Alveolar),
            "ŋ" => Some(Self::Velar),
            _ => None,
        }
    }

    fn closure(self) -> (Articulator, f64, Option<(Articulator, f64)>) {
        match self {
            Self::Labial => (Articulator::LipAperture, BILABIAL_CLOSURE_CM, None),
            Self::Alveolar => (
                Articulator::TongueTipX,
                ALVEOLAR_TIP_X_CM,
                Some((Articulator::TongueTipY, ALVEOLAR_TIP_Y_CM)),
            ),
            Self::Velar => (Articulator::TongueBodyY, VELAR_CLOSURE_Y_CM, None),
        }
    }
}

#[derive(Debug)]
struct NasalRhyme {
    coda: NasalCoda,
    nucleus: String,
    end: f64,
    vowel_seconds: f64,
    nasal_lead: f64,
}

#[derive(Debug)]
struct FinalNasal {
    coda: NasalCoda,
    end: f64,
    fade_before_next_phrase: Option<f64>,
}

fn consonants(input: &[Segment], hz: f64) -> Vec<Segment> {
    consonants_with_scale(input, hz, 0.8)
}

pub(super) fn consonants_with_scale(input: &[Segment], hz: f64, scale: f64) -> Vec<Segment> {
    input
        .iter()
        .map(|s| Segment {
            ipa: s.ipa.clone(),
            duration_seconds: Some(s.duration_seconds.unwrap_or_else(|| {
                scale * TIMING.fallback_seconds.get(&s.ipa).copied().unwrap_or(0.07)
            })),
            f0_hz: Some(hz),
            aspirated: s.aspirated,
            vot_seconds: s.vot_seconds,
            palatalized: s.palatalized,
            breathy: s.breathy,
            ..Segment::default()
        })
        .collect()
}

pub(super) fn vowel(ipa: &str, duration: f64, hz: f64, mark: &Segment) -> Segment {
    Segment {
        ipa: ipa.to_owned(),
        duration_seconds: Some(duration),
        f0_hz: Some(hz),
        stress: Some(1),
        nasalized: mark.nasalized,
        breathy: mark.breathy,
        ..Segment::default()
    }
}

pub(super) fn nucleus_parts(ipa: &str) -> (Option<&str>, &str, Option<&str>) {
    let Some(expanded) = TIMING.expansions.get(ipa) else {
        return (None, ipa, None);
    };
    match expanded.parts.as_slice() {
        [a, b] if expanded.rising => (Some(a), b, None),
        [a, b] => (None, a, Some(b)),
        [a, b, c] => (Some(a), b, Some(c)),
        _ => (None, ipa, None),
    }
}

fn total(segments: &[Segment]) -> f64 {
    segments.iter().map(|s| s.duration_seconds.unwrap()).sum()
}

fn squeeze(coda: &mut [Segment], next_onset: &mut [Segment], span: f64) {
    let sum = total(coda) + total(next_onset);
    let allowance = span - MIN_VOWEL_SECONDS;
    if sum > allowance && sum > 0.0 {
        let factor = allowance.max(0.0) / sum;
        for s in coda.iter_mut().chain(next_onset) {
            s.duration_seconds =
                Some((s.duration_seconds.unwrap() * factor).max(MIN_CONSONANT_SECONDS));
        }
    }
}

pub(super) fn pitch(timing: &Timing) -> Vec<Gesture> {
    let order = [true, false].into_iter().flat_map(|vowel| {
        timing
            .segments
            .iter()
            .filter(move |s| (s.manner == Some(Manner::Vowel)) == vowel)
    });
    order
        .filter_map(|s| {
            s.segment.f0_hz.map(|hz| {
                let ramp = (0.5 * (s.end_seconds - s.start_seconds)).clamp(0.008, 0.060);
                let mut targets = Targets::default();
                targets.set(ControlKey::F0, hz);
                Gesture {
                    t0: s.start_seconds,
                    t1: s.end_seconds,
                    ramp_in: ramp,
                    ramp_out: ramp,
                    strength: 6.0,
                    targets,
                    speed: None,
                    release_hold: None,
                    label: Some("pitch".to_owned()),
                }
            })
        })
        .collect()
}

/// 音符への音節の割り当ては歌詞を繰り返す上流のCLIに合わせる。
pub fn plan(
    syllables: &[Syllable],
    notes: &[Note],
    bpm: f64,
    start_seconds: f64,
) -> Result<SongPlan, &'static str> {
    if !bpm.is_finite() || bpm <= 0.0 || !start_seconds.is_finite() {
        return Err("テンポは有限の正の値、最初の拍は有限の秒数で指定してください");
    }
    if !notes.is_empty() && syllables.is_empty() {
        return Err("音符に割り当てる歌詞の音節がありません");
    }
    if syllables.iter().any(|s| {
        !is_nucleus(&s.nucleus.ipa)
            || s.onset.iter().chain(&s.coda).any(|c| {
                c.duration_seconds
                    .is_some_and(|t| !t.is_finite() || t < 0.0)
            })
    }) {
        return Err("音節の核は母音、子音の長さは有限の非負値を指定してください");
    }
    let beat_seconds = 60.0 / bpm;
    let mut nominal_end = start_seconds;
    let mut placed = Vec::with_capacity(notes.len());
    let mut parent = syllables.first();
    for (i, &note) in notes.iter().enumerate() {
        let span = note.beats * beat_seconds;
        let end = nominal_end + span;
        let hz = midi_to_hz(note.midi);
        if !hz.is_finite() || hz <= 0.0 || !end.is_finite() || end <= nominal_end {
            return Err("音符は有限の音高と時刻を進める正の拍長を指定してください");
        }
        let lyric_index = i % syllables.len();
        let syllable = &syllables[lyric_index];
        if syllable.melisma != Some(true) {
            parent = Some(syllable);
        }
        placed.push(PlacedNote {
            note,
            lyric_index,
            syllable,
            parent: parent.unwrap(),
            beat: nominal_end,
            end,
            hz,
        });
        nominal_end = end;
    }

    let mut end_seconds = nominal_end;
    let mut output_notes = Vec::with_capacity(notes.len());
    let mut phrases = Vec::new();
    let mut unavailable = BTreeSet::new();
    let mut first = 0;
    for last in 0..placed.len() {
        if last + 1 < placed.len() && !placed[last].syllable.phrase_end {
            continue;
        }
        let is_last = last + 1 == placed.len();
        let phrase = &placed[first..=last];
        let last_note = &placed[last];
        let reserve: f64 = if is_last { 0.05 } else { 0.12 };
        let last_end = last_note.end - reserve.min(0.3 * last_note.note.beats * beat_seconds);
        let next_continues = |i: usize| {
            phrase
                .get(i + 1)
                .is_some_and(|n| n.syllable.melisma == Some(true))
        };
        let mut parts: Vec<_> = phrase
            .iter()
            .enumerate()
            .map(|(i, n)| {
                let mut onset = Vec::new();
                if n.syllable.melisma != Some(true) {
                    onset = consonants(&n.syllable.onset, n.hz);
                    if let (Some(medial), _, _) = nucleus_parts(&n.syllable.nucleus.ipa) {
                        onset.push(vowel(medial, MEDIAL_SECONDS, n.hz, &n.syllable.nucleus));
                    }
                }
                let coda = if next_continues(i) {
                    Vec::new()
                } else {
                    consonants(&n.parent.coda, n.hz)
                };
                NoteSegments { onset, coda }
            })
            .collect();
        for i in 0..parts.len() {
            let (before, after) = parts.split_at_mut(i + 1);
            let coda = &mut before[i].coda;
            if let Some(next) = after.first_mut() {
                squeeze(coda, &mut next.onset, phrase[i + 1].beat - phrase[i].beat);
            } else {
                squeeze(coda, &mut [], last_end - phrase[i].beat);
            }
        }
        let planning_start = phrase[0].beat - total(&parts[0].onset) - timing::BREATH_LEAD_SECONDS;
        let mut input = Vec::new();
        let mut nuclei = Vec::with_capacity(parts.len());
        let mut nasal_rhymes = Vec::new();
        let mut final_nasal = None;
        for (i, n) in phrase.iter().enumerate() {
            let note_end = parts
                .get(i + 1)
                .map_or(last_end, |p| phrase[i + 1].beat - total(&p.onset));
            let coda_seconds = total(&parts[i].coda);
            let vdur = (note_end - n.beat - coda_seconds).max(VOWEL_FLOOR_SECONDS);
            input.append(&mut parts[i].onset);
            let main = input.len();
            let mark = &n.syllable.nucleus;
            let (_, held, offglide) = nucleus_parts(&mark.ipa);
            let closing = n.parent.closing.filter(|&length| length > 0.0);
            if let Some(off) = offglide.filter(|_| !next_continues(i)) {
                if let Some(closing) = closing {
                    let glide = 0.5 * closing.min(CLOSING_SHARE * vdur);
                    input.push(vowel(held, vdur - glide, n.hz, mark));
                    input.push(Segment {
                        glide_seconds: Some(glide),
                        ..vowel(off, glide, n.hz, mark)
                    });
                } else {
                    input.push(vowel(held, vdur * 0.8, n.hz, mark));
                    input.push(vowel(off, vdur * 0.2, n.hz, mark));
                }
            } else {
                input.push(vowel(held, vdur, n.hz, mark));
            }
            nuclei.push((main..input.len(), vdur));
            if closing.is_some()
                && let Some(coda) = parts[i].coda.first()
                && let Some(kind) = NasalCoda::from_ipa(&coda.ipa)
            {
                let end = n.beat + vdur;
                nasal_rhymes.push(NasalRhyme {
                    coda: kind,
                    nucleus: held.to_owned(),
                    end,
                    vowel_seconds: end - n.beat,
                    nasal_lead: n.parent.nasal_lead.unwrap_or(0.0),
                });
                if i + 1 == phrase.len() && parts[i].coda.len() == 1 {
                    let fade_before_next_phrase = placed.get(last + 1).map(|next| {
                        let onset = total(&consonants(&next.syllable.onset, next.hz));
                        let medial = if nucleus_parts(&next.syllable.nucleus.ipa).0.is_some() {
                            MEDIAL_SECONDS
                        } else {
                            0.0
                        };
                        (next.beat - (onset + medial) - 0.05 - last_end).clamp(0.0, 0.15)
                    });
                    final_nasal = Some(FinalNasal {
                        coda: kind,
                        end: end + coda_seconds,
                        fade_before_next_phrase,
                    });
                }
            }
            input.append(&mut parts[i].coda);
        }
        let timing = timing::plan(&input, planning_start, 1.0)?;
        let mut actual = timing.segments.iter().peekable();
        for (note, (nucleus, nominal_vowel_seconds)) in phrase.iter().zip(nuclei) {
            while actual.peek().is_some_and(|s| s.input_index < nucleus.start) {
                actual.next();
            }
            let start = actual.peek().unwrap().start_seconds;
            let mut end = start;
            while actual.peek().is_some_and(|s| s.input_index < nucleus.end) {
                end = actual.next().unwrap().end_seconds;
            }
            output_notes.push(NoteTiming {
                note: note.note,
                lyric_index: note.lyric_index,
                beat_seconds: note.beat,
                beat_end_seconds: note.end,
                f0_hz: note.hz,
                nucleus_start_seconds: start,
                nucleus_end_seconds: end,
                nominal_vowel_seconds,
            });
        }
        end_seconds = end_seconds.max(timing.end_seconds);
        for s in &timing.segments {
            if !supported_speech_symbol(s) {
                unavailable.insert(s.segment.ipa.clone());
            }
        }
        let pitch = pitch(&timing);
        phrases.push(SungPhrase {
            first_note_index: first,
            last_note_index: last,
            planning_start_seconds: planning_start,
            timing,
            pitch,
            nasal_rhymes,
            final_nasal,
        });
        first = last + 1;
    }
    Ok(SongPlan {
        notes: output_notes,
        phrases,
        nominal_end_seconds: nominal_end,
        end_seconds,
        render_end_seconds: end_seconds + 0.4,
        unavailable_speech_symbols: unavailable.into_iter().collect(),
    })
}

/// 音符のF0と歌唱の呼気・開大・ビブラートを成人男性の調音スコアにまとめる。
pub fn male_score(plan: &SongPlan, vibrato_cents: f64) -> Result<Vec<Gesture>, &'static str> {
    score_with_body(plan, vibrato_cents, BodyName::Male.into())
}

/// 確定した拍と音素の時刻に、体型別の調音目標を与える。
pub fn score_with_body(
    plan: &SongPlan,
    vibrato_cents: f64,
    body: BodyMix,
) -> Result<Vec<Gesture>, &'static str> {
    if !vibrato_cents.is_finite() {
        return Err("ビブラート深さには有限のセント値を指定してください");
    }
    let mut gestures = Vec::new();
    for phrase in &plan.phrases {
        gestures.extend(sung_phrase_gestures(
            &phrase.timing,
            phrase.planning_start_seconds,
            body,
        )?);
        gestures.extend(phrase.pitch.iter().cloned());
        for rhyme in &phrase.nasal_rhymes {
            add_nasal_rhyme_gestures(rhyme, body, &mut gestures);
        }
        if let Some(final_nasal) = &phrase.final_nasal {
            add_final_nasal_gestures(final_nasal, &mut gestures);
        }
        for note in &plan.notes[phrase.first_note_index..=phrase.last_note_index] {
            let beat = note.beat_seconds;
            let end = beat + note.nominal_vowel_seconds;
            if end - beat > 0.3 {
                let mut targets = Targets::default();
                targets.set(ControlKey::Vibrato, vibrato_cents);
                gestures.push(Gesture {
                    t0: beat + 0.22,
                    t1: end,
                    ramp_in: 0.3,
                    ramp_out: 0.06,
                    strength: 4.0,
                    targets,
                    speed: None,
                    release_hold: None,
                    label: Some("vibrato".into()),
                });
            }
        }
    }
    Ok(gestures)
}

/// 歌唱の鼻音化と閉鎖への移行。係数は固定版CHIMERA由来（MIT）。
fn add_nasal_rhyme_gestures(rhyme: &NasalRhyme, body: BodyMix, gestures: &mut Vec<Gesture>) {
    use ControlKey::Artic;
    let end = rhyme.end;
    let opening = (rhyme.nasal_lead * rhyme.vowel_seconds).min(0.25);
    if opening > 0.0 {
        gestures.push(single(
            "nasal vowel",
            (end - 0.06, end + 0.02),
            (opening, 0.03),
            2.0,
            Artic(Articulator::Velum),
            0.30,
        ));
    }

    let x = Artic(Articulator::TongueBodyX);
    let y = Artic(Articulator::TongueBodyY);
    let mut targets = Targets::default();
    let strength = match rhyme.coda {
        NasalCoda::Labial => return,
        NasalCoda::Alveolar => {
            targets.set(x, 3.2);
            targets.set(y, 7.4);
            0.6
        }
        NasalCoda::Velar => {
            let vowel = vowel_targets(&rhyme.nucleus, body).unwrap_or_default();
            let rise = vowel.get(y).is_none_or(|position| position < 6.95);
            let back = vowel.get(x).is_some_and(|position| position > 3.0);
            if !rise && !back {
                return;
            }
            if rise {
                targets.set(y, 7.95);
            }
            if back {
                targets.set(x, 2.83);
            }
            1.2
        }
    };
    gestures.push(Gesture {
        t0: end - 0.01,
        t1: end + 0.02,
        ramp_in: (0.5 * rhyme.vowel_seconds).min(0.15),
        ramp_out: 0.03,
        strength,
        targets,
        speed: None,
        release_hold: None,
        label: Some("coda approach".into()),
    });
}

fn add_final_nasal_gestures(nasal: &FinalNasal, gestures: &mut Vec<Gesture>) {
    use ControlKey::Artic;
    let (hold, release, velum) = match nasal.fade_before_next_phrase {
        Some(fade) => {
            let hold = fade.min(0.1);
            (hold, 0.05, hold)
        }
        None => (0.10, 0.12, 0.25),
    };
    let (primary, value, secondary) = nasal.coda.closure();
    let start = nasal.end - 0.03;
    let mut closure = single(
        "coda held",
        (start, nasal.end + hold),
        (0.02, release),
        40.0,
        Artic(primary),
        value,
    );
    if let Some((axis, value)) = secondary {
        closure.targets.set(Artic(axis), value);
    }
    gestures.push(closure);
    gestures.push(single(
        "velum",
        (start, nasal.end + velum),
        (0.02, 0.05),
        4.0,
        Artic(Articulator::Velum),
        0.45,
    ));
}
