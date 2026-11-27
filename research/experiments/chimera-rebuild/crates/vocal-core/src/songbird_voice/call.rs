//! 鳴禽のコールの目標値。キーの定数と生成規則は固定上流由来で、LICENSE-CHIMERAを付す。

use crate::airway::songbird::SongbirdControls;
use libm::pow;
use serde::Deserialize;

#[derive(Clone, Copy, Deserialize)]
#[serde(rename_all = "snake_case")]
#[repr(u8)]
pub enum SongbirdCall {
    Flute = 1,
    Trill = 2,
    Chirps = 3,
    Buzz = 4,
}

#[derive(Clone, Copy)]
pub(super) struct Playback {
    pub call: SongbirdCall,
    pub started: f64,
    pub pitch_scale: f64,
    pub amplitude: f64,
}

#[derive(Clone, Copy)]
enum Curve {
    Linear,
    Exponential,
    Step,
}

#[derive(Clone, Copy)]
#[repr(usize)]
enum Field {
    Gate,
    Pitch,
    Voices,
    Drive,
    Interval,
    Tension,
    Purity,
}

use Curve::{Exponential, Linear, Step};
use Field::{Drive, Gate, Interval, Pitch, Purity, Tension, Voices};

const PARAMETERS: [Field; 6] = [Pitch, Voices, Drive, Interval, Tension, Purity];

impl Field {
    fn parameter(self, controls: &mut SongbirdControls) -> Option<&mut f64> {
        match self {
            Gate => None,
            Pitch => Some(&mut controls.pitch_hz),
            Voices => Some(&mut controls.voices),
            Drive => Some(&mut controls.drive),
            Interval => Some(&mut controls.interval_semitones),
            Tension => Some(&mut controls.tension),
            Purity => Some(&mut controls.purity),
        }
    }
}

#[derive(Clone, Copy)]
struct Key {
    seconds: f64,
    curve: Curve,
    values: [Option<f64>; PARAMETERS.len() + 1],
}

const fn key(seconds: f64, curve: Curve, values: &[(Field, f64)]) -> Key {
    let mut fields = [None; PARAMETERS.len() + 1];
    let mut i = 0;
    while i < values.len() {
        let (field, value) = values[i];
        fields[field as usize] = Some(value);
        i += 1;
    }
    Key {
        seconds,
        curve,
        values: fields,
    }
}

const FLUTE: &[Key] = &[
    key(
        0.0,
        Linear,
        &[
            (Gate, 0.0),
            (Pitch, 2000.0),
            (Voices, 0.15),
            (Drive, 0.25),
            (Interval, 7.0),
        ],
    ),
    key(0.02, Linear, &[(Gate, 1.0)]),
    key(0.20, Exponential, &[(Gate, 1.0), (Pitch, 2100.0)]),
    key(0.23, Linear, &[(Gate, 0.0)]),
    key(0.30, Step, &[(Gate, 1.0), (Pitch, 2600.0)]),
    key(0.50, Exponential, &[(Pitch, 2500.0)]),
    key(0.53, Linear, &[(Gate, 0.0)]),
    key(
        0.60,
        Step,
        &[(Gate, 1.0), (Pitch, 3300.0), (Voices, 0.5), (Interval, 4.0)],
    ),
    key(1.10, Exponential, &[(Pitch, 3500.0), (Interval, 5.0)]),
    key(1.20, Linear, &[(Gate, 0.0)]),
];

const TRILL: [Key; 1 + 4 * 18] = {
    let initial = key(0.0, Linear, &[(Voices, 0.15), (Drive, 0.30)]);
    let mut keys = [initial; 1 + 4 * 18];
    let period = 1.0 / 16.0;
    let low = 3000.0 * (1.0 - 0.35 / 2.0);
    let high = 3000.0 * (1.0 + 0.35 / 2.0);
    let mut cycle = 0;
    while cycle < 18 {
        let t = cycle as f64 * period;
        let i = 1 + cycle * 4;
        keys[i] = key(t, Step, &[(Gate, 0.0), (Pitch, low)]);
        keys[i + 1] = key(t + 0.08 * period, Linear, &[(Gate, 1.0)]);
        keys[i + 2] = key(
            t + 0.62 * period,
            Exponential,
            &[(Gate, 1.0), (Pitch, high)],
        );
        keys[i + 3] = key(t + 0.75 * period, Linear, &[(Gate, 0.0)]);
        cycle += 1;
    }
    keys
};

const CHIRPS: [Key; 1 + 4 * 9] = {
    let initial = key(0.0, Linear, &[(Voices, 0.15), (Drive, 0.4)]);
    let mut keys = [initial; 1 + 4 * 9];
    let mut burst = 0;
    while burst < 9 {
        let n = burst as f64;
        let t = n * (0.14 - 0.008 * n);
        let i = 1 + 4 * burst;
        keys[i] = key(t, Step, &[(Gate, 0.0), (Pitch, 7000.0 - 300.0 * n)]);
        keys[i + 1] = key(t + 0.01, Linear, &[(Gate, 1.0)]);
        keys[i + 2] = key(
            t + 0.06,
            Exponential,
            &[(Gate, 1.0), (Pitch, 2400.0 - 80.0 * n)],
        );
        keys[i + 3] = key(t + 0.07, Linear, &[(Gate, 0.0)]);
        burst += 1;
    }
    keys
};

const BUZZ: [Key; 2 + 2 * 8] = {
    let initial = key(
        0.0,
        Linear,
        &[
            (Voices, 0.5),
            (Drive, 0.95),
            (Tension, 0.15),
            (Interval, 0.5),
            (Pitch, 1200.0),
            (Purity, 0.1),
            (Gate, 0.0),
        ],
    );
    let mut keys = [initial; 2 + 2 * 8];
    let mut pulse = 0;
    while pulse < 8 {
        let t = pulse as f64 * 0.07;
        keys[1 + 2 * pulse] = key(0.02 + t, Linear, &[(Gate, 1.0)]);
        keys[2 + 2 * pulse] = key(0.06 + t, Linear, &[(Gate, 0.35)]);
        pulse += 1;
    }
    keys[keys.len() - 1] = key(0.6, Linear, &[(Gate, 0.0)]);
    keys
};

fn evaluate(keys: &[Key], field: Field, seconds: f64) -> Option<f64> {
    // chirpsの後半ではキーが時間的に重なる。定義順に読み、最初の未来キーで止める。
    let mut previous = None;
    for key in keys {
        let Some(value) = key.values[field as usize] else {
            continue;
        };
        if key.seconds <= seconds {
            previous = Some((key.seconds, value));
            continue;
        }
        return previous.map(|(t0, x0)| {
            let u = (seconds - t0) / (key.seconds - t0).max(1e-6);
            match key.curve {
                Step => x0,
                Exponential if x0 > 0.0 && value > 0.0 => x0 * pow(value / x0, u),
                _ => x0 + (value - x0) * u,
            }
        });
    }
    previous.map(|(_, value)| value)
}

impl SongbirdCall {
    fn keys(self) -> &'static [Key] {
        match self {
            Self::Flute => FLUTE,
            Self::Trill => &TRILL,
            Self::Chirps => &CHIRPS,
            Self::Buzz => &BUZZ,
        }
    }

    pub(super) fn pitch_reference(self) -> f64 {
        match self {
            Self::Flute => 2600.0,
            Self::Trill => 3000.0,
            Self::Chirps => 4500.0,
            Self::Buzz => 1200.0,
        }
    }

    pub(super) fn preserve_targets(self, mut old: SongbirdControls, new: &mut SongbirdControls) {
        for field in PARAMETERS {
            if self
                .keys()
                .iter()
                .any(|key| key.values[field as usize].is_some())
            {
                *field.parameter(new).expect("演奏パラメータ") =
                    *field.parameter(&mut old).expect("演奏パラメータ");
            }
        }
    }
}

impl Playback {
    /// コールの目標だけを更新し、終了した制御周期では値を返さない。
    pub(super) fn apply(self, clock: f64, target: &mut SongbirdControls) -> Option<f64> {
        let elapsed = clock - self.started;
        let keys = self.call.keys();
        if elapsed > keys.last().expect("コールの末尾キー").seconds + 0.05 {
            return None;
        }
        for field in PARAMETERS {
            if let Some(value) = evaluate(keys, field, elapsed) {
                *field.parameter(target).expect("演奏パラメータ") = if matches!(field, Pitch) {
                    (value * self.pitch_scale).clamp(400.0, 9000.0)
                } else {
                    value
                };
            }
        }
        Some(evaluate(keys, Gate, elapsed).unwrap_or(0.0) * self.amplitude)
    }
}
