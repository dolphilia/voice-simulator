//! 固定版の辞書・語・句・区間とピッチ目標を公開APIから読み出す。

use chimera::{
    anatomy::human::BodyMix,
    phonetics::{
        Intonation, Plan,
        english::{EnglishG2P, arpabet_to_segments, letter_to_sound},
        planner::{PlanOptions, plan_utterance},
    },
};
use serde_json::{Value, json};
use std::{
    error::Error,
    io::{self, Write},
};

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let [config, dictionary] = args.as_slice() else {
        return Err("ケースと展開した辞書を指定してください".into());
    };
    let input: Value = serde_json::from_slice(&std::fs::read(config)?)?;
    let mut d = EnglishG2P::new();
    d.load_dict(&std::fs::read_to_string(dictionary)?);
    let fallback = EnglishG2P::new();
    let config = &input["english_text"];
    let mut entries = Vec::new();
    for row in config["inputs"].as_array().ok_or("入力配列が必要です")? {
        let dictionary = row["dictionary"].as_bool().unwrap_or(true);
        let g = if dictionary { &d } else { &fallback };
        let text = row["text"].as_str().ok_or("英語テキストが必要です")?;
        let mut start = 0.05;
        let mut end = start;
        let mut rows = Vec::new();
        for phrase in g.to_phrases(text) {
            let Plan {
                segments,
                gestures,
                end: until,
            } = plan_utterance(
                &phrase.segments,
                &PlanOptions {
                    body: BodyMix::MALE,
                    t0: start,
                    intonation: Some(phrase.intonation),
                    f0: Some(112.0),
                    ..PlanOptions::default()
                },
            );
            let pitch = gestures
                .into_iter()
                .filter(|g| g.label_str() == "pitch")
                .collect::<Vec<_>>();
            let mut shown = phrase
                .segments
                .iter()
                .map(|s| format!("{}{}", if s.stress == Some(1) { "ˈ" } else { "" }, s.ipa))
                .collect::<String>();
            if phrase.intonation == Intonation::Question {
                shown.push('?');
            }
            rows.push(json!({"phrase":phrase,"pitch":pitch,"segments":segments,
                             "start_seconds":start,"end_seconds":until,"shown":shown}));
            start = until + phrase.pause;
            end = until;
        }
        let shown = rows
            .iter()
            .map(|p| p["shown"].as_str().unwrap())
            .collect::<Vec<_>>()
            .join(" | ");
        entries.push(
            json!({"id":row["id"],"dictionary":dictionary,"phrases":rows,
                            "shown":shown,"end_seconds":end,"render_end_seconds":end+0.3}),
        );
    }
    let words = config["words"]
        .as_array()
        .into_iter()
        .flatten()
        .map(|value| {
            let word = value.as_str().unwrap();
            json!({"w":word,"dict":{"reduce":d.word(word,true),"full":d.word(word,false)},
               "noDict":{"reduce":fallback.word(word,true),"full":fallback.word(word,false)},
               "lts":letter_to_sound(word)})
        })
        .collect::<Vec<_>>();
    let arpabet = config["arpabet"]
        .as_array()
        .into_iter()
        .flatten()
        .map(|value| {
            let p = value.as_str().unwrap();
            json!({"p":p,"segments":arpabet_to_segments(p)})
        })
        .collect::<Vec<_>>();
    let mut output = io::stdout().lock();
    serde_json::to_writer_pretty(
        &mut output,
        &json!({"entries":entries,"words":words,"arpabet":arpabet}),
    )?;
    writeln!(output)?;
    Ok(())
}
