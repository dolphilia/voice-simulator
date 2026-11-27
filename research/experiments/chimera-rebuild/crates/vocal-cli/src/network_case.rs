use super::Wall;
use serde::Deserialize;
use serde_json::{Value, json};
use std::error::Error;
use std::fs::File;
use std::io::{self, BufWriter, Write};
use std::path::Path;
use vocal_core::airway::network::NetworkSample;
use vocal_core::airway::network::{AirwayNetwork, Boundaries, NoiseSpec, Port, Section};
use vocal_core::breath::BreathSample;
use vocal_core::output::OutputStage;

mod breath_drive;
mod constriction;
mod glottal_drive;
pub(crate) mod pcm;
use breath_drive::{BREATH_HEADER, BreathDrive, BreathInput};
use constriction::SlidingConstriction;
use glottal_drive::{GlottalDrive, GlottisInput, TELEMETRY_HEADER};

#[derive(Deserialize)]
struct NetworkCase {
    network: Network,
    impulse: Option<Impulse>,
    #[serde(default)]
    area_ramps: Vec<AreaRamp>,
    sliding_constriction: Option<SlidingConstriction>,
    glottis: Option<GlottisInput>,
    breath: Option<BreathInput>,
    pcm: Option<pcm::Settings>,
    observe: Observe,
    measurement: Measurement,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Network {
    sample_rate_hz: u32,
    tubes: Vec<Tube>,
    connections: Vec<[usize; 2]>,
    radiators: Vec<usize>,
    #[serde(default)]
    pressure_nodes: Vec<PressureDrive>,
    #[serde(default)]
    ports: Vec<PortInput>,
    turbulence: Option<TurbulenceInput>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct TurbulenceInput {
    seed: u32,
    scale: f64,
    sources: Vec<NoiseInput>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct NoiseInput {
    source: [usize; 2],
    forward: [usize; 2],
    reverse: [usize; 2],
    gain: f64,
    lowpass_hz: f64,
    highpass_hz: f64,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PressureDrive {
    pressure_dyn_cm2: f64,
    ramp_samples: usize,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PortInput {
    nodes: [usize; 2],
    length_cm: f64,
    area_cm2: f64,
    entrance_loss: f64,
    expansion_loss: f64,
    #[serde(default)]
    slit_width_cm: f64,
    include_half_sections: Option<bool>,
    #[serde(default)]
    extra_resistance: f64,
}

impl From<PortInput> for Port {
    fn from(input: PortInput) -> Self {
        Self {
            nodes: input.nodes,
            length_cm: input.length_cm,
            area_cm2: input.area_cm2,
            entrance_loss: input.entrance_loss,
            expansion_loss: input.expansion_loss,
            slit_width_cm: input.slit_width_cm,
            include_half_sections: input.include_half_sections.unwrap_or(true),
            extra_resistance: input.extra_resistance,
        }
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Tube {
    length_cm: f64,
    areas_cm2: Vec<f64>,
    wall: Option<Wall>,
    #[serde(default = "unit_factor")]
    perimeter_factor: f64,
    #[serde(default = "unit_factor")]
    viscous_factor: f64,
}

fn unit_factor() -> f64 {
    1.0
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Impulse {
    node: usize,
    sample: usize,
    volume_cm3: f64,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Observe {
    pressure_nodes: Vec<usize>,
    branches: Vec<[usize; 2]>,
    #[serde(default)]
    area_nodes: Vec<usize>,
    #[serde(default)]
    minimum_area_nodes: Vec<usize>,
    #[serde(default)]
    volume_source_nodes: Vec<usize>,
    #[serde(default)]
    wall_nodes: Vec<usize>,
    #[serde(default)]
    noise_sources: Vec<usize>,
    #[serde(default)]
    noise_branches: Vec<[usize; 2]>,
    #[serde(default)]
    glottal_f0: bool,
}

#[derive(Deserialize)]
struct Measurement {
    sample_count: usize,
    tail_sample_count: Option<usize>,
    junction_node: Option<usize>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct AreaRamp {
    start_sample: usize,
    sample_count: usize,
    block_samples: usize,
    targets: Vec<AreaTarget>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct AreaTarget {
    node: usize,
    area_cm2: f64,
    minimum_area_cm2: Option<f64>,
}

impl AreaTarget {
    fn areas(&self) -> [f64; 2] {
        [
            self.area_cm2,
            self.minimum_area_cm2.unwrap_or(self.area_cm2),
        ]
    }
}

struct AreaProgram {
    ramps: Vec<AreaRamp>,
    initial_areas: Vec<[f64; 2]>,
    target_areas: Vec<[f64; 2]>,
    cursor: usize,
}

impl AreaProgram {
    fn new(
        ramps: Vec<AreaRamp>,
        sections: &[Section],
        tube_cells: usize,
        samples: usize,
    ) -> Result<Self, &'static str> {
        let mut previous_end = 0;
        let mut seen = vec![false; tube_cells];
        for ramp in &ramps {
            let end = ramp
                .start_sample
                .checked_add(ramp.sample_count)
                .ok_or("面積補間の終了位置が範囲外です")?;
            if ramp.start_sample < previous_end
                || end > samples
                || ramp.sample_count == 0
                || ramp.block_samples == 0
                || ramp.targets.is_empty()
            {
                return Err("面積補間の区間・ブロック長・対象節点を確認してください");
            }
            seen.fill(false);
            for target in &ramp.targets {
                let node = target.node;
                let [area, minimum] = target.areas();
                if node >= seen.len()
                    || seen[node]
                    || !area.is_finite()
                    || !(0.0..=area).contains(&minimum)
                {
                    return Err("面積補間に無効な面積または重複・範囲外の節点があります");
                }
                seen[node] = true;
            }
            previous_end = end;
        }
        let initial_areas: Vec<_> = sections
            .iter()
            .map(|section| [section.area_cm2, section.minimum_area_cm2])
            .collect();
        Ok(Self {
            ramps,
            target_areas: initial_areas.clone(),
            initial_areas,
            cursor: 0,
        })
    }

    fn apply(&mut self, sample: usize, airway: &mut AirwayNetwork) -> Result<(), &'static str> {
        if let Some(ramp) = self.ramps.get(self.cursor)
            && sample == ramp.start_sample + ramp.sample_count
        {
            for target in &ramp.targets {
                self.initial_areas[target.node] = target.areas();
            }
            self.cursor += 1;
        }
        let Some(ramp) = self.ramps.get(self.cursor) else {
            return Ok(());
        };
        let Some(elapsed) = sample.checked_sub(ramp.start_sample) else {
            return Ok(());
        };
        if elapsed % ramp.block_samples != 0 {
            return Ok(());
        }
        let block = ramp.block_samples.min(ramp.sample_count - elapsed);
        let fraction = (elapsed + block) as f64 / ramp.sample_count as f64;
        for target in &ramp.targets {
            let [mean, minimum] = self.initial_areas[target.node];
            let [goal_mean, goal_minimum] = target.areas();
            self.target_areas[target.node] = [
                mean + (goal_mean - mean) * fraction,
                minimum + (goal_minimum - minimum) * fraction,
            ];
        }
        airway.set_area_targets(&self.target_areas, block)
    }
}

pub enum Destination<'a> {
    Inspect,
    Trace(&'a Path),
    Pcm {
        wave: &'a Path,
        trace: Option<&'a Path>,
        block_frames: usize,
    },
}

struct Simulation {
    airway: AirwayNetwork,
    program: AreaProgram,
    pressure_drives: Vec<(usize, PressureDrive)>,
    breath: Option<BreathDrive>,
    glottis: Option<GlottalDrive>,
    impulse: Option<Impulse>,
    impulse_flow: f64,
    next_sample: usize,
}

struct NetworkTick {
    inlet_flow: f64,
    signal: NetworkSample,
    breath: Option<BreathSample>,
    glottal: Option<[f64; 5]>,
}

impl Simulation {
    fn step(&mut self) -> Result<NetworkTick, &'static str> {
        let index = self.next_sample;
        self.program.apply(index, &mut self.airway)?;
        for (node, drive) in &self.pressure_drives {
            if self
                .breath
                .as_ref()
                .is_some_and(|breath| breath.node() == *node)
            {
                continue;
            }
            let fraction = if index >= drive.ramp_samples {
                1.0
            } else {
                index as f64 / drive.ramp_samples as f64
            };
            self.airway
                .set_fixed_pressure(*node, drive.pressure_dyn_cm2 * fraction)?;
        }
        let inlet_flow = if self
            .impulse
            .as_ref()
            .is_some_and(|input| index == input.sample)
        {
            self.impulse_flow
        } else {
            0.0
        };
        let breath = self
            .breath
            .as_mut()
            .map(|breath| breath.step(index, &mut self.airway))
            .transpose()?;
        let glottal = self
            .glottis
            .as_mut()
            .map(|glottis| {
                glottis.step(index, &mut self.airway, breath.map(|sample| sample.effort))
            })
            .transpose()?;
        let signal = self.airway.step(
            self.impulse.as_ref().map_or(0, |input| input.node),
            inlet_flow,
        );
        self.next_sample += 1;
        Ok(NetworkTick {
            inlet_flow,
            signal,
            breath,
            glottal,
        })
    }
}

pub fn run(input: Value, destination: Destination<'_>) -> Result<(), Box<dyn Error>> {
    let case: NetworkCase = serde_json::from_value(input.clone())?;
    let mut sections = Vec::new();
    let mut connections = Vec::new();
    for tube in &case.network.tubes {
        if tube.areas_cm2.is_empty() {
            return Err("管には少なくとも一つの断面積を指定してください".into());
        }
        let start = sections.len();
        let dx = tube.length_cm / tube.areas_cm2.len() as f64;
        sections.extend(tube.areas_cm2.iter().map(|&area_cm2| Section {
            length_cm: dx,
            area_cm2,
            minimum_area_cm2: area_cm2,
            perimeter_factor: tube.perimeter_factor,
            viscous_factor: tube.viscous_factor,
            wall: tube.wall.map(Into::into),
        }));
        connections.extend((start..sections.len() - 1).map(|node| [node, node + 1]));
    }
    let tube_cells = sections.len();
    sections.extend(case.network.pressure_nodes.iter().map(|_| Section {
        length_cm: 1.0,
        area_cm2: 100.0,
        minimum_area_cm2: 100.0,
        perimeter_factor: 1.0,
        viscous_factor: 1.0,
        wall: None,
    }));
    let fixed_nodes: Vec<_> = (tube_cells..sections.len()).collect();
    let ports: Vec<_> = case.network.ports.into_iter().map(Port::from).collect();
    connections.extend(&case.network.connections);
    let inlet = case.impulse.as_ref();
    let measurement = &case.measurement;
    if inlet
        .map(|input| input.node)
        .into_iter()
        .chain(measurement.junction_node)
        .chain(case.observe.pressure_nodes.iter().copied())
        .chain(case.observe.area_nodes.iter().copied())
        .chain(case.observe.minimum_area_nodes.iter().copied())
        .chain(case.observe.volume_source_nodes.iter().copied())
        .chain(case.observe.wall_nodes.iter().copied())
        .any(|node| node >= sections.len())
    {
        return Err("注入・計測の節点が存在しません".into());
    }
    if tube_cells == 0
        || case
            .network
            .pressure_nodes
            .iter()
            .any(|drive| !drive.pressure_dyn_cm2.is_finite())
    {
        return Err("少なくとも一つの管と有限の固定圧力を指定してください".into());
    }
    let impulse_flow = inlet.map_or(0.0, |input| {
        input.volume_cm3 * f64::from(case.network.sample_rate_hz)
    });
    if !impulse_flow.is_finite()
        || measurement.sample_count == 0
        || measurement.tail_sample_count == Some(0)
        || inlet.is_some_and(|input| {
            impulse_flow == 0.0
                || input.sample
                    >= measurement
                        .sample_count
                        .saturating_sub(measurement.tail_sample_count.unwrap_or(0))
        })
    {
        return Err("インパルスまたは計測区間の指定が不正です".into());
    }
    let mut airway = AirwayNetwork::new(
        case.network.sample_rate_hz,
        &sections,
        &connections,
        Boundaries {
            radiation_nodes: &case.network.radiators,
            fixed_pressure_nodes: &fixed_nodes,
            ports: &ports,
        },
    )?;
    let ramps = match case.sliding_constriction {
        Some(motion) if case.area_ramps.is_empty() => {
            motion.ramps(&case.network.tubes, measurement.sample_count)?
        }
        Some(_) => return Err("閉鎖軌跡と断面ランプのどちらか一方を指定してください".into()),
        None => case.area_ramps,
    };
    let program = AreaProgram::new(ramps, &sections, tube_cells, measurement.sample_count)?;
    let find_branch = |nodes| {
        connections
            .iter()
            .chain(ports.iter().map(|port| &port.nodes))
            .position(|&edge| edge == nodes)
    };
    let observe_branches = |edges: &[[usize; 2]]| {
        edges
            .iter()
            .map(|&[a, b]| {
                find_branch([a, b])
                    .map(|i| (i, 1.0))
                    .or_else(|| find_branch([b, a]).map(|i| (i, -1.0)))
                    .ok_or("計測対象の枝が存在しません")
            })
            .collect::<Result<Vec<_>, _>>()
    };
    let observed_branches = observe_branches(&case.observe.branches)?;
    let observed_noise_branches = observe_branches(&case.observe.noise_branches)?;
    let breath = case
        .breath
        .map(|input| {
            let [node, _] = input.port;
            let drive = fixed_nodes
                .iter()
                .zip(&case.network.pressure_nodes)
                .find(|(index, _)| **index == node)
                .map(|(_, drive)| drive)
                .ok_or("肺ポートの始点は固定圧力節点で指定してください")?;
            if drive.pressure_dyn_cm2 != 0.0 || drive.ramp_samples != 0 {
                return Err("呼気で駆動する固定節点には初期圧力とランプ長を0で指定してください");
            }
            let port = ports
                .iter()
                .find(|port| port.nodes == input.port && port.area_cm2 > 0.0)
                .ok_or("肺ポートは開口した既存ポートを同じ節点順で指定してください")?;
            let branch = find_branch(input.port).expect("肺ポートは検証済み");
            BreathDrive::new(
                input,
                branch,
                port.extra_resistance,
                case.network.sample_rate_hz,
            )
        })
        .transpose()?;
    let glottis = case
        .glottis
        .map(|input| {
            let branch = find_branch(input.port)
                .filter(|&branch| airway.is_port(branch))
                .ok_or("声門ポートは既存のポートと同じ節点順で指定してください")?;
            GlottalDrive::new(input, branch, case.network.sample_rate_hz)
        })
        .transpose()?;
    if case.observe.glottal_f0 && glottis.is_none() {
        return Err("声門ピッチを観測する場合は声門を設定してください".into());
    }
    if let Some(turbulence) = &case.network.turbulence {
        let directed =
            |nodes| find_branch(nodes).ok_or("乱流源の枝は接続時と同じ節点順で指定してください");
        let sources = turbulence
            .sources
            .iter()
            .map(|s| {
                Ok::<_, &str>(NoiseSpec {
                    source: directed(s.source)?,
                    forward: directed(s.forward)?,
                    reverse: directed(s.reverse)?,
                    gain: s.gain,
                    lowpass_hz: s.lowpass_hz,
                    highpass_hz: s.highpass_hz,
                })
            })
            .collect::<Result<Vec<_>, _>>()?;
        airway.set_noise_seed(turbulence.seed);
        airway.set_noise_scale(turbulence.scale)?;
        airway.set_noise_sources(&sources)?;
    }
    if case
        .observe
        .noise_sources
        .iter()
        .any(|&source| airway.noise_level(source).is_none())
    {
        return Err("計測対象の乱流源が存在しません".into());
    }

    let pcm = case
        .pcm
        .map(|settings| {
            let stage = OutputStage::new(
                case.network.sample_rate_hz,
                settings.sample_rate_hz,
                settings.gain,
            )?;
            if !measurement.sample_count.is_multiple_of(stage.factor()) {
                return Err("PCMの内部サンプル数は間引き係数で割り切れる値にしてください");
            }
            Ok::<_, &'static str>((settings, stage))
        })
        .transpose()?;
    if matches!(destination, Destination::Inspect) {
        let mut stream = io::stdout().lock();
        let mut description = json!({
                "case": input, "unit_system": "CGS", "cells": sections.len(), "branches": connections.len() + ports.len(),
        });
        if let Some(node) = measurement.junction_node {
            let junction = airway.compliance(node);
            description["junction_geometric_compliance_cm3_per_dyn_cm2"] =
                json!(junction.geometric);
            description["junction_effective_compliance_cm3_per_dyn_cm2"] =
                json!(junction.effective);
        }
        if let Some((settings, stage)) = &pcm {
            description["pcm"] = json!({
                "sample_rate_hz": settings.sample_rate_hz,
                "frames": measurement.sample_count / stage.factor(),
                "decimation_factor": stage.factor(),
                "filter_coefficients": stage.coefficients(),
            });
        }
        serde_json::to_writer_pretty(&mut stream, &description)?;
        writeln!(stream)?;
        return Ok(());
    }
    let mut simulation = Simulation {
        airway,
        program,
        pressure_drives: fixed_nodes
            .into_iter()
            .zip(case.network.pressure_nodes)
            .collect(),
        breath,
        glottis,
        impulse: case.impulse,
        impulse_flow,
        next_sample: 0,
    };
    let path = match destination {
        Destination::Trace(path) => path,
        Destination::Pcm {
            wave,
            trace,
            block_frames,
        } => {
            let (settings, stage) = pcm.ok_or("PCMを出力するケースには pcm の設定が必要です")?;
            return pcm::write(
                || {
                    simulation
                        .step()
                        .map(|tick| tick.signal.radiation_flow_derivative_cm3_s2)
                },
                stage,
                settings.sample_rate_hz,
                measurement.sample_count,
                block_frames,
                wave,
                trace,
            );
        }
        Destination::Inspect => unreachable!(),
    };
    let mut stream = BufWriter::new(
        File::create_new(path)
            .map_err(|error| format!("{}: 出力を作成できません ({error})", path.display()))?,
    );
    write!(
        stream,
        "sample,inlet_flow_cm3_s,radiation_flow_cm3_s,radiation_flow_derivative_cm3_s2"
    )?;
    for node in &case.observe.pressure_nodes {
        write!(stream, ",pressure_{node}_dyn_cm2")?;
    }
    for [a, b] in &case.observe.branches {
        write!(stream, ",branch_flow_{a}_{b}_cm3_s")?;
    }
    for node in &case.network.radiators {
        write!(stream, ",radiation_{node}_cm3_s")?;
    }
    for node in &case.observe.area_nodes {
        write!(stream, ",area_{node}_cm2")?;
    }
    for node in &case.observe.minimum_area_nodes {
        write!(stream, ",minimum_area_{node}_cm2")?;
    }
    for node in &case.observe.volume_source_nodes {
        write!(stream, ",volume_source_{node}_cm3_s")?;
    }
    if !case.observe.wall_nodes.is_empty() {
        write!(stream, ",wall_radiation_flow_cm3_s")?;
        for node in &case.observe.wall_nodes {
            write!(
                stream,
                ",wall_displacement_{node}_cm,wall_velocity_{node}_cm_s,wall_flow_{node}_cm3_s"
            )?;
        }
    }
    for source in &case.observe.noise_sources {
        write!(stream, ",noise_level_{source}_dyn_cm2")?;
    }
    for [a, b] in &case.observe.noise_branches {
        write!(stream, ",noise_pressure_{a}_{b}_dyn_cm2")?;
    }
    if simulation.breath.is_some() {
        write!(stream, ",{BREATH_HEADER}")?;
    }
    if simulation.glottis.is_some() {
        write!(stream, ",{TELEMETRY_HEADER}")?;
    }
    if case.observe.glottal_f0 {
        write!(stream, ",glottal_f0_hz")?;
    }
    writeln!(stream)?;

    for index in 0..measurement.sample_count {
        let NetworkTick {
            inlet_flow,
            signal: sample,
            breath: breathing,
            glottal,
        } = simulation.step()?;
        let airway = &simulation.airway;
        write!(stream, "{index}")?;
        let values = [
            inlet_flow,
            sample.radiation_flow_cm3_s,
            sample.radiation_flow_derivative_cm3_s2,
        ]
        .into_iter()
        .chain(
            case.observe
                .pressure_nodes
                .iter()
                .map(|&node| airway.pressure(node)),
        )
        .chain(
            observed_branches
                .iter()
                .map(|&(branch, sign)| sign * airway.branch_flow(branch)),
        )
        .chain(
            case.network
                .radiators
                .iter()
                .map(|&node| airway.radiation_flow(node).unwrap()),
        )
        .chain(
            case.observe
                .area_nodes
                .iter()
                .map(|&node| airway.area(node)),
        )
        .chain(
            case.observe
                .minimum_area_nodes
                .iter()
                .map(|&node| airway.minimum_area(node)),
        )
        .chain(
            case.observe
                .volume_source_nodes
                .iter()
                .map(|&node| airway.volume_source(node)),
        )
        .chain((!case.observe.wall_nodes.is_empty()).then_some(sample.wall_radiation_flow_cm3_s))
        .chain(case.observe.wall_nodes.iter().flat_map(|&node| {
            let wall = airway.wall_motion(node);
            [wall.displacement_cm, wall.velocity_cm_s, wall.flow_cm3_s]
        }))
        .chain(
            case.observe
                .noise_sources
                .iter()
                .map(|&source| airway.noise_level(source).unwrap()),
        )
        .chain(
            observed_noise_branches
                .iter()
                .map(|&(branch, sign)| sign * airway.branch_noise_pressure(branch)),
        )
        .chain(breathing.into_iter().flat_map(|sample| {
            [
                sample.gate,
                sample.base_pressure_dyn_cm2,
                sample.filtered_flow_cm3_s,
                sample.boundary_pressure_dyn_cm2,
                sample.effort,
            ]
        }))
        .chain(
            glottal
                .into_iter()
                .flatten()
                .take(if case.observe.glottal_f0 { 5 } else { 4 }),
        );
        for value in values {
            if !value.is_finite() {
                return Err(format!("サンプル {index} の観測値が非有限です").into());
            }
            write!(stream, ",{value}")?;
        }
        writeln!(stream)?;
    }
    stream.flush()?;
    Ok(())
}
