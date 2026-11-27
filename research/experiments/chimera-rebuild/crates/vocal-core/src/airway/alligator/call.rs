//! アリゲーターの呼び声の制御キー。出典は notes/alligator-{bellow,growl,hiss,dance}.md。

use super::{AlligatorParams, PITCH_LIMITS};
use crate::airway::sample_call_curve as sample_curve;
use serde::Deserialize;

#[derive(Clone, Copy, Deserialize)]
#[serde(rename_all = "snake_case")]
#[repr(u8)]
pub enum AlligatorCall {
    Bellow = 1,
    Growl = 2,
    Hiss = 3,
    Dance = 4,
}

type Curve = &'static [(f64, f64)];

struct CallPlan {
    reference_pitch_hz: Option<f64>,
    gate: Curve,
    pitch: Curve,
    chaos: Curve,
    mouth: Curve,
    hiss: Curve,
}

const BELLOW: CallPlan = CallPlan {
    reference_pitch_hz: Some(28.0),
    gate: &[(0.0, 0.0), (0.15, 1.0), (1.6, 1.0), (2.0, 0.0)],
    pitch: &[(0.0, 30.0), (1.6, 24.0)],
    chaos: &[(0.0, 0.55), (1.6, 0.95)],
    mouth: &[(0.0, 0.02)],
    hiss: &[(0.0, 0.0)],
};

const GROWL: CallPlan = CallPlan {
    reference_pitch_hz: Some(45.0),
    gate: &[(0.0, 1.0), (0.6, 0.0)],
    pitch: &[(0.0, 45.0), (0.5, 38.0)],
    chaos: &[(0.0, 0.7)],
    mouth: &[(0.0, 0.15)],
    hiss: &[],
};

const HISS: CallPlan = CallPlan {
    reference_pitch_hz: None,
    gate: &[(0.0, 0.0), (0.1, 1.0), (1.2, 1.0), (1.3, 0.0)],
    pitch: &[],
    chaos: &[],
    mouth: &[(0.0, 0.9), (1.3, 0.02)],
    hiss: &[(0.0, 1.0), (1.3, 0.0)],
};

const DANCE: CallPlan = CallPlan {
    reference_pitch_hz: Some(18.0),
    gate: &[(0.0, 1.0), (1.6, 1.0), (1.7, 0.0)],
    pitch: &[(0.0, 18.0)],
    chaos: &[(0.0, 0.0), (1.7, 0.75)],
    mouth: &[(0.0, 0.0)],
    hiss: &[],
};

impl AlligatorCall {
    fn plan(self) -> &'static CallPlan {
        match self {
            Self::Bellow => &BELLOW,
            Self::Growl => &GROWL,
            Self::Hiss => &HISS,
            Self::Dance => &DANCE,
        }
    }
}

#[derive(Clone, Copy)]
pub(super) struct Playback {
    pub call: AlligatorCall,
    started: f64,
    pitch_scale: f64,
    amplitude: f64,
}

impl Playback {
    pub fn new(call: AlligatorCall, started: f64, pitch_hz: Option<f64>, amplitude: f64) -> Self {
        let pitch_scale = pitch_hz
            .filter(|&pitch| pitch != 0.0)
            .zip(call.plan().reference_pitch_hz)
            .map_or(1.0, |(pitch, reference)| pitch / reference);
        Self {
            call,
            started,
            pitch_scale,
            amplitude,
        }
    }

    pub fn evaluate(self, now: f64) -> Option<(AlligatorParams, f64)> {
        let elapsed = now - self.started;
        let plan = self.call.plan();
        let &(last, _) = plan.gate.last()?;
        if elapsed > last + 0.05 {
            return None;
        }
        let pitch_hz = sample_curve(plan.pitch, elapsed).map(|pitch| {
            (pitch * self.pitch_scale).clamp(*PITCH_LIMITS.start(), *PITCH_LIMITS.end())
        });
        let targets = AlligatorParams {
            pitch_hz,
            chaos: sample_curve(plan.chaos, elapsed),
            mouth: sample_curve(plan.mouth, elapsed),
            hiss: sample_curve(plan.hiss, elapsed),
            ..AlligatorParams::default()
        };
        Some((
            targets,
            sample_curve(plan.gate, elapsed).unwrap_or_default() * self.amplitude,
        ))
    }

    pub(super) fn retain_owned_targets(self, current: super::AlligatorShape) -> AlligatorParams {
        let plan = self.call.plan();
        AlligatorParams {
            pitch_hz: (!plan.pitch.is_empty()).then_some(current.pitch_hz),
            chaos: (!plan.chaos.is_empty()).then_some(current.chaos),
            mouth: (!plan.mouth.is_empty()).then_some(current.mouth),
            hiss: (!plan.hiss.is_empty()).then_some(current.hiss),
            ..AlligatorParams::default()
        }
    }
}
