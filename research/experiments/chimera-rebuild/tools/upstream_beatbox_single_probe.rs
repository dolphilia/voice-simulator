//! 固定上流の単発打音を、通常の打音レシピと音源で観測する。

use chimera::{
    anatomy::human::{ArticKey, BODY_MALE, BodyMix},
    control::beat_player::BeatPlayer,
    phonetics::beatbox::{BeatStep, beat_ready},
    voice::{
        human_airway::HumanAirway,
        human_voice::{DEFAULT_SOURCE, HumanVoice, SourcePatch},
    },
};
use serde_json::{Value, json};
use std::{
    error::Error,
    fs::File,
    io::{BufWriter, Write},
};
mod upstream_beatbox_oral_trace;

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let [case, trace, pcm, plan] = args.as_slice() else {
        return Err("ケース、観測CSV、PCMと計画の保存先を指定してください".into());
    };
    let case: Value = serde_json::from_slice(&std::fs::read(case)?)?;
    let input = &case["beatbox_voice"];
    let settings = &input["voice"];
    let sound = input["sound"].as_str().ok_or("打音の指定がありません")?;
    let observe_labiodental = sound == "Pf";
    let observe_inward = sound == "^K";
    let observe_crash = sound == "kch";
    let observe_hum = matches!(sound, "m" | "M");
    let observe_pocket = matches!(sound, "!" | "P!");
    let observe_velar = sound == "K" || observe_inward || observe_pocket || observe_crash;
    let observe_oral = observe_labiodental || observe_velar || matches!(sound, "t" | "tss");
    let number = |object: &Value, key: &str| -> Result<f64, Box<dyn Error>> {
        object[key]
            .as_f64()
            .ok_or_else(|| format!("数値設定がありません ({key})").into())
    };
    let rate = number(settings, "output_sample_rate_hz")?;
    let factor = number(input, "internal_sample_rate_hz")? / rate;
    if !matches!(
        sound,
        "B" | "t" | "tss" | "Pf" | "K" | "^K" | "!" | "P!" | "kch" | "m" | "M"
    ) || factor.fract() != 0.0
        || factor < 1.0
        || number(input, "initial_f0_hz")? != DEFAULT_SOURCE.f0
    {
        return Err(
            "固定版の単発 B、t、tss、Pf、K、^K、!、P!、kch、m と整数倍の内部レートが必要です"
                .into(),
        );
    }
    let mut voice = HumanVoice::new(rate, BODY_MALE, factor as usize);
    let ready = beat_ready(BodyMix::MALE);
    let initial = voice.artic.x;
    voice.set_articulation(&ready, None);
    voice.set_source(&SourcePatch {
        f0: Some(number(settings, "f0_hz")?),
        voiced: Some(true),
        pressure: Some(number(settings, "pressure_cm_h2o")?),
        breathiness: Some(number(settings, "breathiness")?),
        tension: Some(number(settings, "tension")?),
        ..SourcePatch::default()
    });
    voice.set_gate(number(settings, "gate")?);
    voice.output_gain = number(settings, "output_gain")?;
    voice.airway.net.noise_scale = number(input, "noise_scale")?;

    let mut player = BeatPlayer::new();
    player.body = BodyMix::MALE;
    let mut step = BeatStep::new(if observe_hum { "m" } else { sound });
    step.accent = Some(number(input, "accent")?);
    step.note = input["midi_note"].as_f64();
    let mut gestures = Vec::new();
    player.gestures(
        &step,
        number(input, "hit_seconds")?,
        number(input, "step_seconds")?,
        &mut gestures,
    );
    voice.schedule(&gestures);
    let frames = (rate * number(input, "render_end_seconds")?).round() as usize;
    let mut report = BufWriter::new(File::create_new(plan)?);
    serde_json::to_writer_pretty(
        &mut report,
        &json!({
            "initial_posture": initial, "ready_targets": ready, "gestures": gestures,
            "output_frames": frames, "decimation_factor": factor as usize,
        }),
    )?;
    writeln!(report)?;
    report.flush()?;

    let mut trace = BufWriter::new(File::create_new(trace)?);
    let mut pcm = BufWriter::new(File::create_new(pcm)?);
    write!(
        trace,
        concat!(
            "frame,lip_aperture_cm,lip_minimum_cm2,lip_area_cm2,lip_flow_cm3_s,nose_flow_cm3_s,",
            "pressure_sub_dyn_cm2,pressure_supra_dyn_cm2,lung_boundary_dyn_cm2,gate,",
            "abduction_cm2,glottal_area_cm2,glottal_flow_cm3_s,glottal_voicing,",
            "glottal_f0_hz,radiation_derivative_cm3_s2,jaw_cm,larynx_cm,oral_end_pressure_dyn_cm2"
        )
    )?;
    if observe_oral {
        write!(
            trace,
            concat!(
                ",tongue_tip_x_cm,tongue_tip_y_cm,oral_minimum_cm2,oral_minimum_cell,",
                "glottis_noise_level,constriction_noise_level,teeth_noise_level"
            )
        )?;
    }
    if observe_labiodental {
        write!(trace, ",labiodental,noise_teeth_distance_cm")?;
    }
    if observe_velar {
        write!(
            trace,
            ",tongue_body_x_cm,tongue_body_y_cm,pharynx_minimum_cm2"
        )?;
    }
    if observe_inward {
        write!(
            trace,
            ",constriction_jet_flow_cm3_s,constriction_noise_forward_pressure,constriction_noise_reverse_pressure"
        )?;
    }
    if observe_crash {
        write!(
            trace,
            ",constriction_noise_tract_cell,lip_protrusion_cm,lip_spread"
        )?;
    }
    if observe_pocket {
        upstream_beatbox_oral_trace::header(&mut trace, &voice)?;
    } else if observe_crash {
        upstream_beatbox_oral_trace::minima_header(&mut trace, &voice)?;
    }
    if observe_hum {
        upstream_beatbox_oral_trace::nasal_header(&mut trace)?;
    }
    writeln!(trace)?;
    let mut audio = [0.0f32];
    for frame in 0..frames {
        voice.render(&mut audio);
        pcm.write_all(&audio[0].to_le_bytes())?;
        let air = &voice.airway;
        let net = &air.net;
        let lip = air.oral.last_node();
        write!(trace, "{frame}")?;
        for value in [
            voice.artic.x.get(ArticKey::LipAp),
            net.amin[lip],
            net.area[lip],
            net.radiated_flow(air.rad_lips),
            net.radiated_flow(air.rad_nose),
            net.p[air.trachea.last_node()],
            net.p[air.pharynx.first_node()],
            net.p[air.lungs],
            voice.gate,
            voice.glottis.params.abduction,
            voice.glottis.area,
            net.u[air.glottis_port],
            voice.glottis.voicing,
            voice.glottis.f0_now,
            net.out,
            voice.artic.x.get(ArticKey::Jaw),
            voice.artic.x.get(ArticKey::Larynx),
            net.p[lip],
        ] {
            write!(trace, ",{value}")?;
        }
        if observe_oral {
            let oral_start = air.oral.first_node();
            let (cell, minimum) = net.amin[oral_start..=lip]
                .iter()
                .copied()
                .enumerate()
                .min_by(|left, right| left.1.total_cmp(&right.1))
                .ok_or("口腔セルを観測できません")?;
            write!(
                trace,
                ",{},{},{minimum},{cell}",
                voice.artic.x.get(ArticKey::TtX),
                voice.artic.x.get(ArticKey::TtY),
            )?;
            for i in 0..3 {
                let level = net
                    .noise_sources()
                    .get(i)
                    .map_or(0.0, |source| source.level);
                write!(trace, ",{level}")?;
            }
        }
        if observe_labiodental {
            write!(
                trace,
                ",{},{}",
                voice.artic.x.get(ArticKey::Labiodental),
                distance_behind_teeth(air),
            )?;
        }
        if observe_velar {
            let area = net.amin[air.pharynx.first_node()..=air.pharynx.last_node()]
                .iter()
                .copied()
                .fold(f64::INFINITY, f64::min);
            write!(
                trace,
                ",{},{},{area}",
                voice.artic.x.get(ArticKey::TbX),
                voice.artic.x.get(ArticKey::TbY),
            )?;
        }
        if observe_inward {
            let [flow, forward, reverse] = net.noise_sources().get(1).map_or([0.0; 3], |s| {
                [net.u[s.src], net.psrc[s.fwd], net.psrc[s.bwd]]
            });
            write!(trace, ",{flow},{forward},{reverse}")?;
        }
        if observe_crash {
            let cell = upstream_beatbox_oral_trace::constriction_noise_tract_cell(air);
            let lip_protrusion = voice.artic.x.get(ArticKey::LipProt);
            let lip_spread = voice.artic.x.get(ArticKey::LipWidth);
            write!(trace, ",{cell},{lip_protrusion},{lip_spread}")?;
        }
        if observe_pocket {
            upstream_beatbox_oral_trace::row(&mut trace, &voice)?;
        } else if observe_crash {
            upstream_beatbox_oral_trace::minima_row(&mut trace, &voice)?;
        }
        if observe_hum {
            upstream_beatbox_oral_trace::nasal_row(&mut trace, &voice)?;
        }
        writeln!(trace)?;
    }
    trace.flush()?;
    pcm.flush()?;
    Ok(())
}

fn distance_behind_teeth(air: &HumanAirway) -> f64 {
    let narrowest = air
        .ph_min
        .iter()
        .chain(&air.or_min)
        .enumerate()
        .filter(|(_, area)| **area > 0.0)
        .min_by(|left, right| left.1.total_cmp(right.1));
    let (Some((index, _)), Some(frame)) = (narrowest, &air.frame) else {
        return 0.0;
    };
    let center = if index < air.n_ph {
        (index as f64 + 0.5) * (air.ph_len / air.n_ph as f64)
    } else {
        air.ph_len + ((index - air.n_ph) as f64 + 0.5) * (air.or_len / air.n_or as f64)
    };
    frame.teeth_s - center
}
