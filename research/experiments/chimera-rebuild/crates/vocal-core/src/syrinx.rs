//! 片側の鳴管振動子。気道に渡す値は正規化した開口率。
//! 周期表の出典は `notes/songbird-syrinx.md`、ライセンスは `LICENSE-CHIMERA`。

use serde::{Deserialize, Serialize};
use std::sync::OnceLock;

#[derive(Deserialize)]
struct PeriodTable {
    alphas: Vec<f64>,
    betas: Vec<f64>,
    #[serde(rename = "T")]
    periods: Vec<Vec<Option<f64>>>,
    lo: Vec<Vec<Option<f64>>>,
    hi: Vec<Vec<Option<f64>>>,
}

impl PeriodTable {
    fn get() -> &'static Self {
        static TABLE: OnceLock<PeriodTable> = OnceLock::new();
        TABLE.get_or_init(|| {
            let mut table: Self = serde_json::from_str(include_str!("syrinx-table.generated.json"))
                .expect("同梱の鳴管周期表を読み込めません");
            for row in 0..table.betas.len() {
                for col in (0..table.alphas.len()).rev() {
                    if table.periods[row][col].is_none() {
                        table.periods[row][col] = Some(
                            table.periods[row]
                                .get(col + 1)
                                .copied()
                                .flatten()
                                .or_else(|| table.periods.get(row + 1).and_then(|next| next[col]))
                                .unwrap_or(10.0),
                        );
                        table.lo[row][col] = Some(
                            table.lo[row]
                                .get(col + 1)
                                .copied()
                                .flatten()
                                .unwrap_or(-1.0),
                        );
                        table.hi[row][col] =
                            Some(table.hi[row].get(col + 1).copied().flatten().unwrap_or(1.0));
                    }
                }
            }
            table
        })
    }

    fn interpolate(&self, alpha: f64, beta: f64) -> [f64; 3] {
        let coordinate = |axis: &[f64], value: f64| {
            let end = axis.len() - 1;
            let index = ((value - axis[0]) / (axis[end] - axis[0]) * end as f64)
                .clamp(0.0, axis.len() as f64 - 1.0001);
            (index as usize, index.fract())
        };
        let (col, u) = coordinate(&self.alphas, alpha);
        let (row, w) = coordinate(&self.betas, beta);
        let along_alpha = |values: &[Option<f64>]| {
            (1.0 - u) * values[col].unwrap_or(0.0) + u * values[col + 1].unwrap_or(0.0)
        };
        [&self.periods, &self.lo, &self.hi]
            .map(|grid| (1.0 - w) * along_alpha(&grid[row]) + w * along_alpha(&grid[row + 1]))
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SyrinxControls {
    pub drive: f64,
    pub tension: f64,
    pub f0_hz: f64,
    pub gate: f64,
}

#[derive(Clone, Copy, Debug, Serialize)]
pub struct SyrinxTuning {
    pub alpha: f64,
    pub beta: f64,
    pub period_tau: f64,
    pub displacement_low: f64,
    pub displacement_high: f64,
    pub substeps: usize,
    pub step_tau: f64,
}

impl SyrinxTuning {
    fn for_controls(rate_hz: u32, controls: SyrinxControls) -> Result<Self, &'static str> {
        if rate_hz == 0
            || !controls.drive.is_finite()
            || !controls.tension.is_finite()
            || !(0.0..=f64::from(rate_hz)).contains(&controls.f0_hz)
            || !(0.0..=1.0).contains(&controls.gate)
        {
            return Err(
                "鳴管には正の内部レート、有限の駆動と張力、内部レート以下の非負音高、0〜1のゲートが必要です",
            );
        }
        let alpha = 0.09 + (0.6 - 0.09) * controls.drive.clamp(0.0, 1.0);
        let beta = 0.2 + (1.3 - 0.2) * controls.tension.clamp(0.0, 1.0);
        let [period_tau, displacement_low, displacement_high] =
            PeriodTable::get().interpolate(alpha, beta);
        let tau_per_sample = (period_tau * controls.f0_hz) / f64::from(rate_hz);
        let substeps = (tau_per_sample / 0.06).ceil().max(1.0) as usize;
        Ok(Self {
            alpha,
            beta,
            period_tau,
            displacement_low,
            displacement_high,
            substeps,
            step_tau: tau_per_sample / substeps as f64,
        })
    }
}

#[derive(Clone, Copy, Debug, Serialize)]
pub struct SyrinxSample {
    pub displacement: f64,
    pub velocity_tau: f64,
    pub gate_smoothed: f64,
    pub opening: f64,
}

pub struct SyrinxLabia {
    rate_hz: u32,
    tuning: SyrinxTuning,
    gate: f64,
    gate_smoothed: f64,
    displacement: f64,
    velocity: f64,
}

impl SyrinxLabia {
    pub fn new(rate_hz: u32, seed: f64, controls: SyrinxControls) -> Result<Self, &'static str> {
        if !seed.is_finite() {
            return Err("鳴管の初期変位に使う種には有限値が必要です");
        }
        Ok(Self {
            rate_hz,
            tuning: SyrinxTuning::for_controls(rate_hz, controls)?,
            gate: controls.gate,
            gate_smoothed: 0.0,
            displacement: 0.2 + 0.05 * seed,
            velocity: 0.0,
        })
    }

    pub fn tuning(&self) -> SyrinxTuning {
        self.tuning
    }

    /// 制御を変えても時系列の状態とゲートの履歴を保つ。
    pub fn set_controls(&mut self, controls: SyrinxControls) -> Result<(), &'static str> {
        self.tuning = SyrinxTuning::for_controls(self.rate_hz, controls)?;
        self.gate = controls.gate;
        Ok(())
    }

    /// 積分後の変位を開口率に写す。ゲートは変位の更新に入らない。
    pub fn step(&mut self) -> SyrinxSample {
        let SyrinxTuning {
            alpha,
            beta,
            displacement_low,
            displacement_high,
            substeps,
            step_tau,
            ..
        } = self.tuning;
        let mut x = self.displacement;
        let mut y = self.velocity;
        let rhs = |x, y| (y, -alpha - beta * x - x * x * x - x * x * y + x * x - x * y);
        let h = step_tau;
        for _ in 0..substeps {
            let (dx1, dy1) = rhs(x, y);
            let (dx2, dy2) = rhs(x + 0.5 * h * dx1, y + 0.5 * h * dy1);
            let (dx3, dy3) = rhs(x + 0.5 * h * dx2, y + 0.5 * h * dy2);
            let (dx4, dy4) = rhs(x + h * dx3, y + h * dy3);
            x += (h / 6.0) * (dx1 + 2.0 * dx2 + 2.0 * dx3 + dx4);
            y += (h / 6.0) * (dy1 + 2.0 * dy2 + 2.0 * dy3 + dy4);
        }
        if !x.is_finite() || x.abs() > 10.0 {
            x = 0.2;
            y = 0.0;
        }
        self.displacement = x;
        self.velocity = y;
        let scaled = ((x - displacement_low) / (displacement_high - displacement_low).max(0.001))
            .clamp(0.0, 1.0);
        self.gate_smoothed += 0.002 * (self.gate - self.gate_smoothed);
        SyrinxSample {
            displacement: x,
            velocity_tau: y,
            gate_smoothed: self.gate_smoothed,
            opening: scaled * scaled * self.gate_smoothed,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::PeriodTable;

    #[test]
    fn missing_corner_inherits_period_and_extrema_from_the_same_row() {
        let table = PeriodTable::get();
        assert_eq!(
            table.interpolate(table.alphas[0], table.betas[0]),
            table.interpolate(table.alphas[1], table.betas[0]),
        );
    }
}
