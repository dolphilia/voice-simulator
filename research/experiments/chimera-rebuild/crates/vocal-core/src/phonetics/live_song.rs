//! 押下と解放を、保持・持ち替え可能な歌唱ジェスチャーに変換する。
//! 固定版CHIMERA（MIT）の歌唱計画とタグによる解放を参照する。

use super::{
    Segment,
    song::{consonants_with_scale, midi_to_hz, nucleus_parts, pitch, vowel},
    speech::{append_breath_and_release, segment_gestures, single, supported_speech_symbol},
    syllables::{Syllable, is_nucleus},
    timing,
};
use crate::{
    anatomy::BodyMix,
    score::{ControlKey, Gesture},
    voice::ArticulatedVoice,
};
use serde::{Deserialize, Serialize};
use std::f64::consts::PI;

const LEAD: f64 = 0.006;
const NOTE_START: f64 = -0.045;
const HOLD: f64 = 30.0;

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(tag = "type", rename_all = "kebab-case", deny_unknown_fields)]
pub enum KeyEvent {
    NoteOn { note: u8, velocity: u8 },
    NoteOff { note: u8 },
}

impl KeyEvent {
    pub fn validate(self) -> Result<(), &'static str> {
        match self {
            Self::NoteOn {
                note: 0..=127,
                velocity: 1..=127,
            }
            | Self::NoteOff { note: 0..=127 } => Ok(()),
            _ => Err("MIDI番号は0〜127、押下のベロシティは1〜127で指定してください"),
        }
    }
}

#[derive(Clone, Copy, Debug, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum Action {
    Syllable,
    Melisma,
    Fallback,
    Release,
    Ignored,
}

#[derive(Debug, Serialize)]
pub struct Transition<'a> {
    pub action: Action,
    pub next_syllable: usize,
    pub sounding_note: Option<u8>,
    pub sounding_syllable: Option<&'a str>,
    pub clock_seconds: f64,
}

#[derive(Clone, Copy)]
struct HeldVoice {
    note: u8,
    syllable: usize,
    tag: u64,
}

pub struct LiveSong {
    syllables: Vec<Syllable>,
    cursor: usize,
    held: Vec<u8>,
    sounding: Option<HeldVoice>,
    score: Vec<(u64, Gesture)>,
    next_tag: u64,
    body: BodyMix,
    vibrato: f64,
}

impl LiveSong {
    pub fn new(
        mut syllables: Vec<Syllable>,
        body: BodyMix,
        vibrato: f64,
    ) -> Result<Self, &'static str> {
        if !vibrato.is_finite() || vibrato < 0.0 {
            return Err("ビブラート深さには有限の非負値を指定してください");
        }
        // 先頭に母音継続だけがあるときも、中立の歌唱母音を参照できるようにする。
        syllables.push(Syllable {
            text: "ah".to_owned(),
            nucleus: Segment {
                ipa: "ɑ".to_owned(),
                ..Segment::default()
            },
            ..Syllable::default()
        });
        for syl in syllables.iter().filter(|s| s.melisma != Some(true)) {
            if !is_nucleus(&syl.nucleus.ipa)
                || [&syl.onset, &syl.coda].into_iter().any(|parts| {
                    !timing::plan(parts, 0.0, 1.0)
                        .is_ok_and(|plan| plan.segments.iter().all(supported_speech_symbol))
                })
            {
                return Err("演奏できない音素または時間指定があります");
            }
        }
        Ok(Self {
            syllables,
            cursor: 0,
            held: Vec::new(),
            sounding: None,
            score: Vec::new(),
            next_tag: 2,
            body,
            vibrato,
        })
    }

    /// 調音・音高のタグを含む、演奏中のスコアの観測用読み出し。
    pub fn scheduled_gestures(&self) -> &[(u64, Gesture)] {
        &self.score
    }

    fn lyric_count(&self) -> usize {
        (self.syllables.len() - 1).max(1)
    }

    pub fn apply(
        &mut self,
        event: KeyEvent,
        voice: &mut ArticulatedVoice,
    ) -> Result<Transition<'_>, &'static str> {
        event.validate()?;
        let time = voice.clock_seconds();
        self.score.retain(|(_, g)| g.speed_end() >= time);
        let action = match event {
            KeyEvent::NoteOn { note, velocity } => self.press(note, velocity, time)?,
            KeyEvent::NoteOff { note } => self.release(note, time)?,
        };
        if !matches!(action, Action::Ignored) {
            voice.set_score(self.score.iter().map(|(_, g)| g.clone()).collect())?;
        }
        Ok(Transition {
            action,
            next_syllable: self.cursor,
            sounding_note: self.sounding.map(|s| s.note),
            sounding_syllable: self
                .sounding
                .map(|s| self.syllables[s.syllable].text.as_str()),
            clock_seconds: time,
        })
    }

    fn press(&mut self, note: u8, velocity: u8, time: f64) -> Result<Action, &'static str> {
        self.held.retain(|&key| key != note);
        self.held.push(note);
        let cursor = self.cursor;
        self.cursor = (cursor + 1) % self.lyric_count();
        let continuation = self.syllables[cursor].melisma == Some(true);
        if let Some(held) = self.sounding.filter(|_| continuation) {
            self.glide(held, note, time);
            return Ok(Action::Melisma);
        }
        // 発声中の語尾の開大だけを切り上げ、末子音の残りは再生する。
        release_matching(&mut self.score, time, |_, g| {
            g.label.as_deref() == Some("exhale")
        });
        let mut segments = Vec::new();
        if let Some(previous) = self.sounding {
            release_matching(&mut self.score, time, |tag, _| {
                tag == previous.tag || tag == previous.tag + 1
            });
            segments.extend(tail(&self.syllables[previous.syllable], previous.note));
        }
        let index = if continuation {
            (0..cursor)
                .rev()
                .find(|&i| self.syllables[i].melisma != Some(true))
                .unwrap_or(self.syllables.len() - 1)
        } else {
            cursor
        };
        let syl = &self.syllables[index];
        let hz = midi_to_hz(f64::from(note));
        if !continuation {
            segments.extend(consonants_with_scale(&syl.onset, hz, 0.7));
        }
        let (medial, held, _) = nucleus_parts(&syl.nucleus.ipa);
        if let Some(ipa) = medial.filter(|_| !continuation) {
            segments.push(vowel(ipa, 0.05, hz, &syl.nucleus));
        }
        segments.push(vowel(held, HOLD, hz, &syl.nucleus));
        let timing = timing::plan(&segments, NOTE_START, 1.0)?;
        let mut gestures = segment_gestures(&timing, self.body)?;
        gestures.extend(pitch(&timing));
        let nucleus_start = timing.segments.last().expect("保持する母音").start_seconds;
        gestures.push(single(
            "breath",
            (NOTE_START + 0.04, timing.end_seconds),
            (0.04, 0.07),
            1.0,
            ControlKey::Breath,
            breath_for(velocity),
        ));
        gestures.push(vibrato(nucleus_start, timing.end_seconds, self.vibrato));
        let tag = self.allocate_tag();
        self.schedule(tag, time, gestures);
        self.sounding = Some(HeldVoice {
            note,
            syllable: index,
            tag,
        });
        Ok(Action::Syllable)
    }

    fn glide(&mut self, mut held: HeldVoice, note: u8, time: f64) {
        release_matching(&mut self.score, time, |tag, _| tag == held.tag + 1);
        self.schedule(
            held.tag,
            time,
            [
                single(
                    "pitch",
                    (0.0, HOLD),
                    (0.05, 0.06),
                    6.0,
                    ControlKey::F0,
                    midi_to_hz(f64::from(note)),
                ),
                vibrato(0.0, HOLD, self.vibrato),
            ],
        );
        held.note = note;
        self.sounding = Some(held);
    }

    fn release(&mut self, note: u8, time: f64) -> Result<Action, &'static str> {
        self.held.retain(|&key| key != note);
        let Some(held) = self.sounding.filter(|s| s.note == note) else {
            return Ok(Action::Ignored);
        };
        if let Some(&previous) = self.held.last() {
            self.glide(held, previous, time);
            return Ok(Action::Fallback);
        }
        self.sounding = None;
        release_matching(&mut self.score, time, |tag, _| {
            tag == held.tag || tag == held.tag + 1
        });
        if self.syllables[self.cursor].melisma != Some(true) {
            let segments = tail(&self.syllables[held.syllable], note);
            if !segments.is_empty() {
                let timing = timing::plan(&segments, NOTE_START, 1.0)?;
                let mut gestures = segment_gestures(&timing, self.body)?;
                gestures.extend(pitch(&timing));
                append_breath_and_release(&timing, NOTE_START, false, &mut gestures);
                let tag = self.allocate_tag();
                self.schedule(tag, time, gestures);
            }
        }
        Ok(Action::Release)
    }

    fn allocate_tag(&mut self) -> u64 {
        let tag = self.next_tag;
        self.next_tag += 2;
        tag
    }

    fn schedule(&mut self, tag: u64, time: f64, gestures: impl IntoIterator<Item = Gesture>) {
        self.score.extend(gestures.into_iter().map(|mut g| {
            let off = time + LEAD;
            g.t0 += off;
            g.t1 += off;
            let pitch = g.targets.get(ControlKey::F0).is_some()
                || g.targets.get(ControlKey::Vibrato).is_some();
            (tag + u64::from(pitch), g)
        }));
    }
}

fn tail(syl: &Syllable, note: u8) -> Vec<Segment> {
    let hz = midi_to_hz(f64::from(note));
    let (_, _, glide) = nucleus_parts(&syl.nucleus.ipa);
    glide
        .into_iter()
        .map(|ipa| vowel(ipa, 0.07, hz, &syl.nucleus))
        .chain(consonants_with_scale(&syl.coda, hz, 0.7))
        .collect()
}

fn vibrato(start: f64, end: f64, depth: f64) -> Gesture {
    single(
        "vibrato",
        (start + 0.22, end),
        (0.3, 0.06),
        4.0,
        ControlKey::Vibrato,
        depth,
    )
}

fn breath_for(velocity: u8) -> f64 {
    let velocity = f64::from(velocity);
    0.62 + 0.4 * (velocity / 96.0).min(1.0) + 0.12 * ((velocity - 96.0) / 31.0).max(0.0)
}

fn release_matching(
    score: &mut Vec<(u64, Gesture)>,
    time: f64,
    matches: impl Fn(u64, &Gesture) -> bool,
) {
    score.retain_mut(|(tag, gesture)| {
        if !matches(*tag, gesture) || time >= gesture.t1 {
            return true;
        }
        if time <= gesture.t0 - gesture.ramp_in {
            return false;
        }
        if time < gesture.t0 {
            let phase = libm::acos((2.0 * gesture.activation(time) - 1.0).clamp(-1.0, 1.0)) / PI;
            gesture.t1 = time - phase * gesture.ramp_out.max(1e-6);
            gesture.t0 = gesture.t1;
        } else {
            gesture.t1 = time;
        }
        true
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn release_inside_attack_keeps_its_weight_and_discards_future_gestures() {
        let now = 0.02;
        let rising = single(
            "rising",
            (0.04, 1.0),
            (0.04, 0.07),
            1.0,
            ControlKey::Breath,
            1.0,
        );
        let future = single(
            "future",
            (0.1, 1.0),
            (0.04, 0.07),
            1.0,
            ControlKey::F0,
            220.0,
        );
        let at_release = rising.activation(now);
        let mut score = vec![(2, rising), (2, future.clone()), (3, future)];
        release_matching(&mut score, now, |tag, _| tag == 2);
        assert_eq!(score.len(), 2);
        assert!((score[0].1.activation(now) - at_release).abs() < 1e-12);
        assert!(score[0].1.activation(now + 0.01) < at_release);
        assert_eq!(score[1].1.t1, 1.0);
    }
}
