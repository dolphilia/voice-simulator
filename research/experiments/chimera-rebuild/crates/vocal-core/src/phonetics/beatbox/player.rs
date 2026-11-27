//! ビートの再生とテンポ変更。先読みと再生位置の時刻はCHIMERA由来（MIT）。

use super::{BeatSound, male_ready_targets};
use crate::{
    articulators::Articulator,
    phonetics::song::midi_to_hz,
    score::{ControlKey, Gesture},
    voice::ArticulatedVoice,
};

#[derive(Clone, Copy)]
pub struct BeatStep {
    pub sound: BeatSound,
    pub accent: f64,
    pub midi_note: Option<f64>,
}

impl BeatStep {
    pub fn append_gestures(
        self,
        hit_seconds: f64,
        step_seconds: f64,
        output: &mut Vec<Gesture>,
    ) -> Result<(), &'static str> {
        self.sound.append_notated_gestures(
            hit_seconds,
            self.accent,
            step_seconds,
            self.midi_note,
            output,
        )
    }
}

#[derive(Clone, Copy)]
pub struct ScheduledStep {
    pub index: usize,
    pub hit_seconds: f64,
    pub beat: Option<BeatStep>,
    pub length_seconds: Option<f64>,
}

#[derive(Clone)]
pub struct BeatPlayer {
    steps: Vec<Option<BeatStep>>,
    bpm: f64,
    swing: f64,
    playing: bool,
    anchor_seconds: f64,
    anchor_step: usize,
    next_step: usize,
    marks: [Option<(usize, f64)>; 32],
    held_bass: Vec<u8>,
    bass_note: u8,
    performer_pitch: Option<u8>,
}

impl BeatPlayer {
    pub const HORIZON_SECONDS: f64 = 0.2;
    pub const BLOCK_FRAMES: usize = 128;
    pub const DEFAULT_BASS_NOTE: u8 = 40;

    /// 打音と休符をループする。対応していない音色はケースの入力エラーとして返す。
    pub fn starting(pattern: &str, bpm: f64, swing: f64, clock: f64) -> Result<Self, &'static str> {
        if !bpm.is_finite() || !swing.is_finite() || !clock.is_finite() || clock < 0.0 {
            return Err("テンポ、スウィング、開始時刻には有限値を指定してください");
        }
        let steps = pattern
            .split(|c: char| c == '|' || c == '\u{feff}' || (c != '\u{85}' && c.is_whitespace()))
            .filter(|token| !token.is_empty())
            .take(256)
            .map(|token| {
                if matches!(token, "." | "-") {
                    return Ok(None);
                }
                let (token, accent) = token.strip_suffix('>').map_or((token, 1.0), |s| (s, 1.3));
                let mut sound = token;
                let mut midi_note = None;
                if let Some((id, digits)) = token.rsplit_once(':')
                    && !id.is_empty()
                    && !digits.is_empty()
                    && digits.bytes().all(|digit| digit.is_ascii_digit())
                {
                    sound = id;
                    midi_note = Some(digits.parse().map_err(|_| "MIDI音高を読み取れません")?);
                }
                let sound =
                    BeatSound::from_id(sound).ok_or("パターンに対応していない打音があります")?;
                Ok(Some(BeatStep {
                    sound,
                    accent,
                    midi_note,
                }))
            })
            .collect::<Result<Vec<_>, _>>()?;
        Ok(Self {
            steps,
            bpm: bpm.clamp(40.0, 240.0),
            swing: swing.clamp(0.0, 0.6),
            playing: true,
            anchor_seconds: clock + Self::HORIZON_SECONDS,
            anchor_step: 0,
            next_step: 0,
            marks: [None; 32],
            held_bass: Vec::with_capacity(128),
            bass_note: Self::DEFAULT_BASS_NOTE,
            performer_pitch: None,
        })
    }

    pub fn steps(&self) -> &[Option<BeatStep>] {
        &self.steps
    }

    /// 保持音の優先順位と、次に置くハムの音高を別々に更新する。
    pub fn set_bass_key(&mut self, note: u8, pressed: bool) -> Result<(), &'static str> {
        if note > 127 {
            return Err("MIDI音番号は0〜127の範囲で指定してください");
        }
        self.held_bass.retain(|&held| held != note);
        if pressed {
            self.held_bass.push(note);
            self.bass_note = note;
        }
        if let Some(&note) = self.held_bass.last() {
            self.performer_pitch = Some(note);
        }
        Ok(())
    }

    /// 保持音を演奏者の調音と呼気に反映する。予約済みのスコアと重ねて発声する。
    pub fn apply_bass(&self, voice: &mut ArticulatedVoice) -> Result<(), &'static str> {
        if let Some(note) = self.performer_pitch {
            voice.set_base_pitch(midi_to_hz(f64::from(note)))?;
        }
        let held = !self.held_bass.is_empty();
        let ready = male_ready_targets();
        let lip = if held {
            -0.25
        } else {
            ready
                .get(ControlKey::Artic(Articulator::LipAperture))
                .ok_or("ビート準備姿勢に唇の目標がありません")?
        };
        let bank = voice.control_inputs().0;
        bank.set_target(Articulator::LipAperture, lip);
        bank.set_target(Articulator::Velum, if held { 0.9 } else { -0.15 });
        voice.set_performer_gate(if held { 1.0 } else { 0.0 })
    }

    /// セルを編集する。先読みで既に予約したジェスチャーはそのまま発音する。
    pub fn toggle_hum(&mut self, index: usize) -> Result<(), &'static str> {
        let step = self
            .steps
            .get_mut(index)
            .ok_or("ステップの番号が範囲外です")?;
        *step = if step.is_some_and(|beat| beat.sound == BeatSound::Hum) {
            None
        } else {
            Some(BeatStep {
                sound: BeatSound::Hum,
                accent: 1.0,
                midi_note: Some(f64::from(self.bass_note)),
            })
        };
        Ok(())
    }

    pub fn next_step(&self) -> usize {
        self.next_step
    }

    fn step_seconds(&self) -> f64 {
        60.0 / self.bpm / 4.0
    }

    /// 再生中は最初の未予約ステップの無スウィング時刻を支点にする。
    pub fn set_tempo(&mut self, bpm: Option<f64>, swing: Option<f64>) -> Result<(), &'static str> {
        let bpm = bpm.unwrap_or(self.bpm);
        let swing = swing.unwrap_or(self.swing);
        if !bpm.is_finite() || !swing.is_finite() {
            return Err("テンポとスウィングには有限値を指定してください");
        }
        let bpm = bpm.clamp(40.0, 240.0);
        if self.playing && bpm != self.bpm {
            self.anchor_seconds += (self.next_step - self.anchor_step) as f64 * self.step_seconds();
            self.anchor_step = self.next_step;
        }
        self.bpm = bpm;
        self.swing = swing.clamp(0.0, 0.6);
        Ok(())
    }

    /// 停止へ切り替えた場合は、呼び出し元が音源のスコアを消す。
    pub fn set_playing(&mut self, playing: bool, clock: f64) -> Result<bool, &'static str> {
        if self.playing == playing {
            return Ok(false);
        }
        if playing {
            if !clock.is_finite() || clock < 0.0 {
                return Err("開始時刻には有限の非負値を指定してください");
            }
            self.anchor_seconds = clock + Self::HORIZON_SECONDS;
            self.anchor_step = 0;
            self.next_step = 0;
            self.marks.fill(None);
        }
        self.playing = playing;
        Ok(!playing)
    }

    pub fn step_at(&self, clock: f64) -> Option<usize> {
        if !self.playing || self.steps.is_empty() {
            return None;
        }
        self.marks
            .iter()
            .flatten()
            .filter(|(_, time)| *time <= clock)
            .max_by(|left, right| left.1.total_cmp(&right.1))
            .map(|(index, _)| index % self.steps.len())
    }

    /// 通算出力フレームの境界で、次の内部サンプルより先に打音を予約する。
    pub fn prepare_frame(
        &mut self,
        frame: u64,
        voice: &mut ArticulatedVoice,
        scratch: &mut Vec<Gesture>,
    ) -> Result<(), &'static str> {
        if !frame.is_multiple_of(Self::BLOCK_FRAMES as u64) {
            return Ok(());
        }
        self.tick(voice.clock_seconds(), |step| {
            if let Some(beat) = step.beat {
                let length = step
                    .length_seconds
                    .ok_or("打音の持続可能時間がありません")?;
                beat.append_gestures(step.hit_seconds, length, scratch)?;
                voice.append_score(scratch)?;
            }
            Ok(())
        })
    }

    /// 先読み内の各ステップを一度通知し、打音の予約に必要な長さを求める。
    pub fn tick(
        &mut self,
        clock: f64,
        mut schedule: impl FnMut(ScheduledStep) -> Result<(), &'static str>,
    ) -> Result<(), &'static str> {
        let length = self.steps.len();
        if !self.playing || length == 0 {
            return Ok(());
        }
        let step_seconds = self.step_seconds();
        for _ in 0..64 {
            let index = self.next_step;
            let mut hit = self.anchor_seconds + (index - self.anchor_step) as f64 * step_seconds;
            if index % 2 == 1 {
                hit += self.swing * 0.5 * step_seconds;
            }
            if hit > clock + Self::HORIZON_SECONDS {
                break;
            }
            let cell = index % length;
            let beat = self.steps[cell].filter(|_| hit >= clock);
            let duration = beat.map(|_| {
                let rests = (1..length)
                    .take_while(|&offset| self.steps[(cell + offset) % length].is_none())
                    .count();
                (1 + rests) as f64 * step_seconds
            });
            schedule(ScheduledStep {
                index,
                hit_seconds: hit,
                beat,
                length_seconds: duration,
            })?;
            // 通算番号が増えるたびに一つ進むため、別の書き込み位置は不要。
            self.marks[index % self.marks.len()] = Some((index, hit));
            self.next_step += 1;
        }
        Ok(())
    }
}
