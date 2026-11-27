//! アザラシの呼気から、気道と動物音声の出力段を通ってPCMを生成する。

use crate::airway::seal::{SealAirway, SealShape};
use crate::creature_midi;
use crate::output::CreatureOutput;
use crate::seal_breath::{CONTROL_FRAMES, SealBreath, SealBreathControls};
use libm::{exp, pow};

mod call;
use call::Playback;
pub use call::SealCall;

const GAIN: f64 = 6.4e-8;
const PITCH_MIN_HZ: f64 = 40.0;
const PITCH_MAX_HZ: f64 = 6000.0;

fn limit_pitch(pitch_hz: f64) -> f64 {
    pitch_hz.clamp(PITCH_MIN_HZ, PITCH_MAX_HZ)
}

#[derive(Clone, Copy, Debug, Default)]
pub struct SealRadiation {
    pub wall_cm3_s: f64,
    pub oral_cm3_s: f64,
    pub nasal_cm3_s: f64,
    pub total_derivative_cm3_s2: f64,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct SealFrame {
    pub gate_target: f64,
    pub gate: f64,
    pub lung_pressure_dyn_cm2: f64,
    pub radiation: [SealRadiation; 2],
    pub glottis: [SealGlottisFrame; 2],
    pub decimated: f64,
    pub dc_removed: f64,
    pub pcm: f32,
    pub call: SealCallFrame,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct SealGlottisFrame {
    pub phase: f64,
    pub f0_hz: f64,
    pub area_cm2: f64,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct SealCallFrame {
    pub active: bool,
    pub id: u8,
    pub clock_seconds: f64,
    pub pitch_hz: f64,
    pub pitch_target_hz: f64,
    pub breath: [f64; 4],
    pub breath_targets: [f64; 4],
    pub pulse_phase: f64,
    pub roughness: f64,
    pub target_roughness: f64,
}

pub struct SealVoice {
    breath: SealBreath,
    airway: SealAirway,
    output: CreatureOutput,
    factor: usize,
    until_control: usize,
    gate_target: f64,
    gate: f64,
    lung_pressure_dyn_cm2: f64,
    clock_seconds: f64,
    pitch: f64,
    pitch_target: f64,
    performer_pitch: f64,
    roughness: f64,
    target_roughness: f64,
    performer_roughness: f64,
    performer_breath: SealBreathControls,
    performer_gate: f64,
    call: Option<Playback>,
}

impl SealVoice {
    pub fn new(breath: SealBreath, shape: SealShape, level: f64) -> Result<Self, &'static str> {
        if !level.is_finite() || level < 0.0 {
            return Err("アザラシの出力レベルは有限の非負値で指定してください");
        }
        let output_rate = breath.output_rate_hz;
        let factor = if output_rate <= 60_000 { 2 } else { 1 };
        let airway = SealAirway::new(output_rate * factor, shape)?;
        let performer_breath = breath.target;
        let performer_gate = breath.gate_target;
        Ok(Self {
            breath,
            airway,
            output: CreatureOutput::new(output_rate, factor as usize, GAIN * level)?,
            factor: factor as usize,
            until_control: 0,
            gate_target: 0.0,
            gate: 0.0,
            lung_pressure_dyn_cm2: 0.0,
            clock_seconds: 0.0,
            pitch: shape.pitch_hz,
            pitch_target: shape.pitch_hz,
            performer_pitch: shape.pitch_hz,
            roughness: shape.roughness,
            target_roughness: shape.roughness,
            performer_roughness: shape.roughness,
            performer_breath,
            performer_gate,
            call: None,
        })
    }

    pub fn factor(&self) -> usize {
        self.factor
    }

    pub fn set_gate(&mut self, gate: f64) -> Result<(), &'static str> {
        self.performer_gate = SealBreath::manual_gate(gate)?;
        Ok(())
    }

    pub fn set_breath_controls(
        &mut self,
        controls: SealBreathControls,
    ) -> Result<(), &'static str> {
        let controls = controls.normalized()?;
        self.performer_breath = controls;
        self.breath.target = self.call.map_or(controls, |call| {
            call.retain_breath_targets(self.breath.target, controls)
        });
        Ok(())
    }

    pub fn set_pitch(&mut self, pitch_hz: f64) -> Result<(), &'static str> {
        if !pitch_hz.is_finite() {
            return Err("アザラシの演奏音高は有限値で指定してください");
        }
        self.performer_pitch = limit_pitch(pitch_hz);
        if self.call.is_none() {
            self.pitch_target = self.performer_pitch;
        }
        Ok(())
    }

    /// 最新の保持音を採用する。全解放では音高目標を残して呼気を閉じる。
    pub fn select_midi_note(&mut self, note: Option<u8>) -> Result<(), &'static str> {
        if let Some(note) = note {
            self.set_pitch(creature_midi::pitch_hz(note, PITCH_MIN_HZ, PITCH_MAX_HZ)?)?;
        }
        self.set_gate(if note.is_some() { 1.0 } else { 0.0 })
    }

    /// コールを鍵盤の音高で開始する。離鍵後も呼気の包絡はコールが進める。
    pub fn midi_call(
        &mut self,
        call: SealCall,
        note: u8,
        pressed: bool,
    ) -> Result<(), &'static str> {
        let pitch = creature_midi::pitch_hz(note, PITCH_MIN_HZ, PITCH_MAX_HZ)?;
        if pressed {
            self.play_call(call, Some(pitch), 1.0)?;
        }
        Ok(())
    }

    pub fn set_roughness(&mut self, roughness: f64) -> Result<(), &'static str> {
        if !roughness.is_finite() {
            return Err("アザラシの粗さは有限値で指定してください");
        }
        self.performer_roughness = roughness.clamp(0.0, 0.8);
        if !self.call.is_some_and(Playback::owns_roughness) {
            self.target_roughness = self.performer_roughness;
        }
        Ok(())
    }

    pub fn play_call(
        &mut self,
        call: SealCall,
        pitch_hz: Option<f64>,
        amplitude: f64,
    ) -> Result<(), &'static str> {
        if !amplitude.is_finite() || pitch_hz.is_some_and(|pitch| !pitch.is_finite()) {
            return Err("アザラシのコールの音高と振幅倍率は有限値で指定してください");
        }
        self.stop_call();
        self.call = Some(Playback::new(call, self.clock_seconds, pitch_hz, amplitude));
        Ok(())
    }

    pub fn stop_call(&mut self) {
        if self.call.take().is_some() {
            self.pitch_target = self.performer_pitch;
            self.target_roughness = self.performer_roughness;
            self.breath.target = self.performer_breath;
        }
    }

    fn control(&mut self) -> Result<(), &'static str> {
        let mut call_gate = 0.0;
        if let Some(call) = self.call {
            if let Some(controls) = call.control(self.clock_seconds, self.performer_breath) {
                self.pitch_target = controls.pitch_hz;
                self.breath.target = controls.breath;
                call_gate = controls.gate;
                if let Some(roughness) = controls.roughness {
                    self.target_roughness = roughness;
                }
            } else {
                self.stop_call();
            }
        }
        let interval = self.breath.control_seconds;
        self.pitch *= pow(self.pitch_target / self.pitch, 1.0 - exp(-interval / 0.010));
        self.roughness += (self.target_roughness - self.roughness) * (1.0 - exp(-interval / 0.050));
        self.breath.gate_target = self.performer_gate.max(call_gate);
        let breath = self.breath.step();
        self.gate_target = breath.gate_target;
        self.gate = breath.gate;
        self.lung_pressure_dyn_cm2 = breath.lung_pressure_dyn_cm2;
        self.airway.set_pitch(self.pitch)?;
        self.airway.set_roughness(self.roughness);
        self.airway.set_lung_pressure(self.lung_pressure_dyn_cm2)?;
        self.output.trim_tail();
        self.until_control = CONTROL_FRAMES;
        self.clock_seconds += interval;
        Ok(())
    }

    /// ホストの呼び出しをまたいで、制御と出力段の状態を保持する。
    pub fn render(&mut self, frames: &mut [SealFrame]) -> Result<(), &'static str> {
        for frame in frames {
            if self.until_control == 0 {
                self.control()?;
            }
            self.until_control -= 1;
            *frame = SealFrame {
                gate_target: self.gate_target,
                gate: self.gate,
                lung_pressure_dyn_cm2: self.lung_pressure_dyn_cm2,
                call: SealCallFrame {
                    active: self.call.is_some(),
                    id: self.call.map_or(0, Playback::id),
                    clock_seconds: self.clock_seconds,
                    pitch_hz: self.pitch,
                    pitch_target_hz: self.pitch_target,
                    breath: self.breath.current.values(),
                    breath_targets: self.breath.target.values(),
                    pulse_phase: self.breath.phase(),
                    roughness: self.roughness,
                    target_roughness: self.target_roughness,
                },
                ..SealFrame::default()
            };
            let mut output = None;
            for (observation, glottis) in frame.radiation[..self.factor]
                .iter_mut()
                .zip(&mut frame.glottis)
            {
                let sample = self.airway.step()?;
                let radiation = sample.radiation_derivative_cm3_s2;
                *observation = SealRadiation {
                    wall_cm3_s: sample.wall_radiation_cm3_s,
                    oral_cm3_s: sample.oral_radiation_cm3_s,
                    nasal_cm3_s: sample.nasal_radiation_cm3_s,
                    total_derivative_cm3_s2: radiation,
                };
                *glottis = SealGlottisFrame {
                    phase: sample.glottis_phase,
                    f0_hz: sample.glottis_f0_hz,
                    area_cm2: sample.glottis_area_cm2,
                };
                output = self.output.push(radiation)?;
            }
            let output = output.ok_or("アザラシの間引きで出力フレームを生成できません")?;
            frame.decimated = output.decimated;
            frame.dc_removed = output.dc_removed;
            frame.pcm = output.pcm;
        }
        Ok(())
    }
}
