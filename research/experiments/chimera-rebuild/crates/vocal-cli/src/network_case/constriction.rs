//! 制御ブロックごとの断面目標に、移動する狭窄の軌跡を展開する。

use super::{AreaRamp, AreaTarget, Tube};
use serde::Deserialize;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct SlidingConstriction {
    tube: usize,
    block_samples: usize,
    width_cells: f64,
    depth: Vec<(usize, f64)>,
    center_cells: Vec<(usize, f64)>,
}

impl SlidingConstriction {
    pub(super) fn ramps(
        &self,
        tubes: &[Tube],
        samples: usize,
    ) -> Result<Vec<AreaRamp>, &'static str> {
        let tube = tubes
            .get(self.tube)
            .ok_or("狭窄の対象になる管が存在しません")?;
        if self.block_samples == 0 || !self.width_cells.is_finite() || self.width_cells <= 0.0 {
            return Err("狭窄の幅と制御ブロック長は正の値にしてください");
        }
        let last_cell = tube.areas_cm2.len().saturating_sub(1) as f64;
        for (curve, limit) in [(&self.depth, f64::MAX), (&self.center_cells, last_cell)] {
            if curve.first().map(|point| point.0) != Some(0)
                || curve.windows(2).any(|pair| pair[0].0 >= pair[1].0)
                || curve
                    .iter()
                    .any(|&(_, value)| !(0.0..=limit).contains(&value))
            {
                return Err(
                    "狭窄の軌跡はサンプル0から時刻順に、深さは非負、中心は管内で指定してください",
                );
            }
        }

        let first_node = tubes[..self.tube]
            .iter()
            .map(|tube| tube.areas_cm2.len())
            .sum::<usize>();
        let mut ramps = Vec::with_capacity(samples.div_ceil(self.block_samples));
        for start_sample in (0..samples).step_by(self.block_samples) {
            let sample_count = self.block_samples.min(samples - start_sample);
            let end_sample = start_sample + sample_count;
            let depth = value_at(&self.depth, end_sample);
            let center = value_at(&self.center_cells, end_sample);
            let targets = tube
                .areas_cm2
                .iter()
                .enumerate()
                .map(|(cell, &rest_area)| {
                    let distance = (cell as f64 - center) / self.width_cells;
                    let remaining = (1.0 - depth * (-distance.powi(2)).exp()).max(0.0);
                    AreaTarget {
                        node: first_node + cell,
                        area_cm2: rest_area * remaining,
                        minimum_area_cm2: None,
                    }
                })
                .collect();
            ramps.push(AreaRamp {
                start_sample,
                sample_count,
                block_samples: sample_count,
                targets,
            });
        }
        Ok(ramps)
    }
}

fn value_at(curve: &[(usize, f64)], sample: usize) -> f64 {
    let next = curve.partition_point(|&(time, _)| time <= sample);
    let (start, from) = curve[next - 1];
    let Some(&(end, to)) = curve.get(next) else {
        return from;
    };
    let fraction = (sample - start) as f64 / (end - start) as f64;
    from + (to - from) * fraction
}
