//! 鳴禽の持続発声・コールと直近の出力フレームの観測に使う C ABI。

use std::ptr;
use vocal_core::{
    airway::songbird::SongbirdControls,
    songbird_voice::{SongbirdCall, SongbirdFrame, SongbirdVoice},
};

pub const MAX_FRAMES: usize = 128;
const ACOUSTIC_WORDS: usize = 8;
const CONTROL_START: usize = ACOUSTIC_WORDS + 3;
const TARGET_START: usize = CONTROL_START + 9;
pub const OBSERVATION_WORDS: usize = TARGET_START + 9;

pub struct SongbirdHandle {
    voice: SongbirdVoice,
    frames: [SongbirdFrame; MAX_FRAMES],
    pcm: [f32; MAX_FRAMES],
    observation: [f64; OBSERVATION_WORDS],
    failed: bool,
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_songbird_layout_version() -> u32 {
    2
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_songbird_max_frames() -> usize {
    MAX_FRAMES
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_songbird_observation_words() -> usize {
    OBSERVATION_WORDS
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_songbird_new(
    sample_rate_hz: u32,
    level: f64,
    pitch_hz: f64,
    interval_semitones: f64,
    voices: f64,
    drive: f64,
    tension: f64,
    pressure_kpa: f64,
    purity: f64,
    oec_cm3: f64,
    gape: f64,
) -> *mut SongbirdHandle {
    let controls = controls_from([
        pitch_hz,
        interval_semitones,
        voices,
        drive,
        tension,
        pressure_kpa,
        purity,
        oec_cm3,
        gape,
    ]);
    let Ok(voice) = SongbirdVoice::new(sample_rate_hz, controls, level) else {
        return ptr::null_mut();
    };
    Box::into_raw(Box::new(SongbirdHandle {
        voice,
        frames: [SongbirdFrame::default(); MAX_FRAMES],
        pcm: [0.0; MAX_FRAMES],
        observation: [0.0; OBSERVATION_WORDS],
        failed: false,
    }))
}

fn controls_from(values: [f64; 9]) -> SongbirdControls {
    let [
        pitch_hz,
        interval_semitones,
        voices,
        drive,
        tension,
        pressure_kpa,
        purity,
        oec_cm3,
        gape,
    ] = values;
    SongbirdControls {
        pitch_hz,
        interval_semitones,
        voices,
        drive,
        tension,
        pressure_kpa,
        purity,
        oec_cm3,
        gape,
    }
}

/// # Safety
/// 非NULLの場合、ハンドルは新規作成時のもので、一度だけ解放する。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_songbird_free(handle: *mut SongbirdHandle) {
    if !handle.is_null() {
        drop(unsafe { Box::from_raw(handle) });
    }
}

/// # Safety
/// 非NULLのハンドルは有効で、この操作中は排他的にアクセスする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_songbird_set_gate(handle: *mut SongbirdHandle, gate: f64) -> u32 {
    let Some(handle) = (unsafe { handle.as_mut() }) else {
        return 0;
    };
    u32::from(!handle.failed && handle.voice.set_gate(gate).is_ok())
}

/// # Safety
/// 非NULLのハンドルは有効で、この操作中は排他的にアクセスする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_songbird_set_controls(
    handle: *mut SongbirdHandle,
    pitch_hz: f64,
    interval_semitones: f64,
    voices: f64,
    drive: f64,
    tension: f64,
    pressure_kpa: f64,
    purity: f64,
    oec_cm3: f64,
    gape: f64,
) -> u32 {
    let Some(handle) = (unsafe { handle.as_mut() }) else {
        return 0;
    };
    let controls = controls_from([
        pitch_hz,
        interval_semitones,
        voices,
        drive,
        tension,
        pressure_kpa,
        purity,
        oec_cm3,
        gape,
    ]);
    u32::from(!handle.failed && handle.voice.set_controls(controls).is_ok())
}

/// MIDI音番号（0〜127）を採用する。−1 は最後のキーの解放。
///
/// # Safety
/// ハンドルは生存中で、他の呼び出しと並行させない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_songbird_select_midi(handle: *mut SongbirdHandle, note: i32) -> u32 {
    let handle = unsafe { &mut *handle };
    if handle.failed || !(-1..=127).contains(&note) {
        return 0;
    }
    u32::from(
        handle
            .voice
            .select_midi_note(u8::try_from(note).ok())
            .is_ok(),
    )
}

fn songbird_call(id: u32) -> Option<SongbirdCall> {
    match id {
        1 => Some(SongbirdCall::Flute),
        2 => Some(SongbirdCall::Trill),
        3 => Some(SongbirdCall::Chirps),
        4 => Some(SongbirdCall::Buzz),
        _ => None,
    }
}

/// 鍵盤の押下でコールを開始する。解放は自動の包絡に影響しない。
///
/// # Safety
/// 非NULLのハンドルは有効で、この操作中は排他的にアクセスする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_songbird_midi_call(
    handle: *mut SongbirdHandle,
    id: u32,
    note: u32,
    pressed: u32,
) -> u32 {
    let (Some(handle), Some(call)) = (unsafe { handle.as_mut() }, songbird_call(id)) else {
        return 0;
    };
    if handle.failed || note > 127 || pressed > 1 {
        return 0;
    }
    u32::from(
        handle
            .voice
            .midi_call(call, note as u8, pressed == 1)
            .is_ok(),
    )
}

/// pitch_hz が NaN のときはコールの既定音高。
///
/// # Safety
/// 非NULLのハンドルは有効で、この操作中は排他的にアクセスする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_songbird_play_call(
    handle: *mut SongbirdHandle,
    id: u32,
    pitch_hz: f64,
    amplitude: f64,
) -> u32 {
    let Some(handle) = (unsafe { handle.as_mut() }) else {
        return 0;
    };
    let Some(call) = songbird_call(id) else {
        return 0;
    };
    let pitch = (!pitch_hz.is_nan()).then_some(pitch_hz);
    u32::from(!handle.failed && handle.voice.play_call(call, pitch, amplitude).is_ok())
}

/// # Safety
/// 非NULLのハンドルは有効で、この操作中は排他的にアクセスする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_songbird_stop_call(handle: *mut SongbirdHandle) -> u32 {
    let Some(handle) = (unsafe { handle.as_mut() }) else {
        return 0;
    };
    if handle.failed {
        return 0;
    }
    handle.voice.stop_call();
    1
}

/// # Safety
/// 非NULLのハンドルは有効で、この操作中は排他的にアクセスする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_songbird_render(handle: *mut SongbirdHandle, len: usize) -> u32 {
    let Some(handle) = (unsafe { handle.as_mut() }) else {
        return 0;
    };
    if handle.failed || !(1..=MAX_FRAMES).contains(&len) {
        return 0;
    }
    let frames = &mut handle.frames[..len];
    if handle.voice.render(frames).is_err() {
        handle.failed = true;
        return 0;
    }
    for (dst, src) in handle.pcm.iter_mut().zip(frames.iter()) {
        *dst = src.pcm;
    }
    let last = &frames[len - 1];
    handle.observation[..CONTROL_START].copy_from_slice(&[
        last.gate,
        last.sac_pressure_dyn_cm2,
        last.opening[0],
        last.opening[1],
        last.port_area_cm2[0],
        last.port_area_cm2[1],
        last.port_flow_cm3_s[0],
        last.port_flow_cm3_s[1],
        last.control_clock_seconds,
        f64::from(last.call_id),
        last.gate_target,
    ]);
    handle.observation[CONTROL_START..TARGET_START].copy_from_slice(&last.controls);
    handle.observation[TARGET_START..].copy_from_slice(&last.targets);
    1
}

/// # Safety
/// ハンドルは有効。次のレンダーが内容を書き換え、解放後は領域を参照できない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_songbird_pcm(handle: *const SongbirdHandle) -> *const f32 {
    unsafe { handle.as_ref() }.map_or(ptr::null(), |handle| handle.pcm.as_ptr())
}

/// # Safety
/// ハンドルは有効。次のレンダーが内容を書き換え、解放後は領域を参照できない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_songbird_observation(handle: *const SongbirdHandle) -> *const f64 {
    unsafe { handle.as_ref() }.map_or(ptr::null(), |handle| handle.observation.as_ptr())
}

/// # Safety
/// 非NULLのハンドルは有効。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_songbird_factor(handle: *const SongbirdHandle) -> usize {
    unsafe { handle.as_ref() }.map_or(0, |handle| handle.voice.factor())
}
