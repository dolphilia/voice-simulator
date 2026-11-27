//! 発話・歌唱・打音のスコアを声道まで進め、閉鎖・流量・放射を出力フレームに合わせて測る。

use super::{Example, report};
use crate::{
    english_case,
    geometry_case::{BodyInput, Pose, voice::Settings},
    network_case::{Destination, pcm},
    song_case::Score,
    write_json,
};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    error::Error,
    fs::File,
    io::{self, BufWriter, Write},
    path::Path,
};
use vocal_core::{
    airway::human::{HumanAirway, TurbulenceSettings as SourceTurbulence},
    anatomy::{BodyMix, BodyName},
    articulators::Articulator,
    output::OutputStage,
    phonetics::{
        beatbox,
        english::{self, English},
        song,
        speech::speech_gestures,
        timing::TimedSegment,
    },
    score::{ControlKey, Gesture, Targets},
    voice::{ArticulatedVoice, FixedVoiceSettings, VoiceSample},
};

pub(crate) mod beat_pattern;
mod telemetry;
use beat_pattern::Playback;

#[derive(Deserialize)]
struct Case {
    speech_voice: Input,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Input {
    input: Example,
    #[serde(default)]
    language: Language,
    body: Option<BodyInput>,
    posture: Pose,
    internal_sample_rate_hz: u32,
    voice: Settings,
    #[serde(default)]
    source_variation: SourceVariation,
    turbulence: Option<TurbulenceSettings>,
    lateral_opening_scale: Option<f64>,
    tract_profile_frames: Option<Vec<usize>>,
    #[serde(default)]
    tract_profile_acoustics: bool,
    #[serde(default)]
    tract_profile_grid: bool,
    #[serde(default)]
    tract_profile_posture: bool,
}

#[derive(Default, Deserialize)]
#[serde(deny_unknown_fields)]
struct SourceVariation {
    pitch_drift_cents: Option<f64>,
    period_jitter: Option<f64>,
    amplitude_shimmer: Option<f64>,
}

#[derive(Deserialize)]
struct SongCase {
    song_voice: SongInput,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SongInput {
    score: Option<Score>,
    scores: Option<Vec<Score>>,
    render_end_seconds: Option<f64>,
    #[serde(default)]
    warm_up_frames: usize,
    body: Option<BodyInput>,
    posture: Pose,
    internal_sample_rate_hz: u32,
    voice: SongVoiceSettings,
    turbulence: Option<TurbulenceSettings>,
    vibrato_cents: Option<f64>,
    tract_profile_frames: Option<Vec<usize>>,
    #[serde(default)]
    tract_profile_acoustics: bool,
    #[serde(default)]
    tract_profile_grid: bool,
}

#[derive(Deserialize)]
struct BeatboxCase {
    beatbox_voice: BeatboxInput,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct BeatboxInput {
    sound: String,
    midi_note: Option<f64>,
    hit_seconds: f64,
    step_seconds: f64,
    accent: f64,
    render_end_seconds: f64,
    posture: Pose,
    internal_sample_rate_hz: u32,
    initial_f0_hz: f64,
    voice: Settings,
    noise_scale: f64,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SongVoiceSettings {
    pressure_cm_h2o: f64,
    gate: f64,
    breathiness: f64,
    tension: f64,
    base_pitch_hz: Option<f64>,
    pitch_drift_cents: Option<f64>,
    period_jitter: Option<f64>,
    amplitude_shimmer: Option<f64>,
    output_sample_rate_hz: u32,
    output_gain: f64,
}

#[derive(Clone, Copy, Default, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
enum Language {
    #[default]
    Ipa,
    English,
}

#[derive(Clone, Copy, Deserialize)]
#[serde(deny_unknown_fields)]
struct TurbulenceSettings {
    scale: f64,
    glottis_gain_multiplier: Option<f64>,
    constriction_gain_multiplier: Option<f64>,
    teeth_lowpass_floor_hz: Option<f64>,
}

impl TurbulenceSettings {
    fn at_scale(scale: f64) -> Self {
        Self {
            scale,
            glottis_gain_multiplier: None,
            constriction_gain_multiplier: None,
            teeth_lowpass_floor_hz: None,
        }
    }
}

pub(crate) fn run(value: Value, destination: Destination<'_>) -> Result<(), Box<dyn Error>> {
    let case = Case::deserialize(&value)?.speech_voice;
    let body = case
        .body
        .map_or_else(|| BodyName::Male.into(), BodyMix::from);
    let adult_male = body.preset() == Some(BodyName::Male);
    let default_f0_hz = match case.language {
        Language::Ipa => body.default_f0_hz(),
        Language::English => english::default_f0_hz(body),
    };
    let settings = case.voice.source(Some(default_f0_hz))?;
    let glide_from_initial = case.language == Language::English
        || !adult_male
        || settings.f0_hz != english::INITIAL_VOICE_F0_HZ;
    let mut initial_settings = settings;
    if glide_from_initial {
        // 上流の音源は110 Hzで初期化され、設定した基準音高へ移動する。
        initial_settings.f0_hz = english::INITIAL_VOICE_F0_HZ;
    }
    let (speech, gestures, render_end, features) = match case.language {
        Language::Ipa => {
            let speech = report(&case.input, None)?;
            let mut gestures = Vec::new();
            for row in &speech.utterances {
                gestures.extend(speech_gestures(
                    &row.timing,
                    row.start_seconds,
                    settings.f0_hz,
                    body,
                )?);
            }
            let symbols = speech
                .utterances
                .iter()
                .flat_map(|row| &row.timing.segments);
            let features = TraceFeatures::from_symbols(symbols);
            (
                serde_json::to_value(&speech)?,
                gestures,
                speech.render_end_seconds,
                features,
            )
        }
        Language::English => {
            let text = case
                .input
                .text
                .as_deref()
                .ok_or("英語の発話テキストを指定してください")?;
            if case.input.segments.is_some() || !case.input.additional_gestures.is_empty() {
                return Err("英語の音声ケースにはテキストを指定してください".into());
            }
            let (plan, gestures) = english::plan_voice_with_body(
                english_case::dictionary()?,
                text,
                case.input.start_seconds.unwrap_or(english::START_SECONDS),
                case.input.rate.unwrap_or(1.0),
                settings.f0_hz,
                body,
            )?;
            let symbols = plan.phrases.iter().flat_map(|row| &row.timing.segments);
            let features = TraceFeatures::from_symbols(symbols);
            (
                serde_json::to_value(&plan)?,
                gestures,
                plan.render_end_seconds,
                features,
            )
        }
    };
    let turbulence = case.turbulence.or_else(|| {
        (features.oral_frication || features.glottal).then_some(TurbulenceSettings::at_scale(1.0))
    });
    let setup = RenderSetup {
        body,
        stage: case.voice.output_stage(case.internal_sample_rate_hz)?,
        output_rate: case.voice.output_sample_rate_hz,
        internal_rate: case.internal_sample_rate_hz,
        posture: case.posture,
        initial_settings,
        base_pitch: glide_from_initial.then_some(settings.f0_hz),
        pitch_drift_cents: case.source_variation.pitch_drift_cents,
        period_jitter: case.source_variation.period_jitter,
        amplitude_shimmer: case.source_variation.amplitude_shimmer,
        base_targets: None,
        beatbox_source: false,
        turbulence,
        lateral_opening_scale: case.lateral_opening_scale,
    };
    let performance = Performance {
        report_key: "speech",
        warm_up_frames: 0,
        report: speech,
        gestures,
        pattern: None,
        render_end,
        features,
        tract_profile_frames: case.tract_profile_frames,
        tract_profile_acoustics: case.tract_profile_acoustics,
        tract_profile_grid: case.tract_profile_grid,
        tract_profile_posture: case.tract_profile_posture,
    };
    render(value, destination, setup, performance, None)
}

pub(crate) fn run_song(
    value: Value,
    destination: Destination<'_>,
    telemetry_path: Option<&Path>,
) -> Result<(), Box<dyn Error>> {
    let case = SongCase::deserialize(&value)?.song_voice;
    let (scores, single_score) = match (&case.score, case.scores.as_deref()) {
        (Some(score), None) => (std::slice::from_ref(score), true),
        (None, Some(scores)) if !scores.is_empty() => (scores, false),
        _ => return Err("歌唱には score または空でない scores の一方を指定してください".into()),
    };
    let body = case
        .body
        .map_or_else(|| BodyName::Male.into(), BodyMix::from);
    let rules = English::default();
    let mut entries = Vec::with_capacity(scores.len());
    let mut gestures = Vec::new();
    for score in scores {
        let dictionary = if score.uses_dictionary() {
            english_case::dictionary()?
        } else {
            &rules
        };
        let (syllables, plan) = score.plan(dictionary)?;
        if !plan.unavailable_speech_symbols.is_empty() {
            return Err(format!(
                "歌唱に未対応の音素があります ({})",
                plan.unavailable_speech_symbols.join(" ")
            )
            .into());
        }
        gestures.extend(song::score_with_body(
            &plan,
            case.vibrato_cents.unwrap_or(35.0),
            body,
        )?);
        entries.push((&score.id, syllables, plan));
    }
    let base_pitch = case.voice.base_pitch_hz.or_else(|| {
        entries
            .iter()
            .find_map(|(_, _, plan)| plan.notes.first().map(|note| note.f0_hz))
    });
    let render_end = case.render_end_seconds.unwrap_or_else(|| {
        entries
            .iter()
            .map(|(_, _, plan)| plan.render_end_seconds)
            .reduce(f64::max)
            .expect("少なくとも1件の歌唱計画")
    });
    let initial_settings = FixedVoiceSettings {
        pressure_cm_h2o: case.voice.pressure_cm_h2o,
        gate: case.voice.gate,
        f0_hz: 110.0,
        breathiness: case.voice.breathiness,
        tension: case.voice.tension,
    };
    let setup = RenderSetup {
        body,
        stage: OutputStage::new(
            case.internal_sample_rate_hz,
            case.voice.output_sample_rate_hz,
            case.voice.output_gain,
        )?,
        output_rate: case.voice.output_sample_rate_hz,
        internal_rate: case.internal_sample_rate_hz,
        posture: case.posture,
        initial_settings,
        base_pitch,
        pitch_drift_cents: case.voice.pitch_drift_cents,
        period_jitter: case.voice.period_jitter,
        amplitude_shimmer: case.voice.amplitude_shimmer,
        base_targets: None,
        beatbox_source: false,
        turbulence: Some(case.turbulence.unwrap_or(TurbulenceSettings::at_scale(1.0))),
        lateral_opening_scale: None,
    };
    let features = TraceFeatures {
        smoothed_pitch: true,
        ..TraceFeatures::from_symbols(
            entries
                .iter()
                .flat_map(|(_, _, plan)| &plan.phrases)
                .flat_map(|phrase| &phrase.timing.segments),
        )
    };
    let mut reports: Vec<_> = entries
        .into_iter()
        .map(|(id, syllables, plan)| json!({"id":id,"syllables":syllables,"plan":plan}))
        .collect();
    let performance = Performance {
        report_key: "song",
        warm_up_frames: case.warm_up_frames,
        report: if single_score {
            reports.remove(0)
        } else {
            json!({"scores":reports})
        },
        gestures,
        pattern: None,
        render_end,
        features,
        tract_profile_frames: case.tract_profile_frames,
        tract_profile_acoustics: case.tract_profile_acoustics,
        tract_profile_grid: case.tract_profile_grid,
        tract_profile_posture: false,
    };
    render(value, destination, setup, performance, telemetry_path)
}

pub(crate) fn run_beatbox(
    value: Value,
    destination: Destination<'_>,
) -> Result<(), Box<dyn Error>> {
    let case = BeatboxCase::deserialize(&value)?.beatbox_voice;
    let sound = beatbox::BeatSound::from_id(&case.sound)
        .ok_or("単発の打音には B、t、tss、Pf、K、^K、!、P!、kch、m のいずれかを指定してください")?;
    let mut gestures = Vec::with_capacity(beatbox::BeatSound::MAX_GESTURES);
    beatbox::BeatStep {
        sound,
        accent: case.accent,
        midi_note: case.midi_note,
    }
    .append_gestures(case.hit_seconds, case.step_seconds, &mut gestures)?;
    if gestures
        .iter()
        .any(|gesture| gesture.t0 - gesture.ramp_in < 0.0)
        || case.render_end_seconds <= case.hit_seconds
    {
        return Err("打音前の準備と打音後の出力を含む時刻を指定してください".into());
    }
    let setup = beatbox_setup(
        case.voice,
        case.posture,
        case.internal_sample_rate_hz,
        case.initial_f0_hz,
        case.noise_scale,
    )?;
    let mut report = json!({
        "sound": sound, "hit_seconds": case.hit_seconds, "step_seconds": case.step_seconds,
        "accent": case.accent, "ready_targets": setup.base_targets,
    });
    if sound == beatbox::BeatSound::Hum || case.midi_note.is_some() {
        report["midi_note"] = json!(case.midi_note);
    }
    let performance = Performance {
        report_key: "beatbox",
        warm_up_frames: 0,
        report,
        gestures,
        pattern: None,
        render_end: case.render_end_seconds,
        features: TraceFeatures {
            beatbox: true,
            velum: sound == beatbox::BeatSound::Hum,
            smoothed_pitch: sound == beatbox::BeatSound::Hum,
            oral_cells: sound.is_hat()
                || sound == beatbox::BeatSound::Snare
                || sound.has_velar_closure(),
            oral_posture: sound.has_velar_closure(),
            pharynx_minimum: sound.has_velar_closure(),
            labiodental: sound == beatbox::BeatSound::Snare,
            inward_jet: sound == beatbox::BeatSound::InwardSnare,
            constriction_position: sound == beatbox::BeatSound::Crash,
            oral_cell_acoustics: sound.has_oral_pocket(),
            ..TraceFeatures::default()
        },
        tract_profile_frames: None,
        tract_profile_acoustics: false,
        tract_profile_grid: false,
        tract_profile_posture: false,
    };
    render(value, destination, setup, performance, None)
}

fn beatbox_setup(
    voice: Settings,
    posture: Pose,
    internal_rate: u32,
    initial_f0: f64,
    noise_scale: f64,
) -> Result<RenderSetup, &'static str> {
    let mut initial_settings = voice.source(None)?;
    let base_pitch = initial_settings.f0_hz;
    initial_settings.f0_hz = initial_f0;
    Ok(RenderSetup {
        body: BodyName::Male.into(),
        stage: voice.output_stage(internal_rate)?,
        output_rate: voice.output_sample_rate_hz,
        internal_rate,
        posture,
        initial_settings,
        base_pitch: Some(base_pitch),
        pitch_drift_cents: None,
        period_jitter: None,
        amplitude_shimmer: None,
        base_targets: Some(beatbox::male_ready_targets()),
        beatbox_source: true,
        turbulence: Some(TurbulenceSettings::at_scale(noise_scale)),
        lateral_opening_scale: None,
    })
}

struct RenderSetup {
    body: BodyMix,
    stage: OutputStage,
    output_rate: u32,
    internal_rate: u32,
    posture: Pose,
    initial_settings: FixedVoiceSettings,
    base_pitch: Option<f64>,
    pitch_drift_cents: Option<f64>,
    period_jitter: Option<f64>,
    amplitude_shimmer: Option<f64>,
    base_targets: Option<Targets>,
    beatbox_source: bool,
    turbulence: Option<TurbulenceSettings>,
    lateral_opening_scale: Option<f64>,
}

struct Performance {
    report_key: &'static str,
    warm_up_frames: usize,
    report: Value,
    gestures: Vec<Gesture>,
    pattern: Option<Playback>,
    render_end: f64,
    features: TraceFeatures,
    tract_profile_frames: Option<Vec<usize>>,
    tract_profile_acoustics: bool,
    tract_profile_grid: bool,
    tract_profile_posture: bool,
}

fn step_audio(
    voice: &mut ArticulatedVoice,
    pattern: &mut Option<Playback>,
) -> Result<VoiceSample, &'static str> {
    if let Some(pattern) = pattern {
        pattern.before_sample(voice)?;
    }
    voice.step()
}

fn render(
    value: Value,
    destination: Destination<'_>,
    setup: RenderSetup,
    performance: Performance,
    telemetry_path: Option<&Path>,
) -> Result<(), Box<dyn Error>> {
    let RenderSetup {
        body,
        mut stage,
        output_rate,
        internal_rate,
        posture,
        initial_settings,
        base_pitch,
        pitch_drift_cents,
        period_jitter,
        amplitude_shimmer,
        beatbox_source,
        turbulence,
        lateral_opening_scale,
        ..
    } = setup;
    let Performance {
        report_key,
        warm_up_frames,
        mut report,
        mut gestures,
        mut pattern,
        render_end,
        features,
        tract_profile_frames,
        tract_profile_acoustics,
        tract_profile_grid,
        tract_profile_posture,
    } = performance;
    let frames = (render_end * f64::from(output_rate)).round();
    if !frames.is_finite() || frames < 1.0 || frames > f64::from(u32::MAX) {
        return Err("発話の出力フレーム数が範囲外です".into());
    }
    let frames = frames as usize;
    warm_up_frames
        .checked_add(frames)
        .and_then(|total| total.checked_mul(stage.factor()))
        .ok_or("予備描画を含めた内部サンプル数が範囲外です")?;
    if let Some(pattern) = &pattern {
        pattern.validate_frames(frames)?;
    }
    let trace = match (
        tract_profile_grid,
        tract_profile_posture,
        tract_profile_acoustics,
    ) {
        (true, false, false) => TractTrace::Grid,
        (false, true, false) => TractTrace::Posture,
        (false, false, acoustics) => TractTrace::Cells { acoustics },
        _ => return Err("圧力・流量、測定線、調音姿勢は別々のトレースに出力してください".into()),
    };
    if (tract_profile_acoustics || tract_profile_grid || tract_profile_posture)
        && tract_profile_frames.is_none()
    {
        return Err("圧力・流量、測定線または調音姿勢には採取フレームを指定してください".into());
    }
    if let Some(selected) = &tract_profile_frames
        && (selected.is_empty()
            || selected.iter().any(|&frame| frame >= frames)
            || selected.windows(2).any(|pair| pair[0] >= pair[1]))
    {
        return Err("断面の採取フレームには、出力範囲内の重複のない昇順を指定してください".into());
    }
    let samples = frames
        .checked_mul(stage.factor())
        .ok_or("内部サンプル数が範囲外です")?;
    let control_block = 64 * stage.factor();
    let mut posture: vocal_core::anatomy::Articulation = posture.into();
    if let Some(scale) = lateral_opening_scale {
        if !(0.0..=1.0).contains(&scale) {
            return Err("側方開きの倍率は0から1の範囲で指定してください".into());
        }
        posture.lateral *= scale;
        let key = ControlKey::Artic(Articulator::Lateral);
        for gesture in &mut gestures {
            if let Some(target) = gesture.targets.get(key) {
                gesture.targets.set(key, target * scale);
            }
        }
    }
    let mut voice = ArticulatedVoice::for_speech_with_body(
        internal_rate,
        control_block,
        posture,
        initial_settings,
        body,
    )?;
    if beatbox_source {
        voice.configure_beatbox(
            base_pitch.ok_or("打音の基準F0がありません")?,
            turbulence.ok_or("打音の乱流倍率がありません")?.scale,
        )?;
    } else {
        if let Some(f0_hz) = base_pitch {
            voice.set_base_pitch(f0_hz)?;
        }
        if let Some(cents) = pitch_drift_cents {
            voice.set_pitch_drift_cents(cents)?;
        }
        if let Some(amount) = period_jitter {
            voice.set_period_jitter(amount)?;
        }
        if let Some(amount) = amplitude_shimmer {
            voice.set_amplitude_shimmer(amount)?;
        }
        if let Some(turbulence) = turbulence {
            voice.enable_turbulence_with_settings(SourceTurbulence {
                scale: turbulence.scale,
                glottis_gain_multiplier: turbulence.glottis_gain_multiplier.unwrap_or(1.0),
                constriction_gain_multiplier: turbulence
                    .constriction_gain_multiplier
                    .unwrap_or(1.0),
                teeth_lowpass_floor_hz: turbulence.teeth_lowpass_floor_hz.unwrap_or(0.0),
            })?;
        }
    }
    if let Destination::Inspect = destination {
        if let Some(pattern) = &pattern {
            let dt = control_block as f64 / f64::from(internal_rate);
            let (reservations, events) = pattern.reservations(frames, dt)?;
            report["reservations"] = reservations;
            if !events.is_empty() {
                report["transport_events"] = json!(events);
            }
        }
        let airway = voice.airway();
        let [_, pharynx, oral, ..] = &airway.tubes;
        return write_json(
            io::stdout().lock(),
            &json!({
                "case": value, (report_key): report, "gestures": gestures, "output_frames": frames,
                "control_block_internal_samples": control_block, "decimation_factor":stage.factor(),
                "noise_branches": {
                    "pharynx": {"base": pharynx.branches.start, "cells": pharynx.nodes.len()},
                    "oral": {"base": oral.branches.start, "cells": oral.nodes.len()},
                    "glottis_port": airway.glottis_port,
                    "sample_rate_hz": output_rate,
                },
            }),
        );
    }
    if warm_up_frames != 0 {
        // 歌唱を予約する位置まで声道・乱流・出力段を進め、保存区間はその位置から始める。
        for _ in 0..warm_up_frames {
            stage.render_frame(|| {
                voice
                    .step()
                    .map(|sample| (sample.radiation.radiation_flow_derivative_cm3_s2, ()))
            })?;
        }
        let origin = voice.clock_seconds();
        for gesture in &mut gestures {
            gesture.t0 += origin;
            gesture.t1 += origin;
        }
    }
    voice.set_score(gestures)?;
    match destination {
        Destination::Trace(path) => {
            if let Some(selected) = tract_profile_frames {
                return render_tract_profile(path, &mut voice, &selected, stage.factor(), trace);
            }
            let mut out = BufWriter::new(File::create_new(path)?);
            write!(
                out,
                concat!(
                    "frame,lip_aperture_cm,lip_minimum_cm2,lip_area_cm2,lip_flow_cm3_s,nose_flow_cm3_s,",
                    "pressure_sub_dyn_cm2,pressure_supra_dyn_cm2,lung_boundary_dyn_cm2,gate,",
                    "abduction_cm2,glottal_area_cm2,glottal_flow_cm3_s,glottal_voicing,",
                    "glottal_f0_hz,radiation_derivative_cm3_s2"
                )
            )?;
            if turbulence.is_some() {
                noise_header(&mut out)?;
            }
            if features.glottal {
                write!(out, ",glottis_jet_area_cm2")?;
            }
            let observe_glottal_phase = features.glottal_stop || warm_up_frames != 0;
            if observe_glottal_phase {
                write!(out, ",glottal_closure_command,glottal_phase")?;
            }
            if amplitude_shimmer.is_some() {
                write!(out, ",glottal_cycle_amplitude_scale")?;
            }
            if features.velum {
                write!(
                    out,
                    ",velum_position_cm2,velum_effective_cm2,velum_port_area_cm2,velum_flow_cm3_s,oral_min_cell_area_cm2"
                )?;
            }
            if features.oral_posture {
                write!(
                    out,
                    ",lip_protrusion_cm,lip_spread,tongue_body_x_cm,tongue_body_y_cm"
                )?;
            }
            if features.jaw_position {
                write!(out, ",jaw_cm")?;
            }
            if features.lateral {
                write!(out, ",lateral_position,lateral_effective")?;
            }
            if features.tip_curl {
                write!(out, ",tongue_tip_curl")?;
            }
            if features.tongue_root {
                write!(out, ",tongue_root_cm")?;
            }
            if features.oral_cells {
                write!(
                    out,
                    ",tongue_tip_x_cm,tongue_tip_y_cm,oral_minimum_cm2,oral_minimum_cell"
                )?;
                for cell in 0..voice.airway().tubes[2].nodes.len() {
                    write!(out, ",oral_cell_{cell}_minimum_cm2")?;
                }
            }
            if features.smoothed_pitch {
                write!(out, ",smoothed_f0_hz")?;
            }
            if features.beatbox {
                write!(out, ",jaw_cm,larynx_cm,oral_end_pressure_dyn_cm2")?;
            }
            if features.labiodental {
                write!(out, ",labiodental")?;
            }
            if features.lower_lip_edge {
                write!(out, ",lower_lip_edge_x_cm,lower_lip_edge_y_cm")?;
            }
            if features.pharynx_minimum {
                write!(out, ",pharynx_minimum_cm2")?;
            }
            if features.constriction_geometry {
                write!(
                    out,
                    ",pharynx_anatomical_length_cm,oral_anatomical_length_cm,pharynx_cells,oral_cells"
                )?;
            }
            if features.oral_branch_flows {
                for branch in 0..voice.airway().tubes[2].branches.len() {
                    write!(out, ",oral_branch_{branch}_flow_cm3_s")?;
                }
            }
            if features.inward_jet {
                write!(out, ",constriction_jet_flow_cm3_s")?;
            }
            if features.constriction_position {
                write!(out, ",constriction_noise_tract_cell")?;
            }
            if features.oral_cell_acoustics {
                write!(out, ",dorsum")?;
                for cell in 0..voice.airway().tubes[2].nodes.len() {
                    write!(
                        out,
                        ",oral_cell_{cell}_pressure_dyn_cm2,oral_cell_{cell}_volume_cm3"
                    )?;
                }
            }
            if pattern.is_some() {
                write!(out, ",beat_next_step,beat_step")?;
            }
            writeln!(out)?;
            for frame in 0..frames {
                let mut sample = step_audio(&mut voice, &mut pattern)?;
                for _ in 1..stage.factor() {
                    sample = step_audio(&mut voice, &mut pattern)?;
                }
                let airway = voice.airway();
                let lip = airway.network.section(airway.lips);
                let lip_aperture = voice
                    .articulators()
                    .state(Articulator::LipAperture)
                    .position;
                write!(out, "{frame}")?;
                for value in [
                    lip_aperture,
                    lip.minimum_area_cm2,
                    lip.area_cm2,
                    sample.lip_flow_cm3_s,
                    sample.nose_flow_cm3_s,
                    sample.subglottal_pressure_dyn_cm2,
                    sample.supraglottal_pressure_dyn_cm2,
                    sample.breath.boundary_pressure_dyn_cm2,
                    sample.breath.gate,
                    sample.abduction_cm2,
                    sample.glottis.area_cm2,
                    sample.glottal_flow_cm3_s,
                    sample.glottis.voicing,
                    sample.glottis.f0_hz,
                    sample.radiation.radiation_flow_derivative_cm3_s2,
                ] {
                    if !value.is_finite() {
                        return Err(format!("出力フレーム {frame} の観測値が非有限です").into());
                    }
                    write!(out, ",{value}")?;
                }
                if turbulence.is_some() {
                    noise_row(&mut out, airway)?;
                }
                if features.glottal {
                    let area = airway.network.branch_area(airway.glottis_port);
                    if !area.is_finite() {
                        return Err(format!("出力フレーム {frame} の声門枝面積が非有限です").into());
                    }
                    write!(out, ",{area}")?;
                }
                if observe_glottal_phase {
                    for value in [sample.glottis.closure_command, sample.glottis.phase] {
                        if !value.is_finite() {
                            return Err(format!(
                                "出力フレーム {frame} の声門閉鎖の観測値が非有限です"
                            )
                            .into());
                        }
                        write!(out, ",{value}")?;
                    }
                }
                if amplitude_shimmer.is_some() {
                    let scale = sample.glottis.cycle_amplitude_scale;
                    if !scale.is_finite() {
                        return Err(
                            format!("出力フレーム {frame} の声門振幅倍率が非有限です").into()
                        );
                    }
                    write!(out, ",{scale}")?;
                }
                if features.velum {
                    let state = voice.articulators().state(Articulator::Velum);
                    let network = &airway.network;
                    let port = airway.velum_port;
                    let oral_min = airway.tubes[2]
                        .nodes
                        .clone()
                        .map(|node| network.area(node))
                        .fold(f64::INFINITY, f64::min);
                    for value in [
                        state.position,
                        state.effective,
                        network.port_area(port).expect("軟口蓋ポート"),
                        network.branch_flow(port),
                        oral_min,
                    ] {
                        if !value.is_finite() {
                            return Err(
                                format!("出力フレーム {frame} の鼻音観測値が非有限です").into()
                            );
                        }
                        write!(out, ",{value}")?;
                    }
                }
                if features.oral_posture {
                    for axis in [
                        Articulator::LipProtrusion,
                        Articulator::LipSpread,
                        Articulator::TongueBodyX,
                        Articulator::TongueBodyY,
                    ] {
                        let value = voice.articulators().state(axis).position;
                        if !value.is_finite() {
                            return Err(format!(
                                "出力フレーム {frame} の口腔姿勢の観測値が非有限です"
                            )
                            .into());
                        }
                        write!(out, ",{value}")?;
                    }
                }
                if features.jaw_position {
                    let jaw = voice.articulators().state(Articulator::Jaw).position;
                    if !jaw.is_finite() {
                        return Err(format!("出力フレーム {frame} の顎位置が非有限です").into());
                    }
                    write!(out, ",{jaw}")?;
                }
                if features.lateral {
                    let state = voice.articulators().state(Articulator::Lateral);
                    write!(out, ",{},{}", state.position, state.effective)?;
                }
                if features.tip_curl {
                    let curl = voice.articulators().state(Articulator::TipCurl).position;
                    if !curl.is_finite() {
                        return Err(format!("出力フレーム {frame} の舌先の反りが非有限です").into());
                    }
                    write!(out, ",{curl}")?;
                }
                if features.tongue_root {
                    let root = voice.articulators().state(Articulator::TongueRoot).position;
                    if !root.is_finite() {
                        return Err(format!("出力フレーム {frame} の舌根座標が非有限です").into());
                    }
                    write!(out, ",{root}")?;
                }
                if features.oral_cells {
                    let bank = voice.articulators();
                    let x = bank.state(Articulator::TongueTipX).position;
                    let y = bank.state(Articulator::TongueTipY).position;
                    let areas = airway.tubes[2]
                        .nodes
                        .clone()
                        .map(|node| airway.network.section(node).minimum_area_cm2);
                    let (cell, area) = areas
                        .clone()
                        .enumerate()
                        .min_by(|(_, a), (_, b)| a.total_cmp(b))
                        .expect("口腔のセル");
                    if ![x, y, area].into_iter().all(f64::is_finite) {
                        return Err(format!("出力フレーム {frame} の舌先観測値が非有限です").into());
                    }
                    write!(out, ",{x},{y},{area},{cell}")?;
                    for area in areas {
                        if !area.is_finite() {
                            return Err(format!(
                                "出力フレーム {frame} の口腔セルの断面が非有限です"
                            )
                            .into());
                        }
                        write!(out, ",{area}")?;
                    }
                }
                if features.smoothed_pitch {
                    let f0 = voice.smoothed_pitch_hz();
                    if !f0.is_finite() {
                        return Err(format!("出力フレーム {frame} の平滑化F0が非有限です").into());
                    }
                    write!(out, ",{f0}")?;
                }
                if features.beatbox {
                    let bank = voice.articulators();
                    for value in [
                        bank.state(Articulator::Jaw).position,
                        bank.state(Articulator::Larynx).position,
                        airway.network.pressure(airway.lips),
                    ] {
                        if !value.is_finite() {
                            return Err(
                                format!("出力フレーム {frame} の打音観測値が非有限です").into()
                            );
                        }
                        write!(out, ",{value}")?;
                    }
                }
                if features.labiodental {
                    let labiodental = voice
                        .articulators()
                        .state(Articulator::Labiodental)
                        .position;
                    if !labiodental.is_finite() {
                        return Err(format!("出力フレーム {frame} の唇歯位置が非有限です").into());
                    }
                    write!(out, ",{labiodental}")?;
                }
                if features.lower_lip_edge {
                    let edge = voice.lower_lip_edge_cm();
                    if ![edge.x, edge.y].into_iter().all(f64::is_finite) {
                        return Err(format!("出力フレーム {frame} の下唇端座標が非有限です").into());
                    }
                    write!(out, ",{},{}", edge.x, edge.y)?;
                }
                if features.pharynx_minimum {
                    let area = airway.tubes[1]
                        .nodes
                        .clone()
                        .map(|node| airway.network.minimum_area(node))
                        .fold(f64::INFINITY, f64::min);
                    if !area.is_finite() {
                        return Err(
                            format!("出力フレーム {frame} の咽頭最小断面が非有限です").into()
                        );
                    }
                    write!(out, ",{area}")?;
                }
                if features.constriction_geometry {
                    let pharynx = &airway.tubes[1];
                    let oral = &airway.tubes[2];
                    write!(
                        out,
                        ",{},{},{},{}",
                        pharynx.anatomical_length_cm,
                        oral.anatomical_length_cm,
                        pharynx.nodes.len(),
                        oral.nodes.len()
                    )?;
                }
                if features.oral_branch_flows {
                    for branch in airway.tubes[2].branches.clone() {
                        let flow = airway.network.branch_flow(branch);
                        if !flow.is_finite() {
                            return Err(
                                format!("出力フレーム {frame} の口腔枝流量が非有限です").into()
                            );
                        }
                        write!(out, ",{flow}")?;
                    }
                }
                if features.inward_jet {
                    let net = &airway.network;
                    let flow = net
                        .noise_spec(1)
                        .map_or(0.0, |spec| net.branch_flow(spec.source));
                    if !flow.is_finite() {
                        return Err(format!("出力フレーム {frame} の狭窄枝流量が非有限です").into());
                    }
                    write!(out, ",{flow}")?;
                }
                if features.constriction_position {
                    let cell = constriction_noise_tract_cell(airway);
                    write!(out, ",{cell}")?;
                }
                if features.oral_cell_acoustics {
                    let dorsum = voice.articulators().state(Articulator::Dorsum).position;
                    write!(out, ",{dorsum}")?;
                    for node in airway.tubes[2].nodes.clone() {
                        let section = airway.network.section(node);
                        let pressure = airway.network.pressure(node);
                        let volume = section.area_cm2 * section.length_cm;
                        if !pressure.is_finite() || !volume.is_finite() {
                            return Err(
                                format!("出力フレーム {frame} の口腔セル状態が非有限です").into()
                            );
                        }
                        write!(out, ",{pressure},{volume}")?;
                    }
                }
                if let Some(pattern) = &pattern {
                    let (next, step) = pattern.position(voice.clock_seconds());
                    write!(out, ",{next},{step}")?;
                }
                writeln!(out)?;
            }
            out.flush()?;
            Ok(())
        }
        Destination::Pcm {
            wave,
            trace,
            block_frames,
        } => {
            if let Some(path) = telemetry_path {
                let mut stage = stage;
                let factor = stage.factor();
                let mut recorder =
                    telemetry::Recorder::new(&voice, output_rate, control_block, body)?;
                pcm::write_frames(
                    || {
                        let (frame, sample) = stage.render_frame(|| {
                            recorder.before_internal(&voice);
                            let sample = step_audio(&mut voice, &mut pattern)?;
                            recorder.after_internal(&voice);
                            Ok((sample.radiation.radiation_flow_derivative_cm3_s2, sample))
                        })?;
                        recorder.output(&voice, &sample, frame.pcm)?;
                        Ok(frame)
                    },
                    output_rate,
                    frames,
                    factor,
                    block_frames,
                    wave,
                    trace,
                )?;
                return recorder.write(path);
            }
            pcm::write(
                || {
                    step_audio(&mut voice, &mut pattern)
                        .map(|s| s.radiation.radiation_flow_derivative_cm3_s2)
                },
                stage,
                output_rate,
                samples,
                block_frames,
                wave,
                trace,
            )
        }
        Destination::Inspect => unreachable!(),
    }
}

enum TractTrace {
    Grid,
    Posture,
    Cells { acoustics: bool },
}

fn render_tract_profile(
    path: &Path,
    voice: &mut ArticulatedVoice,
    selected: &[usize],
    factor: usize,
    trace: TractTrace,
) -> Result<(), Box<dyn Error>> {
    use vocal_core::anatomy::AreaSample;

    let mut out = BufWriter::new(File::create_new(path)?);
    let acoustics = matches!(trace, TractTrace::Cells { acoustics: true });
    let grid = matches!(trace, TractTrace::Grid);
    match trace {
        TractTrace::Grid => write!(out, "frame,ray,{}", AreaSample::COLUMN_NAMES.join(","))?,
        TractTrace::Posture => {
            write!(out, "frame")?;
            for key in Articulator::ALL {
                write!(out, ",{}", key.name())?;
            }
        }
        TractTrace::Cells { .. } => {
            write!(out, "frame,tube,cell,length_cm,area_cm2,minimum_area_cm2")?
        }
    }
    if acoustics {
        write!(out, ",pressure_dyn_cm2,outward_flow_cm3_s")?;
    }
    writeln!(out)?;
    let [pharynx, _] = voice.airway().tract_section_counts();
    let mut rendered = 0;
    for &frame in selected {
        while rendered <= frame {
            for _ in 0..factor {
                voice.step()?;
            }
            rendered += 1;
        }
        if matches!(trace, TractTrace::Posture) {
            // 接触処理後に確定した調音器の値を保存する。格子と同じ内部ステップを通る。
            write!(out, "{frame}")?;
            for key in Articulator::ALL {
                write!(out, ",{}", voice.articulators().state(key).position)?;
            }
            writeln!(out)?;
            continue;
        }
        if grid {
            for (i, sample) in voice.tract_area_samples().iter().enumerate() {
                write!(out, "{frame},{i}")?;
                for value in sample.measurement_values() {
                    write!(out, ",{value}")?;
                }
                writeln!(out)?;
            }
            continue;
        }
        let airway = voice.airway();
        for (i, (cell, [pressure, flow])) in airway
            .tract_sections()
            .zip(airway.tract_acoustics())
            .enumerate()
        {
            let (tube, index) = if i < pharynx {
                ("pharynx", i)
            } else {
                ("oral", i - pharynx)
            };
            write!(
                out,
                "{frame},{tube},{index},{},{},{}",
                cell.length_cm, cell.area_cm2, cell.minimum_area_cm2
            )?;
            if acoustics {
                write!(out, ",{pressure},{flow}")?;
            }
            writeln!(out)?;
        }
    }
    out.flush()?;
    Ok(())
}

#[derive(Default)]
struct TraceFeatures {
    smoothed_pitch: bool,
    beatbox: bool,
    labiodental: bool,
    pharynx_minimum: bool,
    constriction_geometry: bool,
    inward_jet: bool,
    constriction_position: bool,
    oral_cell_acoustics: bool,
    oral_frication: bool,
    glottal: bool,
    glottal_stop: bool,
    velum: bool,
    oral_cells: bool,
    oral_branch_flows: bool,
    oral_posture: bool,
    jaw_position: bool,
    lower_lip_edge: bool,
    lateral: bool,
    tip_curl: bool,
    tongue_root: bool,
}

impl TraceFeatures {
    fn from_symbols<'a>(symbols: impl Iterator<Item = &'a TimedSegment>) -> Self {
        let mut features = Self::default();
        for symbol in symbols {
            let ipa = symbol.segment.ipa.as_str();
            let glide = matches!(ipa, "j" | "ɰ");
            let observe_dorsum = glide || matches!(ipa, "k" | "g" | "ŋ" | "x");
            let affricate = matches!(ipa, "ts" | "tɕ" | "dʑ" | "tʃ" | "dʒ" | "tʂ");
            let tap = ipa == "ɾ";
            let dental = matches!(ipa, "θ" | "ð");
            let labiodental = matches!(ipa, "f" | "v");
            let retroflex = matches!(ipa, "ʂ" | "tʂ");
            let rhotic = matches!(ipa, "ɹ" | "ɻ");
            let glottal_stop = ipa == "ʔ";
            let sibilant_posture = matches!(ipa, "ʃ" | "ɕ" | "ʑ") || retroflex || affricate;
            features.oral_frication |=
                sibilant_posture || dental || labiodental || matches!(ipa, "s" | "z" | "x");
            features.labiodental |= labiodental;
            features.lower_lip_edge |= labiodental;
            features.glottal |= matches!(ipa, "h" | "ɦ");
            features.glottal_stop |= glottal_stop;
            features.velum |= matches!(ipa, "m" | "n" | "ŋ");
            features.oral_cells |= observe_dorsum
                || sibilant_posture
                || tap
                || dental
                || labiodental
                || rhotic
                || glottal_stop
                || matches!(ipa, "t" | "d" | "n" | "w" | "l" | "ɫ");
            features.oral_posture |= observe_dorsum
                || sibilant_posture
                || tap
                || rhotic
                || matches!(ipa, "w" | "l" | "ɫ");
            features.oral_branch_flows |= affricate || tap;
            features.pharynx_minimum |= observe_dorsum || rhotic;
            features.constriction_geometry |= ipa == "x" || retroflex;
            features.jaw_position |= glide || sibilant_posture;
            features.lateral |= matches!(ipa, "l" | "ɫ");
            features.tip_curl |= retroflex || rhotic;
            features.tongue_root |= ipa == "ɹ";
        }
        features
    }
}

fn noise_header(out: &mut impl Write) -> io::Result<()> {
    write!(
        out,
        ",noise_cell,noise_minimum_cm2,noise_teeth_distance_cm,noise_jet_area_cm2,noise_jet_flow_cm3_s"
    )?;
    for prefix in ["glottis_noise", "constriction_noise", "teeth_noise"] {
        for field in [
            "source",
            "forward",
            "reverse",
            "gain",
            "lowpass_hz",
            "level",
            "forward_pressure",
            "reverse_pressure",
        ] {
            write!(out, ",{prefix}_{field}")?;
        }
    }
    Ok(())
}

/// 狭窄乱流の枝を咽頭・口腔の先頭から数える。枝が未登録なら −1。
fn constriction_noise_tract_cell(airway: &HumanAirway) -> isize {
    let Some(spec) = airway.network.noise_spec(1) else {
        return -1;
    };
    let mut offset = 0;
    for tube in &airway.tubes[1..=2] {
        if tube.branches.contains(&spec.source) {
            return (offset + spec.source - tube.branches.start) as isize;
        }
        offset += tube.nodes.len();
    }
    -1
}

fn noise_row(out: &mut impl Write, airway: &HumanAirway) -> io::Result<()> {
    let geometry = airway.frication_geometry();
    let network = &airway.network;
    let cell = geometry.narrowest_cell.map_or(-1, |index| index as isize);
    write!(
        out,
        ",{cell},{},{},{},{}",
        geometry.minimum_area_cm2,
        geometry.teeth_distance_cm,
        geometry.jet_area_cm2,
        geometry.jet_flow_cm3_s
    )?;
    for i in 0..3 {
        if let Some(spec) = network.noise_spec(i) {
            let source = if spec.source == airway.glottis_port {
                -2
            } else {
                spec.source as isize
            };
            write!(
                out,
                ",{source},{},{},{},{},{},{},{}",
                spec.forward,
                spec.reverse,
                spec.gain,
                spec.lowpass_hz,
                network.noise_level(i).unwrap_or(0.0),
                network.branch_noise_pressure(spec.forward),
                network.branch_noise_pressure(spec.reverse)
            )?;
        } else {
            write!(out, ",-1,-1,-1,0,0,0,0,0")?;
        }
    }
    Ok(())
}
