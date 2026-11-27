//! 固定上流のIPA入力処理と、そこで参照される表の公開部分を採取する。

use chimera::phonetics::{inventory, ipa, planner};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};
use std::error::Error;
use std::io;
use std::path::Path;

fn main() -> Result<(), Box<dyn Error>> {
    let input = std::env::args()
        .nth(1)
        .ok_or("IPA比較のケースパスが必要です")?;
    let known = ipa::known_ipa_symbols();
    let result = if input == "--catalog" {
        let consonants: BTreeMap<_, _> = inventory::consonants()
            .iter()
            .map(|entry| {
                (
                    entry.ipa,
                    json!({
                        "manner": entry.manner.as_str(),
                        "voiced": matches!(entry.voicing, inventory::Voicing::Voiced),
                    }),
                )
            })
            .collect();
        let calibrated: BTreeSet<_> = planner::vowel_table()
            .values()
            .flat_map(|table| table.keys())
            .collect();
        let expanded: Vec<_> = known
            .iter()
            .copied()
            .filter(|ipa| planner::expand(ipa).is_some())
            .collect();
        json!({"consonants": consonants, "calibrated_vowels": calibrated, "expanded_vowels": expanded})
    } else {
        report(Path::new(&input), &known)?
    };
    serde_json::to_writer_pretty(io::stdout().lock(), &result)?;
    println!();
    Ok(())
}

fn report(path: &Path, known: &[&str]) -> Result<Value, Box<dyn Error>> {
    let case: Value = serde_json::from_slice(&std::fs::read(path)?)?;
    let inputs = case["ipa"]["inputs"]
        .as_array()
        .ok_or("IPA入力の一覧が必要です")?;
    let mut entries = Vec::with_capacity(inputs.len());
    for input in inputs {
        let id = input["id"].as_str().ok_or("入力IDが必要です")?;
        let text = input["text"].as_str().ok_or("IPA文字列が必要です")?;
        let utterances: Vec<_> = text
            .split('/')
            .map(str::trim)
            .filter(|utterance| !utterance.is_empty())
            .map(|utterance| json!({"text": utterance, "segments": ipa::tokenize_ipa(utterance)}))
            .collect();
        entries.push(json!({
            "id": id,
            "segments": ipa::tokenize_ipa(text),
            "skipped": ipa::skipped_ipa(text),
            "utterances": utterances,
        }));
    }
    Ok(json!({"known_symbols": known, "entries": entries}))
}
