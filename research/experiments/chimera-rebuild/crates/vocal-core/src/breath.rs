//! 肺の呼気圧と下気道の音響抵抗を制御する。気道との入出力はCGS。

pub(crate) const CM_H2O: f64 = 980.665;
const LOWER_AIRWAY_RESISTANCE_CGS: f64 = 0.8 * CM_H2O / 1000.0;
const LOWER_AIRWAY_INERTANCE_CGS: f64 = 5.2e-3;

pub struct BreathSettings {
    pub pressure_cm_h2o: f64,
    pub body_scale: f64,
    pub control_block_samples: usize,
    pub series_resistance_cgs: f64,
    pub compensate: bool,
}

#[derive(Clone, Copy, Debug)]
pub struct BreathControl {
    pub performer_gate: f64,
    pub score_level: f64,
    pub score_activity: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct BreathSample {
    pub gate: f64,
    pub base_pressure_dyn_cm2: f64,
    pub filtered_flow_cm3_s: f64,
    pub boundary_pressure_dyn_cm2: f64,
    pub effort: f64,
}

pub struct Breath {
    pressure_cm_h2o: f64,
    block_samples: usize,
    block_seconds: f64,
    excess_resistance: f64,
    flow_smoothing: f64,
    gate: f64,
    score_release_remaining: f64,
    base_pressure: f64,
    pressure_per_sample: f64,
    filtered_flow: f64,
}

impl Breath {
    pub fn new(rate_hz: u32, settings: BreathSettings) -> Result<Self, &'static str> {
        let BreathSettings {
            pressure_cm_h2o,
            body_scale,
            control_block_samples,
            series_resistance_cgs,
            compensate,
        } = settings;
        if rate_hz == 0
            || control_block_samples == 0
            || !body_scale.is_finite()
            || body_scale <= 0.0
            || [pressure_cm_h2o, series_resistance_cgs]
                .into_iter()
                .any(|v| !v.is_finite() || v < 0.0)
            || !(pressure_cm_h2o * CM_H2O).is_finite()
        {
            return Err("呼気圧、体型、制御周期、肺ポート抵抗を確認してください");
        }
        let rate = f64::from(rate_hz);
        let mut excess_resistance = 0.0;
        let mut flow_smoothing = 0.0;
        if compensate {
            let dc = LOWER_AIRWAY_RESISTANCE_CGS / (body_scale * body_scale * body_scale);
            excess_resistance = series_resistance_cgs - dc;
            let cutoff = excess_resistance * body_scale / LOWER_AIRWAY_INERTANCE_CGS;
            if !cutoff.is_finite() || cutoff < 0.0 {
                return Err("補償付き肺ポートの直列抵抗は下気道の直流抵抗以上にしてください");
            }
            flow_smoothing = 1.0 - libm::exp(-cutoff / rate);
        }
        Ok(Self {
            pressure_cm_h2o,
            block_samples: control_block_samples,
            block_seconds: control_block_samples as f64 / rate,
            excess_resistance,
            flow_smoothing,
            gate: 0.0,
            score_release_remaining: 0.0,
            base_pressure: 0.0,
            pressure_per_sample: 0.0,
            filtered_flow: 0.0,
        })
    }

    /// ブロックの先頭で、有限の操作値・スコア値と0〜1の有効度を受け取る。
    pub fn control(&mut self, input: BreathControl) {
        let score = input.score_level * input.score_activity;
        let goal = if score < 0.0 {
            score
        } else {
            input.performer_gate.clamp(0.0, 1.5).max(score)
        };
        self.score_release_remaining = if input.score_activity > 0.0 {
            0.15
        } else {
            (self.score_release_remaining - self.block_seconds).max(0.0)
        };
        let tau = if goal > self.gate {
            0.025
        } else if self.score_release_remaining > 0.0 {
            0.02
        } else {
            0.07
        };
        self.gate += (goal - self.gate) * (1.0 - libm::exp(-self.block_seconds / tau));
        zero_tiny(&mut self.gate);
        zero_tiny(&mut self.filtered_flow);
        let target = self.pressure_cm_h2o * CM_H2O * self.gate;
        if target == 0.0 {
            zero_tiny(&mut self.base_pressure);
        }
        self.pressure_per_sample = (target - self.base_pressure) / self.block_samples as f64;
    }

    /// 前サンプルの肺ポート流量を受け取り、今回の固定圧力境界を計算する。
    pub fn step(&mut self, previous_flow_cm3_s: f64) -> BreathSample {
        self.base_pressure += self.pressure_per_sample;
        self.filtered_flow += self.flow_smoothing * (previous_flow_cm3_s - self.filtered_flow);
        BreathSample {
            gate: self.gate,
            base_pressure_dyn_cm2: self.base_pressure,
            filtered_flow_cm3_s: self.filtered_flow,
            boundary_pressure_dyn_cm2: self.base_pressure
                + self.excess_resistance * self.filtered_flow,
            effort: ((self.pressure_cm_h2o * self.gate).abs() - 2.2).clamp(0.0, 10.0) / 10.0,
        }
    }
}

fn zero_tiny(value: &mut f64) {
    if value.abs() < 1e-30 {
        *value = 0.0;
    }
}
