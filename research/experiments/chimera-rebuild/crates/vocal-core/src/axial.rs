//! 無限剛体バッフルに取り付けた一様円盤の軸上音圧。入出力はSI。

use std::f64::consts::PI;

const TAP_COUNT: usize = 8;
const EARLIER_TAPS: usize = 3;
const PROCESSING_DELAY: f64 = 5.0;

struct FractionalDelay {
    first_lag: usize,
    weights: [f64; TAP_COUNT],
}

impl FractionalDelay {
    fn new(delay: f64) -> Self {
        let first_lag = delay.floor() as usize - EARLIER_TAPS;
        let position = delay - first_lag as f64;
        let weights = std::array::from_fn(|i| {
            (0..TAP_COUNT)
                .filter(|&j| j != i)
                .map(|j| (position - j as f64) / (i as f64 - j as f64))
                .product()
        });
        Self { first_lag, weights }
    }

    fn value(&self, history: &[f64], cursor: usize) -> f64 {
        let mut index = (cursor + history.len() - self.first_lag) % history.len();
        let anchor = history[index];
        let mut delta = 0.0;
        for weight in self.weights {
            // 定常流量では補間係数の丸めにかかわらず同じ値を返す。
            delta += weight * (history[index] - anchor);
            index = (index + history.len() - 1) % history.len();
        }
        anchor + delta
    }
}

pub struct AxialSample {
    pub disk_pressure_pa: f64,
    pub far_backward_pressure_pa: f64,
    pub far_centered_pressure_pa: f64,
}

pub struct AxialObserver {
    history: Vec<f64>,
    cursor: usize,
    center: FractionalDelay,
    edge: FractionalDelay,
    half_step_advance: FractionalDelay,
    previous_center: f64,
    previous_half_step: f64,
    disk_scale: f64,
    far_scale: f64,
}

impl AxialObserver {
    pub fn new(
        sample_rate_hz: u32,
        area_m2: f64,
        distance_m: f64,
        density_kg_m3: f64,
        speed_m_s: f64,
    ) -> Result<Self, &'static str> {
        let rate = f64::from(sample_rate_hz);
        if ![rate, area_m2, distance_m, density_kg_m3, speed_m_s]
            .into_iter()
            .all(|value| value.is_finite() && value > 0.0)
        {
            return Err("観測のレート、面積、距離、密度、音速は有限の正値が必要です");
        }
        let radius = (area_m2 / PI).sqrt();
        let center = rate * (distance_m / speed_m_s) + PROCESSING_DELAY;
        let path_difference_m = (area_m2 / PI) / (radius.hypot(distance_m) + distance_m);
        let edge = center + rate * (path_difference_m / speed_m_s);
        let disk_scale = density_kg_m3 * speed_m_s / area_m2;
        let far_scale = density_kg_m3 / (2.0 * PI * distance_m) * rate;
        if !(center < edge
            && edge <= 1_000_000.0
            && disk_scale.is_finite()
            && far_scale.is_finite())
        {
            return Err("観測の遅延と換算係数を有限の範囲で計算できません");
        }
        let edge = FractionalDelay::new(edge);
        Ok(Self {
            history: vec![0.0; edge.first_lag + TAP_COUNT],
            cursor: 0,
            center: FractionalDelay::new(center),
            edge,
            half_step_advance: FractionalDelay::new(center - 0.5),
            previous_center: 0.0,
            previous_half_step: 0.0,
            disk_scale,
            far_scale,
        })
    }

    /// 有限長の入力後、遅延線と後退差分が無音に戻ることを確認できる長さ。
    pub fn tail_samples(&self) -> usize {
        // 遅延線の最大ラグを使った後退差分が0に戻る最初の点も含める。
        self.history.len() + 1
    }

    /// 口端の体積流量 m³/s を1サンプル入力し、三つの軸上音圧を Pa で返す。
    pub fn step(&mut self, flow_m3_s: f64) -> AxialSample {
        self.history[self.cursor] = flow_m3_s;
        let center = self.center.value(&self.history, self.cursor);
        let edge = self.edge.value(&self.history, self.cursor);
        let half_step = self.half_step_advance.value(&self.history, self.cursor);
        let sample = AxialSample {
            disk_pressure_pa: self.disk_scale * (center - edge),
            far_backward_pressure_pa: self.far_scale * (center - self.previous_center),
            far_centered_pressure_pa: self.far_scale * (half_step - self.previous_half_step),
        };
        self.previous_center = center;
        self.previous_half_step = half_step;
        self.cursor = (self.cursor + 1) % self.history.len();
        sample
    }
}
