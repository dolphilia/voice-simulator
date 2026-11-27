//! 制御周期ごとに咽頭・口腔の断面と管長の目標を決める。係数はCHIMERA由来（MIT）。

use std::num::NonZeroUsize;

use crate::anatomy::{
    AreaProfile, AreaSample, Articulation, BodyMix, BodyName, BodyParameters, ContactGridScratch,
    INNER_LIP_POINTS, MAX_MEASUREMENT_RAYS, Point, ResampledTract, RoofContact, SagittalFrame,
    SagittalModel, TubeProfile,
};
#[cfg(all(not(target_arch = "wasm32"), feature = "render-allocation-probe"))]
use crate::render_allocation_probe::{Phase as AllocationPhase, scope as allocation_scope};

use super::SOUND_SPEED;

pub(super) struct TractSampling {
    pub(super) design_cell_length_cm: f64,
    stable_cell_length_cm: f64,
    pharynx_cells: NonZeroUsize,
    oral_cells: NonZeroUsize,
    oral_cells_override: Option<NonZeroUsize>,
}

impl TractSampling {
    pub(super) fn for_body(
        sample_rate_hz: u32,
        body: BodyParameters,
    ) -> Result<Self, &'static str> {
        Self::with_oral_cells(sample_rate_hz, body, None)
    }

    pub(super) fn with_oral_cells(
        sample_rate_hz: u32,
        body: BodyParameters,
        oral_cells: Option<NonZeroUsize>,
    ) -> Result<Self, &'static str> {
        if sample_rate_hz == 0 {
            return Err("内部サンプルレートには正値を指定してください");
        }
        if oral_cells.is_some_and(|count| count.get() < 8) {
            return Err("口腔の格子を指定する場合は8セル以上を使ってください");
        }
        let propagation_per_sample = SOUND_SPEED / f64::from(sample_rate_hz);
        let design_cell_length_cm = propagation_per_sample / 0.93;
        let count = |length: f64| {
            NonZeroUsize::new(((length / design_cell_length_cm).floor() as usize).max(8)).unwrap()
        };
        Ok(Self {
            design_cell_length_cm,
            stable_cell_length_cm: propagation_per_sample / 0.97,
            pharynx_cells: count(
                8.7 * body.scale * (0.55 + 0.45 * body.pharynx) - 1.6 * body.scale,
            ),
            oral_cells: oral_cells.unwrap_or_else(|| count(8.3 * body.scale - body.scale)),
            oral_cells_override: oral_cells,
        })
    }

    pub(super) fn resample(&self, profile: &AreaProfile) -> Result<ResampledTract, &'static str> {
        self.resample_reusing(profile, None)
    }

    fn resample_reusing(
        &self,
        profile: &AreaProfile,
        previous: Option<&mut ResampledTract>,
    ) -> Result<ResampledTract, &'static str> {
        if let Some(count) = self.oral_cells_override
            && count.get() as f64 * self.stable_cell_length_cm
                > profile.length_cm - profile.pharynx_length_cm
        {
            return Err("指定した口腔セル数では解剖上の管長でクーラン数が0.97を超えます");
        }
        profile.resample_reusing(self.pharynx_cells, self.oral_cells, previous)
    }

    pub(super) fn matches(&self, tract: &ResampledTract) -> bool {
        tract.pharynx.cells.len() == self.pharynx_cells.get()
            && tract.oral.cells.len() == self.oral_cells.get()
    }

    pub(super) fn simulation_length(&self, tube: &TubeProfile) -> f64 {
        tube.length_cm
            .max(tube.cells.len() as f64 * self.stable_cell_length_cm)
    }
}

pub struct TractTargets {
    pub(super) body: BodyParameters,
    pub(crate) oral_cells_override: Option<NonZeroUsize>,
    area_samples: Vec<AreaSample>,
    pub raw: ResampledTract,
    pub limited: ResampledTract,
    pub pharynx_simulation_length_cm: f64,
    pub oral_simulation_length_cm: f64,
    pub teeth_s_cm: f64,
    pub lips_from: usize,
    pub tip_contact: RoofContact,
    pub body_contact: RoofContact,
    pub velum_cm2: f64,
}

impl TractTargets {
    pub fn body_scale(&self) -> f64 {
        self.body.scale
    }
}

pub struct HumanTractControl {
    model: SagittalModel,
    sampling: TractSampling,
    frame: SagittalFrame,
    contact_scratch: ContactGridScratch,
    area_scratch: Vec<AreaSample>,
    current: TractTargets,
    baseline: ResampledTract,
    dt: f64,
}

impl HumanTractControl {
    /// 初期形状を断面制限の基準にする。
    pub fn adult_male(sample_rate_hz: u32, posture: Articulation) -> Result<Self, &'static str> {
        Self::for_body(sample_rate_hz, BodyName::Male.into(), posture)
    }

    pub fn for_body(
        sample_rate_hz: u32,
        body: BodyMix,
        posture: Articulation,
    ) -> Result<Self, &'static str> {
        Self::with_oral_cells(sample_rate_hz, body, posture, None)
    }

    /// 指定された口腔格子で、管長を延長せずに計測する。
    pub fn with_oral_cells(
        sample_rate_hz: u32,
        body: BodyMix,
        posture: Articulation,
        oral_cells: Option<NonZeroUsize>,
    ) -> Result<Self, &'static str> {
        let model = SagittalModel::new(body);
        let sampling =
            TractSampling::with_oral_cells(sample_rate_hz, body.parameters(), oral_cells)?;
        let mut frame = model.frame_buffer();
        let mut contact_scratch = ContactGridScratch::default();
        let mut area_samples = Vec::with_capacity(MAX_MEASUREMENT_RAYS);
        let current = geometry(
            &model,
            &sampling,
            &mut frame,
            &mut contact_scratch,
            &mut area_samples,
            posture,
            None,
        )?;
        Ok(Self {
            model,
            sampling,
            frame,
            contact_scratch,
            area_scratch: Vec::with_capacity(MAX_MEASUREMENT_RAYS),
            baseline: current.limited.clone(),
            current,
            dt: 0.0,
        })
    }

    pub fn targets(&self) -> &TractTargets {
        &self.current
    }

    pub(crate) fn lower_lip_edge_cm(&self) -> Point {
        self.frame.lower_lip[INNER_LIP_POINTS - 1]
    }

    pub(crate) fn area_samples(&self) -> &[AreaSample] {
        &self.current.area_samples
    }

    /// 直前に確定した断面を、このフレームの基準として保存する。
    pub fn apply(&mut self, posture: Articulation, dt: f64) -> Result<&TractTargets, &'static str> {
        #[cfg(all(not(target_arch = "wasm32"), feature = "render-allocation-probe"))]
        let _allocation = allocation_scope(AllocationPhase::Apply);
        if !dt.is_finite() || dt < 0.0 {
            return Err("制御周期には有限の非負値を指定してください");
        }
        // 新しい周期の制限に使う断面は current にあり、古い baseline の領域を回せる。
        let mut next = geometry(
            &self.model,
            &self.sampling,
            &mut self.frame,
            &mut self.contact_scratch,
            &mut self.area_scratch,
            posture,
            Some((&mut self.current.raw, &mut self.baseline)),
        )?;
        next.limit_against(&self.current.limited, dt);
        let previous = std::mem::replace(&mut self.current, next);
        self.baseline = previous.limited;
        self.area_scratch = previous.area_samples;
        self.dt = dt;
        Ok(&self.current)
    }

    /// 接触補正後も、フレーム開始時点の断面と同じ制御周期を使う。
    pub fn reapply(&mut self, posture: Articulation) -> Result<&TractTargets, &'static str> {
        #[cfg(all(not(target_arch = "wasm32"), feature = "render-allocation-probe"))]
        let _allocation = allocation_scope(AllocationPhase::Reapply);
        // 同じ周期の基準は baseline に残し、直前の計算結果の領域を回す。
        let mut next = geometry(
            &self.model,
            &self.sampling,
            &mut self.frame,
            &mut self.contact_scratch,
            &mut self.area_scratch,
            posture,
            Some((&mut self.current.raw, &mut self.current.limited)),
        )?;
        next.limit_against(&self.baseline, self.dt);
        let previous = std::mem::replace(&mut self.current, next);
        self.area_scratch = previous.area_samples;
        Ok(&self.current)
    }
}

fn geometry(
    model: &SagittalModel,
    sampling: &TractSampling,
    frame: &mut SagittalFrame,
    contact_scratch: &mut ContactGridScratch,
    area_scratch: &mut Vec<AreaSample>,
    posture: Articulation,
    previous: Option<(&mut ResampledTract, &mut ResampledTract)>,
) -> Result<TractTargets, &'static str> {
    model.compute_into(posture, frame);
    let (tip_contact, body_contact) = model.contact_grid_into(frame, contact_scratch);
    let profile =
        model.area_profile_from_contacts_reusing(frame, &contact_scratch.samples, area_scratch)?;
    let (previous_raw, previous_limited) = previous.unzip();
    let raw = match sampling.resample_reusing(&profile, previous_raw) {
        Ok(raw) => raw,
        Err(error) => {
            // 再標本化に失敗しても、候補に使った領域を次回へ戻す。
            *area_scratch = profile.samples;
            return Err(error);
        }
    };
    let lips_from = (raw.oral.cells.len() as f64
        * (1.0 - (profile.length_cm - profile.teeth_s_cm) / raw.oral.length_cm))
        as usize;
    Ok(TractTargets {
        body: profile.body,
        oral_cells_override: sampling.oral_cells_override,
        area_samples: profile.samples,
        limited: {
            #[cfg(all(not(target_arch = "wasm32"), feature = "render-allocation-probe"))]
            let _allocation = allocation_scope(AllocationPhase::CloneCells);
            match previous_limited {
                Some(previous) => ResampledTract {
                    pharynx: copy_into_cell_buffer(&raw.pharynx, &mut previous.pharynx),
                    oral: copy_into_cell_buffer(&raw.oral, &mut previous.oral),
                },
                None => raw.clone(),
            }
        },
        pharynx_simulation_length_cm: sampling.simulation_length(&raw.pharynx),
        oral_simulation_length_cm: sampling.simulation_length(&raw.oral),
        teeth_s_cm: profile.teeth_s_cm,
        lips_from,
        tip_contact,
        body_contact,
        velum_cm2: frame.velum_port_cm2,
        raw,
    })
}

/// 計算が成功してから、使い終わった細管のセル容量だけを引き継ぐ。
fn copy_into_cell_buffer(raw: &TubeProfile, previous: &mut TubeProfile) -> TubeProfile {
    let mut cells = std::mem::take(&mut previous.cells);
    cells.clear();
    cells.extend_from_slice(&raw.cells);
    TubeProfile {
        length_cm: raw.length_cm,
        cells,
    }
}

impl TractTargets {
    fn limit_against(&mut self, baseline: &ResampledTract, dt: f64) {
        if dt > 0.0 {
            let area_scale = self.body.scale * self.body.scale;
            limit_tube(
                &mut self.limited.pharynx,
                &baseline.pharynx,
                usize::MAX,
                dt,
                area_scale,
            );
            limit_tube(
                &mut self.limited.oral,
                &baseline.oral,
                self.lips_from,
                dt,
                area_scale,
            );
        }
    }
}

fn limit_tube(
    target: &mut TubeProfile,
    baseline: &TubeProfile,
    lips_from: usize,
    dt: f64,
    area_scale: f64,
) {
    for (index, (cell, old)) in target.cells.iter_mut().zip(&baseline.cells).enumerate() {
        let lip = index >= lips_from;
        cell.area_cm2 = limit_area(cell.area_cm2, old.area_cm2, lip, dt, area_scale);
        cell.minimum_area_cm2 = limit_area(
            cell.minimum_area_cm2,
            old.minimum_area_cm2,
            lip,
            dt,
            area_scale,
        )
        .clamp(0.0, cell.area_cm2);
    }
}

fn limit_area(target: f64, old: f64, lip: bool, dt: f64, area_scale: f64) -> f64 {
    let open = 45.0 * area_scale;
    let seal = 5.0 * area_scale;
    let seal_lo = 0.03 * area_scale;
    let seal_hi = 0.4 * area_scale;
    let lip_open = 7.0 * area_scale;
    const GAIN: f64 = 40.0;

    if target > old {
        let rate = if lip {
            let u = ((old - seal_lo) / seal_lo).clamp(0.0, 1.0);
            lip_open + (open - lip_open) * (u * u * (3.0 - 2.0 * u))
        } else {
            open
        };
        target.min(old + (rate + GAIN * target) * dt)
    } else {
        let rate = if old < seal_lo {
            seal * (old / seal_lo).sqrt()
        } else {
            let u = ((old - seal_lo) / (seal_hi - seal_lo)).clamp(0.0, 1.0);
            seal + (open - seal) * u * u * (3.0 - 2.0 * u)
        };
        target.max(old - (rate + GAIN * old) * dt)
    }
}

#[cfg(test)]
mod allocation_tests;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejected_resampling_preserves_the_committed_area_samples_and_reuses_both_buffers() {
        let extended_lips = Articulation {
            lip_protrusion_cm: 1.6,
            ..Articulation::neutral()
        };
        let retracted_lips = Articulation {
            lip_protrusion_cm: -0.2,
            ..extended_lips
        };
        let sample_rate_hz = 96_000;
        let model = SagittalModel::adult_male();
        let oral_length = |posture| {
            let profile = model.area_profile(&model.compute(posture)).unwrap();
            profile.length_cm - profile.pharynx_length_cm
        };
        let stable_cell_length_cm = SOUND_SPEED / f64::from(sample_rate_hz) / 0.97;
        let count = (oral_length(extended_lips) / stable_cell_length_cm).floor() as usize;
        assert!(count >= 8);
        assert!(oral_length(retracted_lips) < count as f64 * stable_cell_length_cm);
        let mut control = HumanTractControl::with_oral_cells(
            sample_rate_hz,
            BodyName::Male.into(),
            extended_lips,
            NonZeroUsize::new(count),
        )
        .unwrap();
        let bits = |samples: &[AreaSample]| {
            samples
                .iter()
                .map(|sample| sample.measurement_values().map(f64::to_bits))
                .collect::<Vec<_>>()
        };
        let expected = bits(control.area_samples());
        let committed = control.area_samples().as_ptr();
        let scratch = control.area_scratch.as_ptr();
        let dt = 1.0 / 750.0;
        let cfl_error = "指定した口腔セル数では解剖上の管長でクーラン数が0.97を超えます";

        assert_eq!(control.apply(retracted_lips, dt).err(), Some(cfl_error));
        assert_eq!(bits(control.area_samples()), expected);
        assert_eq!(control.area_samples().as_ptr(), committed);
        assert_eq!(control.area_scratch.as_ptr(), scratch);
        assert_ne!(bits(&control.area_scratch), expected);

        control.apply(extended_lips, dt).unwrap();
        assert_eq!(bits(control.area_samples()), expected);
        assert_eq!(control.area_samples().as_ptr(), scratch);
        assert_eq!(control.area_scratch.as_ptr(), committed);

        assert_eq!(control.reapply(retracted_lips).err(), Some(cfl_error));
        assert_eq!(bits(control.area_samples()), expected);
        assert_eq!(control.area_samples().as_ptr(), scratch);
        assert_eq!(control.area_scratch.as_ptr(), committed);

        control.reapply(extended_lips).unwrap();
        assert_eq!(bits(control.area_samples()), expected);
        assert_eq!(control.area_samples().as_ptr(), committed);
        assert_eq!(control.area_scratch.as_ptr(), scratch);
    }
}
