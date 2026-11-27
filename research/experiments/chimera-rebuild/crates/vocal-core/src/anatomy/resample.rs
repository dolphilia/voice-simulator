//! 不等間隔の声道断面を、咽頭と口腔の等長セルへ割り当てる。係数はCHIMERA由来（MIT）。

use std::num::NonZeroUsize;

use super::AreaProfile;
use super::area::interpolate;

const SUBSAMPLES: usize = 8;
const CLOSURE_AREA_CM2: f64 = 1e-5;

#[derive(Clone, Copy, Debug)]
pub struct TractCell {
    pub area_cm2: f64,
    pub minimum_area_cm2: f64,
}

impl TractCell {
    const CLOSED: Self = Self {
        area_cm2: 0.0,
        minimum_area_cm2: 0.0,
    };
}

#[derive(Clone)]
pub struct TubeProfile {
    pub length_cm: f64,
    pub cells: Vec<TractCell>,
}

#[derive(Clone)]
pub struct ResampledTract {
    pub pharynx: TubeProfile,
    pub oral: TubeProfile,
}

impl AreaProfile {
    pub fn resample(
        &self,
        pharynx_cells: NonZeroUsize,
        oral_cells: NonZeroUsize,
    ) -> Result<ResampledTract, &'static str> {
        self.resample_reusing(pharynx_cells, oral_cells, None)
    }

    /// 入力を検査した後、直前のセル領域へ再標本化する。
    pub(crate) fn resample_reusing(
        &self,
        pharynx_cells: NonZeroUsize,
        oral_cells: NonZeroUsize,
        previous: Option<&mut ResampledTract>,
    ) -> Result<ResampledTract, &'static str> {
        #[cfg(all(not(target_arch = "wasm32"), feature = "render-allocation-probe"))]
        let _allocation = super::allocation_scope(super::AllocationPhase::Resample);
        let split = self.pharynx_length_cm;
        if !(self.length_cm.is_finite() && 0.0 < split && split < self.length_cm)
            || self.samples.is_empty()
            || self.samples.iter().any(|sample| {
                !sample.s_cm.is_finite() || !sample.area_cm2.is_finite() || sample.area_cm2 < 0.0
            })
            || self
                .samples
                .windows(2)
                .any(|pair| pair[1].s_cm < pair[0].s_cm)
        {
            return Err("咽頭・口腔の長さと、距離順に並ぶ非負の面積が必要です");
        }
        let (pharynx_buffer, oral_buffer) = previous
            .map(|tract| {
                (
                    std::mem::take(&mut tract.pharynx.cells),
                    std::mem::take(&mut tract.oral.cells),
                )
            })
            .unwrap_or_default();
        Ok(ResampledTract {
            pharynx: self.tube(0.0, split, pharynx_cells, pharynx_buffer),
            oral: self.tube(split, self.length_cm, oral_cells, oral_buffer),
        })
    }

    fn tube(
        &self,
        start: f64,
        end: f64,
        count: NonZeroUsize,
        mut cells: Vec<TractCell>,
    ) -> TubeProfile {
        let length_cm = end - start;
        let step = length_cm / count.get() as f64;
        cells.clear();
        cells.extend(
            (0..count.get()).map(|index| self.cell(start, step, index, index + 1 == count.get())),
        );
        TubeProfile { length_cm, cells }
    }

    fn cell(&self, origin: f64, step: f64, index: usize, last: bool) -> TractCell {
        let start = origin + step * index as f64;
        // 最終点が丸めで区間の外へ出ても含める。
        let end = origin + step * (index + 1) as f64 + if last { 1e-6 } else { 0.0 };
        let first = self.samples.partition_point(|sample| sample.s_cm < start);
        let mut minimum = self.samples[first..]
            .iter()
            .take_while(|sample| sample.s_cm <= end)
            .map(|sample| sample.area_cm2)
            .fold(f64::INFINITY, f64::min);
        if minimum <= CLOSURE_AREA_CM2 {
            return TractCell::CLOSED;
        }
        let mut inverse_sum = 0.0;
        for sub in 0..SUBSAMPLES {
            let offset = index as f64 + (sub as f64 + 0.5) / SUBSAMPLES as f64;
            let area = self.area_at(origin + step * offset);
            if area <= CLOSURE_AREA_CM2 {
                return TractCell::CLOSED;
            }
            minimum = minimum.min(area);
            inverse_sum += 1.0 / area;
        }
        let area_cm2 = SUBSAMPLES as f64 / inverse_sum;
        TractCell {
            area_cm2,
            minimum_area_cm2: minimum.min(area_cm2),
        }
    }

    fn area_at(&self, s: f64) -> f64 {
        let samples = &self.samples;
        let first = samples[0].area_cm2;
        let epilarynx_length_cm = self.body.epilarynx_length_cm();
        if s <= epilarynx_length_cm {
            let transition = 0.1 * epilarynx_length_cm;
            let start = epilarynx_length_cm - transition;
            let k = self.body.scale;
            let area = self.epilarynx_area(s / epilarynx_length_cm) * k * k;
            return if s <= start {
                area
            } else {
                interpolate(area, first, (s - start) / transition)
            };
        }
        if s <= samples[0].s_cm {
            return first;
        }
        let right = samples.partition_point(|sample| sample.s_cm <= s);
        let before = samples[right - 1];
        let Some(after) = samples.get(right) else {
            return before.area_cm2;
        };
        let fraction = (s - before.s_cm) / (after.s_cm - before.s_cm).max(1e-9);
        interpolate(before.area_cm2, after.area_cm2, fraction)
    }

    fn epilarynx_area(&self, u: f64) -> f64 {
        let vent = 0.95 * (1.0 - 0.75 * self.ventricular.clamp(0.0, 1.0));
        let top = interpolate(1.9, 0.35, self.epilarynx.clamp(0.0, 1.0));
        let piece = |position| {
            if position < 0.3 {
                1.3
            } else if position < 0.5 {
                vent
            } else {
                interpolate(1.2, top, (position - 0.5) / 0.5).min(top)
            }
        };
        let half_ramp = 0.03;
        for boundary in [0.3_f64, 0.5] {
            if (u - boundary).abs() < half_ramp {
                let low = boundary - half_ramp;
                let high = boundary + half_ramp;
                return interpolate(piece(low), piece(high), (u - low) / (2.0 * half_ramp));
            }
        }
        piece(u)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::anatomy::{Articulation, SagittalModel};

    #[test]
    fn rejected_profile_preserves_buffers_for_next_resample() {
        let model = SagittalModel::adult_male();
        let frame = model.compute(Articulation::neutral());
        let mut profile = model.area_profile(&frame).unwrap();
        let pharynx = NonZeroUsize::new(18).unwrap();
        let oral = NonZeroUsize::new(20).unwrap();
        let mut previous = profile.resample(pharynx, oral).unwrap();
        let bits = |tract: &ResampledTract| {
            [&tract.pharynx, &tract.oral].map(|tube| {
                let values = tube
                    .cells
                    .iter()
                    .flat_map(|cell| [cell.area_cm2.to_bits(), cell.minimum_area_cm2.to_bits()])
                    .collect::<Vec<_>>();
                (tube.length_cm.to_bits(), values)
            })
        };
        let expected = bits(&previous);
        let pointers = [
            previous.pharynx.cells.as_ptr(),
            previous.oral.cells.as_ptr(),
        ];
        let last = profile.samples.last_mut().unwrap();
        let area = std::mem::replace(&mut last.area_cm2, f64::NAN);
        assert!(
            profile
                .resample_reusing(pharynx, oral, Some(&mut previous))
                .is_err()
        );
        assert_eq!(bits(&previous), expected);
        profile.samples.last_mut().unwrap().area_cm2 = area;
        let actual = profile
            .resample_reusing(pharynx, oral, Some(&mut previous))
            .unwrap();
        assert_eq!(
            [actual.pharynx.cells.as_ptr(), actual.oral.cells.as_ptr()],
            pointers
        );
        assert_eq!(bits(&actual), expected);
    }
}
