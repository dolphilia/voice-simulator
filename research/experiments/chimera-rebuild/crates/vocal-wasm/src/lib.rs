//! 固定姿勢と調音スコアの発声を線形メモリ経由で操作するC ABI。
//! バッファはハンドルが所有し、次のレンダーで内容を上書きする。

mod alligator;
mod duet_head;
mod elephant;
mod planning;
mod seal;
mod songbird;

use std::ptr;
#[cfg(all(target_arch = "wasm32", feature = "render-phase-probe"))]
use vocal_core::render_phase_probe::{self, Phase};
use vocal_core::{
    airway::human::{HumanAirway, TurbulenceSettings},
    anatomy::{AreaSample, Articulation, BodyMix, MAX_MEASUREMENT_RAYS, SagittalModel},
    articulators::{ARTICULATOR_COUNT, Articulator},
    output::OutputStage,
    phonetics::{
        beatbox::{BeatPlayer, BeatSound},
        live_song::{KeyEvent, LiveSong},
        syllables::Syllable,
    },
    score::Gesture,
    voice::{ArticulatedVoice, FixedVoice, FixedVoiceSettings, VoiceSample},
};

const MAX_FRAMES: usize = 4096;
const CONTROL_OUTPUT_FRAMES: usize = 64;
const CONFIG_WORDS: usize = ARTICULATOR_COUNT + 6;
const OBSERVATION_WORDS: usize = 23;
const GLOTTAL_TRACE_WORDS: usize = 2;
const RADIATION_TRACE_WORDS: usize = 5;
const TRACT_GRID_WORDS: usize = 1 + MAX_MEASUREMENT_RAYS * AreaSample::COLUMN_NAMES.len();

pub struct Handle {
    internal_rate: u32,
    output_rate: u32,
    config: [f64; CONFIG_WORDS],
    pcm: Box<[f32; MAX_FRAMES]>,
    observation: [f64; OBSERVATION_WORDS],
    tract: Vec<f64>,
    tract_grid: Vec<f64>,
    area_grid: Vec<f64>,
    glottal_trace: Vec<f64>,
    radiation_trace: Vec<f64>,
    score: Vec<f64>,
    beat_text: Vec<u8>,
    state: Option<RenderState>,
    score_preparation: Option<PendingScore>,
    failed: bool,
}

struct PendingScore {
    gestures: Vec<Gesture>,
    remaining: usize,
}

struct RenderState {
    voice: Voice,
    stage: OutputStage,
    rendered: u64,
    beat: Option<BeatPlayback>,
    song: Option<LiveSong>,
    manual: bool,
}

struct BeatPlayback {
    player: BeatPlayer,
    scratch: Vec<Gesture>,
}

enum Voice {
    Fixed(Box<FixedVoice>),
    Articulated(Box<ArticulatedVoice>),
}

impl Voice {
    fn step(&mut self) -> Result<VoiceSample, &'static str> {
        match self {
            Self::Fixed(voice) => voice.step(),
            Self::Articulated(voice) => voice.step(),
        }
    }
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_layout_version() -> u32 {
    1
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_max_frames() -> usize {
    MAX_FRAMES
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_control_output_frames() -> usize {
    CONTROL_OUTPUT_FRAMES
}

/// 設定用の領域と出力の領域を確保する。
#[unsafe(no_mangle)]
pub extern "C" fn vocal_new(internal_rate: u32, output_rate: u32) -> *mut Handle {
    Box::into_raw(Box::new(Handle {
        internal_rate,
        output_rate,
        config: [f64::NAN; CONFIG_WORDS],
        pcm: Box::new([0.0; MAX_FRAMES]),
        observation: [0.0; OBSERVATION_WORDS],
        tract: Vec::new(),
        tract_grid: Vec::new(),
        area_grid: Vec::new(),
        glottal_trace: Vec::new(),
        radiation_trace: Vec::new(),
        score: Vec::new(),
        beat_text: Vec::new(),
        state: None,
        score_preparation: None,
        failed: false,
    }))
}

/// # Safety
/// ポインタは `vocal_new` から受け取ったものを一度だけ解放する。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_free(handle: *mut Handle) {
    if !handle.is_null() {
        drop(unsafe { Box::from_raw(handle) });
    }
}

/// 開始前に、調音軸17値と音源・ゲイン6値をこの順に書き込む。
///
/// # Safety
/// ハンドルは生存中で、構成領域への書き込みは他の呼び出しと並行させない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_config(handle: *mut Handle) -> *mut f64 {
    unsafe { &mut *handle }.config.as_mut_ptr()
}

/// ケースの固定姿勢と音源で準備する。成功は1、入力不正または開始済みなら0。
///
/// # Safety
/// ハンドルは生存中で、他の呼び出しと並行させない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_start(handle: *mut Handle) -> u32 {
    let handle = unsafe { &mut *handle };
    if handle.state.is_some() {
        return 0;
    }
    match handle.build() {
        Ok(state) => {
            handle.state = Some(state);
            1
        }
        Err(_) => 0,
    }
}

/// 可動声道を初期姿勢と同じサンプル時計で開始する。
///
/// # Safety
/// ハンドルは生存中で、他の呼び出しと並行させない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_start_manual(handle: *mut Handle) -> u32 {
    let handle = unsafe { &mut *handle };
    if handle.state.is_some() || handle.failed {
        return 0;
    }
    let Ok((posture, source, stage)) = handle.configured() else {
        return 0;
    };
    let Ok(voice) = ArticulatedVoice::for_speech(
        handle.internal_rate,
        CONTROL_OUTPUT_FRAMES * stage.factor(),
        posture,
        source,
    ) else {
        return 0;
    };
    handle.state = Some(RenderState {
        voice: Voice::Articulated(Box::new(voice)),
        stage,
        rendered: 0,
        beat: None,
        song: None,
        manual: true,
    });
    1
}

/// 開始前にスコアの数値領域を確保する。
///
/// # Safety
/// ハンドルは生存中で、書き込みを他の呼び出しと並行させない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_score_buffer(handle: *mut Handle, words: usize) -> *mut f64 {
    let handle = unsafe { &mut *handle };
    if handle.state.is_some()
        || words == 0
        || words > planning::MAX_GESTURES * planning::SCORE_WORDS
        || !words.is_multiple_of(planning::SCORE_WORDS)
    {
        return std::ptr::null_mut();
    }
    handle.score.resize(words, f64::NAN);
    handle.score.as_mut_ptr()
}

/// 最初のフレームより前に、調音スコアを合成器へ配置する。
///
/// # Safety
/// ハンドルは生存中で、他の呼び出しと並行させない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_start_score(
    handle: *mut Handle,
    noise_scale: f64,
    base_pitch_hz: f64,
) -> u32 {
    unsafe { vocal_start_score_with_body(handle, noise_scale, base_pitch_hz, 0.0, 0.0) }
}

/// 選択した体型の声道と声門を作り、最初のフレームより前にスコアを配置する。
///
/// # Safety
/// ハンドルは生存中で、他の呼び出しと並行させない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_start_score_with_body(
    handle: *mut Handle,
    noise_scale: f64,
    base_pitch_hz: f64,
    female: f64,
    child: f64,
) -> u32 {
    start_score(
        unsafe { &mut *handle },
        (!noise_scale.is_nan()).then_some(TurbulenceSettings {
            scale: noise_scale,
            ..TurbulenceSettings::default()
        }),
        base_pitch_hz,
        BodyMix::new(female, child),
        None,
    )
}

/// 調音スコアを声門・狭窄のゲイン倍率と歯の低域通過周波数の下限（Hz）付きで開始する。
///
/// # Safety
/// ハンドルは生存中で、他の呼び出しと並行させない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_start_score_with_turbulence(
    handle: *mut Handle,
    noise_scale: f64,
    base_pitch_hz: f64,
    female: f64,
    child: f64,
    glottis_gain_multiplier: f64,
    constriction_gain_multiplier: f64,
    teeth_lowpass_floor_hz: f64,
) -> u32 {
    start_score(
        unsafe { &mut *handle },
        Some(TurbulenceSettings {
            scale: noise_scale,
            glottis_gain_multiplier,
            constriction_gain_multiplier,
            teeth_lowpass_floor_hz,
        }),
        base_pitch_hz,
        BodyMix::new(female, child),
        None,
    )
}

/// 音源の揺らぎを設定し、指定出力フレームを描画した状態からスコアを開始する。
///
/// # Safety
/// ハンドルは生存中で、他の呼び出しと並行させない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_start_score_prepared(
    handle: *mut Handle,
    noise_scale: f64,
    base_pitch_hz: f64,
    female: f64,
    child: f64,
    glottis_gain_multiplier: f64,
    constriction_gain_multiplier: f64,
    teeth_lowpass_floor_hz: f64,
    warm_up_frames: usize,
    pitch_drift_cents: f64,
    period_jitter: f64,
    amplitude_shimmer: f64,
) -> u32 {
    let started = unsafe {
        vocal_start_score_preparation(
            handle,
            noise_scale,
            base_pitch_hz,
            female,
            child,
            glottis_gain_multiplier,
            constriction_gain_multiplier,
            teeth_lowpass_floor_hz,
            warm_up_frames,
            pitch_drift_cents,
            period_jitter,
            amplitude_shimmer,
        )
    };
    if started == 0 || warm_up_frames == 0 {
        return started;
    }
    let handle = unsafe { &mut *handle };
    if handle.advance_score_preparation(warm_up_frames).is_err() {
        handle.state = None;
        handle.score_preparation = None;
        return 0;
    }
    1
}

/// スコアの予備描画を準備し、描画は後続の呼び出しで行う。0フレームなら即座に予約する。
///
/// # Safety
/// ハンドルは生存中で、他の呼び出しと並行させない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_start_score_preparation(
    handle: *mut Handle,
    noise_scale: f64,
    base_pitch_hz: f64,
    female: f64,
    child: f64,
    glottis_gain_multiplier: f64,
    constriction_gain_multiplier: f64,
    teeth_lowpass_floor_hz: f64,
    warm_up_frames: usize,
    pitch_drift_cents: f64,
    period_jitter: f64,
    amplitude_shimmer: f64,
) -> u32 {
    start_score(
        unsafe { &mut *handle },
        (!noise_scale.is_nan()).then_some(TurbulenceSettings {
            scale: noise_scale,
            glottis_gain_multiplier,
            constriction_gain_multiplier,
            teeth_lowpass_floor_hz,
        }),
        base_pitch_hz,
        BodyMix::new(female, child),
        Some(ScorePreparation {
            warm_up_frames,
            pitch_drift_cents,
            period_jitter,
            amplitude_shimmer,
        }),
    )
}

/// 予備描画を指定出力フレーム数まで進める。最後の片の直後にスコアを予約する。
///
/// # Safety
/// ハンドルは生存中で、他の呼び出しと並行させない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_advance_score_preparation(
    handle: *mut Handle,
    frames: usize,
) -> u32 {
    let handle = unsafe { &mut *handle };
    if handle.failed || handle.score_preparation.is_none() || !(1..=MAX_FRAMES).contains(&frames) {
        return 0;
    }
    if handle.advance_score_preparation(frames).is_err() {
        handle.failed = true;
        return 0;
    }
    1
}

struct ScorePreparation {
    warm_up_frames: usize,
    pitch_drift_cents: f64,
    period_jitter: f64,
    amplitude_shimmer: f64,
}

fn start_score(
    handle: &mut Handle,
    turbulence: Option<TurbulenceSettings>,
    base_pitch_hz: f64,
    body: BodyMix,
    preparation: Option<ScorePreparation>,
) -> u32 {
    if handle.state.is_some() || handle.score.is_empty() {
        return 0;
    }
    let prepare = || {
        let (posture, source, stage) = handle.configured()?;
        let mut voice = ArticulatedVoice::for_speech_with_body(
            handle.internal_rate,
            CONTROL_OUTPUT_FRAMES * stage.factor(),
            posture,
            source,
            body,
        )?;
        if !base_pitch_hz.is_nan() {
            voice.set_base_pitch(base_pitch_hz)?;
        }
        if let Some(settings) = turbulence {
            voice.enable_turbulence_with_settings(settings)?;
        }
        let gestures = planning::decode_score(&handle.score);
        let pending = if let Some(preparation) = preparation {
            preparation
                .warm_up_frames
                .checked_mul(stage.factor())
                .ok_or("予備描画の内部フレーム数が範囲外です")?;
            voice.set_pitch_drift_cents(preparation.pitch_drift_cents)?;
            voice.set_period_jitter(preparation.period_jitter)?;
            voice.set_amplitude_shimmer(preparation.amplitude_shimmer)?;
            if preparation.warm_up_frames == 0 {
                schedule_prepared_score(&mut voice, gestures)?;
                None
            } else {
                Some(PendingScore {
                    gestures,
                    remaining: preparation.warm_up_frames,
                })
            }
        } else {
            voice.set_score(gestures)?;
            None
        };
        Ok::<_, &'static str>((
            RenderState {
                voice: Voice::Articulated(Box::new(voice)),
                stage,
                rendered: 0,
                beat: None,
                song: None,
                manual: false,
            },
            pending,
        ))
    };
    match prepare() {
        Ok((state, pending)) => {
            handle.state = Some(state);
            handle.score_preparation = pending;
            1
        }
        Err(_) => 0,
    }
}

fn schedule_prepared_score(
    voice: &mut ArticulatedVoice,
    mut gestures: Vec<Gesture>,
) -> Result<(), &'static str> {
    let origin = voice.clock_seconds();
    for gesture in &mut gestures {
        gesture.t0 += origin;
        gesture.t1 += origin;
    }
    voice.set_score(gestures)
}

/// 開始前にUTF-8の記譜文字列を書き込む領域を確保する。
///
/// # Safety
/// ハンドルは生存中で、書き込みを他の呼び出しと並行させない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_beat_text(handle: *mut Handle, bytes: usize) -> *mut u8 {
    let handle = unsafe { &mut *handle };
    let input = &mut handle.beat_text;
    if handle.state.is_some()
        || bytes == 0
        || input
            .try_reserve_exact(bytes.saturating_sub(input.len()))
            .is_err()
    {
        return ptr::null_mut();
    }
    input.resize(bytes, 0);
    input.as_mut_ptr()
}

/// 固定パターンを成人男性の打音モードで開始する。
///
/// # Safety
/// ハンドルは生存中で、他の呼び出しと並行させない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_start_beat(
    handle: *mut Handle,
    bpm: f64,
    swing: f64,
    initial_pitch_hz: f64,
    noise_scale: f64,
) -> u32 {
    let handle = unsafe { &mut *handle };
    if handle.state.is_some() || handle.beat_text.is_empty() {
        return 0;
    }
    let prepare = || {
        let pattern = std::str::from_utf8(&handle.beat_text)
            .map_err(|_| "ビートはUTF-8で指定してください")?;
        let player = BeatPlayer::starting(pattern, bpm, swing, 0.0)?;
        let (posture, mut source, stage) = handle.configured()?;
        let base_pitch_hz = source.f0_hz;
        source.f0_hz = initial_pitch_hz;
        let mut voice = ArticulatedVoice::for_speech(
            handle.internal_rate,
            CONTROL_OUTPUT_FRAMES * stage.factor(),
            posture,
            source,
        )?;
        voice.configure_beatbox(base_pitch_hz, noise_scale)?;
        // 先読みと減衰で重なるジェスチャーを準備時に確保する。
        voice.set_score(Vec::with_capacity(16 * BeatSound::MAX_GESTURES))?;
        Ok::<_, &'static str>(RenderState {
            voice: Voice::Articulated(Box::new(voice)),
            stage,
            rendered: 0,
            manual: false,
            beat: Some(BeatPlayback {
                player,
                scratch: Vec::with_capacity(BeatSound::MAX_GESTURES),
            }),
            song: None,
        })
    };
    match prepare() {
        Ok(state) => {
            handle.state = Some(state);
            1
        }
        Err(_) => 0,
    }
}

/// 準備領域に書いた音節JSONから鍵盤歌唱を初期化する。
///
/// # Safety
/// ハンドルは有効で、他の呼び出しと並行させない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_start_live_song(
    handle: *mut Handle,
    vibrato: f64,
    female: f64,
    child: f64,
) -> u32 {
    let handle = unsafe { &mut *handle };
    if handle.state.is_some() {
        return 0;
    }
    let start = || {
        let syllables: Vec<Syllable> =
            serde_json::from_slice(&handle.beat_text).map_err(|_| "音節JSONを読み取れません")?;
        let body = BodyMix::new(female, child);
        let song = LiveSong::new(syllables, body, vibrato)?;
        let (posture, source, stage) = handle.configured()?;
        let mut voice = ArticulatedVoice::for_speech_with_body(
            handle.internal_rate,
            CONTROL_OUTPUT_FRAMES * stage.factor(),
            posture,
            source,
            body,
        )?;
        voice.enable_turbulence(1.0)?;
        Ok::<_, &'static str>(RenderState {
            voice: Voice::Articulated(Box::new(voice)),
            stage,
            rendered: 0,
            beat: None,
            song: Some(song),
            manual: false,
        })
    };
    let Ok(state) = start() else { return 0 };
    handle.state = Some(state);
    1
}

/// 速度が0なら解放、正なら押下。次の出力フレームから反映する。
///
/// # Safety
/// ハンドルは有効で、他の呼び出しと並行させない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_live_song_key(handle: *mut Handle, note: u32, velocity: u32) -> u32 {
    let handle = unsafe { &mut *handle };
    let Some(RenderState {
        voice: Voice::Articulated(voice),
        song: Some(song),
        ..
    }) = &mut handle.state
    else {
        return 0;
    };
    let (Ok(note), Ok(velocity)) = (u8::try_from(note), u8::try_from(velocity)) else {
        return 0;
    };
    let key = if velocity == 0 {
        KeyEvent::NoteOff { note }
    } else {
        KeyEvent::NoteOn { note, velocity }
    };
    u32::from(song.apply(key, voice).is_ok())
}

/// 録音停止時に鍵盤歌唱の調音スコアを終了する。
///
/// # Safety
/// ハンドルは有効で、他の呼び出しと並行させない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_stop_live_song(handle: *mut Handle) -> u32 {
    let handle = unsafe { &mut *handle };
    let Some(RenderState {
        voice: Voice::Articulated(voice),
        song: Some(_),
        ..
    }) = &mut handle.state
    else {
        return 0;
    };
    voice.cancel_score();
    1
}

/// 現在の音源時計でテンポを更新する。NaNの項目は現在値を保持する。
///
/// # Safety
/// ハンドルは生存中で、他の呼び出しと並行させない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_set_beat_tempo(handle: *mut Handle, bpm: f64, swing: f64) -> u32 {
    let handle = unsafe { &mut *handle };
    let Some(beat) = handle.state.as_mut().and_then(|state| state.beat.as_mut()) else {
        return 0;
    };
    u32::from(
        !handle.failed
            && beat
                .player
                .set_tempo(
                    (!bpm.is_nan()).then_some(bpm),
                    (!swing.is_nan()).then_some(swing),
                )
                .is_ok(),
    )
}

/// 音源を進める前に再生状態を更新し、停止した場合はスコアを消去する。
///
/// # Safety
/// ハンドルは生存中で、他の呼び出しと並行させない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_set_beat_playing(handle: *mut Handle, playing: u32) -> u32 {
    let handle = unsafe { &mut *handle };
    let Some(RenderState {
        beat: Some(beat),
        voice: Voice::Articulated(voice),
        ..
    }) = &mut handle.state
    else {
        return 0;
    };
    if handle.failed || playing > 1 {
        return 0;
    }
    match beat.player.set_playing(playing == 1, voice.clock_seconds()) {
        Ok(clear) => {
            if clear {
                voice.cancel_score();
            }
            1
        }
        Err(_) => 0,
    }
}

/// 次の描画フレームからビートの低音を押下または解放する。
///
/// # Safety
/// ハンドルは生存中で、他の呼び出しと並行させない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_beat_bass_key(handle: *mut Handle, note: u32, pressed: u32) -> u32 {
    let handle = unsafe { &mut *handle };
    let Some(RenderState {
        beat: Some(beat),
        voice: Voice::Articulated(voice),
        ..
    }) = &mut handle.state
    else {
        return 0;
    };
    u32::from(
        !handle.failed
            && note <= 127
            && pressed <= 1
            && beat.player.set_bass_key(note as u8, pressed == 1).is_ok()
            && beat.player.apply_bass(voice).is_ok(),
    )
}

/// 次に未予約のステップを採用するときに使う、ハムのセルを切り替える。
///
/// # Safety
/// ハンドルは生存中で、他の呼び出しと並行させない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_toggle_beat_hum(handle: *mut Handle, step: usize) -> u32 {
    let handle = unsafe { &mut *handle };
    let Some(beat) = handle.state.as_mut().and_then(|state| state.beat.as_mut()) else {
        return 0;
    };
    u32::from(!handle.failed && beat.player.toggle_hum(step).is_ok())
}

/// 開始後、次の呼び出しで指定数のPCMをこの先頭から書く。
///
/// # Safety
/// ハンドルは生存中で、返された領域は読み取り専用。レンダーと同時に読まない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_pcm(handle: *const Handle) -> *const f32 {
    unsafe { &*handle }.pcm.as_ptr()
}

/// 最後に処理した出力フレームの観測領域を返す。
///
/// # Safety
/// ハンドルは生存中で、返された領域は読み取り専用。レンダーと同時に読まない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_observation(handle: *const Handle) -> *const f64 {
    unsafe { &*handle }.observation.as_ptr()
}

/// 声門の観測領域を確保する。レンダーごとに出力フレーム順の面積・流量を上書きする。
///
/// # Safety
/// ハンドルは生存中で、領域と他の呼び出しへの並行アクセスは行わない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_glottal_trace_init(handle: *mut Handle) -> *const f64 {
    let trace = &mut unsafe { &mut *handle }.glottal_trace;
    trace.resize(MAX_FRAMES * GLOTTAL_TRACE_WORDS, 0.0);
    trace.as_ptr()
}

/// 各出力フレームの末尾で、壁・口端・鼻端・合算の流量（cm³/s）と微分（cm³/s²）を採取する。
/// 領域はレンダーごとに先頭から上書きされ、直近の成功した呼び出しのフレーム数だけ有効。
/// # Safety
/// ハンドルは生存中で、返された領域は読み取り専用。他の呼び出しと並行して読まない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_radiation_trace_init(handle: *mut Handle) -> *const f64 {
    let trace = &mut unsafe { &mut *handle }.radiation_trace;
    trace.resize(MAX_FRAMES * RADIATION_TRACE_WORDS, 0.0);
    trace.as_ptr()
}

/// 固定姿勢の測定線と断面積を取得する。冒頭1値が行数で、続く各行は11値。
/// 矢状面の座標と計算面積を保持し、描画側で三次元へ変換する。
///
/// # Safety
/// ハンドルは生存中で、領域と他の呼び出しへの並行アクセスは行わない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_fixed_area_grid(handle: *mut Handle) -> *const f64 {
    let handle = unsafe { &mut *handle };
    let Ok((posture, _, _)) = handle.configured() else {
        return ptr::null();
    };
    let model = SagittalModel::adult_male();
    let Ok(profile) = model.area_profile(&model.compute(posture)) else {
        return ptr::null();
    };
    handle.area_grid.clear();
    handle.area_grid.push(profile.samples.len() as f64);
    for sample in profile.samples {
        handle
            .area_grid
            .extend_from_slice(&sample.measurement_values());
    }
    handle.area_grid.as_ptr()
}

/// 声道の採取領域を確保する。冒頭2値は咽頭・口腔のセル数。
///
/// # Safety
/// ハンドルは生存中で、領域と他の呼び出しへの並行アクセスは行わない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_tract_init(handle: *mut Handle) -> *const f64 {
    let handle = unsafe { &mut *handle };
    let Some(Voice::Articulated(voice)) = handle.state.as_ref().map(|state| &state.voice) else {
        return ptr::null();
    };
    let [pharynx, oral] = voice.airway().tract_section_counts();
    handle.tract.resize(2 + 5 * (pharynx + oral), 0.0);
    handle.tract[..2].copy_from_slice(&[pharynx as f64, oral as f64]);
    handle.tract.as_ptr()
}

/// 全セルの断面（長さ、平均面積、最小面積）に続いて、全セルの圧力と流量を保存する。
///
/// # Safety
/// ハンドルは生存中で、領域と他の呼び出しへの並行アクセスは行わない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_tract_snapshot(handle: *mut Handle) -> u32 {
    let handle = unsafe { &mut *handle };
    if handle.tract.is_empty() || handle.failed {
        return 0;
    }
    let Some(Voice::Articulated(voice)) = handle.state.as_ref().map(|state| &state.voice) else {
        return 0;
    };
    let airway = voice.airway();
    let [pharynx, oral] = airway.tract_section_counts();
    let (geometry, acoustics) = handle.tract[2..].split_at_mut(3 * (pharynx + oral));
    for (row, cell) in geometry.chunks_exact_mut(3).zip(airway.tract_sections()) {
        row.copy_from_slice(&[cell.length_cm, cell.area_cm2, cell.minimum_area_cm2]);
    }
    for (row, state) in acoustics.chunks_exact_mut(2).zip(airway.tract_acoustics()) {
        row.copy_from_slice(&state);
    }
    1
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_tract_grid_words() -> usize {
    TRACT_GRID_WORDS
}

/// 調音制御の測定線の領域を事前に確保する。先頭は使用行数。
///
/// # Safety
/// ハンドルは生存中で、領域と他の呼び出しへの並行アクセスは行わない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_tract_grid_init(handle: *mut Handle) -> *const f64 {
    let handle = unsafe { &mut *handle };
    if !matches!(
        handle.state.as_ref().map(|state| &state.voice),
        Some(Voice::Articulated(_))
    ) {
        return ptr::null();
    }
    handle.tract_grid.resize(TRACT_GRID_WORDS, 0.0);
    handle.tract_grid.as_ptr()
}

/// 最後に確定した測定線を、出力音声や音響セルと同じレンダー位置で採取する。
///
/// # Safety
/// ハンドルは生存中で、領域と他の呼び出しへの並行アクセスは行わない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_tract_grid_snapshot(handle: *mut Handle) -> u32 {
    let handle = unsafe { &mut *handle };
    if handle.tract_grid.is_empty() || handle.failed {
        return 0;
    }
    let Some(Voice::Articulated(voice)) = handle.state.as_ref().map(|state| &state.voice) else {
        return 0;
    };
    let samples = voice.tract_area_samples();
    if samples.len() > MAX_MEASUREMENT_RAYS {
        return 0;
    }
    handle.tract_grid[0] = samples.len() as f64;
    let words = AreaSample::COLUMN_NAMES.len();
    for (row, sample) in handle.tract_grid[1..].chunks_exact_mut(words).zip(samples) {
        row.copy_from_slice(&sample.measurement_values());
    }
    1
}

/// 呼気目標を変更する。開始前・失敗後・不正な目標は0を返す。
///
/// # Safety
/// ハンドルは生存中で、他の呼び出しと並行させない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_set_gate(handle: *mut Handle, goal: f64) -> u32 {
    let handle = unsafe { &mut *handle };
    if handle.failed {
        return 0;
    }
    match handle.state.as_mut().map(|state| &mut state.voice) {
        Some(Voice::Fixed(voice)) => u32::from(voice.set_performer_gate(goal).is_ok()),
        Some(Voice::Articulated(voice)) => u32::from(voice.set_performer_gate(goal).is_ok()),
        _ => 0,
    }
}

/// 手動発声の基準F0を変更する。音高の平滑化は次の制御更新で行う。
///
/// # Safety
/// ハンドルは生存中で、他の呼び出しと並行させない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_set_manual_pitch(handle: *mut Handle, f0_hz: f64) -> u32 {
    let handle = unsafe { &mut *handle };
    let Some(state) = handle
        .state
        .as_mut()
        .filter(|state| state.manual && !handle.failed)
    else {
        return 0;
    };
    match &mut state.voice {
        Voice::Articulated(voice) => u32::from(voice.set_base_pitch(f0_hz).is_ok()),
        _ => 0,
    }
}

/// 舌体と唇の基準目標をまとめて変更する。
///
/// # Safety
/// ハンドルは生存中で、他の呼び出しと並行させない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_set_manual_targets(
    handle: *mut Handle,
    tongue_x_cm: f64,
    tongue_y_cm: f64,
    lip_aperture_cm: f64,
) -> u32 {
    let handle = unsafe { &mut *handle };
    let values = [tongue_x_cm, tongue_y_cm, lip_aperture_cm];
    if handle.failed || !values.iter().all(|value| value.is_finite()) {
        return 0;
    }
    let Some(Voice::Articulated(voice)) = handle.state.as_mut().map(|state| &mut state.voice)
    else {
        return 0;
    };
    let (bank, _) = voice.control_inputs();
    let axes = [
        Articulator::TongueBodyX,
        Articulator::TongueBodyY,
        Articulator::LipAperture,
    ];
    for (axis, value) in axes.into_iter().zip(values) {
        bank.set_target(axis, value);
    }
    1
}

/// 制御境界で手動発声の体型を変える。成功時は咽頭・口腔のセル数を16ビットずつ返す。
///
/// # Safety
/// ハンドルは生存中で、他の呼び出しと並行させない。声道観測は変更後に再確保する。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_switch_manual_body(
    handle: *mut Handle,
    female: f64,
    child: f64,
) -> u32 {
    let handle = unsafe { &mut *handle };
    let Some(state) = &mut handle.state else {
        return 0;
    };
    if handle.failed
        || !state.manual
        || !state.rendered.is_multiple_of(CONTROL_OUTPUT_FRAMES as u64)
    {
        return 0;
    }
    let Voice::Articulated(voice) = &mut state.voice else {
        return 0;
    };
    if voice
        .switch_manual_body(BodyMix::new(female, child))
        .is_err()
    {
        return 0;
    }
    state.stage.reset();
    handle.tract.clear();
    let [pharynx, oral] = voice.airway().tract_section_counts();
    ((pharynx as u32) << 16) | oral as u32
}

/// 1〜4096フレームを進める。成功は1、入力不正または発声の計算エラーなら0。
///
/// # Safety
/// ハンドルは生存中で、他の呼び出しや領域へのアクセスと並行させない。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_render(handle: *mut Handle, frames: usize) -> u32 {
    let handle = unsafe { &mut *handle };
    if handle.failed || handle.score_preparation.is_some() || !(1..=MAX_FRAMES).contains(&frames) {
        return 0;
    }
    let Some(state) = &mut handle.state else {
        return 0;
    };

    let mut observation = [0.0; OBSERVATION_WORDS];
    let mut glottal_trace = handle.glottal_trace.chunks_exact_mut(GLOTTAL_TRACE_WORDS);
    let mut radiation = handle
        .radiation_trace
        .chunks_exact_mut(RADIATION_TRACE_WORDS);
    #[cfg(all(target_arch = "wasm32", feature = "render-phase-probe"))]
    render_phase_probe::mark(Phase::LoopStart);
    for pcm in &mut handle.pcm[..frames] {
        if let (Some(beat), Voice::Articulated(voice)) = (&mut state.beat, &mut state.voice)
            && beat
                .player
                .prepare_frame(state.rendered, voice, &mut beat.scratch)
                .is_err()
        {
            handle.failed = true;
            return 0;
        }
        let rendered = state.stage.render_frame(|| {
            let sample = state.voice.step()?;
            #[cfg(all(target_arch = "wasm32", feature = "render-phase-probe"))]
            render_phase_probe::next_internal_sample();
            Ok((sample.radiation.radiation_flow_derivative_cm3_s2, sample))
        });
        let Ok((frame, sample)) = rendered else {
            // 内部サンプルの途中まで進んだ可能性があるので、このハンドルでは再開しない。
            handle.failed = true;
            return 0;
        };
        *pcm = frame.pcm;
        state.rendered += 1;
        if let Some(row) = glottal_trace.next() {
            row.copy_from_slice(&[sample.glottis.area_cm2, sample.glottal_flow_cm3_s]);
        }
        if let Some(row) = radiation.next() {
            row.copy_from_slice(&[
                sample.radiation.wall_radiation_flow_cm3_s,
                sample.lip_flow_cm3_s,
                sample.nose_flow_cm3_s,
                sample.radiation.radiation_flow_cm3_s,
                sample.radiation.radiation_flow_derivative_cm3_s2,
            ]);
        }
        observation = [
            state.rendered as f64,
            sample.breath.gate,
            sample.glottis.area_cm2,
            sample.glottal_flow_cm3_s,
            sample.glottis.phase,
            sample.glottis.voicing,
            sample.glottis.f0_hz,
            sample.radiation.radiation_flow_derivative_cm3_s2,
            0.0,
            0.0,
            0.0,
            sample.abduction_cm2,
            0.0,
            0.0,
            0.0,
            sample.nose_flow_cm3_s,
            0.0,
            -1.0,
            0.0,
            0.0,
            -1.0,
            0.0,
            0.0,
        ];
    }
    #[cfg(all(target_arch = "wasm32", feature = "render-phase-probe"))]
    render_phase_probe::mark(Phase::LoopEnd);
    if let Voice::Articulated(voice) = &state.voice {
        let airway = voice.airway();
        let bank = voice.articulators();
        observation[8] = bank.state(Articulator::LipAperture).position;
        observation[9] = airway.network.section(airway.lips).minimum_area_cm2;
        observation[10] = voice.smoothed_pitch_hz();
        observation[12] = bank.state(Articulator::TongueBodyX).position;
        observation[13] = bank.state(Articulator::TongueBodyY).position;
        let oral = &airway.tubes[2].nodes;
        let center = oral.start + oral.len() / 2 - 1;
        observation[14] = airway.network.section(center).minimum_area_cm2;
        observation[16] = airway.network.port_area(airway.velum_port).unwrap_or(0.0);
        observation[19] = airway.frication_geometry().minimum_area_cm2;
        if let Some(teeth) = airway.network.noise_spec(2) {
            observation[20] = teeth.source as f64;
            observation[21] = airway.network.noise_level(2).unwrap_or(0.0);
            observation[22] = airway.network.branch_noise_pressure(teeth.forward);
        }
        if let Some(beat) = &state.beat {
            observation[17] = beat
                .player
                .step_at(voice.clock_seconds())
                .map_or(-1.0, |step| step as f64);
            observation[18] = beat.player.next_step() as f64;
        }
    }
    handle.observation = observation;
    1
}

/// 診断用WASMで、1回のレンダーに内部計時点を付ける。
///
/// # Safety
/// `vocal_render` と同じ条件で呼び出す。
#[cfg(all(target_arch = "wasm32", feature = "render-phase-probe"))]
#[unsafe(no_mangle)]
pub unsafe extern "C" fn vocal_render_traced(handle: *mut Handle, frames: usize) -> u32 {
    render_phase_probe::trace_render(|| unsafe { vocal_render(handle, frames) })
}

impl Handle {
    fn advance_score_preparation(&mut self, frames: usize) -> Result<(), &'static str> {
        let Some(pending) = &mut self.score_preparation else {
            return Err("進める予備描画がありません");
        };
        let Some(RenderState {
            voice: Voice::Articulated(voice),
            stage,
            ..
        }) = &mut self.state
        else {
            return Err("予備描画用の声道がありません");
        };
        let frames = frames.min(pending.remaining);
        for _ in 0..frames {
            stage.render_frame(|| {
                voice
                    .step()
                    .map(|sample| (sample.radiation.radiation_flow_derivative_cm3_s2, ()))
            })?;
        }
        pending.remaining -= frames;
        if pending.remaining == 0 {
            let pending = self.score_preparation.take().unwrap();
            schedule_prepared_score(voice, pending.gestures)?;
        }
        Ok(())
    }

    fn configured(&self) -> Result<(Articulation, FixedVoiceSettings, OutputStage), &'static str> {
        let (axes, source) = self.config.split_at(ARTICULATOR_COUNT);
        let &[pressure_cm_h2o, gate, f0_hz, breathiness, tension, gain] = source else {
            unreachable!("初期設定のレイアウト");
        };
        if !self.config.iter().all(|v| v.is_finite()) {
            return Err("初期姿勢と音源には有限値を指定してください");
        }
        // 固定音源の初期化が過大なフィルタや声道を確保しないようにする。
        if self.internal_rate > 384_000 || self.output_rate < 8_000 {
            return Err("固定発声のレートは出力8 kHz以上、内部384 kHz以下で指定してください");
        }
        let stage = OutputStage::new(self.internal_rate, self.output_rate, gain)?;
        let posture = Articulation::from_axis_values(axes.try_into().expect("調音軸の型"));
        Ok((
            posture,
            FixedVoiceSettings {
                pressure_cm_h2o,
                gate,
                f0_hz,
                breathiness,
                tension,
            },
            stage,
        ))
    }

    fn build(&self) -> Result<RenderState, &'static str> {
        let (posture, source, stage) = self.configured()?;
        let model = SagittalModel::adult_male();
        let frame = model.compute(posture);
        let airway = HumanAirway::fixed_from_profile(
            self.internal_rate,
            &model.area_profile(&frame)?,
            frame.velum_port_cm2,
        )?;
        let voice = FixedVoice::new(
            airway,
            self.internal_rate,
            CONTROL_OUTPUT_FRAMES * stage.factor(),
            source,
        )?;
        Ok(RenderState {
            voice: Voice::Fixed(Box::new(voice)),
            stage,
            rendered: 0,
            beat: None,
            song: None,
            manual: false,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        alloc::{GlobalAlloc, Layout, System},
        cell::Cell,
    };

    #[cfg(all(not(target_arch = "wasm32"), feature = "render-allocation-probe"))]
    mod speech_allocation;

    struct CountingAllocator;

    thread_local! {
        pub(super) static ALLOCATIONS: Cell<usize> = const { Cell::new(0) };
    }

    #[global_allocator]
    static ALLOCATOR: CountingAllocator = CountingAllocator;

    unsafe impl GlobalAlloc for CountingAllocator {
        unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
            let _ = ALLOCATIONS.try_with(|count| count.set(count.get() + 1));
            unsafe { System.alloc(layout) }
        }

        unsafe fn realloc(&self, p: *mut u8, layout: Layout, size: usize) -> *mut u8 {
            let _ = ALLOCATIONS.try_with(|count| count.set(count.get() + 1));
            unsafe { System.realloc(p, layout, size) }
        }

        unsafe fn dealloc(&self, p: *mut u8, layout: Layout) {
            unsafe { System.dealloc(p, layout) }
        }
    }

    #[test]
    fn score_preparation_keeps_the_same_state_through_partial_last_block() {
        use vocal_core::score::ControlKey;

        let input =
            serde_json::from_str(include_str!("../../../cases/vowel-voice-i.json")).unwrap();
        let mut config = fixture_config(&input, 110.0);
        config[ARTICULATOR_COUNT + 1] = 0.0;
        let mut row = [f64::NAN; planning::SCORE_WORDS];
        row[..5].copy_from_slice(&[0.0, 0.5, 0.02, 0.01, 1.0]);
        row[7 + ControlKey::Breath.index()] = 1.0;
        row[7 + ControlKey::F0.index()] = 160.0;
        // 両ハンドルの設定と調音スコアを同じABIで書き込む。
        unsafe {
            for warm_up_frames in [0, 257] {
                let bulk = vocal_new(96_000, 48_000);
                let split = vocal_new(96_000, 48_000);
                for handle in [bulk, split] {
                    std::slice::from_raw_parts_mut(vocal_config(handle), CONFIG_WORDS)
                        .copy_from_slice(&config);
                    std::slice::from_raw_parts_mut(
                        vocal_score_buffer(handle, row.len()),
                        row.len(),
                    )
                    .copy_from_slice(&row);
                }
                assert_eq!(
                    vocal_start_score_prepared(
                        bulk,
                        1.0,
                        110.0,
                        0.0,
                        0.0,
                        1.0,
                        1.0,
                        1200.0,
                        warm_up_frames,
                        5.0,
                        0.00455,
                        0.042
                    ),
                    1
                );
                assert_eq!(
                    vocal_start_score_preparation(
                        split,
                        1.0,
                        110.0,
                        0.0,
                        0.0,
                        1.0,
                        1.0,
                        1200.0,
                        warm_up_frames,
                        5.0,
                        0.00455,
                        0.042
                    ),
                    1
                );
                if warm_up_frames > 0 {
                    assert_eq!(vocal_advance_score_preparation(split, 0), 0);
                    assert_eq!(vocal_advance_score_preparation(split, MAX_FRAMES + 1), 0);
                    for _ in (0..warm_up_frames).step_by(128) {
                        assert_eq!(vocal_render(split, 128), 0);
                        assert_eq!(vocal_advance_score_preparation(split, 128), 1);
                    }
                }
                assert_eq!(vocal_advance_score_preparation(split, 128), 0);
                for block in 1..=2 {
                    for handle in [bulk, split] {
                        assert_eq!(vocal_render(handle, MAX_FRAMES), 1);
                        assert_eq!(*vocal_observation(handle), (block * MAX_FRAMES) as f64);
                    }
                    let a = std::slice::from_raw_parts(vocal_pcm(bulk), MAX_FRAMES);
                    let b = std::slice::from_raw_parts(vocal_pcm(split), MAX_FRAMES);
                    assert!(a.iter().zip(b).all(|(a, b)| a.to_bits() == b.to_bits()));
                }
                vocal_free(split);
                vocal_free(bulk);
            }
        }
    }

    #[test]
    fn fixed_voice_render_does_not_allocate() {
        let handle = vocal_new(96_000, 48_000);
        // ハンドルを単一スレッドで所有し、設定領域の長さをABIに合わせる。
        unsafe {
            assert_eq!(vocal_render(handle, 1), 0);
            assert_eq!(vocal_start(handle), 0);
            let config = std::slice::from_raw_parts_mut(vocal_config(handle), CONFIG_WORDS);
            config.copy_from_slice(&[
                0.413, 3.683, 7.739, 6.545, 7.288, 0.0, 0.514, 1.046, 0.0, 1.0, 0.0, -0.15, 0.798,
                0.0, 0.0, 0.0, 0.0, 7.2, 1.0, 110.0, 0.15, 0.5, 5.5e-7,
            ]);
            assert_eq!(vocal_start(handle), 1);
            assert_eq!(vocal_start(handle), 0);
            let pcm = vocal_pcm(handle);
            let observation = vocal_observation(handle);
            let before = ALLOCATIONS.with(Cell::get);
            for _ in 0..1000 {
                assert_eq!(vocal_render(handle, 0), 0);
            }
            assert_eq!(*observation, 0.0);
            assert_eq!(vocal_render(handle, MAX_FRAMES + 1), 0);
            assert_eq!(vocal_set_gate(handle, f64::NAN), 0);
            let mut rendered = 0;
            for (block, gate) in [(128, 1.0), (77, 0.0), (MAX_FRAMES, 0.6), (1, 0.0)] {
                assert_eq!(vocal_set_gate(handle, gate), 1);
                assert_eq!(vocal_render(handle, block), 1);
                rendered += block;
                assert_eq!(vocal_pcm(handle), pcm);
                assert_eq!(vocal_observation(handle), observation);
                assert_eq!(*observation, rendered as f64);
            }
            let count = ALLOCATIONS.with(Cell::get) - before;
            eprintln!("レンダー中の割り当て: {count}");
            assert_eq!(count, 0);
            vocal_free(handle);
        }
    }

    #[test]
    fn fixed_voice_radiation_trace_does_not_allocate() {
        let handle = vocal_new(96_000, 48_000);
        // 試験が単独で所有するハンドルの構成領域と、直近の描画だけを参照する。
        unsafe {
            let config = std::slice::from_raw_parts_mut(vocal_config(handle), CONFIG_WORDS);
            config.copy_from_slice(&[
                0.413, 3.683, 7.739, 6.545, 7.288, 0.0, 0.514, 1.046, 0.0, 1.0, 0.0, -0.15, 0.798,
                0.0, 0.0, 0.0, 0.0, 3.6, 1.0, 110.0, 0.15, 0.5, 5.5e-7,
            ]);
            assert_eq!(vocal_start(handle), 1);
            let trace = vocal_radiation_trace_init(handle);
            let observation = vocal_observation(handle);
            let before = ALLOCATIONS.with(Cell::get);
            for frames in [128, 77, MAX_FRAMES, 1] {
                assert_eq!(vocal_render(handle, frames), 1);
                let rows = std::slice::from_raw_parts(trace, frames * RADIATION_TRACE_WORDS);
                for row in rows.chunks_exact(RADIATION_TRACE_WORDS) {
                    assert!(row.iter().all(|value| value.is_finite()));
                    assert_eq!(((row[0] + row[1]) + row[2]).to_bits(), row[3].to_bits());
                }
                let row = &rows[rows.len() - RADIATION_TRACE_WORDS..];
                assert_eq!(row[2].to_bits(), (*observation.add(15)).to_bits());
                assert_eq!(row[4].to_bits(), (*observation.add(7)).to_bits());
            }
            let count = ALLOCATIONS.with(Cell::get) - before;
            assert_eq!(vocal_layout_version(), 1);
            assert_eq!(OBSERVATION_WORDS, 23);
            println!("vocal_legacy_observation_words: {OBSERVATION_WORDS}");
            println!("放射観測付きレンダー中の割り当て: {count}");
            assert_eq!(count, 0);
            vocal_free(handle);
        }
    }

    #[test]
    fn songbird_sustain_render_does_not_allocate() {
        use crate::songbird::*;
        for rate in [48_000, 96_000] {
            let handle =
                vocal_songbird_new(rate, 1.0, 2600.0, 7.0, 0.5, 0.35, 0.4, 0.9, 0.8, 0.4, 0.55);
            assert!(!handle.is_null());
            // このテストが作成したハンドルを排他的に所有する。
            unsafe {
                let pcm = vocal_songbird_pcm(handle);
                let observation = vocal_songbird_observation(handle);
                let before = ALLOCATIONS.with(Cell::get);
                assert_eq!(vocal_songbird_render(handle, 0), 0);
                assert_eq!(vocal_songbird_render(handle, 129), 0);
                assert_eq!(vocal_songbird_set_gate(handle, f64::NAN), 0);
                for gate in [0.0, 1.0, 0.0] {
                    assert_eq!(vocal_songbird_set_gate(handle, gate), 1);
                    for _ in 0..24 {
                        for len in [77, 128, 1] {
                            assert_eq!(vocal_songbird_render(handle, len), 1);
                            assert_eq!(vocal_songbird_pcm(handle), pcm);
                            assert_eq!(vocal_songbird_observation(handle), observation);
                            assert!(
                                std::slice::from_raw_parts(pcm, len)
                                    .iter()
                                    .all(|x| x.is_finite())
                            );
                            assert!(
                                std::slice::from_raw_parts(observation, OBSERVATION_WORDS)
                                    .iter()
                                    .all(|x| x.is_finite())
                            );
                        }
                    }
                }
                let allocations = ALLOCATIONS.with(Cell::get) - before;
                vocal_songbird_free(handle);
                eprintln!("songbird_render_allocations_{rate}={allocations}");
                assert_eq!(allocations, 0);
            }
        }
    }

    #[test]
    fn alligator_fixed_render_does_not_allocate() {
        use crate::alligator::*;

        let handle = vocal_alligator_new(48_000, 1.0, 28.0, 0.75, 18.0, 0.02, 0.8, 0.0);
        assert!(!handle.is_null());
        // 試験中はハンドルを排他的に使用する。
        unsafe {
            let pcm = vocal_alligator_pcm(handle);
            let observation = vocal_alligator_observation(handle);
            let before = ALLOCATIONS.with(Cell::get);
            for (gate, frames) in [(1.0, 57_600), (0.0, 19_200)] {
                assert_eq!(vocal_alligator_set_gate(handle, gate), 1);
                for start in (0..frames).step_by(128) {
                    assert_eq!(vocal_alligator_render(handle, (frames - start).min(128)), 1);
                }
            }
            assert_eq!(vocal_alligator_pcm(handle), pcm);
            assert_eq!(vocal_alligator_observation(handle), observation);
            let count = ALLOCATIONS.with(Cell::get) - before;
            vocal_alligator_free(handle);
            eprintln!("alligator_render_allocations_48000={count}");
            assert_eq!(count, 0);
        }
    }

    #[test]
    fn alligator_bellow_render_does_not_allocate() {
        use crate::alligator::*;

        let handle = vocal_alligator_new(44_100, 1.0, 28.0, 0.75, 18.0, 0.22, 0.8, 0.35);
        assert!(!handle.is_null());
        // 試験中はこのハンドルを排他的に使用する。
        unsafe {
            let observation = vocal_alligator_observation(handle);
            let before = ALLOCATIONS.with(Cell::get);
            let render = |count: usize| {
                for start in (0..count).step_by(128) {
                    assert_eq!(vocal_alligator_render(handle, (count - start).min(128)), 1);
                }
            };
            render(73);
            assert_eq!(vocal_alligator_play_call(handle, 1, 42.0, 0.6), 1);
            render(832 - 73);
            let before_oral_noise = ALLOCATIONS.with(Cell::get);
            render(1);
            let oral_noise_allocations = ALLOCATIONS.with(Cell::get) - before_oral_noise;
            render(9901 - 833);
            assert_eq!(
                vocal_alligator_set_params(handle, 34.0, 0.2, 22.0, 0.35, 0.25, 0.4),
                1
            );
            render(11009 - 9901);
            assert_eq!(vocal_alligator_set_gate(handle, 0.72), 1);
            render(53107 - 11009);
            assert_eq!(vocal_alligator_stop_call(handle), 1);
            render(54000 - 53107);
            assert_eq!(vocal_alligator_set_gate(handle, 0.0), 1);
            render(65_000 - 54000);
            assert_eq!(vocal_alligator_observation(handle), observation);
            let count = ALLOCATIONS.with(Cell::get) - before;
            vocal_alligator_free(handle);
            eprintln!("alligator_oral_noise_switch_allocations_44100={oral_noise_allocations}");
            eprintln!("alligator_render_allocations_44100={count}");
            assert_eq!(count, 0);
        }
    }

    #[test]
    fn alligator_growl_switch_does_not_allocate() {
        use crate::alligator::*;

        let handle = vocal_alligator_new(44_100, 1.0, 28.0, 0.75, 18.0, 0.02, 0.8, 0.0);
        assert!(!handle.is_null());
        // ブラウザの切り替えケースと同じフレームでコールと手動目標を更新する。
        unsafe {
            let observation = vocal_alligator_observation(handle);
            let before = ALLOCATIONS.with(Cell::get);
            let render = |count: usize| {
                for start in (0..count).step_by(128) {
                    assert_eq!(vocal_alligator_render(handle, (count - start).min(128)), 1);
                }
            };
            render(73);
            assert_eq!(vocal_alligator_play_call(handle, 1, f64::NAN, 1.0), 1);
            render(12_001 - 73);
            assert_eq!(
                vocal_alligator_set_params(handle, 31.0, 0.22, f64::NAN, 0.34, f64::NAN, 0.62),
                1
            );
            render(23_617 - 12_001);
            assert_eq!(vocal_alligator_play_call(handle, 2, 70.0, 0.6), 1);
            render(27_137 - 23_617);
            assert_eq!(
                vocal_alligator_set_params(handle, 32.0, 0.27, 24.0, 0.26, f64::NAN, 0.05),
                1
            );
            render(65_000 - 27_137);
            assert_eq!(vocal_alligator_observation(handle), observation);
            let count = ALLOCATIONS.with(Cell::get) - before;
            vocal_alligator_free(handle);
            eprintln!("alligator_render_allocations_44100={count}");
            assert_eq!(count, 0);
        }
    }

    #[test]
    fn alligator_hiss_noise_switches_do_not_allocate() {
        use crate::alligator::*;

        let handle = vocal_alligator_new(96_000, 1.0, 28.0, 0.75, 18.0, 0.02, 0.8, 0.0);
        assert!(!handle.is_null());
        // 気道と観測用バッファを、口腔乱流源の解除と再登録をまたいで使う。
        unsafe {
            let observation = vocal_alligator_observation(handle);
            let before = ALLOCATIONS.with(Cell::get);
            assert_eq!(vocal_alligator_render(handle, 17), 1);
            assert_eq!(vocal_alligator_play_call(handle, 3, f64::NAN, 1.0), 1);
            let mut frame = 17;
            for (end, oral_noise) in [
                (896, 1.0),
                (897, 0.0),
                (109_440, 0.0),
                (109_441, 1.0),
                (140_800, 1.0),
            ] {
                while frame < end {
                    let len = (end - frame).min(128);
                    assert_eq!(vocal_alligator_render(handle, len), 1);
                    frame += len;
                }
                assert_eq!(vocal_alligator_observation(handle), observation);
                assert_eq!(*observation.add(2), oral_noise);
            }
            let count = ALLOCATIONS.with(Cell::get) - before;
            vocal_alligator_free(handle);
            eprintln!("alligator_render_allocations_96000={count}");
            assert_eq!(count, 0);
        }
    }

    #[test]
    fn alligator_dance_render_does_not_allocate() {
        use crate::alligator::*;

        let handle = vocal_alligator_new(96_000, 1.0, 18.0, 0.0, 18.0, 0.0, 0.8, 0.0);
        assert!(!handle.is_null());
        // コール開始から自然終了後まで同じハンドルで描画する。
        unsafe {
            let observation = vocal_alligator_observation(handle);
            let before = ALLOCATIONS.with(Cell::get);
            assert_eq!(vocal_alligator_render(handle, 17), 1);
            assert_eq!(vocal_alligator_play_call(handle, 4, f64::NAN, 1.0), 1);
            for start in (17..181_000).step_by(128) {
                assert_eq!(
                    vocal_alligator_render(handle, (181_000 - start).min(128)),
                    1
                );
            }
            assert_eq!(vocal_alligator_observation(handle), observation);
            let count = ALLOCATIONS.with(Cell::get) - before;
            vocal_alligator_free(handle);
            eprintln!("alligator_render_allocations_96000={count}");
            assert_eq!(count, 0);
        }
    }

    #[test]
    fn elephant_fixed_render_does_not_allocate() {
        use crate::elephant::*;

        for (rate, start, change, end) in [
            (44_100, 17, Some(22_051), 52_000),
            (96_000, 0, None, 57_600),
        ] {
            let handle = vocal_elephant_new(rate, 1.0, 14.0, 16.0, 0.0, 0.2, 0.0, 470.0);
            assert!(!handle.is_null());
            // 音の立ち上がりと経路変更で同じ描画バッファを使う。
            unsafe {
                let pcm = vocal_elephant_pcm(handle);
                let observation = vocal_elephant_observation(handle);
                let before = ALLOCATIONS.with(Cell::get);
                let render = |frames: usize| {
                    for offset in (0..frames).step_by(128) {
                        assert_eq!(vocal_elephant_render(handle, (frames - offset).min(128)), 1);
                    }
                };
                render(start);
                assert_eq!(vocal_elephant_set_gate(handle, 1.0), 1);
                let boundary = change.unwrap_or(end);
                render(boundary - start);
                if change.is_some() {
                    assert_eq!(
                        vocal_elephant_set_params(
                            handle,
                            f64::NAN,
                            f64::NAN,
                            1.0,
                            f64::NAN,
                            f64::NAN,
                            f64::NAN
                        ),
                        1
                    );
                }
                render(end - boundary);
                assert_eq!(vocal_elephant_pcm(handle), pcm);
                assert_eq!(vocal_elephant_observation(handle), observation);
                let count = ALLOCATIONS.with(Cell::get) - before;
                vocal_elephant_free(handle);
                eprintln!("elephant_render_allocations_{rate}={count}");
                assert_eq!(count, 0);
            }
        }
    }

    #[test]
    fn elephant_rumble_render_does_not_allocate() {
        use crate::elephant::*;

        let handle = vocal_elephant_new(44_100, 1.0, 19.0, 16.0, 0.05, 0.2, 0.0, 470.0);
        assert!(!handle.is_null());
        // 始動、編集、ゲートの切り替え、停止で観測用メモリを使い続ける。
        unsafe {
            let observation = vocal_elephant_observation(handle);
            let before = ALLOCATIONS.with(Cell::get);
            let render = |frames: usize| {
                for offset in (0..frames).step_by(128) {
                    assert_eq!(vocal_elephant_render(handle, (frames - offset).min(128)), 1);
                }
            };
            render(173);
            assert_eq!(vocal_elephant_play_call(handle, 1, 22.0, 0.8), 1);
            render(30_013 - 173);
            assert_eq!(
                vocal_elephant_set_params(handle, 31.0, 22.0, 0.2, 0.6, f64::NAN, f64::NAN),
                1
            );
            render(40_019 - 30_013);
            assert_eq!(vocal_elephant_set_gate(handle, 0.95), 1);
            render(54_813 - 40_019);
            assert_eq!(vocal_elephant_set_gate(handle, 0.0), 1);
            render(61_913 - 54_813);
            assert_eq!(vocal_elephant_stop_call(handle), 1);
            render(76_000 - 61_913);
            assert_eq!(vocal_elephant_observation(handle), observation);
            let count = ALLOCATIONS.with(Cell::get) - before;
            vocal_elephant_free(handle);
            eprintln!("elephant_render_allocations_44100={count}");
            assert_eq!(count, 0);
        }
    }

    #[test]
    fn elephant_trumpet_render_does_not_allocate() {
        use crate::elephant::*;

        let handle = vocal_elephant_new(44_100, 1.0, 20.0, 20.0, 0.35, 0.2, 0.15, 610.0);
        assert!(!handle.is_null());
        // 置き換えと弁の編集・停止でPCMと観測のバッファを再利用する。
        unsafe {
            let pcm = vocal_elephant_pcm(handle);
            let observation = vocal_elephant_observation(handle);
            let before = ALLOCATIONS.with(Cell::get);
            let render = |start: usize, end: usize| {
                for frame in (start..end).step_by(128) {
                    assert_eq!(vocal_elephant_render(handle, (end - frame).min(128)), 1);
                }
            };
            let absent = f64::NAN;
            render(0, 173);
            assert_eq!(vocal_elephant_play_call(handle, 1, absent, 1.0), 1);
            render(173, 42_013);
            assert_eq!(
                vocal_elephant_set_params(handle, 31.0, absent, 0.55, absent, absent, absent),
                1
            );
            render(42_013, 48_021);
            assert_eq!(vocal_elephant_play_call(handle, 2, absent, 0.75), 1);
            render(48_021, 62_317);
            assert_eq!(
                vocal_elephant_set_params(handle, 24.0, 21.0, 0.7, 0.25, 0.4, 655.0),
                1
            );
            render(62_317, 86_011);
            assert_eq!(vocal_elephant_stop_call(handle), 1);
            render(86_011, 98_000);
            assert_eq!(vocal_elephant_pcm(handle), pcm);
            assert_eq!(vocal_elephant_observation(handle), observation);
            let count = ALLOCATIONS.with(Cell::get) - before;
            vocal_elephant_free(handle);
            eprintln!("elephant_render_allocations_44100={count}");
            assert_eq!(count, 0);
        }
    }

    #[test]
    fn elephant_squeak_render_does_not_allocate() {
        use crate::elephant::*;

        let handle = vocal_elephant_new(44_100, 1.0, 20.0, 18.0, 0.35, 0.2, 0.15, 580.0);
        assert!(!handle.is_null());
        // trumpetで保持した目標を解除し、squeakの途中停止まで同じ領域で描画する。
        unsafe {
            let pcm = vocal_elephant_pcm(handle);
            let observation = vocal_elephant_observation(handle);
            let before = ALLOCATIONS.with(Cell::get);
            let render = |start: usize, end: usize| {
                for frame in (start..end).step_by(128) {
                    assert_eq!(vocal_elephant_render(handle, (end - frame).min(128)), 1);
                }
            };
            let absent = f64::NAN;
            render(0, 173);
            assert_eq!(vocal_elephant_play_call(handle, 2, absent, 1.0), 1);
            render(173, 15_119);
            assert_eq!(
                vocal_elephant_set_params(handle, absent, 19.0, absent, 0.68, 0.2, 600.0),
                1
            );
            render(15_119, 19_917);
            assert_eq!(vocal_elephant_play_call(handle, 3, absent, 0.65), 1);
            render(19_917, 25_123);
            assert_eq!(
                vocal_elephant_set_params(handle, 25.0, 23.0, 0.7, 0.25, 0.45, 640.0),
                1
            );
            render(25_123, 35_011);
            assert_eq!(vocal_elephant_stop_call(handle), 1);
            render(35_011, 46_000);
            assert_eq!(vocal_elephant_pcm(handle), pcm);
            assert_eq!(vocal_elephant_observation(handle), observation);
            let count = ALLOCATIONS.with(Cell::get) - before;
            vocal_elephant_free(handle);
            eprintln!("elephant_render_allocations_44100={count}");
            assert_eq!(count, 0);
        }
    }

    #[test]
    fn seal_sustain_render_does_not_allocate() {
        use crate::seal::*;

        for (rate, warmup, held, tail) in
            [(48_000, 0, 57_600, 19_200), (96_000, 145, 15_856, 41_599)]
        {
            let handle = vocal_seal_new(rate, 1.0, 18.0, 0.6, 0.55, 10.0, 900.0, 0.6, 0.05, 0.35);
            assert!(!handle.is_null());
            // 試験中はこのハンドルを排他的に使用する。
            unsafe {
                let pcm = vocal_seal_pcm(handle);
                let observation = vocal_seal_observation(handle);
                let before = ALLOCATIONS.with(Cell::get);
                for (gate, count) in [(0.0, warmup), (1.0, held), (0.0, tail)] {
                    assert_eq!(vocal_seal_set_gate(handle, gate), 1);
                    for start in (0..count).step_by(128) {
                        assert_eq!(vocal_seal_render(handle, (count - start).min(128)), 1);
                    }
                }
                assert_eq!(vocal_seal_pcm(handle), pcm);
                assert_eq!(vocal_seal_observation(handle), observation);
                assert_eq!(
                    vocal_seal_factor(handle),
                    if rate <= 60_000 { 2 } else { 1 }
                );
                let allocations = ALLOCATIONS.with(Cell::get) - before;
                vocal_seal_free(handle);
                eprintln!("seal_render_allocations_{rate}={allocations}");
                assert_eq!(allocations, 0);
            }
        }
    }

    #[test]
    fn seal_trill_render_does_not_allocate() {
        use crate::seal::*;

        let handle = vocal_seal_new(44_100, 1.0, 18.0, 0.6, 0.55, 10.0, 900.0, 0.6, 0.05, 0.35);
        assert!(!handle.is_null());
        // 試験中はこのハンドルを排他的に使用する。
        unsafe {
            let pcm = vocal_seal_pcm(handle);
            let observation = vocal_seal_observation(handle);
            let before = ALLOCATIONS.with(Cell::get);
            let render = |count: usize| {
                for start in (0..count).step_by(128) {
                    assert_eq!(vocal_seal_render(handle, (count - start).min(128)), 1);
                }
            };
            assert_eq!(vocal_seal_set_gate(handle, 0.35), 1);
            render(73);
            assert_eq!(vocal_seal_play_call(handle, 1, 1800.0, 0.6), 1);
            render(8401 - 73);
            assert_eq!(vocal_seal_set_pitch(handle, 1250.0), 1);
            render(10731 - 8401);
            assert_eq!(vocal_seal_set_breath(handle, 27.0, 0.2, 0.65, 14.0), 1);
            render(11223 - 10731);
            assert_eq!(vocal_seal_set_gate(handle, 0.8), 1);
            render(18327 - 11223);
            assert_eq!(vocal_seal_set_gate(handle, 0.35), 1);
            render(23221 - 18327);
            assert_eq!(vocal_seal_stop_call(handle), 1);
            render(50_000 - 23221);
            assert_eq!(vocal_seal_pcm(handle), pcm);
            assert_eq!(vocal_seal_observation(handle), observation);
            let allocations = ALLOCATIONS.with(Cell::get) - before;
            vocal_seal_free(handle);
            eprintln!("seal_render_allocations_44100={allocations}");
            assert_eq!(allocations, 0);
        }
    }

    #[test]
    fn seal_zap_switch_does_not_allocate() {
        use crate::seal::*;

        let handle = vocal_seal_new(44_100, 1.0, 18.0, 0.6, 0.55, 10.0, 900.0, 0.6, 0.05, 0.35);
        assert!(!handle.is_null());
        // 試験中はこのハンドルを排他的に使用する。
        unsafe {
            let pcm = vocal_seal_pcm(handle);
            let observation = vocal_seal_observation(handle);
            let before = ALLOCATIONS.with(Cell::get);
            let render = |count: usize| {
                for start in (0..count).step_by(128) {
                    assert_eq!(vocal_seal_render(handle, (count - start).min(128)), 1);
                }
            };
            assert_eq!(vocal_seal_set_gate(handle, 0.25), 1);
            render(73);
            assert_eq!(vocal_seal_play_call(handle, 1, f64::NAN, 0.9), 1);
            render(7101 - 73);
            assert_eq!(vocal_seal_set_breath(handle, 27.0, 0.25, 0.65, 14.0), 1);
            render(7117 - 7101);
            assert_eq!(vocal_seal_set_pitch(handle, 1200.0), 1);
            render(8301 - 7117);
            assert_eq!(vocal_seal_play_call(handle, 2, 4200.0, 0.65), 1);
            render(9437 - 8301);
            assert_eq!(vocal_seal_set_breath(handle, 31.0, 0.45, 0.72, 16.0), 1);
            render(28_000 - 9437);
            assert_eq!(vocal_seal_pcm(handle), pcm);
            assert_eq!(vocal_seal_observation(handle), observation);
            let allocations = ALLOCATIONS.with(Cell::get) - before;
            vocal_seal_free(handle);
            eprintln!("seal_render_allocations_44100={allocations}");
            assert_eq!(allocations, 0);
        }
    }

    #[test]
    fn seal_whistle_render_does_not_allocate() {
        use crate::seal::*;

        let handle = vocal_seal_new(44_100, 1.0, 18.0, 0.6, 0.55, 10.0, 900.0, 0.6, 0.05, 0.35);
        assert!(!handle.is_null());
        // 試験中はこのハンドルを排他的に使用する。
        unsafe {
            let pcm = vocal_seal_pcm(handle);
            let observation = vocal_seal_observation(handle);
            let before = ALLOCATIONS.with(Cell::get);
            let render = |count: usize| {
                for start in (0..count).step_by(128) {
                    assert_eq!(vocal_seal_render(handle, (count - start).min(128)), 1);
                }
            };
            assert_eq!(vocal_seal_set_gate(handle, 0.25), 1);
            render(73);
            assert_eq!(vocal_seal_play_call(handle, 3, 850.0, 0.8), 1);
            render(20_003 - 73);
            assert_eq!(vocal_seal_set_breath(handle, 24.0, 0.42, 0.7, 12.0), 1);
            assert_eq!(vocal_seal_set_pitch(handle, 1250.0), 1);
            render(56_000 - 20_003);
            assert_eq!(vocal_seal_pcm(handle), pcm);
            assert_eq!(vocal_seal_observation(handle), observation);
            let allocations = ALLOCATIONS.with(Cell::get) - before;
            vocal_seal_free(handle);
            eprintln!("seal_render_allocations_44100={allocations}");
            assert_eq!(allocations, 0);
        }
    }

    #[test]
    fn seal_chug_render_does_not_allocate() {
        use crate::seal::*;

        let handle = vocal_seal_new(44_100, 1.0, 18.0, 0.6, 0.55, 10.0, 900.0, 0.6, 0.05, 0.35);
        assert!(!handle.is_null());
        // 試験中はこのハンドルを排他的に使用する。
        unsafe {
            let observation = vocal_seal_observation(handle);
            let before = ALLOCATIONS.with(Cell::get);
            let render = |count: usize| {
                for start in (0..count).step_by(128) {
                    assert_eq!(vocal_seal_render(handle, (count - start).min(128)), 1);
                }
            };
            assert_eq!(vocal_seal_set_gate(handle, 0.25), 1);
            render(73);
            assert_eq!(vocal_seal_play_call(handle, 4, 120.0, 0.8), 1);
            render(9_891 - 73);
            assert_eq!(vocal_seal_set_breath(handle, 22.0, 0.35, 0.6, 12.0), 1);
            assert_eq!(vocal_seal_set_roughness(handle, 0.5), 1);
            render(53_000 - 9_891);
            assert_eq!(vocal_seal_observation(handle), observation);
            let allocations = ALLOCATIONS.with(Cell::get) - before;
            vocal_seal_free(handle);
            eprintln!("seal_render_allocations_44100={allocations}");
            assert_eq!(allocations, 0);
        }
    }

    #[test]
    fn songbird_call_render_does_not_allocate() {
        use crate::songbird::*;
        let handle = vocal_songbird_new(
            48_000, 1.0, 2600.0, 7.0, 0.5, 0.35, 0.4, 0.9, 0.8, 0.4, 0.55,
        );
        let chirps = vocal_songbird_new(
            44_100, 1.0, 2600.0, 7.0, 0.5, 0.35, 0.4, 0.9, 0.8, 0.4, 0.55,
        );
        let buzz = vocal_songbird_new(
            96_000, 1.0, 2600.0, 7.0, 0.5, 0.35, 0.4, 0.9, 0.8, 0.4, 0.55,
        );
        assert!(!handle.is_null() && !chirps.is_null() && !buzz.is_null());
        // このテストが初期化したハンドルを排他的に所有する。
        unsafe {
            let pcm = vocal_songbird_pcm(handle);
            let observation = vocal_songbird_observation(handle);
            let before = ALLOCATIONS.with(Cell::get);
            assert_eq!(vocal_songbird_play_call(handle, 0, f64::NAN, 1.0), 0);
            assert_eq!(vocal_songbird_render(handle, 73), 1);
            assert_eq!(vocal_songbird_play_call(handle, 1, 3380.0, 0.8), 1);
            assert_eq!(vocal_songbird_render(handle, 55), 1);
            for _ in 0..42 {
                assert_eq!(vocal_songbird_render(handle, 128), 1);
            }
            assert_eq!(
                vocal_songbird_set_controls(
                    handle, 3000.0, 2.0, 0.8, 0.4, 0.45, 1.1, 0.65, 0.5, 0.35
                ),
                1
            );
            assert_eq!(vocal_songbird_set_gate(handle, 0.35), 1);
            assert_eq!(vocal_songbird_render(handle, 77), 1);
            assert_eq!(vocal_songbird_stop_call(handle), 1);
            assert_eq!(vocal_songbird_render(handle, 128), 1);
            // buzz の再生中に手動値を受け取り、そのまま trill に切り替える。
            assert_eq!(vocal_songbird_set_gate(handle, 0.0), 1);
            assert_eq!(vocal_songbird_play_call(handle, 4, f64::NAN, 1.0), 1);
            assert_eq!(vocal_songbird_render(handle, 77), 1);
            assert_eq!(
                vocal_songbird_set_controls(
                    handle, 3100.0, -4.0, 0.75, 0.42, 0.65, 1.05, 0.7, 0.5, 0.45
                ),
                1
            );
            assert_eq!(vocal_songbird_play_call(handle, 2, f64::NAN, 1.0), 1);
            for _ in 0..600 {
                assert_eq!(vocal_songbird_render(handle, 128), 1);
            }
            // chirps の開始211、自然終了、末尾まで44.1 kHzで測る。
            assert_eq!(vocal_songbird_render(chirps, 128), 1);
            assert_eq!(vocal_songbird_render(chirps, 83), 1);
            assert_eq!(vocal_songbird_play_call(chirps, 3, f64::NAN, 1.0), 1);
            for _ in 0..377 {
                assert_eq!(vocal_songbird_render(chirps, 128), 1);
            }
            assert_eq!(vocal_songbird_render(chirps, 43), 1);
            // buzz の開始147と自然終了を96 kHzで通す。
            assert_eq!(vocal_songbird_render(buzz, 128), 1);
            assert_eq!(vocal_songbird_render(buzz, 19), 1);
            assert_eq!(vocal_songbird_play_call(buzz, 4, 1500.0, 0.8), 1);
            for _ in 0..823 {
                assert_eq!(vocal_songbird_render(buzz, 128), 1);
            }
            assert_eq!(vocal_songbird_render(buzz, 109), 1);
            assert_eq!(vocal_songbird_pcm(handle), pcm);
            assert_eq!(vocal_songbird_observation(handle), observation);
            assert!(
                std::slice::from_raw_parts(observation, OBSERVATION_WORDS)
                    .iter()
                    .all(|x| x.is_finite())
            );
            let allocations = ALLOCATIONS.with(Cell::get) - before;
            vocal_songbird_free(handle);
            vocal_songbird_free(chirps);
            vocal_songbird_free(buzz);
            eprintln!("songbird_call_render_allocations={allocations}");
            assert_eq!(allocations, 0);
        }
    }

    #[derive(Clone, Copy)]
    struct AllocationSource {
        initial_pitch_hz: f64,
        base_pitch_hz: f64,
        noise_scale: f64,
        tract_stride: Option<usize>,
    }

    fn fixture_config(input: &serde_json::Value, pitch_hz: f64) -> [f64; CONFIG_WORDS] {
        let p = &input["posture"];
        let v = &input["voice"];
        [
            &p["jaw_cm"],
            &p["tongue_body_cm"][0],
            &p["tongue_body_cm"][1],
            &p["tongue_tip_cm"][0],
            &p["tongue_tip_cm"][1],
            &p["tip_curl"],
            &p["tongue_root_cm"],
            &p["lip_aperture_cm"],
            &p["lip_protrusion_cm"],
            &p["lip_spread"],
            &p["labiodental"],
            &p["velum_cm2"],
            &p["larynx_cm"],
            &p["epilarynx"],
            &p["ventricular"],
            &p["lateral"],
            &p["dorsum"],
            &v["pressure_cm_h2o"],
            &v["gate"],
            &serde_json::Value::from(pitch_hz),
            &v["breathiness"],
            &v["tension"],
            &v["output_gain"],
        ]
        .map(|value| value.as_f64().unwrap_or(0.0))
    }

    #[test]
    fn fixed_rate_render_allocation_profile() {
        fixed_rate_allocation_counts(include_str!(
            "../../../cases/worklet-realtime-voice-44100.json"
        ));
    }

    #[test]
    fn fixed_rate_render_allocation_profile_32000() {
        fixed_rate_allocation_counts(include_str!(
            "../../../cases/worklet-realtime-voice-32000.json"
        ));
    }

    #[test]
    fn fixed_rate_render_allocation_profile_16000() {
        fixed_rate_allocation_counts(include_str!(
            "../../../cases/worklet-realtime-voice-16000.json"
        ));
    }

    #[test]
    fn fixed_rate_render_allocation_profile_96000() {
        fixed_rate_allocation_counts(include_str!(
            "../../../cases/worklet-realtime-voice-96000.json"
        ));
    }

    fn fixed_rate_allocation_counts(case: &str) {
        let input: serde_json::Value =
            serde_json::from_str(include_str!("../../../cases/vowel-voice-i.json")).unwrap();
        let case: serde_json::Value = serde_json::from_str(case).unwrap();
        let settings = &case["measurement"];
        let integer = |key: &str| settings[key].as_u64().unwrap() as usize;
        let quantum = integer("expected_quantum_frames");
        let frames = integer("expected_output_frames");
        let start = integer("pre_roll_frames");
        let stop = integer("expected_stop_frame");
        assert!(
            [start, stop, frames]
                .into_iter()
                .all(|frame| frame.is_multiple_of(quantum))
        );
        let mut config = fixture_config(&input, input["voice"]["f0_hz"].as_f64().unwrap());
        config[ARTICULATOR_COUNT + 1] = 0.0; // 呼気の初期値
        let mut counts = Vec::with_capacity(frames / quantum);
        let handle = vocal_new(
            integer("internal_rate_hz") as u32,
            integer("output_rate_hz") as u32,
        );
        // 同じスレッドの描画ABIで、開始から減衰末尾までの量子を再現する。
        unsafe {
            std::slice::from_raw_parts_mut(vocal_config(handle), CONFIG_WORDS)
                .copy_from_slice(&config);
            assert_eq!(vocal_start(handle), 1);
            for frame in (0..frames).step_by(quantum) {
                let before = ALLOCATIONS.with(Cell::get);
                if frame == start {
                    assert_eq!(vocal_set_gate(handle, 1.0), 1);
                } else if frame == stop {
                    assert_eq!(vocal_set_gate(handle, 0.0), 1);
                }
                assert_eq!(vocal_render(handle, quantum), 1);
                assert_eq!(*vocal_observation(handle), (frame + quantum) as f64);
                counts.push(ALLOCATIONS.with(Cell::get) - before);
            }
            vocal_free(handle);
        }
        println!(
            "fixed_rate_render_allocations={}",
            serde_json::to_string(&counts).unwrap()
        );
    }

    fn scored_allocation_counts(
        input: &serde_json::Value,
        settings: &serde_json::Value,
        source: AllocationSource,
        mut observe: impl FnMut(&Handle, usize, bool),
    ) -> Vec<usize> {
        let quantum = settings["expected_render_quantum_frames"].as_u64().unwrap() as usize;
        let observation_stride = settings["observation_stride_frames"].as_u64().unwrap() as usize;
        let frames = settings["output_frames"].as_u64().unwrap() as usize;
        let handle = vocal_new(
            settings["internal_rate_hz"].as_u64().unwrap() as u32,
            settings["output_rate_hz"].as_u64().unwrap() as u32,
        );
        let config = fixture_config(input, source.initial_pitch_hz);
        let mut counts = Vec::with_capacity(frames.div_ceil(quantum));
        // ブラウザと同じABIの領域を同じスレッドで扱う。
        unsafe {
            assert_eq!(config.len(), CONFIG_WORDS);
            std::slice::from_raw_parts_mut(vocal_config(handle), CONFIG_WORDS)
                .copy_from_slice(&config);
            let score_words = planning::vocal_plan_score_words();
            assert!(score_words > 0);
            std::slice::from_raw_parts_mut(vocal_score_buffer(handle, score_words), score_words)
                .copy_from_slice(std::slice::from_raw_parts(
                    planning::vocal_plan_score(),
                    score_words,
                ));
            assert_eq!(
                vocal_start_score(handle, source.noise_scale, source.base_pitch_hz),
                1
            );
            if source.tract_stride.is_some() {
                assert!(!vocal_glottal_trace_init(handle).is_null());
                assert!(!vocal_tract_init(handle).is_null());
            }
            #[cfg(all(not(target_arch = "wasm32"), feature = "render-allocation-probe"))]
            let _ = vocal_core::render_allocation_probe::take_counts();
            let mut rendered = 0;
            while rendered < frames {
                let before = ALLOCATIONS.with(Cell::get);
                let end = (rendered + quantum).min(frames);
                while rendered < end {
                    let observation_left = observation_stride - rendered % observation_stride;
                    let tract_left = source
                        .tract_stride
                        .map_or(usize::MAX, |stride| stride - rendered % stride);
                    let step = (end - rendered).min(observation_left).min(tract_left);
                    assert_eq!(vocal_render(handle, step), 1);
                    rendered += step;
                    if source
                        .tract_stride
                        .is_some_and(|stride| rendered.is_multiple_of(stride) || rendered == frames)
                    {
                        assert_eq!(vocal_tract_snapshot(handle), 1);
                    }
                    observe(&*handle, step, rendered == end);
                }
                counts.push(ALLOCATIONS.with(Cell::get) - before);
            }
            assert_eq!(*vocal_observation(handle), frames as f64);
            vocal_free(handle);
        }
        counts
    }

    fn write_planner_input(input: &[u8]) {
        let target = planning::vocal_plan_input(input.len());
        assert!(!target.is_null());
        // 同じスレッド内で、確保した直後の入力領域へ全バイトを渡す。
        unsafe {
            std::slice::from_raw_parts_mut(target, input.len()).copy_from_slice(input);
        }
    }

    #[test]
    fn male_ipa_plan_glides_to_explicit_pitch_and_enables_labiodental_noise() {
        write_planner_input("ɑfɑvɑ".as_bytes());
        let length = planning::vocal_ipa_plan(0.05, 1.0, 112.0);
        assert!(length > 0);
        // プランナーを更新する前に同じスレッド内で報告を読む。
        let bytes = unsafe { std::slice::from_raw_parts(planning::vocal_plan_report(), length) };
        let report: serde_json::Value = serde_json::from_slice(bytes).unwrap();
        let plan = &report["plan"];
        assert_eq!(plan["base_pitch_hz"], 112.0);
        assert_eq!(plan["initial_pitch_hz"], 110.0);
        assert_eq!(plan["glide_from_initial"], true);
        assert_eq!(plan["noise_scale"], 1.0);
    }

    #[test]
    fn each_retroflex_consonant_enables_turbulence_in_ipa_plan() {
        for text in ["ɑʂɑ", "ɑtʂɑ"] {
            write_planner_input(text.as_bytes());
            let length = planning::vocal_ipa_plan(0.05, 1.0, 112.0);
            assert!(length > 0, "{text}");
            // 他の摩擦音を含まない入力で乱流設定を確認する。
            let bytes =
                unsafe { std::slice::from_raw_parts(planning::vocal_plan_report(), length) };
            let report: serde_json::Value = serde_json::from_slice(bytes).unwrap();
            assert_eq!(report["plan"]["noise_scale"], 1.0, "{text}");
        }
    }

    #[test]
    fn dental_dh_enables_turbulence_in_both_contexts() {
        for text in ["ðə", "ɑðə"] {
            write_planner_input(text.as_bytes());
            let length = planning::vocal_ipa_plan(0.05, 1.0, 112.0);
            assert!(length > 0, "{text}");
            // /ð/ だけで乱流が有効になり、閉鎖や狭窄の音を描画できる。
            let bytes =
                unsafe { std::slice::from_raw_parts(planning::vocal_plan_report(), length) };
            let report: serde_json::Value = serde_json::from_slice(bytes).unwrap();
            assert_eq!(report["plan"]["noise_scale"], 1.0, "{text}");
        }
    }

    #[test]
    fn ipa_render_allocation_profile() {
        let input: serde_json::Value =
            serde_json::from_str(include_str!("../../../cases/bilabial-p.json")).unwrap();
        let input = &input["speech_voice"];
        let fixture: serde_json::Value =
            serde_json::from_str(include_str!("../../../cases/worklet-ipa-voice.json")).unwrap();
        let profile: serde_json::Value =
            serde_json::from_str(include_str!("../../../cases/worklet-tract-profile.json"))
                .unwrap();
        let tract_stride = profile["measurement"]["profile_stride_output_frames"]
            .as_u64()
            .unwrap() as usize;
        let f0 = input["voice"]["f0_hz"].as_f64().unwrap();
        write_planner_input(input["input"]["text"].as_str().unwrap().as_bytes());
        assert!(planning::vocal_ipa_plan(0.05, input["input"]["rate"].as_f64().unwrap(), f0) > 0);
        let counts = scored_allocation_counts(
            input,
            &fixture["measurement"],
            AllocationSource {
                initial_pitch_hz: f0,
                base_pitch_hz: f64::NAN,
                noise_scale: f64::NAN,
                tract_stride: Some(tract_stride),
            },
            |_, _, _| {},
        );
        println!(
            "ipa_render_allocations={}",
            serde_json::to_string(&counts).unwrap()
        );
    }

    #[test]
    fn song_render_allocation_profile() {
        use std::io::Read;

        let input: serde_json::Value =
            serde_json::from_str(include_str!("../../../cases/song-voice-long.json")).unwrap();
        let input = &input["song_voice"];
        let fixture: serde_json::Value =
            serde_json::from_str(include_str!("../../../cases/worklet-song-voice.json")).unwrap();
        let mut request = input["score"].clone();
        request["vibrato_cents"] = input["vibrato_cents"].clone();
        write_planner_input(&serde_json::to_vec(&request).unwrap());

        let mut dictionary = Vec::new();
        let compressed = include_bytes!("../../../data/cmudict.txt.gz");
        flate2::read::GzDecoder::new(&compressed[..])
            .read_to_end(&mut dictionary)
            .unwrap();
        let destination = planning::vocal_song_dictionary(dictionary.len());
        assert!(!destination.is_null());
        // このスレッドで確保した辞書領域を歌唱プランナーに渡す。
        let prepared = unsafe {
            std::slice::from_raw_parts_mut(destination, dictionary.len())
                .copy_from_slice(&dictionary);
            let len = planning::vocal_song_plan();
            serde_json::from_slice::<serde_json::Value>(std::slice::from_raw_parts(
                planning::vocal_plan_report(),
                len,
            ))
            .unwrap()
        };
        let plan = &prepared["plan"];
        let settings = &fixture["measurement"];
        let source = AllocationSource {
            initial_pitch_hz: plan["initial_pitch_hz"].as_f64().unwrap(),
            base_pitch_hz: plan["base_pitch_hz"].as_f64().unwrap(),
            noise_scale: plan["noise_scale"].as_f64().unwrap(),
            tract_stride: None,
        };
        #[cfg(all(not(target_arch = "wasm32"), feature = "render-allocation-probe"))]
        if let Some(directory) = std::env::var_os("CHIMERA_SONG_ALLOCATION_PROBE_OUTPUT") {
            let directory = std::path::Path::new(&directory);
            record_song_allocation_phases(directory, input, settings, source);
            return;
        }
        let counts = scored_allocation_counts(input, settings, source, |_, _, _| {});
        println!(
            "song_render_allocations={}",
            serde_json::to_string(&counts).unwrap()
        );
    }

    #[cfg(all(not(target_arch = "wasm32"), feature = "render-allocation-probe"))]
    fn record_song_allocation_phases(
        directory: &std::path::Path,
        input: &serde_json::Value,
        settings: &serde_json::Value,
        source: AllocationSource,
    ) {
        use std::fs::{self, File};
        use vocal_core::render_allocation_probe as probe;

        let frames = settings["output_frames"].as_u64().unwrap() as usize;
        let quantum = settings["expected_render_quantum_frames"].as_u64().unwrap() as usize;
        let stride = settings["observation_stride_frames"].as_u64().unwrap() as usize;
        for mode in ["plain", "traced"] {
            let mut pcm = Vec::with_capacity(frames);
            let mut states = Vec::with_capacity(frames.div_ceil(stride));
            let mut phases = Vec::with_capacity(frames.div_ceil(quantum));
            let mut render = || {
                scored_allocation_counts(input, settings, source, |handle, length, quantum_end| {
                    pcm.extend_from_slice(&handle.pcm[..length]);
                    states.push(handle.observation);
                    if quantum_end {
                        phases.push(probe::take_counts());
                    }
                })
            };
            let counts = if mode == "traced" {
                probe::trace(|| ALLOCATIONS.get(), render)
            } else {
                render()
            };
            assert_eq!(pcm.len(), frames);
            assert_eq!(states.len(), frames.div_ceil(stride));
            assert_eq!(phases.len(), frames.div_ceil(quantum));
            let pcm: Vec<_> = pcm.into_iter().flat_map(f32::to_le_bytes).collect();
            let states: Vec<_> = states
                .into_iter()
                .flatten()
                .flat_map(f64::to_le_bytes)
                .collect();
            fs::write(directory.join(format!("{mode}.f32le")), pcm).unwrap();
            fs::write(directory.join(format!("{mode}-observations.f64le")), states).unwrap();
            let report = serde_json::json!({
                "phase_names": probe::PHASE_NAMES,
                "total_by_quantum": counts,
                "phase_counts": phases,
            });
            let file = File::create(directory.join(format!("{mode}-counts.json"))).unwrap();
            serde_json::to_writer(file, &report).unwrap();
        }
    }
}
