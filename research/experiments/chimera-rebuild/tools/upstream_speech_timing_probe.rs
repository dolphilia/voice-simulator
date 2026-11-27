//! 固定上流のKlatt長と発話計画の時刻だけを観測する。

use chimera::anatomy::human::BodyMix;
use chimera::phonetics::{
    Segment,
    durations::{SegInfo, klatt_durations},
    inventory, ipa, planner,
};
use serde_json::{Value, json};
use std::collections::BTreeMap;
use std::error::Error;
use std::io::{self, Write};

const CLI_PAUSE_SECONDS: f64 = 0.35;
const CLI_TAIL_SECONDS: f64 = 0.20;

fn main() -> Result<(), Box<dyn Error>> {
    let mut args = std::env::args().skip(1);
    let first = args.next().ok_or("時刻の比較ケースを指定してください")?;
    let result = if first == "--catalog" {
        let path = args.next().ok_or("長さ表と展開候補を指定してください")?;
        catalog(serde_json::from_slice(&std::fs::read(path)?)?)?
    } else {
        measure(serde_json::from_slice(&std::fs::read(first)?)?)?
    };
    let mut out = io::stdout().lock();
    serde_json::to_writer_pretty(&mut out, &result)?;
    writeln!(out)?;
    Ok(())
}

fn catalog(input: Value) -> Result<Value, Box<dyn Error>> {
    let candidates: Vec<String> = serde_json::from_value(input["expansion_candidates"].clone())?;
    let expansions = candidates
        .iter()
        .map(|symbol| {
            let parts = planner::expand(symbol).ok_or("展開候補が公開APIにありません")?;
            Ok((
                symbol,
                json!({"parts": parts, "rising": planner::is_rising(symbol)}),
            ))
        })
        .collect::<Result<BTreeMap<_, _>, Box<dyn Error>>>()?;
    let fallback_seconds = inventory::consonants()
        .iter()
        .map(|entry| (entry.ipa, entry.dur))
        .collect::<BTreeMap<_, _>>();
    Ok(json!({
        "fallback_seconds": fallback_seconds,
        "expansions": expansions,
        "klatt_milliseconds": input["klatt_milliseconds"],
    }))
}

fn measure(input: Value) -> Result<Value, Box<dyn Error>> {
    let examples = input["speech_timing"]["inputs"]
        .as_array()
        .ok_or("時刻の比較入力が必要です")?;
    let mut entries = Vec::with_capacity(examples.len());
    for example in examples {
        let mut next_start = example["start_seconds"].as_f64().unwrap_or(0.05);
        let rate = example["rate"].as_f64().unwrap_or(1.0);
        let input: Vec<(Option<&str>, Vec<Segment>)> = if let Some(text) = example["text"].as_str()
        {
            text.split('/')
                .map(str::trim)
                .filter(|text| !text.is_empty())
                .map(|text| (Some(text), ipa::tokenize_ipa(text)))
                .collect()
        } else {
            vec![(None, serde_json::from_value(example["segments"].clone())?)]
        };

        let mut utterances = Vec::with_capacity(input.len());
        for (text, source) in input {
            let durations = klatt_durations(&source, |s| {
                if planner::is_vowel(&s.ipa, BodyMix::MALE) {
                    return SegInfo {
                        vowel: true,
                        ..Default::default()
                    };
                }
                let d = inventory::phoneme(&s.ipa, BodyMix::MALE);
                SegInfo {
                    vowel: false,
                    manner: d.map(|definition| definition.manner),
                    voiced: Some(d.is_some_and(|definition| {
                        definition.voicing == inventory::Voicing::Voiced
                    })),
                    dur: d.map(|definition| definition.dur),
                }
            });
            let plan = planner::plan_utterance(
                &source,
                &planner::PlanOptions {
                    body: BodyMix::MALE,
                    t0: next_start,
                    rate: Some(rate),
                    f0: Some(110.0),
                    ..Default::default()
                },
            );
            utterances.push(json!({
                "text": text,
                "input_segments": source,
                "start_seconds": next_start,
                "end_seconds": plan.end,
                "durations_seconds": durations,
                "segments": plan.segments,
            }));
            next_start = plan.end + CLI_PAUSE_SECONDS;
        }
        entries.push(json!({
            "id": example["id"],
            "rate": rate,
            "utterances": utterances,
            "render_end_seconds": next_start + CLI_TAIL_SECONDS,
        }));
    }
    Ok(json!({"entries": entries}))
}
