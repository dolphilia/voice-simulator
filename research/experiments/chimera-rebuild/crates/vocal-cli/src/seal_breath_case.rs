use crate::{Destination, write_json};
use serde::Deserialize;
use serde_json::{Value, json};
use std::error::Error;
use std::fs::File;
use std::io::{self, BufWriter, Write};
use vocal_core::seal_breath::{CONTROL_FRAMES, SealBreath, SealBreathControls};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct SealBreathCase {
    pub(crate) sample_rate_hz: u32,
    pub(crate) frames: usize,
    controls: SealBreathControls,
    #[serde(default)]
    pub(crate) events: Vec<Event>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Event {
    pub(crate) frame: usize,
    pub(crate) controls: Option<SealBreathControls>,
    pub(crate) gate: Option<f64>,
}

impl Event {
    pub(crate) fn apply(&self, breath: &mut SealBreath) -> Result<(), &'static str> {
        if let Some(controls) = self.controls {
            breath.set_controls(controls)?;
        }
        if let Some(gate) = self.gate {
            breath.set_gate(gate)?;
        }
        Ok(())
    }
}

impl SealBreathCase {
    pub(crate) fn prepare(&self) -> Result<SealBreath, &'static str> {
        if self.frames == 0 {
            return Err("呼気パルスの観測フレーム数には1以上が必要です");
        }
        let mut breath = SealBreath::new(self.sample_rate_hz, self.controls)?;
        let mut previous = None;
        for event in &self.events {
            if event.frame >= self.frames
                || previous.is_some_and(|frame| frame >= event.frame)
                || (event.controls.is_none() && event.gate.is_none())
            {
                return Err("呼気パルスのイベントは観測範囲内で時刻順に指定してください");
            }
            event.apply(&mut breath)?;
            previous = Some(event.frame);
        }
        breath.set_controls(self.controls)?;
        breath.set_gate(0.0)?;
        Ok(breath)
    }
}

pub fn run(settings: &Value, destination: Destination<'_>) -> Result<(), Box<dyn Error>> {
    let case: SealBreathCase = serde_json::from_value(settings.clone())?;
    let mut breath = case.prepare()?;
    let path = match destination {
        Destination::Inspect => {
            return write_json(
                io::stdout().lock(),
                &json!({
                    "seal_breath": settings,
                    "control_frames": CONTROL_FRAMES,
                    "control_seconds": CONTROL_FRAMES as f64 / f64::from(case.sample_rate_hz),
                    "initial_phase": breath.phase(),
                    "rows": case.frames.div_ceil(CONTROL_FRAMES),
                }),
            );
        }
        Destination::Trace(path) => path,
        Destination::Pcm { .. } => {
            return Err("アザラシの呼気パルスは render で制御の観測値を保存できます".into());
        }
    };
    let mut output = BufWriter::new(File::create_new(path)?);
    writeln!(
        output,
        concat!(
            "control,frame,phase,half_sine,pulse_gain,gate_target,gate,pulse_rate_hz,pulse_depth,",
            "duty,pressure_cm_h2o,base_pressure_dyn_cm2,lung_pressure_dyn_cm2"
        )
    )?;
    let mut events = case.events.iter().peekable();
    let frames = (0..case.frames).step_by(CONTROL_FRAMES);
    for (control, frame) in frames.enumerate() {
        while let Some(event) = events.next_if(|event| event.frame <= frame) {
            event.apply(&mut breath)?;
        }
        let row = breath.step();
        let p = row.controls;
        writeln!(
            output,
            "{control},{frame},{},{},{},{},{},{},{},{},{},{},{}",
            row.phase,
            row.half_sine,
            row.pulse_gain,
            row.gate_target,
            row.gate,
            p.pulse_rate_hz,
            p.pulse_depth,
            p.duty,
            p.pressure_cm_h2o,
            row.base_pressure_dyn_cm2,
            row.lung_pressure_dyn_cm2
        )?;
    }
    output.flush()?;
    Ok(())
}
