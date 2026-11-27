//! 固定気道の連続時間線形モデル。節点・枝を木として求解する。

use super::TAU;
use std::ops::{Add, Div, Mul, Sub};

#[derive(Clone, Copy, Debug, Default)]
pub struct Phasor {
    pub real: f64,
    pub imaginary: f64,
}

impl Phasor {
    const ONE: Self = Self::new(1.0, 0.0);

    const fn new(real: f64, imaginary: f64) -> Self {
        Self { real, imaginary }
    }

    pub fn magnitude(self) -> f64 {
        self.real.hypot(self.imaginary)
    }

    fn is_finite(self) -> bool {
        self.real.is_finite() && self.imaginary.is_finite()
    }
}

impl Add for Phasor {
    type Output = Self;

    fn add(self, other: Self) -> Self {
        Self::new(self.real + other.real, self.imaginary + other.imaginary)
    }
}

impl Sub for Phasor {
    type Output = Self;

    fn sub(self, other: Self) -> Self {
        Self::new(self.real - other.real, self.imaginary - other.imaginary)
    }
}

impl Mul for Phasor {
    type Output = Self;

    fn mul(self, other: Self) -> Self {
        Self::new(
            self.real * other.real - self.imaginary * other.imaginary,
            self.real * other.imaginary + self.imaginary * other.real,
        )
    }
}

impl Mul<f64> for Phasor {
    type Output = Self;

    fn mul(self, scale: f64) -> Self {
        Self::new(self.real * scale, self.imaginary * scale)
    }
}

impl Div for Phasor {
    type Output = Self;

    fn div(self, other: Self) -> Self {
        let denominator = other.real * other.real + other.imaginary * other.imaginary;
        Self::new(
            (self.real * other.real + self.imaginary * other.imaginary) / denominator,
            (self.imaginary * other.real - self.real * other.imaginary) / denominator,
        )
    }
}

#[derive(Clone, Copy, Debug)]
pub struct LinearWall {
    pub area_cm2: f64,
    pub parameters: super::WallParameters,
}

#[derive(Clone, Copy, Debug)]
pub struct LinearNode {
    pub compliance: f64,
    pub wall: Option<LinearWall>,
    pub fixed_pressure: bool,
    /// 放射負荷の慣性と抵抗。
    pub radiation: Option<[f64; 2]>,
}

#[derive(Clone, Copy, Debug)]
pub struct LinearBranch {
    pub nodes: [usize; 2],
    pub inertance: f64,
    pub resistance: f64,
    pub open: bool,
}

pub struct LinearElements {
    pub nodes: Vec<LinearNode>,
    pub branches: Vec<LinearBranch>,
}

pub struct TransferPoint {
    pub frequency_hz: f64,
    pub total: Phasor,
    /// 放射節点番号の昇順。注入源から切り離された端の応答は0。
    pub radiators: Vec<Phasor>,
    pub wall: Phasor,
}

impl TransferPoint {
    pub fn pressure_db(&self) -> f64 {
        20.0 * (TAU * self.frequency_hz.max(1e-3) * self.total.magnitude() + 1e-30).log10()
    }
}

impl LinearElements {
    /// 注入単位流量から放射流量への応答。枝番号で切断を指定する。
    pub fn transfer(
        &self,
        inject: usize,
        cut: &[usize],
        frequencies_hz: &[f64],
    ) -> Result<Vec<TransferPoint>, &'static str> {
        if inject >= self.nodes.len() || cut.iter().any(|&edge| edge >= self.branches.len()) {
            return Err("注入節点と切断枝は実在する番号を指定してください");
        }
        if frequencies_hz
            .iter()
            .any(|&frequency| !frequency.is_finite() || frequency <= 0.0)
        {
            return Err("周波数には有限の正値を指定してください");
        }
        let mut adjacency = vec![Vec::new(); self.nodes.len()];
        for (index, branch) in self.branches.iter().enumerate() {
            if branch.open && !cut.contains(&index) {
                let [a, b] = branch.nodes;
                adjacency[a].push((b, index));
                adjacency[b].push((a, index));
            }
        }
        let mut parent = vec![None; self.nodes.len()];
        let mut order = vec![inject];
        let mut cursor = 0;
        while let Some(&node) = order.get(cursor) {
            for &(next, edge) in &adjacency[node] {
                if parent[node].is_some_and(|(_, incoming)| incoming == edge) {
                    continue;
                }
                if next == inject || parent[next].is_some() {
                    return Err(
                        "線形伝達の計算には注入節点から到達できる回路が木である必要があります",
                    );
                }
                parent[next] = Some((node, edge));
                order.push(next);
            }
            cursor += 1;
        }

        let n = self.nodes.len();
        let radiators: Vec<_> = self
            .nodes
            .iter()
            .enumerate()
            .filter_map(|(index, node)| node.radiation.map(|_| index))
            .collect();
        let mut admittance = vec![Phasor::default(); n];
        let mut equivalent = vec![Phasor::default(); n];
        let mut pressure = vec![Phasor::default(); n];
        let mut wall_y = vec![Phasor::default(); n];
        let mut radiation_y = vec![Phasor::default(); n];
        let mut response = Vec::with_capacity(frequencies_hz.len());

        for &frequency in frequencies_hz {
            let omega = TAU * frequency.max(1e-3);
            let impedance = |edge: usize| {
                let branch = self.branches[edge];
                Phasor::new(branch.resistance, omega * branch.inertance)
            };

            for &index in &order {
                let node = self.nodes[index];
                let grounded = if node.fixed_pressure { 1e30 } else { 0.0 };
                wall_y[index] = node.wall.map_or(Phasor::default(), |wall| {
                    let p = wall.parameters;
                    Phasor::new(wall.area_cm2, 0.0)
                        / Phasor::new(
                            p.resistance_dyn_s_cm3,
                            omega * p.mass_g_cm2 - p.stiffness_dyn_cm3 / omega,
                        )
                });
                radiation_y[index] =
                    node.radiation
                        .map_or(Phasor::default(), |[inertance, resistance]| {
                            Phasor::new(1.0 / resistance, -1.0 / (omega * inertance))
                        });
                admittance[index] = Phasor::new(grounded, omega * node.compliance)
                    + wall_y[index]
                    + radiation_y[index];
            }
            // 子の節点アドミタンスを、枝を含む親から見た値へ換算する。
            for &node in order[1..].iter().rev() {
                let (up, edge) = parent[node].expect("根以外は親を持つ");
                let y = admittance[node];
                equivalent[node] = y / (Phasor::ONE + impedance(edge) * y);
                admittance[up] = admittance[up] + equivalent[node];
            }

            pressure[inject] = Phasor::ONE / admittance[inject];
            let mut wall = Phasor::default();
            for &node in &order {
                if let Some((up, edge)) = parent[node] {
                    let flow = pressure[up] * equivalent[node];
                    pressure[node] = pressure[up] - impedance(edge) * flow;
                }
                if let Some(parameters) = self.nodes[node].wall.map(|wall| wall.parameters) {
                    wall = wall + pressure[node] * wall_y[node] * parameters.radiation_fraction;
                }
            }
            let end_flows: Vec<_> = radiators
                .iter()
                .map(|&node| pressure[node] * radiation_y[node])
                .collect();
            let total = end_flows.iter().fold(wall, |sum, &flow| sum + flow);
            if !total.is_finite()
                || !wall.is_finite()
                || end_flows.iter().any(|flow| !flow.is_finite())
            {
                return Err("指定周波数の気道の線形伝達関数が有限範囲を超えました");
            }
            response.push(TransferPoint {
                frequency_hz: frequency,
                total,
                radiators: end_flows,
                wall,
            });
        }
        Ok(response)
    }
}
