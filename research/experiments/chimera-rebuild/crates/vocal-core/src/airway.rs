//! 固定した円形一様管と振動する管壁の CGS 音響モデル。

use std::f64::consts::{PI, TAU};

pub mod alligator;
pub mod elephant;
pub mod frequency;
pub mod human;
mod mammal;
pub mod network;
pub mod seal;
pub mod songbird;
pub mod tract_control;

const AIR_DENSITY: f64 = 1.14e-3;
const SOUND_SPEED: f64 = 35_000.0;
const DYNAMIC_VISCOSITY: f64 = 1.86e-4;
const VISCOSITY_REFERENCE_HZ: f64 = 700.0;

pub(crate) fn trim_tiny(value: &mut f64) {
    if value.abs() < 1e-30 {
        *value = 0.0;
    }
}

/// 一つのパラメータを定義したキーだけを使い、最後のキー以降は値を保持する。
fn sample_call_curve(keys: &[(f64, f64)], elapsed: f64) -> Option<f64> {
    sample_call_curve_with(keys, elapsed, |_, from, to, part| from + (to - from) * part)
}

fn sample_call_curve_with(
    keys: &[(f64, f64)],
    elapsed: f64,
    mix: impl Fn(usize, f64, f64, f64) -> f64,
) -> Option<f64> {
    let (&(first, first_value), rest) = keys.split_first()?;
    if elapsed < first {
        return None;
    }
    let mut previous = (first, first_value);
    for (index, &(next, next_value)) in rest.iter().enumerate() {
        if elapsed < next {
            let (time, value) = previous;
            return Some(mix(
                index + 1,
                value,
                next_value,
                (elapsed - time) / (next - time),
            ));
        }
        previous = (next, next_value);
    }
    Some(previous.1)
}

fn viscous_factor() -> f64 {
    (AIR_DENSITY * DYNAMIC_VISCOSITY * TAU * VISCOSITY_REFERENCE_HZ / 2.0).sqrt()
}

fn radiation_coefficients(area_cm2: f64) -> (f64, f64) {
    let inertance = 8.0 * AIR_DENSITY / (3.0 * PI * (PI * area_cm2).sqrt());
    let resistance = 128.0 * AIR_DENSITY * SOUND_SPEED / (9.0 * PI * PI * area_cm2);
    (inertance, resistance)
}

struct RadiationLoad {
    inertance: f64,
    resistance: f64,
    inertance_flow: f64,
    flow: f64,
}

struct OutletHalfCell {
    inertance: f64,
    flow: f64,
}

impl RadiationLoad {
    fn new(inertance: f64, resistance: f64) -> Self {
        Self {
            inertance,
            resistance,
            inertance_flow: 0.0,
            flow: 0.0,
        }
    }

    /// 終端セルと並列 R–L 負荷を中点で接続する。
    fn step(&mut self, dt: f64, compliance: f64, old_pressure: f64, inflow: f64) -> f64 {
        let old_load_flow = self.inertance_flow;
        let half_conductance = 0.5 / self.resistance;
        let half_inertance_gain = dt / (2.0 * self.inertance);
        let compliance_per_step = compliance / dt;
        let load = half_conductance + 0.5 * half_inertance_gain;
        let new_pressure = (old_pressure * (compliance_per_step - load) + inflow - old_load_flow)
            / (compliance_per_step + load);
        let pressure_sum = old_pressure + new_pressure;
        self.inertance_flow = old_load_flow + half_inertance_gain * pressure_sum;
        self.flow = 0.5 * (old_load_flow + self.inertance_flow) + half_conductance * pressure_sum;
        new_pressure
    }

    /// 直列の半セル、圧縮性と放射負荷を一つの中点更新で解く。
    fn step_with_half_cell(
        &mut self,
        series: &mut OutletHalfCell,
        dt: f64,
        compliance: f64,
        old_pressure: f64,
        inflow: f64,
    ) -> (f64, f64) {
        let half_dt = 0.5 * dt;
        let compliance_gain = half_dt / compliance;
        let series_impedance = series.inertance / half_dt;
        let midpoint_impedance = 1.0 / (1.0 / self.resistance + half_dt / self.inertance);
        let series_mid = (old_pressure
            + compliance_gain * inflow
            + series_impedance * series.flow
            + midpoint_impedance * self.inertance_flow)
            / (compliance_gain + series_impedance + midpoint_impedance);
        let load_pressure_mid = midpoint_impedance * (series_mid - self.inertance_flow);
        self.inertance_flow += dt / self.inertance * load_pressure_mid;
        self.flow = series_mid;
        series.flow = 2.0 * series_mid - series.flow;
        let next_pressure = old_pressure + dt / compliance * (inflow - series_mid);
        (next_pressure, load_pressure_mid)
    }

    fn update_aperture(&mut self, area_cm2: f64) {
        let (inertance, resistance) = radiation_coefficients(area_cm2);
        if inertance > self.inertance {
            self.inertance_flow *= self.inertance / inertance;
        }
        self.inertance = inertance;
        self.resistance = resistance;
    }

    fn close(&mut self) {
        self.inertance_flow *= 0.995;
        self.flow = self.inertance_flow;
    }
}

#[derive(Clone, Copy, Debug)]
pub struct TubeGeometry {
    pub length_cm: f64,
    pub area_cm2: f64,
    pub cells: usize,
    pub sample_rate_hz: u32,
}

#[derive(Clone, Copy, Debug)]
pub struct TubeCoefficients {
    pub cell_length_cm: f64,
    pub step_seconds: f64,
    pub courant: f64,
    pub cell_compliance: f64,
    pub branch_inertance: f64,
    pub branch_resistance: f64,
    pub radiation_inertance: f64,
    pub radiation_resistance: f64,
}

impl TubeCoefficients {
    /// 管内の枝の粘性抵抗にだけ倍率を適用する。終端の放射抵抗は元の値を使う。
    pub fn with_viscous_scale(mut self, scale: f64) -> Result<Self, &'static str> {
        let resistance = self.branch_resistance * scale;
        if scale < 0.0 || !resistance.is_finite() {
            return Err("管内粘性の倍率と適用後の枝抵抗には有限の非負値が必要です");
        }
        self.branch_resistance = resistance;
        Ok(self)
    }
}

impl TubeGeometry {
    pub fn coefficients(self) -> Result<TubeCoefficients, &'static str> {
        if !self.length_cm.is_finite() || self.length_cm <= 0.0 {
            return Err("管長には有限の正値が必要です");
        }
        // 上流のコンプライアンスに断面積の下限が適用される領域は可動断面の段階で扱う。
        if !self.area_cm2.is_finite() || self.area_cm2 < 0.02 {
            return Err("固定管の断面積は有限かつ 0.02 cm² 以上で指定してください");
        }
        if self.cells < 2 || self.sample_rate_hz == 0 {
            return Err("セル数は 2 以上、サンプルレートは正値で指定してください");
        }

        let area = self.area_cm2;
        let dx = self.length_cm / self.cells as f64;
        let dt = 1.0 / f64::from(self.sample_rate_hz);
        let courant = SOUND_SPEED * dt / dx;
        if !(0.0 < courant && courant < 1.0) {
            return Err("固定管のクーラン数 c·Δt/Δx は 0 より大きく 1 未満である必要があります");
        }

        let perimeter = 2.0 * (PI * area).sqrt();
        let viscous = viscous_factor();
        let (radiation_inertance, radiation_resistance) = radiation_coefficients(area);
        let coefficients = TubeCoefficients {
            cell_length_cm: dx,
            step_seconds: dt,
            courant,
            cell_compliance: (area * dx) / (AIR_DENSITY * SOUND_SPEED * SOUND_SPEED),
            branch_inertance: AIR_DENSITY * dx / area,
            branch_resistance: (viscous * perimeter) * (dx / area) / area,
            radiation_inertance,
            radiation_resistance,
        };
        if ![
            coefficients.cell_compliance,
            coefficients.branch_inertance,
            coefficients.branch_resistance,
            coefficients.radiation_inertance,
            coefficients.radiation_resistance,
        ]
        .into_iter()
        .all(|value| value.is_finite() && value > 0.0)
        {
            return Err("管の形状から有限かつ正の音響素子を計算できません");
        }
        Ok(coefficients)
    }
}

#[derive(Clone, Copy, Debug)]
pub struct AirwaySample {
    pub inlet_pressure_dyn_cm2: f64,
    pub outlet_pressure_dyn_cm2: f64,
    pub outlet_branch_flow_cm3_s: f64,
    pub radiation_load_pressure_mid_dyn_cm2: f64,
    pub radiation_flow_cm3_s: f64,
    pub radiation_flow_derivative_cm3_s2: f64,
    pub wall: Option<WallSample>,
}

pub struct TubeEnergySample {
    pub stored_energy_erg: f64,
    pub half_cell_flow_cm3_s: f64,
    pub radiation_inertance_flow_cm3_s: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct WallParameters {
    pub mass_g_cm2: f64,
    pub resistance_dyn_s_cm3: f64,
    pub stiffness_dyn_cm3: f64,
    pub radiation_fraction: f64,
}

impl WallParameters {
    pub fn validate(self) -> Result<(), &'static str> {
        if !self.mass_g_cm2.is_finite()
            || self.mass_g_cm2 <= 0.0
            || !self.resistance_dyn_s_cm3.is_finite()
            || self.resistance_dyn_s_cm3 < 0.0
            || !self.stiffness_dyn_cm3.is_finite()
            || self.stiffness_dyn_cm3 < 0.0
        {
            return Err("壁の質量は有限の正値、抵抗と剛性は有限の非負値で指定してください");
        }
        if !(0.0..=1.0).contains(&self.radiation_fraction) {
            return Err("壁の放射割合は 0 以上 1 以下で指定してください");
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug)]
pub struct WallSample {
    pub inlet_wall_flow_cm3_s: f64,
    pub outlet_wall_flow_cm3_s: f64,
    pub total_wall_flow_cm3_s: f64,
    pub wall_radiation_flow_cm3_s: f64,
    pub inlet_branch_flow_cm3_s: f64,
    pub outlet_branch_flow_cm3_s: f64,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct WallMotion {
    pub displacement_cm: f64,
    pub velocity_cm_s: f64,
    pub flow_cm3_s: f64,
}

impl WallMotion {
    fn step(&mut self, wall: WallParameters, dt: f64, surface_cm2: f64, old_pressure: f64) -> f64 {
        let mass_per_step = wall.mass_g_cm2 / dt;
        let half_resistance = 0.5 * wall.resistance_dyn_s_cm3;
        let restoring_pressure = wall.stiffness_dyn_cm3 * self.displacement_cm;
        self.velocity_cm_s = ((mass_per_step - half_resistance) * self.velocity_cm_s
            + old_pressure
            - restoring_pressure)
            / (mass_per_step + half_resistance);
        self.displacement_cm += dt * self.velocity_cm_s;
        self.flow_cm3_s = surface_cm2 * self.velocity_cm_s;
        self.flow_cm3_s
    }
}

struct TubeWall {
    parameters: WallParameters,
    cell_surface_cm2: f64,
    cells: Vec<WallMotion>,
}

impl TubeWall {
    fn step(&mut self, step_seconds: f64, pressures: &[f64]) -> f64 {
        let mut wall_flow = 0.0;
        for (cell, &pressure) in self.cells.iter_mut().zip(pressures) {
            wall_flow += cell.step(
                self.parameters,
                step_seconds,
                self.cell_surface_cm2,
                pressure,
            );
        }
        wall_flow
    }
}

pub struct UniformTube {
    coefficients: TubeCoefficients,
    pressures: Vec<f64>,
    branch_flows: Vec<f64>,
    radiation: RadiationLoad,
    outlet_half_cell: Option<OutletHalfCell>,
    previous_radiation_flow: f64,
    wall: Option<TubeWall>,
}

impl UniformTube {
    pub fn new(geometry: TubeGeometry) -> Result<Self, &'static str> {
        let coefficients = geometry.coefficients()?;
        Ok(Self {
            coefficients,
            pressures: vec![0.0; geometry.cells],
            branch_flows: vec![0.0; geometry.cells - 1],
            radiation: RadiationLoad::new(
                coefficients.radiation_inertance,
                coefficients.radiation_resistance,
            ),
            outlet_half_cell: None,
            previous_radiation_flow: 0.0,
            wall: None,
        })
    }

    pub fn with_wall(geometry: TubeGeometry, wall: WallParameters) -> Result<Self, &'static str> {
        wall.validate()?;
        let mut tube = Self::new(geometry)?;
        tube.wall = Some(TubeWall {
            parameters: wall,
            cell_surface_cm2: 2.0
                * (PI * geometry.area_cm2).sqrt()
                * tube.coefficients.cell_length_cm,
            cells: vec![WallMotion::default(); geometry.cells],
        });
        Ok(tube)
    }

    pub fn with_viscous_scale(mut self, scale: f64) -> Result<Self, &'static str> {
        self.coefficients = self.coefficients.with_viscous_scale(scale)?;
        Ok(self)
    }

    /// 最後のセル中心と並列R–L負荷の間に、半セル長の直列慣性を置く。
    pub fn with_outlet_half_cell(mut self) -> Result<Self, &'static str> {
        let inertance = 0.5 * self.coefficients.branch_inertance;
        if inertance <= 0.0 {
            return Err("口端半セルの慣性は正値が必要です");
        }
        self.outlet_half_cell = Some(OutletHalfCell {
            inertance,
            flow: 0.0,
        });
        Ok(self)
    }

    /// 剛体かつ管内粘性なしの場合の離散エネルギーを、現在の圧力時刻で測る。
    /// 管内枝は圧力時刻を挟む二つの半時刻の流量の積で評価する。
    pub fn lossless_energy(&self) -> Option<TubeEnergySample> {
        let k = self.coefficients;
        if self.wall.is_some() || k.branch_resistance != 0.0 {
            return None;
        }
        let compression =
            0.5 * k.cell_compliance * self.pressures.iter().map(|p| p * p).sum::<f64>();
        let internal_flow_product: f64 = self
            .branch_flows
            .iter()
            .zip(self.pressures.windows(2))
            .map(|(&flow, p)| {
                let next_flow = flow + (k.step_seconds / k.branch_inertance) * (p[0] - p[1]);
                flow * next_flow
            })
            .sum();
        let internal = 0.5 * k.branch_inertance * internal_flow_product;
        let (half_cell_flow, half_cell_energy) =
            self.outlet_half_cell.as_ref().map_or((0.0, 0.0), |s| {
                (s.flow, 0.5 * s.inertance * s.flow * s.flow)
            });
        let radiation_flow = self.radiation.inertance_flow;
        let radiation_energy = 0.5 * self.radiation.inertance * radiation_flow * radiation_flow;
        Some(TubeEnergySample {
            stored_energy_erg: compression + internal + half_cell_energy + radiation_energy,
            half_cell_flow_cm3_s: half_cell_flow,
            radiation_inertance_flow_cm3_s: radiation_flow,
        })
    }

    pub fn step(&mut self, inlet_flow_cm3_s: f64) -> AirwaySample {
        let k = self.coefficients;
        let inertia_per_step = k.branch_inertance / k.step_seconds;
        let flow_denominator = inertia_per_step + k.branch_resistance;
        for (flow, pressure_pair) in self.branch_flows.iter_mut().zip(self.pressures.windows(2)) {
            let pressure_difference = pressure_pair[0] - pressure_pair[1];
            *flow = (pressure_difference + inertia_per_step * *flow) / flow_denominator;
        }

        let wall_total_flow = self
            .wall
            .as_mut()
            .map_or(0.0, |wall| wall.step(k.step_seconds, &self.pressures));
        let wall = self.wall.as_ref();
        let pressure_scale = k.step_seconds / k.cell_compliance;
        let last_node = self.pressures.len() - 1;
        let mut incoming = inlet_flow_cm3_s;
        for (index, (pressure, &outgoing)) in self.pressures[..last_node]
            .iter_mut()
            .zip(&self.branch_flows)
            .enumerate()
        {
            let wall_flow = wall.map_or(0.0, |wall| wall.cells[index].flow_cm3_s);
            *pressure += pressure_scale * (incoming - outgoing - wall_flow);
            incoming = outgoing;
        }

        // 終端セルと放射負荷を中点で接続し、圧力と慣性枝流量の新しい値を求める。
        let outlet_wall_flow = wall.map_or(0.0, |wall| wall.cells[last_node].flow_cm3_s);
        let outlet_inflow = incoming - outlet_wall_flow;
        let old_pressure = self.pressures[last_node];
        let (new_pressure, load_pressure_mid) = match &mut self.outlet_half_cell {
            Some(series) => self.radiation.step_with_half_cell(
                series,
                k.step_seconds,
                k.cell_compliance,
                old_pressure,
                outlet_inflow,
            ),
            None => {
                let next = self.radiation.step(
                    k.step_seconds,
                    k.cell_compliance,
                    old_pressure,
                    outlet_inflow,
                );
                (next, 0.5 * (old_pressure + next))
            }
        };
        self.pressures[last_node] = new_pressure;
        let wall_sample = wall.map(|wall| WallSample {
            inlet_wall_flow_cm3_s: wall.cells[0].flow_cm3_s,
            outlet_wall_flow_cm3_s: outlet_wall_flow,
            total_wall_flow_cm3_s: wall_total_flow,
            wall_radiation_flow_cm3_s: wall_total_flow * wall.parameters.radiation_fraction,
            inlet_branch_flow_cm3_s: self.branch_flows[0],
            outlet_branch_flow_cm3_s: incoming,
        });
        let radiation_flow =
            self.radiation.flow + wall_sample.map_or(0.0, |obs| obs.wall_radiation_flow_cm3_s);
        let derivative = (radiation_flow - self.previous_radiation_flow) / k.step_seconds;
        self.previous_radiation_flow = radiation_flow;
        AirwaySample {
            inlet_pressure_dyn_cm2: self.pressures[0],
            outlet_pressure_dyn_cm2: new_pressure,
            outlet_branch_flow_cm3_s: incoming,
            radiation_load_pressure_mid_dyn_cm2: load_pressure_mid,
            radiation_flow_cm3_s: radiation_flow,
            radiation_flow_derivative_cm3_s2: derivative,
            wall: wall_sample,
        }
    }
}
