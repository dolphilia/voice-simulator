//! アザラシの呼び声のキー評価。出典は notes/seal-{trill,zap,whistle,chug}.md。
//! 上流のライセンスは LICENSE-CHIMERA。

use super::limit_pitch;
use crate::seal_breath::SealBreathControls;
use libm::pow;
use serde::Deserialize;

#[derive(Clone, Copy, Debug, Deserialize)]
#[serde(rename_all = "snake_case")]
#[repr(u8)]
pub enum SealCall {
    Trill = 1,
    Zap = 2,
    Whistle = 3,
    Chug = 4,
}

#[derive(Clone, Copy)]
pub(super) struct Playback {
    call: SealCall,
    started: f64,
    pitch_scale: f64,
    amplitude: f64,
}

pub(super) struct CallControl {
    pub pitch_hz: f64,
    pub breath: SealBreathControls,
    pub gate: f64,
    pub roughness: Option<f64>,
}

impl Playback {
    pub fn new(call: SealCall, started: f64, pitch_hz: Option<f64>, amplitude: f64) -> Self {
        let reference_pitch = match call {
            SealCall::Trill => 3600.0,
            SealCall::Zap => 6000.0,
            SealCall::Whistle => 1700.0,
            SealCall::Chug => 90.0,
        };
        Self {
            call,
            started,
            pitch_scale: pitch_hz
                .filter(|&pitch| pitch != 0.0)
                .map_or(1.0, |pitch| pitch / reference_pitch),
            amplitude,
        }
    }

    pub fn id(self) -> u8 {
        self.call as u8
    }

    pub fn owns_roughness(self) -> bool {
        matches!(self.call, SealCall::Chug)
    }

    pub fn retain_breath_targets(
        self,
        current: SealBreathControls,
        manual: SealBreathControls,
    ) -> SealBreathControls {
        let timing = match self.call {
            SealCall::Trill | SealCall::Chug => current,
            SealCall::Zap | SealCall::Whistle => manual,
        };
        SealBreathControls {
            pulse_depth: current.pulse_depth,
            pressure_cm_h2o: manual.pressure_cm_h2o,
            ..timing
        }
    }

    pub fn control(self, clock: f64, manual: SealBreathControls) -> Option<CallControl> {
        let elapsed = clock - self.started;
        let sweep = |start, finish, from, to| {
            if elapsed < to {
                start * pow(finish / start, (elapsed - from) / (to - from))
            } else {
                finish
            }
        };
        match self.call {
            SealCall::Trill => {
                const SWEEP: f64 = 3.6;
                const RELEASE: f64 = 3.9;
                if elapsed > RELEASE + 0.05 {
                    return None;
                }
                let gate = if elapsed < SWEEP {
                    1.0
                } else if elapsed < RELEASE {
                    1.0 - (elapsed - SWEEP) / (RELEASE - SWEEP)
                } else {
                    0.0
                };
                Some(CallControl {
                    pitch_hz: limit_pitch(sweep(3600.0, 95.0, 0.0, SWEEP) * self.pitch_scale),
                    breath: SealBreathControls {
                        pulse_rate_hz: sweep(42.0, 6.0, 0.0, SWEEP),
                        pulse_depth: 0.9,
                        duty: 0.5,
                        ..manual
                    },
                    gate: self.amplitude * gate,
                    roughness: None,
                })
            }
            SealCall::Zap => {
                const RELEASE: f64 = 0.17;
                if elapsed > RELEASE + 0.05 {
                    return None;
                }
                Some(CallControl {
                    pitch_hz: limit_pitch(sweep(6000.0, 1100.0, 0.0, 0.15) * self.pitch_scale),
                    breath: SealBreathControls {
                        pulse_depth: 0.0,
                        ..manual
                    },
                    gate: self.amplitude * (1.0 - elapsed / RELEASE).max(0.0),
                    roughness: None,
                })
            }
            SealCall::Whistle => {
                const TURN: f64 = 0.45;
                const HOLD: f64 = 0.95;
                const RELEASE: f64 = 1.0;
                if elapsed > RELEASE + 0.05 {
                    return None;
                }
                let pitch_hz = if elapsed < TURN {
                    sweep(1700.0, 620.0, 0.0, TURN)
                } else {
                    sweep(620.0, 1500.0, TURN, HOLD)
                };
                Some(CallControl {
                    pitch_hz: limit_pitch(pitch_hz * self.pitch_scale),
                    breath: SealBreathControls {
                        pulse_depth: 0.1,
                        ..manual
                    },
                    gate: self.amplitude * (1.0 - elapsed / RELEASE).max(0.0),
                    roughness: None,
                })
            }
            SealCall::Chug => {
                const HOLD: f64 = 0.9;
                const RELEASE: f64 = 0.95;
                if elapsed > RELEASE + 0.05 {
                    return None;
                }
                let gate = if elapsed < HOLD {
                    1.0
                } else if elapsed < RELEASE {
                    1.0 - (elapsed - HOLD) / (RELEASE - HOLD)
                } else {
                    0.0
                };
                let roughness = if elapsed < RELEASE {
                    0.3 + (0.05 - 0.3) * (elapsed / RELEASE)
                } else {
                    0.05
                };
                Some(CallControl {
                    pitch_hz: limit_pitch(90.0 * self.pitch_scale),
                    breath: SealBreathControls {
                        pulse_rate_hz: 11.0,
                        pulse_depth: 1.0,
                        duty: 0.35,
                        ..manual
                    },
                    gate: self.amplitude * gate,
                    roughness: Some(roughness),
                })
            }
        }
    }
}
