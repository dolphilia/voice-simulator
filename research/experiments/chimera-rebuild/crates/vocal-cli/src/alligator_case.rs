use crate::{Destination, network_case::pcm::create_wave, write_json};
use serde::Deserialize;
use serde_json::{Value, json};
use std::error::Error;
use std::fs::File;
use std::io::{self, BufWriter, Write};
use vocal_core::airway::alligator::{
    AlligatorCall, AlligatorFrame, AlligatorParams, AlligatorShape, AlligatorVoice, CONTROL_FRAMES,
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Case {
    sample_rate_hz: u32,
    frames: usize,
    shape: AlligatorShape,
    level: f64,
    events: Vec<Event>,
    #[serde(default)]
    observe_call: bool,
    #[serde(default)]
    observe_noise: bool,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Event {
    frame: usize,
    gate: Option<f64>,
    held_midi: Option<HeldMidi>,
    midi_call: Option<MidiCall>,
    params: Option<AlligatorParams>,
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
    id: AlligatorCall,
    note: u8,
    pressed: bool,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Call {
    id: AlligatorCall,
    pitch_hz: Option<f64>,
    amplitude: Option<f64>,
}

impl Event {
    fn apply(&self, voice: &mut AlligatorVoice) -> Result<(), &'static str> {
        if let Some(held) = &self.held_midi {
            voice.select_midi_note(held.note)?;
        }
        if let Some(call) = &self.midi_call {
            voice.midi_call(call.id, call.note, call.pressed)?;
        }
        if let Some(params) = self.params {
            voice.set_params(params)?;
        }
        if let Some(gate) = self.gate {
            voice.set_gate(gate)?;
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
    let mut previous = None;
    for event in &case.events {
        let midi = event.held_midi.is_some() || event.midi_call.is_some();
        let direct = event.gate.is_some()
            || event.params.is_some()
            || event.play_call.is_some()
            || event.stop_call;
        if event.frame >= case.frames
            || previous.is_some_and(|(frame, last_midi)| {
                event.frame < frame || (event.frame == frame && !(last_midi && midi))
            })
            || event.gate.is_some_and(|gate| !(0.0..=1.5).contains(&gate))
            || (event.play_call.is_some() && event.stop_call)
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
                "アリゲーターの手動目標・MIDI・コールの内容と時刻順を確認してください".into(),
            );
        }
        previous = Some((event.frame, midi));
    }
    let mut voice = AlligatorVoice::new(case.sample_rate_hz, case.shape, case.level)?;
    let factor = voice.factor();
    let rows = case
        .frames
        .checked_mul(factor)
        .filter(|&rows| rows > 0)
        .ok_or("アリゲーターの内部サンプル数を確認してください")?;
    let (trace, wave, block) = match destination {
        Destination::Inspect => {
            return write_json(
                io::stdout().lock(),
                &json!({
                    "alligator_voice": settings,
                    "internal_rate_hz": u64::from(case.sample_rate_hz) * factor as u64,
                    "decimation_factor": factor,
                    "control_frames": CONTROL_FRAMES,
                    "rows": rows,
                    "geometry": voice.geometry(),
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
    write!(
        trace,
        concat!(
            "sample,frame,gate,lung_pressure_dyn_cm2,lung_flow_cm3_s,trachea_inlet_pressure_dyn_cm2,",
            "trachea_end_pressure_dyn_cm2,pharynx_pressure_dyn_cm2,glottis_drive_dyn_cm2,",
            "glottis_area_cm2,glottis_flow_cm3_s,glottis_voicing,glottis_phase,glottis_f0_hz,",
            "velum_area_cm2,velum_flow_cm3_s,wall_cm3_s,oral_cm3_s,nasal_cm3_s,radiation_cm3_s2,",
            "decimated,dc_removed,pcm_f32"
        )
    )?;
    if case.observe_call {
        write!(
            trace,
            concat!(
                ",call_id,control_clock_seconds,gate_target,oral_tip_area_cm2,oral_noise,",
                "pitch_hz,chaos,pressure_cm_h2o,mouth,nostrils,hiss,",
                "target_pitch_hz,target_chaos,target_pressure_cm_h2o,target_mouth,target_nostrils,target_hiss"
            )
        )?;
    }
    if case.observe_noise {
        write!(
            trace,
            ",glottal_noise_level_dyn_cm2,glottal_noise_pressure_dyn_cm2,oral_noise_level_dyn_cm2"
        )?;
    }
    writeln!(trace)?;
    let mut frames = vec![AlligatorFrame::default(); block.min(case.frames)];
    let mut events = case.events.iter().peekable();
    let mut start = 0;
    while start < case.frames {
        while let Some(event) = events.next_if(|event| event.frame == start) {
            event.apply(&mut voice)?;
        }
        let next_event = events.peek().map_or(case.frames, |event| event.frame);
        let count = frames.len().min(next_event - start);
        voice.render(&mut frames[..count])?;
        for (offset, record) in frames[..count].iter().enumerate() {
            let frame = start + offset;
            for (sub, s) in record.internal[..factor].iter().enumerate() {
                let sample = frame * factor + sub;
                let pcm = if sub + 1 == factor {
                    record.output
                } else {
                    Default::default()
                };
                write!(trace, "{sample},{frame},{}", record.gate)?;
                for value in [
                    s.lung_pressure_dyn_cm2,
                    s.lung_flow_cm3_s,
                    s.trachea_inlet_pressure_dyn_cm2,
                    s.trachea_end_pressure_dyn_cm2,
                    s.pharynx_pressure_dyn_cm2,
                    s.glottis_drive_dyn_cm2,
                    s.glottis_area_cm2,
                    s.glottis_flow_cm3_s,
                    s.glottis_voicing,
                    s.glottis_phase,
                    s.glottis_f0_hz,
                    s.velum_area_cm2,
                    s.velum_flow_cm3_s,
                    s.wall_radiation_cm3_s,
                    s.oral_radiation_cm3_s,
                    s.nasal_radiation_cm3_s,
                    s.radiation_derivative_cm3_s2,
                    pcm.decimated,
                    pcm.dc_removed,
                ] {
                    write!(trace, ",{value}")?;
                }
                write!(trace, ",{}", pcm.pcm)?;
                if case.observe_call {
                    let c = record.control;
                    write!(
                        trace,
                        ",{},{},{},{},{}",
                        c.call_id,
                        c.clock_seconds,
                        c.gate_target,
                        s.oral_tip_area_cm2,
                        u8::from(c.oral_noise)
                    )?;
                    for value in c.current.values().into_iter().chain(c.target.values()) {
                        write!(trace, ",{value}")?;
                    }
                }
                if case.observe_noise {
                    write!(
                        trace,
                        ",{},{},{}",
                        s.glottal_noise_level_dyn_cm2,
                        s.glottal_noise_pressure_dyn_cm2,
                        s.oral_noise_level_dyn_cm2
                    )?;
                }
                writeln!(trace)?;
            }
            if let Some(wave) = &mut wave {
                wave.write_all(&record.output.pcm.to_le_bytes())?;
            }
        }
        start += count;
    }
    trace.flush()?;
    if let Some(wave) = &mut wave {
        wave.flush()?;
    }
    Ok(())
}
