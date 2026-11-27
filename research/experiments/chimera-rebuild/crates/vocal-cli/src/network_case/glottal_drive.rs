//! 研究ケースの声門設定と、枝を解く前の圧力・面積の更新。

use serde::Deserialize;
use vocal_core::airway::network::AirwayNetwork;
use vocal_core::glottis::{
    DEFAULT_CYCLE_SEED, DEFAULT_VIBRATO_RATE_HZ, Glottis, GlottisParameters,
};

pub(super) const TELEMETRY_HEADER: &str =
    "glottal_area_cm2,glottal_pressure_drop_dyn_cm2,glottal_voicing,glottal_phase";

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct GlottisInput {
    pub(super) port: [usize; 2],
    params: ParametersInput,
    abduction_steps: Vec<(usize, f64)>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ParametersInput {
    f0_hz: f64,
    amplitude_cm2: f64,
    chink_cm2: f64,
    open_quotient: f64,
    open_with_abduction: f64,
    skew: f64,
    closure_sharpness: f64,
    effort: f64,
    closure: f64,
    threshold_dyn_cm2: f64,
    #[serde(default)]
    jitter: f64,
    #[serde(default)]
    shimmer: f64,
    #[serde(default = "default_cycle_seed")]
    cycle_seed: u32,
    #[serde(default)]
    drift_cents: f64,
    #[serde(default)]
    vibrato_depth_cents: f64,
    #[serde(default = "default_vibrato_rate")]
    vibrato_rate_hz: f64,
    #[serde(default)]
    fry: f64,
    #[serde(default)]
    diplophonia: f64,
    #[serde(default)]
    chaos: f64,
}

fn default_cycle_seed() -> u32 {
    DEFAULT_CYCLE_SEED
}

fn default_vibrato_rate() -> f64 {
    DEFAULT_VIBRATO_RATE_HZ
}

pub(super) struct GlottalDrive {
    port: [usize; 2],
    branch: usize,
    glottis: Glottis,
    abduction_steps: Vec<(usize, f64)>,
    control_index: usize,
}

impl GlottalDrive {
    pub(super) fn new(
        input: GlottisInput,
        branch: usize,
        rate_hz: u32,
    ) -> Result<Self, &'static str> {
        let steps = input.abduction_steps;
        if steps.first().map(|step| step.0) != Some(0)
            || steps.windows(2).any(|pair| pair[0].0 >= pair[1].0)
            || steps
                .iter()
                .any(|&(_, area)| !area.is_finite() || area < 0.0)
        {
            return Err("声帯の開大面積はサンプル0から時刻順に、有限の非負値を指定してください");
        }
        let p = input.params;
        let glottis = Glottis::new(
            rate_hz,
            GlottisParameters {
                f0_hz: p.f0_hz,
                amplitude_cm2: p.amplitude_cm2,
                chink_cm2: p.chink_cm2,
                open_quotient: p.open_quotient,
                open_with_abduction: p.open_with_abduction,
                skew: p.skew,
                closure_sharpness: p.closure_sharpness,
                effort: p.effort,
                closure: p.closure,
                threshold_dyn_cm2: p.threshold_dyn_cm2,
                jitter: p.jitter,
                shimmer: p.shimmer,
                cycle_seed: p.cycle_seed,
                drift_cents: p.drift_cents,
                vibrato_depth_cents: p.vibrato_depth_cents,
                vibrato_rate_hz: p.vibrato_rate_hz,
                fry: p.fry,
                diplophonia: p.diplophonia,
                chaos: p.chaos,
            },
        )?;
        Ok(Self {
            port: input.port,
            branch,
            glottis,
            abduction_steps: steps,
            control_index: 0,
        })
    }

    pub(super) fn step(
        &mut self,
        sample: usize,
        airway: &mut AirwayNetwork,
        breath_effort: Option<f64>,
    ) -> Result<[f64; 5], &'static str> {
        if let Some(effort) = breath_effort {
            self.glottis.set_effort(effort)?;
        }
        if self
            .abduction_steps
            .get(self.control_index + 1)
            .is_some_and(|step| step.0 == sample)
        {
            self.control_index += 1;
        }
        let [below, above] = self.port;
        let pressure_drop = airway.pressure(below) - airway.pressure(above);
        let state = self
            .glottis
            .step(pressure_drop, self.abduction_steps[self.control_index].1);
        airway.set_port_area(self.branch, state.area_cm2)?;
        Ok([
            state.area_cm2,
            pressure_drop,
            state.voicing,
            state.phase,
            state.f0_hz,
        ])
    }
}
