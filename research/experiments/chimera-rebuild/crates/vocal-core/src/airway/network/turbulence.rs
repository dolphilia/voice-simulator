//! 狭窄のレイノルズ数で駆動する帯域雑音と、枝への圧力注入。

use super::{AIR_DENSITY, Branch, CLOSED_AREA_CM2, DYNAMIC_VISCOSITY};
use crate::random::Mulberry32;
use std::f64::consts::{PI, TAU};

const CRITICAL_REYNOLDS: f64 = 1800.0;
const SATURATION_REYNOLDS: f64 = 12000.0;
const KINEMATIC_VISCOSITY: f64 = DYNAMIC_VISCOSITY / AIR_DENSITY;

#[derive(Clone, Copy, Debug)]
pub struct NoiseSpec {
    pub source: usize,
    pub forward: usize,
    pub reverse: usize,
    pub gain: f64,
    pub lowpass_hz: f64,
    pub highpass_hz: f64,
}

struct NoiseSource {
    spec: NoiseSpec,
    highpass_pole: f64,
    lowpass_amount: f64,
    highpass_average: f64,
    first_lowpass: f64,
    second_lowpass: f64,
    level: f64,
}

pub(super) struct Turbulence {
    rate_hz: f64,
    scale: f64,
    random: Mulberry32,
    sources: Vec<NoiseSource>,
    next_sources: Vec<NoiseSource>,
    pub(super) pressure: Vec<f64>,
}

impl Turbulence {
    pub(super) fn new(rate_hz: u32, branches: usize) -> Self {
        Self {
            rate_hz: f64::from(rate_hz),
            scale: 1.0,
            random: Mulberry32::new(12345),
            sources: Vec::new(),
            next_sources: Vec::new(),
            pressure: vec![0.0; branches],
        }
    }

    pub(super) fn set_seed(&mut self, seed: u32) {
        self.random = Mulberry32::new(seed);
    }

    pub(super) fn reserve_sources(&mut self, count: usize) {
        // 登録を更新するたびに入れ替えるので、両方に必要な領域を確保する。
        for buffer in [&mut self.sources, &mut self.next_sources] {
            buffer.reserve_exact(count.saturating_sub(buffer.len()));
        }
    }

    pub(super) fn set_scale(&mut self, scale: f64) -> Result<(), &'static str> {
        if !scale.is_finite() || scale < 0.0 {
            return Err("乱流の倍率は有限の非負値で指定してください");
        }
        self.scale = scale;
        Ok(())
    }

    pub(super) fn set_sources(&mut self, specs: &[NoiseSpec]) -> Result<(), &'static str> {
        let branches = self.pressure.len();
        if specs.iter().any(|spec| {
            [spec.source, spec.forward, spec.reverse]
                .into_iter()
                .any(|i| i >= branches)
                || [spec.gain, spec.highpass_hz, spec.lowpass_hz]
                    .into_iter()
                    .any(|x| !x.is_finite() || x < 0.0)
        }) {
            return Err("乱流源に実在する枝と有効な利得・周波数を指定してください");
        }
        self.next_sources.clear();
        for &spec in specs {
            let prior = self
                .sources
                .iter()
                .find(|old| old.spec.source == spec.source && old.spec.forward == spec.forward);
            self.next_sources.push(NoiseSource {
                spec,
                highpass_pole: libm::exp(-TAU * spec.highpass_hz / self.rate_hz),
                lowpass_amount: 1.0 - libm::exp(-TAU * spec.lowpass_hz / self.rate_hz),
                highpass_average: prior.map_or(0.0, |old| old.highpass_average),
                first_lowpass: prior.map_or(0.0, |old| old.first_lowpass),
                second_lowpass: prior.map_or(0.0, |old| old.second_lowpass),
                level: 0.0,
            });
        }
        std::mem::swap(&mut self.sources, &mut self.next_sources);
        self.pressure.fill(0.0);
        Ok(())
    }

    pub(super) fn spec(&self, source: usize) -> Option<NoiseSpec> {
        self.sources.get(source).map(|source| source.spec)
    }

    pub(super) fn set_gain(&mut self, source: usize, gain: f64) -> Result<(), &'static str> {
        if !gain.is_finite() || gain < 0.0 {
            return Err("乱流源の利得は有限の非負値で指定してください");
        }
        let source = self.sources.get_mut(source).ok_or("乱流源がありません")?;
        // 同じ乱流源のフィルタと乱数列を保ったまま利得を変える。
        source.spec.gain = gain;
        Ok(())
    }

    pub(super) fn level(&self, source: usize) -> Option<f64> {
        self.sources.get(source).map(|source| source.level)
    }

    pub(super) fn step(&mut self, branches: &[Branch]) {
        if self.sources.is_empty() {
            return;
        }
        self.pressure.fill(0.0);
        let scale = self.scale * (96000.0 / self.rate_hz).sqrt();
        let saturation = SATURATION_REYNOLDS.powi(2) - CRITICAL_REYNOLDS.powi(2);
        for source in &mut self.sources {
            let branch = &branches[source.spec.source];
            let flow = branch.flow;
            let mut level = 0.0;
            if branch.area_cm2 > CLOSED_AREA_CM2 {
                let reynolds =
                    2.0 * flow.abs() / (KINEMATIC_VISCOSITY * (PI * branch.area_cm2).sqrt());
                if reynolds > CRITICAL_REYNOLDS {
                    let excess = reynolds.powi(2) - CRITICAL_REYNOLDS.powi(2);
                    level = source.spec.gain * scale * excess / (1.0 + excess / saturation);
                }
            }
            // 振幅がゼロの間も乱数列とフィルタを進める。
            let white = self.random.bipolar() * 1.732;
            source.highpass_average +=
                (1.0 - source.highpass_pole) * (white - source.highpass_average);
            let highpassed = white - source.highpass_average;
            source.first_lowpass += source.lowpass_amount * (highpassed - source.first_lowpass);
            source.second_lowpass +=
                source.lowpass_amount * (source.first_lowpass - source.second_lowpass);
            source.level = level;
            if level != 0.0 {
                let pressure = level * source.second_lowpass;
                if flow >= 0.0 {
                    self.pressure[source.spec.forward] += pressure;
                } else {
                    self.pressure[source.spec.reverse] -= pressure;
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::airway::{
        human::HumanAirway, network::Section, tract_control::HumanTractControl, viscous_factor,
    };
    use crate::anatomy::Articulation;

    #[test]
    fn human_airway_reuses_both_noise_registrations_without_changing_filter_state() {
        let rate = 96_000;
        let tract = HumanTractControl::adult_male(rate, Articulation::neutral()).unwrap();
        let network = HumanAirway::from_targets(rate, tract.targets())
            .unwrap()
            .network;
        let mut reserved = network.turbulence;
        let mut branches = network.branches;
        branches[0].area_cm2 = 0.08;
        branches[0].flow = 250.0;
        branches[1].area_cm2 = 0.04;
        branches[1].flow = -180.0;
        let mut reference = Turbulence::new(rate, branches.len());
        reserved.set_seed(12345);
        reference.set_seed(12345);

        let base = NoiseSpec {
            source: 0,
            forward: 1,
            reverse: 2,
            gain: 3.2e-6,
            lowpass_hz: 3500.0,
            highpass_hz: 300.0,
        };
        let narrow = NoiseSpec {
            source: 1,
            forward: 2,
            reverse: 0,
            gain: 1.364e-6,
            lowpass_hz: 2600.0,
            highpass_hz: 350.0,
        };
        let teeth = NoiseSpec {
            forward: 0,
            reverse: 2,
            highpass_hz: 1200.0,
            ..narrow
        };
        let louder = NoiseSpec {
            gain: 2.0 * narrow.gain,
            ..narrow
        };
        let filter_state = |source: &NoiseSource| {
            [
                source.highpass_average,
                source.first_lowpass,
                source.second_lowpass,
                source.level,
            ]
            .map(f64::to_bits)
        };

        assert!(reserved.sources.capacity() >= 3 && reserved.next_sources.capacity() >= 3);
        let mut current = reserved.sources.as_ptr();
        let mut next = reserved.next_sources.as_ptr();
        let registrations: [&[NoiseSpec]; 4] = [
            &[base],
            &[base, narrow, teeth],
            &[louder, base, teeth],
            &[base],
        ];
        for specs in registrations {
            reserved.set_sources(specs).unwrap();
            reference.set_sources(specs).unwrap();
            std::mem::swap(&mut current, &mut next);
            assert_eq!(reserved.sources.as_ptr(), current);
            assert_eq!(reserved.next_sources.as_ptr(), next);
            assert!(
                reserved
                    .sources
                    .iter()
                    .map(filter_state)
                    .eq(reference.sources.iter().map(filter_state))
            );
            for _ in 0..128 {
                reserved.step(&branches);
                reference.step(&branches);
                assert!(
                    reserved
                        .sources
                        .iter()
                        .map(filter_state)
                        .eq(reference.sources.iter().map(filter_state))
                );
                assert!(
                    reserved
                        .pressure
                        .iter()
                        .copied()
                        .map(f64::to_bits)
                        .eq(reference.pressure.iter().copied().map(f64::to_bits))
                );
            }
            assert!(reserved.pressure.iter().any(|&p| p != 0.0));
        }
    }

    #[test]
    fn retains_filter_state_when_gain_changes() {
        let section = Section {
            length_cm: 0.4,
            area_cm2: 0.08,
            minimum_area_cm2: 0.08,
            perimeter_factor: 1.0,
            viscous_factor: 1.0,
            wall: None,
        };
        let sections = [section; 3];
        let mut sections_branches = [
            Branch::new([0, 1], None, &sections, viscous_factor()),
            Branch::new([1, 2], None, &sections, viscous_factor()),
        ];
        sections_branches[0].flow = 250.0;
        let spec = NoiseSpec {
            source: 0,
            forward: 1,
            reverse: 0,
            gain: 1.364e-6,
            lowpass_hz: 2600.0,
            highpass_hz: 350.0,
        };
        let mut control = Turbulence::new(96000, sections_branches.len());
        let mut changed = Turbulence::new(96000, sections_branches.len());
        for model in [&mut control, &mut changed] {
            model.set_sources(&[spec]).unwrap();
            for _ in 0..128 {
                model.step(&sections_branches);
            }
        }
        changed
            .set_sources(&[NoiseSpec {
                gain: 2.0 * spec.gain,
                ..spec
            }])
            .unwrap();
        control.step(&sections_branches);
        changed.step(&sections_branches);
        assert_ne!(control.pressure[1], 0.0);
        assert_eq!(changed.pressure[1], 2.0 * control.pressure[1]);
        changed.set_sources(&[]).unwrap();
        changed.step(&sections_branches);
        assert_eq!(changed.pressure, [0.0, 0.0]);
    }
}
