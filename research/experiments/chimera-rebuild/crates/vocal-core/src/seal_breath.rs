//! ウェッデルアザラシのパルスで変調された肺の固定圧力境界。

use crate::airway::trim_tiny;
use crate::breath::CM_H2O;
use libm::{exp, pow, sin};
use serde::{Deserialize, Serialize};
use std::f64::consts::PI;

pub const CONTROL_FRAMES: usize = 64;

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SealBreathControls {
    pub pulse_rate_hz: f64,
    pub pulse_depth: f64,
    pub duty: f64,
    pub pressure_cm_h2o: f64,
}

impl SealBreathControls {
    pub(crate) fn normalized(self) -> Result<Self, &'static str> {
        if ![
            self.pulse_rate_hz,
            self.pulse_depth,
            self.duty,
            self.pressure_cm_h2o,
        ]
        .into_iter()
        .all(f64::is_finite)
        {
            return Err("呼気パルスの制御値は有限値で指定してください");
        }
        Ok(Self {
            pulse_rate_hz: self.pulse_rate_hz.clamp(2.0, 60.0),
            pulse_depth: self.pulse_depth.clamp(0.0, 1.0),
            duty: self.duty.clamp(0.15, 1.0),
            pressure_cm_h2o: self.pressure_cm_h2o.clamp(2.0, 25.0),
        })
    }

    pub(crate) fn values(self) -> [f64; 4] {
        [
            self.pulse_rate_hz,
            self.pulse_depth,
            self.duty,
            self.pressure_cm_h2o,
        ]
    }
}

pub struct SealBreathFrame {
    pub controls: SealBreathControls,
    pub phase: f64,
    pub half_sine: f64,
    pub pulse_gain: f64,
    pub gate: f64,
    pub gate_target: f64,
    pub base_pressure_dyn_cm2: f64,
    pub lung_pressure_dyn_cm2: f64,
}

pub struct SealBreath {
    pub(crate) output_rate_hz: u32,
    pub(crate) control_seconds: f64,
    phase: f64,
    gate: f64,
    pub(crate) gate_target: f64,
    pub(crate) current: SealBreathControls,
    pub(crate) target: SealBreathControls,
}

impl SealBreath {
    pub fn new(output_rate_hz: u32, initial: SealBreathControls) -> Result<Self, &'static str> {
        if output_rate_hz == 0 {
            return Err("呼気パルスのサンプルレートには正の値が必要です");
        }
        let initial = initial.normalized()?;
        let control_seconds = CONTROL_FRAMES as f64 / f64::from(output_rate_hz);
        Ok(Self {
            output_rate_hz,
            control_seconds,
            // 上流は出力前に無呼気の制御を1回適用する。
            phase: (initial.pulse_rate_hz * control_seconds).fract(),
            gate: 0.0,
            gate_target: 0.0,
            current: initial,
            target: initial,
        })
    }

    pub fn phase(&self) -> f64 {
        self.phase
    }

    pub fn set_controls(&mut self, target: SealBreathControls) -> Result<(), &'static str> {
        self.target = target.normalized()?;
        Ok(())
    }

    pub fn set_gate(&mut self, gate: f64) -> Result<(), &'static str> {
        self.gate_target = Self::manual_gate(gate)?;
        Ok(())
    }

    pub(crate) fn manual_gate(gate: f64) -> Result<f64, &'static str> {
        if !gate.is_finite() {
            return Err("呼気ゲートは有限値で指定してください");
        }
        Ok(gate.clamp(0.0, 1.5))
    }

    /// 64出力フレームの区間に適用する制御を更新し、肺圧を返す。
    pub fn step(&mut self) -> SealBreathFrame {
        let dt = self.control_seconds;
        let alpha = |tau| 1.0 - exp(-dt / tau);
        let linear = |current, target, tau| current + (target - current) * alpha(tau);
        let c = self.current;
        let t = self.target;
        let controls = SealBreathControls {
            pulse_rate_hz: c.pulse_rate_hz * pow(t.pulse_rate_hz / c.pulse_rate_hz, alpha(0.020)),
            pulse_depth: linear(c.pulse_depth, t.pulse_depth, 0.020),
            duty: linear(c.duty, t.duty, 0.020),
            pressure_cm_h2o: linear(c.pressure_cm_h2o, t.pressure_cm_h2o, 0.010),
        };
        self.current = controls;
        let tau = if self.gate_target > self.gate {
            0.006
        } else {
            0.030
        };
        self.gate = linear(self.gate, self.gate_target, tau);
        trim_tiny(&mut self.gate);
        self.phase += controls.pulse_rate_hz * dt;
        self.phase -= self.phase.floor();
        let half_sine = if self.phase < controls.duty {
            sin((PI * self.phase) / controls.duty)
        } else {
            0.0
        };
        let pulse_gain = 1.0 - controls.pulse_depth + controls.pulse_depth * half_sine;
        let base_pressure_dyn_cm2 = controls.pressure_cm_h2o * CM_H2O * self.gate;
        SealBreathFrame {
            controls,
            phase: self.phase,
            half_sine,
            pulse_gain,
            gate: self.gate,
            gate_target: self.gate_target,
            base_pressure_dyn_cm2,
            lung_pressure_dyn_cm2: base_pressure_dyn_cm2 * pulse_gain,
        }
    }
}
