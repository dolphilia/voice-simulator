use crate::seal_breath_case::SealBreathCase;
use crate::{Destination, write_json};
use serde::Deserialize;
use serde_json::{Value, json};
use std::error::Error;
use std::fs::File;
use std::io::{self, BufWriter, Write};
use vocal_core::airway::seal::{SealAirway, SealShape};
use vocal_core::seal_breath::CONTROL_FRAMES;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Case {
    breath: SealBreathCase,
    shape: SealShape,
}

pub fn run(settings: &Value, destination: Destination<'_>) -> Result<(), Box<dyn Error>> {
    let case: Case = serde_json::from_value(settings.clone())?;
    let input = &case.breath;
    let mut breath = input.prepare()?;
    let oversample = if input.sample_rate_hz <= 60_000 { 2 } else { 1 };
    let rate = input.sample_rate_hz * oversample;
    let factor = oversample as usize;
    let rows = input
        .frames
        .checked_mul(factor)
        .ok_or("アザラシの内部サンプル数が処理可能範囲を超えています")?;
    let mut airway = SealAirway::new(rate, case.shape)?;
    let path = match destination {
        Destination::Inspect => {
            return write_json(
                io::stdout().lock(),
                &json!({
                    "seal_airway": settings,
                    "internal_rate_hz": rate,
                    "oversample": oversample,
                    "rows": rows,
                    "geometry": airway.geometry(),
                }),
            );
        }
        Destination::Trace(path) => path,
        Destination::Pcm { .. } => {
            return Err("アザラシの気道の内部系列には render を使います".into());
        }
    };
    let mut out = BufWriter::new(File::create_new(path)?);
    writeln!(
        out,
        concat!(
            "sample,lung_pressure_dyn_cm2,lung_flow_cm3_s,trachea_inlet_pressure_dyn_cm2,",
            "trachea_end_pressure_dyn_cm2,pharynx_pressure_dyn_cm2,glottis_drive_dyn_cm2,",
            "glottis_area_cm2,glottis_flow_cm3_s,glottis_voicing,glottis_f0_hz,velum_flow_cm3_s,",
            "nasal_radiation_cm3_s,radiation_derivative_cm3_s2"
        )
    )?;
    let mut events = input.events.iter().peekable();
    for frame in 0..input.frames {
        if frame % CONTROL_FRAMES == 0 {
            while let Some(event) = events.next_if(|event| event.frame <= frame) {
                event.apply(&mut breath)?;
            }
            airway.set_lung_pressure(breath.step().lung_pressure_dyn_cm2)?;
        }
        for subframe in 0..factor {
            let s = airway.step()?;
            let sample = frame * factor + subframe;
            writeln!(
                out,
                "{sample},{},{},{},{},{},{},{},{},{},{},{},{},{}",
                s.lung_pressure_dyn_cm2,
                s.lung_flow_cm3_s,
                s.trachea_inlet_pressure_dyn_cm2,
                s.trachea_end_pressure_dyn_cm2,
                s.pharynx_pressure_dyn_cm2,
                s.glottis_drive_dyn_cm2,
                s.glottis_area_cm2,
                s.glottis_flow_cm3_s,
                s.glottis_voicing,
                s.glottis_f0_hz,
                s.velum_flow_cm3_s,
                s.nasal_radiation_cm3_s,
                s.radiation_derivative_cm3_s2
            )?;
        }
    }
    out.flush()?;
    Ok(())
}
