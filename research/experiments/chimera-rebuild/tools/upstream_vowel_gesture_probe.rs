//! 固定上流が作った母音ジェスチャーと、調音器の制御更新を観測する。

use chimera::{
    anatomy::human::{ArticKey, ArticPatch, BodyMix, NEUTRAL},
    control::{
        articulators::ArticulatorBank,
        score::{Blended, ControlKey, Gesture, GestureScore, N_CONTROL, Targets, activation},
    },
    phonetics::{
        Segment, ipa,
        planner::{PlanOptions, plan_utterance, vowel_artic, vowel_table},
    },
};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    error::Error,
    io::{self, Write},
};

const ARTIC_NAMES: [&str; 17] = [
    "jaw_cm",
    "tongue_body_x_cm",
    "tongue_body_y_cm",
    "tongue_tip_x_cm",
    "tongue_tip_y_cm",
    "tip_curl",
    "tongue_root_cm",
    "lip_aperture_cm",
    "lip_protrusion_cm",
    "lip_spread",
    "labiodental",
    "velum_cm2",
    "larynx_cm",
    "epilarynx",
    "ventricular",
    "lateral",
    "dorsum",
];
const SOURCE_NAMES: [&str; 5] = [
    "abduction_cm2",
    "closure",
    "breath",
    "f0_hz",
    "vibrato_cents",
];

fn candidate_name(key: ControlKey) -> &'static str {
    match key {
        ControlKey::Artic(key) => ARTIC_NAMES[key.index()],
        ControlKey::Source(key) => SOURCE_NAMES[key as usize],
    }
}

fn targets_report(targets: &Targets) -> BTreeMap<&'static str, f64> {
    targets
        .iter()
        .map(|(key, value)| (candidate_name(key), value))
        .collect()
}

fn initial_bank(obs: &Value) -> ArticulatorBank {
    let pose = &obs["posture"];
    let mut initial = ArticPatch::default();
    for key in ArticKey::ALL {
        let value = match key {
            ArticKey::TbX => &pose["tongue_body_cm"][0],
            ArticKey::TbY => &pose["tongue_body_cm"][1],
            ArticKey::TtX => &pose["tongue_tip_cm"][0],
            ArticKey::TtY => &pose["tongue_tip_cm"][1],
            _ => &pose[candidate_name(key.into())],
        };
        initial.set(key, value.as_f64().unwrap_or(0.0));
    }
    let mut bank = ArticulatorBank::new();
    bank.tip_free = obs["tip_free"].as_bool().unwrap();
    bank.snap(&initial);
    bank
}

fn observe(case: &Value, keys: &BTreeMap<&str, ControlKey>) -> Result<Value, Box<dyn Error>> {
    let inputs = &case["speech_timing"];
    let obs = &inputs["observe_score"];
    let dt =
        obs["control_block_samples"].as_f64().unwrap() / obs["sample_rate_hz"].as_f64().unwrap();
    let frame_count = obs["frames"].as_u64().unwrap();
    let base_weight = obs["base_weight"].as_f64().unwrap();
    let observed = obs["keys"]
        .as_array()
        .unwrap()
        .iter()
        .map(|name| {
            let name = name.as_str().unwrap();
            (name, keys[name])
        })
        .collect::<Vec<_>>();
    let mut entries = Vec::new();
    for input in inputs["inputs"].as_array().unwrap() {
        let rate = input["rate"].as_f64().unwrap_or(1.0);
        let mut start = input["start_seconds"].as_f64().unwrap_or(0.05);
        let utterances = if let Some(text) = input["text"].as_str() {
            text.split('/')
                .map(str::trim)
                .filter(|part| !part.is_empty())
                .map(ipa::tokenize_ipa)
                .collect()
        } else {
            vec![serde_json::from_value::<Vec<Segment>>(
                input["segments"].clone(),
            )?]
        };

        let mut score = GestureScore::new();
        for source in utterances {
            let plan = plan_utterance(
                &source,
                &PlanOptions {
                    body: BodyMix::MALE,
                    t0: start,
                    rate: Some(rate),
                    f0: Some(110.0),
                    ..PlanOptions::default()
                },
            );
            let vowels = plan.segments.iter().filter(|row| row.kind == "vowel");
            // 上流では先頭から母音の形状ジェスチャーを一つずつ並べる。
            for (index, vowel) in vowels.enumerate() {
                let gesture = plan.gestures[index];
                assert_eq!(gesture.label_str(), vowel.ipa);
                assert_eq!(gesture.t0, vowel.t0);
                assert_eq!(gesture.t1, vowel.t1);
                score.add(gesture);
            }
            start = plan.end + 0.35;
        }
        for definition in input["additional_gestures"]
            .as_array()
            .into_iter()
            .flatten()
        {
            let mut data = definition.clone();
            let targets: BTreeMap<String, f64> = serde_json::from_value(data["targets"].clone())?;
            data["targets"] = json!(
                targets
                    .iter()
                    .map(|(name, value)| { (keys[name.as_str()].name(), value) })
                    .collect::<BTreeMap<_, _>>()
            );
            score.add(serde_json::from_value::<Gesture>(data)?);
        }

        let gestures = score
            .gestures()
            .iter()
            .map(|gesture| {
                let mut projected = serde_json::to_value(gesture)?;
                projected["targets"] = json!(targets_report(&gesture.targets));
                Ok::<_, serde_json::Error>(projected)
            })
            .collect::<Result<Vec<_>, _>>()?;

        let mut bank = initial_bank(obs);
        let mut frames = Vec::new();
        let mut blend = [Blended::default(); N_CONTROL];
        for index in 0..frame_count {
            let time = index as f64 * dt;
            score.blend_all(time, &mut blend);
            bank.step(dt, Some(&blend), base_weight);
            let mut blend_row = BTreeMap::new();
            let mut articulation = BTreeMap::new();
            for &(name, key) in &observed {
                let mixed = blend[key.index()];
                // 一成分だけを合成した場合と照合する。
                assert_eq!(mixed, score.blend(key, time));
                blend_row.insert(
                    name,
                    json!({
                        "value": mixed.value, "weight": mixed.weight, "speed": mixed.speed,
                    }),
                );
                if let ControlKey::Artic(key) = key {
                    let speed = bank.speed[key.index()]
                        * if mixed.weight > 0.0 { mixed.speed } else { 1.0 };
                    articulation.insert(
                        name,
                        json!({
                            "position": bank.x.get(key), "velocity": bank.v[key.index()],
                            "effective": bank.effective.get(key), "applied_speed": speed,
                        }),
                    );
                }
            }
            frames.push(json!({
                "time_seconds": time,
                "activation": score.gestures().iter().map(|g| activation(g, time)).collect::<Vec<_>>(),
                "blend": blend_row,
                "articulators": articulation,
            }));
        }
        entries.push(json!({"id": input["id"], "score": {"gestures": gestures, "frames": frames}}));
    }
    Ok(json!({"entries": entries}))
}

fn main() -> Result<(), Box<dyn Error>> {
    let keys = (0..N_CONTROL)
        .map(ControlKey::from_index)
        .map(|key| (candidate_name(key), key))
        .collect();
    let arg = std::env::args()
        .nth(1)
        .ok_or("観測するケースか目録を指定してください")?;
    let out = if arg == "--catalog" || arg == "--catalog-body" {
        let with_pose = arg == "--catalog-body";
        let body = if with_pose {
            let body = std::env::args()
                .nth(2)
                .ok_or("体型JSONを指定してください")?;
            serde_json::from_str::<BodyMix>(&body)?
        } else {
            BodyMix::MALE
        };
        let mut entries = BTreeMap::new();
        for symbol in vowel_table()["male"].keys() {
            let target = vowel_artic(symbol, body).ok_or("母音の目録に目標がありません")?;
            let values = target
                .iter()
                .map(|(key, value)| (candidate_name(key.into()), value))
                .collect::<BTreeMap<_, _>>();
            let value = if with_pose {
                json!({"targets": values, "posture": target.apply_to(&NEUTRAL)})
            } else {
                json!(values)
            };
            entries.insert(symbol, value);
        }
        json!(entries)
    } else {
        observe(&serde_json::from_slice(&std::fs::read(arg)?)?, &keys)?
    };
    let mut output = io::stdout().lock();
    serde_json::to_writer_pretty(&mut output, &out)?;
    writeln!(output)?;
    Ok(())
}
