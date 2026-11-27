//! 固定版の予約時刻、音源の観測と通常EngineのPCMを保存する。

use chimera::{
    anatomy::human::{ArticKey, ArticPatch, BodyMix, NEUTRAL},
    control::beat_player::BeatPlayer,
    engine::{Engine, SUB_BLOCK},
    math::midi_to_hz,
    phonetics::beatbox::{BASS_NOTE, BeatStep, beat_ready, parse_beat},
    voice::human_voice::{DEFAULT_SOURCE, SourcePatch, oversample_for},
};
use serde_json::{Value, json};
use std::{
    error::Error,
    fs::File,
    io::{BufWriter, Write},
    path::Path,
};
mod upstream_beatbox_oral_trace;

enum Event {
    Tempo(Option<f64>, Option<f64>),
    Playing(bool),
    BassKey(u8, bool),
    ToggleHum(usize),
}

// ブラウザのストアが作る調音・音高・セル操作を、採用フレームでEngineに渡す。
struct BeatEdits {
    steps: Vec<Option<BeatStep>>,
    held: Vec<u8>,
    last_pressed: f64,
}

impl BeatEdits {
    fn new(steps: &[Option<BeatStep>]) -> Self {
        Self {
            steps: steps.to_vec(),
            held: Vec::new(),
            last_pressed: BASS_NOTE,
        }
    }

    fn apply(
        &mut self,
        event: &Event,
        engine: &mut Engine,
        player: Option<&mut BeatPlayer>,
        clock: f64,
    ) -> Result<(), Box<dyn Error>> {
        match *event {
            Event::Tempo(bpm, swing) => {
                engine.set_beat_tempo(bpm, swing);
                if let Some(p) = player {
                    p.set_tempo(bpm.unwrap_or(p.bpm), swing.unwrap_or(p.swing));
                }
            }
            Event::Playing(playing) => {
                engine.set_beat_playing(playing);
                if let Some(p) = player {
                    if playing && !p.playing {
                        p.start(clock);
                    } else if !playing && p.playing {
                        p.stop();
                    }
                }
            }
            Event::BassKey(note, pressed) => {
                self.held.retain(|&held| held != note);
                if pressed {
                    self.held.push(note);
                    self.last_pressed = f64::from(note);
                }
                if let Some(&last) = self.held.last() {
                    engine.set_source(&SourcePatch {
                        f0: Some(midi_to_hz(f64::from(last))),
                        ..SourcePatch::default()
                    });
                }
                let held = !self.held.is_empty();
                let lip = if held {
                    -0.25
                } else {
                    beat_ready(BodyMix::MALE)
                        .get(ArticKey::LipAp)
                        .ok_or("準備姿勢の唇目標がありません")?
                };
                let patch = ArticPatch::default()
                    .with(ArticKey::LipAp, lip)
                    .with(ArticKey::Velum, if held { 0.9 } else { NEUTRAL.velum });
                engine.set_artic(&patch, None);
                engine.set_gate(if held { 1.0 } else { 0.0 });
            }
            Event::ToggleHum(index) => {
                let cell = self
                    .steps
                    .get_mut(index)
                    .ok_or("ハムのステップが範囲外です")?;
                *cell = if cell.is_some_and(|step| step.id.as_str() == "m") {
                    None
                } else {
                    parse_beat(&format!("m:{}", self.last_pressed))[0]
                };
                engine.set_beat_steps(&self.steps);
                if let Some(p) = player {
                    p.set_steps(&self.steps);
                }
            }
        }
        Ok(())
    }
}

fn number(value: &Value, key: &str) -> Result<f64, Box<dyn Error>> {
    value[key]
        .as_f64()
        .ok_or_else(|| format!("数値設定がありません ({key})").into())
}

fn write_pcm(path: &Path, audio: &[f32]) -> Result<(), Box<dyn Error>> {
    let mut output = BufWriter::new(File::create_new(path)?);
    for sample in audio {
        output.write_all(&sample.to_le_bytes())?;
    }
    output.flush()?;
    Ok(())
}

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let [case_path, artifacts] = args.as_slice() else {
        return Err("ケースと保存先を指定してください".into());
    };
    let artifacts = Path::new(artifacts);
    let case: Value = serde_json::from_slice(&std::fs::read(case_path)?)?;
    let input = &case["beatbox_pattern"];
    let settings = &input["voice"];
    let pattern = input["pattern"].as_str().ok_or("パターンがありません")?;
    let rate = number(settings, "output_sample_rate_hz")?;
    let bpm = number(input, "bpm")?;
    let swing = number(input, "swing")?;
    let frames = (rate * number(input, "render_end_seconds")?).round() as usize;
    let mut events = Vec::new();
    if let Some(entries) = input["events"].as_array() {
        for entry in entries {
            let frame = entry["frame"]
                .as_u64()
                .ok_or("操作のフレームがありません")? as usize;
            if frame >= frames || events.last().is_some_and(|(previous, _)| *previous > frame) {
                return Err("操作を描画範囲内の時刻順に並べてください".into());
            }
            let event = match entry["type"].as_str() {
                Some("tempo") => Event::Tempo(entry["bpm"].as_f64(), entry["swing"].as_f64()),
                Some("playing") => {
                    Event::Playing(entry["playing"].as_bool().ok_or("再生状態がありません")?)
                }
                Some("bass_key") => Event::BassKey(
                    entry["note"]
                        .as_u64()
                        .filter(|&n| n <= 127)
                        .ok_or("音番号が範囲外です")? as u8,
                    entry["pressed"].as_bool().ok_or("押下状態がありません")?,
                ),
                Some("toggle_hum") => Event::ToggleHum(
                    entry["step"].as_u64().ok_or("ステップ指定がありません")? as usize,
                ),
                _ => return Err("不明な再生操作です".into()),
            };
            events.push((frame, event));
        }
    }
    if number(input, "initial_f0_hz")? != DEFAULT_SOURCE.f0
        || number(input, "internal_sample_rate_hz")? != rate * oversample_for(rate) as f64
    {
        return Err("上流Engineの初期F0と内部レートに合わせてください".into());
    }
    let ready = beat_ready(BodyMix::MALE);
    let source = SourcePatch {
        f0: Some(number(settings, "f0_hz")?),
        voiced: Some(true),
        pressure: Some(number(settings, "pressure_cm_h2o")?),
        breathiness: Some(number(settings, "breathiness")?),
        tension: Some(number(settings, "tension")?),
        ..SourcePatch::default()
    };
    let gate = number(settings, "gate")?;
    let noise_scale = number(input, "noise_scale")?;
    let output_gain = number(settings, "output_gain")?;
    let steps = parse_beat(pattern);
    let observe_labiodental = steps.iter().flatten().any(|step| step.id.as_str() == "Pf");
    let observe_inward = steps.iter().flatten().any(|step| step.id.as_str() == "^K");
    let observe_lip_pop = steps.iter().flatten().any(|step| step.id.as_str() == "P!");
    let observe_crash = steps.iter().flatten().any(|step| step.id.as_str() == "kch");
    let observe_midi = events
        .iter()
        .any(|(_, event)| matches!(event, Event::BassKey(..) | Event::ToggleHum(_)));
    let observe_hum = observe_midi || steps.iter().flatten().any(|step| step.id.as_str() == "m");
    let observe_pocket =
        observe_lip_pop || steps.iter().flatten().any(|step| step.id.as_str() == "!");
    let observe_velar = observe_inward
        || observe_pocket
        || observe_crash
        || steps.iter().flatten().any(|step| step.id.as_str() == "K");
    let observe_oral = observe_labiodental
        || observe_hum
        || observe_velar
        || steps
            .iter()
            .flatten()
            .any(|step| matches!(step.id.as_str(), "t" | "tss"));
    let setup = || {
        let mut engine = Engine::new(rate);
        engine.set_artic(&ready, None);
        engine.set_source(&source);
        engine.set_gate(gate);
        engine.voice_mut().output_gain = output_gain;
        engine.voice_mut().airway.net.noise_scale = noise_scale;
        engine.set_beat_steps(&steps);
        engine.set_beat_tempo(Some(bpm), Some(swing));
        engine.set_beat_playing(true);
        engine
    };

    for block in case["measurement"]["host_block_frames"]
        .as_array()
        .ok_or("ホスト幅がありません")?
    {
        let block = block.as_u64().filter(|&n| n > 0).ok_or("不正なホスト幅")? as usize;
        let mut engine = setup();
        let mut pcm = vec![0.0f32; frames];
        let mut commands = events.iter().peekable();
        let mut edits = BeatEdits::new(&steps);
        let mut frame = 0;
        while frame < frames {
            while let Some((_, event)) = commands.next_if(|(time, _)| *time == frame) {
                let clock = engine.clock();
                edits.apply(event, &mut engine, None, clock)?;
            }
            let next_event = commands.peek().map_or(frames, |(time, _)| *time);
            let end = (frame + block).min(next_event);
            engine.render(&mut pcm[frame..end]);
            frame = end;
        }
        write_pcm(
            &artifacts.join(format!("upstream-engine-{block}.f32")),
            &pcm,
        )?;
    }

    let mut engine = setup();
    let voice = engine.voice_mut();
    let initial = voice.artic.x;
    let mut player = BeatPlayer::new();
    player.set_steps(&steps);
    player.set_tempo(bpm, swing);
    player.start(voice.clock);
    let mut trace = BufWriter::new(File::create_new(artifacts.join("upstream-trace.csv"))?);
    write!(
        trace,
        concat!(
            "frame,lip_minimum_cm2,lip_flow_cm3_s,pressure_supra_dyn_cm2,",
            "gate,glottal_area_cm2,glottal_f0_hz,larynx_cm,beat_step"
        )
    )?;
    if observe_oral {
        write!(
            trace,
            concat!(
                ",tongue_tip_x_cm,tongue_tip_y_cm,oral_minimum_cm2,abduction_cm2,",
                "glottal_voicing,glottal_flow_cm3_s,glottis_noise_level,constriction_noise_level,teeth_noise_level"
            )
        )?;
    }
    if observe_labiodental {
        write!(trace, ",labiodental")?;
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
            ",lung_boundary_dyn_cm2,constriction_jet_flow_cm3_s,constriction_noise_forward_pressure,constriction_noise_reverse_pressure"
        )?;
    }
    if observe_lip_pop {
        write!(trace, ",jaw_cm,lip_area_cm2")?;
    }
    if observe_crash {
        write!(
            trace,
            ",constriction_noise_tract_cell,lip_protrusion_cm,lip_spread"
        )?;
    }
    if observe_pocket {
        upstream_beatbox_oral_trace::header(&mut trace, voice)?;
    } else if observe_crash {
        upstream_beatbox_oral_trace::minima_header(&mut trace, voice)?;
    }
    if observe_midi {
        write!(trace, ",lip_aperture_cm")?;
    }
    if observe_hum {
        write!(trace, ",nose_flow_cm3_s")?;
        upstream_beatbox_oral_trace::nasal_header(&mut trace)?;
    }
    writeln!(trace)?;
    let mut hits = Vec::new();
    let mut commands = events.iter().peekable();
    let mut observed_events = Vec::new();
    let mut edits = BeatEdits::new(&steps);
    let mut pcm = vec![0.0f32; frames];
    for (frame, output) in pcm.iter_mut().enumerate() {
        let clock = engine.clock();
        while let Some((_, event)) = commands.next_if(|(time, _)| *time == frame) {
            edits.apply(event, &mut engine, Some(&mut player), clock)?;
            observed_events.push(json!({"frame": frame, "clock_seconds": clock}));
        }
        if frame % SUB_BLOCK == 0 {
            player.tick(clock, &mut |gestures| {
                hits.push(json!({"frame": frame, "clock_seconds": clock, "gestures": gestures}));
            });
        }
        engine.render(std::slice::from_mut(output));
        let position = engine.beat_step();
        if position != player.step_at(engine.clock()) {
            return Err(format!("予約観測器とEngineの再生位置が異なります ({frame})").into());
        }
        let voice = engine.voice_mut();
        let air = &voice.airway;
        let net = &air.net;
        let lip = air.oral.last_node();
        write!(
            trace,
            "{frame},{},{},{},{},{},{},{},{}",
            net.amin[lip],
            net.radiated_flow(air.rad_lips),
            net.p[air.pharynx.first_node()],
            voice.gate,
            voice.glottis.area,
            voice.glottis.f0_now,
            voice.artic.x.get(ArticKey::Larynx),
            position,
        )?;
        if observe_oral {
            let oral_minimum = net.amin[air.oral.first_node()..=lip]
                .iter()
                .copied()
                .fold(f64::INFINITY, f64::min);
            for value in [
                voice.artic.x.get(ArticKey::TtX),
                voice.artic.x.get(ArticKey::TtY),
                oral_minimum,
                voice.glottis.params.abduction,
                voice.glottis.voicing,
                net.u[air.glottis_port],
            ] {
                write!(trace, ",{value}")?;
            }
            for i in 0..3 {
                let level = net
                    .noise_sources()
                    .get(i)
                    .map_or(0.0, |source| source.level);
                write!(trace, ",{level}")?;
            }
        }
        if observe_labiodental {
            write!(trace, ",{}", voice.artic.x.get(ArticKey::Labiodental))?;
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
            write!(trace, ",{},{flow},{forward},{reverse}", net.p[air.lungs])?;
        }
        if observe_lip_pop {
            write!(
                trace,
                ",{},{}",
                voice.artic.x.get(ArticKey::Jaw),
                net.area[lip]
            )?;
        }
        if observe_crash {
            let cell = upstream_beatbox_oral_trace::constriction_noise_tract_cell(air);
            let lip_protrusion = voice.artic.x.get(ArticKey::LipProt);
            let lip_spread = voice.artic.x.get(ArticKey::LipWidth);
            write!(trace, ",{cell},{lip_protrusion},{lip_spread}")?;
        }
        if observe_pocket {
            upstream_beatbox_oral_trace::row(&mut trace, voice)?;
        } else if observe_crash {
            upstream_beatbox_oral_trace::minima_row(&mut trace, voice)?;
        }
        if observe_midi {
            write!(trace, ",{}", voice.artic.x.get(ArticKey::LipAp))?;
        }
        if observe_hum {
            write!(trace, ",{}", net.radiated_flow(air.rad_nose))?;
            upstream_beatbox_oral_trace::nasal_row(&mut trace, voice)?;
        }
        writeln!(trace)?;
    }
    trace.flush()?;
    write_pcm(&artifacts.join("upstream-probe.f32"), &pcm)?;
    let mut report = BufWriter::new(File::create_new(artifacts.join("upstream-plan.json"))?);
    let mut plan = json!({
            "initial_posture": initial, "ready_targets": ready, "hits": hits,
            "slot_accents": steps.iter().map(|step| step.map(|s| s.accent.unwrap_or(1.0))).collect::<Vec<_>>(),
            "slot_sounds": steps.iter().map(|step| step.as_ref().map(|s| s.id.as_str())).collect::<Vec<_>>(),
    });
    if observe_hum || steps.iter().flatten().any(|step| step.note.is_some()) {
        let notes: Vec<_> = steps.iter().map(|step| step.and_then(|s| s.note)).collect();
        plan["slot_midi_notes"] = json!(notes);
    }
    if observe_midi {
        plan["midi_edited_slot_notes"] = json!(
            edits
                .steps
                .iter()
                .map(|step| step.and_then(|s| s.note))
                .collect::<Vec<_>>()
        );
    }
    if !observed_events.is_empty() {
        plan["transport_events"] = json!(observed_events);
    }
    serde_json::to_writer_pretty(&mut report, &plan)?;
    writeln!(report)?;
    report.flush()?;
    Ok(())
}
