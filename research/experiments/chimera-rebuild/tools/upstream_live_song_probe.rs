//! 固定上流のブラウザで採取した歌唱スケジュールを、候補の採用時刻へ揃えて再生する。

use chimera::{
    anatomy::human::{ArticKey, ArticPatch, BodyMix},
    control::score::Gesture,
    engine::Engine,
    voice::human_voice::SourcePatch,
};
use serde_json::{Value, json};
use std::{
    error::Error,
    fs::{self, File},
    io::{BufWriter, Write},
};

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let [case, trace, pcm] = args.as_slice() else {
        return Err("イベント表と観測CSV・PCMの保存先を指定してください".into());
    };
    let input: Value = serde_json::from_slice(&fs::read(case)?)?;
    let settings = &input["voice"];
    let number = |key: &str| settings[key].as_f64().ok_or("音源の設定値がありません");
    let rate = number("output_sample_rate_hz")?;
    let mut engine = Engine::new(rate);
    let body: BodyMix = serde_json::from_value(input["body"].clone())?;
    if body != BodyMix::MALE {
        engine.set_body(body);
    }
    engine.set_source(&SourcePatch {
        f0: Some(number("f0_hz")?),
        pressure: Some(number("pressure_cm_h2o")?),
        breathiness: Some(number("breathiness")?),
        tension: Some(number("tension")?),
        drift: Some(0.0),
        ..SourcePatch::default()
    });
    {
        let voice = engine.voice_mut();
        let p = &input["posture"];
        let pose = json!({
            "jaw":p["jaw_cm"],"tbX":p["tongue_body_cm"][0],"tbY":p["tongue_body_cm"][1],
            "ttX":p["tongue_tip_cm"][0],"ttY":p["tongue_tip_cm"][1],"ttCurl":p["tip_curl"],
            "root":p["tongue_root_cm"],"lipAp":p["lip_aperture_cm"],"lipProt":p["lip_protrusion_cm"],
            "lipWidth":p["lip_spread"],"labiodental":p["labiodental"],"velum":p["velum_cm2"],
            "larynx":p["larynx_cm"],"dorsum":p["dorsum"]
        });
        let posture: ArticPatch = serde_json::from_value(pose)?;
        voice.artic.snap(&posture);
        voice.airway.apply(&voice.artic.x, 0.0);
        voice.airway.net.snap_to_targets();
        voice.airway.net.noise_scale = 1.0;
        voice.glottis.params.jitter = 0.0;
        voice.glottis.params.shimmer = 0.0;
        voice.output_gain = number("output_gain")?;
    }
    engine.set_gate(number("gate")?);
    let frames = input["frames"]
        .as_u64()
        .ok_or("出力フレーム数がありません")?;
    let mut events = input["events"]
        .as_array()
        .ok_or("イベント表がありません")?
        .iter()
        .peekable();
    let mut out = BufWriter::new(File::create_new(trace)?);
    let mut audio = BufWriter::new(File::create_new(pcm)?);
    writeln!(
        out,
        concat!(
            "frame,lip_aperture_cm,lip_minimum_cm2,gate,voicing,lip_flow_cm3_s,",
            "glottal_area_cm2,glottal_flow_cm3_s,radiation_derivative_cm3_s2,pcm_f32"
        )
    )?;
    for frame in 0..frames {
        if input["stop_frame"].as_u64() == Some(frame) {
            engine.stop_speech();
            engine.set_gate(0.0);
        }
        while events
            .peek()
            .is_some_and(|event| event["frame"].as_u64() == Some(frame))
        {
            for command in events.next().expect("時刻の揃ったイベント")["commands"]
                .as_array()
                .ok_or("イベントの操作列がありません")?
            {
                match command["type"].as_str() {
                    Some("schedule") => {
                        let gestures: Vec<Gesture> =
                            serde_json::from_value(command["gestures"].clone())?;
                        engine.schedule(
                            &gestures,
                            command["lead"].as_f64().ok_or("先読み時間がありません")?,
                            false,
                        );
                    }
                    Some("release") => {
                        engine.release(command["tag"].as_f64().ok_or("タグがありません")?)
                    }
                    _ => return Err("未知の歌唱操作です".into()),
                }
            }
        }
        let mut sample = [0.0f32];
        engine.render(&mut sample);
        let voice = engine.voice();
        let air = &voice.airway;
        let net = &air.net;
        let lip = voice.artic.x.get(ArticKey::LipAp);
        let minimum = net.amin[air.oral.last_node()];
        writeln!(
            out,
            "{frame},{lip},{minimum},{},{},{},{},{},{},{}",
            voice.gate,
            voice.glottis.voicing,
            net.radiated_flow(air.rad_lips),
            voice.glottis.area,
            net.u[air.glottis_port],
            net.out,
            sample[0]
        )?;
        audio.write_all(&sample[0].to_le_bytes())?;
    }
    if events.next().is_some() {
        return Err("出力範囲外または時刻順でないイベントがあります".into());
    }
    out.flush()?;
    audio.flush()?;
    Ok(())
}
