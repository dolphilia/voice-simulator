//! 固定上流が返したPCMと、同じ実行の間引き前の放射を取る。

use chimera::airway::network::{AirwayNetwork, Tube};
use chimera::creatures::{CreatureDef, CreatureSim, CreatureVoice, seal};
use chimera::sources::glottis::ParametricGlottis;
use serde_json::Value;
use std::env;
use std::error::Error;
use std::fs;
use std::io::{self, BufWriter, Write};
use std::sync::{Arc, Mutex};

fn params(def: &CreatureDef, input: &Value, keys: &[(&str, &str)]) -> Vec<(usize, f64)> {
    keys.iter()
        .map(|&(upper, name)| {
            (
                def.param_index(upper).unwrap(),
                input[name].as_f64().unwrap(),
            )
        })
        .collect()
}

const BREATH_KEYS: [(&str, &str); 4] = [
    ("pulseRate", "pulse_rate_hz"),
    ("pulse", "pulse_depth"),
    ("duty", "duty"),
    ("pressure", "pressure_cm_h2o"),
];
const SHAPE_KEYS: [(&str, &str); 4] = [
    ("pitch", "pitch_hz"),
    ("bright", "brightness"),
    ("rough", "roughness"),
    ("mouth", "mouth"),
];

#[derive(Default)]
struct Samples {
    radiation: [[f64; 4]; 2],
    glottis: [[f64; 4]; 2],
    count: usize,
}

struct GlottalObservation {
    shadow: ParametricGlottis,
    nodes: [usize; 2],
    port: usize,
    controls: [usize; 3],
}

struct Capture {
    sim: Box<dyn CreatureSim>,
    observed: Arc<Mutex<Samples>>,
    wall_weights: Vec<(usize, f64)>,
    radiators: [usize; 2],
    glottis: Option<GlottalObservation>,
}

impl CreatureSim for Capture {
    fn net(&self) -> Option<&AirwayNetwork> {
        self.sim.net()
    }

    fn net_mut(&mut self) -> Option<&mut AirwayNetwork> {
        self.sim.net_mut()
    }

    fn tubes(&self) -> &[(&'static str, Tube)] {
        self.sim.tubes()
    }

    fn control(&mut self, params: &[f64], gate: f64, dt: f64) {
        if let Some(glottis) = &mut self.glottis {
            let [pitch, brightness, roughness] = glottis.controls.map(|index| params[index]);
            let voice = &mut glottis.shadow.params;
            voice.f0 = pitch;
            voice.open_quotient = 0.55 - 0.25 * brightness;
            voice.closure_sharpness = 0.4 + 0.6 * brightness;
            voice.effort = 0.5 + 0.5 * brightness;
            voice.chaos = roughness;
        }
        self.sim.control(params, gate, dt);
    }

    fn flush_tiny(&mut self) {
        if let Some(glottis) = &mut self.glottis {
            glottis.shadow.flush_tiny();
        }
        self.sim.flush_tiny();
    }

    fn gain(&self) -> f64 {
        self.sim.gain()
    }

    fn sample(&mut self) -> f64 {
        // 実際の気道の更新前差圧を使い、更新後のポート面積で観測用の声門を照合する。
        let shadow_area = self.glottis.as_mut().map(|glottis| {
            let net = self.sim.net().unwrap();
            let [left, right] = glottis.nodes;
            glottis.shadow.next(net.p[left] - net.p[right])
        });
        let radiation = self.sim.sample();
        let net = self.sim.net().unwrap();
        let wall = self
            .wall_weights
            .iter()
            .map(|&(node, weight)| net.wall_u[node] * weight)
            .sum();
        let [oral, nasal] = self.radiators.map(|index| net.rad_u[index]);
        let mut samples = self.observed.lock().unwrap();
        let index = samples.count;
        samples.radiation[index] = [wall, oral, nasal, radiation];
        if let (Some(glottis), Some(shadow_area)) = (&self.glottis, shadow_area) {
            let area = net.port_area[glottis.port];
            samples.glottis[index] = [
                glottis.shadow.cycle_phase(),
                glottis.shadow.f0_now,
                area,
                (area - shadow_area).abs(),
            ];
        }
        samples.count += 1;
        radiation
    }
}

fn main() -> Result<(), Box<dyn Error>> {
    let input = env::args().nth(1).ok_or("比較ケースが必要です")?;
    if let Some(id) = input
        .strip_prefix("--")
        .and_then(|flag| flag.strip_suffix("-definition"))
    {
        let def = seal::def();
        let index = def.call_index(id).ok_or("アザラシのコールがありません")?;
        serde_json::to_writer(io::stdout().lock(), &def.calls[index])?;
        return Ok(());
    }
    let case: Value = serde_json::from_str(&fs::read_to_string(input)?)?;
    let case = &case["seal_voice"];
    let breath = &case["breath"];
    let def = Box::leak(Box::new(seal::def()));
    let mut initial = params(def, &case["shape"], &SHAPE_KEYS);
    initial.extend(params(def, &breath["controls"], &BREATH_KEYS));
    let mut voice = CreatureVoice::new(def, breath["sample_rate_hz"].as_f64().unwrap(), &initial);
    voice.level = case["level"].as_f64().unwrap();
    let net = voice.sim.net().unwrap();
    let named = |name| {
        net.tubes[net
            .tube_names
            .iter()
            .position(|value| value == name)
            .unwrap()]
    };
    let lung = named("lungs").first_node();
    let geometry = net.linear_elements();
    let radiators = ["oral", "nasal"].map(|name| {
        let node = named(name).last_node();
        geometry.rad_nodes.iter().position(|&r| r == node).unwrap()
    });
    let trace_glottis = case["observe_glottis"].as_bool().unwrap_or_default();
    let glottis = trace_glottis.then(|| {
        let nodes = [named("trachea").last_node(), named("pharynx").first_node()];
        let port = geometry
            .a
            .iter()
            .zip(&geometry.b)
            .position(|(&a, &b)| [a, b] == nodes)
            .unwrap();
        let mut shadow = ParametricGlottis::new(voice.fs);
        shadow.params.amplitude = 0.22;
        shadow.params.chink = 0.01;
        shadow.params.jitter = 0.002;
        shadow.params.shimmer = 0.01;
        shadow.params.drift = 2.0;
        GlottalObservation {
            shadow,
            nodes,
            port,
            controls: ["pitch", "bright", "rough"].map(|name| def.param_index(name).unwrap()),
        }
    });
    let observed = Arc::new(Mutex::new(Samples::default()));
    let inner = std::mem::replace(&mut voice.sim, def.create(voice.fs));
    voice.sim = Box::new(Capture {
        sim: inner,
        observed: Arc::clone(&observed),
        wall_weights: geometry
            .wall_rad
            .into_iter()
            .enumerate()
            .filter(|(_, weight)| *weight != 0.0)
            .collect(),
        radiators,
        glottis,
    });
    let mut output = BufWriter::new(io::stdout().lock());
    write!(
        output,
        concat!(
            "frame,internal_sample,gate,lung_pressure_dyn_cm2,",
            "wall_0,oral_0,nasal_0,radiation_0,wall_1,oral_1,nasal_1,radiation_1,pcm_f32"
        )
    )?;
    let playback_events = case["events"]
        .as_array()
        .map(Vec::as_slice)
        .unwrap_or_default();
    let trace_call_id = case["observe_call_id"].as_bool().unwrap_or_default();
    let trace_call = trace_call_id || !playback_events.is_empty();
    if trace_call {
        write!(
            output,
            concat!(
                ",active_call,control_clock_seconds,pitch_hz,target_pitch_hz,",
                "pulse_rate_hz,pulse_depth,duty,pressure_cm_h2o,",
                "target_pulse_rate_hz,target_pulse_depth,target_duty,target_pressure_cm_h2o"
            )
        )?;
    }
    if trace_call_id {
        write!(output, ",call_id")?;
    }
    if trace_glottis {
        write!(output, ",roughness,target_roughness")?;
        for index in 0..2 {
            write!(
                output,
                ",glottis_phase_{index},glottis_f0_hz_{index},glottis_area_cm2_{index},shadow_area_error_{index}"
            )?;
        }
    }
    writeln!(output)?;
    let pitch_index = def.param_index("pitch").unwrap();
    let roughness_index = def.param_index("rough").unwrap();
    let breath_indices = BREATH_KEYS.map(|(name, _)| def.param_index(name).unwrap());
    let mut playback_events = playback_events.iter().peekable();
    let mut events = breath["events"].as_array().unwrap().iter().peekable();
    for frame in 0..breath["frames"].as_u64().unwrap() {
        if let Some(event) = events.next_if(|event| event["frame"].as_u64() == Some(frame)) {
            if let Some(controls) = event.get("controls") {
                voice.set_params(&params(def, controls, &BREATH_KEYS));
            }
            if let Some(gate) = event["gate"].as_f64() {
                voice.set_gate(gate);
            }
        }
        if let Some(event) = playback_events.next_if(|event| event["frame"].as_u64() == Some(frame))
        {
            if let Some(pitch) = event["pitch_hz"].as_f64() {
                voice.set_params(&[(pitch_index, pitch)]);
            }
            if let Some(roughness) = event["roughness"].as_f64() {
                voice.set_params(&[(roughness_index, roughness)]);
            }
            if let Some(call) = event.get("play_call") {
                voice.play_call_id(
                    call["id"].as_str().unwrap(),
                    call["pitch_hz"].as_f64(),
                    call["amplitude"].as_f64().unwrap_or(1.0),
                );
            }
            if event["stop_call"].as_bool().unwrap_or_default() {
                voice.stop_call();
            }
        }
        let mut pcm = [0.0];
        voice.render(&mut pcm);
        let mut current = observed.lock().unwrap();
        if current.count != voice.m {
            return Err("上流の内部サンプル数が一致しません".into());
        }
        let internal = (frame + 1) * voice.m as u64 - 1;
        write!(
            output,
            "{frame},{internal},{},{}",
            voice.gate,
            voice.sim.net().unwrap().p[lung]
        )?;
        for value in current.radiation.into_iter().flatten() {
            write!(output, ",{value}")?;
        }
        write!(output, ",{}", pcm[0])?;
        if trace_call {
            let values = voice.values();
            let targets = voice.targets();
            write!(
                output,
                ",{},{},{},{}",
                u8::from(voice.active_call().is_some()),
                voice.clock,
                values[pitch_index],
                targets[pitch_index]
            )?;
            for value in breath_indices
                .map(|index| values[index])
                .into_iter()
                .chain(breath_indices.map(|index| targets[index]))
            {
                write!(output, ",{value}")?;
            }
        }
        if trace_call_id {
            let id = voice
                .active_call()
                .and_then(|name| def.call_index(name))
                .map_or(0, |index| index + 1);
            write!(output, ",{id}")?;
        }
        if trace_glottis {
            write!(
                output,
                ",{},{}",
                voice.values()[roughness_index],
                voice.targets()[roughness_index]
            )?;
            for value in current.glottis.into_iter().flatten() {
                write!(output, ",{value}")?;
            }
        }
        writeln!(output)?;
        current.count = 0;
    }
    output.flush()?;
    Ok(())
}
