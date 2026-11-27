//! アザラシの手動発声とコールを描画し、直近フレームの観測を渡す C ABI。

use std::ptr;

use vocal_core::{
    airway::seal::SealShape,
    seal_breath::{SealBreath, SealBreathControls},
    seal_voice::{SealCall, SealFrame, SealVoice},
};

const MAX_FRAMES: usize = 128;
const OBSERVATION_WORDS: usize = 35;

pub struct SealHandle {
    voice: SealVoice,
    frames: [SealFrame; MAX_FRAMES],
    pcm: [f32; MAX_FRAMES],
    observation: [f64; OBSERVATION_WORDS],
    failed: bool,
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_seal_layout_version() -> u32 {
    3
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_seal_max_frames() -> usize {
    MAX_FRAMES
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_seal_observation_words() -> usize {
    OBSERVATION_WORDS
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_seal_new(
    rate_hz: u32,
    level: f64,
    pulse_rate_hz: f64,
    pulse_depth: f64,
    duty: f64,
    pressure_cm_h2o: f64,
    pitch_hz: f64,
    brightness: f64,
    roughness: f64,
    mouth: f64,
) -> *mut SealHandle {
    let controls = SealBreathControls {
        pulse_rate_hz,
        pulse_depth,
        duty,
        pressure_cm_h2o,
    };
    let shape = SealShape {
        pitch_hz,
        brightness,
        roughness,
        mouth,
    };
    let Ok(voice) =
        SealBreath::new(rate_hz, controls).and_then(|breath| SealVoice::new(breath, shape, level))
    else {
        return ptr::null_mut();
    };
    Box::into_raw(Box::new(SealHandle {
        voice,
        frames: [SealFrame::default(); MAX_FRAMES],
        pcm: [0.0; MAX_FRAMES],
        observation: [0.0; OBSERVATION_WORDS],
        failed: false,
    }))
}

/// # Safety
/// 非NULLの場合はこのABIで作成したハンドルを一度だけ解放する。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_seal_free(handle: *mut SealHandle) {
    if !handle.is_null() {
        drop(unsafe { Box::from_raw(handle) });
    }
}

/// # Safety
/// 非NULLのハンドルは有効で、この操作中は排他的にアクセスする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_seal_set_gate(handle: *mut SealHandle, gate: f64) -> u32 {
    apply(unsafe { handle.as_mut() }, |voice| voice.set_gate(gate))
}

fn apply(
    handle: Option<&mut SealHandle>,
    operation: impl FnOnce(&mut SealVoice) -> Result<(), &'static str>,
) -> u32 {
    u32::from(handle.is_some_and(|handle| !handle.failed && operation(&mut handle.voice).is_ok()))
}

/// # Safety
/// 非NULLのハンドルは有効で、この操作中は排他的にアクセスする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_seal_set_breath(
    handle: *mut SealHandle,
    pulse_rate_hz: f64,
    pulse_depth: f64,
    duty: f64,
    pressure_cm_h2o: f64,
) -> u32 {
    apply(unsafe { handle.as_mut() }, |voice| {
        voice.set_breath_controls(SealBreathControls {
            pulse_rate_hz,
            pulse_depth,
            duty,
            pressure_cm_h2o,
        })
    })
}

/// # Safety
/// 非NULLのハンドルは有効で、この操作中は排他的にアクセスする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_seal_set_pitch(handle: *mut SealHandle, pitch_hz: f64) -> u32 {
    apply(unsafe { handle.as_mut() }, |voice| {
        voice.set_pitch(pitch_hz)
    })
}

/// 保持中の最新MIDI音を選ぶ。−1は全解放。
///
/// # Safety
/// 非NULLのハンドルは有効で、この操作中は排他的にアクセスする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_seal_select_midi(handle: *mut SealHandle, note: i32) -> u32 {
    let Some(handle) = (unsafe { handle.as_mut() }) else {
        return 0;
    };
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

/// # Safety
/// 非NULLのハンドルは有効で、この操作中は排他的にアクセスする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_seal_set_roughness(handle: *mut SealHandle, roughness: f64) -> u32 {
    apply(unsafe { handle.as_mut() }, |voice| {
        voice.set_roughness(roughness)
    })
}

fn seal_call(id: u32) -> Option<SealCall> {
    match id {
        1 => Some(SealCall::Trill),
        2 => Some(SealCall::Zap),
        3 => Some(SealCall::Whistle),
        4 => Some(SealCall::Chug),
        _ => None,
    }
}

/// 選択したコールにMIDIの押下または解放を渡す。
///
/// # Safety
/// 非NULLのハンドルは有効で、この操作中は排他的にアクセスする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_seal_midi_call(
    handle: *mut SealHandle,
    id: u32,
    note: u32,
    pressed: u32,
) -> u32 {
    let Some(call) = seal_call(id) else {
        return 0;
    };
    if note > 127 || pressed > 1 {
        return 0;
    }
    apply(unsafe { handle.as_mut() }, |voice| {
        voice.midi_call(call, note as u8, pressed == 1)
    })
}

/// `pitch_hz` の NaN はコール本来の音高を指定する。
///
/// # Safety
/// 非NULLのハンドルは有効で、この操作中は排他的にアクセスする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_seal_play_call(
    handle: *mut SealHandle,
    id: u32,
    pitch_hz: f64,
    amplitude: f64,
) -> u32 {
    let Some(call) = seal_call(id) else {
        return 0;
    };
    let pitch = (!pitch_hz.is_nan()).then_some(pitch_hz);
    apply(unsafe { handle.as_mut() }, |voice| {
        voice.play_call(call, pitch, amplitude)
    })
}

/// # Safety
/// 非NULLのハンドルは有効で、この操作中は排他的にアクセスする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_seal_stop_call(handle: *mut SealHandle) -> u32 {
    apply(unsafe { handle.as_mut() }, |voice| {
        voice.stop_call();
        Ok(())
    })
}

/// # Safety
/// 非NULLのハンドルは有効で、この操作中は排他的にアクセスする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_seal_render(handle: *mut SealHandle, len: usize) -> u32 {
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
    for (output, frame) in handle.pcm.iter_mut().zip(frames.iter()) {
        *output = frame.pcm;
    }
    let last = &frames[len - 1];
    let [first, second] = last.radiation;
    let [glottis_first, glottis_second] = last.glottis;
    let call = last.call;
    let [pulse_rate, depth, duty, pressure] = call.breath;
    let [
        target_pulse_rate,
        target_depth,
        target_duty,
        target_pressure,
    ] = call.breath_targets;
    handle.observation = [
        last.gate_target,
        last.gate,
        last.lung_pressure_dyn_cm2,
        first.wall_cm3_s,
        first.oral_cm3_s,
        first.nasal_cm3_s,
        first.total_derivative_cm3_s2,
        second.wall_cm3_s,
        second.oral_cm3_s,
        second.nasal_cm3_s,
        second.total_derivative_cm3_s2,
        last.decimated,
        last.dc_removed,
        f64::from(call.active),
        call.clock_seconds,
        call.pitch_hz,
        call.pitch_target_hz,
        pulse_rate,
        depth,
        duty,
        pressure,
        target_pulse_rate,
        target_depth,
        target_duty,
        target_pressure,
        call.pulse_phase,
        f64::from(call.id),
        call.roughness,
        call.target_roughness,
        glottis_first.phase,
        glottis_first.f0_hz,
        glottis_first.area_cm2,
        glottis_second.phase,
        glottis_second.f0_hz,
        glottis_second.area_cm2,
    ];
    1
}

/// # Safety
/// ハンドルは有効。描画時に内容を上書きし、解放後は参照できない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_seal_pcm(handle: *const SealHandle) -> *const f32 {
    unsafe { handle.as_ref() }.map_or(ptr::null(), |handle| handle.pcm.as_ptr())
}

/// # Safety
/// ハンドルは有効。描画時に内容を上書きし、解放後は参照できない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_seal_observation(handle: *const SealHandle) -> *const f64 {
    unsafe { handle.as_ref() }.map_or(ptr::null(), |handle| handle.observation.as_ptr())
}

/// # Safety
/// 非NULLのハンドルは有効。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_seal_factor(handle: *const SealHandle) -> usize {
    unsafe { handle.as_ref() }.map_or(0, |handle| handle.voice.factor())
}
