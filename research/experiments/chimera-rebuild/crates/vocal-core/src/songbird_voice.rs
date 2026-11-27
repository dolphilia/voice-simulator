//! 鳴禽の演奏パラメータと呼気を更新し、放射を出力PCMにする。

use crate::airway::songbird::{SongbirdAirway, SongbirdControls};
use crate::airway::trim_tiny;
use crate::creature_midi;
use crate::output::Decimator;
use libm::{exp, pow, tanh};
use std::f64::consts::TAU;

mod call;
use call::Playback;
pub use call::SongbirdCall;

pub const CONTROL_FRAMES: usize = 64;
const GAIN: f64 = 4.8e-7;

#[derive(Clone, Copy, Default)]
pub struct SongbirdFrame {
    pub gate: f64,
    pub controls: [f64; 9],
    pub targets: [f64; 9],
    pub control_clock_seconds: f64,
    pub active_call: bool,
    pub call_id: u8,
    pub gate_target: f64,
    pub sac_pressure_dyn_cm2: f64,
    pub opening: [f64; 2],
    pub port_area_cm2: [f64; 2],
    pub port_flow_cm3_s: [f64; 2],
    pub radiation: [f64; 4],
    pub decimated: f64,
    pub dc_removed: f64,
    pub pcm: f32,
}

pub struct SongbirdVoice {
    airway: SongbirdAirway,
    factor: usize,
    decimator: Decimator,
    gain: f64,
    before_control: usize,
    control_seconds: f64,
    clock: f64,
    current: SongbirdControls,
    performer: SongbirdControls,
    target: SongbirdControls,
    gate: f64,
    gate_target: f64,
    call: Option<Playback>,
    call_gate: f64,
    dc_pole: f64,
    previous_input: f64,
    previous_filtered: f64,
}

impl SongbirdVoice {
    pub fn new(rate_hz: u32, initial: SongbirdControls, level: f64) -> Result<Self, &'static str> {
        if !level.is_finite() || level < 0.0 {
            return Err("鳴禽の出力レベルは有限の非負値で指定してください");
        }
        let factor = if rate_hz > 60_000 { 2 } else { 4 };
        let internal_rate = rate_hz
            .checked_mul(factor as u32)
            .ok_or("鳴禽の内部レートが範囲外です")?;
        let airway = SongbirdAirway::new(internal_rate, initial)?;
        Ok(Self {
            airway,
            factor,
            decimator: Decimator::new(factor)?,
            gain: GAIN * level,
            before_control: 0,
            control_seconds: (CONTROL_FRAMES * factor) as f64 / f64::from(internal_rate),
            clock: 0.0,
            current: initial,
            performer: initial,
            target: initial,
            gate: 0.0,
            gate_target: 0.0,
            call: None,
            call_gate: 0.0,
            dc_pole: exp(-TAU * 12.0 / f64::from(rate_hz)),
            previous_input: 0.0,
            previous_filtered: 0.0,
        })
    }

    pub fn factor(&self) -> usize {
        self.factor
    }

    pub fn set_controls(&mut self, controls: SongbirdControls) -> Result<(), &'static str> {
        controls.validate(self.gate_target)?;
        self.performer = controls;
        let mut controls = controls;
        if let Some(call) = self.call {
            call.call.preserve_targets(self.target, &mut controls);
        }
        self.target = controls;
        Ok(())
    }

    pub fn set_gate(&mut self, gate: f64) -> Result<(), &'static str> {
        if !(0.0..=1.5).contains(&gate) {
            return Err("鳴禽の呼気ゲートは0〜1.5の範囲で指定してください");
        }
        self.gate_target = gate;
        Ok(())
    }

    /// 保持中の最新MIDI音を採用する。解放後は基準音高を保持し、呼気を閉じる。
    pub fn select_midi_note(&mut self, note: Option<u8>) -> Result<(), &'static str> {
        if let Some(note) = note {
            let mut controls = self.performer;
            controls.pitch_hz = Self::midi_pitch_hz(note)?;
            self.set_controls(controls)?;
        }
        self.set_gate(if note.is_some() { 1.0 } else { 0.0 })
    }

    /// 押下はコールを指定音高で開始し、解放はコールの包絡をそのまま進める。
    pub fn midi_call(
        &mut self,
        call: SongbirdCall,
        note: u8,
        pressed: bool,
    ) -> Result<(), &'static str> {
        let pitch = Self::midi_pitch_hz(note)?;
        if pressed {
            self.play_call(call, Some(pitch), 1.0)?;
        }
        Ok(())
    }

    fn midi_pitch_hz(note: u8) -> Result<f64, &'static str> {
        creature_midi::pitch_hz(
            note,
            SongbirdControls::PITCH_MIN_HZ,
            SongbirdControls::PITCH_MAX_HZ,
        )
    }

    pub fn play_call(
        &mut self,
        call: SongbirdCall,
        pitch_hz: Option<f64>,
        amplitude: f64,
    ) -> Result<(), &'static str> {
        if !(0.0..=1.5).contains(&amplitude)
            || pitch_hz.is_some_and(|pitch| !pitch.is_finite() || pitch < 0.0)
        {
            return Err("コールの音高には有限の非負値、呼気倍率には0〜1.5を指定してください");
        }
        self.stop_call();
        let pitch_scale = pitch_hz
            .filter(|pitch| *pitch > 0.0)
            .map_or(1.0, |pitch| pitch / call.pitch_reference());
        self.call = Some(Playback {
            call,
            started: self.clock,
            pitch_scale,
            amplitude,
        });
        Ok(())
    }

    pub fn stop_call(&mut self) {
        if self.call.take().is_some() {
            self.target = self.performer;
            self.call_gate = 0.0;
        }
    }

    fn control(&mut self) -> Result<(), &'static str> {
        if let Some(call) = self.call {
            match call.apply(self.clock, &mut self.target) {
                Some(gate) => self.call_gate = gate,
                None => self.stop_call(),
            }
        }
        let dt = self.control_seconds;
        let coefficient = |tau| 1.0 - exp(-dt / tau);
        let linear = |current, target, tau| current + (target - current) * coefficient(tau);
        let log = |current, target, tau| current * pow(target / current, coefficient(tau));
        let c = self.current;
        let t = self.target;
        self.current = SongbirdControls {
            pitch_hz: log(c.pitch_hz, t.pitch_hz, 0.008),
            interval_semitones: linear(c.interval_semitones, t.interval_semitones, 0.020),
            voices: linear(c.voices, t.voices, 0.020),
            drive: linear(c.drive, t.drive, 0.020),
            tension: linear(c.tension, t.tension, 0.020),
            pressure_kpa: linear(c.pressure_kpa, t.pressure_kpa, 0.010),
            purity: linear(c.purity, t.purity, 0.020),
            oec_cm3: log(c.oec_cm3, t.oec_cm3, 0.030),
            gape: linear(c.gape, t.gape, 0.020),
        };
        let gate_target = self.gate_target.max(self.call_gate);
        let tau = if gate_target > self.gate {
            0.004
        } else {
            0.012
        };
        self.gate = linear(self.gate, gate_target, tau);
        trim_tiny(&mut self.gate);
        trim_tiny(&mut self.previous_input);
        trim_tiny(&mut self.previous_filtered);
        self.before_control = CONTROL_FRAMES;
        self.airway
            .control(self.current, self.gate, CONTROL_FRAMES * self.factor)?;
        self.airway.trim_creature_tail();
        self.clock += dt;
        Ok(())
    }

    pub fn render(&mut self, frames: &mut [SongbirdFrame]) -> Result<(), &'static str> {
        for frame in frames {
            if self.before_control == 0 {
                self.control()?;
            }
            self.before_control -= 1;
            frame.gate = self.gate;
            frame.controls = self.current.values();
            frame.targets = self.target.values();
            frame.control_clock_seconds = self.clock;
            frame.active_call = self.call.is_some();
            frame.call_id = self.call.map_or(0, |playback| playback.call as u8);
            frame.gate_target = self.gate_target.max(self.call_gate);
            frame.radiation.fill(0.0);
            for sub in 0..self.factor {
                let sample = self.airway.step()?;
                let radiation = sample.radiation_derivative_cm3_s2;
                if !radiation.is_finite() {
                    return Err("鳴禽の放射に非有限値があります");
                }
                frame.radiation[sub] = radiation;
                frame.sac_pressure_dyn_cm2 = sample.sac_pressure_dyn_cm2;
                frame.opening = sample.opening;
                frame.port_area_cm2 = sample.port_area_cm2;
                frame.port_flow_cm3_s = sample.port_flow_cm3_s;
                if let Some(decimated) = self.decimator.push(radiation) {
                    let input = decimated * self.gain;
                    let filtered =
                        input - self.previous_input + self.dc_pole * self.previous_filtered;
                    if !filtered.is_finite() {
                        return Err("鳴禽のDC除去後の系列に非有限値があります");
                    }
                    self.previous_input = input;
                    self.previous_filtered = filtered;
                    let magnitude = filtered.abs();
                    let bounded = if magnitude > 0.7 {
                        filtered.signum() * (0.7 + 0.3 * tanh((magnitude - 0.7) / 0.3))
                    } else {
                        filtered
                    };
                    frame.decimated = decimated;
                    frame.dc_removed = filtered;
                    frame.pcm = bounded as f32;
                }
            }
        }
        Ok(())
    }
}
