use crate::{Destination, write_json};
use serde::Deserialize;
use serde_json::{Value, json};
use std::error::Error;
use std::fs::File;
use std::io::{self, BufWriter, Write};
use vocal_core::lip_reed::{LipReed, LipReedParameters};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Case {
    sample_rate_hz: u32,
    frames: usize,
    parameters: LipReedParameters,
    pressure_steps: Vec<PressureStep>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PressureStep {
    frame: usize,
    dyn_cm2: f64,
}

pub fn run(settings: &Value, destination: Destination<'_>) -> Result<(), Box<dyn Error>> {
    let case: Case = serde_json::from_value(settings.clone())?;
    if case.frames == 0
        || case
            .pressure_steps
            .windows(2)
            .any(|pair| pair[0].frame >= pair[1].frame)
        || case
            .pressure_steps
            .iter()
            .any(|step| step.frame >= case.frames || !step.dyn_cm2.is_finite())
    {
        return Err("圧力の変更は描画範囲内で時刻順に指定してください".into());
    }
    let mut reed = LipReed::new(case.sample_rate_hz, case.parameters)?;
    let path = match destination {
        Destination::Inspect => {
            return write_json(
                io::stdout().lock(),
                &json!({
                    "lip_reed": settings,
                    "internal_rate_hz": case.sample_rate_hz,
                    "rows": case.frames,
                }),
            );
        }
        Destination::Trace(path) => path,
        Destination::Pcm { .. } => {
            return Err("差圧に対する弁単体の応答は render でCSVに出力できます".into());
        }
    };
    let mut trace = BufWriter::new(File::create_new(path)?);
    writeln!(
        trace,
        "frame,drive_dyn_cm2,height_cm,speed_cm_s,opening_cm2"
    )?;
    let mut pressure_steps = case.pressure_steps.iter().peekable();
    let mut drive = 0.0;
    for frame in 0..case.frames {
        if let Some(step) = pressure_steps.next_if(|step| step.frame == frame) {
            drive = step.dyn_cm2;
        }
        let state = reed.step(drive);
        writeln!(
            trace,
            "{frame},{drive},{},{},{}",
            state.height_cm, state.speed_cm_s, state.opening_cm2
        )?;
    }
    trace.flush()?;
    Ok(())
}
