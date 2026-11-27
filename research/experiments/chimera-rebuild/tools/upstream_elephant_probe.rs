//! 固定上流の鼻の基部・弁・先端を、実際の CreatureVoice の描画中に観測する。

use chimera::airway::network::{AirwayNetwork, Tube};
use chimera::creatures::{CreatureSim, CreatureVoice, elephant};
use chimera::sources::glottis::ParametricGlottis;
use chimera::sources::valves::LipReed;
use serde_json::{Value, json};
use std::env;
use std::error::Error;
use std::fs;
use std::io::{self, BufWriter, Write};
use std::sync::{Arc, Mutex};

const SHAPE_KEYS: [(&str, &str); 6] = [
    ("pitch", "pitch_hz"),
    ("pressure", "pressure_cm_h2o"),
    ("trunk", "trunk"),
    ("chaos", "chaos"),
    ("mode", "mode"),
    ("lipPitch", "lip_pitch_hz"),
];

struct Capture {
    sim: Box<dyn CreatureSim>,
    shadow: ParametricGlottis,
    row: Arc<Mutex<[f64; 26]>>,
    pressure_nodes: [usize; 7],
    ports: [usize; 4],
    indices: [usize; 6],
    wall_weights: Vec<(usize, f64)>,
    observe_valve: bool,
    mode: f64,
    reed: LipReed,
    source_state: Vec<(&'static str, f64)>,
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

    fn control(&mut self, params: &[f64], gate: f64, interval: f64) {
        let [pitch, _, _, chaos, mode, lip_pitch] = self.indices.map(|index| params[index]);
        self.shadow.params.f0 = pitch;
        self.shadow.params.chaos = chaos * 0.6;
        self.shadow.params.amplitude = 1.6 * (1.0 - mode);
        self.shadow.params.abduction = 0.05 + 3.0 * mode;
        self.mode = mode;
        self.reed.f = lip_pitch;
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
        let [lung, below, above, oral, base, inlet, tip] = self.pressure_nodes;
        let [lung_port, glottis, velum, valve] = self.ports;
        let net = self.sim.net().unwrap();
        let drive = net.p[below] - net.p[above];
        let mut reed_drive = 0.0;
        if self.observe_valve && self.mode > 0.02 {
            reed_drive = (net.p[base] - net.p[inlet]) * self.mode;
            self.reed.next(reed_drive);
        }
        let predicted_area = self.shadow.next(drive);
        let radiation = self.sim.sample();
        if self.observe_valve {
            self.sim.source_state(&mut self.source_state);
        }
        let reed_telemetry = self
            .source_state
            .iter()
            .find(|(name, _)| *name == "lips")
            .map_or(0.0, |(_, value)| *value);
        let net = self.sim.net().unwrap();
        let wall = self
            .wall_weights
            .iter()
            .map(|&(k, w)| net.wall_u[k] * w)
            .sum();
        *self.row.lock().unwrap() = [
            net.p[lung],
            net.u[lung_port],
            net.p[below],
            net.p[above],
            drive,
            net.port_area[glottis],
            net.u[glottis],
            self.shadow.cycle_phase(),
            self.shadow.f0_now,
            net.area[oral],
            net.port_area[velum],
            net.u[velum],
            net.p[base],
            net.p[inlet],
            net.p[tip],
            net.port_area[valve],
            net.u[valve],
            wall,
            net.radiated_flow(0),
            net.radiated_flow(1),
            radiation,
            (net.port_area[glottis] - predicted_area).abs(),
            reed_drive,
            self.reed.opening,
            reed_telemetry,
            net.noise_sources()[0].gain,
        ];
        radiation
    }
}

fn capture_reed(case: &Value) -> Result<(), Box<dyn Error>> {
    let mut reed = LipReed::new(case["sample_rate_hz"].as_f64().unwrap());
    let params = &case["parameters"];
    reed.f = params["pitch_hz"].as_f64().unwrap();
    reed.zeta = params["damping_ratio"].as_f64().unwrap();
    reed.h0 = params["rest_gap_cm"].as_f64().unwrap();
    reed.width = params["width_cm"].as_f64().unwrap();
    reed.surface_per_mass = params["surface_per_mass_cm2_g"].as_f64().unwrap();
    let mut steps = case["pressure_steps"].as_array().unwrap().iter().peekable();
    let mut drive = 0.0;
    let mut out = BufWriter::new(io::stdout().lock());
    writeln!(out, "frame,drive_dyn_cm2,opening_cm2")?;
    for frame in 0..case["frames"].as_u64().unwrap() {
        if let Some(step) = steps.next_if(|step| step["frame"].as_u64() == Some(frame)) {
            drive = step["dyn_cm2"].as_f64().unwrap();
        }
        let opening = reed.next(drive);
        writeln!(out, "{frame},{drive},{opening}")?;
    }
    out.flush()?;
    Ok(())
}

fn main() -> Result<(), Box<dyn Error>> {
    let mut args = env::args().skip(1);
    let path = args.next().ok_or("ゾウの比較ケースが必要です")?;
    if let Some(id) = path
        .strip_prefix("--")
        .and_then(|flag| flag.strip_suffix("-definition"))
    {
        let def = elephant::def();
        let index = def.call_index(id).ok_or("ゾウのコールの定義がありません")?;
        serde_json::to_writer(io::stdout().lock(), &def.calls[index])?;
        return Ok(());
    }
    let config: Value = serde_json::from_str(&fs::read_to_string(path)?)?;
    if let Some(case) = config.get("lip_reed") {
        return capture_reed(case);
    }
    let case = &config["elephant_voice"];
    let observe_call = case["observe_call"].as_bool().unwrap_or_default();
    let observe_valve = case["observe_valve"].as_bool().unwrap_or_default();
    let shape = &case["shape"];
    let frames = case["frames"].as_u64().unwrap();
    let def = Box::leak(Box::new(elephant::def()));
    let params = SHAPE_KEYS.map(|(key, field)| {
        let index = def.param_index(key).unwrap();
        (
            index,
            shape[field].as_f64().unwrap_or(def.params[index].default),
        )
    });
    let indices = params.map(|(index, _)| index);
    let mut voice = CreatureVoice::new(def, case["sample_rate_hz"].as_f64().unwrap(), &params);
    voice.level = case["level"].as_f64().unwrap();
    if voice.m != 1 {
        return Err("ゾウの内部レートと出力レートが一致しません".into());
    }
    let net = voice.sim.net().unwrap();
    let tube = |name| {
        net.tubes[net
            .tube_names
            .iter()
            .position(|value| value == name)
            .unwrap()]
    };
    let [trachea, pharynx, oral, nasal, trunk] =
        ["trachea", "pharynx", "oral", "nasal", "trunk"].map(tube);
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
        branch(nasal.last_node(), trunk.first_node()),
    ];
    if args.next().as_deref() == Some("--inspect") {
        let geometry = json!({
            "internal_rate_hz": voice.fs, "decimation_factor": voice.m, "control_frames": 64, "rows": frames,
            "geometry": {
                "trachea_cells": trachea.n, "pharynx_cells": pharynx.n, "oral_cells": oral.n,
                "nasal_cells": nasal.n, "trunk_cells": trunk.n, "courant": net.check_cfl(),
                "oral_tip_area_cm2": net.area[oral.last_node()], "velum_area_cm2": net.port_area[ports[2]],
                "trunk_valve_area_cm2": net.port_area[ports[3]],
                "trunk_inlet_area_cm2": net.area[trunk.first_node()], "trunk_tip_area_cm2": net.area[trunk.last_node()],
            },
        });
        serde_json::to_writer(io::stdout().lock(), &geometry)?;
        return Ok(());
    }
    let mut shadow = ParametricGlottis::new(voice.fs);
    shadow.threshold = 1.5 * 980.665;
    shadow.params.amplitude = 1.6;
    shadow.params.abduction = 0.05;
    shadow.params.open_quotient = 0.6;
    shadow.params.effort = 0.9;
    let mut reed = LipReed::new(voice.fs);
    reed.zeta = 0.08;
    reed.h0 = 0.003;
    reed.width = 2.4;
    reed.surface_per_mass = 40.0;
    let row = Arc::new(Mutex::new([0.0; 26]));
    let sim = std::mem::replace(&mut voice.sim, def.create(voice.fs));
    voice.sim = Box::new(Capture {
        sim,
        shadow,
        row: Arc::clone(&row),
        indices,
        ports,
        observe_valve,
        mode: 0.0,
        reed,
        source_state: Vec::with_capacity(2),
        pressure_nodes: [
            lung,
            trachea.last_node(),
            pharynx.first_node(),
            oral.last_node(),
            nasal.last_node(),
            trunk.first_node(),
            trunk.last_node(),
        ],
        wall_weights: elements
            .wall_rad
            .into_iter()
            .enumerate()
            .filter(|&(_, weight)| weight != 0.0)
            .collect(),
    });
    let mut out = BufWriter::new(io::stdout().lock());
    write!(
        out,
        concat!(
            "frame,gate,pitch_hz,pressure_cm_h2o,trunk,chaos,",
            "lung_pressure_dyn_cm2,lung_flow_cm3_s,trachea_end_pressure_dyn_cm2,pharynx_pressure_dyn_cm2,",
            "glottis_drive_dyn_cm2,glottis_area_cm2,glottis_flow_cm3_s,glottis_phase,glottis_f0_hz,",
            "oral_tip_area_cm2,velum_area_cm2,velum_flow_cm3_s,nasal_base_pressure_dyn_cm2,",
            "trunk_inlet_pressure_dyn_cm2,trunk_tip_pressure_dyn_cm2,trunk_valve_area_cm2,trunk_valve_flow_cm3_s,",
            "wall_cm3_s,oral_cm3_s,nasal_cm3_s,radiation_cm3_s2,shadow_area_error_cm2,pcm_f32"
        )
    )?;
    if observe_call {
        write!(
            out,
            concat!(
                ",call_id,control_clock_seconds,target_pitch_hz,target_pressure_cm_h2o,",
                "target_trunk,target_chaos"
            )
        )?;
    }
    if observe_valve {
        write!(
            out,
            concat!(
                ",mode,lip_pitch_hz,target_mode,target_lip_pitch_hz,glottis_abduction_cm2,",
                "glottis_amplitude_cm2,glottal_noise_gain,reed_drive_dyn_cm2,reed_opening_cm2,reed_telemetry"
            )
        )?;
    }
    writeln!(out)?;
    let mut events = case["events"].as_array().unwrap().iter().peekable();
    for frame in 0..frames {
        if let Some(event) = events.next_if(|event| event["frame"].as_u64() == Some(frame)) {
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
                    call["id"].as_str().ok_or("ゾウのコールIDが必要です")?,
                    call["pitch_hz"].as_f64(),
                    call["amplitude"].as_f64().unwrap_or(1.0),
                );
            }
            if event["stop_call"].as_bool() == Some(true) {
                voice.stop_call();
            }
        }
        let mut pcm = [0.0];
        voice.render(&mut pcm);
        write!(out, "{frame},{}", voice.gate)?;
        for &index in &indices[..4] {
            write!(out, ",{}", voice.values()[index])?;
        }
        let row = row.lock().unwrap();
        for value in &row[..22] {
            write!(out, ",{value}")?;
        }
        write!(out, ",{}", pcm[0])?;
        if observe_call {
            let call = voice
                .active_call()
                .and_then(|id| def.call_index(id))
                .map_or(0, |index| index + 1);
            write!(out, ",{call},{}", voice.clock)?;
            for &index in &indices[..4] {
                write!(out, ",{}", voice.targets()[index])?;
            }
        }
        if observe_valve {
            let [mode, lip_pitch] = [indices[4], indices[5]].map(|i| voice.values()[i]);
            write!(
                out,
                ",{mode},{lip_pitch},{},{},{},{},{},{},{},{}",
                voice.targets()[indices[4]],
                voice.targets()[indices[5]],
                0.05 + 3.0 * mode,
                1.6 * (1.0 - mode),
                row[25],
                row[22],
                row[23],
                row[24]
            )?;
        }
        writeln!(out)?;
    }
    out.flush()?;
    Ok(())
}
