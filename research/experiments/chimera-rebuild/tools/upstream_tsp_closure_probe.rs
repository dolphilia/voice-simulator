//! 固定版の通常発話と同じ初期化で、口腔の最小断面と放射を採る。

#[cfg(tsp_voice_probe)]
mod tsp_fine_trace;

use chimera::{
    anatomy::human::{ArticKey, BODY_FEMALE, BODY_MALE},
    math::js_round,
    phonetics::{
        english::EnglishG2P,
        planner::{PhraseInput, PlanOptions, plan_phrases},
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
    let mut args: Vec<_> = std::env::args().skip(1).collect();
    #[cfg(tsp_voice_probe)]
    let source_options = if args.len() > 5 {
        args.split_off(5)
    } else {
        Vec::new()
    };
    let observe_teeth = args.last().is_some_and(|arg| arg == "--teeth");
    if observe_teeth {
        args.pop();
    }
    let [input, dictionary, trace, wave, plan] = args.as_slice() else {
        return Err("本文、辞書、状態とPCMと計画の保存先を指定してください".into());
    };
    let input: Value = serde_json::from_slice(&fs::read(input)?)?;
    let spec = &input["speech_voice"];
    if spec["input"]["rate"] != 1.0 {
        return Err("等速の発話条件を指定してください".into());
    }
    let (body_name, body, f0) = match spec["body"].as_str() {
        Some("female") => ("female", BODY_FEMALE, 205.0),
        Some("male") => ("male", BODY_MALE, 112.0),
        _ => return Err("男性または女性の体型を指定してください".into()),
    };
    let text = spec["input"]["text"].as_str().ok_or("本文がありません")?;
    let mut g2p = EnglishG2P::new();
    g2p.load_dict(&fs::read_to_string(dictionary)?);
    let phrases: Vec<_> = g2p
        .to_phrases(text)
        .into_iter()
        .map(|p| PhraseInput {
            segments: p.segments,
            intonation: Some(p.intonation),
            pause: Some(p.pause),
        })
        .collect();
    let score = plan_phrases(
        &phrases,
        &PlanOptions {
            body: body_name.into(),
            t0: 0.05,
            f0: Some(f0),
            ..Default::default()
        },
    );
    let fs = spec["voice"]["output_sample_rate_hz"].as_f64().unwrap_or(48_000.0);
    let frames = js_round(fs * (score.end + 0.3)) as usize;
    fs::write(
        plan,
        serde_json::to_vec(&json!({
            "segments": score.segments, "gestures": score.gestures, "output_frames": frames,
        }))?,
    )?;
    let mut voice = HumanVoice::new(fs, body, 2);
    let source = SourcePatch::f0(f0);
    #[cfg(tsp_voice_probe)]
    let source = if source_options.get(1).is_some_and(|variant| matches!(variant.as_str(), "drift_zero" | "jitter_zero")) {
        SourcePatch { drift: Some(0.0), ..source }
    } else {
        source
    };
    voice.set_source(&source);
    voice.schedule(&score.gestures);
    #[cfg(tsp_voice_probe)]
    {
        let [count, variant, output] = source_options.as_slice() else {
            return Err("観測フレーム数、音源条件、出力段の保存先を指定してください".into());
        };
        match variant.as_str() {
            "default" | "drift_zero" => {}
            "jitter_zero" => voice.glottis.params.jitter = 0.0,
            "zero" => {
                voice.set_source(&SourcePatch {
                    drift: Some(0.0),
                    ..Default::default()
                });
                voice.glottis.params.jitter = 0.0;
                voice.glottis.params.shimmer = 0.0;
            }
            _ => return Err("音源条件が登録値と一致しません".into()),
        }
        render_source(&mut voice, [trace, wave, output], frames, count.parse()?)?;
        return Ok(());
    }
    #[cfg(not(tsp_voice_probe))]
    render_closure(&mut voice, trace, wave, frames, observe_teeth)
}

#[cfg(not(tsp_voice_probe))]
fn render_closure(
    voice: &mut HumanVoice,
    trace: &str,
    wave: &str,
    frames: usize,
    observe_teeth: bool,
) -> Result<(), Box<dyn Error>> {
    let mut pcm = BufWriter::new(File::create_new(wave)?);
    let mut out = BufWriter::new(File::create_new(trace)?);
    write!(
        out,
        "frame,oral_minimum_cm2,oral_minimum_cell,lip_minimum_cm2,tongue_tip_y_cm,lip_flow_cm3_s,nose_flow_cm3_s,radiation_derivative_cm3_s2"
    )?;
    if observe_teeth {
        write!(
            out,
            ",teeth_noise_source,teeth_noise_gain,teeth_noise_level,teeth_noise_forward_pressure,teeth_noise_reverse_pressure"
        )?;
    }
    writeln!(out)?;
    let mut sample = [0.0f32];
    for frame in 0..frames {
        voice.render(&mut sample);
        pcm.write_all(&sample[0].to_le_bytes())?;
        let airway = &voice.airway;
        let net = &airway.net;
        let last = airway.oral.last_node();
        let (cell, area) = net.amin[airway.oral.first_node()..=last]
            .iter()
            .enumerate()
            .min_by(|a, b| a.1.total_cmp(b.1))
            .ok_or("口腔セルがありません")?;
        write!(
            out,
            "{frame},{area},{cell},{},{},{},{},{}",
            net.amin[last],
            voice.artic.x.get(ArticKey::TtY),
            net.radiated_flow(airway.rad_lips),
            net.radiated_flow(airway.rad_nose),
            net.out
        )?;
        if observe_teeth {
            if let Some(spec) = net.noise_sources().get(2) {
                write!(
                    out,
                    ",{},{},{},{},{}",
                    spec.src, spec.gain, spec.level, net.psrc[spec.fwd], net.psrc[spec.bwd]
                )?;
            } else {
                write!(out, ",-1,0,0,0,0")?;
            }
        }
        writeln!(out)?;
    }
    out.flush()?;
    pcm.flush()?;
    Ok(())
}

#[cfg(tsp_voice_probe)]
fn render_source(
    voice: &mut HumanVoice,
    [trace, wave, output]: [&str; 3],
    frames: usize,
    count: usize,
) -> Result<(), Box<dyn Error>> {
    if count > frames {
        return Err("観測範囲が音声を越えています".into());
    }
    let mut pcm = BufWriter::new(File::create_new(wave)?);
    let mut trace = BufWriter::new(File::create_new(trace)?);
    let mut output = BufWriter::new(File::create_new(output)?);
    #[cfg(tsp_pressure_replay)]
    let mut pressure = open_pressure_files(voice, frames * 2)?;
    #[cfg(tsp_cycle_scales)]
    let mut cycle = {
        let path = std::env::var_os("CHIMERA_PROBE_CYCLE_TRACE").ok_or("周期倍率と振幅倍率の保存先がありません")?;
        BufWriter::new(File::create_new(path)?)
    };
    let mut sample = [0.0f32];
    for frame in 0..frames {
        voice.render(&mut sample);
        pcm.write_all(&sample[0].to_le_bytes())?;
        #[cfg(tsp_pressure_replay)]
        for row in &voice.probe_pressure_pair {
            tsp_fine_trace::write_row(&mut pressure, row)?;
        }
        if frame < count {
            #[cfg(tsp_cycle_scales)]
            for row in &voice.probe_cycle_pair {
                tsp_fine_trace::write_row(&mut cycle, row)?;
            }
            for row in &voice.probe_source_pair {
                tsp_fine_trace::write_row(&mut trace, row)?;
            }
            tsp_fine_trace::write_row(&mut output, &voice.probe_radiation_pair)?;
            tsp_fine_trace::write_row(&mut output, &voice.probe_output)?;
        }
    }
    output.flush()?;
    trace.flush()?;
    pcm.flush()?;
    #[cfg(tsp_pressure_replay)]
    pressure.flush()?;
    #[cfg(tsp_cycle_scales)]
    cycle.flush()?;
    Ok(())
}

#[cfg(all(tsp_voice_probe, tsp_pressure_replay))]
fn open_pressure_files(voice: &mut HumanVoice, samples: usize) -> Result<BufWriter<File>, Box<dyn Error>> {
    if let Some(path) = std::env::var_os("CHIMERA_PROBE_PRESSURE_INPUT") {
        let bytes = fs::read(path)?;
        if bytes.len() != samples * size_of::<f64>() {
            return Err("圧差系列の長さが内部サンプル数と一致しません".into());
        }
        let values: Vec<_> = bytes
            .chunks_exact(size_of::<f64>())
            .map(|bytes| f64::from_le_bytes(bytes.try_into().expect("8バイトの圧差")))
            .collect();
        if !values.iter().all(|value| value.is_finite()) {
            return Err("圧差系列に有限でない値があります".into());
        }
        voice.probe_pressure_input = Some(values);
    }
    let path = std::env::var_os("CHIMERA_PROBE_PRESSURE_TRACE").ok_or("圧差観測の保存先がありません")?;
    Ok(BufWriter::new(File::create_new(path)?))
}
