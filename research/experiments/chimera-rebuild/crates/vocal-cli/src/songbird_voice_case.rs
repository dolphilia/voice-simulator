use crate::{Destination, network_case::pcm::create_wave, write_json};
use serde::Deserialize;
use serde_json::{Value, json};
use std::error::Error;
use std::fs::File;
use std::io::{self, BufWriter, Write};
use vocal_core::airway::songbird::SongbirdControls;
use vocal_core::songbird_voice::{CONTROL_FRAMES, SongbirdCall, SongbirdFrame, SongbirdVoice};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Case {
    sample_rate_hz: u32,
    frames: usize,
    level: f64,
    controls: SongbirdControls,
    #[serde(default)]
    events: Vec<Event>,
    #[serde(default)]
    observe_call_id: bool,
    #[serde(default)]
    observe_syrinx: bool,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Event {
    frame: usize,
    gate: Option<f64>,
    held_midi: Option<HeldMidi>,
    midi_call: Option<MidiCall>,
    controls: Option<SongbirdControls>,
    play_call: Option<Call>,
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
    id: SongbirdCall,
    note: u8,
    pressed: bool,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Call {
    id: SongbirdCall,
    pitch_hz: Option<f64>,
    amplitude: Option<f64>,
}

impl Event {
    fn is_midi(&self) -> bool {
        self.held_midi.is_some() || self.midi_call.is_some()
    }

    fn apply(&self, voice: &mut SongbirdVoice) -> Result<(), &'static str> {
        if let Some(gate) = self.gate {
            voice.set_gate(gate)?;
        }
        if let Some(controls) = self.controls {
            voice.set_controls(controls)?;
        }
        if let Some(held) = &self.held_midi {
            voice.select_midi_note(held.note)?;
        }
        if let Some(call) = &self.midi_call {
            voice.midi_call(call.id, call.note, call.pressed)?;
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
    if case.frames == 0 {
        return Err("鳴禽の出力フレーム数には1以上が必要です".into());
    }
    let mut voice = SongbirdVoice::new(case.sample_rate_hz, case.controls, case.level)?;
    let mut previous = None;
    for event in &case.events {
        let has_direct_controls = event.gate.is_some()
            || event.controls.is_some()
            || event.play_call.is_some()
            || event.stop_call;
        if event.frame >= case.frames
            || previous.is_some_and(|(frame, midi)| {
                frame > event.frame || (frame == event.frame && !(midi && event.is_midi()))
            })
            || (event.is_midi() == has_direct_controls)
            || (event.held_midi.is_some() && event.midi_call.is_some())
            || (event.stop_call && event.play_call.is_some())
        {
            return Err("鳴禽のイベントは観測範囲内で時刻順に指定してください".into());
        }
        event.apply(&mut voice)?;
        previous = Some((event.frame, event.is_midi()));
    }
    voice.stop_call();
    voice.set_gate(0.0)?;
    voice.set_controls(case.controls)?;
    let factor = voice.factor();
    case.frames
        .checked_mul(factor)
        .ok_or("鳴禽の内部サンプル数が範囲外です")?;
    let (trace, wave, block) = match destination {
        Destination::Inspect => {
            return write_json(
                io::stdout().lock(),
                &json!({
                    "songbird_voice": settings, "internal_rate_hz": u64::from(case.sample_rate_hz) * factor as u64,
                    "decimation_factor": factor, "control_frames": CONTROL_FRAMES, "filter_taps": 24 * factor + 1,
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
        .map(|path| create_wave(path, case.sample_rate_hz, case.frames))
        .transpose()?;
    let mut trace = BufWriter::new(File::create_new(trace)?);
    let observe_call = case.observe_call_id
        || case
            .events
            .iter()
            .any(|event| event.play_call.is_some() || event.stop_call || event.midi_call.is_some());
    write!(
        trace,
        concat!(
            "frame,internal_sample,gate,pitch_hz,interval_semitones,voices,drive,tension,",
            "pressure_kpa,purity,oec_cm3,gape,sac_pressure_dyn_cm2,left_opening,right_opening,",
            "radiation_0,radiation_1,radiation_2,radiation_3,decimated,dc_removed,pcm_f32"
        )
    )?;
    if observe_call {
        write!(
            trace,
            concat!(
                ",control_clock_seconds,active_call,target_pitch_hz,target_interval_semitones,target_voices,",
                "target_drive,target_tension,target_pressure_kpa,target_purity,target_oec_cm3,target_gape,gate_target"
            )
        )?;
    }
    if case.observe_call_id {
        write!(trace, ",call_id")?;
    }
    if case.observe_syrinx {
        write!(
            trace,
            ",left_port_area_cm2,right_port_area_cm2,left_port_flow_cm3_s,right_port_flow_cm3_s"
        )?;
    }
    writeln!(trace)?;
    let mut events = case.events.iter().peekable();
    let block = block.min(case.frames);
    let mut buffer = vec![SongbirdFrame::default(); block];
    let mut frame = 0;
    while frame < case.frames {
        while let Some(event) = events.next_if(|event| event.frame == frame) {
            event.apply(&mut voice)?;
        }
        let end = events.peek().map_or(case.frames, |event| event.frame);
        let active = (end - frame).min(block);
        voice.render(&mut buffer[..active])?;
        for sample in &buffer[..active] {
            if let Some(wave) = &mut wave {
                wave.write_all(&sample.pcm.to_le_bytes())?;
            }
            write!(
                trace,
                "{frame},{},{}",
                (frame + 1) * factor - 1,
                sample.gate
            )?;
            for value in sample
                .controls
                .into_iter()
                .chain([sample.sac_pressure_dyn_cm2])
                .chain(sample.opening)
                .chain(sample.radiation)
                .chain([sample.decimated, sample.dc_removed])
            {
                if !value.is_finite() {
                    return Err(format!("鳴禽のフレーム {frame} に非有限な状態があります").into());
                }
                write!(trace, ",{value}")?;
            }
            write!(trace, ",{}", sample.pcm)?;
            if observe_call {
                write!(
                    trace,
                    ",{},{}",
                    sample.control_clock_seconds,
                    u8::from(sample.active_call)
                )?;
                for value in sample.targets.into_iter().chain([sample.gate_target]) {
                    write!(trace, ",{value}")?;
                }
            }
            if case.observe_call_id {
                write!(trace, ",{}", sample.call_id)?;
            }
            if case.observe_syrinx {
                for value in sample
                    .port_area_cm2
                    .into_iter()
                    .chain(sample.port_flow_cm3_s)
                {
                    if !value.is_finite() {
                        return Err(
                            format!("鳴禽のフレーム {frame} に非有限な鳴管状態があります").into(),
                        );
                    }
                    write!(trace, ",{value}")?;
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
