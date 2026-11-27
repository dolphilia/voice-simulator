//! ウェッデルアザラシの肺・気管・声門・口鼻腔の結合。単位は CGS。
//! 出典は notes/seal-airway.md、上流のライセンスは LICENSE-CHIMERA。

use super::mammal::{MammalAirway, MammalSpec};
use crate::breath::CM_H2O;
use crate::glottis::{DEFAULT_CYCLE_SEED, DEFAULT_VIBRATO_RATE_HZ, Glottis, GlottisParameters};
use serde::{Deserialize, Serialize};

pub use super::mammal::{MammalAirwaySample as SealAirwaySample, MammalGeometry as SealGeometry};

#[derive(Clone, Copy, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SealShape {
    pub pitch_hz: f64,
    pub brightness: f64,
    pub roughness: f64,
    pub mouth: f64,
}

impl SealShape {
    fn glottis(self, rate_hz: u32) -> Result<Glottis, &'static str> {
        if !(40.0..=6000.0).contains(&self.pitch_hz)
            || !(0.0..=1.0).contains(&self.brightness)
            || !(0.0..=0.8).contains(&self.roughness)
            || !(0.0..=1.0).contains(&self.mouth)
        {
            return Err("アザラシの音高・明るさ・粗さ・口の開きが範囲外です");
        }
        Glottis::new(
            rate_hz,
            GlottisParameters {
                f0_hz: self.pitch_hz,
                amplitude_cm2: 0.22,
                chink_cm2: 0.01,
                open_quotient: 0.55 - 0.25 * self.brightness,
                open_with_abduction: 0.0,
                skew: 0.62,
                closure_sharpness: 0.4 + 0.6 * self.brightness,
                effort: 0.5 + 0.5 * self.brightness,
                closure: 0.0,
                threshold_dyn_cm2: 2.5 * CM_H2O,
                jitter: 0.002,
                shimmer: 0.01,
                cycle_seed: DEFAULT_CYCLE_SEED,
                drift_cents: 2.0,
                vibrato_depth_cents: 0.0,
                vibrato_rate_hz: DEFAULT_VIBRATO_RATE_HZ,
                fry: 0.0,
                diplophonia: 0.0,
                chaos: self.roughness,
            },
        )
    }
}

pub struct SealAirway(MammalAirway);

impl SealAirway {
    /// 初期制御の断面を使い、静止した気道を組み立てる。
    pub fn new(rate_hz: u32, shape: SealShape) -> Result<Self, &'static str> {
        Ok(Self(MammalAirway::new(
            rate_hz,
            shape.glottis(rate_hz)?,
            MammalSpec {
                tubes: [(24.0, 4.0), (11.0, 3.0), (12.0, 3.6), (12.0, 1.5)],
                coarse: 1.0,
                wall_radiation: 0.6,
                oral_tip_from: 0.8,
                oral_tip_area_cm2: 0.3 + 4.0 * shape.mouth,
                velum_area_cm2: 0.0,
                glottal_noise_gain: 2e-6,
                oral_noise_gain: None,
                trunk: None,
            },
        )?))
    }

    pub fn geometry(&self) -> SealGeometry {
        self.0.geometry()
    }

    pub(crate) fn set_pitch(&mut self, pitch_hz: f64) -> Result<(), &'static str> {
        self.0.set_pitch(pitch_hz)
    }

    pub(crate) fn set_roughness(&mut self, roughness: f64) {
        self.0.set_roughness(roughness);
    }

    pub fn set_lung_pressure(&mut self, pressure_dyn_cm2: f64) -> Result<(), &'static str> {
        self.0.set_lung_pressure(pressure_dyn_cm2)
    }

    pub fn step(&mut self) -> Result<SealAirwaySample, &'static str> {
        self.0.step(0.0)
    }
}
