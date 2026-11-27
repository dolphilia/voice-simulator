//! ページ側で使う発話・歌唱プランナーと、調音スコアの数値形式。
use std::{cell::RefCell, ptr};

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use vocal_core::{
    anatomy::{BodyMix, BodyName},
    phonetics::{
        english::{self, English},
        ipa_plan, song,
        speech::speech_gestures,
        syllables::Syllable,
        timing::TimedSegment,
    },
    score::{CONTROL_COUNT, ControlKey, Gesture, Targets},
};

pub(crate) const SCORE_WORDS: usize = 7 + CONTROL_COUNT;
pub(crate) const MAX_GESTURES: usize = 4000;

#[cfg(all(test, not(target_arch = "wasm32"), feature = "render-allocation-probe"))]
pub(crate) mod allocation;
mod report;

macro_rules! plan_step {
    ($phase:ident, $operation:expr) => {{
        #[cfg(all(test, not(target_arch = "wasm32"), feature = "render-allocation-probe"))]
        let _allocation = allocation::scope(allocation::Phase::$phase);
        $operation
    }};
}

type Prepared = (Value, Vec<Gesture>);

#[derive(Default)]
struct PlanBuffers {
    input: Vec<u8>,
    dictionary: Vec<u8>,
    report: Vec<u8>,
    score: Vec<f64>,
}

thread_local! {
    static PLAN: RefCell<PlanBuffers> = RefCell::default();
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SongInput {
    id: String,
    lyrics: Option<String>,
    syllables: Option<Vec<Syllable>>,
    notes: Vec<song::Note>,
    bpm: f64,
    start_seconds: f64,
    vibrato_cents: f64,
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_plan_input(bytes: usize) -> *mut u8 {
    if !(1..=32_768).contains(&bytes) {
        return ptr::null_mut();
    }
    PLAN.with_borrow_mut(|plan| {
        plan.input.resize(bytes, 0);
        plan.input.as_mut_ptr()
    })
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_plan_dictionary(bytes: usize) -> *mut u8 {
    if !(1..=8 * 1024 * 1024).contains(&bytes) {
        return ptr::null_mut();
    }
    PLAN.with_borrow_mut(|plan| {
        plan.dictionary.resize(bytes, 0);
        plan.dictionary.as_mut_ptr()
    })
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_song_dictionary(bytes: usize) -> *mut u8 {
    vocal_plan_dictionary(bytes)
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_ipa_plan(start: f64, rate: f64, f0: f64) -> usize {
    run_ipa_plan(start, rate, f0, BodyName::Male.into())
}

/// 省略されたF0（NaN）は、IPAの既定音高へ解決する。
#[unsafe(no_mangle)]
pub extern "C" fn vocal_ipa_plan_with_body(
    start: f64,
    rate: f64,
    f0: f64,
    female: f64,
    child: f64,
) -> usize {
    let body = BodyMix::new(female, child);
    let f0 = if f0.is_nan() {
        body.default_f0_hz()
    } else {
        f0
    };
    run_ipa_plan(start, rate, f0, body)
}

fn run_ipa_plan(start: f64, rate: f64, f0: f64, body: BodyMix) -> usize {
    PLAN.with_borrow_mut(|plan| {
        let prepared = prepare_ipa(&plan.input, start, rate, f0, body).map_err(str::to_owned);
        plan.store(prepared)
    })
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_english_plan(start: f64, rate: f64, f0: f64) -> usize {
    run_english_plan(start, rate, f0, BodyName::Male.into())
}

/// 体型を適用し、基準F0の省略（NaN）には英語ケースの既定音高を使う。
#[unsafe(no_mangle)]
pub extern "C" fn vocal_english_plan_with_body(
    start: f64,
    rate: f64,
    f0: f64,
    female: f64,
    child: f64,
) -> usize {
    let body = BodyMix::new(female, child);
    let f0 = if f0.is_nan() {
        english::default_f0_hz(body)
    } else {
        f0
    };
    run_english_plan(start, rate, f0, body)
}

fn run_english_plan(start: f64, rate: f64, f0: f64, body: BodyMix) -> usize {
    PLAN.with_borrow_mut(|plan| {
        let prepared = prepare_english(&plan.input, &plan.dictionary, start, rate, f0, body);
        plan.store(prepared)
    })
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_song_plan() -> usize {
    run_song_plan(BodyName::Male.into())
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_song_plan_with_body(female: f64, child: f64) -> usize {
    run_song_plan(BodyMix::new(female, child))
}

fn run_song_plan(body: BodyMix) -> usize {
    PLAN.with_borrow_mut(|plan| {
        let prepared = prepare_song(&plan.input, &plan.dictionary, body);
        plan.store(prepared)
    })
}

/// 譜面や調音スコアを作らず、歌詞を歌唱用の音節へ変換する。
#[unsafe(no_mangle)]
pub extern "C" fn vocal_lyric_syllables() -> usize {
    PLAN.with_borrow_mut(|plan| {
        let result = (|| {
            let text = str::from_utf8(&plan.input).map_err(|_| "歌詞をUTF-8として読めません")?;
            let dictionary = dictionary_lexicon(&plan.dictionary)?;
            Ok((json!(song::lyric_syllables(text, &dictionary)), Vec::new()))
        })();
        plan.store(result)
    })
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_plan_report() -> *const u8 {
    PLAN.with_borrow(|plan| plan.report.as_ptr())
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_plan_score() -> *const f64 {
    PLAN.with_borrow(|plan| plan.score.as_ptr())
}

#[unsafe(no_mangle)]
pub extern "C" fn vocal_plan_score_words() -> usize {
    PLAN.with_borrow(|plan| plan.score.len())
}

impl PlanBuffers {
    fn store<P: Serialize>(&mut self, prepared: Result<(P, Vec<Gesture>), String>) -> usize {
        self.score.clear();
        let error = match &prepared {
            Ok((report, gestures)) if gestures.len() <= MAX_GESTURES => {
                plan_step!(ScoreWords, {
                    self.score.reserve(gestures.len() * SCORE_WORDS);
                    for g in gestures {
                        self.score.extend([
                            g.t0,
                            g.t1,
                            g.ramp_in,
                            g.ramp_out,
                            g.strength,
                            g.speed.unwrap_or(f64::NAN),
                            g.release_hold.unwrap_or(f64::NAN),
                        ]);
                        self.score.extend(
                            ControlKey::all().map(|key| g.targets.get(key).unwrap_or(f64::NAN)),
                        );
                    }
                });
                let report = plan_step!(ReportValue, report::PlanReport::new(report, gestures));
                if self.write_report(&report).is_ok() {
                    return self.report.len();
                }
                self.score.clear();
                "調音スコアの報告をJSONに変換できません"
            }
            Ok(_) => "調音ジェスチャー数が上限を超えました",
            Err(error) => error.as_str(),
        };
        self.write_report(&report::ErrorReport { error })
            .expect("文字列だけのエラー報告をバイト列に書ける");
        self.report.len()
    }

    fn write_report(&mut self, report: &impl Serialize) -> Result<(), serde_json::Error> {
        plan_step!(ReportJson, {
            self.report.clear();
            // 最初は serde_json::to_vec と同じ容量で書き始める。
            self.report.reserve(128);
            serde_json::to_writer(&mut self.report, report)
        })
    }
}

fn prepare_ipa(
    input: &[u8],
    start: f64,
    rate: f64,
    f0: f64,
    body: BodyMix,
) -> Result<Prepared, &'static str> {
    if !f0.is_finite() || f0 <= 0.0 {
        return Err("基準F0には有限の正の値を指定してください");
    }
    let text = str::from_utf8(input).map_err(|_| "IPA入力はUTF-8で指定してください")?;
    let plan = ipa_plan::plan(Some(text), None, Some(start), rate)?;
    if !plan
        .utterances
        .iter()
        .any(|span| !span.timing.segments.is_empty())
    {
        return Err("発声できるIPA音素がありません");
    }
    let mut gestures = Vec::new();
    for span in &plan.utterances {
        gestures.extend(speech_gestures(&span.timing, span.start_seconds, f0, body)?);
    }
    let noise_scale = noise_scale(
        plan.utterances
            .iter()
            .flat_map(|span| &span.timing.segments),
    );
    let glide = body.preset() != Some(BodyName::Male) || f0 != english::INITIAL_VOICE_F0_HZ;
    Ok((
        json!({
            "speech": {"utterances": plan.utterances, "render_end_seconds": plan.render_end_seconds, "rate": rate},
            "noise_scale": noise_scale,
            "base_pitch_hz": f0,
            "initial_pitch_hz": if glide { english::INITIAL_VOICE_F0_HZ } else { f0 },
            "glide_from_initial": glide,
        }),
        gestures,
    ))
}

fn noise_scale<'a>(mut symbols: impl Iterator<Item = &'a TimedSegment>) -> Option<f64> {
    symbols
        .any(|s| {
            matches!(
                s.segment.ipa.as_str(),
                "s" | "z"
                    | "ʃ"
                    | "ɕ"
                    | "ʑ"
                    | "ʂ"
                    | "f"
                    | "v"
                    | "θ"
                    | "ð"
                    | "x"
                    | "ts"
                    | "tɕ"
                    | "dʑ"
                    | "tʃ"
                    | "dʒ"
                    | "tʂ"
                    | "h"
                    | "ɦ"
            )
        })
        .then_some(1.0)
}

fn dictionary_lexicon(dictionary: &[u8]) -> Result<English<'_>, &'static str> {
    let dictionary = str::from_utf8(dictionary).map_err(|_| "発音辞書をUTF-8として読めません")?;
    let lexicon = English::with_dictionary(dictionary);
    if lexicon.dictionary_entries() == 0 {
        return Err("発音辞書に有効な項目がありません");
    }
    Ok(lexicon)
}

fn prepare_english(
    input: &[u8],
    dictionary: &[u8],
    start: f64,
    rate: f64,
    f0: f64,
    body: BodyMix,
) -> Result<(report::EnglishReport, Vec<Gesture>), String> {
    let text = plan_step!(
        SpeechPlan,
        str::from_utf8(input).map_err(|_| String::from("英語入力はUTF-8で指定してください"))
    )?;
    let lexicon = plan_step!(DictionaryIndex, dictionary_lexicon(dictionary))?;
    let (plan, gestures) = plan_step!(
        SpeechPlan,
        english::plan_voice_with_body(&lexicon, text, start, rate, f0, body)
    )?;
    if plan.phrases.is_empty() {
        return Err("発声できる英語の語がありません".into());
    }
    let noise_scale = noise_scale(plan.phrases.iter().flat_map(|span| &span.timing.segments));
    Ok((
        plan_step!(
            SpeechValue,
            report::EnglishReport {
                base_pitch_hz: f0,
                initial_pitch_hz: english::INITIAL_VOICE_F0_HZ,
                noise_scale,
                speech: plan,
            }
        ),
        gestures,
    ))
}

fn prepare_song(input: &[u8], dictionary: &[u8], body: BodyMix) -> Result<Prepared, String> {
    let request: SongInput = serde_json::from_slice(input)
        .map_err(|error| format!("歌唱入力の形式が不正です（{error}）"))?;
    let syllables = match (request.lyrics, request.syllables) {
        (Some(lyrics), None) => song::lyric_syllables(&lyrics, &dictionary_lexicon(dictionary)?),
        (None, Some(syllables)) => syllables,
        _ => return Err("歌詞または音節を一方だけ指定してください".into()),
    };
    let plan = song::plan(
        &syllables,
        &request.notes,
        request.bpm,
        request.start_seconds,
    )?;
    if !plan.unavailable_speech_symbols.is_empty() {
        return Err(format!(
            "歌唱に未対応の音素があります ({})",
            plan.unavailable_speech_symbols.join(" ")
        ));
    }
    let base_pitch_hz = plan
        .notes
        .first()
        .ok_or("歌唱する音符を指定してください")?
        .f0_hz;
    let gestures = song::score_with_body(&plan, request.vibrato_cents, body)?;
    let report = json!({
        "song": {"id": request.id, "syllables": syllables, "plan": plan},
        "noise_scale": 1.0,
        "base_pitch_hz": base_pitch_hz,
        "initial_pitch_hz": 110.0,
    });
    Ok((report, gestures))
}

/// 調音用の数値列を復元する。文字の観測ラベルはメインスレッドのJSONに持つ。
pub(crate) fn decode_score(words: &[f64]) -> Vec<Gesture> {
    let optional = |x: f64| (!x.is_nan()).then_some(x);
    words
        .chunks_exact(SCORE_WORDS)
        .map(|row| {
            let mut targets = Targets::default();
            for (key, value) in ControlKey::all().zip(row[7..].iter().copied()) {
                if let Some(value) = optional(value) {
                    targets.set(key, value);
                }
            }
            Gesture {
                t0: row[0],
                t1: row[1],
                ramp_in: row[2],
                ramp_out: row[3],
                strength: row[4],
                speed: optional(row[5]),
                release_hold: optional(row[6]),
                targets,
                label: None,
            }
        })
        .collect()
}
