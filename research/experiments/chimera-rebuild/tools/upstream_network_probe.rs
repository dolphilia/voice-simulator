//! 上流の気道ネットワークを構築し、公開状態から計測系列を取得する。

use chimera::airway::network::{AirwayNetwork, Area, NoiseSpec, PortSpec, TubeSpec};
use chimera::physics::WallParams;
use chimera::sources::glottis::ParametricGlottis;
use std::error::Error;
use std::f64::consts::PI;
use std::io::{self, BufWriter, Write};
use std::str::{FromStr, SplitWhitespace};

fn read<T: FromStr>(input: &mut SplitWhitespace<'_>) -> Result<T, &'static str> {
    input
        .next()
        .ok_or("比較入力の項目が不足しています")?
        .parse()
        .map_err(|_| "比較入力を数値として読み取れません")
}

struct AreaRamp {
    start: usize,
    count: usize,
    block: usize,
    targets: Vec<(usize, f64, f64)>,
}

// 固定形状の比較用。HumanVoice の私有状態に相当する呼気圧と流量を公開グラフの外で計算する。
struct ReferenceBreath {
    node: usize,
    branch: usize,
    pressure_cm_h2o: f64,
    block: usize,
    frequency: f64,
    excess: f64,
    flow_step: f64,
    steps: Vec<(usize, f64, f64, f64)>,
    cursor: usize,
    gate: f64,
    hold: f64,
    pressure: f64,
    pressure_step: f64,
    flow: f64,
}

impl ReferenceBreath {
    fn step(&mut self, sample: usize, net: &mut AirwayNetwork) -> [f64; 5] {
        use chimera::airway::network::tiny;
        use chimera::math::exp;
        use chimera::physics::CM_H2O;
        if sample % self.block == 0 {
            while self
                .steps
                .get(self.cursor + 1)
                .is_some_and(|point| point.0 <= sample)
            {
                self.cursor += 1;
            }
            let (_, performer, score, activity) = self.steps[self.cursor];
            let score_breath = score * activity;
            let goal = if score_breath < 0.0 {
                score_breath
            } else {
                performer.max(score_breath)
            };
            let dt = self.block as f64 / self.frequency;
            self.hold = if activity > 0.0 {
                0.15
            } else {
                (self.hold - dt).max(0.0)
            };
            let tau = if goal > self.gate {
                0.025
            } else if self.hold > 0.0 {
                0.02
            } else {
                0.07
            };
            self.gate += (goal - self.gate) * (1.0 - exp(-dt / tau));
            tiny(&mut self.gate);
            tiny(&mut self.flow);
            let target = self.pressure_cm_h2o * CM_H2O * self.gate;
            if target == 0.0 {
                tiny(&mut self.pressure);
            }
            self.pressure_step = (target - self.pressure) / self.block as f64;
        }
        self.pressure += self.pressure_step;
        self.flow += self.flow_step * (net.u[self.branch] - self.flow);
        let boundary = self.pressure + self.excess * self.flow;
        net.set_fixed_pressure(self.node, boundary);
        let effort = (((self.pressure_cm_h2o * self.gate).abs() - 2.2) / 10.0).clamp(0.0, 1.0);
        [self.gate, self.pressure, self.flow, boundary, effort]
    }
}

fn main() -> Result<(), Box<dyn Error>> {
    let path = std::env::args_os()
        .nth(1)
        .ok_or("上流比較用の入力ファイルが必要です")?;
    let file = std::fs::read_to_string(path)?;
    let mut input = file.split_whitespace();
    let fs: f64 = read(&mut input)?;
    let samples: usize = read(&mut input)?;
    let inlet: usize = read(&mut input)?;
    let impulse_sample: usize = read(&mut input)?;
    let impulse_volume: f64 = read(&mut input)?;
    let tubes: usize = read(&mut input)?;
    let mut network = AirwayNetwork::new(fs);
    let mut connections = Vec::new();
    let mut tube_ranges = Vec::new();
    let mut initial_areas = Vec::new();
    let mut wall_radiation_fractions = Vec::new();
    let mut lengths = Vec::new();
    let mut perimeter_factors = Vec::new();
    for i in 0..tubes {
        let length: f64 = read(&mut input)?;
        let cells: usize = read(&mut input)?;
        let areas: Vec<f64> = (0..cells)
            .map(|_| read(&mut input))
            .collect::<Result<_, _>>()?;
        let start = initial_areas.len();
        initial_areas.extend(&areas);
        let perimeter = read(&mut input)?;
        let viscosity = read(&mut input)?;
        let mut spec = TubeSpec::new(&format!("probe{i}"), cells, length, Area::Profile(areas))
            .perimeter(perimeter)
            .viscous(viscosity);
        let mut radiation_fraction = 0.0;
        if read::<u8>(&mut input)? != 0 {
            let wall = WallParams {
                mass: read(&mut input)?,
                resistance: read(&mut input)?,
                stiffness: read(&mut input)?,
            };
            radiation_fraction = read(&mut input)?;
            spec = spec.wall(Some(wall)).radiating(radiation_fraction);
        }
        wall_radiation_fractions.extend(std::iter::repeat_n(radiation_fraction, cells));
        lengths.extend(std::iter::repeat_n(length / cells as f64, cells));
        perimeter_factors.extend(std::iter::repeat_n(perimeter, cells));
        let tube = network.add_tube(spec);
        connections.extend(
            (0..cells.saturating_sub(1))
                .map(|node| (tube.node(node), tube.node(node + 1), tube.branch(node))),
        );
        tube_ranges.push((tube, start..start + cells));
    }
    for _ in 0..read::<usize>(&mut input)? {
        let a = read(&mut input)?;
        let b = read(&mut input)?;
        connections.push((a, b, network.connect(a, b)));
    }
    let mut radiators = Vec::new();
    for _ in 0..read::<usize>(&mut input)? {
        let node = read(&mut input)?;
        radiators.push((node, network.add_radiation(node)));
    }
    let mut pressure_nodes = Vec::new();
    for _ in 0..read::<usize>(&mut input)? {
        pressure_nodes.push(read::<usize>(&mut input)?);
    }
    let mut branch_nodes = Vec::new();
    for _ in 0..read::<usize>(&mut input)? {
        branch_nodes.push((read(&mut input)?, read(&mut input)?));
    }
    let mut area_nodes = Vec::new();
    for _ in 0..read::<usize>(&mut input)? {
        area_nodes.push(read::<usize>(&mut input)?);
    }
    let mut minimum_area_nodes = Vec::new();
    for _ in 0..read::<usize>(&mut input)? {
        minimum_area_nodes.push(read::<usize>(&mut input)?);
    }
    let wall_nodes: Vec<usize> = (0..read::<usize>(&mut input)?)
        .map(|_| read(&mut input))
        .collect::<Result<_, _>>()?;
    let mut ramps = Vec::new();
    for _ in 0..read::<usize>(&mut input)? {
        let start = read(&mut input)?;
        let count = read(&mut input)?;
        let block = read(&mut input)?;
        let mut targets = Vec::new();
        for _ in 0..read::<usize>(&mut input)? {
            targets.push((read(&mut input)?, read(&mut input)?, read(&mut input)?));
        }
        ramps.push(AreaRamp {
            start,
            count,
            block,
            targets,
        });
    }
    let mut drives = Vec::new();
    for i in 0..read::<usize>(&mut input)? {
        let pressure: f64 = read(&mut input)?;
        let ramp: usize = read(&mut input)?;
        let node = network.add_pressure_node(&format!("pressure{i}"));
        drives.push((node, pressure, ramp));
        wall_radiation_fractions.push(0.0);
        lengths.push(1.0);
        perimeter_factors.push(1.0);
    }
    for _ in 0..read::<usize>(&mut input)? {
        let a = read(&mut input)?;
        let b = read(&mut input)?;
        let area = read(&mut input)?;
        let length = read(&mut input)?;
        let entrance = read(&mut input)?;
        let expansion = read(&mut input)?;
        let slit = read(&mut input)?;
        let include_half = read::<u8>(&mut input)? != 0;
        let extra = read(&mut input)?;
        let mut port = PortSpec::new(area, length)
            .kinetic(entrance, expansion)
            .slit(slit)
            .resistance(extra);
        if !include_half {
            port = port.no_half_sections();
        }
        connections.push((a, b, network.add_port(a, b, port)));
    }
    let mut observed_branches = Vec::new();
    for (a, b) in branch_nodes {
        let (index, sign) = connections
            .iter()
            .find_map(|&(left, right, index)| {
                if (left, right) == (a, b) {
                    Some((index, 1.0))
                } else if (left, right) == (b, a) {
                    Some((index, -1.0))
                } else {
                    None
                }
            })
            .ok_or("上流ネットワークに計測対象の枝がありません")?;
        observed_branches.push((a, b, index, sign));
    }
    network.noise_scale = read(&mut input)?;
    let directed = |a, b| {
        connections
            .iter()
            .find_map(|&(left, right, id)| ((a, b) == (left, right)).then_some(id))
            .ok_or("上流の乱流源の枝が存在しません")
    };
    let mut sources = Vec::new();
    for _ in 0..read::<usize>(&mut input)? {
        let source = directed(read(&mut input)?, read(&mut input)?)?;
        let forward = directed(read(&mut input)?, read(&mut input)?)?;
        let reverse = directed(read(&mut input)?, read(&mut input)?)?;
        let gain = read(&mut input)?;
        sources.push(
            NoiseSpec::new(source, forward, reverse, gain)
                .band(read(&mut input)?, read(&mut input)?),
        );
    }
    let observed_noise: Vec<usize> = (0..read::<usize>(&mut input)?)
        .map(|_| read(&mut input))
        .collect::<Result<_, _>>()?;
    let mut observe_glottal_f0 = false;
    let mut glottal_drive = if read::<u8>(&mut input)? != 0 {
        let a = read(&mut input)?;
        let b = read(&mut input)?;
        let branch = directed(a, b)?;
        let mut source = ParametricGlottis::new(fs);
        source.params.f0 = read(&mut input)?;
        source.params.amplitude = read(&mut input)?;
        source.params.chink = read(&mut input)?;
        source.params.open_quotient = read(&mut input)?;
        source.params.open_with_abduction = read(&mut input)?;
        source.params.skew = read(&mut input)?;
        source.params.closure_sharpness = read(&mut input)?;
        source.params.effort = read(&mut input)?;
        source.params.closure = read(&mut input)?;
        source.threshold = read(&mut input)?;
        source.params.jitter = read(&mut input)?;
        source.params.shimmer = read(&mut input)?;
        source.params.drift = read(&mut input)?;
        source.params.vibrato_depth = read(&mut input)?;
        source.params.vibrato_rate = read(&mut input)?;
        source.params.fry = read(&mut input)?;
        source.params.diplophonia = read(&mut input)?;
        source.params.chaos = read(&mut input)?;
        observe_glottal_f0 = read::<u8>(&mut input)? != 0;
        let steps: Vec<(usize, f64)> = (0..read::<usize>(&mut input)?)
            .map(|_| Ok((read(&mut input)?, read(&mut input)?)))
            .collect::<Result<_, &'static str>>()?;
        Some((a, b, branch, source, steps, 0))
    } else {
        None
    };
    let mut breath = if read::<u8>(&mut input)? != 0 {
        let node = read(&mut input)?;
        let branch = directed(node, read(&mut input)?)?;
        let pressure_cm_h2o = read(&mut input)?;
        let scale: f64 = read(&mut input)?;
        let block = read(&mut input)?;
        let extra: f64 = read(&mut input)?;
        let compensate = read::<u8>(&mut input)? != 0;
        let excess = if compensate {
            extra - (0.8 * chimera::physics::CM_H2O / 1000.0) / (scale * scale * scale)
        } else {
            0.0
        };
        let steps = (0..read::<usize>(&mut input)?)
            .map(|_| {
                Ok((
                    read(&mut input)?,
                    read(&mut input)?,
                    read(&mut input)?,
                    read(&mut input)?,
                ))
            })
            .collect::<Result<_, &'static str>>()?;
        Some(ReferenceBreath {
            node,
            branch,
            pressure_cm_h2o,
            block,
            frequency: fs,
            excess,
            flow_step: 1.0 - chimera::math::exp((-excess * scale / 5.2e-3) / fs),
            steps,
            cursor: 0,
            gate: 0.0,
            hold: 0.0,
            pressure: 0.0,
            pressure_step: 0.0,
            flow: 0.0,
        })
    } else {
        None
    };
    if input.next().is_some() {
        return Err("比較入力に余分な項目があります".into());
    }

    let has_wall_radiation = wall_radiation_fractions
        .iter()
        .any(|&fraction| fraction != 0.0);
    network.finalize();
    network.set_noise_sources(&sources);
    network.begin_block(1);
    let mut output = BufWriter::new(io::stdout().lock());
    write!(
        output,
        "sample,inlet_flow_cm3_s,radiation_flow_cm3_s,radiation_flow_derivative_cm3_s2"
    )?;
    for node in &pressure_nodes {
        write!(output, ",pressure_{node}_dyn_cm2")?;
    }
    for (a, b, _, _) in &observed_branches {
        write!(output, ",branch_flow_{a}_{b}_cm3_s")?;
    }
    for (node, _) in &radiators {
        write!(output, ",radiation_{node}_cm3_s")?;
    }
    for node in &area_nodes {
        write!(output, ",area_{node}_cm2")?;
    }
    for node in &minimum_area_nodes {
        write!(output, ",minimum_area_{node}_cm2")?;
    }
    if !wall_nodes.is_empty() {
        write!(output, ",wall_radiation_flow_cm3_s")?;
        for node in &wall_nodes {
            write!(
                output,
                ",wall_displacement_{node}_cm,wall_velocity_{node}_cm_s,wall_flow_{node}_cm3_s"
            )?;
        }
    }
    for source in &observed_noise {
        write!(output, ",noise_level_{source}_dyn_cm2")?;
    }
    if breath.is_some() {
        write!(
            output,
            ",breath_gate,breath_base_pressure_dyn_cm2,breath_filtered_flow_cm3_s,breath_boundary_pressure_dyn_cm2,breath_effort"
        )?;
    }
    if glottal_drive.is_some() {
        write!(
            output,
            ",glottal_area_cm2,glottal_pressure_drop_dyn_cm2,glottal_voicing,glottal_phase"
        )?;
    }
    if observe_glottal_f0 {
        write!(output, ",glottal_f0_hz")?;
    }
    writeln!(output)?;
    let mut cursor = 0;
    let mut next_update = ramps.first().map_or(samples, |ramp| ramp.start);
    let mut holding_block = 1;
    let mut initial_minimums = initial_areas.clone();
    let mut target_areas = initial_areas.clone();
    let mut target_minimums = initial_minimums.clone();
    for i in 0..samples {
        if i == next_update {
            if let Some(ramp) = ramps.get(cursor)
                && i == ramp.start + ramp.count
            {
                for &(node, mean, minimum) in &ramp.targets {
                    initial_areas[node] = mean;
                    initial_minimums[node] = minimum;
                }
                holding_block = ramp.block;
                cursor += 1;
            }
            let block = match ramps.get(cursor) {
                Some(ramp) if i >= ramp.start => {
                    let elapsed = i - ramp.start;
                    let block = ramp.block.min(ramp.count - elapsed);
                    let fraction = (elapsed + block) as f64 / ramp.count as f64;
                    for &(node, mean, minimum) in &ramp.targets {
                        let start_mean = initial_areas[node];
                        let start_minimum = initial_minimums[node];
                        target_areas[node] = start_mean + (mean - start_mean) * fraction;
                        target_minimums[node] =
                            start_minimum + (minimum - start_minimum) * fraction;
                    }
                    for (tube, cells) in &tube_ranges {
                        network.set_tube_targets(
                            *tube,
                            &target_areas[cells.clone()],
                            None,
                            Some(&target_minimums[cells.clone()]),
                        );
                    }
                    block
                }
                Some(ramp) => holding_block.min(ramp.start - i),
                None => holding_block,
            };
            network.begin_block(block);
            next_update = i + block;
        }
        let flow = if i == impulse_sample {
            impulse_volume * fs
        } else {
            0.0
        };
        network.ext_flow[inlet] = flow;
        for &(node, pressure, ramp) in &drives {
            if breath.as_ref().is_some_and(|control| control.node == node) {
                continue;
            }
            let fraction = if i >= ramp {
                1.0
            } else {
                i as f64 / ramp as f64
            };
            network.set_fixed_pressure(node, pressure * fraction);
        }
        let breathing = breath.as_mut().map(|breath| breath.step(i, &mut network));
        let glottal = glottal_drive
            .as_mut()
            .map(|(a, b, branch, source, steps, cursor)| {
                if steps.get(*cursor + 1).is_some_and(|step| step.0 == i) {
                    *cursor += 1;
                }
                source.params.abduction = steps[*cursor].1;
                if let Some([_, _, _, _, effort]) = breathing {
                    source.params.effort = effort;
                }
                let pressure_drop = network.p[*a] - network.p[*b];
                let area = source.next(pressure_drop);
                network.set_port_area(*branch, area);
                [
                    area,
                    pressure_drop,
                    source.voicing,
                    source.cycle_phase(),
                    source.f0_now,
                ]
            });
        let derivative = network.step();
        let wall_radiation = has_wall_radiation.then(|| -> f64 {
            network
                .wall_u
                .iter()
                .zip(&wall_radiation_fractions)
                .map(|(flow, fraction)| flow * fraction)
                .sum()
        });
        let radiation: f64 = radiators
            .iter()
            .map(|&(_, id)| network.radiated_flow(id))
            .sum();
        let radiation = wall_radiation.map_or(radiation, |wall| radiation + wall);
        write!(output, "{i},{flow},{radiation},{derivative}")?;
        for &node in &pressure_nodes {
            write!(output, ",{}", network.p[node])?;
        }
        for &(_, _, index, sign) in &observed_branches {
            write!(output, ",{}", sign * network.u[index])?;
        }
        for &(_, id) in &radiators {
            write!(output, ",{}", network.radiated_flow(id))?;
        }
        for &node in &area_nodes {
            write!(output, ",{}", network.area[node])?;
        }
        for &node in &minimum_area_nodes {
            write!(output, ",{}", network.amin[node])?;
        }
        if !wall_nodes.is_empty() {
            write!(output, ",{}", wall_radiation.unwrap_or(0.0))?;
            for &node in &wall_nodes {
                let surface = 2.0
                    * (PI * network.area[node].max(0.02)).sqrt()
                    * lengths[node]
                    * perimeter_factors[node];
                let flow = network.wall_u[node];
                write!(
                    output,
                    ",{},{},{flow}",
                    network.wall_y[node],
                    flow / surface
                )?;
            }
        }
        for &source in &observed_noise {
            write!(output, ",{}", network.noise_sources()[source].level)?;
        }
        if let Some([gate, pressure, flow, boundary, effort]) = breathing {
            write!(output, ",{gate},{pressure},{flow},{boundary},{effort}")?;
        }
        if let Some([area, drop, gate, phase, f0]) = glottal {
            write!(output, ",{area},{drop},{gate},{phase}")?;
            if observe_glottal_f0 {
                write!(output, ",{f0}")?;
            }
        }
        writeln!(output)?;
    }
    output.flush()?;
    Ok(())
}
