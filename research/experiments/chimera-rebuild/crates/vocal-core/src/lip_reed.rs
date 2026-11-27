//! 圧力差で開く弁の振動。式と出典は notes/elephant-valve.md。
//! 上流のライセンスは LICENSE-CHIMERA。

use serde::Deserialize;
use std::f64::consts::TAU;

#[derive(Clone, Copy, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LipReedParameters {
    pub pitch_hz: f64,
    pub damping_ratio: f64,
    pub rest_gap_cm: f64,
    pub width_cm: f64,
    pub surface_per_mass_cm2_g: f64,
}

#[derive(Clone, Copy, Default)]
pub struct LipReedState {
    pub height_cm: f64,
    pub speed_cm_s: f64,
    pub opening_cm2: f64,
}

pub struct LipReed {
    dt: f64,
    parameters: LipReedParameters,
    height_cm: f64,
    speed_cm_s: f64,
}

impl LipReed {
    pub fn new(rate_hz: u32, parameters: LipReedParameters) -> Result<Self, &'static str> {
        let mut reed = Self {
            dt: 1.0 / f64::from(rate_hz),
            parameters,
            height_cm: 0.0,
            speed_cm_s: 0.0,
        };
        if rate_hz == 0
            || !parameters.rest_gap_cm.is_finite()
            || [
                parameters.damping_ratio,
                parameters.width_cm,
                parameters.surface_per_mass_cm2_g,
            ]
            .into_iter()
            .any(|value| !value.is_finite() || value < 0.0)
        {
            return Err("弁のレート・静止隙間・減衰・幅・受圧面積を確認してください");
        }
        reed.set_pitch(parameters.pitch_hz)?;
        Ok(reed)
    }

    pub(crate) fn set_pitch(&mut self, pitch_hz: f64) -> Result<(), &'static str> {
        if !pitch_hz.is_finite() || pitch_hz <= 0.0 || pitch_hz * self.dt >= 0.5 {
            return Err("弁の固有周波数を確認してください");
        }
        self.parameters.pitch_hz = pitch_hz;
        Ok(())
    }

    pub fn state(&self) -> LipReedState {
        LipReedState {
            height_cm: self.height_cm,
            speed_cm_s: self.speed_cm_s,
            opening_cm2: self.height_cm.max(0.0) * self.parameters.width_cm,
        }
    }

    pub fn step(&mut self, pressure_difference_dyn_cm2: f64) -> LipReedState {
        let parameters = self.parameters;
        let omega = TAU * parameters.pitch_hz;
        let acceleration = parameters.surface_per_mass_cm2_g * pressure_difference_dyn_cm2
            - 2.0 * parameters.damping_ratio * omega * self.speed_cm_s
            - omega * omega * (self.height_cm - parameters.rest_gap_cm);
        self.speed_cm_s += acceleration * self.dt;
        // 新しい速度で変位を進め、衝突時は境界の外向き速度を止める。
        self.height_cm += self.speed_cm_s * self.dt;
        if self.height_cm < -0.05 {
            self.height_cm = -0.05;
            self.speed_cm_s = self.speed_cm_s.max(0.0);
        } else if self.height_cm > 0.8 {
            self.height_cm = 0.8;
            self.speed_cm_s = self.speed_cm_s.min(0.0);
        }
        self.state()
    }
}
