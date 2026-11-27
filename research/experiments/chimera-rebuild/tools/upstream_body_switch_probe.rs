//! 固定上流Engineの体型変更を保存ケースの出力フレームで実行する。
use chimera::anatomy::human::{ArticKey, ArticPatch, BodyMix};
use chimera::engine::Engine;
use chimera::voice::human_voice::{HumanVoice, SourcePatch};
use serde_json::Value;
use std::error::Error;
use std::fs::{self, File};
use std::io::{BufWriter, Write};

fn normalize(voice: &mut HumanVoice, gain: f64) {
    voice.airway.net.noise_scale = 0.0;
    voice.glottis.params.jitter = 0.0;
    voice.glottis.params.shimmer = 0.0;
    voice.output_gain = gain;
}

fn initial_posture(pose: &Value) -> ArticPatch {
    let mut patch = ArticPatch::default();
    let keys = [
        &pose["jaw_cm"],
        &pose["tongue_body_cm"][0],
        &pose["tongue_body_cm"][1],
        &pose["tongue_tip_cm"][0],
        &pose["tongue_tip_cm"][1],
        &pose["tip_curl"],
        &pose["tongue_root_cm"],
        &pose["lip_aperture_cm"],
        &pose["lip_protrusion_cm"],
        &pose["lip_spread"],
        &pose["labiodental"],
        &pose["velum_cm2"],
        &pose["larynx_cm"],
        &pose["epilarynx"],
        &pose["ventricular"],
        &pose["lateral"],
        &pose["dorsum"],
    ];
    for (axis, value) in ArticKey::ALL.into_iter().zip(keys) {
        patch.set(axis, value.as_f64().unwrap_or(0.0));
    }
    patch
}

fn main() -> Result<(), Box<dyn Error>> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    let [case_path, pcm_path, trace_path] = args.as_slice() else {
        return Err("ケース、PCM、観測の出力先を指定してください".into());
    };
    let case: Value = serde_json::from_slice(&fs::read(case_path)?)?;
    let cfg = &case["articulators"];
    let settings = &case["voice"];
    let rate = settings["output_sample_rate_hz"]
        .as_f64()
        .ok_or("出力レートがありません")?;
    if case["body"] != "male"
        || cfg["control_block_samples"] != 128
        || cfg["sample_rate_hz"] != 96000
        || rate != 48000.0
    {
        return Err("成人男性を始点にした登録済みの制御周期とレートが必要です".into());
    }
    let gain = settings["output_gain"]
        .as_f64()
        .ok_or("ゲインがありません")?;
    let total = case["measurement"]["frames"]
        .as_u64()
        .ok_or("計測長がありません")?
        * 64;
    let mut events = cfg["events"]
        .as_array()
        .ok_or("イベント列がありません")?
        .iter()
        .peekable();
    let mut engine = Engine::new(rate);
    let voice = engine.voice_mut();
    voice.artic.tip_free = cfg["tip_free"].as_bool().ok_or("舌先の設定がありません")?;
    voice.artic.snap(&initial_posture(&case["posture"]));
    voice.airway.apply(&voice.artic.x, 0.0);
    voice.airway.net.snap_to_targets();
    engine.set_source(&SourcePatch {
        f0: settings["f0_hz"].as_f64(),
        pressure: settings["pressure_cm_h2o"].as_f64(),
        breathiness: settings["breathiness"].as_f64(),
        tension: settings["tension"].as_f64(),
        drift: Some(0.0),
        ..SourcePatch::default()
    });
    normalize(engine.voice_mut(), gain);
    engine.set_gate(settings["gate"].as_f64().ok_or("初期呼気がありません")?);
    let mut pcm = BufWriter::new(File::create_new(pcm_path)?);
    let mut trace = BufWriter::new(File::create_new(trace_path)?);
    writeln!(
        trace,
        concat!(
            "frame,gate,glottal_area_cm2,glottal_flow_cm3_s,glottal_phase,glottal_voicing,glottal_f0_hz,",
            "radiation_derivative_cm3_s2,lip_aperture_cm,lip_minimum_cm2,tongue_body_x_cm,tongue_body_y_cm,",
            "oral_minimum_cm2,voice_clock_seconds,pharynx_cells,oral_cells,lip_target_cm",
        )
    )?;
    let mut sample = [0.0_f32];
    for frame in 0..total {
        if let Some(event) =
            events.next_if(|event| event["frame"].as_u64().is_some_and(|f| 64 * f == frame))
        {
            if let Some(gate) = event["gate"].as_f64() {
                engine.set_gate(gate);
            }
            if let Some(targets) = event["targets"].as_object() {
                let mut patch = ArticPatch::default();
                for (name, value) in targets {
                    let axis = match name.as_str() {
                        "tongue_body_x_cm" => ArticKey::TbX,
                        "tongue_body_y_cm" => ArticKey::TbY,
                        "lip_aperture_cm" => ArticKey::LipAp,
                        _ => return Err(format!("未登録の手動軸 {name}").into()),
                    };
                    patch.set(axis, value.as_f64().ok_or("目標が数値ではありません")?);
                }
                engine.set_artic(&patch, None);
            }
            if let Some(body) = event.get("body") {
                engine.set_body(serde_json::from_value::<BodyMix>(body.clone())?);
                normalize(engine.voice_mut(), gain);
            }
        }
        engine.render(&mut sample);
        pcm.write_all(&sample[0].to_le_bytes())?;
        let voice = engine.voice();
        let airway = &voice.airway;
        let net = &airway.net;
        let oral = airway.oral.node(airway.n_or / 2 - 1);
        write!(trace, "{frame}")?;
        for value in [
            voice.gate,
            voice.glottis.area,
            net.u[airway.glottis_port],
            voice.glottis.cycle_phase(),
            voice.glottis.voicing,
            voice.glottis.f0_now,
            net.out,
            voice.artic.x.get(ArticKey::LipAp),
            net.amin[airway.oral.last_node()],
            voice.artic.x.get(ArticKey::TbX),
            voice.artic.x.get(ArticKey::TbY),
            net.amin[oral],
            engine.clock(),
            airway.n_ph as f64,
            airway.n_or as f64,
            voice.artic.target.get(ArticKey::LipAp),
        ] {
            write!(trace, ",{value}")?;
        }
        writeln!(trace)?;
    }
    trace.flush()?;
    pcm.flush()?;
    Ok(())
}
