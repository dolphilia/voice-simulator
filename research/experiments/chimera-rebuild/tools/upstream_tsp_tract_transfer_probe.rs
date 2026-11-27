//! 固定上流の通常発話を描画し、指定フレーム直後の実効断面を線形化する。

mod tsp_transfer_request;

use chimera::{
    anatomy::human::BODY_MALE,
    airway::frequency::{find_peaks, transfer_function},
    math::js_round,
    phonetics::{english::EnglishG2P, planner::{PhraseInput, PlanOptions, plan_phrases}},
    physics::{C_SOUND, RHO},
    voice::human_voice::{HumanVoice, SourcePatch},
};
use serde_json::{Value, json};
use std::{error::Error, f64::consts::PI, fs, io::{BufWriter, Write}};
use tsp_transfer_request::TransferRequest;

fn snapshot(voice: &HumanVoice, request: &TransferRequest) -> Value {
    let airway = &voice.airway;
    let network = &airway.net;
    let el = network.linear_elements_at_current_geometry();
    let inject = airway.pharynx.first_node();
    let cut = airway.glottis_port;
    let lips = airway.oral.last_node();
    let nose = airway.nasal.last_node();
    let response = transfer_function(&el, inject, &request.frequencies, &[cut]);
    let mut radiators = vec![[0.0; 2]; el.n_nodes];
    for (&node, &area) in el.rad_nodes.iter().zip(&el.rad_area) {
        radiators[node] = [8.0 * RHO / (3.0 * PI * (PI * area).sqrt()),
                           128.0 * RHO * C_SOUND / (9.0 * PI * PI * area)];
    }
    let nodes: Vec<_> = (0..el.n_nodes).map(|i| json!([
        el.c[i], u8::from(el.fixed[i]), el.wall_area[i], el.wall_m[i], el.wall_r[i],
        el.wall_k[i], el.wall_rad[i], radiators[i][0], radiators[i][1]
    ])).collect();
    let branches: Vec<_> = (0..el.n_branches).map(|i| json!([
        el.a[i], el.b[i], u8::from(el.open[i]), el.l[i], el.r[i]
    ])).collect();
    let sections: Vec<_> = [("pharynx", airway.pharynx), ("oral", airway.oral)].into_iter()
        .flat_map(|(name, tube)| (0..tube.n).map(move |i| {
            let node = tube.node(i);
            json!([name, i, network.dx[node], network.area[node], network.amin[node]])
        })).collect();
    let peaks: Vec<_> = find_peaks(&request.frequencies, &response.mag, 150.0).into_iter()
        .map(|p| json!([p.freq, p.bw, p.db])).collect();
    json!({"completed_frames": request.completed_frames, "sections": sections, "nodes": nodes,
           "branches": branches, "inject": inject, "cut": [el.a[cut], el.b[cut]],
           "lips": lips, "nose": nose, "velum_cm2": network.port_area[airway.velum_port],
           "frequencies_hz": response.freqs, "magnitude": response.mag, "peaks": peaks})
}

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let [case, dictionary, study, pcm, geometry] = args.as_slice() else {
        return Err("発話ケース、辞書、計測条件、PCM・断面の出力先を指定してください".into());
    };
    let input: Value = serde_json::from_slice(&fs::read(case)?)?;
    let speech = &input["speech_voice"];
    if speech["body"] != "male" || speech["input"]["rate"] != 1.0 {
        return Err("男性・等速の発話を指定してください".into());
    }
    let text = speech["input"]["text"].as_str().ok_or("本文がありません")?;
    let request = TransferRequest::read(study)?;
    let mut g2p = EnglishG2P::new();
    g2p.load_dict(&fs::read_to_string(dictionary)?);
    let phrases: Vec<_> = g2p.to_phrases(text).into_iter().map(|p| PhraseInput {
        segments: p.segments, intonation: Some(p.intonation), pause: Some(p.pause),
    }).collect();
    let score = plan_phrases(&phrases, &PlanOptions {
        body: "male".into(), t0: 0.05, f0: Some(112.0), ..Default::default()
    });
    let mut voice = HumanVoice::new(48_000.0, BODY_MALE, 2);
    voice.set_source(&SourcePatch::f0(112.0));
    voice.schedule(&score.gestures);
    let mut samples = vec![0.0f32; js_round(48_000.0 * (score.end + 0.3)) as usize];
    if request.completed_frames > samples.len() {
        return Err("観測時刻が発話の範囲外です".into());
    }
    let (head, tail) = samples.split_at_mut(request.completed_frames);
    for block in head.chunks_mut(128) {
        voice.render(block);
    }
    fs::write(geometry, serde_json::to_vec(&snapshot(&voice, &request))?)?;
    for block in tail.chunks_mut(128) {
        voice.render(block);
    }
    let mut file = BufWriter::new(fs::File::create_new(pcm)?);
    for sample in samples {
        file.write_all(&sample.to_le_bytes())?;
    }
    file.flush()?;
    Ok(())
}
