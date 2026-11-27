//! 秒単位のジェスチャーを制御成分ごとの目標、重み、速度倍率に変換する。

use crate::articulators::{ARTICULATOR_COUNT, Articulator, BlendedTarget};
use serde::{Deserialize, Deserializer, Serialize, Serializer, ser::SerializeMap};
use std::{collections::BTreeMap, f64::consts::PI};

const SOURCE_NAMES: [&str; 5] = [
    "abduction_cm2",
    "closure",
    "breath",
    "f0_hz",
    "vibrato_cents",
];
pub const CONTROL_COUNT: usize = ARTICULATOR_COUNT + SOURCE_NAMES.len();

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ControlKey {
    Artic(Articulator),
    Abduction,
    Closure,
    Breath,
    F0,
    Vibrato,
}

impl ControlKey {
    const SOURCE_KEYS: [Self; SOURCE_NAMES.len()] = [
        Self::Abduction,
        Self::Closure,
        Self::Breath,
        Self::F0,
        Self::Vibrato,
    ];

    pub fn index(self) -> usize {
        match self {
            Self::Artic(key) => key.index(),
            Self::Abduction => ARTICULATOR_COUNT,
            Self::Closure => ARTICULATOR_COUNT + 1,
            Self::Breath => ARTICULATOR_COUNT + 2,
            Self::F0 => ARTICULATOR_COUNT + 3,
            Self::Vibrato => ARTICULATOR_COUNT + 4,
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            Self::Artic(key) => key.name(),
            _ => SOURCE_NAMES[self.index() - ARTICULATOR_COUNT],
        }
    }

    pub fn from_name(name: &str) -> Option<Self> {
        Articulator::from_name(name).map(Self::Artic).or_else(|| {
            SOURCE_NAMES
                .iter()
                .position(|&s| s == name)
                .map(|i| Self::SOURCE_KEYS[i])
        })
    }

    pub fn all() -> impl Iterator<Item = Self> {
        Articulator::ALL
            .into_iter()
            .map(Self::Artic)
            .chain(Self::SOURCE_KEYS)
    }
}

#[derive(Clone, Copy, Debug, Default)]
pub struct Targets([Option<f64>; CONTROL_COUNT]);

impl Targets {
    pub fn get(&self, key: ControlKey) -> Option<f64> {
        self.0[key.index()]
    }

    pub fn set(&mut self, key: ControlKey, value: f64) {
        self.0[key.index()] = Some(value);
    }
}

impl Serialize for Targets {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        let mut map = serializer.serialize_map(None)?;
        for key in ControlKey::all() {
            if let Some(value) = self.0[key.index()] {
                map.serialize_entry(key.name(), &value)?;
            }
        }
        map.end()
    }
}

impl<'de> Deserialize<'de> for Targets {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        let mut targets = Self::default();
        for (name, value) in BTreeMap::<String, f64>::deserialize(deserializer)? {
            let key = ControlKey::from_name(&name).ok_or_else(|| {
                serde::de::Error::custom(format!("未知の制御成分があります ({name})"))
            })?;
            targets.set(key, value);
        }
        Ok(targets)
    }
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Gesture {
    pub t0: f64,
    pub t1: f64,
    pub ramp_in: f64,
    pub ramp_out: f64,
    pub strength: f64,
    pub targets: Targets,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub speed: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub release_hold: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub label: Option<String>,
}

impl Gesture {
    /// 速い発話では調音ランプと速度の保持を短縮する。ピッチと呼気のランプは保つ。
    pub(crate) fn shorten_for_rate(&mut self, rate: f64) {
        if rate > 1.0
            && self.targets.0[ControlKey::F0.index()].is_none()
            && self.targets.0[ControlKey::Breath.index()].is_none()
        {
            self.ramp_in /= rate;
            self.ramp_out /= rate;
            self.release_hold = self.release_hold.map(|hold| hold / rate);
        }
    }

    pub fn validate(&self) -> Result<(), &'static str> {
        if !(self.t0.is_finite()
            && self.t1.is_finite()
            && self.t0 <= self.t1
            && (self.t0 - self.ramp_in).is_finite()
            && self.speed_end().is_finite()
            && [
                self.ramp_in,
                self.ramp_out,
                self.strength,
                self.speed.unwrap_or(1.0),
                self.release_hold.unwrap_or(0.0),
            ]
            .into_iter()
            .all(|v| v.is_finite() && v >= 0.0)
            && self.targets.0.into_iter().flatten().all(f64::is_finite))
        {
            return Err("ジェスチャーの時刻、目標、重みまたは速度倍率が不正です");
        }
        Ok(())
    }

    pub(crate) fn speed_end(&self) -> f64 {
        self.t1 + self.ramp_out + self.release_hold.unwrap_or(0.0)
    }

    /// 上昇・下降は余弦で接続し、保持区間は1になる。
    pub fn activation(&self, time: f64) -> f64 {
        let attack = self.t0 - self.ramp_in;
        if time <= attack || time >= self.t1 + self.ramp_out {
            0.0
        } else if time < self.t0 {
            let phase = (time - attack) / self.ramp_in.max(1e-6);
            0.5 - 0.5 * libm::cos(PI * phase)
        } else if time > self.t1 {
            let phase = (time - self.t1) / self.ramp_out.max(1e-6);
            0.5 + 0.5 * libm::cos(PI * phase)
        } else {
            1.0
        }
    }
}

/// 調音器と音源の制御成分を一巡で合成する。活性外でも速度の窓は残り得る。
pub fn blend_at(gestures: &[Gesture], time: f64) -> [BlendedTarget; CONTROL_COUNT] {
    let mut output = [BlendedTarget::default(); CONTROL_COUNT];
    for gesture in gestures {
        let weight = gesture.activation(time) * gesture.strength;
        let speed = gesture
            .speed
            .filter(|_| time >= gesture.t0 - gesture.ramp_in && time <= gesture.speed_end());
        if weight == 0.0 && speed.is_none() {
            continue;
        }
        for (combined, target) in output.iter_mut().zip(gesture.targets.0) {
            if let Some(value) = target {
                if let Some(speed) = speed {
                    combined.speed = combined.speed.max(speed);
                }
                combined.weight += weight;
                combined.value += weight * value;
            }
        }
    }
    for combined in &mut output {
        if combined.weight > 0.0 {
            combined.value /= combined.weight;
        }
    }
    output
}
