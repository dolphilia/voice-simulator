//! 接触補正後の格子から、中心線に沿った断面積を計算する。係数はCHIMERA由来（MIT）。

use std::f64::consts::FRAC_PI_4;

use super::grid::smoothstep;
use super::{BodyParameters, ContactSample, Region, SagittalFrame, SagittalModel};

#[derive(Clone, Copy, Debug)]
pub struct AreaSample {
    pub contact: ContactSample,
    pub area_cm2: f64,
    pub s_cm: f64,
}

impl AreaSample {
    pub const COLUMN_NAMES: [&str; 11] = [
        "region",
        "inner_x_cm",
        "inner_y_cm",
        "outer_x_cm",
        "outer_y_cm",
        "mid_x_cm",
        "mid_y_cm",
        "ray_cm",
        "gap_cm",
        "area_cm2",
        "s_cm",
    ];

    /// 描画・計測の共通行。座標・距離は cm、面積は cm²。
    pub fn measurement_values(self) -> [f64; Self::COLUMN_NAMES.len()] {
        let ray = self.contact.ray;
        [
            f64::from(ray.region as u8),
            ray.inner.x,
            ray.inner.y,
            ray.outer.x,
            ray.outer.y,
            ray.mid.x,
            ray.mid.y,
            ray.gap_cm,
            self.contact.gap_cm,
            self.area_cm2,
            self.s_cm,
        ]
    }
}

pub struct AreaProfile {
    pub samples: Vec<AreaSample>,
    pub pharynx_length_cm: f64,
    pub teeth_s_cm: f64,
    pub length_cm: f64,
    pub lip_area_cm2: f64,
    pub split_index: Option<usize>,
    pub(super) epilarynx: f64,
    pub(super) ventricular: f64,
    pub(crate) body: BodyParameters,
}

impl SagittalModel {
    pub fn area_profile(&self, frame: &SagittalFrame) -> Result<AreaProfile, &'static str> {
        self.area_profile_from_contacts(frame, &self.contact_grid(frame).samples)
    }

    pub(crate) fn area_profile_from_contacts(
        &self,
        frame: &SagittalFrame,
        contacts: &[ContactSample],
    ) -> Result<AreaProfile, &'static str> {
        self.area_profile_from_contacts_reusing(frame, contacts, &mut Vec::new())
    }

    pub(crate) fn area_profile_from_contacts_reusing(
        &self,
        frame: &SagittalFrame,
        contacts: &[ContactSample],
        samples: &mut Vec<AreaSample>,
    ) -> Result<AreaProfile, &'static str> {
        #[cfg(all(not(target_arch = "wasm32"), feature = "render-allocation-probe"))]
        let _allocation = super::allocation_scope(super::AllocationPhase::AreaProfile);
        let teeth_x = self.palate[self.palate.len() - 1].x;
        let k = self.body.scale;
        let epilarynx_length_cm = self.body.epilarynx_length_cm();
        let mut s_cm = epilarynx_length_cm;
        let mut previous = None;
        samples.clear();
        samples.reserve(contacts.len());
        samples.extend(contacts.iter().copied().map(|contact| {
            let mid = contact.ray.mid;
            if let Some(previous) = previous {
                s_cm += (mid - previous).norm();
            }
            previous = Some(mid);
            let gap = contact.gap_cm;
            let power = libm::pow(gap, 1.4);
            let area_cm2 = match contact.ray.region {
                Region::Pharynx => 2.0 * power,
                Region::Oral => {
                    let ahead = smoothstep((mid.x - frame.tip.x) / (0.4 * k));
                    interpolate(2.6 * power, 1.6 * power, ahead)
                }
                Region::Front => {
                    let lip_weight = ((mid.x - teeth_x) / (0.45 * k)).clamp(0.0, 1.0);
                    let ellipse = FRAC_PI_4 * gap * frame.lip_width_cm;
                    interpolate(2.0 * power, ellipse, lip_weight)
                }
            };
            AreaSample {
                contact,
                area_cm2,
                s_cm,
            }
        }));

        for i in 1..samples.len().saturating_sub(1) {
            let ceiling = 1.35 * samples[i - 1].area_cm2.max(samples[i + 1].area_cm2);
            samples[i].area_cm2 = samples[i].area_cm2.min(ceiling);
        }
        if frame.lateral > 0.0 {
            let floor = 0.35 * frame.lateral * k * k;
            for sample in samples.iter_mut() {
                let ray = sample.contact.ray;
                if !matches!(ray.region, Region::Pharynx) && (ray.mid - frame.tip).norm() < 1.4 * k
                {
                    sample.area_cm2 = sample.area_cm2.max(floor);
                }
            }
        }

        let lip = samples.last().ok_or("断面を計算できる測定点がありません")?;
        let split_index = samples
            .iter()
            .position(|sample| matches!(sample.contact.ray.region, Region::Oral));
        let junction = samples
            .get(split_index.unwrap_or(12))
            .ok_or("咽頭端を決める測定点がありません")?;
        let teeth = samples
            .iter()
            .find(|sample| matches!(sample.contact.ray.region, Region::Front))
            .unwrap_or(lip);
        Ok(AreaProfile {
            pharynx_length_cm: junction.s_cm,
            teeth_s_cm: teeth.s_cm,
            length_cm: lip.s_cm,
            lip_area_cm2: lip.area_cm2,
            split_index,
            epilarynx: frame.epilarynx,
            ventricular: frame.ventricular,
            body: self.body,
            samples: std::mem::take(samples),
        })
    }
}

pub(super) fn interpolate(a: f64, b: f64, t: f64) -> f64 {
    a + (b - a) * t
}
