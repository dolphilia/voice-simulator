//! 保存したMIDIイベントを出力フレーム境界で再実行する歌唱ケース。

use crate::{
    geometry_case::{BodyInput, Pose, voice::Settings},
    network_case::{Destination, pcm},
    write_json,
};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    error::Error,
    fs::File,
    io::{self, BufWriter, Write},
};
use vocal_core::{
    anatomy::{BodyMix, BodyName},
    articulators::Articulator,
    output::OutputStage,
    phonetics::{
        live_song::{KeyEvent, LiveSong},
        syllables::Syllable,
    },
    voice::{ArticulatedVoice, VoiceSample},
};

#[derive(Deserialize)]
struct Case {
    live_song_voice: Input,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Input {
    body: Option<BodyInput>,
    posture: Pose,
    voice: Settings,
    internal_sample_rate_hz: u32,
    vibrato_cents: f64,
    frames: usize,
    stop_frame: Option<usize>,
    syllables: Vec<Syllable>,
    events: Vec<Event>,
    #[serde(default)]
    observe_gestures: bool,
}

#[derive(Deserialize)]
struct Event {
    frame: usize,
    #[serde(flatten)]
    key: KeyEvent,
}

pub(super) fn run(value: Value, destination: Destination<'_>) -> Result<(), Box<dyn Error>> {
    let input = Case::deserialize(&value)?.live_song_voice;
    let voice = input.voice;
    let rate = voice.output_sample_rate_hz;
    let mut stage = voice.output_stage(input.internal_sample_rate_hz)?;
    let factor = stage.factor();
    if input.frames == 0
        || input.frames > (u32::MAX as usize - 50) / 4
        || input.stop_frame.is_some_and(|frame| frame >= input.frames)
        || input
            .events
            .iter()
            .any(|e| e.frame >= input.stop_frame.unwrap_or(input.frames))
        || input
            .events
            .windows(2)
            .any(|pair| pair[0].frame > pair[1].frame)
    {
        return Err(
            "出力長とイベントのフレーム番号を確認してください。イベントは時刻順に指定します".into(),
        );
    }
    for event in &input.events {
        event.key.validate()?;
    }
    let body = input
        .body
        .map_or_else(|| BodyName::Male.into(), BodyMix::from);
    let mut song = LiveSong::new(input.syllables, body, input.vibrato_cents)?;
    let mut human = ArticulatedVoice::for_speech_with_body(
        input.internal_sample_rate_hz,
        64 * factor,
        input.posture.into(),
        voice.source(Some(110.0))?,
        body,
    )?;
    human.enable_turbulence(1.0)?;
    let mut events = input.events.iter().peekable();
    let apply = |frame,
                 song: &mut LiveSong,
                 human: &mut ArticulatedVoice,
                 events: &mut std::iter::Peekable<std::slice::Iter<'_, Event>>|
     -> Result<Vec<Value>, &'static str> {
        if input.stop_frame == Some(frame) {
            human.cancel_score();
            human.set_performer_gate(0.0)?;
        }
        let mut report = Vec::new();
        while events.peek().is_some_and(|e| e.frame == frame) {
            let event = events.next().expect("適用フレームの一致");
            let transition = song.apply(event.key, human)?;
            report.push(json!({ "frame":frame, "key":event.key, "transition":transition }));
        }
        Ok(report)
    };
    let render = |human: &mut ArticulatedVoice, stage: &mut OutputStage| {
        stage.render_frame(|| {
            let sample = human.step()?;
            Ok((sample.radiation.radiation_flow_derivative_cm3_s2, sample))
        })
    };
    match destination {
        Destination::Inspect => {
            let end = input.events.last().map_or(0, |e| e.frame);
            let mut transitions = Vec::with_capacity(input.events.len());
            let mut scheduled = Vec::new();
            for frame in 0..=end {
                let applied = apply(frame, &mut song, &mut human, &mut events)?;
                if input.observe_gestures && !applied.is_empty() {
                    scheduled.push(json!({ "frame":frame, "gestures":song.scheduled_gestures() }));
                }
                transitions.extend(applied);
                if frame < end {
                    render(&mut human, &mut stage)?;
                }
            }
            let mut result = json!({"output_frames":input.frames, "transitions":transitions});
            if input.observe_gestures {
                result["scheduled"] = json!(scheduled);
            }
            write_json(io::stdout().lock(), &result)
        }
        Destination::Trace(path) => {
            let mut output = BufWriter::new(File::create_new(path)?);
            writeln!(
                output,
                concat!(
                    "frame,lip_aperture_cm,lip_minimum_cm2,gate,voicing,f0_hz,smoothed_f0_hz,nose_flow_cm3_s,",
                    "lip_flow_cm3_s,glottal_area_cm2,glottal_flow_cm3_s,radiation_derivative_cm3_s2"
                )
            )?;
            for frame in 0..input.frames {
                apply(frame, &mut song, &mut human, &mut events)?;
                let (_, s): (_, VoiceSample) = render(&mut human, &mut stage)?;
                let lip = human
                    .articulators()
                    .state(Articulator::LipAperture)
                    .position;
                let airway = human.airway();
                let min_area = airway.network.section(airway.lips).minimum_area_cm2;
                writeln!(
                    output,
                    "{frame},{lip},{min_area},{},{},{},{},{},{},{},{},{}",
                    s.breath.gate,
                    s.glottis.voicing,
                    s.glottis.f0_hz,
                    human.smoothed_pitch_hz(),
                    s.nose_flow_cm3_s,
                    s.lip_flow_cm3_s,
                    s.glottis.area_cm2,
                    s.glottal_flow_cm3_s,
                    s.radiation.radiation_flow_derivative_cm3_s2
                )?;
            }
            output.flush()?;
            Ok(())
        }
        Destination::Pcm {
            wave,
            trace,
            block_frames,
        } => {
            let mut frame = 0;
            pcm::write_frames(
                || {
                    apply(frame, &mut song, &mut human, &mut events)?;
                    frame += 1;
                    render(&mut human, &mut stage).map(|(output, _)| output)
                },
                rate,
                input.frames,
                factor,
                block_frames,
                wave,
                trace,
            )
        }
    }
}
