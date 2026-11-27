//! アフリカゾウの声門と口・鼻の発声。出典は notes/elephant-{fixed-voice,rumble,valve}.md。
//! 上流のライセンスは LICENSE-CHIMERA。

use super::mammal::{MammalAirway, MammalGeometry, MammalSpec, TrunkGeometry, TrunkSpec};
use super::trim_tiny;
use crate::breath::CM_H2O;
use crate::creature_midi;
use crate::glottis::{DEFAULT_CYCLE_SEED, DEFAULT_VIBRATO_RATE_HZ, Glottis, GlottisParameters};
use crate::lip_reed::{LipReed, LipReedParameters, LipReedState};
use crate::output::{CreatureOutput, CreaturePcm};
use serde::{Deserialize, Serialize};

pub use super::mammal::{MammalAirwaySample, TrunkSample};
mod call;
pub use call::ElephantCall;
use call::Playback;

pub const CONTROL_FRAMES: usize = 64;
const TRUNK_VALVE_AREA_CM2: f64 = 4.5;
const PITCH_LIMITS: std::ops::RangeInclusive<f64> = 8.0..=45.0;
const DEFAULT_LIP_PITCH_HZ: f64 = 470.0;

fn default_lip_pitch() -> f64 {
    DEFAULT_LIP_PITCH_HZ
}

#[derive(Clone, Copy, Default, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ElephantShape {
    pub pitch_hz: f64,
    pub pressure_cm_h2o: f64,
    pub trunk: f64,
    pub chaos: f64,
    #[serde(default)]
    pub mode: f64,
    #[serde(default = "default_lip_pitch")]
    pub lip_pitch_hz: f64,
}

impl ElephantShape {
    fn validate(self, rate_hz: u32) -> Result<(), &'static str> {
        if !PITCH_LIMITS.contains(&self.pitch_hz)
            || self.pitch_hz >= f64::from(rate_hz) * 0.5
            || !(3.0..=45.0).contains(&self.pressure_cm_h2o)
            || !(150.0..=900.0).contains(&self.lip_pitch_hz)
            || self.lip_pitch_hz >= f64::from(rate_hz) * 0.5
            || [self.trunk, self.chaos, self.mode]
                .into_iter()
                .any(|value| !(0.0..=1.0).contains(&value))
        {
            return Err("ゾウの音高・呼気圧・形状の範囲を確認してください");
        }
        Ok(())
    }

    fn oral_area(self) -> f64 {
        0.05 + 10.0 * (1.0 - self.trunk)
    }

    fn velum_area(self) -> f64 {
        0.1 + 6.0 * self.trunk
    }

    pub fn glottis_amplitude_cm2(self) -> f64 {
        1.6 * (1.0 - self.mode)
    }

    pub fn glottis_abduction_cm2(self) -> f64 {
        0.05 + 3.0 * self.mode
    }

    pub fn glottal_noise_gain(self) -> f64 {
        4e-7 * (1.0 - self.mode)
    }

    fn glottis(self, rate_hz: u32) -> Result<Glottis, &'static str> {
        Glottis::new(
            rate_hz,
            GlottisParameters {
                f0_hz: self.pitch_hz,
                amplitude_cm2: self.glottis_amplitude_cm2(),
                chink_cm2: 0.006,
                open_quotient: 0.6,
                open_with_abduction: 0.0,
                skew: 0.62,
                closure_sharpness: 0.6,
                effort: 0.9,
                closure: 0.0,
                threshold_dyn_cm2: 1.5 * CM_H2O,
                jitter: 0.004,
                shimmer: 0.03,
                cycle_seed: DEFAULT_CYCLE_SEED,
                drift_cents: 6.0,
                vibrato_depth_cents: 0.0,
                vibrato_rate_hz: DEFAULT_VIBRATO_RATE_HZ,
                fry: 0.0,
                diplophonia: 0.0,
                chaos: self.chaos * 0.6,
            },
        )
    }
}

#[derive(Clone, Copy, Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ElephantParams {
    pub pitch_hz: Option<f64>,
    pub pressure_cm_h2o: Option<f64>,
    pub trunk: Option<f64>,
    pub chaos: Option<f64>,
    pub mode: Option<f64>,
    pub lip_pitch_hz: Option<f64>,
}

impl ElephantParams {
    fn apply(self, previous: ElephantShape) -> ElephantShape {
        ElephantShape {
            pitch_hz: self.pitch_hz.unwrap_or(previous.pitch_hz),
            pressure_cm_h2o: self.pressure_cm_h2o.unwrap_or(previous.pressure_cm_h2o),
            trunk: self.trunk.unwrap_or(previous.trunk),
            chaos: self.chaos.unwrap_or(previous.chaos),
            mode: self.mode.unwrap_or(previous.mode),
            lip_pitch_hz: self.lip_pitch_hz.unwrap_or(previous.lip_pitch_hz),
        }
    }
}

#[derive(Serialize)]
pub struct ElephantGeometry {
    #[serde(flatten)]
    mammal: MammalGeometry,
    #[serde(flatten)]
    trunk: TrunkGeometry,
    velum_area_cm2: f64,
}

#[derive(Clone, Copy, Default)]
pub struct ElephantFrame {
    pub gate: f64,
    pub current: ElephantShape,
    pub target: ElephantShape,
    pub gate_goal: f64,
    pub call_id: u8,
    pub control_clock_seconds: f64,
    pub airway: MammalAirwaySample,
    pub trunk: TrunkSample,
    pub reed: LipReedState,
    pub reed_drive_dyn_cm2: f64,
    pub output: CreaturePcm,
}

pub struct ElephantVoice {
    rate_hz: u32,
    airway: MammalAirway,
    reed: LipReed,
    output: CreatureOutput,
    until_control: usize,
    gate: f64,
    manual_gate: f64,
    gate_goal: f64,
    playback: Option<Playback>,
    clock_seconds: f64,
    control_seconds: f64,
    gate_coefficients: [f64; 2],
    shape_coefficients: [f64; 4],
    performer: ElephantShape,
    target: ElephantShape,
    current: ElephantShape,
    articulating: bool,
}

impl ElephantVoice {
    pub fn new(rate_hz: u32, shape: ElephantShape, level: f64) -> Result<Self, &'static str> {
        shape.validate(rate_hz)?;
        let dt = CONTROL_FRAMES as f64 / f64::from(rate_hz);
        let coefficient = |tau: f64| 1.0 - libm::exp(-dt / tau);
        Ok(Self {
            rate_hz,
            airway: MammalAirway::new(
                rate_hz,
                shape.glottis(rate_hz)?,
                MammalSpec {
                    tubes: [(45.0, 14.0), (32.0, 14.0), (28.0, 10.0), (14.0, 6.0)],
                    coarse: 1.2,
                    wall_radiation: 0.6,
                    oral_tip_from: 0.85,
                    oral_tip_area_cm2: shape.oral_area(),
                    velum_area_cm2: shape.velum_area(),
                    glottal_noise_gain: shape.glottal_noise_gain(),
                    oral_noise_gain: None,
                    trunk: Some(TrunkSpec {
                        length_cm: 185.0,
                        base_area_cm2: 4.2,
                        taper_cm2: -3.0,
                        coarse: 2.3,
                        max_cells: 110,
                        perimeter_factor: 1.4,
                    }),
                },
            )?,
            reed: LipReed::new(
                rate_hz,
                LipReedParameters {
                    pitch_hz: shape.lip_pitch_hz,
                    damping_ratio: 0.08,
                    rest_gap_cm: 0.003,
                    width_cm: 2.4,
                    surface_per_mass_cm2_g: 40.0,
                },
            )?,
            output: CreatureOutput::new(rate_hz, 1, 1.8e-6 * level)?,
            until_control: 0,
            gate: 0.0,
            manual_gate: 0.0,
            gate_goal: 0.0,
            playback: None,
            clock_seconds: 0.0,
            control_seconds: dt,
            gate_coefficients: [0.012, 0.06].map(coefficient),
            shape_coefficients: [0.05, 0.02, 0.04, 0.03].map(coefficient),
            performer: shape,
            target: shape,
            current: shape,
            articulating: false,
        })
    }

    pub fn geometry(&self) -> ElephantGeometry {
        ElephantGeometry {
            mammal: self.airway.geometry(),
            trunk: self.airway.trunk_geometry().expect("ゾウには鼻の管がある"),
            velum_area_cm2: self.airway.initial_velum_area(),
        }
    }

    pub fn set_gate(&mut self, gate: f64) -> Result<(), &'static str> {
        if !(0.0..=1.5).contains(&gate) {
            return Err("ゾウの呼気ゲートは0〜1.5の範囲で指定してください");
        }
        self.manual_gate = gate;
        Ok(())
    }

    pub fn set_params(&mut self, params: ElephantParams) -> Result<(), &'static str> {
        let performer = params.apply(self.performer);
        performer.validate(self.rate_hz)?;
        self.performer = performer;
        self.target = self.playback.map_or(performer, |call| {
            call.retain_owned_targets(self.target).apply(performer)
        });
        Ok(())
    }

    /// 最新の保持音を選ぶ。全解放では音高目標を保ったまま呼気を閉じる。
    pub fn select_midi_note(&mut self, note: Option<u8>) -> Result<(), &'static str> {
        if let Some(note) = note {
            let pitch_hz =
                creature_midi::pitch_hz(note, *PITCH_LIMITS.start(), *PITCH_LIMITS.end())?;
            self.set_params(ElephantParams {
                pitch_hz: Some(pitch_hz),
                ..ElephantParams::default()
            })?;
        }
        self.set_gate(if note.is_some() { 1.0 } else { 0.0 })
    }

    /// 鍵盤でコールを開始する。離鍵後もコールの呼気包絡を進める。
    pub fn midi_call(
        &mut self,
        call: ElephantCall,
        note: u8,
        pressed: bool,
    ) -> Result<(), &'static str> {
        let pitch = creature_midi::pitch_hz(note, *PITCH_LIMITS.start(), *PITCH_LIMITS.end())?;
        if pressed {
            self.play_call(call, Some(pitch), 1.0)?;
        }
        Ok(())
    }

    pub fn play_call(
        &mut self,
        call: ElephantCall,
        pitch_hz: Option<f64>,
        amplitude: f64,
    ) -> Result<(), &'static str> {
        if !amplitude.is_finite() || pitch_hz.is_some_and(|pitch| !pitch.is_finite()) {
            return Err("ゾウのコールの音高と振幅倍率は有限値で指定してください");
        }
        self.stop_call();
        self.playback = Some(Playback::new(call, self.clock_seconds, pitch_hz, amplitude));
        Ok(())
    }

    pub fn stop_call(&mut self) {
        if self.playback.take().is_some() {
            self.target = self.performer;
        }
    }

    fn control(&mut self) -> Result<(), &'static str> {
        let mut call_gate = 0.0;
        if let Some(call) = self.playback {
            if let Some((targets, gate)) = call.evaluate(self.clock_seconds) {
                self.target = targets.apply(self.target);
                call_gate = gate;
            } else {
                self.stop_call();
            }
        }
        self.gate_goal = self.manual_gate.max(call_gate);
        let [attack, release] = self.gate_coefficients;
        let gate_alpha = if self.gate_goal > self.gate {
            attack
        } else {
            release
        };
        self.gate += (self.gate_goal - self.gate) * gate_alpha;
        trim_tiny(&mut self.gate);
        self.output.trim_tail();

        let [source, pressure, route, mode] = self.shape_coefficients;
        let previous_trunk = self.current.trunk;
        self.current.pitch_hz *= libm::pow(self.target.pitch_hz / self.current.pitch_hz, source);
        self.current.chaos += (self.target.chaos - self.current.chaos) * source;
        self.current.pressure_cm_h2o +=
            (self.target.pressure_cm_h2o - self.current.pressure_cm_h2o) * pressure;
        self.current.trunk += (self.target.trunk - self.current.trunk) * route;
        self.current.mode += (self.target.mode - self.current.mode) * mode;
        self.current.lip_pitch_hz *= libm::pow(
            self.target.lip_pitch_hz / self.current.lip_pitch_hz,
            pressure,
        );
        let shape = self.current;
        self.airway
            .set_lung_pressure(shape.pressure_cm_h2o * CM_H2O * self.gate)?;
        self.airway.set_source(
            shape.pitch_hz,
            shape.glottis_amplitude_cm2(),
            [shape.chaos * 0.6, 0.004, 0.03],
        )?;
        self.airway
            .set_glottal_noise_gain(shape.glottal_noise_gain())?;
        self.reed.set_pitch(shape.lip_pitch_hz)?;
        self.articulating |= shape.trunk != previous_trunk;
        if self.articulating {
            self.airway
                .set_articulation(shape.oral_area(), shape.velum_area(), CONTROL_FRAMES)?;
        }
        self.until_control = CONTROL_FRAMES;
        self.clock_seconds += self.control_seconds;
        Ok(())
    }

    pub fn render(&mut self, frames: &mut [ElephantFrame]) -> Result<(), &'static str> {
        for frame in frames {
            if self.until_control == 0 {
                self.control()?;
            }
            self.until_control -= 1;
            let shape = self.current;
            let (reed, reed_drive_dyn_cm2, valve_area) = if shape.mode > 0.02 {
                let drive = self
                    .airway
                    .trunk_pressure_difference()
                    .expect("ゾウには鼻の管がある")
                    * shape.mode;
                let reed = self.reed.step(drive);
                (
                    reed,
                    drive,
                    reed.opening_cm2
                        .max(TRUNK_VALVE_AREA_CM2 * (1.0 - shape.mode)),
                )
            } else {
                (self.reed.state(), 0.0, TRUNK_VALVE_AREA_CM2)
            };
            self.airway.set_trunk_valve_area(valve_area)?;
            let airway = self.airway.step(shape.glottis_abduction_cm2())?;
            *frame = ElephantFrame {
                gate: self.gate,
                current: self.current,
                target: self.target,
                gate_goal: self.gate_goal,
                call_id: self.playback.map_or(0, |call| call.id as u8),
                control_clock_seconds: self.clock_seconds,
                airway,
                trunk: self.airway.trunk_sample().expect("ゾウには鼻の管がある"),
                reed,
                reed_drive_dyn_cm2,
                output: self
                    .output
                    .push(airway.radiation_derivative_cm3_s2)?
                    .ok_or("ゾウの出力フレームを生成できません")?,
            };
        }
        Ok(())
    }
}
