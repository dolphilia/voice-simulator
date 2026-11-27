//! 固定上流の実気道、声門の状態、出力PCMを同じ描画時刻で採取する。

use chimera::airway::network::{AirwayNetwork, Tube};
use chimera::creatures::{CreatureSim, CreatureVoice, alligator};
use chimera::sources::glottis::ParametricGlottis;
use serde_json::{Value, json};
use std::env;
use std::error::Error;
use std::fs;
use std::io::{self, BufWriter, Write};
use std::sync::{Arc, Mutex};

const SHAPE_KEYS: [(&str, &str); 6] = [
    ("pitch", "pitch_hz"),
    ("chaos", "chaos"),
    ("pressure", "pressure_cm_h2o"),
    ("mouth", "mouth"),
    ("nostrils", "nostrils"),
    ("hiss", "hiss"),
];

#[derive(Default)]
struct Samples {
    values: [[f64; 23]; 2],
    count: usize,
}

struct Capture {
    sim: Box<dyn CreatureSim>,
    shadow: ParametricGlottis,
    samples: Arc<Mutex<Samples>>,
    lung: usize,
    trachea: Tube,
    pharynx: Tube,
    oral_tip: usize,
    ports: [usize; 3],
    indices: [usize; 6],
    wall_weights: Vec<(usize, f64)>,
    prepare_network_blocks: bool,
}

impl CreatureSim for Capture {
    fn net(&self) -> Option<&AirwayNetwork> {
        self.sim.net()
    }

    fn net_mut(&mut self) -> Option<&mut AirwayNetwork> {
        if self.prepare_network_blocks {
            self.sim.net_mut()
        } else {
            // 初期断面を確定済みの短い対照に限って、微小値の整理を含む begin_block を省く。
            None
        }
    }

    fn tubes(&self) -> &[(&'static str, Tube)] {
        self.sim.tubes()
    }

    fn control(&mut self, params: &[f64], gate: f64, interval: f64) {
        let [pitch, chaos, _, _, _, hiss] = self.indices.map(|index| params[index]);
        let glottis = &mut self.shadow.params;
        glottis.f0 = pitch;
        glottis.amplitude = 0.9 * (1.0 - hiss);
        glottis.abduction = 0.02 + 0.8 * hiss;
        glottis.chaos = chaos;
        glottis.jitter = 0.01 + 0.05 * chaos;
        glottis.shimmer = 0.05 + 0.25 * chaos;
        self.sim.control(params, gate, interval);
    }

    fn flush_tiny(&mut self) {
        self.shadow.flush_tiny();
        self.sim.flush_tiny();
    }

    fn gain(&self) -> f64 {
        self.sim.gain()
    }

    fn sample(&mut self) -> f64 {
        let [lung_port, glottis, velum] = self.ports;
        let a = self.trachea.last_node();
        let b = self.pharynx.first_node();
        let net = self.sim.net().unwrap();
        let drive = net.p[a] - net.p[b];
        let predicted_area = self.shadow.next(drive);
        let radiation = self.sim.sample();
        let net = self.sim.net().unwrap();
        let sources = net.noise_sources();
        let glottal_noise = &sources[0];
        let wall = self
            .wall_weights
            .iter()
            .map(|&(node, weight)| weight * net.wall_u[node])
            .sum();
        let mut samples = self.samples.lock().unwrap();
        let index = samples.count;
        samples.values[index] = [
            net.p[self.lung],
            net.u[lung_port],
            net.p[self.trachea.first_node()],
            net.p[a],
            net.p[b],
            drive,
            net.port_area[glottis],
            net.u[glottis],
            self.shadow.voicing,
            self.shadow.cycle_phase(),
            self.shadow.f0_now,
            net.port_area[velum],
            net.u[velum],
            wall,
            net.rad_u[0],
            net.rad_u[1],
            radiation,
            (net.port_area[glottis] - predicted_area).abs(),
            net.area[self.oral_tip],
            f64::from(u8::from(net.noise_sources().len() > 1)),
            glottal_noise.level,
            net.psrc[glottal_noise.fwd] + net.psrc[glottal_noise.bwd],
            sources.get(1).map_or(0.0, |source| source.level),
        ];
        samples.count += 1;
        radiation
    }
}

fn main() -> Result<(), Box<dyn Error>> {
    let mut args = env::args().skip(1);
    let path = args.next().ok_or("比較ケースが必要です")?;
    if let Some(id) = path
        .strip_prefix("--")
        .and_then(|flag| flag.strip_suffix("-definition"))
    {
        let def = alligator::def();
        let index = def
            .call_index(id)
            .ok_or("アリゲーターのコールの定義がありません")?;
        serde_json::to_writer(io::stdout().lock(), &def.calls[index])?;
        return Ok(());
    }
    let case: Value = serde_json::from_str(&fs::read_to_string(path)?)?;
    let case = &case["alligator_voice"];
    let shape = &case["shape"];
    let frames = case["frames"].as_u64().unwrap();
    let def = Box::leak(Box::new(alligator::def()));
    let params = SHAPE_KEYS.map(|(key, field)| {
        (
            def.param_index(key).unwrap(),
            shape[field].as_f64().unwrap(),
        )
    });
    let indices = params.map(|(index, _)| index);
    let mut voice = CreatureVoice::new(def, case["sample_rate_hz"].as_f64().unwrap(), &params);
    voice.level = case["level"].as_f64().unwrap();
    let mode = args.next();
    if mode.as_deref() == Some("--mute-noise") {
        voice
            .sim
            .net_mut()
            .ok_or("アリゲーターの気道がありません")?
            .noise_scale = 0.0;
    }
    let net = voice.sim.net().unwrap();
    let tube = |name| {
        net.tubes[net
            .tube_names
            .iter()
            .position(|value| value == name)
            .unwrap()]
    };
    let [trachea, pharynx, oral, nasal] = ["trachea", "pharynx", "oral", "nasal"].map(tube);
    let lung = tube("lungs").first_node();
    let elements = net.linear_elements();
    let branch = |left, right| {
        elements
            .a
            .iter()
            .zip(&elements.b)
            .position(|(&a, &b)| a == left && b == right)
            .unwrap()
    };
    let ports = [
        branch(lung, trachea.first_node()),
        branch(trachea.last_node(), pharynx.first_node()),
        branch(pharynx.last_node(), nasal.first_node()),
    ];
    let observe_call = case["observe_call"].as_bool().unwrap_or_default();
    let observe_noise = case["observe_noise"].as_bool().unwrap_or_default();
    if mode.as_deref() == Some("--inspect") {
        let info = json!({
            "internal_rate_hz": voice.fs,
            "decimation_factor": voice.m,
            "control_frames": 64,
            "rows": frames * voice.m as u64,
            "geometry": {
                "trachea_cells": trachea.n,
                "pharynx_cells": pharynx.n,
                "oral_cells": oral.n,
                "nasal_cells": nasal.n,
                "oral_tip_area_cm2": net.area[oral.last_node()],
                "velum_area_cm2": net.port_area[ports[2]],
                "oral_noise_cell": net.noise_sources().get(1).map(|s| s.src - oral.branch(0)),
                "courant": net.check_cfl(),
            },
        });
        serde_json::to_writer(io::stdout().lock(), &info)?;
        return Ok(());
    }
    let hiss = shape["hiss"].as_f64().unwrap();
    let chaos = shape["chaos"].as_f64().unwrap();
    let mut shadow = ParametricGlottis::new(voice.fs);
    shadow.threshold = 1.5 * 980.665;
    shadow.params.f0 = shape["pitch_hz"].as_f64().unwrap();
    shadow.params.amplitude = 0.9 * (1.0 - hiss);
    shadow.params.abduction = 0.02 + 0.8 * hiss;
    shadow.params.open_quotient = 0.5;
    shadow.params.closure_sharpness = 0.8;
    shadow.params.effort = 1.0;
    shadow.params.chaos = chaos;
    shadow.params.jitter = 0.01 + 0.05 * chaos;
    shadow.params.shimmer = 0.05 + 0.25 * chaos;
    shadow.params.drift = 8.0;
    let samples = Arc::new(Mutex::new(Samples::default()));
    let sim = std::mem::replace(&mut voice.sim, def.create(voice.fs));
    voice.sim = Box::new(Capture {
        sim,
        shadow,
        samples: Arc::clone(&samples),
        lung,
        trachea,
        pharynx,
        oral_tip: oral.last_node(),
        ports,
        indices,
        prepare_network_blocks: mode.as_deref() != Some("--skip-network-block"),
        wall_weights: elements
            .wall_rad
            .into_iter()
            .enumerate()
            .filter(|&(_, w)| w != 0.0)
            .collect(),
    });
    let mut out = BufWriter::new(io::stdout().lock());
    write!(
        out,
        concat!(
            "sample,frame,gate,lung_pressure_dyn_cm2,lung_flow_cm3_s,trachea_inlet_pressure_dyn_cm2,",
            "trachea_end_pressure_dyn_cm2,pharynx_pressure_dyn_cm2,glottis_drive_dyn_cm2,",
            "glottis_area_cm2,glottis_flow_cm3_s,glottis_voicing,glottis_phase,glottis_f0_hz,",
            "velum_area_cm2,velum_flow_cm3_s,wall_cm3_s,oral_cm3_s,nasal_cm3_s,radiation_cm3_s2,",
            "shadow_area_cm2,pcm_f32"
        )
    )?;
    if observe_call {
        write!(
            out,
            concat!(
                ",call_id,control_clock_seconds,oral_tip_area_cm2,oral_noise,",
                "pitch_hz,chaos,pressure_cm_h2o,mouth,nostrils,hiss,",
                "target_pitch_hz,target_chaos,target_pressure_cm_h2o,target_mouth,target_nostrils,target_hiss"
            )
        )?;
    }
    if observe_noise {
        write!(
            out,
            ",glottal_noise_level_dyn_cm2,glottal_noise_pressure_dyn_cm2,oral_noise_level_dyn_cm2"
        )?;
    }
    writeln!(out)?;
    let mut events = case["events"].as_array().unwrap().iter().peekable();
    for frame in 0..frames {
        if let Some(event) = events.next_if(|e| e["frame"].as_u64() == Some(frame)) {
            if let Some(patch) = event.get("params") {
                for ((_, field), index) in SHAPE_KEYS.into_iter().zip(indices) {
                    if let Some(value) = patch[field].as_f64() {
                        voice.set_params(&[(index, value)]);
                    }
                }
            }
            if let Some(gate) = event["gate"].as_f64() {
                voice.set_gate(gate);
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
        let mut block = samples.lock().unwrap();
        if block.count != voice.m {
            return Err("内部サンプル数が一致しません".into());
        }
        for (sub, values) in block.values[..block.count].iter().enumerate() {
            let index = frame * voice.m as u64 + sub as u64;
            write!(out, "{index},{frame},{}", voice.gate)?;
            for value in &values[..18] {
                write!(out, ",{value}")?;
            }
            let pcm = if sub + 1 == voice.m { pcm[0] } else { 0.0 };
            write!(out, ",{pcm}")?;
            if observe_call {
                let id = voice
                    .active_call()
                    .and_then(|id| def.call_index(id))
                    .map_or(0, |id| id + 1);
                write!(out, ",{id},{},{},{}", voice.clock, values[18], values[19])?;
                let current = indices.map(|index| voice.values()[index]);
                let targets = indices.map(|index| voice.targets()[index]);
                for value in current.into_iter().chain(targets) {
                    write!(out, ",{value}")?;
                }
            }
            if observe_noise {
                for value in &values[20..] {
                    write!(out, ",{value}")?;
                }
            }
            writeln!(out)?;
        }
        block.count = 0;
    }
    out.flush()?;
    Ok(())
}
