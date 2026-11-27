//! 体型別の断面目標から乱流源を選ぶ。係数は固定版CHIMERA（MIT）。

use super::HumanAirway;
use crate::airway::{PI, network::NoiseSpec, tract_control::TractTargets};

pub(super) const MAX_TURBULENCE_SOURCES: usize = 3;

/// 調音で配置する乱流源の設定。既定値は固定版の音響処理に対応する。
#[derive(Clone, Copy, Debug)]
pub struct TurbulenceSettings {
    pub scale: f64,
    pub glottis_gain_multiplier: f64,
    pub constriction_gain_multiplier: f64,
    /// 歯の乱流フィルタの低域通過周波数の下限（Hz）。0なら噴流の値を使う。
    pub teeth_lowpass_floor_hz: f64,
}

impl Default for TurbulenceSettings {
    fn default() -> Self {
        Self {
            scale: 1.0,
            glottis_gain_multiplier: 1.0,
            constriction_gain_multiplier: 1.0,
            teeth_lowpass_floor_hz: 0.0,
        }
    }
}

#[derive(Clone, Copy, Debug, Default)]
pub struct FricationGeometry {
    /// 咽頭と口腔をつないだセル列での位置。
    pub narrowest_cell: Option<usize>,
    pub minimum_area_cm2: f64,
    pub teeth_distance_cm: f64,
    /// 制御更新直前の励起枝の面積と流量。
    pub jet_area_cm2: f64,
    pub jet_flow_cm3_s: f64,
}

impl HumanAirway {
    pub(crate) fn register_turbulence(
        &mut self,
        targets: &TractTargets,
        settings: TurbulenceSettings,
    ) -> Result<(), &'static str> {
        #[cfg(all(not(target_arch = "wasm32"), feature = "render-allocation-probe"))]
        let _allocation = super::allocation_scope(super::AllocationPhase::Turbulence);
        let [trachea, pharynx, oral, ..] = &self.tubes;
        let ph = &targets.limited.pharynx;
        let mouth = &targets.limited.oral;
        let n_ph = ph.cells.len();
        let last = n_ph + mouth.cells.len() - 2;
        let ph_dx = ph.length_cm / n_ph as f64;
        let or_dx = mouth.length_cm / mouth.cells.len() as f64;
        let scale = self.body.scale;
        let area_scale = scale * scale;
        let branch = |cell: usize| {
            if cell < n_ph {
                Some(pharynx.branches.start + cell.min(pharynx.branches.len() - 1))
            } else if cell == n_ph {
                None
            } else {
                Some(oral.branches.start + (cell - n_ph).min(oral.branches.len() - 1))
            }
        };

        let glottis = NoiseSpec {
            source: self.glottis_port,
            forward: pharynx.branches.start + 1,
            reverse: trachea.branches.end - 1,
            gain: 3.2e-6 * settings.glottis_gain_multiplier,
            lowpass_hz: 3500.0,
            highpass_hz: 300.0,
        };
        let mut sources = [glottis; MAX_TURBULENCE_SOURCES];
        let mut len = 1;
        let mut geometry = FricationGeometry::default();
        let narrow = ph
            .cells
            .iter()
            .chain(&mouth.cells)
            .enumerate()
            .map(|(index, cell)| (index, cell.minimum_area_cm2))
            .filter(|(_, area)| *area > 0.0)
            .min_by(|a, b| a.1.total_cmp(&b.1));
        if let Some((cell, area)) = narrow {
            let dx = if cell < n_ph { ph_dx } else { or_dx };
            let position = if cell < n_ph {
                (cell as f64 + 0.5) * ph_dx
            } else {
                ph.length_cm + ((cell - n_ph) as f64 + 0.5) * or_dx
            };
            let behind = targets.teeth_s_cm - position;
            geometry.narrowest_cell = Some(cell);
            geometry.minimum_area_cm2 = area;
            geometry.teeth_distance_cm = behind;
            let offset = (0.9 * scale / dx).round().max(1.0) as usize;
            let weight = 1.0 - smooth(0.35 * area_scale, 0.9 * area_scale, area);
            if weight > 0.0
                && let (Some(source), Some(forward), Some(reverse)) = (
                    branch(cell.min(last)),
                    branch(cell.saturating_add(offset).min(last)),
                    branch(cell.saturating_sub(offset)),
                )
            {
                sources[len] = NoiseSpec {
                    source,
                    forward,
                    reverse,
                    gain: (1.364e-6 * settings.constriction_gain_multiplier) * weight,
                    lowpass_hz: 2600.0,
                    highpass_hz: 350.0,
                };
                len += 1;
                geometry.jet_area_cm2 = self.network.branch_area(source);
                geometry.jet_flow_cm3_s = self.network.branch_flow(source);
                let reference_distance = behind / scale;
                let distance_weight = smooth(1.0, 1.5, reference_distance)
                    * (1.0 - smooth(2.6, 4.0, reference_distance));
                let teeth_weight =
                    distance_weight * (1.0 - smooth(0.2 * area_scale, 0.5 * area_scale, area));
                let teeth_cell = ((targets.teeth_s_cm - ph.length_cm) / or_dx)
                    .round()
                    .clamp(0.0, (mouth.cells.len() - 2) as f64)
                    as usize;
                if teeth_weight > 1e-3
                    && let Some(teeth_branch) = branch(n_ph + teeth_cell)
                {
                    let jet_area = geometry.jet_area_cm2.max(1e-6);
                    let velocity = geometry.jet_flow_cm3_s.abs() / jet_area;
                    let diameter = 2.0 * (jet_area / PI).sqrt();
                    let eddy = diameter.max(0.17 * behind);
                    let top = velocity * diameter / (eddy * eddy);
                    let spread = (5000.0 / top.max(1200.0)).sqrt();
                    sources[len] = NoiseSpec {
                        source,
                        forward: teeth_branch,
                        reverse,
                        gain: 3.0e-6 * teeth_weight * spread,
                        // 励起ゲインには噴流の周波数を使い、下限はフィルタにだけ適用する。
                        lowpass_hz: top.max(settings.teeth_lowpass_floor_hz),
                        highpass_hz: 1200.0,
                    };
                    len += 1;
                }
            }
        }

        self.network.set_noise_sources(&sources[..len])?;
        self.frication_geometry = geometry;
        Ok(())
    }
}

fn smooth(lower: f64, upper: f64, value: f64) -> f64 {
    let t = ((value - lower) / (upper - lower)).clamp(0.0, 1.0);
    t * t * (3.0 - 2.0 * t)
}
