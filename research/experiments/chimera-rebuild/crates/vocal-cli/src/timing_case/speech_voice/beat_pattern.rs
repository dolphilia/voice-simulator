//! 休符を含むパターンを、出力128フレームごとの音源時計で予約する。

use super::{Performance, Pose, Settings, TraceFeatures, beatbox_setup, render};
use crate::network_case::Destination;
use serde::Deserialize;
use serde_json::{Value, json};
use std::error::Error;
use vocal_core::{
    phonetics::beatbox::{BeatPlayer, BeatSound},
    score::Gesture,
    voice::ArticulatedVoice,
};

#[derive(Deserialize)]
struct Case {
    beatbox_pattern: Input,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Input {
    pattern: String,
    bpm: f64,
    swing: f64,
    render_end_seconds: f64,
    posture: Pose,
    internal_sample_rate_hz: u32,
    initial_f0_hz: f64,
    voice: Settings,
    noise_scale: f64,
    #[serde(default)]
    events: Vec<TransportEvent>,
}

#[derive(Clone, Copy, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
enum TransportEvent {
    Tempo {
        frame: usize,
        bpm: Option<f64>,
        swing: Option<f64>,
    },
    Playing {
        frame: usize,
        playing: bool,
    },
    BassKey {
        frame: usize,
        note: u8,
        pressed: bool,
    },
    ToggleHum {
        frame: usize,
        step: usize,
    },
}

impl TransportEvent {
    fn frame(self) -> usize {
        match self {
            Self::Tempo { frame, .. }
            | Self::Playing { frame, .. }
            | Self::BassKey { frame, .. }
            | Self::ToggleHum { frame, .. } => frame,
        }
    }

    fn apply(
        self,
        player: &mut BeatPlayer,
        clock: f64,
        voice: Option<&mut ArticulatedVoice>,
    ) -> Result<bool, &'static str> {
        match self {
            Self::Tempo { bpm, swing, .. } => {
                player.set_tempo(bpm, swing)?;
                Ok(false)
            }
            Self::Playing { playing, .. } => player.set_playing(playing, clock),
            Self::BassKey { note, pressed, .. } => {
                player.set_bass_key(note, pressed)?;
                if let Some(voice) = voice {
                    player.apply_bass(voice)?;
                }
                Ok(false)
            }
            Self::ToggleHum { step, .. } => {
                player.toggle_hum(step)?;
                Ok(false)
            }
        }
    }
}

pub(crate) fn run(value: Value, destination: Destination<'_>) -> Result<(), Box<dyn Error>> {
    let case = Case::deserialize(&value)?.beatbox_pattern;
    let player = BeatPlayer::starting(&case.pattern, case.bpm, case.swing, 0.0)?;
    let slot_sounds: Vec<_> = player
        .steps()
        .iter()
        .map(|step| step.map(|s| s.sound))
        .collect();
    let slot_accents: Vec<_> = player
        .steps()
        .iter()
        .map(|step| step.map(|s| s.accent))
        .collect();
    let observe_hat = slot_sounds.iter().flatten().any(|sound| sound.is_hat());
    let observe_labiodental = slot_sounds.contains(&Some(BeatSound::Snare));
    let observe_hum = slot_sounds.contains(&Some(BeatSound::Hum))
        || case.events.iter().any(|event| {
            matches!(
                event,
                TransportEvent::BassKey { .. } | TransportEvent::ToggleHum { .. }
            )
        });
    let observe_velar = slot_sounds
        .iter()
        .flatten()
        .any(|sound| sound.has_velar_closure());
    let setup = beatbox_setup(
        case.voice,
        case.posture,
        case.internal_sample_rate_hz,
        case.initial_f0_hz,
        case.noise_scale,
    )?;
    let mut report = json!({
        "slot_accents": slot_accents,
        "slot_sounds": slot_sounds,
        "ready_targets": setup.base_targets,
        "scheduler_block_frames": BeatPlayer::BLOCK_FRAMES,
    });
    if observe_hum
        || player
            .steps()
            .iter()
            .flatten()
            .any(|step| step.midi_note.is_some())
    {
        let notes: Vec<_> = player
            .steps()
            .iter()
            .map(|step| step.and_then(|s| s.midi_note))
            .collect();
        report["slot_midi_notes"] = json!(notes);
    }
    let performance = Performance {
        warm_up_frames: 0,
        report_key: "beatbox_pattern",
        report,
        gestures: Vec::new(),
        pattern: Some(Playback {
            player,
            sample: 0,
            output_factor: setup.stage.factor(),
            events: case.events,
            event_index: 0,
            scratch: Vec::with_capacity(BeatSound::MAX_GESTURES),
        }),
        render_end: case.render_end_seconds,
        features: TraceFeatures {
            beatbox: true,
            velum: observe_hum,
            smoothed_pitch: observe_hum,
            oral_cells: observe_hat || observe_labiodental || observe_velar || observe_hum,
            oral_posture: observe_velar,
            pharynx_minimum: observe_velar,
            labiodental: observe_labiodental,
            inward_jet: slot_sounds.contains(&Some(BeatSound::InwardSnare)),
            constriction_position: slot_sounds.contains(&Some(BeatSound::Crash)),
            oral_cell_acoustics: slot_sounds
                .iter()
                .flatten()
                .any(|sound| sound.has_oral_pocket()),
            ..TraceFeatures::default()
        },
        tract_profile_frames: None,
        tract_profile_acoustics: false,
        tract_profile_grid: false,
        tract_profile_posture: false,
    };
    render(value, destination, setup, performance, None)
}

#[derive(Clone)]
pub(super) struct Playback {
    player: BeatPlayer,
    sample: usize,
    output_factor: usize,
    events: Vec<TransportEvent>,
    event_index: usize,
    scratch: Vec<Gesture>,
}

impl Playback {
    pub(super) fn validate_frames(&self, frames: usize) -> Result<(), &'static str> {
        if self.events.iter().any(|event| event.frame() >= frames)
            || self
                .events
                .windows(2)
                .any(|events| events[0].frame() > events[1].frame())
        {
            return Err("再生操作のフレームは出力範囲内で時刻順に指定してください");
        }
        Ok(())
    }

    fn apply_events(
        &mut self,
        frame: usize,
        clock: f64,
        mut voice: Option<&mut ArticulatedVoice>,
        mut observe: impl FnMut(usize, bool),
    ) -> Result<bool, &'static str> {
        let mut canceled = false;
        while let Some(&event) = self.events.get(self.event_index)
            && event.frame() == frame
        {
            let next = self.player.next_step();
            let clear = event.apply(&mut self.player, clock, voice.as_deref_mut())?;
            observe(next, clear);
            canceled |= clear;
            self.event_index += 1;
        }
        Ok(canceled)
    }

    pub(super) fn before_sample(
        &mut self,
        voice: &mut ArticulatedVoice,
    ) -> Result<(), &'static str> {
        let clock = voice.clock_seconds();
        if let Some(event) = self.events.get(self.event_index)
            && self.sample == event.frame() * self.output_factor
            && self.apply_events(event.frame(), clock, Some(voice), |_, _| {})?
        {
            voice.cancel_score();
        }
        if self.sample.is_multiple_of(self.output_factor) {
            let frame = self.sample / self.output_factor;
            self.player
                .prepare_frame(frame as u64, voice, &mut self.scratch)?;
        }
        self.sample += 1;
        Ok(())
    }

    pub(super) fn position(&self, clock: f64) -> (usize, i32) {
        (
            self.player.next_step(),
            self.player.step_at(clock).map_or(-1, |step| step as i32),
        )
    }

    /// 描画せずに、出力フレームと調音制御の時計で予約と再生操作を追う。
    pub(super) fn reservations(
        &self,
        frames: usize,
        control_seconds: f64,
    ) -> Result<(Value, Vec<Value>), &'static str> {
        let mut playback = self.clone();
        let mut clock = 0.0;
        let mut rows = Vec::new();
        let mut events = Vec::new();
        let mut scratch = Vec::with_capacity(BeatSound::MAX_GESTURES);
        for frame in 0..frames {
            playback.apply_events(frame, clock, None, |next, cleared| {
                events.push(json!({
                    "frame": frame, "clock_seconds": clock,
                    "next_step_before": next, "score_cleared": cleared
                }));
            })?;
            if frame.is_multiple_of(BeatPlayer::BLOCK_FRAMES) {
                playback.player.tick(clock, |step| {
                    let gestures = if let Some(beat) = step.beat {
                        scratch.clear();
                        let length = step
                            .length_seconds
                            .ok_or("打音の持続可能時間がありません")?;
                        beat.append_gestures(step.hit_seconds, length, &mut scratch)?;
                        Some(scratch.as_slice())
                    } else {
                        None
                    };
                    let mut row = json!({
                        "frame": frame, "clock_seconds": clock, "gestures": gestures,
                        "step": {
                            "index": step.index,
                            "hit_seconds": step.hit_seconds,
                            "accent": step.beat.map(|beat| beat.accent),
                            "sound": step.beat.map(|beat| beat.sound),
                            "length_seconds": step.length_seconds,
                        },
                    });
                    if let Some(note) = step.beat.and_then(|beat| beat.midi_note) {
                        row["step"]["midi_note"] = json!(note);
                    }
                    rows.push(row);
                    Ok(())
                })?;
            }
            if frame.is_multiple_of(64) {
                clock += control_seconds;
            }
        }
        Ok((json!(rows), events))
    }
}
