//! 固定上流の体型端点と補間。パラメータはCHIMERA由来（Jameson Hodge、MIT）。

use super::Point;
use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum BodyName {
    Male,
    Female,
    Child,
}

#[derive(Clone, Copy, Debug, Serialize)]
pub struct BodyParameters {
    pub scale: f64,
    pub pharynx: f64,
    pub tongue_radius: f64,
    pub lip_width: f64,
    pub fold_length: f64,
    pub open_phase: f64,
}

impl BodyName {
    pub const fn parameters(self) -> BodyParameters {
        match self {
            Self::Male => BodyParameters {
                scale: 1.0,
                pharynx: 1.0,
                tongue_radius: 2.25,
                lip_width: 4.6,
                fold_length: 1.0,
                open_phase: 0.0,
            },
            Self::Female => BodyParameters {
                scale: 0.9,
                pharynx: 0.88,
                tongue_radius: 2.2,
                lip_width: 4.4,
                fold_length: 0.67,
                open_phase: 0.13,
            },
            Self::Child => BodyParameters {
                scale: 0.74,
                pharynx: 0.8,
                tongue_radius: 2.15,
                lip_width: 4.0,
                fold_length: 0.35,
                open_phase: 0.13,
            },
        }
    }

    fn default_f0_hz(self) -> f64 {
        match self {
            Self::Male => 110.0,
            Self::Female => 205.0,
            Self::Child => 260.0,
        }
    }
}

impl BodyParameters {
    pub(super) fn point(self, template_x: f64, template_y: f64) -> Point {
        let x = template_x - 0.14 * (template_x - 0.5).max(0.0);
        let y = if template_y < 7.0 && self.pharynx != 1.0 {
            7.0 - (7.0 - template_y) * self.pharynx
        } else {
            template_y
        };
        Point::new(x * self.scale, y * self.scale)
    }

    pub fn epilarynx_length_cm(self) -> f64 {
        2.4 * self.scale * self.pharynx
    }
}

/// 成人の中で女性を混ぜ、その結果と子どもを混ぜる二軸の入力。
#[derive(Clone, Copy, Debug)]
pub struct BodyMix {
    female: f64,
    child: f64,
}

impl BodyMix {
    pub fn new(female: f64, child: f64) -> Self {
        let normalize = |value: f64| {
            if value.is_finite() {
                value.clamp(0.0, 1.0)
            } else {
                0.0
            }
        };
        Self {
            female: normalize(female),
            child: normalize(child),
        }
    }

    pub fn weights(self) -> [(BodyName, f64); 3] {
        let adult = 1.0 - self.child;
        [
            (BodyName::Male, adult * (1.0 - self.female)),
            (BodyName::Female, adult * self.female),
            (BodyName::Child, self.child),
        ]
    }

    /// 体型を復元するための女性・子どもの入力係数。
    pub fn coefficients(self) -> [f64; 2] {
        [self.female, self.child]
    }

    pub fn nearest(self) -> BodyName {
        let [male, female, child] = self.weights();
        [female, child]
            .into_iter()
            .fold(male, |best, next| if next.1 > best.1 { next } else { best })
            .0
    }

    pub fn preset(self) -> Option<BodyName> {
        self.weights()
            .into_iter()
            .find(|(_, weight)| *weight == 1.0)
            .map(|(name, _)| name)
    }

    fn blend(self, property: impl Fn(BodyName) -> f64) -> f64 {
        self.weights()
            .into_iter()
            .map(|(name, weight)| weight * property(name))
            .sum()
    }

    pub fn parameters(self) -> BodyParameters {
        if let Some(preset) = self.preset() {
            return preset.parameters();
        }
        let blend =
            |select: fn(BodyParameters) -> f64| self.blend(|name| select(name.parameters()));
        BodyParameters {
            scale: blend(|body| body.scale),
            pharynx: blend(|body| body.pharynx),
            tongue_radius: blend(|body| body.tongue_radius),
            lip_width: blend(|body| body.lip_width),
            fold_length: blend(|body| body.fold_length),
            open_phase: blend(|body| body.open_phase),
        }
    }

    pub fn default_f0_hz(self) -> f64 {
        self.interpolate_pitch_hz(BodyName::default_f0_hz)
    }

    pub(crate) fn interpolate_pitch_hz(self, endpoint: impl Fn(BodyName) -> f64) -> f64 {
        match self.preset() {
            Some(name) => endpoint(name),
            None => libm::exp(self.blend(|name| libm::log(endpoint(name)))),
        }
    }
}

impl From<BodyName> for BodyMix {
    fn from(name: BodyName) -> Self {
        match name {
            BodyName::Male => Self::new(0.0, 0.0),
            BodyName::Female => Self::new(1.0, 0.0),
            BodyName::Child => Self::new(0.0, 1.0),
        }
    }
}
