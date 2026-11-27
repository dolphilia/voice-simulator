//! 保存済みの英語ケースを通常の描画ABIで再生するネイティブ診断。

use super::*;
use serde_json::Value;
use std::{fs, path::Path};
use vocal_core::render_allocation_probe as probe;

fn counted<T>(operation: impl FnOnce() -> T) -> (T, usize) {
    let before = ALLOCATIONS.get();
    let value = operation();
    (value, ALLOCATIONS.get() - before)
}

fn read_json(path: &Path) -> Value {
    serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
}

#[test]
fn english_tsp_allocation_profile() {
    let Some(directory) = std::env::var_os("CHIMERA_SPEECH_ALLOCATION_PROBE_OUTPUT") else {
        return;
    };
    let directory = Path::new(&directory);
    let fixture = read_json(&directory.join("input.json"));
    let spec: Value = serde_json::from_str(include_str!(
        "../../../../cases/worklet-live-tsp-allocation-44100.json"
    ))
    .unwrap();
    let input = &fixture["speech_voice"];
    let request = &input["input"];
    assert_eq!(request["id"], spec["recording_id"]);
    assert_eq!(input["body"], "female");
    assert_eq!(
        input["internal_sample_rate_hz"],
        spec["measurement"]["internal_rate_hz"]
    );
    assert_eq!(
        input["voice"]["output_sample_rate_hz"],
        spec["measurement"]["output_rate_hz"]
    );
    let text = request["text"].as_str().unwrap().as_bytes();
    let mut dictionary = Vec::new();
    std::io::Read::read_to_end(
        &mut flate2::read::GzDecoder::new(&include_bytes!("../../../../data/cmudict.txt.gz")[..]),
        &mut dictionary,
    )
    .unwrap();
    let (_, input_words) = counted(|| write_planner_input(text));
    let (_, dictionary_buffer) = counted(|| {
        let destination = planning::vocal_plan_dictionary(dictionary.len());
        assert!(!destination.is_null());
        // このスレッド内で確保した辞書領域を英語プランナーに渡す。
        unsafe {
            std::slice::from_raw_parts_mut(destination, dictionary.len())
                .copy_from_slice(&dictionary);
        }
    });
    let start = request["start_seconds"].as_f64().unwrap();
    let rate = request["rate"].as_f64().unwrap();
    let pitch = input["voice"]["f0_hz"].as_f64();
    if std::env::var_os("CHIMERA_SPEECH_PLAN_PREWARM").is_some() {
        use vocal_core::phonetics::english::{self, English};

        let tsv = std::str::from_utf8(&dictionary).unwrap();
        let text = std::str::from_utf8(text).unwrap();
        let body = BodyMix::new(1.0, 0.0);
        let f0 = pitch.unwrap_or_else(|| english::default_f0_hz(body));
        let (lexicon, index_count) = counted(|| English::with_dictionary(tsv));
        let (result, plan_count) =
            counted(|| english::plan_voice_with_body(&lexicon, text, start, rate, f0, body));
        assert!(result.is_ok());
        fs::write(
            directory.join("planner-prewarm.json"),
            serde_json::to_vec(&serde_json::json!({
                "dictionary_index": index_count, "speech_plan": plan_count,
            }))
            .unwrap(),
        )
        .unwrap();
    }
    let plan_english =
        || planning::vocal_english_plan_with_body(start, rate, pitch.unwrap_or(f64::NAN), 1.0, 0.0);
    let detailed = std::env::var_os("CHIMERA_SPEECH_PLAN_PHASES").is_some();
    let ((length, english_plan), cold_counts) = if detailed {
        let (result, phases) = planning::allocation::measure(|| counted(plan_english));
        (result, Some(phases))
    } else {
        (counted(plan_english), None)
    };
    assert!(length > 0);
    let plan = unsafe { std::slice::from_raw_parts(planning::vocal_plan_report(), length) };
    let data: Value = serde_json::from_slice(plan).unwrap();
    assert!(data.get("error").is_none(), "{data}");
    fs::write(directory.join("plan.json"), plan).unwrap();
    fs::write(
        directory.join("planner-counts.json"),
        serde_json::to_vec(&serde_json::json!({ "input_buffer":input_words, "dictionary_buffer":dictionary_buffer, "english_plan":english_plan })).unwrap(),
    )
    .unwrap();
    if let Some(cold_counts) = cold_counts {
        let cold_score = score_bytes();
        fs::write(directory.join("cold-score.f64le"), cold_score).unwrap();
        let ((repeat_length, repeat_total), repeat_counts) =
            planning::allocation::measure(|| counted(plan_english));
        assert!(repeat_length > 0);
        let repeat_plan =
            unsafe { std::slice::from_raw_parts(planning::vocal_plan_report(), repeat_length) };
        fs::write(directory.join("repeat-plan.json"), repeat_plan).unwrap();
        fs::write(directory.join("repeat-score.f64le"), score_bytes()).unwrap();

        let text = std::str::from_utf8(&dictionary).unwrap();
        let (direct, direct_count) =
            counted(|| vocal_core::phonetics::english::English::with_dictionary(text));
        fs::write(directory.join("planner-phases.json"), serde_json::to_vec(&serde_json::json!({
            "phase_names": planning::allocation::PHASE_NAMES,
            "cold": {"total": english_plan, "phases": cold_counts},
            "repeat": {"total": repeat_total, "phases": repeat_counts},
            "direct_dictionary": {"allocations": direct_count, "entries": direct.dictionary_entries()},
        })).unwrap()).unwrap();
    }
    let score = unsafe {
        std::slice::from_raw_parts(
            planning::vocal_plan_score(),
            planning::vocal_plan_score_words(),
        )
    };
    for mode in ["plain", "traced"] {
        record_render(
            directory,
            mode,
            input,
            &spec["measurement"],
            &data["plan"],
            score,
        );
    }
    if std::env::var_os("CHIMERA_SPEECH_REPORT_TRANSITIONS").is_some() {
        record_report_transitions(directory, text, plan_english);
    }
}

fn record_report_transitions(directory: &Path, original: &[u8], plan: impl Fn() -> usize) {
    let original_score = fs::read(directory.join("cold-score.f64le")).unwrap();
    let mut rows = Vec::new();
    for (name, text) in [
        ("short", b"A.".as_slice()),
        ("invalid_utf8", b"\xff".as_slice()),
        ("restored", original),
    ] {
        write_planner_input(text);
        let ((length, total), phases) = planning::allocation::measure(|| counted(&plan));
        // ABIが返した現在の出力範囲を、次に書き込む前に読む。
        let report = unsafe { std::slice::from_raw_parts(planning::vocal_plan_report(), length) };
        rows.push(serde_json::json!({
            "name": name,
            "length": length,
            "report": std::str::from_utf8(report).unwrap(),
            "score_words": planning::vocal_plan_score_words(),
            "score_matches_original": score_bytes() == original_score,
            "total": total,
            "phases": phases,
        }));
    }
    fs::write(
        directory.join("planner-report-transitions.json"),
        serde_json::to_vec(&rows).unwrap(),
    )
    .unwrap();
}

fn score_bytes() -> Vec<u8> {
    // 再計画で無効になるスコア領域を、このスレッドで直ちにバイト列に移す。
    let score = unsafe {
        std::slice::from_raw_parts(
            planning::vocal_plan_score(),
            planning::vocal_plan_score_words(),
        )
    };
    score.iter().copied().flat_map(f64::to_le_bytes).collect()
}

fn record_render(
    directory: &Path,
    mode: &str,
    input: &Value,
    spec: &Value,
    plan: &Value,
    score: &[f64],
) {
    let number = |name: &str| spec[name].as_u64().unwrap() as usize;
    let frames = number("output_frames");
    let quantum = number("quantum_frames");
    let stride = number("observation_stride_frames");
    let tract_stride = number("tract_stride_frames");
    let config = fixture_config(input, plan["initial_pitch_hz"].as_f64().unwrap());
    let variation = &input["source_variation"];
    let turbulence = &input["turbulence"];
    let (handle, handle_count) = counted(|| {
        vocal_new(
            number("internal_rate_hz") as u32,
            number("output_rate_hz") as u32,
        )
    });
    // 1スレッドで確保したハンドルと各ABI領域のみを扱う。
    unsafe {
        let (_, config_count) = counted(|| {
            std::slice::from_raw_parts_mut(vocal_config(handle), CONFIG_WORDS)
                .copy_from_slice(&config);
        });
        let (_, score_count) = counted(|| {
            let destination = vocal_score_buffer(handle, score.len());
            assert!(!destination.is_null());
            std::slice::from_raw_parts_mut(destination, score.len()).copy_from_slice(score);
        });
        let (started, command_count) = counted(|| {
            vocal_start_score_prepared(
                handle,
                turbulence["scale"]
                    .as_f64()
                    .unwrap_or(plan["noise_scale"].as_f64().unwrap()),
                plan["base_pitch_hz"].as_f64().unwrap(),
                1.0,
                0.0,
                turbulence["glottis_gain_multiplier"]
                    .as_f64()
                    .unwrap_or(1.0),
                turbulence["constriction_gain_multiplier"]
                    .as_f64()
                    .unwrap_or(1.0),
                turbulence["teeth_lowpass_floor_hz"].as_f64().unwrap_or(0.0),
                0,
                variation["pitch_drift_cents"].as_f64().unwrap(),
                variation["period_jitter"].as_f64().unwrap(),
                variation["amplitude_shimmer"].as_f64().unwrap(),
            )
        });
        assert_eq!(started, 1);
        let (_, trace_setup) = counted(|| {
            assert!(!vocal_glottal_trace_init(handle).is_null());
            assert!(!vocal_tract_init(handle).is_null());
        });

        let mut pcm = Vec::with_capacity(frames);
        let mut observations = Vec::with_capacity(frames.div_ceil(stride));
        let mut glottal = Vec::with_capacity(frames * GLOTTAL_TRACE_WORDS);
        let tract_words = (&(*handle).tract).len();
        let mut tract = Vec::with_capacity(frames.div_ceil(tract_stride) * (tract_words - 1));
        let mut totals = Vec::with_capacity(frames.div_ceil(quantum));
        let mut phases = Vec::with_capacity(frames.div_ceil(quantum));
        let mut render = || {
            let mut pos = 0;
            for end in (quantum..frames + quantum)
                .step_by(quantum)
                .map(|end| end.min(frames))
            {
                let (_, count) = counted(|| {
                    while pos < end {
                        let step = (end - pos)
                            .min(stride - pos % stride)
                            .min(tract_stride - pos % tract_stride);
                        assert_eq!(vocal_render(handle, step), 1);
                        pos += step;
                        let sampled = &*handle;
                        pcm.extend_from_slice(&sampled.pcm[..step]);
                        glottal.extend_from_slice(
                            &sampled.glottal_trace[..step * GLOTTAL_TRACE_WORDS],
                        );
                        if pos.is_multiple_of(stride) || pos == frames {
                            observations.push(sampled.observation);
                        }
                        if pos.is_multiple_of(tract_stride) || pos == frames {
                            assert_eq!(vocal_tract_snapshot(handle), 1);
                            tract.push((pos - 1) as f64);
                            tract.extend_from_slice(&(&*handle).tract[2..]);
                        }
                    }
                });
                totals.push(count);
                phases.push(probe::take_counts());
            }
        };
        if mode == "traced" {
            probe::trace(|| ALLOCATIONS.get(), render);
        } else {
            render();
        }
        assert_eq!(*vocal_observation(handle), frames as f64);
        vocal_free(handle);
        let bytes = |values: Vec<f64>| {
            values
                .into_iter()
                .flat_map(f64::to_le_bytes)
                .collect::<Vec<_>>()
        };
        fs::write(
            directory.join(format!("{mode}.f32le")),
            pcm.into_iter()
                .flat_map(f32::to_le_bytes)
                .collect::<Vec<_>>(),
        )
        .unwrap();
        for (name, data) in [
            (
                "observations",
                bytes(observations.into_iter().flatten().collect()),
            ),
            ("glottal", bytes(glottal)),
            ("tract", bytes(tract)),
        ] {
            fs::write(directory.join(format!("{mode}-{name}.f64le")), data).unwrap();
        }
        let report = serde_json::json!({
            "setup": {"handle": handle_count, "configuration": config_count, "score_buffer": score_count,
                      "start_score_prepared": command_count, "trace_setup": trace_setup},
            "phase_names": probe::PHASE_NAMES, "total_by_quantum": totals, "phase_counts": phases,
        });
        serde_json::to_writer(
            fs::File::create(directory.join(format!("{mode}-counts.json"))).unwrap(),
            &report,
        )
        .unwrap();
    }
}
