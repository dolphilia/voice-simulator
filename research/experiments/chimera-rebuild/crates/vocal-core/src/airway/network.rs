//! 気道グラフの接続と、可動断面・節点・枝の更新。物理量は CGS。

use super::frequency::{LinearBranch, LinearElements, LinearNode, LinearWall};
use super::{
    AIR_DENSITY, DYNAMIC_VISCOSITY, PI, RadiationLoad, SOUND_SPEED, WallMotion, WallParameters,
    radiation_coefficients, trim_tiny, viscous_factor,
};
use std::collections::HashSet;

mod geometry;
mod turbulence;
use geometry::MovingAreas;
pub use turbulence::NoiseSpec;
use turbulence::Turbulence;

const MIN_CELL_AREA_CM2: f64 = 0.02;
const CLOSED_AREA_CM2: f64 = 0.0002;

#[derive(Clone, Copy, Debug)]
pub struct Section {
    pub length_cm: f64,
    pub area_cm2: f64,
    pub minimum_area_cm2: f64,
    pub perimeter_factor: f64,
    pub viscous_factor: f64,
    pub wall: Option<WallParameters>,
}

impl Section {
    fn volume(self) -> f64 {
        self.area_cm2.max(MIN_CELL_AREA_CM2) * self.length_cm
    }

    fn is_closed(self) -> bool {
        self.minimum_area_cm2 < CLOSED_AREA_CM2
    }

    fn wall_surface(self) -> f64 {
        2.0 * (PI * self.area_cm2.max(MIN_CELL_AREA_CM2)).sqrt()
            * self.length_cm
            * self.perimeter_factor
    }
}

#[derive(Clone, Copy, Debug)]
pub struct JunctionCompliance {
    pub geometric: f64,
    pub effective: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct Port {
    pub nodes: [usize; 2],
    pub length_cm: f64,
    pub area_cm2: f64,
    pub entrance_loss: f64,
    pub expansion_loss: f64,
    pub slit_width_cm: f64,
    pub include_half_sections: bool,
    pub extra_resistance: f64,
}

pub struct Boundaries<'a> {
    pub radiation_nodes: &'a [usize],
    pub fixed_pressure_nodes: &'a [usize],
    pub ports: &'a [Port],
}

struct Branch {
    nodes: [usize; 2],
    port: Option<Port>,
    area_cm2: f64,
    inertance: f64,
    resistance: f64,
    forward_loss: f64,
    reverse_loss: f64,
    flow: f64,
    previous_inertance: f64,
}

fn branch_impedance(
    left: Section,
    right: Section,
    port: Option<Port>,
    viscosity: f64,
) -> (f64, f64) {
    let half_sections = 0.5
        * AIR_DENSITY
        * (left.length_cm / left.area_cm2.max(1e-6) + right.length_cm / right.area_cm2.max(1e-6));
    match port {
        Some(port) => {
            let inverse = 1.0 / port.area_cm2;
            let half = if port.include_half_sections {
                half_sections
            } else {
                0.0
            };
            let inertance = AIR_DENSITY * port.length_cm * inverse + half;
            let duct_resistance = if port.slit_width_cm > 0.0 {
                12.0 * DYNAMIC_VISCOSITY
                    * port.length_cm
                    * port.slit_width_cm.powi(2)
                    * inverse.powi(3)
            } else {
                2.0 * viscosity
                    * PI.sqrt()
                    * port.length_cm
                    * port.area_cm2.sqrt()
                    * inverse.powi(2)
            };
            (inertance, duct_resistance + port.extra_resistance)
        }
        None => {
            let lateral_resistance = |section: Section| {
                2.0 * (PI * section.area_cm2).sqrt() * section.length_cm / section.area_cm2.powi(2)
                    * section.perimeter_factor
                    * section.viscous_factor
            };
            (
                half_sections,
                0.5 * viscosity * (lateral_resistance(left) + lateral_resistance(right)),
            )
        }
    }
}

impl Branch {
    fn new(nodes: [usize; 2], port: Option<Port>, sections: &[Section], viscosity: f64) -> Self {
        let [left, right] = nodes.map(|index| sections[index]);
        let area_cm2 = port.map_or(left.minimum_area_cm2.min(right.minimum_area_cm2), |port| {
            port.area_cm2
        });
        if area_cm2 < CLOSED_AREA_CM2 {
            return Self {
                nodes,
                port,
                area_cm2,
                inertance: 0.0,
                resistance: 0.0,
                forward_loss: 0.0,
                reverse_loss: 0.0,
                flow: 0.0,
                previous_inertance: 0.0,
            };
        }
        let (inertance, resistance) = branch_impedance(left, right, port, viscosity);
        let expansion = |inverse_area_difference: f64| {
            0.5 * AIR_DENSITY * inverse_area_difference.max(0.0).powi(2)
        };
        let (forward_loss, reverse_loss) = match port {
            Some(port) => {
                let inverse = 1.0 / port.area_cm2;
                let entry = port.entrance_loss * 0.5 * AIR_DENSITY * inverse.powi(2);
                let loss = |downstream: Section| {
                    entry
                        + port.expansion_loss
                            * expansion(inverse - 1.0 / downstream.area_cm2.max(1e-6))
                };
                (loss(right), loss(left))
            }
            None => {
                let forward = expansion(1.0 / left.minimum_area_cm2 - 1.0 / right.area_cm2);
                let reverse = expansion(1.0 / right.minimum_area_cm2 - 1.0 / left.area_cm2);
                (forward + 0.1 * reverse, reverse + 0.1 * forward)
            }
        };
        Self {
            nodes,
            port,
            area_cm2,
            inertance,
            resistance,
            forward_loss,
            reverse_loss,
            flow: 0.0,
            previous_inertance: inertance,
        }
    }

    fn update_geometry(&mut self, sections: &[Section], viscosity: f64) {
        let next = Self::new(self.nodes, self.port, sections, viscosity);
        *self = Self {
            flow: if next.inertance > 0.0 { self.flow } else { 0.0 },
            previous_inertance: self.inertance,
            ..next
        };
    }

    fn step(&mut self, dt: f64, pressure_difference: f64) -> f64 {
        let inertance_per_step = self.inertance / dt;
        // 慣性が増すときは運動量、減るときは流量を引き継ぐ。
        let carried_inertance = self.previous_inertance.min(self.inertance);
        let drive = pressure_difference + (carried_inertance / dt) * self.flow;
        let linear = inertance_per_step + self.resistance;
        let loss = if drive >= 0.0 {
            self.forward_loss
        } else {
            self.reverse_loss
        };
        self.flow = if loss == 0.0 {
            drive / linear
        } else {
            2.0 * drive / (linear + (linear * linear + 4.0 * loss * drive.abs()).sqrt())
        };
        self.previous_inertance = self.inertance;
        self.flow
    }
}

pub struct NetworkSample {
    pub radiation_flow_cm3_s: f64,
    pub radiation_flow_derivative_cm3_s2: f64,
    pub wall_radiation_flow_cm3_s: f64,
}

pub struct AirwayNetwork {
    dt: f64,
    sections: Vec<Section>,
    neighbors: Vec<Vec<usize>>,
    moving_areas: MovingAreas,
    branches: Vec<Branch>,
    port_areas_changed: bool,
    port_area_increments_cm2: Vec<f64>,
    turbulence: Turbulence,
    compliance: Vec<JunctionCompliance>,
    inverse_inertance_sum: Vec<f64>,
    pressure: Vec<f64>,
    net_flow: Vec<f64>,
    fixed_pressure: Vec<bool>,
    wall_motion: Vec<WallMotion>,
    radiators: Vec<Option<RadiationLoad>>,
    previous_radiation_flow: f64,
}

impl AirwayNetwork {
    pub fn new(
        sample_rate_hz: u32,
        sections: &[Section],
        connections: &[[usize; 2]],
        boundaries: Boundaries<'_>,
    ) -> Result<Self, &'static str> {
        if sample_rate_hz == 0 || sections.is_empty() {
            return Err("正のサンプルレートと少なくとも一つのセルが必要です");
        }
        let dt = 1.0 / f64::from(sample_rate_hz);
        let n = sections.len();
        let mut compliance = Vec::with_capacity(n);
        for section in sections {
            if !section.perimeter_factor.is_finite()
                || section.perimeter_factor < 1.0
                || !section.viscous_factor.is_finite()
                || section.viscous_factor < 0.0
            {
                return Err("円周倍率は1以上、粘性倍率は0以上の有限値で指定してください");
            }
            if let Some(wall) = section.wall {
                wall.validate()?;
            }
            let courant = SOUND_SPEED * dt / section.length_cm;
            if !(0.0 < courant && courant < 1.0) {
                return Err("節点のクーラン数 c·Δt/Δx は 0 より大きく 1 未満である必要があります");
            }
            if !section.area_cm2.is_finite()
                || !(0.0..=section.area_cm2).contains(&section.minimum_area_cm2)
            {
                return Err("平均断面積は有限、最小断面積は 0 以上かつ平均以下にしてください");
            }
            let geometric = section.volume() / (AIR_DENSITY * SOUND_SPEED * SOUND_SPEED);
            if !geometric.is_finite() {
                return Err("節点コンプライアンスが非有限です");
            }
            compliance.push(JunctionCompliance {
                geometric,
                effective: geometric,
            });
        }

        let mut neighbors = vec![Vec::new(); n];
        let mut branch_keys = HashSet::new();
        let mut branches = Vec::with_capacity(connections.len() + boundaries.ports.len());
        let viscosity = viscous_factor();
        for ([left, right], port) in connections
            .iter()
            .copied()
            .map(|nodes| (nodes, None))
            .chain(
                boundaries
                    .ports
                    .iter()
                    .map(|&port| (port.nodes, Some(port))),
            )
        {
            if left >= n || right >= n || left == right {
                return Err("枝は異なる実在節点で接続してください");
            }
            if !branch_keys.insert((left.min(right), left.max(right))) {
                return Err("同じ二節点への重複接続があります");
            }
            if let Some(port) = port
                && (!(port.length_cm.is_finite() && port.length_cm > 0.0)
                    || [
                        port.area_cm2,
                        port.entrance_loss,
                        port.expansion_loss,
                        port.slit_width_cm,
                        port.extra_resistance,
                    ]
                    .into_iter()
                    .any(|value| !value.is_finite() || value < 0.0))
            {
                return Err("ポートの長さには有限の正値、他の係数には有限の非負値が必要です");
            }
            let branch = Branch::new([left, right], port, sections, viscosity);
            if ![
                branch.inertance,
                branch.resistance,
                branch.forward_loss,
                branch.reverse_loss,
            ]
            .into_iter()
            .all(f64::is_finite)
            {
                return Err("枝から有限かつ正の音響素子を計算できません");
            }
            neighbors[left].push(right);
            neighbors[right].push(left);
            branches.push(branch);
        }

        let mut fixed_pressure = vec![false; n];
        for &node in boundaries.fixed_pressure_nodes {
            let flag = fixed_pressure
                .get_mut(node)
                .ok_or("固定圧力の節点が存在しません")?;
            if *flag {
                return Err("固定圧力の指定が重複しています");
            }
            *flag = true;
        }
        let mut radiators: Vec<_> = (0..n).map(|_| None).collect();
        for &node in boundaries.radiation_nodes {
            let load = radiators
                .get_mut(node)
                .ok_or("放射端の節点が存在しません")?;
            if load.is_some() {
                return Err("放射端の指定が重複しています");
            }
            if fixed_pressure[node] {
                return Err("固定圧力の節点を放射端に指定できません");
            }
            let (inertance, resistance) =
                radiation_coefficients(sections[node].area_cm2.max(1.0e-4));
            if ![inertance, resistance]
                .into_iter()
                .all(|value| value.is_finite() && value > 0.0)
            {
                return Err("放射端から有限かつ正の音響素子を計算できません");
            }
            *load = Some(RadiationLoad::new(inertance, resistance));
        }

        let mut network = Self {
            dt,
            sections: sections.to_vec(),
            neighbors,
            moving_areas: MovingAreas::new(sections, dt),
            turbulence: Turbulence::new(sample_rate_hz, branches.len()),
            port_area_increments_cm2: vec![0.0; branches.len()],
            branches,
            port_areas_changed: false,
            compliance,
            inverse_inertance_sum: vec![0.0; n],
            radiators,
            pressure: vec![0.0; n],
            net_flow: vec![0.0; n],
            fixed_pressure,
            wall_motion: vec![WallMotion::default(); n],
            previous_radiation_flow: 0.0,
        };
        network.update_compliance();
        Ok(network)
    }

    fn update_compliance(&mut self) {
        self.inverse_inertance_sum.fill(0.0);
        for branch in &self.branches {
            if branch.inertance > 0.0 {
                let reciprocal = 1.0 / branch.inertance;
                for index in branch.nodes {
                    self.inverse_inertance_sum[index] += reciprocal;
                }
            }
        }
        for (index, node) in self.compliance.iter_mut().enumerate() {
            let geometric =
                self.sections[index].volume() / (AIR_DENSITY * SOUND_SPEED * SOUND_SPEED);
            let effective = if self.neighbors[index].len() >= 3 {
                geometric.max(self.dt * self.dt * self.inverse_inertance_sum[index] / 2.4)
            } else {
                geometric
            };
            *node = JunctionCompliance {
                geometric,
                effective,
            };
        }
    }

    /// 現断面を始点に、次の steps サンプルで指定面積へ線形補間する。
    pub fn set_area_targets(
        &mut self,
        areas_cm2: &[[f64; 2]],
        steps: usize,
    ) -> Result<(), &'static str> {
        self.set_geometry_targets(areas_cm2, None, &[], steps)
    }

    /// 断面、セル長、ポート面積を同じ内部サンプル数で補間する。
    /// 長さを省略した場合と表にないポートは、現在値を保つ。
    pub fn set_geometry_targets(
        &mut self,
        areas_cm2: &[[f64; 2]],
        lengths_cm: Option<&[f64]>,
        ports: &[(usize, f64)],
        steps: usize,
    ) -> Result<(), &'static str> {
        for (index, &(branch, area)) in ports.iter().enumerate() {
            if !self.is_port(branch) || !area.is_finite() || area < 0.0 {
                return Err("補間先は実在するポートと有限の非負面積で指定してください");
            }
            if ports[..index].iter().any(|&(other, _)| branch == other) {
                return Err("ポートの補間先が重複しています");
            }
        }
        self.moving_areas
            .set_targets(&self.sections, areas_cm2, lengths_cm, steps, self.dt)?;
        self.port_area_increments_cm2.fill(0.0);
        let scale = 1.0 / steps as f64;
        for &(branch, area) in ports {
            let current = self.branches[branch]
                .port
                .expect("検証済みのポート")
                .area_cm2;
            self.port_area_increments_cm2[branch] = (area - current) * scale;
        }
        Ok(())
    }

    pub fn area(&self, node: usize) -> f64 {
        self.sections[node].area_cm2
    }

    pub fn section(&self, node: usize) -> Section {
        self.sections[node]
    }

    pub fn branch_count(&self) -> usize {
        self.branches.len()
    }

    /// 現在の固定形状から、流量が微小なときの線形要素を取り出す。
    pub fn linear_elements(&self) -> LinearElements {
        let nodes = self
            .sections
            .iter()
            .enumerate()
            .map(|(index, section)| LinearNode {
                compliance: self.compliance[index].geometric,
                wall: section.wall.map(|parameters| LinearWall {
                    area_cm2: section.wall_surface(),
                    parameters,
                }),
                fixed_pressure: self.fixed_pressure[index],
                radiation: self.radiators[index].as_ref().map(|_| {
                    let (inertance, resistance) =
                        radiation_coefficients(section.area_cm2.max(1e-4));
                    [inertance, resistance]
                }),
            })
            .collect();
        let viscosity = viscous_factor();
        let branches = self
            .branches
            .iter()
            .map(|branch| {
                let [left, right] = branch.nodes.map(|index| self.sections[index]);
                // 較正時の開閉は、両側の代表面積またはポート面積で判定する。
                let opening = branch
                    .port
                    .map_or(left.area_cm2.min(right.area_cm2), |port| port.area_cm2);
                let open = opening >= CLOSED_AREA_CM2;
                let (inertance, resistance) = if open {
                    branch_impedance(left, right, branch.port, viscosity)
                } else {
                    (0.0, 0.0)
                };
                LinearBranch {
                    nodes: branch.nodes,
                    inertance,
                    resistance,
                    open,
                }
            })
            .collect();
        LinearElements { nodes, branches }
    }

    pub fn courant(&self) -> f64 {
        let shortest = self
            .sections
            .iter()
            .zip(&self.fixed_pressure)
            .filter(|(_, fixed)| !**fixed)
            .map(|(section, _)| section.length_cm)
            .fold(f64::INFINITY, f64::min);
        SOUND_SPEED * self.dt / shortest
    }

    pub fn minimum_area(&self, node: usize) -> f64 {
        self.sections[node].minimum_area_cm2
    }

    pub fn set_fixed_pressure(
        &mut self,
        node: usize,
        pressure_dyn_cm2: f64,
    ) -> Result<(), &'static str> {
        if self.fixed_pressure.get(node) != Some(&true) || !pressure_dyn_cm2.is_finite() {
            return Err("固定圧力の節点番号と有限の圧力値を指定してください");
        }
        self.pressure[node] = pressure_dyn_cm2;
        Ok(())
    }

    pub fn volume_source(&self, node: usize) -> f64 {
        self.moving_areas.filtered_flow(node)
    }

    pub fn compliance(&self, node: usize) -> JunctionCompliance {
        self.compliance[node]
    }

    pub fn pressure(&self, node: usize) -> f64 {
        self.pressure[node]
    }

    pub fn branch_area(&self, branch: usize) -> f64 {
        self.branches[branch].area_cm2
    }

    pub fn branch_flow(&self, branch: usize) -> f64 {
        self.branches[branch].flow
    }

    /// 指定したポートの断面積を、次の枝更新に反映する。
    pub fn set_port_area(&mut self, branch: usize, area_cm2: f64) -> Result<(), &'static str> {
        if !area_cm2.is_finite() || area_cm2 < 0.0 {
            return Err("ポートの断面積は有限の非負値で指定してください");
        }
        let port = self
            .branches
            .get_mut(branch)
            .and_then(|branch| branch.port.as_mut())
            .ok_or("断面積の変更先は実在するポートで指定してください")?;
        self.port_areas_changed |= port.area_cm2 != area_cm2;
        port.area_cm2 = area_cm2;
        self.port_area_increments_cm2[branch] = 0.0;
        Ok(())
    }

    pub fn port_area(&self, branch: usize) -> Option<f64> {
        self.branches.get(branch)?.port.map(|port| port.area_cm2)
    }

    pub fn is_port(&self, branch: usize) -> bool {
        self.branches
            .get(branch)
            .is_some_and(|branch| branch.port.is_some())
    }

    pub fn set_noise_seed(&mut self, seed: u32) {
        self.turbulence.set_seed(seed);
    }

    pub fn set_noise_scale(&mut self, scale: f64) -> Result<(), &'static str> {
        self.turbulence.set_scale(scale)
    }

    pub(super) fn reserve_noise_sources(&mut self, count: usize) {
        self.turbulence.reserve_sources(count);
    }

    pub fn set_noise_sources(&mut self, sources: &[NoiseSpec]) -> Result<(), &'static str> {
        self.turbulence.set_sources(sources)
    }

    pub(super) fn set_noise_gain(&mut self, source: usize, gain: f64) -> Result<(), &'static str> {
        self.turbulence.set_gain(source, gain)
    }

    pub fn noise_spec(&self, source: usize) -> Option<NoiseSpec> {
        self.turbulence.spec(source)
    }

    pub fn noise_level(&self, source: usize) -> Option<f64> {
        self.turbulence.level(source)
    }

    pub fn branch_noise_pressure(&self, branch: usize) -> f64 {
        self.turbulence.pressure[branch]
    }

    pub fn radiation_flow(&self, node: usize) -> Option<f64> {
        self.radiators[node].as_ref().map(|load| load.flow)
    }

    pub fn wall_motion(&self, node: usize) -> WallMotion {
        self.wall_motion[node]
    }

    /// 動物音声の制御境界で無励振に近い気道の履歴を整理する。
    pub(super) fn trim_creature_tail(&mut self) {
        let quiet = self
            .pressure
            .iter()
            .zip(&self.fixed_pressure)
            .all(|(&pressure, &fixed)| fixed || pressure.abs() < 1e-9)
            && self.branches.iter().all(|branch| branch.flow.abs() < 1e-9);
        for ((pressure, fixed), wall) in self
            .pressure
            .iter_mut()
            .zip(&self.fixed_pressure)
            .zip(&mut self.wall_motion)
        {
            if !fixed {
                if quiet {
                    *pressure = 0.0;
                } else {
                    trim_tiny(pressure);
                }
            }
            if quiet {
                wall.velocity_cm_s = 0.0;
                if wall.displacement_cm.abs() < 1e-12 {
                    wall.displacement_cm = 0.0;
                }
            }
            trim_tiny(&mut wall.displacement_cm);
            trim_tiny(&mut wall.velocity_cm_s);
        }
        for branch in &mut self.branches {
            if quiet {
                branch.flow = 0.0;
            } else {
                trim_tiny(&mut branch.flow);
            }
        }
        for load in self.radiators.iter_mut().flatten() {
            if quiet {
                load.inertance_flow = 0.0;
            } else {
                trim_tiny(&mut load.inertance_flow);
            }
            trim_tiny(&mut load.flow);
        }
        self.moving_areas.trim_tiny_flow();
        trim_tiny(&mut self.previous_radiation_flow);
    }

    /// 有効な入口の節点番号と一ステップ分の注入流量を受け取る。更新中にメモリ確保しない。
    pub fn step(&mut self, inlet: usize, inlet_flow_cm3_s: f64) -> NetworkSample {
        self.step_with_prescribed_flow(inlet, inlet_flow_cm3_s, None)
    }

    pub(crate) fn step_with_prescribed_flow(
        &mut self,
        inlet: usize,
        inlet_flow_cm3_s: f64,
        prescribed: Option<(usize, f64)>,
    ) -> NetworkSample {
        // 乱流が読むのは、断面を変更する前の枝面積と最後に解いた流量。
        self.turbulence.step(&self.branches);
        self.net_flow.fill(0.0);
        self.net_flow[inlet] = inlet_flow_cm3_s;
        let sections_changed = self.moving_areas.step(
            &mut self.sections,
            &self.neighbors,
            self.dt,
            &mut self.net_flow,
        );
        if sections_changed || self.port_areas_changed {
            let viscosity = viscous_factor();
            for (branch, &increment) in self.branches.iter_mut().zip(&self.port_area_increments_cm2)
            {
                if sections_changed
                    && increment != 0.0
                    && let Some(port) = &mut branch.port
                {
                    port.area_cm2 = (port.area_cm2 + increment).max(0.0);
                }
                if sections_changed
                    || branch
                        .port
                        .is_some_and(|port| port.area_cm2 != branch.area_cm2)
                {
                    branch.update_geometry(&self.sections, viscosity);
                }
            }
            if sections_changed {
                for (node, load) in self.radiators.iter_mut().enumerate() {
                    if let Some(load) = load
                        && !self.sections[node].is_closed()
                    {
                        load.update_aperture(self.sections[node].area_cm2);
                    }
                }
            }
            self.update_compliance();
            self.port_areas_changed = false;
        }
        for (index, (branch, &noise)) in self
            .branches
            .iter_mut()
            .zip(&self.turbulence.pressure)
            .enumerate()
        {
            let [left, right] = branch.nodes;
            // 指定流量を元の枝と同じ順序・符号で両端の体積収支に加える。
            if let Some((_, flow)) = prescribed.filter(|&(source, _)| source == index) {
                branch.flow = flow;
                self.net_flow[left] -= flow;
                self.net_flow[right] += flow;
                continue;
            }
            if branch.inertance == 0.0 {
                continue;
            }
            let mut difference = self.pressure[left] - self.pressure[right];
            if noise != 0.0 {
                difference += noise;
            }
            let flow = branch.step(self.dt, difference);
            self.net_flow[left] -= flow;
            self.net_flow[right] += flow;
        }

        let mut wall_radiation = 0.0;
        for (node, section) in self.sections.iter().enumerate() {
            if let Some(wall) = section.wall {
                // 壁面積は今の平均断面で求め、閉鎖時にも下限を設ける。
                let surface = section.wall_surface();
                let flow = self.wall_motion[node].step(wall, self.dt, surface, self.pressure[node]);
                self.net_flow[node] -= flow;
                wall_radiation += wall.radiation_fraction * flow;
            }
        }

        let mut radiation_flow = wall_radiation;
        for node in 0..self.sections.len() {
            if self.fixed_pressure[node] {
                continue;
            }
            let compliance = self.compliance[node].effective;
            let inflow = self.net_flow[node];
            if self.sections[node].is_closed() {
                if let Some(load) = &mut self.radiators[node] {
                    self.pressure[node] *= 0.98;
                    load.close();
                    radiation_flow += load.flow;
                } else {
                    let mut sum = 0.0;
                    let mut count = 0;
                    for &other in &self.neighbors[node] {
                        if !self.sections[other].is_closed() {
                            sum += self.pressure[other];
                            count += 1;
                        }
                    }
                    if count > 0 {
                        self.pressure[node] +=
                            0.02 * (sum / f64::from(count) - self.pressure[node]);
                    }
                }
            } else if let Some(load) = &mut self.radiators[node] {
                self.pressure[node] = load.step(self.dt, compliance, self.pressure[node], inflow);
                radiation_flow += load.flow;
            } else {
                self.pressure[node] += self.dt / compliance * inflow;
            }
        }
        let derivative = (radiation_flow - self.previous_radiation_flow) / self.dt;
        self.previous_radiation_flow = radiation_flow;
        NetworkSample {
            radiation_flow_cm3_s: radiation_flow,
            radiation_flow_derivative_cm3_s2: derivative,
            wall_radiation_flow_cm3_s: wall_radiation,
        }
    }
}
