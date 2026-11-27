//! 固定上流の実際の内部サンプルを、比較用のラッパーから観測する。

use chimera::airway::network::{AirwayNetwork, Tube};
use chimera::creatures::{CreatureDef, CreatureSim, CreatureVoice, seal};
use chimera::physics::C_SOUND;
use chimera::sources::glottis::ParametricGlottis;
use serde_json::{Value, json};
use std::env;
use std::error::Error;
use std::fs;
use std::io::{self, BufWriter, Write};

fn breath_params(def: &CreatureDef, input: &Value) -> [(usize, f64); 4] {
    let keys = [
        ("pulseRate", "pulse_rate_hz"),
        ("pulse", "pulse_depth"),
        ("duty", "duty"),
        ("pressure", "pressure_cm_h2o"),
    ];
    keys.map(|(upper, name)| {
        (
            def.param_index(upper).unwrap(),
            input[name].as_f64().unwrap(),
        )
    })
}

struct Observation {
    sim: Box<dyn CreatureSim>,
    shadow: ParametricGlottis,
    output: BufWriter<io::Stdout>,
    sample: usize,
    lung: usize,
    trachea: Tube,
    pharynx: Tube,
    lung_port: usize,
    glottis_port: usize,
    velum_port: usize,
}

impl CreatureSim for Observation {
    fn net(&self) -> Option<&AirwayNetwork> {
        self.sim.net()
    }

    fn net_mut(&mut self) -> Option<&mut AirwayNetwork> {
        self.sim.net_mut()
    }

    fn tubes(&self) -> &[(&'static str, Tube)] {
        self.sim.tubes()
    }

    fn control(&mut self, parameters: &[f64], gate: f64, interval: f64) {
        self.sim.control(parameters, gate, interval);
    }

    fn flush_tiny(&mut self) {
        self.shadow.flush_tiny();
        self.sim.flush_tiny();
    }

    fn gain(&self) -> f64 {
        self.sim.gain()
    }

    fn sample(&mut self) -> f64 {
        let a = self.trachea.last_node();
        let b = self.pharynx.first_node();
        let net = self.sim.net().unwrap();
        let drive = net.p[a] - net.p[b];
        let area = self.shadow.next(drive);
        let radiation = self.sim.sample();
        let net = self.sim.net().unwrap();
        let error = (net.port_area[self.glottis_port] - area).abs();
        let sample = self.sample;
        let lung_pressure = net.p[self.lung];
        let lung_flow = net.u[self.lung_port];
        let inlet_pressure = net.p[self.trachea.first_node()];
        let subglottal = net.p[a];
        let supraglottal = net.p[b];
        let area = net.port_area[self.glottis_port];
        let glottis_flow = net.u[self.glottis_port];
        let voicing = self.shadow.voicing;
        let f0 = self.shadow.f0_now;
        let velum_flow = net.u[self.velum_port];
        let nasal_radiation = net.rad_u[1];
        writeln!(
            self.output,
            "{sample},{lung_pressure},{lung_flow},{inlet_pressure},{subglottal},{supraglottal},\
             {drive},{area},{glottis_flow},{voicing},{f0},{velum_flow},{nasal_radiation},{radiation},{error}"
        )
        .expect("観測値を出力できません");
        self.sample += 1;
        radiation
    }
}

fn main() -> Result<(), Box<dyn Error>> {
    let mut args = env::args().skip(1);
    let input = args.next().ok_or("比較ケースが必要です")?;
    let inspect = args.next().as_deref() == Some("--inspect");
    let case: Value = serde_json::from_str(&fs::read_to_string(input)?)?;
    let case = &case["seal_airway"];
    let breath = &case["breath"];
    let shape = &case["shape"];
    let def = Box::leak(Box::new(seal::def()));
    let pitch = shape["pitch_hz"].as_f64().unwrap();
    let brightness = shape["brightness"].as_f64().unwrap();
    let roughness = shape["roughness"].as_f64().unwrap();
    let mouth = shape["mouth"].as_f64().unwrap();
    let settings = [
        (def.param_index("pitch").unwrap(), pitch),
        (def.param_index("bright").unwrap(), brightness),
        (def.param_index("rough").unwrap(), roughness),
        (def.param_index("mouth").unwrap(), mouth),
    ];
    let output_frames = breath["frames"].as_u64().unwrap();
    let mut voice = CreatureVoice::new(
        def,
        breath["sample_rate_hz"].as_f64().unwrap(),
        &[settings, breath_params(def, &breath["controls"])].concat(),
    );
    let net = voice.sim.net().unwrap();
    let tube = |name| {
        net.tubes[net
            .tube_names
            .iter()
            .position(|value| value == name)
            .unwrap()]
    };
    let [trachea, pharynx, oral, nasal] = ["trachea", "pharynx", "oral", "nasal"].map(tube);
    if inspect {
        let info = json!({
            "internal_rate_hz": voice.fs,
            "oversample": voice.m,
            "rows": output_frames * voice.m as u64,
            "geometry": {
                "trachea_cells": trachea.n,
                "pharynx_cells": pharynx.n,
                "oral_cells": oral.n,
                "nasal_cells": nasal.n,
                "oral_tip_area_cm2": net.area[oral.last_node()],
                "courant": net.dx.iter().map(|&dx| C_SOUND / voice.fs / dx).fold(0.0_f64, f64::max),
            },
        });
        serde_json::to_writer(io::stdout().lock(), &info)?;
        return Ok(());
    }
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
    let mut shadow = ParametricGlottis::new(voice.fs);
    shadow.params.f0 = pitch;
    shadow.params.amplitude = 0.22;
    shadow.params.open_quotient = 0.55 - 0.25 * brightness;
    shadow.params.closure_sharpness = 0.4 + 0.6 * brightness;
    shadow.params.effort = 0.5 + 0.5 * brightness;
    shadow.params.chink = 0.01;
    shadow.params.jitter = 0.002;
    shadow.params.shimmer = 0.01;
    shadow.params.drift = 2.0;
    shadow.params.chaos = roughness;
    let mut output = BufWriter::new(io::stdout());
    writeln!(
        output,
        concat!(
            "sample,lung_pressure_dyn_cm2,lung_flow_cm3_s,trachea_inlet_pressure_dyn_cm2,",
            "trachea_end_pressure_dyn_cm2,pharynx_pressure_dyn_cm2,glottis_drive_dyn_cm2,",
            "glottis_area_cm2,glottis_flow_cm3_s,glottis_voicing,glottis_f0_hz,velum_flow_cm3_s,",
            "nasal_radiation_cm3_s,radiation_derivative_cm3_s2,shadow_area_error_cm2"
        )
    )?;
    let inner = std::mem::replace(&mut voice.sim, def.create(voice.fs));
    voice.sim = Box::new(Observation {
        sim: inner,
        shadow,
        output,
        sample: 0,
        lung,
        trachea,
        pharynx,
        lung_port: branch(lung, trachea.first_node()),
        glottis_port: branch(trachea.last_node(), pharynx.first_node()),
        velum_port: branch(pharynx.last_node(), nasal.first_node()),
    });
    let mut events = breath["events"].as_array().unwrap().iter().peekable();
    for frame in 0..output_frames {
        if let Some(event) = events.next_if(|event| event["frame"].as_u64() == Some(frame)) {
            if let Some(controls) = event.get("controls") {
                voice.set_params(&breath_params(def, controls));
            }
            if let Some(gate) = event["gate"].as_f64() {
                voice.set_gate(gate);
            }
        }
        voice.render(&mut [0.0]);
    }
    Ok(())
}
