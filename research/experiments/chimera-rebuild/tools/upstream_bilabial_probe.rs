//! 固定版のスコアを声道に通し、実フレームの唇・声門・放射とPCMを採取する。

use chimera::{
    anatomy::human::{ArticKey, ArticPatch, BodyMix, BodyName},
    engine::default_f0,
    phonetics::{
        Intonation, Plan, Segment, Syllable,
        english::EnglishG2P,
        ipa::tokenize_ipa,
        planner::{PlanOptions, plan_utterance},
        sing::{SongOptions, SungNote, midi_to_hz, plan_song},
        mandarin::{MandarinLexicon, is_han},
        syllables::lyrics_to_syllables_with,
    },
    voice::{
        human_airway::HumanAirway,
        human_voice::{HumanVoice, SourcePatch},
    },
};
use serde_json::{Value, json};
use std::{
    error::Error,
    fs::File,
    io::{self, BufWriter, Write},
};

fn lexicon(load_dictionary: bool) -> Result<EnglishG2P, Box<dyn Error>> {
    let mut lexicon = EnglishG2P::new();
    if load_dictionary {
        let gzip = std::process::Command::new("gzip")
            .args(["-dc", "public/data/cmudict.txt.gz"])
            .output()?;
        if !gzip.status.success() {
            return Err("固定版の辞書を展開できません".into());
        }
        lexicon.load_dict(std::str::from_utf8(&gzip.stdout)?);
    }
    Ok(lexicon)
}

fn song(score: &Value, vibrato: f64, body: BodyMix) -> Result<Plan, Box<dyn Error>> {
    let syllables: Vec<Syllable> = match score["lyrics"].as_str() {
        Some(text) => {
            let mut mandarin = MandarinLexicon::new();
            if text.chars().any(is_han) {
                let data = std::process::Command::new("gzip")
                    .args(["-dc", "public/data/mandarin.txt.gz"])
                    .output()?;
                if !data.status.success() {
                    return Err("固定版の中国語辞書を展開できません".into());
                }
                mandarin.load(std::str::from_utf8(&data.stdout)?);
            }
            lyrics_to_syllables_with(
                text,
                &lexicon(score["dictionary"].as_bool().unwrap_or(true))?,
                &mandarin,
            )
        }
        None => serde_json::from_value(score["syllables"].clone())?,
    };
    let notes = score["notes"]
        .as_array()
        .ok_or("歌唱の音符を指定してください")?;
    if !notes.is_empty() && syllables.is_empty() {
        return Err("歌唱の音節を指定してください".into());
    }
    let melody: Vec<_> = notes
        .iter()
        .enumerate()
        .map(|(i, n)| SungNote {
            midi: n["midi"].as_f64().unwrap(),
            beats: n["beats"].as_f64().unwrap(),
            syl: syllables[i % syllables.len()].clone(),
        })
        .collect();
    Ok(plan_song(
        &melody,
        &SongOptions {
            body,
            bpm: score["bpm"].as_f64().unwrap(),
            t0: score["start_seconds"].as_f64().unwrap(),
            vibrato,
        },
    ))
}

fn text_f0(body: BodyMix) -> f64 {
    // render::text_f0 の端点と、混合条件で登録した対数補間を使う。
    let endpoint = |name| match name {
        BodyName::Male => 112.0,
        BodyName::Female => 205.0,
        BodyName::Child => 250.0,
    };
    if let Some(name) = body.preset() {
        return endpoint(name);
    }
    chimera::math::exp(body.blend(|name| chimera::math::ln(endpoint(name))))
}

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let [case, trace, pcm, plans] = args.as_slice() else {
        return Err("ケースと観測CSV、PCM、計画の保存先を指定してください".into());
    };
    let case: Value = serde_json::from_slice(&std::fs::read(case)?)?;
    let singing = case.get("song_voice").is_some();
    let speech = &case[if singing {
        "song_voice"
    } else {
        "speech_voice"
    }];
    let input = &speech["input"];
    let english = speech["language"].as_str() == Some("english");
    let body = match speech.get("body") {
        Some(value) => serde_json::from_value::<BodyMix>(value.clone())?,
        None => BodyMix::MALE,
    };
    let lateral_scale = speech["lateral_opening_scale"].as_f64().unwrap_or(1.0);
    let settings = &speech["voice"];
    let number = |key: &str| -> Result<f64, &'static str> {
        settings[key].as_f64().ok_or("音源の設定値がありません")
    };
    let rate = number("output_sample_rate_hz")?;
    let internal_rate = speech["internal_sample_rate_hz"].as_f64().unwrap();
    let factor = internal_rate / rate;
    let f0 = if singing {
        speech["score"]["notes"][0]["midi"]
            .as_f64()
            .map_or(110.0, midi_to_hz)
    } else {
        settings["f0_hz"].as_f64().unwrap_or_else(|| {
            if english {
                text_f0(body)
            } else {
                default_f0(body)
            }
        })
    };
    if factor.fract() != 0.0 || factor < 1.0 {
        return Err("内部レートを出力レートの整数倍にそろえる".into());
    }
    let mut voice = HumanVoice::new(rate, body.body(), factor as usize);
    let pose = &speech["posture"];
    let initial = json!({
        "jaw":pose["jaw_cm"],"tbX":pose["tongue_body_cm"][0],"tbY":pose["tongue_body_cm"][1],
        "ttX":pose["tongue_tip_cm"][0],"ttY":pose["tongue_tip_cm"][1],"ttCurl":pose["tip_curl"],
        "root":pose["tongue_root_cm"],"lipAp":pose["lip_aperture_cm"],"lipProt":pose["lip_protrusion_cm"],
        "lipWidth":pose["lip_spread"],"labiodental":pose["labiodental"],"velum":pose["velum_cm2"],
        "larynx":pose["larynx_cm"],"epilarynx":pose["epilarynx"].as_f64().unwrap_or(0.0),
        "ventricular":pose["ventricular"].as_f64().unwrap_or(0.0),"lateral":pose["lateral"].as_f64().unwrap_or(0.0) * lateral_scale,
        "dorsum":pose["dorsum"]
    });
    voice
        .artic
        .snap(&serde_json::from_value::<ArticPatch>(initial)?);
    voice.airway.apply(&voice.artic.x, 0.0);
    voice.airway.net.snap_to_targets();

    voice.set_source(&SourcePatch {
        f0: Some(f0),
        pressure: Some(number("pressure_cm_h2o")?),
        breathiness: Some(number("breathiness")?),
        tension: Some(number("tension")?),
        drift: Some(0.0),
        ..SourcePatch::default()
    });
    voice.glottis.params.jitter = 0.0;
    voice.glottis.params.shimmer = 0.0;
    voice.output_gain = number("output_gain")?;
    voice.set_gate(number("gate")?);

    let utterances: Vec<(Vec<Segment>, Option<Intonation>, f64)> = if singing {
        Vec::new()
    } else if english {
        let lexicon = lexicon(true)?;
        let text = input["text"]
            .as_str()
            .ok_or("英語テキストを指定してください")?;
        lexicon
            .to_phrases(text)
            .into_iter()
            .map(|phrase| (phrase.segments, Some(phrase.intonation), phrase.pause))
            .collect()
    } else if let Some(text) = input["text"].as_str() {
        text.split('/')
            .map(str::trim)
            .filter(|part| !part.is_empty())
            .map(|p| (tokenize_ipa(p), None, 0.35))
            .collect()
    } else {
        vec![(
            serde_json::from_value::<Vec<Segment>>(input["segments"].clone())?,
            None,
            0.35,
        )]
    };
    let mut start = input["start_seconds"].as_f64().unwrap_or(0.05);
    let mut end = start;
    let mut results = Vec::with_capacity(utterances.len());
    for (utterance, intonation, pause) in utterances {
        let mut plan = plan_utterance(
            &utterance,
            &PlanOptions {
                body,
                t0: start,
                rate: input["rate"].as_f64(),
                intonation,
                f0: Some(f0),
                ..PlanOptions::default()
            },
        );
        if lateral_scale != 1.0 {
            for gesture in &mut plan.gestures {
                if let Some(target) = gesture.targets.get(ArticKey::Lateral) {
                    gesture
                        .targets
                        .set(ArticKey::Lateral, target * lateral_scale);
                }
            }
        }
        voice.schedule(&plan.gestures);
        end = plan.end;
        start = end + pause;
        results.push(plan);
    }
    if singing {
        let plan = song(
            &speech["score"],
            speech["vibrato_cents"].as_f64().unwrap_or(35.0),
            body,
        )?;
        voice.schedule(&plan.gestures);
        end = plan.end;
        results.push(plan);
    }
    let scale = speech["turbulence"]["scale"].as_f64().or_else(|| {
        (singing
            || results
                .iter()
                .flat_map(|plan| &plan.segments)
                .any(|part| {
                    matches!(part.ipa.as_str(),
                        "s" | "z" | "ʃ" | "ɕ" | "ʑ" | "ʂ" | "f" | "v" | "ð" | "x"
                        | "ts" | "tɕ" | "dʑ" | "tʃ" | "dʒ" | "tʂ" | "h" | "ɦ")
                }))
        .then_some(1.0)
    });
    let observe_nasal = results
        .iter()
        .flat_map(|plan| &plan.segments)
        .any(|part| matches!(part.ipa.as_str(), "m" | "n" | "ŋ"));
    let observe_glottal = results
        .iter()
        .flat_map(|plan| &plan.segments)
        .any(|part| matches!(part.ipa.as_str(), "h" | "ɦ"));
    let observe_glottal_stop = results
        .iter()
        .flat_map(|plan| &plan.segments)
        .any(|part| part.ipa == "ʔ");
    let observe_glide = results
        .iter()
        .flat_map(|plan| &plan.segments)
        .any(|part| matches!(part.ipa.as_str(), "j" | "ɰ"));
    let observe_affricate = results
        .iter()
        .flat_map(|plan| &plan.segments)
        .any(|part| matches!(part.ipa.as_str(), "ts" | "tɕ" | "dʑ" | "tʃ" | "dʒ" | "tʂ"));
    let observe_tap = results
        .iter()
        .flat_map(|plan| &plan.segments)
        .any(|part| part.ipa == "ɾ");
    let observe_labiodental = results
        .iter()
        .flat_map(|plan| &plan.segments)
        .any(|part| matches!(part.ipa.as_str(), "f" | "v"));
    let observe_retroflex = results
        .iter()
        .flat_map(|plan| &plan.segments)
        .any(|part| matches!(part.ipa.as_str(), "ʂ" | "tʂ"));
    let observe_rhotic = results
        .iter()
        .flat_map(|plan| &plan.segments)
        .any(|part| matches!(part.ipa.as_str(), "ɹ" | "ɻ"));
    let observe_tongue_root = results
        .iter()
        .flat_map(|plan| &plan.segments)
        .any(|part| part.ipa == "ɹ");
    let observe_sibilant_posture = observe_affricate
        || observe_retroflex
        || results
            .iter()
            .flat_map(|plan| &plan.segments)
            .any(|part| matches!(part.ipa.as_str(), "ʃ" | "ɕ" | "ʑ"));
    let observe_velar_fricative = results
        .iter()
        .flat_map(|plan| &plan.segments)
        .any(|part| part.ipa == "x");
    let observe_dorsum = observe_glide
        || observe_velar_fricative
        || results
            .iter()
            .flat_map(|plan| &plan.segments)
            .any(|part| matches!(part.ipa.as_str(), "k" | "g" | "ŋ"));
    let observe_oral_cells = observe_dorsum
        || observe_sibilant_posture
        || observe_tap
        || observe_labiodental
        || observe_rhotic
        || observe_glottal_stop
        || results
            .iter()
            .flat_map(|plan| &plan.segments)
            .any(|part| matches!(part.ipa.as_str(), "t" | "d" | "ð" | "n" | "w" | "l" | "ɫ"));
    let observe_oral_posture = observe_dorsum
        || observe_sibilant_posture
        || observe_tap
        || observe_rhotic
        || results
            .iter()
            .flat_map(|plan| &plan.segments)
            .any(|part| matches!(part.ipa.as_str(), "w" | "l" | "ɫ"));
    let observe_lateral = results
        .iter()
        .flat_map(|plan| &plan.segments)
        .any(|part| matches!(part.ipa.as_str(), "l" | "ɫ"));
    voice.airway.net.noise_scale = scale.unwrap_or(0.0);
    if let Some(multiplier) = speech["turbulence"]["glottis_gain_multiplier"].as_f64() {
        if !multiplier.is_finite() || multiplier < 0.0 {
            return Err("声門の乱流源の倍率は有限で0以上の値を指定してください".into());
        }
        voice.airway.noise_gain.glottis *= multiplier;
    }
    if let Some(multiplier) = speech["turbulence"]["constriction_gain_multiplier"].as_f64() {
        if !multiplier.is_finite() || multiplier < 0.0 {
            return Err("狭窄の乱流源の倍率は有限で0以上の値を指定してください".into());
        }
        voice.airway.noise_gain.constriction *= multiplier;
    }
    let seconds = if singing {
        end + 0.4
    } else if english {
        end + 0.30
    } else {
        start + 0.20
    };
    let frames = (rate * seconds).round() as usize;
    let mut plan_writer = BufWriter::new(File::create_new(plans)?);
    serde_json::to_writer_pretty(
        &mut plan_writer,
        &json!({"plans":results,"output_frames":frames}),
    )?;
    writeln!(plan_writer)?;
    plan_writer.flush()?;

    let mut out = BufWriter::new(File::create_new(trace)?);
    let mut audio_file = BufWriter::new(File::create_new(pcm)?);
    if let Some(selected) = speech.get("tract_profile_frames") {
        let selected: Vec<usize> = serde_json::from_value(selected.clone())?;
        let acoustics = speech["tract_profile_acoustics"].as_bool().unwrap_or(false);
        let grid = speech["tract_profile_grid"].as_bool().unwrap_or(false);
        return tract_profile(
            &mut voice,
            frames,
            &selected,
            (acoustics, grid),
            &mut out,
            &mut audio_file,
        );
    }
    write!(
        out,
        concat!(
            "frame,lip_aperture_cm,lip_minimum_cm2,lip_area_cm2,lip_flow_cm3_s,nose_flow_cm3_s,",
            "pressure_sub_dyn_cm2,pressure_supra_dyn_cm2,lung_boundary_dyn_cm2,gate,",
            "abduction_cm2,glottal_area_cm2,glottal_flow_cm3_s,glottal_voicing,",
            "glottal_f0_hz,radiation_derivative_cm3_s2"
        )
    )?;
    if scale.is_some() {
        noise_header(&mut out)?;
    }
    if observe_glottal {
        write!(out, ",glottis_jet_area_cm2")?;
    }
    if observe_glottal_stop {
        write!(out, ",glottal_closure_command,glottal_phase")?;
    }
    if observe_nasal {
        write!(
            out,
            ",velum_position_cm2,velum_effective_cm2,velum_port_area_cm2,velum_flow_cm3_s,oral_min_cell_area_cm2"
        )?;
    }
    if observe_oral_posture {
        write!(
            out,
            ",lip_protrusion_cm,lip_spread,tongue_body_x_cm,tongue_body_y_cm"
        )?;
    }
    if observe_glide || observe_sibilant_posture {
        write!(out, ",jaw_cm")?;
    }
    if observe_lateral {
        write!(out, ",lateral_position,lateral_effective")?;
    }
    if observe_retroflex || observe_rhotic {
        write!(out, ",tongue_tip_curl")?;
    }
    if observe_tongue_root {
        write!(out, ",tongue_root_cm")?;
    }
    if observe_oral_cells {
        write!(
            out,
            ",tongue_tip_x_cm,tongue_tip_y_cm,oral_minimum_cm2,oral_minimum_cell"
        )?;
        for cell in 0..voice.airway.oral.n {
            write!(out, ",oral_cell_{cell}_minimum_cm2")?;
        }
    }
    if singing {
        write!(out, ",smoothed_f0_hz")?;
    }
    if observe_labiodental {
        write!(out, ",labiodental,lower_lip_edge_x_cm,lower_lip_edge_y_cm")?;
    }
    if observe_dorsum || observe_rhotic {
        write!(out, ",pharynx_minimum_cm2")?;
    }
    if observe_velar_fricative || observe_retroflex {
        write!(out, ",pharynx_anatomical_length_cm,oral_anatomical_length_cm,pharynx_cells,oral_cells")?;
    }
    if observe_affricate || observe_tap {
        for branch in 0..voice.airway.oral.n - 1 {
            write!(out, ",oral_branch_{branch}_flow_cm3_s")?;
        }
    }
    writeln!(out)?;
    let mut prior_areas = Vec::new();
    let mut prior_flows = Vec::new();
    let mut audio = [0.0f32];
    for frame in 0..frames {
        if scale.is_some() && frame % 64 == 0 {
            prior_areas.clone_from(&voice.airway.net.branch_area);
            prior_flows.clone_from(&voice.airway.net.u);
        }
        voice.render(&mut audio);
        audio_file.write_all(&audio[0].to_le_bytes())?;
        let air = &voice.airway;
        let net = &air.net;
        let lip = air.oral.last_node();
        write!(out, "{frame}")?;
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
        ] {
            write!(out, ",{value}")?;
        }
        if scale.is_some() {
            noise_row(&mut out, air, &prior_areas, &prior_flows)?;
        }
        if observe_glottal {
            write!(out, ",{}", net.branch_area[air.glottis_port])?;
        }
        if observe_glottal_stop {
            write!(out, ",{},{}", voice.glottis.params.closure, voice.glottis.cycle_phase())?;
        }
        if observe_nasal {
            write!(
                out,
                ",{},{},{},{},{}",
                voice.artic.x.get(ArticKey::Velum),
                voice.artic.effective.get(ArticKey::Velum),
                net.port_area[air.velum_port],
                net.u[air.velum_port],
                net.area[air.oral.first_node()..=air.oral.last_node()]
                    .iter()
                    .copied()
                    .fold(f64::INFINITY, f64::min)
            )?;
        }
        if observe_oral_posture {
            for axis in [
                ArticKey::LipProt,
                ArticKey::LipWidth,
                ArticKey::TbX,
                ArticKey::TbY,
            ] {
                write!(out, ",{}", voice.artic.x.get(axis))?;
            }
        }
        if observe_glide || observe_sibilant_posture {
            write!(out, ",{}", voice.artic.x.get(ArticKey::Jaw))?;
        }
        if observe_lateral {
            write!(
                out,
                ",{},{}",
                voice.artic.x.get(ArticKey::Lateral),
                voice.artic.effective.get(ArticKey::Lateral)
            )?;
        }
        if observe_retroflex || observe_rhotic {
            write!(out, ",{}", voice.artic.x.get(ArticKey::TtCurl))?;
        }
        if observe_tongue_root {
            write!(out, ",{}", voice.artic.x.get(ArticKey::Root))?;
        }
        if observe_oral_cells {
            let areas = &net.amin[air.oral.first_node()..=air.oral.last_node()];
            let (cell, area) = areas
                .iter()
                .copied()
                .enumerate()
                .min_by(|(_, a), (_, b)| a.total_cmp(b))
                .expect("口腔のセル");
            write!(
                out,
                ",{},{},{area},{cell}",
                voice.artic.x.get(ArticKey::TtX),
                voice.artic.x.get(ArticKey::TtY)
            )?;
            for area in areas {
                write!(out, ",{area}")?;
            }
        }
        if singing {
            write!(out, ",{}", voice.glottis.params.f0)?;
        }
        if observe_labiodental {
            let frame = air.frame.as_ref().ok_or("声道の輪郭を取得できません")?;
            // 先頭の7点が下唇の内側で、最後の内側点が開口端。
            let edge = frame.lower_lip[6];
            write!(out, ",{},{},{}", voice.artic.x.get(ArticKey::Labiodental), edge.x, edge.y)?;
        }
        if observe_dorsum || observe_rhotic {
            let minimum = net.amin[air.pharynx.first_node()..=air.pharynx.last_node()]
                .iter()
                .copied()
                .fold(f64::INFINITY, f64::min);
            write!(out, ",{minimum}")?;
        }
        if observe_velar_fricative || observe_retroflex {
            write!(out, ",{},{},{},{}", air.ph_len, air.or_len, air.n_ph, air.n_or)?;
        }
        if observe_affricate || observe_tap {
            for branch in 0..air.oral.n - 1 {
                write!(out, ",{}", net.u[air.oral.branch(branch)])?;
            }
        }
        writeln!(out)?;
    }
    out.flush()?;
    audio_file.flush()?;
    Ok(())
}

fn tract_profile(
    voice: &mut HumanVoice,
    frames: usize,
    selected: &[usize],
    (acoustics, grid): (bool, bool),
    out: &mut impl Write,
    pcm: &mut impl Write,
) -> Result<(), Box<dyn Error>> {
    if grid {
        write!(out, "frame,ray,region,inner_x_cm,inner_y_cm,outer_x_cm,outer_y_cm,mid_x_cm,mid_y_cm,ray_cm,gap_cm,area_cm2,s_cm")?;
    } else {
        write!(out, "frame,tube,cell,length_cm,area_cm2,minimum_area_cm2")?;
    }
    let oral_link = if acoustics {
        write!(out, ",pressure_dyn_cm2,outward_flow_cm3_s")?;
        let airway = &voice.airway;
        let linear = airway.net.linear_elements();
        Some(
            linear
                .a
                .iter()
                .zip(&linear.b)
                .position(|(&a, &b)| {
                    a == airway.pharynx.last_node() && b == airway.oral.first_node()
                })
                .ok_or("固定上流の咽頭と口腔を結ぶ枝がありません")?,
        )
    } else {
        None
    };
    writeln!(out)?;
    let mut samples = selected.iter().copied().peekable();
    let mut audio = [0.0f32];
    for frame in 0..frames {
        voice.render(&mut audio);
        pcm.write_all(&audio[0].to_le_bytes())?;
        if samples.peek() != Some(&frame) {
            continue;
        }
        samples.next();
        let airway = &voice.airway;
        if grid {
            let geometry = airway.frame.as_ref().ok_or("固定上流の声道形状がありません")?;
            for (index, ray) in geometry.grid.iter().enumerate() {
                writeln!(out, "{frame},{index},{},{},{},{},{},{},{},{},{},{},{}",
                    ray.region, ray.inner.x, ray.inner.y, ray.outer.x, ray.outer.y,
                    ray.mid.x, ray.mid.y, ray.ray, ray.d, ray.area, ray.s)?;
            }
            continue;
        }
        let net = &airway.net;
        for (name, tube) in [("pharynx", airway.pharynx), ("oral", airway.oral)] {
            for cell in 0..tube.n {
                let index = tube.node(cell);
                write!(
                    out,
                    "{frame},{name},{cell},{},{},{}",
                    net.dx[index], net.area[index], net.amin[index]
                )?;
                if let Some(oral_link) = oral_link {
                    let flow = if cell + 1 < tube.n {
                        net.u[tube.branch(cell)]
                    } else if tube == airway.pharynx {
                        net.u[oral_link]
                    } else {
                        net.rad_u[airway.rad_lips]
                    };
                    write!(out, ",{},{flow}", net.p[index])?;
                }
                writeln!(out)?;
            }
        }
    }
    if samples.peek().is_some() {
        return Err("固定上流で採取できないフレームがあります".into());
    }
    out.flush()?;
    pcm.flush()?;
    Ok(())
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

fn noise_row(
    out: &mut impl Write,
    air: &HumanAirway,
    areas: &[f64],
    flows: &[f64],
) -> io::Result<()> {
    let net = &air.net;
    let list = net.noise_sources();
    let (cell, area) = air
        .ph_min
        .iter()
        .chain(&air.or_min)
        .copied()
        .enumerate()
        .filter(|(_, a)| *a > 0.0)
        .min_by(|a, b| a.1.total_cmp(&b.1))
        .map_or((-1, 0.0), |(i, a)| (i as isize, a));
    let distance = if cell < 0 {
        0.0
    } else {
        let i = cell as usize;
        let center = if i < air.n_ph {
            (i as f64 + 0.5) * (air.ph_len / air.n_ph as f64)
        } else {
            air.ph_len + ((i - air.n_ph) as f64 + 0.5) * (air.or_len / air.n_or as f64)
        };
        air.frame.as_ref().unwrap().teeth_s - center
    };
    let (jet_area, jet_flow) = list
        .get(1)
        .map_or((0.0, 0.0), |s| (areas[s.src], flows[s.src]));
    write!(out, ",{cell},{area},{distance},{jet_area},{jet_flow}")?;
    for i in 0..3 {
        if let Some(spec) = list.get(i) {
            let source = if spec.src == air.glottis_port {
                -2
            } else {
                spec.src as isize
            };
            // 上流はフィルタ係数を非公開にしている。歯の低域通過周波数を制御直前の枝から復元する。
            let a = jet_area.max(1e-6);
            let d = 2.0 * (a / std::f64::consts::PI).sqrt();
            let lowpass = match i {
                0 => 3500.0,
                1 => 2600.0,
                _ => jet_flow.abs() * (d / a) / d.max(0.17 * distance).powi(2),
            };
            write!(
                out,
                ",{source},{},{},{},{},{},{},{}",
                spec.fwd,
                spec.bwd,
                spec.gain,
                lowpass,
                spec.level,
                net.psrc[spec.fwd],
                net.psrc[spec.bwd]
            )?;
        } else {
            write!(out, ",-1,-1,-1,0,0,0,0,0")?;
        }
    }
    Ok(())
}
