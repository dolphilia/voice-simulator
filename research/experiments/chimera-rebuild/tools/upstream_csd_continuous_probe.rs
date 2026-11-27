//! 固定版のCSDと同じ順で句を予約し、単一の声の状態とPCMを観測する。

use chimera::{
    anatomy::human::{ArticPatch, BODY_FEMALE},
    math::midi_to_hz,
    phonetics::{
        Syllable,
        sing::{SongOptions, SungNote, plan_song},
    },
    voice::human_voice::{HumanVoice, SourcePatch},
};
use serde_json::{Value, json};
use std::{
    error::Error,
    fs::{self, File},
    io::{BufWriter, Write},
};

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let [case, mode, samples, trace, score] = args.as_slice() else {
        return Err(
            "ケース、standard または matched、PCM、状態、スコアの保存先を指定してください".into(),
        );
    };
    if !matches!(mode.as_str(), "standard" | "matched") {
        return Err("観測条件が不正です".into());
    }
    let case: Value = serde_json::from_slice(&fs::read(case)?)?;
    let spec = &case["song_voice"];
    let settings = &spec["voice"];
    let number = |table: &Value, key: &str| table[key].as_f64().ok_or("観測の設定値がありません");
    let rates = (
        number(settings, "output_sample_rate_hz")?,
        number(spec, "internal_sample_rate_hz")?,
    );
    if spec["body"] != "female" || rates != (48_000.0, 96_000.0) {
        return Err("成人女性、出力48 kHz・内部96 kHzの条件を指定してください".into());
    }
    let duration = number(spec, "render_end_seconds")?;
    let frames = (rates.0 * duration).round() as usize;
    let phrases = spec["scores"].as_array().ok_or("句の配列がありません")?;
    let first_midi = phrases
        .first()
        .and_then(|phrase| phrase["notes"][0]["midi"].as_f64())
        .ok_or("冒頭の音符がありません")?;
    let mut voice = HumanVoice::new(rates.0, BODY_FEMALE, 2);
    let mut source = SourcePatch {
        f0: Some(midi_to_hz(first_midi)),
        voiced: Some(true),
        pressure: Some(number(settings, "pressure_cm_h2o")?),
        tension: Some(number(settings, "tension")?),
        ..Default::default()
    };
    if mode == "matched" {
        let pose = &spec["posture"];
        let initial: ArticPatch = serde_json::from_value(json!({
            "jaw":pose["jaw_cm"], "tbX":pose["tongue_body_cm"][0], "tbY":pose["tongue_body_cm"][1],
            "ttX":pose["tongue_tip_cm"][0], "ttY":pose["tongue_tip_cm"][1], "ttCurl":pose["tip_curl"],
            "root":pose["tongue_root_cm"], "lipAp":pose["lip_aperture_cm"], "lipProt":pose["lip_protrusion_cm"],
            "lipWidth":pose["lip_spread"], "labiodental":pose["labiodental"], "velum":pose["velum_cm2"],
            "larynx":pose["larynx_cm"], "dorsum":pose["dorsum"],
        }))?;
        voice.artic.snap(&initial);
        voice.airway.apply(&voice.artic.x, 0.0);
        voice.airway.net.snap_to_targets();
        source.drift = Some(0.0);
        source.breathiness = Some(number(settings, "breathiness")?);
        voice.output_gain = number(settings, "output_gain")?;
    }
    voice.set_source(&source);
    if mode == "matched" {
        voice.glottis.params.jitter = 0.0;
        voice.glottis.params.shimmer = 0.0;
    }
    let mut plans = Vec::new();
    for phrase in phrases {
        let syllables: Vec<Syllable> = serde_json::from_value(phrase["syllables"].clone())?;
        let raw = phrase["notes"].as_array().ok_or("句に音符がありません")?;
        if raw.len() != syllables.len() {
            return Err("音符と音節の数が違います".into());
        }
        let notes = raw
            .iter()
            .zip(syllables)
            .map(|(row, syl)| {
                Ok(SungNote {
                    midi: number(row, "midi")?,
                    beats: number(row, "beats")?,
                    syl,
                })
            })
            .collect::<Result<Vec<_>, &str>>()?;
        let plan = plan_song(
            &notes,
            &SongOptions {
                body: "female".into(),
                t0: number(phrase, "start_seconds")?,
                bpm: number(phrase, "bpm")?,
                vibrato: number(spec, "vibrato_cents")?,
            },
        );
        voice.schedule(&plan.gestures);
        plans.push(json!({"id":phrase["id"], "segments":plan.segments, "gestures":plan.gestures}));
    }
    fs::write(
        score,
        serde_json::to_vec(&json!({"plans": plans, "dropped": voice.score.dropped}))?,
    )?;
    let mut pcm = BufWriter::new(File::create_new(samples)?);
    let mut state = BufWriter::new(File::create_new(trace)?);
    writeln!(
        state,
        "frame,gate,smoothed_f0_hz,glottal_f0_hz,glottal_area_cm2,glottal_flow_cm3_s,lip_flow_cm3_s,radiation_derivative_cm3_s2"
    )?;
    let mut one = [0.0f32];
    for frame in 0..frames {
        voice.render(&mut one);
        pcm.write_all(&one[0].to_le_bytes())?;
        let net = &voice.airway.net;
        writeln!(
            state,
            "{frame},{},{},{},{},{},{},{}",
            voice.gate,
            voice.glottis.params.f0,
            voice.glottis.f0_now,
            voice.glottis.area,
            net.u[voice.airway.glottis_port],
            net.radiated_flow(voice.airway.rad_lips),
            net.out
        )?;
    }
    pcm.flush()?;
    state.flush()?;
    Ok(())
}
