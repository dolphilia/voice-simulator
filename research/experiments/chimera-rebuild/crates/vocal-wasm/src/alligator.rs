//! アリゲーターの発声、コール制御、気道の観測を線形メモリへ載せる C ABI。

use std::ptr;
use vocal_core::airway::alligator::{
    AlligatorAirwaySample, AlligatorCall, AlligatorFrame, AlligatorParams, AlligatorShape,
    AlligatorVoice,
};

const MAX_FRAMES: usize = 128;
const FRAME_WORDS: usize = 5;
const SAMPLE_WORDS: usize = 18;
const FIXED_WORDS: usize = FRAME_WORDS + 2 * SAMPLE_WORDS;
const PARAMETER_COUNT: usize = 6;
const CALL_WORDS: usize = 2 + 2 * PARAMETER_COUNT;
const NOISE_SAMPLE_WORDS: usize = 3;
const OBSERVATION_WORDS: usize = FIXED_WORDS + CALL_WORDS + 2 * NOISE_SAMPLE_WORDS;

pub struct AlligatorHandle {
    voice: AlligatorVoice,
    frames: [AlligatorFrame; MAX_FRAMES],
    pcm: [f32; MAX_FRAMES],
    observation: [f64; OBSERVATION_WORDS],
    failed: bool,
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_alligator_layout_version() -> u32 {
    3
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_alligator_max_frames() -> usize {
    MAX_FRAMES
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_alligator_observation_words() -> usize {
    OBSERVATION_WORDS
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_alligator_new(
    rate_hz: u32,
    level: f64,
    pitch_hz: f64,
    chaos: f64,
    pressure_cm_h2o: f64,
    mouth: f64,
    nostrils: f64,
    hiss: f64,
) -> *mut AlligatorHandle {
    let shape = AlligatorShape {
        pitch_hz,
        chaos,
        pressure_cm_h2o,
        mouth,
        nostrils,
        hiss,
    };
    let Ok(voice) = AlligatorVoice::new(rate_hz, shape, level) else {
        return ptr::null_mut();
    };
    Box::into_raw(Box::new(AlligatorHandle {
        voice,
        frames: [AlligatorFrame::default(); MAX_FRAMES],
        pcm: [0.0; MAX_FRAMES],
        observation: [0.0; OBSERVATION_WORDS],
        failed: false,
    }))
}

/// # Safety
/// 非NULLなら作成済みのハンドルを一度だけ解放する。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_alligator_free(handle: *mut AlligatorHandle) {
    if !handle.is_null() {
        drop(unsafe { Box::from_raw(handle) });
    }
}

/// # Safety
/// 非NULLのハンドルは有効で、この操作中は排他的にアクセスする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_alligator_set_gate(handle: *mut AlligatorHandle, gate: f64) -> u32 {
    apply(unsafe { handle.as_mut() }, |voice| voice.set_gate(gate))
}

fn apply(
    handle: Option<&mut AlligatorHandle>,
    operation: impl FnOnce(&mut AlligatorVoice) -> Result<(), &'static str>,
) -> u32 {
    u32::from(handle.is_some_and(|handle| !handle.failed && operation(&mut handle.voice).is_ok()))
}

/// 保持中のMIDI音を選ぶ。−1は全解放。
///
/// # Safety
/// 非NULLのハンドルは有効で、この操作中は排他的にアクセスする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_alligator_select_midi(
    handle: *mut AlligatorHandle,
    note: i32,
) -> u32 {
    if !(-1..=127).contains(&note) {
        return 0;
    }
    apply(unsafe { handle.as_mut() }, |voice| {
        voice.select_midi_note(u8::try_from(note).ok())
    })
}

/// NaN の項目は現在の手動値を使う。
///
/// # Safety
/// 非NULLのハンドルは有効で、この操作中は排他的にアクセスする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_alligator_set_params(
    handle: *mut AlligatorHandle,
    pitch_hz: f64,
    chaos: f64,
    pressure_cm_h2o: f64,
    mouth: f64,
    nostrils: f64,
    hiss: f64,
) -> u32 {
    let optional = |value: f64| (!value.is_nan()).then_some(value);
    apply(unsafe { handle.as_mut() }, |voice| {
        voice.set_params(AlligatorParams {
            pitch_hz: optional(pitch_hz),
            chaos: optional(chaos),
            pressure_cm_h2o: optional(pressure_cm_h2o),
            mouth: optional(mouth),
            nostrils: optional(nostrils),
            hiss: optional(hiss),
        })
    })
}

fn alligator_call(id: u32) -> Option<AlligatorCall> {
    match id {
        1 => Some(AlligatorCall::Bellow),
        2 => Some(AlligatorCall::Growl),
        3 => Some(AlligatorCall::Hiss),
        4 => Some(AlligatorCall::Dance),
        _ => None,
    }
}

/// 鍵盤でコールを開始する。pressed が0なら離鍵を表す。
///
/// # Safety
/// 非NULLのハンドルは有効で、この操作中は排他的にアクセスする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_alligator_midi_call(
    handle: *mut AlligatorHandle,
    id: u32,
    note: u32,
    pressed: u32,
) -> u32 {
    let Some(call) = alligator_call(id) else {
        return 0;
    };
    if note > 127 || pressed > 1 {
        return 0;
    }
    apply(unsafe { handle.as_mut() }, |voice| {
        voice.midi_call(call, note as u8, pressed == 1)
    })
}

/// 音高が NaN の場合はコール本来の音高を使う。
///
/// # Safety
/// 非NULLのハンドルは有効で、この操作中は排他的にアクセスする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_alligator_play_call(
    handle: *mut AlligatorHandle,
    id: u32,
    pitch_hz: f64,
    amplitude: f64,
) -> u32 {
    let Some(call) = alligator_call(id) else {
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
pub unsafe extern "C" fn vocal_alligator_stop_call(handle: *mut AlligatorHandle) -> u32 {
    apply(unsafe { handle.as_mut() }, |voice| {
        voice.stop_call();
        Ok(())
    })
}

fn sample_values(sample: &AlligatorAirwaySample) -> [f64; SAMPLE_WORDS] {
    [
        sample.lung_pressure_dyn_cm2,
        sample.lung_flow_cm3_s,
        sample.trachea_inlet_pressure_dyn_cm2,
        sample.trachea_end_pressure_dyn_cm2,
        sample.pharynx_pressure_dyn_cm2,
        sample.glottis_drive_dyn_cm2,
        sample.glottis_area_cm2,
        sample.glottis_flow_cm3_s,
        sample.glottis_voicing,
        sample.glottis_phase,
        sample.glottis_f0_hz,
        sample.velum_area_cm2,
        sample.velum_flow_cm3_s,
        sample.wall_radiation_cm3_s,
        sample.oral_radiation_cm3_s,
        sample.nasal_radiation_cm3_s,
        sample.radiation_derivative_cm3_s2,
        sample.oral_tip_area_cm2,
    ]
}

/// # Safety
/// 非NULLのハンドルは有効で、この操作中は排他的にアクセスする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_alligator_render(handle: *mut AlligatorHandle, len: usize) -> u32 {
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
    for (pcm, frame) in handle.pcm.iter_mut().zip(frames.iter()) {
        *pcm = frame.output.pcm;
    }
    let last = &frames[len - 1];
    let (fixed, diagnostics) = handle.observation.split_at_mut(FIXED_WORDS);
    let (call, noise) = diagnostics.split_at_mut(CALL_WORDS);
    let (frame, samples) = fixed.split_at_mut(FRAME_WORDS);
    frame.copy_from_slice(&[
        last.control.gate_target,
        last.gate,
        f64::from(last.control.oral_noise),
        last.output.decimated,
        last.output.dc_removed,
    ]);
    for (output, sample) in samples.chunks_exact_mut(SAMPLE_WORDS).zip(&last.internal) {
        output.copy_from_slice(&sample_values(sample));
    }
    call[0] = f64::from(last.control.call_id);
    call[1] = last.control.clock_seconds;
    let (current, target) = call[2..].split_at_mut(PARAMETER_COUNT);
    current.copy_from_slice(&last.control.current.values());
    target.copy_from_slice(&last.control.target.values());
    for (output, sample) in noise
        .chunks_exact_mut(NOISE_SAMPLE_WORDS)
        .zip(&last.internal)
    {
        output.copy_from_slice(&[
            sample.glottal_noise_level_dyn_cm2,
            sample.glottal_noise_pressure_dyn_cm2,
            sample.oral_noise_level_dyn_cm2,
        ]);
    }
    1
}

/// # Safety
/// ハンドルは有効で、次の描画でバッファの内容を上書きする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_alligator_pcm(handle: *const AlligatorHandle) -> *const f32 {
    unsafe { handle.as_ref() }.map_or(ptr::null(), |handle| handle.pcm.as_ptr())
}

/// # Safety
/// ハンドルは有効で、次の描画でバッファの内容を上書きする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_alligator_observation(handle: *const AlligatorHandle) -> *const f64 {
    unsafe { handle.as_ref() }.map_or(ptr::null(), |handle| handle.observation.as_ptr())
}

/// # Safety
/// 非NULLならハンドルは有効である必要がある。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_alligator_factor(handle: *const AlligatorHandle) -> usize {
    unsafe { handle.as_ref() }.map_or(0, |handle| handle.voice.factor())
}
