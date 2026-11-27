use crate::{Destination, network_case::pcm::create_wave, write_json};
use serde::Deserialize;
use serde_json::{Value, json};
use std::error::Error;
use std::fs::File;
use std::io::{self, BufWriter, Write};
use vocal_core::airway::elephant::{
    CONTROL_FRAMES, ElephantCall, ElephantFrame, ElephantParams, ElephantShape, ElephantVoice,
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Case {
    sample_rate_hz: u32,
    frames: usize,
    shape: ElephantShape,
    level: f64,
    events: Vec<Event>,
    #[serde(default)]
    observe_call: bool,
    #[serde(default)]
    observe_valve: bool,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Event {
    frame: usize,
    gate: Option<f64>,
    held_midi: Option<HeldMidi>,
    midi_call: Option<MidiCall>,
    params: Option<ElephantParams>,
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
    id: ElephantCall,
    note: u8,
    pressed: bool,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Call {
    id: ElephantCall,
    pitch_hz: Option<f64>,
    amplitude: Option<f64>,
}

impl Event {
    fn is_midi(&self) -> bool {
        self.held_midi.is_some() || self.midi_call.is_some()
    }

    fn apply(&self, voice: &mut ElephantVoice) -> Result<(), &'static str> {
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
    if case.frames == 0
        || case.events.windows(2).any(|pair| {
            pair[0].frame > pair[1].frame
                || (pair[0].frame == pair[1].frame && !(pair[0].is_midi() && pair[1].is_midi()))
        })
        || case.events.iter().any(|event| {
            let direct = event.gate.is_some()
                || event.params.is_some()
                || event.play_call.is_some()
                || event.stop_call;
            event.frame >= case.frames
                || event.gate.is_some_and(|gate| !(0.0..=1.5).contains(&gate))
                || (event.play_call.is_some() && event.stop_call)
                || event.is_midi() == direct
                || (event.held_midi.is_some() && event.midi_call.is_some())
                || event.midi_call.as_ref().is_some_and(|call| call.note > 127)
                || event
                    .held_midi
                    .as_ref()
                    .and_then(|held| held.note)
                    .is_some_and(|note| note > 127)
        })
    {
        return Err("ゾウの手動目標・MIDI・コールの内容と時刻順を確認してください".into());
    }
    let mut voice = ElephantVoice::new(case.sample_rate_hz, case.shape, case.level)?;
    let (trace, wave, block) = match destination {
        Destination::Inspect => {
            return write_json(
                io::stdout().lock(),
                &json!({
                    "elephant_voice": settings,
                    "internal_rate_hz": case.sample_rate_hz,
                    "decimation_factor": 1,
                    "control_frames": CONTROL_FRAMES,
                    "rows": case.frames,
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
            "frame,gate,pitch_hz,pressure_cm_h2o,trunk,chaos,",
            "lung_pressure_dyn_cm2,lung_flow_cm3_s,trachea_end_pressure_dyn_cm2,pharynx_pressure_dyn_cm2,",
            "glottis_drive_dyn_cm2,glottis_area_cm2,glottis_flow_cm3_s,glottis_phase,glottis_f0_hz,",
            "oral_tip_area_cm2,velum_area_cm2,velum_flow_cm3_s,nasal_base_pressure_dyn_cm2,",
            "trunk_inlet_pressure_dyn_cm2,trunk_tip_pressure_dyn_cm2,trunk_valve_area_cm2,trunk_valve_flow_cm3_s,",
            "wall_cm3_s,oral_cm3_s,nasal_cm3_s,radiation_cm3_s2,decimated,dc_removed,pcm_f32"
        )
    )?;
    if case.observe_call {
        write!(
            trace,
            concat!(
                ",call_id,control_clock_seconds,target_pitch_hz,target_pressure_cm_h2o,",
                "target_trunk,target_chaos,gate_goal"
            )
        )?;
    }
    if case.observe_valve {
        write!(
            trace,
            concat!(
                ",mode,lip_pitch_hz,target_mode,target_lip_pitch_hz,glottis_abduction_cm2,",
                "glottis_amplitude_cm2,glottal_noise_gain,reed_drive_dyn_cm2,reed_opening_cm2,reed_height_cm,reed_speed_cm_s"
            )
        )?;
    }
    writeln!(trace)?;
    let mut frames = vec![ElephantFrame::default(); block.min(case.frames)];
    let mut events = case.events.iter().peekable();
    let mut start = 0;
    while start < case.frames {
        while let Some(event) = events.next_if(|event| event.frame == start) {
            event.apply(&mut voice)?;
        }
        let next = events.peek().map_or(case.frames, |event| event.frame);
        let count = frames.len().min(next - start);
        voice.render(&mut frames[..count])?;
        for (offset, frame) in frames[..count].iter().enumerate() {
            write_row(
                &mut trace,
                start + offset,
                frame,
                case.observe_call,
                case.observe_valve,
            )?;
            if let Some(wave) = &mut wave {
                wave.write_all(&frame.output.pcm.to_le_bytes())?;
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

fn write_row(
    trace: &mut impl Write,
    index: usize,
    frame: &ElephantFrame,
    observe_call: bool,
    observe_valve: bool,
) -> io::Result<()> {
    let s = frame.airway;
    let t = frame.trunk;
    let p = frame.current;
    write!(trace, "{index}")?;
    for value in [
        frame.gate,
        p.pitch_hz,
        p.pressure_cm_h2o,
        p.trunk,
        p.chaos,
        s.lung_pressure_dyn_cm2,
        s.lung_flow_cm3_s,
        s.trachea_end_pressure_dyn_cm2,
        s.pharynx_pressure_dyn_cm2,
        s.glottis_drive_dyn_cm2,
        s.glottis_area_cm2,
        s.glottis_flow_cm3_s,
        s.glottis_phase,
        s.glottis_f0_hz,
        s.oral_tip_area_cm2,
        s.velum_area_cm2,
        s.velum_flow_cm3_s,
        t.nasal_base_pressure_dyn_cm2,
        t.trunk_inlet_pressure_dyn_cm2,
        t.trunk_tip_pressure_dyn_cm2,
        t.trunk_valve_area_cm2,
        t.trunk_valve_flow_cm3_s,
        s.wall_radiation_cm3_s,
        s.oral_radiation_cm3_s,
        s.nasal_radiation_cm3_s,
        s.radiation_derivative_cm3_s2,
        frame.output.decimated,
        frame.output.dc_removed,
    ] {
        write!(trace, ",{value}")?;
    }
    write!(trace, ",{}", frame.output.pcm)?;
    if observe_call {
        let target = frame.target;
        write!(
            trace,
            ",{},{},{},{},{},{},{}",
            frame.call_id,
            frame.control_clock_seconds,
            target.pitch_hz,
            target.pressure_cm_h2o,
            target.trunk,
            target.chaos,
            frame.gate_goal
        )?;
    }
    if observe_valve {
        write!(
            trace,
            ",{},{},{},{},{},{},{},{},{},{},{}",
            p.mode,
            p.lip_pitch_hz,
            frame.target.mode,
            frame.target.lip_pitch_hz,
            p.glottis_abduction_cm2(),
            p.glottis_amplitude_cm2(),
            p.glottal_noise_gain(),
            frame.reed_drive_dyn_cm2,
            frame.reed.opening_cm2,
            frame.reed.height_cm,
            frame.reed.speed_cm_s
        )?;
    }
    writeln!(trace)
}
