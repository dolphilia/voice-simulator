//! 発話の母音目標を、指定された制御周期で既存の調音器へ渡す。

use crate::geometry_case::Pose;
use serde::{Deserialize, Serialize};
use std::{
    collections::BTreeMap,
    num::{NonZeroU32, NonZeroUsize},
};

use vocal_core::{
    articulators::{ARTICULATOR_COUNT, ArticulatorBank, BlendedTarget},
    score::{ControlKey, Gesture, blend_at},
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Observation {
    sample_rate_hz: NonZeroU32,
    control_block_samples: NonZeroUsize,
    frames: NonZeroUsize,
    base_weight: f64,
    tip_free: bool,
    posture: Pose,
    keys: Vec<String>,
}

#[derive(Serialize)]
pub(super) struct ObservedScore {
    gestures: Vec<Gesture>,
    frames: Vec<Frame>,
}

#[derive(Serialize)]
struct Frame {
    time_seconds: f64,
    activation: Vec<f64>,
    blend: BTreeMap<&'static str, BlendedTarget>,
    articulators: BTreeMap<&'static str, ArticulationSample>,
}

#[derive(Serialize)]
struct ArticulationSample {
    position: f64,
    velocity: f64,
    effective: f64,
    applied_speed: f64,
}

impl Observation {
    pub(super) fn observe(&self, gestures: Vec<Gesture>) -> Result<ObservedScore, &'static str> {
        let mut keys = self
            .keys
            .iter()
            .map(|name| {
                ControlKey::from_name(name).ok_or("観測する制御成分の名前を確認してください")
            })
            .collect::<Result<Vec<_>, _>>()?;
        keys.sort_unstable_by_key(|key| key.index());
        if keys.is_empty() || keys.windows(2).any(|pair| pair[0] == pair[1]) {
            return Err("観測する制御成分を重複なしで指定してください");
        }

        for gesture in &gestures {
            gesture.validate()?;
        }
        let dt = self.control_block_samples.get() as f64 / f64::from(self.sample_rate_hz.get());
        let mut bank = ArticulatorBank::new(self.posture.into(), self.tip_free)?;
        let mut frames = Vec::with_capacity(self.frames.get());
        for index in 0..self.frames.get() {
            let time = index as f64 * dt;
            let blend = blend_at(&gestures, time);
            // 音源用成分も出力前に検査し、調音器には先頭の調音成分を渡す。
            let (articulation, source) = blend.split_at(ARTICULATOR_COUNT);
            for &value in source {
                value.validate()?;
            }
            bank.step(dt, articulation.try_into().unwrap(), self.base_weight)?;

            let mut frame = Frame {
                time_seconds: time,
                activation: gestures.iter().map(|g| g.activation(time)).collect(),
                blend: BTreeMap::new(),
                articulators: BTreeMap::new(),
            };
            for &key in &keys {
                frame.blend.insert(key.name(), blend[key.index()]);
                if let ControlKey::Artic(artic) = key {
                    let s = bank.state(artic);
                    frame.articulators.insert(
                        key.name(),
                        ArticulationSample {
                            position: s.position,
                            velocity: s.velocity,
                            effective: s.effective,
                            applied_speed: s.applied_speed,
                        },
                    );
                }
            }
            frames.push(frame);
        }

        Ok(ObservedScore { gestures, frames })
    }
}
