//! 上流のレンダーが更新した肺の固定圧力節点を読む。

use chimera::creatures::{CreatureVoice, seal};
use serde_json::Value;
use std::env;
use std::error::Error;
use std::fs;
use std::io::{self, BufWriter, Write};

fn parameters(input: &Value, indices: [usize; 4]) -> [(usize, f64); 4] {
    let keys = ["pulse_rate_hz", "pulse_depth", "duty", "pressure_cm_h2o"];
    std::array::from_fn(|i| (indices[i], input[keys[i]].as_f64().expect("比較用の制御値")))
}

fn main() -> Result<(), Box<dyn Error>> {
    let input = env::args().nth(1).ok_or("比較ケースが必要です")?;
    let case: Value = serde_json::from_str(&fs::read_to_string(input)?)?;
    let source = &case["seal_breath"];
    let def = Box::leak(Box::new(seal::def()));
    let indices =
        ["pulseRate", "pulse", "duty", "pressure"].map(|key| def.param_index(key).unwrap());
    let mut voice = CreatureVoice::new(
        def,
        source["sample_rate_hz"].as_f64().unwrap(),
        &parameters(&source["controls"], indices),
    );
    let net = voice.sim.net().ok_or("アザラシの気道がありません")?;
    let tube = net
        .tube_names
        .iter()
        .position(|name| name == "lungs")
        .ok_or("固定肺圧の節点がありません")?;
    let lung = net.tubes[tube].first_node();
    let mut events = source["events"].as_array().unwrap().iter().peekable();
    let mut out = BufWriter::new(io::stdout().lock());
    writeln!(
        out,
        "control,frame,gate,pulse_rate_hz,pulse_depth,duty,pressure_cm_h2o,lung_pressure_dyn_cm2"
    )?;
    for frame in 0..source["frames"].as_u64().unwrap() {
        if let Some(event) = events.next_if(|event| event["frame"].as_u64() == Some(frame)) {
            if let Some(controls) = event.get("controls") {
                voice.set_params(&parameters(controls, indices));
            }
            if let Some(gate) = event["gate"].as_f64() {
                voice.set_gate(gate);
            }
        }
        voice.render(&mut [0.0]);
        if frame % 64 == 0 {
            let control = frame / 64;
            let [rate, depth, duty, pressure] = indices.map(|index| voice.values()[index]);
            let gate = voice.gate;
            let lung_pressure = voice.sim.net().unwrap().p[lung];
            writeln!(
                out,
                "{control},{frame},{gate},{rate},{depth},{duty},{pressure},{lung_pressure}"
            )?;
        }
    }
    out.flush()?;
    Ok(())
}
