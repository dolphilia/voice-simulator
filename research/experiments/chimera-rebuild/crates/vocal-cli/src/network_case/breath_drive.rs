//! 呼気の操作値・スコア値を制御周期で読み、肺の境界圧に変換する。

use serde::Deserialize;
use vocal_core::airway::network::AirwayNetwork;
use vocal_core::breath::{Breath, BreathControl, BreathSample, BreathSettings};

pub(super) const BREATH_HEADER: &str = "breath_gate,breath_base_pressure_dyn_cm2,breath_filtered_flow_cm3_s,breath_boundary_pressure_dyn_cm2,breath_effort";

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct BreathInput {
    pub(super) port: [usize; 2],
    pressure_cm_h2o: f64,
    body_scale: f64,
    control_block_samples: usize,
    compensate: bool,
    steps: Vec<(usize, f64, f64, f64)>,
}

pub(super) struct BreathDrive {
    node: usize,
    branch: usize,
    block_samples: usize,
    steps: Vec<(usize, f64, f64, f64)>,
    cursor: usize,
    breath: Breath,
}

impl BreathDrive {
    pub(super) fn new(
        input: BreathInput,
        branch: usize,
        resistance: f64,
        rate_hz: u32,
    ) -> Result<Self, &'static str> {
        if input.steps.first().map(|step| step.0) != Some(0)
            || input.steps.windows(2).any(|pair| pair[0].0 >= pair[1].0)
            || input.steps.iter().any(|&(_, performer, score, activity)| {
                !(0.0..=1.5).contains(&performer)
                    || !(-1.5..=1.5).contains(&score)
                    || !(0.0..=1.0).contains(&activity)
            })
        {
            return Err(
                "呼気の指定はサンプル0から時刻順に並べ、操作、スコア、有効度の範囲を確認してください",
            );
        }
        let breath = Breath::new(
            rate_hz,
            BreathSettings {
                pressure_cm_h2o: input.pressure_cm_h2o,
                body_scale: input.body_scale,
                control_block_samples: input.control_block_samples,
                series_resistance_cgs: resistance,
                compensate: input.compensate,
            },
        )?;
        Ok(Self {
            node: input.port[0],
            branch,
            block_samples: input.control_block_samples,
            steps: input.steps,
            cursor: 0,
            breath,
        })
    }

    pub(super) fn node(&self) -> usize {
        self.node
    }

    pub(super) fn step(
        &mut self,
        sample: usize,
        airway: &mut AirwayNetwork,
    ) -> Result<BreathSample, &'static str> {
        if sample.is_multiple_of(self.block_samples) {
            while self
                .steps
                .get(self.cursor + 1)
                .is_some_and(|step| step.0 <= sample)
            {
                self.cursor += 1;
            }
            let (_, performer_gate, score_level, score_activity) = self.steps[self.cursor];
            self.breath.control(BreathControl {
                performer_gate,
                score_level,
                score_activity,
            });
        }
        let state = self.breath.step(airway.branch_flow(self.branch));
        airway.set_fixed_pressure(self.node, state.boundary_pressure_dyn_cm2)?;
        Ok(state)
    }
}
