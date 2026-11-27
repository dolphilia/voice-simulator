//! 調音目標への臨界減衰追従。可動域と係数はCHIMERA由来（MIT）。

use serde::Serialize;
use std::f64::consts::TAU;

use crate::anatomy::{Articulation, Point, RoofContact, resting_tip};

pub const ARTICULATOR_COUNT: usize = 17;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum Articulator {
    Jaw,
    TongueBodyX,
    TongueBodyY,
    TongueTipX,
    TongueTipY,
    TipCurl,
    TongueRoot,
    LipAperture,
    LipProtrusion,
    LipSpread,
    Labiodental,
    Velum,
    Larynx,
    Epilarynx,
    Ventricular,
    Lateral,
    Dorsum,
}

#[derive(Clone, Copy, Debug)]
pub struct ArticulatorSpec {
    pub minimum: f64,
    pub maximum: f64,
    pub natural_frequency_hz: f64,
    pub unit: &'static str,
}

const fn spec(
    minimum: f64,
    maximum: f64,
    natural_frequency_hz: f64,
    unit: &'static str,
) -> ArticulatorSpec {
    ArticulatorSpec {
        minimum,
        maximum,
        natural_frequency_hz,
        unit,
    }
}

const SPECS: [ArticulatorSpec; ARTICULATOR_COUNT] = [
    spec(-0.1, 2.6, 10.0, "cm"),
    spec(1.0, 4.8, 12.0, "cm"),
    spec(4.8, 9.2, 12.0, "cm"),
    spec(3.5, 8.0, 13.0, "cm"),
    spec(5.0, 10.8, 13.0, "cm"),
    spec(0.0, 1.0, 9.0, "1"),
    spec(-1.0, 1.0, 9.0, "cm"),
    spec(-0.4, 2.4, 11.0, "cm"),
    spec(-0.2, 1.5, 11.0, "cm"),
    spec(0.0, 1.0, 11.0, "1"),
    spec(0.0, 1.0, 10.0, "1"),
    spec(-0.25, 1.4, 12.0, "cm2"),
    spec(-1.6, 1.6, 8.0, "cm"),
    spec(0.0, 1.0, 6.0, "1"),
    spec(0.0, 1.0, 6.0, "1"),
    spec(0.0, 1.0, 10.0, "1"),
    spec(0.0, 1.0, 9.0, "1"),
];

const NAMES: [&str; ARTICULATOR_COUNT] = [
    "jaw_cm",
    "tongue_body_x_cm",
    "tongue_body_y_cm",
    "tongue_tip_x_cm",
    "tongue_tip_y_cm",
    "tip_curl",
    "tongue_root_cm",
    "lip_aperture_cm",
    "lip_protrusion_cm",
    "lip_spread",
    "labiodental",
    "velum_cm2",
    "larynx_cm",
    "epilarynx",
    "ventricular",
    "lateral",
    "dorsum",
];

impl Articulator {
    pub const ALL: [Self; ARTICULATOR_COUNT] = [
        Self::Jaw,
        Self::TongueBodyX,
        Self::TongueBodyY,
        Self::TongueTipX,
        Self::TongueTipY,
        Self::TipCurl,
        Self::TongueRoot,
        Self::LipAperture,
        Self::LipProtrusion,
        Self::LipSpread,
        Self::Labiodental,
        Self::Velum,
        Self::Larynx,
        Self::Epilarynx,
        Self::Ventricular,
        Self::Lateral,
        Self::Dorsum,
    ];

    pub fn index(self) -> usize {
        self as usize
    }

    pub fn name(self) -> &'static str {
        NAMES[self.index()]
    }

    pub fn spec(self) -> ArticulatorSpec {
        SPECS[self.index()]
    }

    pub fn from_name(name: &str) -> Option<Self> {
        NAMES
            .iter()
            .position(|&key| key == name)
            .map(|i| Self::ALL[i])
    }
}

#[derive(Clone, Copy, Debug, Serialize)]
pub struct BlendedTarget {
    pub value: f64,
    pub weight: f64,
    pub speed: f64,
}

impl Default for BlendedTarget {
    fn default() -> Self {
        Self {
            value: 0.0,
            weight: 0.0,
            speed: 1.0,
        }
    }
}

impl BlendedTarget {
    pub fn validate(self) -> Result<(), &'static str> {
        if !self.value.is_finite()
            || !self.weight.is_finite()
            || self.weight < 0.0
            || !self.speed.is_finite()
            || self.speed < 0.0
        {
            return Err("合成目標は有限値、重みと速度倍率は有限の非負値を指定してください");
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug)]
pub struct ArticulatorState {
    pub position: f64,
    pub velocity: f64,
    pub target: f64,
    pub effective: f64,
    pub base_speed: f64,
    pub applied_speed: f64,
}

impl Articulation {
    /// `Articulator::ALL` の順に並んだ値を矢状面モデルへ渡す。
    pub fn from_axis_values(values: [f64; ARTICULATOR_COUNT]) -> Self {
        use Articulator::*;
        let position = |key: Articulator| values[key.index()];
        Self {
            jaw_cm: position(Jaw),
            tongue_body_cm: Point::new(position(TongueBodyX), position(TongueBodyY)),
            tongue_tip_cm: Point::new(position(TongueTipX), position(TongueTipY)),
            tip_curl: position(TipCurl),
            tongue_root_cm: position(TongueRoot),
            lip_aperture_cm: position(LipAperture),
            lip_protrusion_cm: position(LipProtrusion),
            lip_spread: position(LipSpread),
            labiodental: position(Labiodental),
            velum_cm2: position(Velum),
            larynx_cm: position(Larynx),
            epilarynx: position(Epilarynx),
            ventricular: position(Ventricular),
            lateral: position(Lateral),
            dorsum: position(Dorsum),
        }
    }
}

pub struct ArticulatorBank {
    states: [ArticulatorState; ARTICULATOR_COUNT],
    tip_free: bool,
}

impl ArticulatorBank {
    /// 指定姿勢を可動域へ収め、速度0で初期化する。
    pub fn new(initial: Articulation, tip_free: bool) -> Result<Self, &'static str> {
        let positions = [
            initial.jaw_cm,
            initial.tongue_body_cm.x,
            initial.tongue_body_cm.y,
            initial.tongue_tip_cm.x,
            initial.tongue_tip_cm.y,
            initial.tip_curl,
            initial.tongue_root_cm,
            initial.lip_aperture_cm,
            initial.lip_protrusion_cm,
            initial.lip_spread,
            initial.labiodental,
            initial.velum_cm2,
            initial.larynx_cm,
            initial.epilarynx,
            initial.ventricular,
            initial.lateral,
            initial.dorsum,
        ];
        if positions.iter().any(|value| !value.is_finite()) {
            return Err("調音器の初期姿勢には有限値を指定してください");
        }
        let states = Articulator::ALL.map(|key| {
            let bounds = key.spec();
            let position = positions[key.index()].clamp(bounds.minimum, bounds.maximum);
            ArticulatorState {
                position,
                velocity: 0.0,
                target: position,
                effective: position,
                base_speed: 1.0,
                applied_speed: 1.0,
            }
        });
        Ok(Self { states, tip_free })
    }

    pub fn state(&self, key: Articulator) -> ArticulatorState {
        self.states[key.index()]
    }

    pub fn posture(&self) -> Articulation {
        Articulation::from_axis_values(self.states.map(|state| state.position))
    }

    /// 体型の座標で測った接触を基準座標に戻し、接触面へ向かう速度を除く。
    pub fn enforce_tongue_contacts(
        &mut self,
        tip: RoofContact,
        body: RoofContact,
        body_scale: f64,
    ) -> bool {
        let penetration_limit_cm = -0.1 * body_scale;
        let mut changed = false;
        for (probe, x_key, y_key) in [
            (tip, Articulator::TongueTipX, Articulator::TongueTipY),
            (body, Articulator::TongueBodyX, Articulator::TongueBodyY),
        ] {
            if probe.distance_cm >= penetration_limit_cm {
                continue;
            }
            let mut x = self.state(x_key);
            let mut y = self.state(y_key);
            let x_scale = (if x.position > 0.5 { 1.0 / 0.86 } else { 1.0 }) / body_scale;
            let y_scale = 1.0 / body_scale;
            let depth = penetration_limit_cm - probe.distance_cm;
            x.position += probe.normal.x * depth * x_scale;
            y.position += probe.normal.y * depth * y_scale;
            let inward =
                x.velocity * probe.normal.x / x_scale + y.velocity * probe.normal.y / y_scale;
            if inward < 0.0 {
                x.velocity -= inward * probe.normal.x * x_scale;
                y.velocity -= inward * probe.normal.y * y_scale;
            }
            self.states[x_key.index()] = x;
            self.states[y_key.index()] = y;
            changed = true;
        }
        changed
    }

    /// 指定した成分だけ基準目標を変える。
    pub fn set_target(&mut self, key: Articulator, value: f64) {
        if value.is_finite() {
            let bounds = key.spec();
            self.states[key.index()].target = value.clamp(bounds.minimum, bounds.maximum);
        }
    }

    pub fn set_speed(&mut self, key: Articulator, speed: f64) -> Result<(), &'static str> {
        if !speed.is_finite() || speed < 0.0 {
            return Err("速度倍率には有限の非負値を指定してください");
        }
        self.states[key.index()].base_speed = speed;
        Ok(())
    }

    pub fn set_tip_free(&mut self, free: bool) {
        self.tip_free = free;
    }

    pub fn tip_free(&self) -> bool {
        self.tip_free
    }

    pub fn step(
        &mut self,
        dt: f64,
        blends: &[BlendedTarget; ARTICULATOR_COUNT],
        base_weight: f64,
    ) -> Result<(), &'static str> {
        if !dt.is_finite() || dt <= 0.0 || !base_weight.is_finite() || base_weight < 0.0 {
            return Err("正の制御時間幅と有限の非負の基準重みを指定してください");
        }
        let mut next = self.states;
        if self.tip_free {
            let jaw = self.state(Articulator::Jaw).position;
            let body = Point::new(
                self.state(Articulator::TongueBodyX).position,
                self.state(Articulator::TongueBodyY).position,
            );
            let tip = resting_tip(jaw, body);
            next[Articulator::TongueTipX.index()].target = tip.x;
            next[Articulator::TongueTipY.index()].target = tip.y;
        }
        for ((key, state), &blend) in Articulator::ALL.into_iter().zip(&mut next).zip(blends) {
            blend.validate()?;
            let bounds = key.spec();
            let mut target = state.target;
            let mut speed = state.base_speed;
            if blend.weight > 0.0 {
                target = if key == Articulator::Velum {
                    target + (blend.weight / 2.0).min(1.0) * (blend.value - target)
                } else {
                    (target * base_weight + blend.value * blend.weight)
                        / (base_weight + blend.weight)
                };
                speed *= blend.speed;
            }
            if !target.is_finite() || !speed.is_finite() {
                return Err("調音器の合成目標または速度倍率が有限範囲を超えました");
            }
            state.effective = target.clamp(bounds.minimum, bounds.maximum);
            state.applied_speed = speed;
            let omega = TAU * bounds.natural_frequency_hz * speed;
            let acceleration =
                omega * omega * (state.effective - state.position) - 2.0 * omega * state.velocity;
            state.velocity += acceleration * dt;
            state.position += state.velocity * dt;
            if state.effective == 0.0 && state.position.abs() < 1e-30 {
                state.position = 0.0;
            }
            if state.velocity.abs() < 1e-30 {
                state.velocity = 0.0;
            }
            if !state.position.is_finite() || !state.velocity.is_finite() {
                return Err("調音器の位置または速度が有限範囲を超えました");
            }
        }
        self.states = next;
        Ok(())
    }
}
