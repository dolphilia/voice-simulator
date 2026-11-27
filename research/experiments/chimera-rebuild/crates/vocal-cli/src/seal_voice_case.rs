use crate::seal_breath_case::SealBreathCase;
use crate::{Destination, network_case::pcm::create_wave, write_json};
use serde::Deserialize;
use serde_json::{Value, json};
use std::error::Error;
use std::fs::File;
use std::io::{self, BufWriter, Write};
use vocal_core::airway::seal::SealShape;
use vocal_core::seal_breath::CONTROL_FRAMES;
use vocal_core::seal_voice::{SealCall, SealFrame, SealVoice};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Case {
    breath: SealBreathCase,
    shape: SealShape,
    level: f64,
    #[serde(default)]
    events: Vec<CallEvent>,
    #[serde(default)]
    observe_call_id: bool,
    #[serde(default)]
    observe_glottis: bool,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CallEvent {
    frame: usize,
    held_midi: Option<HeldMidi>,
    midi_call: Option<MidiCall>,
    pitch_hz: Option<f64>,
    roughness: Option<f64>,
    play_call: Option<PlayCall>,
    #[serde(default)]
    stop_call: bool,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct HeldMidi {
    note: Option<u8>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct MidiCall {
    id: SealCall,
    note: u8,
    pressed: bool,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PlayCall {
    id: SealCall,
    pitch_hz: Option<f64>,
    amplitude: Option<f64>,
}

impl CallEvent {
    fn apply(&self, voice: &mut SealVoice) -> Result<(), &'static str> {
        if let Some(held) = &self.held_midi {
            voice.select_midi_note(held.note)?;
        }
        if let Some(call) = &self.midi_call {
            voice.midi_call(call.id, call.note, call.pressed)?;
        }
        if let Some(pitch) = self.pitch_hz {
            voice.set_pitch(pitch)?;
        }
        if let Some(roughness) = self.roughness {
            voice.set_roughness(roughness)?;
        }
        if let Some(call) = &self.play_call {
            voice.play_call(call.id, call.pitch_hz, call.amplitude.unwrap_or(1.0))?;
        }
        if self.stop_call {
            voice.stop_call();
        }
        Ok(())
    }
}

pub fn run(settings: &Value, destination: Destination<'_>) -> Result<(), Box<dyn Error>> {
    let case: Case = serde_json::from_value(settings.clone())?;
    let input = &case.breath;
    let mut previous = None;
    for event in &case.events {
        let midi = event.held_midi.is_some() || event.midi_call.is_some();
        let direct = event.pitch_hz.is_some()
            || event.roughness.is_some()
            || event.play_call.is_some()
            || event.stop_call;
        if event.frame >= input.frames
            || previous.is_some_and(|(frame, last_midi)| {
                frame > event.frame || (frame == event.frame && !(last_midi && midi))
            })
            || (event.stop_call && event.play_call.is_some())
            || midi == direct
            || (event.held_midi.is_some() && event.midi_call.is_some())
            || event.midi_call.as_ref().is_some_and(|call| call.note > 127)
            || event
                .held_midi
                .as_ref()
                .and_then(|held| held.note)
                .is_some_and(|note| note > 127)
        {
            return Err(
                "アザラシのコールと音高のイベントは観測範囲内で時刻順に指定してください".into(),
            );
        }
        previous = Some((event.frame, midi));
    }
    let mut voice = SealVoice::new(input.prepare()?, case.shape, case.level)?;
    let factor = voice.factor();
    input
        .frames
        .checked_mul(factor)
        .ok_or("アザラシの内部サンプル数が処理可能範囲を超えています")?;
    let (trace, wave, block) = match destination {
        Destination::Inspect => {
            return write_json(
                io::stdout().lock(),
                &json!({
                    "seal_voice": settings,
                    "internal_rate_hz": u64::from(input.sample_rate_hz) * factor as u64,
                    "decimation_factor": factor,
                    "control_frames": CONTROL_FRAMES,
                    "filter_taps": if factor == 1 { 1 } else { 24 * factor + 1 },
                }),
            );
        }
        Destination::Trace(path) => (path, None, 128),
        Destination::Pcm {
            wave,
            trace,
            block_frames,
        } => (
            trace.ok_or("このケースのPCM出力には計測CSVのパスが必要です")?,
            Some(wave),
            block_frames,
        ),
    };
    if block == 0 {
        return Err("ブロックのフレーム数には正の値を指定してください".into());
    }
    let mut wave = wave
        .map(|path| create_wave(path, input.sample_rate_hz, input.frames))
        .transpose()?;
    let mut trace = BufWriter::new(File::create_new(trace)?);
    write!(
        trace,
        concat!(
            "frame,internal_sample,gate_target,gate,lung_pressure_dyn_cm2,",
            "wall_0,oral_0,nasal_0,radiation_0,wall_1,oral_1,nasal_1,radiation_1,",
            "decimated,dc_removed,pcm_f32"
        )
    )?;
    let observe_call = case.observe_call_id || !case.events.is_empty();
    if observe_call {
        write!(
            trace,
            concat!(
                ",active_call,control_clock_seconds,pitch_hz,target_pitch_hz,",
                "pulse_rate_hz,pulse_depth,duty,pressure_cm_h2o,",
                "target_pulse_rate_hz,target_pulse_depth,target_duty,target_pressure_cm_h2o,pulse_phase"
            )
        )?;
    }
    if case.observe_call_id {
        write!(trace, ",call_id")?;
    }
    if case.observe_glottis {
        write!(
            trace,
            ",roughness,target_roughness,glottis_phase_0,glottis_f0_hz_0,glottis_area_cm2_0,glottis_phase_1,glottis_f0_hz_1,glottis_area_cm2_1"
        )?;
    }
    writeln!(trace)?;
    let mut events = input.events.iter().peekable();
    let mut call_events = case.events.iter().peekable();
    let mut buffer = vec![SealFrame::default(); block.min(input.frames)];
    let mut frame = 0;
    while frame < input.frames {
        if let Some(event) = events.next_if(|event| event.frame == frame) {
            if let Some(controls) = event.controls {
                voice.set_breath_controls(controls)?;
            }
            if let Some(gate) = event.gate {
                voice.set_gate(gate)?;
            }
        }
        while let Some(event) = call_events.next_if(|event| event.frame == frame) {
            event.apply(&mut voice)?;
        }
        let end = events
            .peek()
            .map_or(input.frames, |event| event.frame)
            .min(call_events.peek().map_or(input.frames, |event| event.frame));
        let count = (end - frame).min(buffer.len());
        voice.render(&mut buffer[..count])?;
        for sample in &buffer[..count] {
            if let Some(wave) = &mut wave {
                wave.write_all(&sample.pcm.to_le_bytes())?;
            }
            write!(
                trace,
                "{frame},{},{},{},{}",
                (frame + 1) * factor - 1,
                sample.gate_target,
                sample.gate,
                sample.lung_pressure_dyn_cm2
            )?;
            for r in sample.radiation {
                write!(
                    trace,
                    ",{},{},{},{}",
                    r.wall_cm3_s, r.oral_cm3_s, r.nasal_cm3_s, r.total_derivative_cm3_s2
                )?;
            }
            write!(
                trace,
                ",{},{},{}",
                sample.decimated, sample.dc_removed, sample.pcm
            )?;
            if observe_call {
                let call = sample.call;
                write!(
                    trace,
                    ",{},{},{},{}",
                    u8::from(call.active),
                    call.clock_seconds,
                    call.pitch_hz,
                    call.pitch_target_hz,
                )?;
                for value in call.breath.into_iter().chain(call.breath_targets) {
                    write!(trace, ",{value}")?;
                }
                write!(trace, ",{}", call.pulse_phase)?;
            }
            if case.observe_call_id {
                write!(trace, ",{}", sample.call.id)?;
            }
            if case.observe_glottis {
                write!(
                    trace,
                    ",{},{}",
                    sample.call.roughness, sample.call.target_roughness
                )?;
                for g in sample.glottis {
                    write!(trace, ",{},{},{}", g.phase, g.f0_hz, g.area_cm2)?;
                }
            }
            writeln!(trace)?;
            frame += 1;
        }
    }
    if let Some(wave) = &mut wave {
        wave.flush()?;
    }
    trace.flush()?;
    Ok(())
}
