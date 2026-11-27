//! 固定上流の歌唱予約位置を変え、出力サンプルごとに声門・気道・放射を観測する。

use chimera::{
    anatomy::human::{ArticKey, ArticPatch, BodyMix, NEUTRAL, rest_tip},
    engine::Engine,
    phonetics::{
        english::EnglishG2P,
        sing::{SongOptions, SungNote, plan_song},
        syllables::{English, read_lyrics},
    },
    voice::human_voice::SourcePatch,
};
use serde_json::{Value, json};
use std::{
    error::Error,
    fs::{self, File},
    io::{BufWriter, Write},
    path::Path,
};

const TRACE_HEADER: &str = concat!(
    "relative_frame,absolute_frame,gate,lip_opening_cm,lip_area_cm2,lung_pressure_dyn_cm2,",
    "glottal_phase_cycles,glottal_f0_hz,glottal_voicing,glottal_area_cm2,glottal_flow_cm3_s,",
    "subglottal_pressure_dyn_cm2,supraglottal_pressure_dyn_cm2,",
    "dominant_noise_level,signed_noise_pressure_dyn_cm2,noise_pressure_branch,",
    "lip_radiation_cm3_s,nose_radiation_cm3_s,radiation_derivative_cm3_s2"
);

fn trace_row(
    out: &mut impl Write,
    engine: &Engine,
    absolute: i64,
    relative: i64,
) -> std::io::Result<()> {
    let voice = engine.voice();
    let airway = &voice.airway;
    let net = &airway.net;
    let level = net
        .noise_sources()
        .iter()
        .map(|source| source.level)
        .fold(0.0, f64::max);
    let (noise_pressure_branch, pressure) = net
        .psrc
        .iter()
        .copied()
        .enumerate()
        .filter(|(_, pressure)| *pressure != 0.0)
        .max_by(|(_, a), (_, b)| a.abs().total_cmp(&b.abs()))
        .map_or((-1, 0.0), |(i, v)| (i as i64, v));
    writeln!(
        out,
        "{relative},{absolute},{},{},{},{},{},{},{},{},{},{},{},{level},{pressure},{noise_pressure_branch},{},{},{}",
        voice.gate,
        voice.artic.x.get(ArticKey::LipAp),
        net.amin[airway.oral.last_node()],
        net.p[airway.lungs],
        voice.glottis.cycle_phase(),
        voice.glottis.f0_now,
        voice.glottis.voicing,
        voice.glottis.area,
        net.u[airway.glottis_port],
        net.p[airway.trachea.last_node()],
        net.p[airway.pharynx.first_node()],
        net.radiated_flow(airway.rad_lips),
        net.radiated_flow(airway.rad_nose),
        net.out,
    )
}

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let [input_path, dictionary, destination] = args.as_slice() else {
        return Err("入力JSON、辞書、出力ディレクトリを指定してください".into());
    };
    let input: Value = serde_json::from_slice(&fs::read(input_path)?)?;
    let rate = input["output_rate_hz"]
        .as_f64()
        .ok_or("サンプルレートがありません")?;
    let lead = input["lead_seconds"]
        .as_f64()
        .ok_or("先行時間がありません")?;
    let lead_frames = (lead * rate).round() as i64;
    let samples = input["comparison_samples"]
        .as_i64()
        .ok_or("サンプル数がありません")?;
    let score = &input["score"];
    let body: BodyMix = serde_json::from_value(input["body"].clone())?;
    let source: SourcePatch = serde_json::from_value(input["source"].clone())?;
    let mut g2p = EnglishG2P::new();
    g2p.load_dict(&fs::read_to_string(dictionary)?);
    let lyrics = score["lyrics"].as_str().ok_or("歌詞がありません")?;
    let syllables = read_lyrics(lyrics, &[&English(&g2p)]);
    let recorded_notes: Vec<[f64; 2]> = serde_json::from_value(score["notes"].clone())?;
    if syllables.len() != recorded_notes.len() {
        return Err("音節数と音符数が一致しません".into());
    }
    let notes = recorded_notes
        .into_iter()
        .zip(syllables)
        .map(|([midi, beats], syl)| SungNote { midi, beats, syl })
        .collect::<Vec<_>>();
    let options = SongOptions {
        body,
        bpm: score["bpm"].as_f64().ok_or("テンポがありません")?,
        t0: score["first_beat_seconds"]
            .as_f64()
            .ok_or("最初の拍がありません")?,
        vibrato: score["vibrato_cents"]
            .as_f64()
            .ok_or("ビブラートがありません")?,
    };
    let plan = plan_song(&notes, &options);
    let tip = rest_tip(
        NEUTRAL.get(ArticKey::Jaw),
        NEUTRAL.get(ArticKey::TbX),
        NEUTRAL.get(ArticKey::TbY),
    );
    let mut posture = ArticPatch::default();
    for (target, value) in posture.values.iter_mut().zip(NEUTRAL.to_array()) {
        *target = Some(value);
    }
    posture.values[ArticKey::TtX.index()] = Some(tip.x);
    posture.values[ArticKey::TtY.index()] = Some(tip.y);

    let starts: Vec<i64> = serde_json::from_value(input["schedule_engine_frames"].clone())?;
    let scales: Vec<u8> = serde_json::from_value(input["noise_scales"].clone())?;
    let mut arms = Vec::new();
    let out = Path::new(destination);
    for scale in scales {
        for start in &starts {
            let mut engine = Engine::new(rate);
            if body != BodyMix::MALE {
                engine.set_body(body);
            }
            engine.set_source(&source);
            engine.set_artic(&posture, Some(true));
            engine.set_gate(0.0);
            engine.voice_mut().airway.net.noise_scale = f64::from(scale);
            let internal_rate = engine.voice().airway.net.fs;
            let mut warm = [0.0f32; 128];
            let mut before = *start as usize;
            while before > 0 {
                let n = before.min(warm.len());
                engine.render(&mut warm[..n]);
                before -= n;
            }
            let clock = engine.clock();
            let label = format!("frame-{start}-noise-{scale}");
            let mut trace = BufWriter::new(File::create_new(out.join(format!("{label}.csv")))?);
            let mut audio = BufWriter::new(File::create_new(out.join(format!("{label}.f32le")))?);
            writeln!(trace, "{TRACE_HEADER}")?;
            trace_row(&mut trace, &engine, start - 1, -lead_frames - 1)?;
            let origin = engine.schedule(&plan.gestures, lead, true);
            let mut first_noise_injection = None;
            for relative in -lead_frames..samples {
                let mut sample = [0.0f32];
                engine.render(&mut sample);
                trace_row(
                    &mut trace,
                    &engine,
                    start + lead_frames + relative,
                    relative,
                )?;
                if first_noise_injection.is_none() {
                    let airway = &engine.voice().airway;
                    let net = &airway.net;
                    if net.psrc.iter().any(|&pressure| pressure != 0.0) {
                        let pressures: Vec<_> = net
                            .psrc
                            .iter()
                            .enumerate()
                            .filter(|(_, pressure)| **pressure != 0.0)
                            .map(|(branch, pressure)| (branch, *pressure))
                            .collect();
                        let sources: Vec<_> = net.noise_sources().iter().filter(|s| s.level > 0.0)
                            .map(|s| json!({"source_branch": s.src, "forward_branch": s.fwd, "reverse_branch": s.bwd,
                                "level": s.level, "flow_cm3_s": net.u[s.src]}))
                            .collect();
                        first_noise_injection = Some(
                            json!({"relative_frame": relative, "glottis_port": airway.glottis_port,
                            "active_sources": sources, "branch_pressures_dyn_cm2": pressures}),
                        );
                    }
                }
                if relative >= 0 {
                    audio.write_all(&sample[0].to_le_bytes())?;
                }
            }
            trace.flush()?;
            audio.flush()?;
            arms.push(json!({"label": label, "schedule_frame":start, "noise_scale":scale,
                "clock_at_schedule_seconds":clock, "origin_seconds":origin, "internal_sample_rate_hz":internal_rate,
                "first_noise_injection": first_noise_injection}));
        }
    }
    let evidence = json!({"arms":arms,"segments":plan.segments,"end_seconds":plan.end});
    serde_json::to_writer_pretty(File::create_new(out.join("probe.json"))?, &evidence)?;
    Ok(())
}
