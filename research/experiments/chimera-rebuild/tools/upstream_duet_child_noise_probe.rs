//! 固定上流の歌唱声部を通常の歌唱設定から描画して比較用の列を出す。

mod duet_child_noise_trace;

use chimera::{
    anatomy::human::{ArticKey, BodyMix},
    phonetics::{
        english::EnglishG2P,
        sing::{SongOptions, SungNote, midi_to_hz, plan_song},
        syllables::{English, read_lyrics},
    },
    voice::human_voice::{HumanVoice, SourcePatch},
};
use serde_json::Value;
use std::{
    error::Error,
    fs::{self, File},
    io::{BufWriter, Write},
};

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let (args, radiation_path) = duet_child_noise_trace::trace_arg(&args, "--radiation-components");
    let (args, output_path) = duet_child_noise_trace::trace_arg(args, "--output-trace");
    let (case, dict, count, variant, trace_path, pcm_path, startup_path) = match args {
        [case, dict, count, variant, trace, pcm] => (case, dict, count, variant, trace, pcm, None),
        [case, dict, count, variant, trace, pcm, startup] => {
            (case, dict, count, variant, trace, pcm, Some(startup))
        }
        _ => {
            return Err(
                "ケース、辞書、観測点数、条件、CSV、PCMと、必要なら初期状態CSVを指定してください"
                    .into(),
            );
        }
    };
    let (drift, jitter, shimmer) = match variant.as_str() {
        "default" => (false, false, false),
        "without_drift" => (true, false, false),
        "without_jitter" => (false, true, false),
        "without_shimmer" => (false, false, true),
        "without_all_three" => (true, true, true),
        _ => return Err("音源の条件名が不正です".into()),
    };
    let case: Value = serde_json::from_slice(&fs::read(case)?)?;
    let body: BodyMix = serde_json::from_value(case["body"].clone())?;
    let score = &case["score"];
    let rate = case["sample_rate_hz"]
        .as_f64()
        .ok_or("出力レートがありません")?;
    let number = |key: &str| -> Result<f64, String> {
        score[key]
            .as_f64()
            .ok_or_else(|| format!("譜面の設定がありません ({key})"))
    };
    let mut lexicon = EnglishG2P::new();
    lexicon.load_dict(&fs::read_to_string(dict)?);
    let syllables = read_lyrics(
        score["lyrics"].as_str().ok_or("歌詞がありません")?,
        &[&English(&lexicon)],
    );
    let notes: Vec<[f64; 2]> = serde_json::from_value(score["notes"].clone())?;
    if notes.is_empty() || notes.len() != syllables.len() {
        return Err("音符と音節の数が一致しません".into());
    }
    let f0 = midi_to_hz(notes[0][0]);
    let notes: Vec<_> = notes
        .into_iter()
        .zip(syllables)
        .map(|([midi, beats], syl)| SungNote { midi, beats, syl })
        .collect();
    let plan = plan_song(
        &notes,
        &SongOptions {
            body,
            bpm: number("bpm")?,
            t0: number("t0")?,
            vibrato: number("vibrato")?,
        },
    );
    let mut voice = HumanVoice::new(rate, body.body(), 2);
    if let Some(gain) = case.get("probe_output_gain") {
        voice.output_gain = gain
            .as_f64()
            .filter(|gain| gain.is_finite() && *gain >= 0.0)
            .ok_or("観測用の出力ゲインには有限の非負値を指定してください")?;
    }
    voice.set_source(&SourcePatch {
        f0: Some(f0),
        voiced: Some(true),
        pressure: Some(9.0),
        tension: Some(0.55),
        drift: drift.then_some(0.0),
        ..Default::default()
    });
    if jitter {
        voice.glottis.params.jitter = 0.0;
    }
    if shimmer {
        voice.glottis.params.shimmer = 0.0;
    }
    serde_json::to_writer(std::io::stdout().lock(), &plan.gestures)?;
    voice.schedule(&plan.gestures);
    let mut trace = BufWriter::new(File::create_new(trace_path)?);
    writeln!(trace, "{}", duet_child_noise_trace::HEADER)?;
    let mut pcm = BufWriter::new(File::create_new(pcm_path)?);
    let mut output_trace = output_path
        .map(File::create_new)
        .transpose()?
        .map(BufWriter::new);
    let mut radiation_trace = radiation_path
        .map(File::create_new)
        .transpose()?
        .map(BufWriter::new);
    if let Some(out) = &mut radiation_trace {
        writeln!(out, "{}", duet_child_noise_trace::RADIATION_HEADER)?;
    }
    let count = count.parse::<usize>()?;
    let frames = ((plan.end + 0.4) * rate).round() as usize;
    let mut startup = startup_path
        .map(File::create_new)
        .transpose()?
        .map(BufWriter::new);
    if let Some(out) = &mut startup {
        writeln!(out, "{}", duet_child_noise_trace::STARTUP_HEADER)?;
        write_startup(out, &voice, 0)?;
    }
    let mut sample = [0.0f32];
    for frame in 0..frames {
        voice.render(&mut sample);
        pcm.write_all(&sample[0].to_le_bytes())?;
        if let Some(out) = &mut output_trace {
            duet_child_noise_trace::write_output_row(
                out,
                voice.probe_radiation_pair,
                voice.probe_output,
            )?;
        }
        if frame < count {
            if let Some(out) = &mut radiation_trace {
                duet_child_noise_trace::write_radiation_pair(
                    out,
                    frame,
                    voice.probe_radiation_components,
                )?;
            }
            if let Some(out) = &mut startup {
                write_startup(out, &voice, frame + 1)?;
            }
            let air = &voice.airway;
            let net = &air.net;
            let mut max = (0.0, -1.0);
            let sources = net.noise_sources();
            for source in sources {
                if source.level > max.0 {
                    max = (source.level, source.src as f64);
                }
            }
            let first = sources
                .first()
                .filter(|source| source.src == air.glottis_port)
                .ok_or("声門の乱流枝がありません")?;
            let [area, flow] = net.probe_first_noise_drive;
            duet_child_noise_trace::write_row(
                &mut trace,
                frame,
                [
                    voice.artic.x.get(ArticKey::LipAp),
                    net.area[air.oral.last_node()],
                    net.area[air.pharynx.first_node()],
                    voice.gate,
                    voice.glottis.f0_now,
                    voice.glottis.cycle_phase(),
                    voice.glottis.area,
                    area,
                    flow,
                    first.level,
                    first.gain,
                    max.0,
                    max.1,
                ],
            )?;
        }
    }
    pcm.flush()?;
    trace.flush()?;
    if let Some(out) = &mut startup {
        out.flush()?;
    }
    if let Some(out) = &mut output_trace {
        out.flush()?;
    }
    if let Some(out) = &mut radiation_trace {
        out.flush()?;
    }
    Ok(())
}

fn write_startup(out: &mut impl Write, voice: &HumanVoice, sample: usize) -> std::io::Result<()> {
    let bank = &voice.artic;
    let air = &voice.airway;
    let net = &air.net;
    duet_child_noise_trace::write_row(
        out,
        sample,
        [
            bank.x.tt_x,
            bank.x.tt_y,
            bank.target.tt_x,
            bank.target.tt_y,
            bank.v[ArticKey::TtX.index()],
            bank.v[ArticKey::TtY.index()],
            net.area[air.oral.last_node()],
            net.area[air.pharynx.first_node()],
            net.u[air.glottis_port],
            net.out,
        ],
    )
}
