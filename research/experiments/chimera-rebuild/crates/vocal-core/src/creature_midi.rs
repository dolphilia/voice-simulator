//! 固定上流の動物ごとの発声域に合わせた鍵盤の移調。

use crate::phonetics::song::midi_to_hz;
use libm::{floor, log2, pow, sqrt};

/// 中央のドを音域の中央へオクターブ単位で近づけ、範囲を外れた音を折り返す。
pub(crate) fn pitch_hz(note: u8, low: f64, high: f64) -> Result<f64, &'static str> {
    if note > 127 {
        return Err("MIDI音番号は0〜127の範囲で指定してください");
    }
    let octaves = floor(log2(sqrt(low * high) / midi_to_hz(60.0)) + 0.5);
    let mut pitch = midi_to_hz(f64::from(note)) * pow(2.0, octaves);
    while pitch > high {
        pitch *= 0.5;
    }
    while pitch < low {
        pitch *= 2.0;
    }
    Ok(pitch.min(high))
}
