//! 圧力差で駆動する声門面積モデル。物理量はCGS。

use crate::random::Mulberry32;
use std::f64::consts::{PI, TAU};

pub const DEFAULT_CYCLE_SEED: u32 = 777;
pub const DEFAULT_VIBRATO_RATE_HZ: f64 = 6.0;
const PITCH_INTERVAL: u8 = 32;

#[derive(Clone, Copy, Debug)]
pub struct GlottisParameters {
    pub f0_hz: f64,
    pub amplitude_cm2: f64,
    pub chink_cm2: f64,
    pub open_quotient: f64,
    pub open_with_abduction: f64,
    pub skew: f64,
    pub closure_sharpness: f64,
    pub effort: f64,
    pub closure: f64,
    pub threshold_dyn_cm2: f64,
    pub jitter: f64,
    pub shimmer: f64,
    pub cycle_seed: u32,
    pub drift_cents: f64,
    pub vibrato_depth_cents: f64,
    pub vibrato_rate_hz: f64,
    pub fry: f64,
    pub diplophonia: f64,
    pub chaos: f64,
}

#[derive(Clone, Copy, Debug)]
pub struct GlottisSample {
    pub area_cm2: f64,
    pub voicing: f64,
    pub phase: f64,
    pub f0_hz: f64,
    pub filtered_pressure_drop_dyn_cm2: f64,
    /// スコアから渡された平滑化前の閉鎖指示（無次元）。
    pub closure_command: f64,
    /// 現在の周期の振動面積に掛ける無次元の倍率。
    pub cycle_amplitude_scale: f64,
}

pub struct Glottis {
    parameters: GlottisParameters,
    sample_rate_hz: f64,
    pitch: PitchModulation,
    phase: f64,
    odd_cycle: bool,
    chaos_state: f64,
    cycle_period_scale: f64,
    cycle_amplitude_scale: f64,
    cycle_random: Mulberry32,
    pressure: f64,
    voicing: f64,
    gap_cm2: f64,
    closure: f64,
    amplitude_cm2: f64,
    pressure_coefficient: f64,
    voicing_coefficient: f64,
    control_coefficient: f64,
}

impl Glottis {
    pub fn new(rate_hz: u32, parameters: GlottisParameters) -> Result<Self, &'static str> {
        let rate = f64::from(rate_hz);
        let p = parameters;
        if !(p.f0_hz > 0.0 && p.f0_hz < rate * 0.5)
            || [
                p.amplitude_cm2,
                p.chink_cm2,
                p.open_with_abduction,
                p.jitter,
                p.shimmer,
                p.drift_cents,
                p.vibrato_depth_cents,
                p.vibrato_rate_hz,
            ]
            .into_iter()
            .any(|value| !value.is_finite() || value < 0.0)
            || [
                p.open_quotient,
                p.skew,
                p.closure_sharpness,
                p.effort,
                p.closure,
                p.fry,
                p.diplophonia,
                p.chaos,
            ]
            .into_iter()
            .any(|value| !(0.0..=1.0).contains(&value))
            || !p.threshold_dyn_cm2.is_finite()
            || p.threshold_dyn_cm2 <= 0.0
        {
            return Err("声門の周波数、断面、しきい値と各制御値の範囲を確認してください");
        }
        Ok(Self {
            parameters,
            sample_rate_hz: rate,
            pitch: PitchModulation::new(rate),
            phase: 0.0,
            odd_cycle: false,
            chaos_state: 0.37,
            cycle_period_scale: 1.0,
            cycle_amplitude_scale: 1.0,
            cycle_random: Mulberry32::new(p.cycle_seed),
            pressure: 0.0,
            voicing: 0.0,
            gap_cm2: 0.0,
            closure: 0.0,
            amplitude_cm2: 0.0,
            pressure_coefficient: 1.0 - libm::exp(-TAU * 30.0 / rate),
            voicing_coefficient: 1.0 - libm::exp(-TAU * 25.0 / rate),
            control_coefficient: 1.0 - libm::exp(-1.0 / (0.004 * rate)),
        })
    }

    pub fn set_effort(&mut self, effort: f64) -> Result<(), &'static str> {
        if !(0.0..=1.0).contains(&effort) {
            return Err("声門の強さは0から1までの値で指定してください");
        }
        self.parameters.effort = effort;
        Ok(())
    }

    pub(crate) fn valid_pitch(&self, f0_hz: f64) -> bool {
        f0_hz > 0.0 && f0_hz < self.sample_rate_hz * 0.5
    }

    pub(crate) fn set_pitch(&mut self, f0_hz: f64) -> Result<(), &'static str> {
        if !self.valid_pitch(f0_hz) {
            return Err("声門の基本周波数が範囲外です");
        }
        self.parameters.f0_hz = f0_hz;
        Ok(())
    }

    pub(crate) fn set_pitch_drift_cents(&mut self, cents: f64) -> Result<(), &'static str> {
        if !cents.is_finite() || cents < 0.0 {
            return Err("ピッチドリフトは0以上の有限なセント値で指定してください");
        }
        self.parameters.drift_cents = cents;
        Ok(())
    }

    pub(crate) fn set_period_jitter(&mut self, amount: f64) -> Result<(), &'static str> {
        if !amount.is_finite() || amount < 0.0 {
            return Err("周期ジッターは0以上の有限な係数で指定してください");
        }
        self.parameters.jitter = amount;
        Ok(())
    }

    pub(crate) fn set_amplitude_shimmer(&mut self, amount: f64) -> Result<(), &'static str> {
        if !amount.is_finite() || amount < 0.0 {
            return Err("振幅シマーは0以上の有限な係数で指定してください");
        }
        self.parameters.shimmer = amount;
        Ok(())
    }

    pub(crate) fn set_chaos(&mut self, amount: f64) {
        self.parameters.chaos = amount;
    }

    pub(crate) fn set_dynamic_source(
        &mut self,
        pitch_hz: f64,
        amplitude_cm2: f64,
        [chaos, jitter, shimmer]: [f64; 3],
    ) -> Result<(), &'static str> {
        self.set_pitch(pitch_hz)?;
        self.parameters.amplitude_cm2 = amplitude_cm2;
        self.parameters.chaos = chaos;
        self.parameters.jitter = jitter;
        self.parameters.shimmer = shimmer;
        Ok(())
    }

    pub(crate) fn use_beatbox_variation(&mut self) {
        // 上流の既定音源は粗さ0.1、ドリフト5セントで動作する。
        let roughness = 0.1;
        self.parameters.jitter = 0.0021 + 0.0245 * roughness;
        self.parameters.shimmer = 0.02 + 0.22 * roughness;
        self.parameters.drift_cents = 5.0;
    }

    pub(crate) fn trim_tail(&mut self) {
        for state in [
            &mut self.pressure,
            &mut self.voicing,
            &mut self.amplitude_cm2,
            &mut self.closure,
            &mut self.gap_cm2,
        ] {
            crate::airway::trim_tiny(state);
        }
    }

    pub(crate) fn set_score_controls(
        &mut self,
        f0_hz: f64,
        closure: f64,
        vibrato: f64,
    ) -> Result<(), &'static str> {
        let valid_f0 = self.valid_pitch(f0_hz);
        let valid_vibrato = vibrato.is_finite() && vibrato >= 0.0;
        if !(valid_f0 && (0.0..=1.0).contains(&closure) && valid_vibrato) {
            return Err("スコアによる声門のF0・閉鎖・ビブラートが範囲外です");
        }
        self.parameters.f0_hz = f0_hz;
        self.parameters.closure = closure;
        self.parameters.vibrato_depth_cents = vibrato;
        Ok(())
    }

    /// 有限の前ステップの圧力差と非負の開大面積から、このサンプルの面積を求める。
    pub fn step(&mut self, pressure_drop_dyn_cm2: f64, abduction_cm2: f64) -> GlottisSample {
        let p = self.parameters;
        self.pressure += self.pressure_coefficient * (pressure_drop_dyn_cm2 - self.pressure);
        let mut f0_hz = p.f0_hz * self.pitch.step(p, self.sample_rate_hz);
        if p.fry > 0.0 {
            f0_hz = f0_hz * (1.0 - p.fry) + f0_hz.min(48.0) * p.fry;
        }
        let pressure_gate = smoothstep(
            0.8 * p.threshold_dyn_cm2,
            1.6 * p.threshold_dyn_cm2,
            self.pressure,
        );
        let contact_gate = 1.0 - smoothstep(0.08, 0.22, self.gap_cm2 - p.chink_cm2);
        let target_gate = pressure_gate * contact_gate * (1.0 - self.closure);
        self.voicing += self.voicing_coefficient * (target_gate - self.voicing);
        self.phase += (f0_hz / self.sample_rate_hz) / self.cycle_period_scale;
        if self.phase >= 1.0 {
            self.phase -= 1.0;
            self.odd_cycle = !self.odd_cycle;
            let period_change = 0.08 * p.diplophonia;
            let (period_offset, amplitude_drop) = if self.odd_cycle {
                (period_change, 0.35 * p.diplophonia)
            } else {
                (-period_change, 0.0)
            };
            let (chaos_period, chaos_amplitude) = if p.chaos > 0.0 {
                let rate = 2.9 + 1.1 * p.chaos;
                let state = self.chaos_state;
                self.chaos_state = rate * state * (1.0 - state);
                if !(self.chaos_state > 0.0 && self.chaos_state < 1.0) {
                    self.chaos_state = 0.37;
                }
                let deviation = self.chaos_state - 0.5;
                (0.45 * p.chaos * deviation, 1.1 * p.chaos * deviation)
            } else {
                (0.0, 0.0)
            };
            // 境界へ運ぶ増分には旧周期の倍率を使い、新周期の振幅はここで決める。
            // 係数がゼロでも上流と同じ順番で乱数列を進める。
            self.cycle_period_scale =
                (1.0 + p.jitter * self.cycle_random.gauss() + period_offset + chaos_period)
                    .clamp(0.55, 1.8);
            self.cycle_amplitude_scale =
                (1.0 + p.shimmer * self.cycle_random.gauss() - amplitude_drop + chaos_amplitude)
                    .max(0.12);
        }
        let base_open = (p.open_quotient - 0.18 * (p.effort - 0.5)).clamp(0.25, 0.98);
        let mut open =
            (base_open + p.open_with_abduction * (self.gap_cm2 - p.chink_cm2).max(0.0)).min(0.98);
        if p.fry > 0.0 {
            open = open * (1.0 - p.fry) + 0.28 * p.fry;
        }
        let skew = p.skew.clamp(0.3, 0.9);
        let mut pulse = pulse_shape(self.phase, open, skew, p.closure_sharpness);
        if p.fry > 0.3 && self.phase > 0.38 {
            let secondary_gain = 0.55 * smoothstep(0.3, 0.8, p.fry);
            pulse += secondary_gain
                * pulse_shape(self.phase - 0.38, open * 0.8, skew, p.closure_sharpness);
        }
        let coefficient = self.control_coefficient;
        self.amplitude_cm2 +=
            coefficient * (p.amplitude_cm2 * (0.45 + 0.75 * p.effort) - self.amplitude_cm2);
        self.closure += coefficient * (p.closure - self.closure);
        self.gap_cm2 += coefficient * (abduction_cm2 + p.chink_cm2 - self.gap_cm2);
        GlottisSample {
            area_cm2: (self.amplitude_cm2 * self.cycle_amplitude_scale * self.voicing * pulse
                + self.gap_cm2 * (1.0 - 0.92 * self.closure))
                .max(0.0),
            voicing: self.voicing,
            phase: self.phase,
            f0_hz,
            filtered_pressure_drop_dyn_cm2: self.pressure,
            closure_command: p.closure,
            cycle_amplitude_scale: self.cycle_amplitude_scale,
        }
    }
}

struct PitchModulation {
    drift_random: Mulberry32,
    drift_states: [f64; 3],
    drift_poles: [f64; 3],
    drift_input_gains: [f64; 3],
    vibrato_phase: f64,
    factor: f64,
    samples_until_update: u8,
}

impl PitchModulation {
    fn new(sample_rate_hz: f64) -> Self {
        let control_rate = sample_rate_hz / f64::from(PITCH_INTERVAL);
        let poles = [0.3, 0.3 * 3.0, 0.3 * 9.0].map(|hz| libm::exp(-TAU * hz / control_rate));
        Self {
            drift_random: Mulberry32::new(4242),
            drift_states: [0.0; 3],
            drift_poles: poles,
            drift_input_gains: poles.map(|pole| (1.0 - pole * pole).sqrt()),
            vibrato_phase: 0.0,
            factor: 1.0,
            samples_until_update: 0,
        }
    }

    fn step(&mut self, p: GlottisParameters, sample_rate_hz: f64) -> f64 {
        if self.samples_until_update == 0 {
            self.samples_until_update = PITCH_INTERVAL;
            let mut summed = 0.0;
            for (index, state) in self.drift_states.iter_mut().enumerate() {
                *state = self.drift_poles[index] * *state
                    + self.drift_input_gains[index] * self.drift_random.gauss();
                summed += *state / (index + 1) as f64;
            }
            let drift = summed / 1.4;
            // ドリフトの深さがゼロのときも、ドリフト値はビブラート速度に使う。
            self.vibrato_phase += ((p.vibrato_rate_hz * f64::from(PITCH_INTERVAL))
                / sample_rate_hz)
                * (1.0 + 0.04 * drift);
            if self.vibrato_phase > 1.0 {
                self.vibrato_phase -= 1.0;
            }
            let cents =
                p.vibrato_depth_cents * libm::sin(TAU * self.vibrato_phase) + p.drift_cents * drift;
            self.factor = libm::pow(2.0, cents / 1200.0);
        }
        self.samples_until_update -= 1;
        self.factor
    }
}

fn smoothstep(lower: f64, upper: f64, value: f64) -> f64 {
    let t = ((value - lower) / (upper - lower)).clamp(0.0, 1.0);
    t * t * (3.0 - 2.0 * t)
}

fn pulse_shape(phase: f64, open: f64, skew: f64, sharpness: f64) -> f64 {
    if phase >= open {
        return 0.0;
    }
    let time = phase / open;
    if time < skew {
        return 0.5 - 0.5 * libm::cos(PI * time / skew);
    }
    let closing = (time - skew) / (1.0 - skew);
    let soft = 0.5 + 0.5 * libm::cos(PI * closing);
    let hard = libm::cos(0.5 * PI * closing);
    soft + (hard - soft) * sharpness
}
