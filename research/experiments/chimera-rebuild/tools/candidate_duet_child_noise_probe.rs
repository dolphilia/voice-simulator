//! 研究版の既存コアで、歌唱声部の声門乱流計算の前後を観測する。

mod duet_child_noise_trace;

use serde_json::Value;
use std::{
    error::Error,
    fs::{self, File},
    io::{BufWriter, Write},
};
use vocal_core::{
    anatomy::{Articulation, BodyMix, BodyName, Point},
    articulators::Articulator,
    output::OutputStage,
    phonetics::{english::English, song},
    voice::{ArticulatedVoice, FixedVoiceSettings},
};

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let (args, radiation_path) = duet_child_noise_trace::trace_arg(&args, "--radiation-components");
    let (args, output_path) = duet_child_noise_trace::trace_arg(args, "--output-trace");
    let (case, dict, count, trace_path, pcm_path, startup_path) = match args {
        [case, dict, count, trace, pcm] => (case, dict, count, trace, pcm, None),
        [case, dict, count, trace, pcm, startup] => (case, dict, count, trace, pcm, Some(startup)),
        _ => {
            return Err(
                "ケース、辞書、観測点数、CSV、PCMと、必要なら初期状態CSVを指定してください".into(),
            );
        }
    };
    let case: Value = serde_json::from_slice(&fs::read(case)?)?;
    let input = &case["song_voice"];
    let score = &input["score"];
    let lexicon_text = fs::read_to_string(dict)?;
    let lexicon = English::with_dictionary(&lexicon_text);
    let lyrics = score["lyrics"].as_str().ok_or("歌詞がありません")?;
    let number = |object: &Value, key: &str| -> Result<f64, String> {
        object[key]
            .as_f64()
            .ok_or_else(|| format!("数値の設定がありません ({key})"))
    };
    let syllables = song::lyric_syllables(lyrics, &lexicon);
    let notes: Vec<song::Note> = serde_json::from_value(score["notes"].clone())?;
    let plan = song::plan(
        &syllables,
        &notes,
        number(score, "bpm")?,
        number(score, "start_seconds")?,
    )?;
    let body = if input["body"].is_object() {
        let mix = &input["body"];
        BodyMix::new(number(mix, "female")?, number(mix, "child")?)
    } else {
        serde_json::from_value::<BodyName>(input["body"].clone())?.into()
    };
    let gestures = song::score_with_body(&plan, number(input, "vibrato_cents")?, body)?;
    let settings = &input["voice"];
    let pose = &input["posture"];
    let point = |key: &str| -> Result<Point, Box<dyn Error>> {
        let [x, y]: [f64; 2] = serde_json::from_value(pose[key].clone())?;
        Ok(Point::new(x, y))
    };
    let articulation = Articulation {
        jaw_cm: number(pose, "jaw_cm")?,
        tongue_body_cm: point("tongue_body_cm")?,
        tongue_tip_cm: point("tongue_tip_cm")?,
        tongue_root_cm: number(pose, "tongue_root_cm")?,
        tip_curl: number(pose, "tip_curl")?,
        dorsum: number(pose, "dorsum")?,
        lip_aperture_cm: number(pose, "lip_aperture_cm")?,
        lip_protrusion_cm: number(pose, "lip_protrusion_cm")?,
        lip_spread: number(pose, "lip_spread")?,
        labiodental: number(pose, "labiodental")?,
        velum_cm2: number(pose, "velum_cm2")?,
        larynx_cm: number(pose, "larynx_cm")?,
        lateral: pose["lateral"].as_f64().unwrap_or_default(),
        epilarynx: pose["epilarynx"].as_f64().unwrap_or_default(),
        ventricular: pose["ventricular"].as_f64().unwrap_or_default(),
    };
    let internal_rate = serde_json::from_value(input["internal_sample_rate_hz"].clone())?;
    let output_rate = serde_json::from_value(settings["output_sample_rate_hz"].clone())?;
    let gain = number(settings, "output_gain")?;
    let mut output = OutputStage::new(internal_rate, output_rate, gain)?;
    let mut output_trace = output_path
        .map(File::create_new)
        .transpose()?
        .map(BufWriter::new);
    let mut radiation_trace = radiation_path
        .map(File::create_new)
        .transpose()?
        .map(BufWriter::new);
    if (output_trace.is_some() || radiation_trace.is_some()) && output.factor() != 2 {
        return Err("出力段の観測には内部レートが出力の2倍のケースを指定してください".into());
    }
    if let Some(out) = &mut radiation_trace {
        writeln!(out, "{}", duet_child_noise_trace::RADIATION_HEADER)?;
    }
    let mut voice = ArticulatedVoice::for_speech_with_body(
        internal_rate,
        64 * output.factor(),
        articulation,
        FixedVoiceSettings {
            pressure_cm_h2o: number(settings, "pressure_cm_h2o")?,
            gate: number(settings, "gate")?,
            f0_hz: 110.0,
            breathiness: number(settings, "breathiness")?,
            tension: number(settings, "tension")?,
        },
        body,
    )?;
    voice.set_base_pitch(plan.notes.first().ok_or("音符がありません")?.f0_hz)?;
    voice.enable_turbulence(1.0)?;
    let mut trace = BufWriter::new(File::create_new(trace_path)?);
    writeln!(trace, "{}", duet_child_noise_trace::HEADER)?;
    serde_json::to_writer(std::io::stdout().lock(), &gestures)?;
    voice.set_score(gestures)?;
    let mut pcm = BufWriter::new(File::create_new(pcm_path)?);
    let count = count.parse::<usize>()?;
    let frames = (plan.render_end_seconds * f64::from(output_rate)).round() as usize;
    let mut startup = startup_path
        .map(File::create_new)
        .transpose()?
        .map(BufWriter::new);
    if let Some(out) = &mut startup {
        writeln!(out, "{}", duet_child_noise_trace::STARTUP_HEADER)?;
        write_startup(out, &voice, 0, 0.0)?;
    }
    for frame in 0..frames {
        let mut radiation = [0.0; 2];
        let mut components = [[0.0; 6]; 2];
        let record_components = radiation_trace.is_some() && frame < count;
        let (rendered, (sample, [area, flow])) = output.render_frame(|| {
            let air = voice.airway();
            let port = air.glottis_port;
            let drive = [air.network.branch_area(port), air.network.branch_flow(port)];
            let sample = voice.step()?;
            let next = sample.radiation.radiation_flow_derivative_cm3_s2;
            if output_trace.is_some() {
                radiation = [radiation[1], next];
            }
            if record_components {
                let air = voice.airway();
                components = [
                    components[1],
                    [
                        sample.lip_flow_cm3_s,
                        sample.nose_flow_cm3_s,
                        sample.radiation.wall_radiation_flow_cm3_s,
                        sample.radiation.radiation_flow_cm3_s,
                        next,
                        air.network.branch_area(air.velum_port),
                    ],
                ];
            }
            Ok((next, (sample, drive)))
        })?;
        pcm.write_all(&rendered.pcm.to_le_bytes())?;
        if let Some(out) = &mut output_trace {
            duet_child_noise_trace::write_output_row(
                out,
                radiation,
                [
                    rendered.decimated,
                    rendered.decimated * gain,
                    rendered.dc_removed,
                    rendered.envelope,
                    rendered.hold_frames as f64,
                ],
            )?;
        }
        if frame < count {
            if let Some(out) = &mut radiation_trace {
                duet_child_noise_trace::write_radiation_pair(out, frame, components)?;
            }
            if let Some(out) = &mut startup {
                write_startup(
                    out,
                    &voice,
                    frame + 1,
                    sample.radiation.radiation_flow_derivative_cm3_s2,
                )?;
            }
            let air = voice.airway();
            let net = &air.network;
            let mut max = (0.0, -1.0);
            for (spec, level) in (0..).map_while(|i| net.noise_spec(i).zip(net.noise_level(i))) {
                if level > max.0 {
                    max = (level, spec.source as f64);
                }
            }
            duet_child_noise_trace::write_row(
                &mut trace,
                frame,
                [
                    voice
                        .articulators()
                        .state(Articulator::LipAperture)
                        .position,
                    net.area(air.lips),
                    net.area(air.tubes[1].nodes.start),
                    sample.breath.gate,
                    sample.glottis.f0_hz,
                    sample.glottis.phase,
                    sample.glottis.area_cm2,
                    area,
                    flow,
                    net.noise_level(0).ok_or("声門の乱流源がありません")?,
                    net.noise_spec(0)
                        .filter(|spec| spec.source == air.glottis_port)
                        .ok_or("声門の乱流枝が違います")?
                        .gain,
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

fn write_startup(
    out: &mut impl Write,
    voice: &ArticulatedVoice,
    sample: usize,
    radiation: f64,
) -> std::io::Result<()> {
    let bank = voice.articulators();
    let x = bank.state(Articulator::TongueTipX);
    let y = bank.state(Articulator::TongueTipY);
    let air = voice.airway();
    duet_child_noise_trace::write_row(
        out,
        sample,
        [
            x.position,
            y.position,
            x.target,
            y.target,
            x.velocity,
            y.velocity,
            air.network.area(air.lips),
            air.network.area(air.tubes[1].nodes.start),
            air.network.branch_flow(air.glottis_port),
            radiation,
        ],
    )
}
