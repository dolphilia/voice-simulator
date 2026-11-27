//! 内部レートの放射を、間引き・DC除去・リミッターを通してPCMへ変換する。

use std::f64::consts::{PI, TAU};

#[derive(Clone, Copy, Debug, Default)]
pub struct OutputFrame {
    pub decimated: f64,
    pub dc_removed: f64,
    pub envelope: f64,
    pub hold_frames: usize,
    pub pcm: f32,
}

pub struct OutputStage {
    decimator: Decimator,
    gain: f64,
    dc_pole: f64,
    previous_input: f64,
    previous_dc_removed: f64,
    envelope: f64,
    hold_frames: usize,
    hold_duration: usize,
    release: f64,
}

impl OutputStage {
    pub fn new(
        internal_rate_hz: u32,
        output_rate_hz: u32,
        gain: f64,
    ) -> Result<Self, &'static str> {
        if output_rate_hz == 0
            || internal_rate_hz < output_rate_hz
            || !internal_rate_hz.is_multiple_of(output_rate_hz)
            || !gain.is_finite()
            || gain < 0.0
        {
            return Err(
                "内部レートは出力レートの正の整数倍、ゲインは有限の非負値で指定してください",
            );
        }
        let rate = f64::from(output_rate_hz);
        Ok(Self {
            decimator: Decimator::new((internal_rate_hz / output_rate_hz) as usize)?,
            gain,
            dc_pole: libm::exp(-TAU * 25.0 / rate),
            previous_input: 0.0,
            previous_dc_removed: 0.0,
            envelope: 0.0,
            hold_frames: 0,
            hold_duration: (0.025 * rate).round() as usize,
            release: libm::exp(-1.0 / (0.2 * rate)),
        })
    }

    pub fn factor(&self) -> usize {
        self.decimator.factor
    }

    pub fn coefficients(&self) -> &[f64] {
        &self.decimator.coefficients
    }

    /// サンプル境界で出力段を静止状態へ戻す。
    pub fn reset(&mut self) {
        self.decimator.history.fill(0.0);
        self.decimator.write_at = 0;
        self.decimator.phase = 0;
        self.previous_input = 0.0;
        self.previous_dc_removed = 0.0;
        self.envelope = 0.0;
        self.hold_frames = 0;
    }

    /// 内部サンプルを進め、最終サンプルの観測値と同時刻のPCMを返す。
    pub fn render_frame<T>(
        &mut self,
        mut next: impl FnMut() -> Result<(f64, T), &'static str>,
    ) -> Result<(OutputFrame, T), &'static str> {
        loop {
            let (radiation, observation) = next()?;
            if !radiation.is_finite() {
                return Err("PCMへ渡す放射信号に非有限値があります");
            }
            if let Some(output) = self.push(radiation) {
                if ![
                    output.decimated,
                    output.dc_removed,
                    output.envelope,
                    f64::from(output.pcm),
                ]
                .into_iter()
                .all(f64::is_finite)
                {
                    return Err("PCM出力段に非有限値があります");
                }
                return Ok((output, observation));
            }
        }
    }

    /// 内部の放射を一サンプル受け取り、出力時刻にあたる場合だけ1フレームを返す。
    pub fn push(&mut self, radiation: f64) -> Option<OutputFrame> {
        let decimated = self.decimator.push(radiation)?;
        let input = decimated * self.gain;
        let highpassed = input - self.previous_input + self.dc_pole * self.previous_dc_removed;
        self.previous_input = input;
        self.previous_dc_removed = highpassed;

        let magnitude = highpassed.abs();
        if magnitude >= self.envelope {
            self.envelope = magnitude;
            self.hold_frames = self.hold_duration;
        } else if self.hold_frames > 0 {
            self.hold_frames -= 1;
        } else {
            self.envelope *= self.release;
        }

        let mut sample = highpassed;
        if self.envelope > 0.75 {
            sample *= 0.75 / self.envelope;
        }
        let magnitude = sample.abs();
        if magnitude > 0.85 {
            sample = sample.signum() * (0.85 + 0.15 * libm::tanh((magnitude - 0.85) / 0.15));
        }
        Some(OutputFrame {
            decimated,
            dc_removed: highpassed,
            envelope: self.envelope,
            hold_frames: self.hold_frames,
            pcm: sample as f32,
        })
    }
}

#[derive(Clone, Copy, Debug, Default)]
pub struct CreaturePcm {
    pub decimated: f64,
    pub dc_removed: f64,
    pub pcm: f32,
}

pub(crate) struct CreatureOutput {
    decimator: Decimator,
    gain: f64,
    dc_pole: f64,
    previous_input: f64,
    previous_filtered: f64,
}

impl CreatureOutput {
    pub(crate) fn new(rate: u32, factor: usize, gain: f64) -> Result<Self, &'static str> {
        if rate == 0 || !gain.is_finite() || gain < 0.0 {
            return Err("動物音声の出力レートとゲインを確認してください");
        }
        Ok(Self {
            decimator: Decimator::new(factor)?,
            gain,
            dc_pole: libm::exp(-TAU * 12.0 / f64::from(rate)),
            previous_input: 0.0,
            previous_filtered: 0.0,
        })
    }

    pub(crate) fn trim_tail(&mut self) {
        crate::airway::trim_tiny(&mut self.previous_input);
        crate::airway::trim_tiny(&mut self.previous_filtered);
    }

    pub(crate) fn push(&mut self, radiation: f64) -> Result<Option<CreaturePcm>, &'static str> {
        if !radiation.is_finite() {
            return Err("動物音声の放射に非有限値があります");
        }
        let Some(decimated) = self.decimator.push(radiation) else {
            return Ok(None);
        };
        let input = decimated * self.gain;
        let filtered = input - self.previous_input + self.dc_pole * self.previous_filtered;
        if !filtered.is_finite() {
            return Err("動物音声のDC除去後に非有限値があります");
        }
        self.previous_input = input;
        self.previous_filtered = filtered;
        let magnitude = filtered.abs();
        let bounded = if magnitude > 0.7 {
            filtered.signum() * (0.7 + 0.3 * libm::tanh((magnitude - 0.7) / 0.3))
        } else {
            filtered
        };
        Ok(Some(CreaturePcm {
            decimated,
            dc_removed: filtered,
            pcm: bounded as f32,
        }))
    }
}

pub(crate) struct Decimator {
    factor: usize,
    coefficients: Vec<f64>,
    history: Vec<f64>,
    write_at: usize,
    phase: usize,
}

impl Decimator {
    pub(crate) fn new(factor: usize) -> Result<Self, &'static str> {
        let length = if factor == 1 {
            1
        } else {
            factor
                .checked_mul(24)
                .and_then(|length| length.checked_add(1))
                .ok_or("間引きフィルタの長さが範囲を超えています")?
        };
        let capacity = length
            .checked_mul(2)
            .ok_or("間引きフィルタの履歴が範囲を超えています")?;
        let mut coefficients = allocate_zeros(length)?;
        if factor == 1 {
            coefficients[0] = 1.0;
        } else {
            lowpass(&mut coefficients, 0.46 / factor as f64);
        }
        Ok(Self {
            factor,
            coefficients,
            history: allocate_zeros(capacity)?,
            write_at: 0,
            phase: 0,
        })
    }

    pub(crate) fn push(&mut self, input: f64) -> Option<f64> {
        let length = self.coefficients.len();
        self.history[self.write_at] = input;
        self.history[self.write_at + length] = input;
        self.write_at += 1;
        if self.write_at == length {
            self.write_at = 0;
        }
        self.phase += 1;
        if self.phase < self.factor {
            return None;
        }
        self.phase = 0;
        let history = &self.history[self.write_at..self.write_at + length];
        Some(
            history
                .iter()
                .zip(self.coefficients.iter().rev())
                .map(|(x, h)| x * h)
                .sum(),
        )
    }
}

fn allocate_zeros(length: usize) -> Result<Vec<f64>, &'static str> {
    let mut values = Vec::new();
    values
        .try_reserve_exact(length)
        .map_err(|_| "間引きフィルタのメモリを確保できません")?;
    values.resize(length, 0.0);
    Ok(values)
}

fn lowpass(coefficients: &mut [f64], cutoff: f64) {
    let order = (coefficients.len() - 1) as f64;
    let window_beta = 8.5;
    let i0_edge = bessel_i0(window_beta);
    for (index, coefficient) in coefficients.iter_mut().enumerate() {
        let offset = index as f64 - order / 2.0;
        let sinc = if offset == 0.0 {
            2.0 * cutoff
        } else {
            libm::sin(TAU * cutoff * offset) / (PI * offset)
        };
        let position = 2.0 * index as f64 / order - 1.0;
        let window = bessel_i0(window_beta * (1.0 - position * position).max(0.0).sqrt()) / i0_edge;
        *coefficient = sinc * window;
    }
    let sum: f64 = coefficients.iter().sum();
    for coefficient in coefficients {
        *coefficient /= sum;
    }
}

fn bessel_i0(value: f64) -> f64 {
    let mut sum = 1.0;
    let mut term = 1.0;
    for k in 1..30 {
        let quotient = value / (2.0 * f64::from(k));
        term *= quotient * quotient;
        sum += term;
        if term < 1e-12 * sum {
            break;
        }
    }
    sum
}
