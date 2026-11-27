//! ゾウのコールのキーと演奏値の所有。出典は notes/elephant-{rumble,trumpet,squeak}.md。

use super::{ElephantParams, ElephantShape, PITCH_LIMITS};
use crate::airway::sample_call_curve_with;
use serde::Deserialize;

struct Curve {
    keys: &'static [(f64, f64)],
    exponential_endpoints: &'static [usize],
}

impl Curve {
    const fn linear(keys: &'static [(f64, f64)]) -> Self {
        Self {
            keys,
            exponential_endpoints: &[],
        }
    }

    const fn with_exponential(keys: &'static [(f64, f64)], endpoints: &'static [usize]) -> Self {
        Self {
            keys,
            exponential_endpoints: endpoints,
        }
    }

    fn sample(&self, elapsed: f64) -> Option<f64> {
        sample_call_curve_with(self.keys, elapsed, |endpoint, from, to, part| {
            if self.exponential_endpoints.contains(&endpoint) && from > 0.0 && to > 0.0 {
                from * libm::pow(to / from, part)
            } else {
                from + (to - from) * part
            }
        })
    }

    fn retain(&self, current: f64) -> Option<f64> {
        (!self.keys.is_empty()).then_some(current)
    }
}

struct CallPlan {
    reference_pitch_hz: f64,
    gate: Curve,
    pitch_hz: Curve,
    pressure_cm_h2o: Curve,
    trunk: Curve,
    chaos: Curve,
    mode: Curve,
    lip_pitch_hz: Curve,
}

const EMPTY: Curve = Curve::linear(&[]);
const RUMBLE: CallPlan = CallPlan {
    reference_pitch_hz: 14.0,
    gate: Curve::linear(&[(0.0, 0.0), (0.3, 1.0), (2.7, 1.0), (3.1, 0.0)]),
    pitch_hz: Curve::linear(&[(0.0, 15.0), (2.7, 12.0)]),
    pressure_cm_h2o: EMPTY,
    trunk: Curve::linear(&[(0.0, 1.0)]),
    chaos: EMPTY,
    mode: Curve::linear(&[(0.0, 0.0)]),
    lip_pitch_hz: EMPTY,
};
const TRUMPET: CallPlan = CallPlan {
    reference_pitch_hz: 470.0,
    gate: Curve::linear(&[(0.0, 0.0), (0.05, 1.0), (1.25, 0.0)]),
    pitch_hz: EMPTY,
    pressure_cm_h2o: Curve::with_exponential(&[(0.0, 26.0), (1.1, 34.0), (1.25, 16.0)], &[1]),
    trunk: EMPTY,
    chaos: Curve::with_exponential(&[(0.0, 0.1), (1.1, 0.6)], &[1]),
    mode: Curve::linear(&[(0.0, 1.0), (1.25, 0.0)]),
    lip_pitch_hz: Curve::with_exponential(&[(0.0, 380.0), (0.5, 520.0), (1.1, 470.0)], &[1, 2]),
};
const SQUEAK: CallPlan = CallPlan {
    reference_pitch_hz: 850.0,
    gate: Curve::linear(&[(0.0, 0.0), (0.04, 1.0), (0.5, 0.0)]),
    pitch_hz: EMPTY,
    pressure_cm_h2o: Curve::linear(&[(0.0, 20.0), (0.5, 16.0)]),
    trunk: EMPTY,
    chaos: EMPTY,
    mode: Curve::linear(&[(0.0, 1.0), (0.5, 0.0)]),
    lip_pitch_hz: Curve::linear(&[(0.0, 820.0), (0.45, 880.0)]),
};

#[derive(Clone, Copy, Deserialize)]
#[serde(rename_all = "snake_case")]
#[repr(u8)]
pub enum ElephantCall {
    Rumble = 1,
    Trumpet = 2,
    Squeak = 3,
}

impl ElephantCall {
    fn plan(self) -> &'static CallPlan {
        match self {
            Self::Rumble => &RUMBLE,
            Self::Trumpet => &TRUMPET,
            Self::Squeak => &SQUEAK,
        }
    }
}

#[derive(Clone, Copy)]
pub(super) struct Playback {
    pub id: ElephantCall,
    started: f64,
    pitch_scale: f64,
    amplitude: f64,
}

impl Playback {
    pub fn new(id: ElephantCall, started: f64, pitch_hz: Option<f64>, amplitude: f64) -> Self {
        Self {
            id,
            started,
            pitch_scale: pitch_hz
                .filter(|&pitch| pitch != 0.0)
                .map_or(1.0, |pitch| pitch / id.plan().reference_pitch_hz),
            amplitude,
        }
    }

    pub fn evaluate(self, now: f64) -> Option<(ElephantParams, f64)> {
        let elapsed = now - self.started;
        let plan = self.id.plan();
        if elapsed > plan.gate.keys.last()?.0 + 0.05 {
            return None;
        }
        let targets = ElephantParams {
            pitch_hz: plan.pitch_hz.sample(elapsed).map(|pitch| {
                (pitch * self.pitch_scale).clamp(*PITCH_LIMITS.start(), *PITCH_LIMITS.end())
            }),
            pressure_cm_h2o: plan.pressure_cm_h2o.sample(elapsed),
            trunk: plan.trunk.sample(elapsed),
            chaos: plan.chaos.sample(elapsed),
            mode: plan.mode.sample(elapsed),
            // 上流の音高ロールは声門音高に付く。弁音高はキーの値で駆動する。
            lip_pitch_hz: plan.lip_pitch_hz.sample(elapsed),
        };
        Some((targets, plan.gate.sample(elapsed)? * self.amplitude))
    }

    pub fn retain_owned_targets(self, current: ElephantShape) -> ElephantParams {
        let plan = self.id.plan();
        ElephantParams {
            pitch_hz: plan.pitch_hz.retain(current.pitch_hz),
            pressure_cm_h2o: plan.pressure_cm_h2o.retain(current.pressure_cm_h2o),
            trunk: plan.trunk.retain(current.trunk),
            chaos: plan.chaos.retain(current.chaos),
            mode: plan.mode.retain(current.mode),
            lip_pitch_hz: plan.lip_pitch_hz.retain(current.lip_pitch_hz),
        }
    }
}
