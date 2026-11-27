use crate::{Destination, write_json};
use serde::Deserialize;
use serde_json::{Value, json};
use std::error::Error;
use std::fs::File;
use std::io::{self, BufWriter, Write};
use vocal_core::syrinx::{SyrinxControls, SyrinxLabia};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Case {
    sample_rate_hz: u32,
    sample_count: usize,
    seed: f64,
    controls: SyrinxControls,
    #[serde(default)]
    events: Vec<ControlEvent>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ControlEvent {
    sample: usize,
    controls: SyrinxControls,
}

pub fn run(settings: &Value, destination: Destination<'_>) -> Result<(), Box<dyn Error>> {
    let case: Case = serde_json::from_value(settings.clone())?;
    let mut source = SyrinxLabia::new(case.sample_rate_hz, case.seed, case.controls)?;
    let initial_tuning = source.tuning();
    let mut last_sample = 0;
    let mut event_tunings = Vec::with_capacity(case.events.len());
    for event in &case.events {
        if event.sample <= last_sample || event.sample >= case.sample_count {
            return Err("鳴管の制御イベントは初期サンプルの後に昇順で置いてください".into());
        }
        source.set_controls(event.controls)?;
        event_tunings.push(json!({"sample": event.sample, "tuning": source.tuning()}));
        last_sample = event.sample;
    }
    if case.sample_count == 0 {
        return Err("鳴管ケースの観測サンプル数には1以上が必要です".into());
    }
    let path = match destination {
        Destination::Inspect => {
            return write_json(
                io::stdout().lock(),
                &json!({
                    "syrinx_labia": settings,
                    "initial_tuning": initial_tuning,
                    "event_tunings": event_tunings,
                }),
            );
        }
        Destination::Trace(path) => path,
        Destination::Pcm { .. } => {
            return Err("鳴管単体の開口率を保存するには render を使ってください".into());
        }
    };
    source.set_controls(case.controls)?;
    let mut output = BufWriter::new(File::create_new(path)?);
    let mut events = case.events.iter().peekable();
    writeln!(
        output,
        "sample,displacement,velocity_tau,gate_smoothed,opening"
    )?;
    for sample in 0..case.sample_count {
        if let Some(event) = events.next_if(|event| event.sample == sample) {
            source.set_controls(event.controls)?;
        }
        let state = source.step();
        let values = [
            state.displacement,
            state.velocity_tau,
            state.gate_smoothed,
            state.opening,
        ];
        if !values.into_iter().all(f64::is_finite) {
            return Err(format!("鳴管のサンプル {sample} に非有限値があります").into());
        }
        let [x, y, gate, opening] = values;
        writeln!(output, "{sample},{x},{y},{gate},{opening}")?;
    }
    output.flush()?;
    Ok(())
}
