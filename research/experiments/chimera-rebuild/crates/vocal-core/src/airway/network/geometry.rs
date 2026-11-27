//! セルの面積補間と移動壁の体積速度源。

use super::{SOUND_SPEED, Section, trim_tiny};
use std::f64::consts::TAU;

const SQUEEZE_AREA_CM2: f64 = 0.12;
const VOLUME_SOURCE_CUTOFF_HZ: f64 = 60.0;

#[derive(Clone, Copy)]
struct VolumeCell {
    volume_cm3: f64,
    target_minimum_area_cm2: f64,
    area_increment_cm2: f64,
    minimum_area_increment_cm2: f64,
    length_increment_cm: f64,
    first_pole: f64,
    filtered_flow: f64,
}

pub(super) struct MovingAreas {
    cells: Vec<VolumeCell>,
    spill: Vec<f64>,
    remaining: usize,
    coefficient: f64,
    enabled: bool,
}

impl MovingAreas {
    pub(super) fn new(sections: &[Section], dt: f64) -> Self {
        Self {
            cells: sections
                .iter()
                .map(|section| VolumeCell {
                    volume_cm3: section.volume(),
                    target_minimum_area_cm2: section.minimum_area_cm2,
                    area_increment_cm2: 0.0,
                    minimum_area_increment_cm2: 0.0,
                    length_increment_cm: 0.0,
                    first_pole: 0.0,
                    filtered_flow: 0.0,
                })
                .collect(),
            spill: vec![0.0; sections.len()],
            remaining: 0,
            coefficient: 1.0 - libm::exp(-TAU * VOLUME_SOURCE_CUTOFF_HZ * dt),
            enabled: false,
        }
    }

    pub(super) fn set_targets(
        &mut self,
        sections: &[Section],
        targets: &[[f64; 2]],
        lengths_cm: Option<&[f64]>,
        steps: usize,
        dt: f64,
    ) -> Result<(), &'static str> {
        if let Some(lengths) = lengths_cm
            && (lengths.len() != sections.len()
                || lengths.iter().any(|&length| {
                    let courant = SOUND_SPEED * dt / length;
                    !(0.0 < courant && courant < 1.0)
                }))
        {
            return Err(
                "節点ごとの補間先のセル長は、クーラン数が0より大きく1未満になる値を指定してください",
            );
        }
        let target_length =
            |index: usize| lengths_cm.map_or(sections[index].length_cm, |lengths| lengths[index]);
        if steps == 0
            || targets.len() != self.cells.len()
            || targets.iter().enumerate().any(|(index, &[area, minimum])| {
                let current = sections[index];
                let maximum_volume = Section {
                    area_cm2: area.max(current.area_cm2),
                    length_cm: target_length(index).max(current.length_cm),
                    ..current
                }
                .volume();
                !area.is_finite() || !(0.0..=area).contains(&minimum) || !maximum_volume.is_finite()
            })
        {
            return Err("有限の非負面積を全節点分と、正の補間サンプル数を指定してください");
        }
        let scale = 1.0 / steps as f64;
        for (index, (cell, &[target, minimum])) in self.cells.iter_mut().zip(targets).enumerate() {
            let section = sections[index];
            cell.target_minimum_area_cm2 = minimum;
            cell.area_increment_cm2 = (target - section.area_cm2) * scale;
            cell.minimum_area_increment_cm2 = (minimum - section.minimum_area_cm2) * scale;
            cell.length_increment_cm = (target_length(index) - section.length_cm) * scale;
        }
        self.remaining = steps;
        self.enabled = true;
        Ok(())
    }

    pub(super) fn filtered_flow(&self, node: usize) -> f64 {
        self.cells[node].filtered_flow
    }

    pub(super) fn trim_tiny_flow(&mut self) {
        for cell in &mut self.cells {
            trim_tiny(&mut cell.first_pole);
            trim_tiny(&mut cell.filtered_flow);
        }
    }

    pub(super) fn step(
        &mut self,
        sections: &mut [Section],
        neighbors: &[Vec<usize>],
        dt: f64,
        flow: &mut [f64],
    ) -> bool {
        if !self.enabled {
            return false;
        }
        self.spill.fill(0.0);
        let changing = self.remaining > 0;
        if changing {
            self.remaining -= 1;
            for i in 0..sections.len() {
                let section = &mut sections[i];
                let cell = &mut self.cells[i];
                section.area_cm2 = (section.area_cm2 + cell.area_increment_cm2).max(0.0);
                section.minimum_area_cm2 = (section.minimum_area_cm2
                    + cell.minimum_area_increment_cm2)
                    .clamp(0.0, section.area_cm2);
                section.length_cm += cell.length_increment_cm;
                let area = section.minimum_area_cm2;
                let next_volume = section.volume();
                let raw = (cell.volume_cm3 - next_volume) / dt;
                cell.volume_cm3 = next_volume;
                if raw == 0.0 || area >= SQUEEZE_AREA_CM2 {
                    self.spill[i] += raw;
                    continue;
                }

                // 狭まるセルで生じた流量を開いている近隣へ移し、その後に平滑化する。
                let s = area / SQUEEZE_AREA_CM2;
                let keep = s * s * (3.0 - 2.0 * s);
                self.spill[i] += raw * keep;
                let open = neighbors[i].iter().copied().filter(|&node| {
                    sections[node].minimum_area_cm2 >= SQUEEZE_AREA_CM2
                        || self.cells[node].target_minimum_area_cm2 >= SQUEEZE_AREA_CM2
                });
                let count = open.clone().count();
                if count > 0 {
                    let share = raw * (1.0 - keep) / count as f64;
                    for node in open {
                        self.spill[node] += share;
                    }
                }
            }
        }
        for ((cell, &injection), sum) in self.cells.iter_mut().zip(&self.spill).zip(flow) {
            cell.first_pole += self.coefficient * (injection - cell.first_pole);
            cell.filtered_flow += self.coefficient * (cell.first_pole - cell.filtered_flow);
            *sum += cell.filtered_flow;
        }
        changing
    }
}
