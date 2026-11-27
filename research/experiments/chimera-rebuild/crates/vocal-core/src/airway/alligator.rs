//! アメリカアリゲーターの制御と発声。出典は notes/alligator-{fixed-voice,bellow,growl}.md。
//! 上流のライセンスは LICENSE-CHIMERA。

use super::mammal::{MammalAirway, MammalGeometry, MammalSpec};
use super::trim_tiny;
use crate::breath::CM_H2O;
use crate::creature_midi;
use crate::glottis::{DEFAULT_CYCLE_SEED, DEFAULT_VIBRATO_RATE_HZ, Glottis, GlottisParameters};
use crate::output::{CreatureOutput, CreaturePcm};
use serde::{Deserialize, Serialize};

mod call;
pub use super::mammal::MammalAirwaySample as AlligatorAirwaySample;
pub use call::AlligatorCall;
use call::Playback;

pub const CONTROL_FRAMES: usize = 64;
const GAIN: f64 = 2.8e-7;
const PITCH_LIMITS: std::ops::RangeInclusive<f64> = 12.0..=120.0;

#[derive(Clone, Copy, Default, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AlligatorShape {
    pub pitch_hz: f64,
    pub chaos: f64,
    pub pressure_cm_h2o: f64,
    pub mouth: f64,
    pub nostrils: f64,
    pub hiss: f64,
}

impl AlligatorShape {
    fn validate(self) -> Result<(), &'static str> {
        if !PITCH_LIMITS.contains(&self.pitch_hz)
            || !(3.0..=40.0).contains(&self.pressure_cm_h2o)
            || [self.chaos, self.mouth, self.nostrils, self.hiss]
                .into_iter()
                .any(|value| !(0.0..=1.0).contains(&value))
        {
            return Err("アリゲーターの音高・呼気圧・形状の範囲を確認してください");
        }
        Ok(())
    }

    pub fn values(self) -> [f64; 6] {
        [
            self.pitch_hz,
            self.chaos,
            self.pressure_cm_h2o,
            self.mouth,
            self.nostrils,
            self.hiss,
        ]
    }

    fn period_variation(self) -> [f64; 3] {
        [
            self.chaos,
            0.01 + 0.05 * self.chaos,
            0.05 + 0.25 * self.chaos,
        ]
    }

    fn amplitude(self) -> f64 {
        0.9 * (1.0 - self.hiss)
    }

    fn mouth_area(self) -> f64 {
        0.05 + 12.0 * self.mouth
    }

    fn nasal_area(self) -> f64 {
        0.4 + 1.6 * self.nostrils
    }

    fn glottis(self, rate_hz: u32) -> Result<Glottis, &'static str> {
        self.validate()?;
        let [chaos, jitter, shimmer] = self.period_variation();
        Glottis::new(
            rate_hz,
            GlottisParameters {
                f0_hz: self.pitch_hz,
                amplitude_cm2: self.amplitude(),
                chink_cm2: 0.006,
                open_quotient: 0.5,
                open_with_abduction: 0.0,
                skew: 0.62,
                closure_sharpness: 0.8,
                effort: 1.0,
                closure: 0.0,
                threshold_dyn_cm2: 1.5 * CM_H2O,
                jitter,
                shimmer,
                cycle_seed: DEFAULT_CYCLE_SEED,
                drift_cents: 8.0,
                vibrato_depth_cents: 0.0,
                vibrato_rate_hz: DEFAULT_VIBRATO_RATE_HZ,
                fry: 0.0,
                diplophonia: 0.0,
                chaos,
            },
        )
    }
}

#[derive(Clone, Copy, Default, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct AlligatorParams {
    pub pitch_hz: Option<f64>,
    pub chaos: Option<f64>,
    pub pressure_cm_h2o: Option<f64>,
    pub mouth: Option<f64>,
    pub nostrils: Option<f64>,
    pub hiss: Option<f64>,
}

impl AlligatorParams {
    fn apply(self, previous: AlligatorShape) -> AlligatorShape {
        AlligatorShape {
            pitch_hz: self.pitch_hz.unwrap_or(previous.pitch_hz),
            chaos: self.chaos.unwrap_or(previous.chaos),
            pressure_cm_h2o: self.pressure_cm_h2o.unwrap_or(previous.pressure_cm_h2o),
            mouth: self.mouth.unwrap_or(previous.mouth),
            nostrils: self.nostrils.unwrap_or(previous.nostrils),
            hiss: self.hiss.unwrap_or(previous.hiss),
        }
    }
}

#[derive(Serialize)]
pub struct AlligatorGeometry {
    #[serde(flatten)]
    common: MammalGeometry,
    velum_area_cm2: f64,
    oral_noise_cell: Option<usize>,
}

#[derive(Clone, Copy, Default)]
pub struct AlligatorFrame {
    pub gate: f64,
    pub internal: [AlligatorAirwaySample; 2],
    pub output: CreaturePcm,
    pub control: AlligatorControlFrame,
}

#[derive(Clone, Copy, Default)]
pub struct AlligatorControlFrame {
    pub call_id: u8,
    pub clock_seconds: f64,
    pub gate_target: f64,
    pub current: AlligatorShape,
    pub target: AlligatorShape,
    pub oral_noise: bool,
}

pub struct AlligatorVoice {
    airway: MammalAirway,
    output: CreatureOutput,
    factor: usize,
    until_control: usize,
    manual_gate: f64,
    gate_target: f64,
    gate: f64,
    attack_coefficient: f64,
    release_coefficient: f64,
    clock_seconds: f64,
    control_seconds: f64,
    shape_coefficients: [f64; 3],
    performer: AlligatorShape,
    target: AlligatorShape,
    current: AlligatorShape,
    call: Option<Playback>,
    articulating: bool,
}

impl AlligatorVoice {
    pub fn new(rate_hz: u32, shape: AlligatorShape, level: f64) -> Result<Self, &'static str> {
        let factor = if rate_hz > 60_000 { 1 } else { 2 };
        let internal_rate = rate_hz * factor;
        let control_seconds = CONTROL_FRAMES as f64 / f64::from(rate_hz);
        let airway = MammalAirway::new(
            internal_rate,
            shape.glottis(internal_rate)?,
            MammalSpec {
                tubes: [(30.0, 6.0), (18.0, 7.0), (24.0, 6.0), (26.0, 1.8)],
                coarse: 1.3,
                wall_radiation: 1.0,
                oral_tip_from: 0.85,
                oral_tip_area_cm2: shape.mouth_area(),
                velum_area_cm2: shape.nasal_area(),
                glottal_noise_gain: 6e-6,
                oral_noise_gain: Some(4e-6),
                trunk: None,
            },
        )?;
        Ok(Self {
            airway,
            output: CreatureOutput::new(rate_hz, factor as usize, GAIN * level)?,
            factor: factor as usize,
            until_control: 0,
            manual_gate: 0.0,
            gate_target: 0.0,
            gate: 0.0,
            attack_coefficient: 1.0 - libm::exp(-control_seconds / 0.012),
            release_coefficient: 1.0 - libm::exp(-control_seconds / 0.06),
            clock_seconds: 0.0,
            control_seconds,
            shape_coefficients: [0.05, 0.03, 0.04]
                .map(|tau| 1.0 - libm::exp(-control_seconds / tau)),
            performer: shape,
            target: shape,
            current: shape,
            call: None,
            articulating: false,
        })
    }

    pub fn factor(&self) -> usize {
        self.factor
    }

    pub fn geometry(&self) -> AlligatorGeometry {
        AlligatorGeometry {
            common: self.airway.geometry(),
            velum_area_cm2: self.airway.initial_velum_area(),
            oral_noise_cell: self.airway.oral_noise_cell(),
        }
    }

    pub fn set_gate(&mut self, gate: f64) -> Result<(), &'static str> {
        if !(0.0..=1.5).contains(&gate) {
            return Err("アリゲーターの呼気ゲートは0〜1.5の範囲で指定してください");
        }
        self.manual_gate = gate;
        Ok(())
    }

    pub fn set_params(&mut self, params: AlligatorParams) -> Result<(), &'static str> {
        let shape = params.apply(self.performer);
        shape.validate()?;
        self.target = self.call.map_or(shape, |call| {
            call.retain_owned_targets(self.target).apply(shape)
        });
        self.performer = shape;
        Ok(())
    }

    /// 最新の保持音を選ぶ。全解放では音高目標を保ったまま呼気を閉じる。
    pub fn select_midi_note(&mut self, note: Option<u8>) -> Result<(), &'static str> {
        if let Some(note) = note {
            let pitch_hz =
                creature_midi::pitch_hz(note, *PITCH_LIMITS.start(), *PITCH_LIMITS.end())?;
            self.set_params(AlligatorParams {
                pitch_hz: Some(pitch_hz),
                ..AlligatorParams::default()
            })?;
        }
        self.set_gate(if note.is_some() { 1.0 } else { 0.0 })
    }

    /// コールの押下だけを発音に反映する。離鍵しても呼気包絡は進み続ける。
    pub fn midi_call(
        &mut self,
        call: AlligatorCall,
        note: u8,
        pressed: bool,
    ) -> Result<(), &'static str> {
        let pitch_hz = creature_midi::pitch_hz(note, *PITCH_LIMITS.start(), *PITCH_LIMITS.end())?;
        if pressed {
            self.play_call(call, Some(pitch_hz), 1.0)?;
        }
        Ok(())
    }

    pub fn play_call(
        &mut self,
        call: AlligatorCall,
        pitch_hz: Option<f64>,
        amplitude: f64,
    ) -> Result<(), &'static str> {
        if !amplitude.is_finite() || pitch_hz.is_some_and(|pitch| !pitch.is_finite()) {
            return Err("アリゲーターのコールの音高と振幅倍率は有限値で指定してください");
        }
        self.stop_call();
        self.call = Some(Playback::new(call, self.clock_seconds, pitch_hz, amplitude));
        Ok(())
    }

    pub fn stop_call(&mut self) {
        if self.call.take().is_some() {
            self.target = self.performer;
        }
    }

    fn control(&mut self) -> Result<(), &'static str> {
        let mut call_gate = 0.0;
        if let Some(call) = self.call {
            if let Some((targets, gate)) = call.evaluate(self.clock_seconds) {
                self.target = targets.apply(self.target);
                call_gate = gate;
            } else {
                self.stop_call();
            }
        }
        self.gate_target = self.manual_gate.max(call_gate);
        let coefficient = if self.gate_target > self.gate {
            self.attack_coefficient
        } else {
            self.release_coefficient
        };
        self.gate += (self.gate_target - self.gate) * coefficient;
        trim_tiny(&mut self.gate);
        self.output.trim_tail();

        let previous = self.current;
        let [shape, pressure, hiss] = self.shape_coefficients;
        let approach = |current, target, alpha| current + (target - current) * alpha;
        self.current.pitch_hz *= libm::pow(self.target.pitch_hz / previous.pitch_hz, shape);
        self.current.chaos = approach(previous.chaos, self.target.chaos, shape);
        self.current.pressure_cm_h2o = approach(
            previous.pressure_cm_h2o,
            self.target.pressure_cm_h2o,
            pressure,
        );
        self.current.mouth = approach(previous.mouth, self.target.mouth, shape);
        self.current.nostrils = approach(previous.nostrils, self.target.nostrils, shape);
        self.current.hiss = approach(previous.hiss, self.target.hiss, hiss);

        let current = self.current;
        self.airway
            .set_lung_pressure(current.pressure_cm_h2o * CM_H2O * self.gate)?;
        self.airway.set_source(
            current.pitch_hz,
            current.amplitude(),
            current.period_variation(),
        )?;
        self.articulating |=
            previous.mouth != current.mouth || previous.nostrils != current.nostrils;
        if self.articulating {
            self.airway.set_articulation(
                current.mouth_area(),
                current.nasal_area(),
                CONTROL_FRAMES * self.factor,
            )?;
        }
        self.until_control = CONTROL_FRAMES;
        self.clock_seconds += self.control_seconds;
        Ok(())
    }

    pub fn render(&mut self, frames: &mut [AlligatorFrame]) -> Result<(), &'static str> {
        for frame in frames {
            if self.until_control == 0 {
                self.control()?;
            }
            self.until_control -= 1;
            *frame = AlligatorFrame {
                gate: self.gate,
                control: AlligatorControlFrame {
                    call_id: self.call.map_or(0, |call| call.call as u8),
                    clock_seconds: self.clock_seconds,
                    gate_target: self.gate_target,
                    current: self.current,
                    target: self.target,
                    oral_noise: self.airway.oral_noise_cell().is_some(),
                },
                ..AlligatorFrame::default()
            };
            let mut output = None;
            for sample in &mut frame.internal[..self.factor] {
                *sample = self.airway.step(0.02 + 0.8 * self.current.hiss)?;
                output = self.output.push(sample.radiation_derivative_cm3_s2)?;
            }
            frame.output = output.ok_or("アリゲーターの間引きで出力フレームを生成できません")?;
        }
        Ok(())
    }
}
