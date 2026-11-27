//! 上流のHumanVoiceで固定母音を発声し、上流の解析器でPCM窓を測る。

use chimera::analysis::{
    lpc::{FormantOpts, autocorr, estimate_formants, levinson, poly_roots},
    pitch::{YinOpts, yin_pitch},
};
use chimera::anatomy::human::{BodyMix, NEUTRAL};
use chimera::engine::default_f0;
use chimera::math::{PI, cos, exp, pow};
use chimera::phonetics::planner::{vowel_artic, vowel_table};
use chimera::voice::human_voice::{DEFAULT_SOURCE, HumanVoice, SourcePatch};
use std::error::Error;
use std::fs::{self, File};
use std::io::{BufWriter, Write};
use std::path::Path;

fn main() -> Result<(), Box<dyn Error>> {
    let arguments: Vec<_> = std::env::args().skip(1).collect();
    match arguments.as_slice() {
        [
            mode,
            ipa,
            internal,
            output,
            frames,
            pressure,
            gate,
            breathiness,
            tension,
            gain,
            directory,
            extra @ ..,
        ] if matches!(
            mode.as_str(),
            "render" | "render-body" | "render-calibrated" | "render-research-flow"
        ) =>
        {
            let internal = internal.parse::<usize>()?;
            let output = output.parse::<usize>()?;
            let factor = internal / output;
            let (body, pitch, events) =
                if matches!(mode.as_str(), "render-body" | "render-calibrated") {
                    let [body_arg, pitch_arg] = extra else {
                        return Err("体型と固定音高を指定してください".into());
                    };
                    let body = match body_arg.as_str() {
                        "male" => BodyMix::MALE,
                        "female" => BodyMix::FEMALE,
                        "child" => BodyMix::CHILD,
                        blend => {
                            let (female, child) =
                                blend.split_once(',').ok_or("体型の指定が不正です")?;
                            BodyMix::new(female.parse()?, child.parse()?)
                        }
                    };
                    let pitch = if pitch_arg == "default" {
                        default_f0(body)
                    } else {
                        pitch_arg.parse()?
                    };
                    (body, pitch, &extra[2..])
                } else {
                    let events = if mode == "render-research-flow" {
                        &[]
                    } else {
                        extra
                    };
                    (BodyMix::MALE, DEFAULT_SOURCE.f0, events)
                };
            let pose = if mode == "render-calibrated" {
                vowel_artic(ipa, body).ok_or("較正済みの母音目標がありません")?
            } else {
                vowel_table()["male"]
                    .get(ipa.as_str())
                    .ok_or("較正表に母音がありません")?
                    .artic
            }
            .apply_to(&NEUTRAL);
            let mut voice = HumanVoice::new(output as f64, body.body(), factor);
            voice.artic.x = pose;
            voice.artic.target = pose;
            voice.artic.tip_free = false;
            voice.max_penetration = f64::INFINITY;
            voice.airway.apply(&pose, 0.0);
            voice.airway.net.snap_to_targets();
            voice.airway.net.noise_scale = 0.0;
            voice.set_source(&SourcePatch {
                f0: Some(pitch),
                pressure: Some(pressure.parse()?),
                breathiness: Some(breathiness.parse()?),
                tension: Some(tension.parse()?),
                drift: Some(0.0),
                ..SourcePatch::default()
            });
            voice.glottis.params.jitter = 0.0;
            voice.glottis.params.shimmer = 0.0;
            // 計測用の上流ビルドでは、目標と初期値を揃えて音高グライドを隔離する。
            #[cfg(chimera_fixed_pitch_probe)]
            voice.probe_set_initial_f0(pitch);
            #[cfg(not(chimera_fixed_pitch_probe))]
            if matches!(mode.as_str(), "render-body" | "render-calibrated") {
                return Err("体型比較には初期音高を指定できる上流の計測用ビルドが必要です".into());
            }
            voice.output_gain = gain.parse()?;
            voice.set_gate(gate.parse()?);

            #[cfg(research_fixed_glottal_flow)]
            if mode == "render-research-flow" {
                voice.research_flow_trace = Some(Vec::new());
                match extra {
                    [] => {}
                    [path] => {
                        let data = fs::read(path)?;
                        if data.len() != frames.parse::<usize>()? * factor * 8 {
                            return Err("声門流量列の長さが内部サンプル数と一致しません".into());
                        }
                        let values = data
                            .chunks_exact(8)
                            .map(|bytes| f64::from_le_bytes(bytes.try_into().unwrap()))
                            .collect::<Vec<_>>();
                        if values.iter().any(|value| !value.is_finite()) {
                            return Err("有限の声門流量を指定してください".into());
                        }
                        voice.research_flow = Some(values);
                    }
                    _ => return Err("声門流量は1ファイルで指定してください".into()),
                }
            }
            #[cfg(not(research_fixed_glottal_flow))]
            if mode == "render-research-flow" {
                return Err("内部声門流量を記録する上流の計測用ビルドが必要です".into());
            }

            let changes = match events {
                [] => Vec::new(),
                [path] => fs::read_to_string(path)?
                    .lines()
                    .map(|line| -> Result<(usize, f64), Box<dyn Error>> {
                        let (frame, goal) =
                            line.split_once(' ').ok_or("呼気イベントの書式が不正です")?;
                        Ok((frame.parse()?, goal.parse()?))
                    })
                    .collect::<Result<Vec<_>, _>>()?,
                _ => return Err("呼気イベントは1ファイルで指定してください".into()),
            };
            let mut changes = changes.into_iter().peekable();
            let make = |name| File::create_new(Path::new(directory).join(name)).map(BufWriter::new);
            let mut pcm = make("upstream-voice.f32")?;
            let mut trace = make("upstream-trace.csv")?;
            #[cfg(chimera_pharynx_balance_probe)]
            {
                voice.research_pharynx_balance =
                    Some(Vec::with_capacity(frames.parse::<usize>()? * factor));
            }
            let mut lung_flow = if mode == "render-body" && factor == 1 {
                Some(make("upstream-lung-flow.f64")?)
            } else {
                None
            };
            writeln!(
                trace,
                concat!(
                    "frame,internal_sample,gate,lung_boundary_dyn_cm2,pressure_sub_dyn_cm2,pressure_supra_dyn_cm2,",
                    "glottal_area_cm2,glottal_flow_cm3_s,glottal_phase,glottal_voicing,glottal_f0_hz,",
                    "lip_flow_cm3_s,nose_flow_cm3_s,radiation_derivative_cm3_s2",
                )
            )?;
            for frame in 0..frames.parse::<usize>()? {
                if let Some((_, goal)) = changes.next_if(|&(at, _)| at == frame) {
                    voice.set_gate(goal);
                }
                let mut sample = [0.0_f32];
                voice.render(&mut sample);
                pcm.write_all(&sample[0].to_le_bytes())?;
                let index = (frame + 1) * factor - 1;
                let air = &voice.airway;
                let net = &air.net;
                if let Some(flow) = &mut lung_flow {
                    flow.write_all(&net.u[air.lung_port].to_le_bytes())?;
                }
                writeln!(
                    trace,
                    "{frame},{index},{},{},{},{},{},{},{},{},{},{},{},{}",
                    voice.gate,
                    net.p[air.lungs],
                    net.p[air.trachea.last_node()],
                    net.p[air.pharynx.first_node()],
                    voice.glottis.area,
                    net.u[air.glottis_port],
                    voice.glottis.cycle_phase(),
                    voice.glottis.voicing,
                    voice.glottis.f0_now,
                    net.radiated_flow(air.rad_lips),
                    net.radiated_flow(air.rad_nose),
                    net.out
                )?;
            }
            #[cfg(chimera_pharynx_balance_probe)]
            if let Some(rows) = voice.research_pharynx_balance.take() {
                let mut result = make("upstream-pharynx-balance.csv")?;
                writeln!(
                    result,
                    concat!(
                        "internal_sample,pressure_supra_dyn_cm2,glottal_area_cm2,glottal_flow_cm3_s,",
                        "pharynx_next_pressure_dyn_cm2,pharynx_outflow_cm3_s,pharynx_wall_flow_cm3_s,",
                        "pharynx_volume_source_cm3_s,pharynx_area_cm2,pharynx_length_cm,pharynx_compliance_cgs",
                    )
                )?;
                for (index, row) in rows.iter().enumerate() {
                    write!(result, "{index}")?;
                    for value in row {
                        write!(result, ",{value}")?;
                    }
                    writeln!(result)?;
                }
                result.flush()?;
            }
            if voice.artic.x != pose {
                return Err("発声中に固定姿勢が変化しました".into());
            }
            trace.flush()?;
            pcm.flush()?;
            if let Some(flow) = &mut lung_flow {
                flow.flush()?;
            }
            #[cfg(research_fixed_glottal_flow)]
            if let Some(samples) = &voice.research_flow_trace {
                let mut internal = make("upstream-internal.f64")?;
                for sample in samples.iter().flatten() {
                    internal.write_all(&sample.to_le_bytes())?;
                }
                internal.flush()?;
            }
        }
        [
            mode,
            wave,
            rate,
            f0_min,
            f0_max,
            threshold,
            lpc_wave,
            lpc_rate,
            order,
            pre,
            min_freq,
            max_bw,
            output,
            roots,
        ] if mode == "analyze" => {
            let wave = read_f64(wave)?;
            let lpc_wave = read_f64(lpc_wave)?;
            let pitch = yin_pitch(
                &wave,
                rate.parse()?,
                YinOpts {
                    min_f0: Some(f0_min.parse()?),
                    max_f0: Some(f0_max.parse()?),
                    threshold: Some(threshold.parse()?),
                },
            );
            let mut out = BufWriter::new(File::create_new(output)?);
            writeln!(out, "kind,frequency_hz,aperiodicity_or_bandwidth_hz")?;
            if pitch.f0 > 0.0 {
                writeln!(out, "pitch,{},{}", pitch.f0, pitch.aperiodicity)?;
            } else {
                writeln!(out, "pitch,,{}", pitch.aperiodicity)?;
            }
            let lpc_rate = lpc_rate.parse()?;
            let order = order.parse()?;
            let pre = pre.parse()?;
            let mut root_output = BufWriter::new(File::create_new(roots)?);
            writeln!(root_output, "real,imaginary")?;
            if lpc_wave.iter().any(|&sample| sample != 0.0) {
                let formants = estimate_formants(
                    &lpc_wave,
                    lpc_rate,
                    FormantOpts {
                        order: Some(order),
                        pre_emph: Some(pre),
                        min_freq: Some(min_freq.parse()?),
                        max_bw: Some(max_bw.parse()?),
                    },
                );
                for formant in formants {
                    writeln!(out, "formant,{},{}", formant.freq, formant.bw)?;
                }
                let mut x = Vec::with_capacity(lpc_wave.len());
                for (i, &v) in lpc_wave.iter().enumerate() {
                    let previous = if i == 0 { 0.0 } else { pre * lpc_wave[i - 1] };
                    let phase = 2.0 * PI * i as f64 / (lpc_wave.len() as f64 - 1.0);
                    x.push((v - previous) * (0.54 - 0.46 * cos(phase)));
                }
                let mut correlation = autocorr(&x, order);
                for (i, r) in correlation.iter_mut().enumerate().skip(1) {
                    *r *= exp(-0.5 * pow(2.0 * PI * 40.0 * i as f64 / lpc_rate, 2.0));
                }
                let (real, imaginary) = poly_roots(&levinson(&correlation, order).a, 400);
                for (real, imaginary) in real.into_iter().zip(imaginary) {
                    writeln!(root_output, "{real},{imaginary}")?;
                }
            }
            root_output.flush()?;
            out.flush()?;
        }
        _ => return Err("render または analyze の引数を確認してください".into()),
    }
    Ok(())
}

fn read_f64(path: &str) -> Result<Vec<f64>, Box<dyn Error>> {
    let bytes = fs::read(path)?;
    let mut samples = bytes.chunks_exact(8);
    if !samples.remainder().is_empty() || bytes.is_empty() {
        return Err("PCM窓には倍精度サンプルを指定してください".into());
    }
    Ok(samples
        .by_ref()
        .map(|sample| f64::from_le_bytes(sample.try_into().expect("8バイト")))
        .collect())
}
