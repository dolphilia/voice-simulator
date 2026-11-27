//! アフリカゾウの発声・コール制御と気道・入口弁の観測を線形メモリへ載せる C ABI。

use std::ptr;
use vocal_core::airway::elephant::{
    ElephantCall, ElephantFrame, ElephantParams, ElephantShape, ElephantVoice,
};

const MAX_FRAMES: usize = 128;
const OBSERVATION_WORDS: usize = 46;

pub struct ElephantHandle {
    voice: ElephantVoice,
    frames: [ElephantFrame; MAX_FRAMES],
    pcm: [f32; MAX_FRAMES],
    observation: [f64; OBSERVATION_WORDS],
    failed: bool,
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_elephant_layout_version() -> u32 {
    3
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_elephant_max_frames() -> usize {
    MAX_FRAMES
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_elephant_observation_words() -> usize {
    OBSERVATION_WORDS
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_elephant_new(
    rate_hz: u32,
    level: f64,
    pitch_hz: f64,
    pressure_cm_h2o: f64,
    trunk: f64,
    chaos: f64,
    mode: f64,
    lip_pitch_hz: f64,
) -> *mut ElephantHandle {
    let shape = ElephantShape {
        pitch_hz,
        pressure_cm_h2o,
        trunk,
        chaos,
        mode,
        lip_pitch_hz,
    };
    let Ok(voice) = ElephantVoice::new(rate_hz, shape, level) else {
        return ptr::null_mut();
    };
    Box::into_raw(Box::new(ElephantHandle {
        voice,
        frames: [ElephantFrame::default(); MAX_FRAMES],
        pcm: [0.0; MAX_FRAMES],
        observation: [0.0; OBSERVATION_WORDS],
        failed: false,
    }))
}

/// # Safety
/// 非NULLなら作成済みのハンドルを一度だけ解放する。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_elephant_free(handle: *mut ElephantHandle) {
    if !handle.is_null() {
        drop(unsafe { Box::from_raw(handle) });
    }
}

/// # Safety
/// 非NULLのハンドルは有効で、この操作中は排他的にアクセスする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_elephant_set_gate(handle: *mut ElephantHandle, gate: f64) -> u32 {
    u32::from(
        unsafe { handle.as_mut() }
            .is_some_and(|handle| !handle.failed && handle.voice.set_gate(gate).is_ok()),
    )
}

/// 保持中のMIDI音を選ぶ。−1は全解放。
///
/// # Safety
/// 非NULLのハンドルは有効で、この操作中は排他的にアクセスする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_elephant_select_midi(handle: *mut ElephantHandle, note: i32) -> u32 {
    if !(-1..=127).contains(&note) {
        return 0;
    }
    u32::from(unsafe { handle.as_mut() }.is_some_and(|handle| {
        !handle.failed
            && handle
                .voice
                .select_midi_note(u8::try_from(note).ok())
                .is_ok()
    }))
}

/// NaN の項目は現在の手動値を使う。
///
/// # Safety
/// 非NULLのハンドルは有効で、この操作中は排他的にアクセスする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_elephant_set_params(
    handle: *mut ElephantHandle,
    pitch_hz: f64,
    pressure_cm_h2o: f64,
    trunk: f64,
    chaos: f64,
    mode: f64,
    lip_pitch_hz: f64,
) -> u32 {
    let optional = |value: f64| (!value.is_nan()).then_some(value);
    let params = ElephantParams {
        pitch_hz: optional(pitch_hz),
        pressure_cm_h2o: optional(pressure_cm_h2o),
        trunk: optional(trunk),
        chaos: optional(chaos),
        mode: optional(mode),
        lip_pitch_hz: optional(lip_pitch_hz),
    };
    u32::from(
        unsafe { handle.as_mut() }
            .is_some_and(|handle| !handle.failed && handle.voice.set_params(params).is_ok()),
    )
}

fn elephant_call(id: u32) -> Option<ElephantCall> {
    match id {
        1 => Some(ElephantCall::Rumble),
        2 => Some(ElephantCall::Trumpet),
        3 => Some(ElephantCall::Squeak),
        _ => None,
    }
}

/// 鍵盤でコールを開始する。pressed が0なら離鍵を表す。
///
/// # Safety
/// 非NULLのハンドルは有効で、この操作中は排他的にアクセスする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_elephant_midi_call(
    handle: *mut ElephantHandle,
    call_id: u32,
    note: u32,
    pressed: u32,
) -> u32 {
    let Some(call) = elephant_call(call_id) else {
        return 0;
    };
    if note > 127 || pressed > 1 {
        return 0;
    }
    u32::from(unsafe { handle.as_mut() }.is_some_and(|handle| {
        !handle.failed
            && handle
                .voice
                .midi_call(call, note as u8, pressed == 1)
                .is_ok()
    }))
}

/// # Safety
/// 非NULLのハンドルは有効で、この操作中は排他的にアクセスする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_elephant_play_call(
    handle: *mut ElephantHandle,
    call_id: u32,
    pitch_hz: f64,
    amplitude: f64,
) -> u32 {
    let Some(call) = elephant_call(call_id) else {
        return 0;
    };
    let pitch = (!pitch_hz.is_nan()).then_some(pitch_hz);
    u32::from(unsafe { handle.as_mut() }.is_some_and(|handle| {
        !handle.failed && handle.voice.play_call(call, pitch, amplitude).is_ok()
    }))
}

/// # Safety
/// 非NULLのハンドルは有効で、この操作中は排他的にアクセスする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_elephant_stop_call(handle: *mut ElephantHandle) -> u32 {
    let Some(handle) = (unsafe { handle.as_mut() }).filter(|handle| !handle.failed) else {
        return 0;
    };
    handle.voice.stop_call();
    1
}

fn observe(frame: &ElephantFrame) -> [f64; OBSERVATION_WORDS] {
    let airway = &frame.airway;
    let trunk = &frame.trunk;
    [
        frame.gate,
        frame.current.pitch_hz,
        frame.current.pressure_cm_h2o,
        frame.current.trunk,
        frame.current.chaos,
        airway.lung_pressure_dyn_cm2,
        airway.lung_flow_cm3_s,
        airway.trachea_end_pressure_dyn_cm2,
        airway.pharynx_pressure_dyn_cm2,
        airway.glottis_drive_dyn_cm2,
        airway.glottis_area_cm2,
        airway.glottis_flow_cm3_s,
        airway.glottis_phase,
        airway.glottis_f0_hz,
        airway.oral_tip_area_cm2,
        airway.velum_area_cm2,
        airway.velum_flow_cm3_s,
        trunk.nasal_base_pressure_dyn_cm2,
        trunk.trunk_inlet_pressure_dyn_cm2,
        trunk.trunk_tip_pressure_dyn_cm2,
        trunk.trunk_valve_area_cm2,
        trunk.trunk_valve_flow_cm3_s,
        airway.wall_radiation_cm3_s,
        airway.oral_radiation_cm3_s,
        airway.nasal_radiation_cm3_s,
        airway.radiation_derivative_cm3_s2,
        frame.output.decimated,
        frame.output.dc_removed,
        frame.target.trunk,
        f64::from(frame.call_id),
        frame.control_clock_seconds,
        frame.gate_goal,
        frame.target.pitch_hz,
        frame.target.pressure_cm_h2o,
        frame.target.chaos,
        frame.current.mode,
        frame.current.lip_pitch_hz,
        frame.target.mode,
        frame.target.lip_pitch_hz,
        frame.current.glottis_abduction_cm2(),
        frame.current.glottis_amplitude_cm2(),
        frame.current.glottal_noise_gain(),
        frame.reed_drive_dyn_cm2,
        frame.reed.opening_cm2,
        frame.reed.height_cm,
        frame.reed.speed_cm_s,
    ]
}

/// # Safety
/// 非NULLのハンドルは有効で、この操作中は排他的にアクセスする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_elephant_render(handle: *mut ElephantHandle, len: usize) -> u32 {
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
    for (value, frame) in handle.pcm.iter_mut().zip(frames.iter()) {
        *value = frame.output.pcm;
    }
    handle.observation = observe(&frames[len - 1]);
    1
}

/// # Safety
/// ハンドルは有効で、次の描画でバッファの内容を上書きする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_elephant_pcm(handle: *const ElephantHandle) -> *const f32 {
    unsafe { handle.as_ref() }.map_or(ptr::null(), |handle| handle.pcm.as_ptr())
}

/// # Safety
/// ハンドルは有効で、次の描画でバッファの内容を上書きする。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_elephant_observation(handle: *const ElephantHandle) -> *const f64 {
    unsafe { handle.as_ref() }.map_or(ptr::null(), |handle| handle.observation.as_ptr())
}
