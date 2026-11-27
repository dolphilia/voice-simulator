//! 英語の発音、句の時刻、抑揚を既存のケース入口から観察する。

use crate::{network_case::Destination, write_json};
use flate2::read::GzDecoder;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    error::Error,
    fs::File,
    io::{self, BufWriter, Read},
    sync::LazyLock,
};
use vocal_core::phonetics::english::{self, English, TextPlan};

const DICTIONARY: &[u8] = include_bytes!("../../../data/cmudict.txt.gz");
static DICTIONARY_TEXT: LazyLock<Result<String, io::Error>> = LazyLock::new(|| {
    let mut text = String::new();
    GzDecoder::new(DICTIONARY).read_to_string(&mut text)?;
    Ok(text)
});
static FIXED_LEXICON: LazyLock<Result<English<'static>, io::Error>> = LazyLock::new(|| {
    DICTIONARY_TEXT
        .as_ref()
        .map(|text| English::with_dictionary(text))
        .map_err(|e| io::Error::new(e.kind(), e.to_string()))
});

pub(crate) fn dictionary() -> Result<&'static English<'static>, io::Error> {
    FIXED_LEXICON
        .as_ref()
        .map_err(|e| io::Error::new(e.kind(), e.to_string()))
}

#[derive(Deserialize)]
struct Case {
    english_text: Inputs,
}

#[derive(Deserialize)]
struct Inputs {
    inputs: Vec<Example>,
    #[serde(default)]
    words: Vec<String>,
    #[serde(default)]
    arpabet: Vec<String>,
}

#[derive(Deserialize)]
struct Example {
    id: String,
    text: String,
    dictionary: Option<bool>,
}

#[derive(Serialize)]
struct Entry<'a> {
    id: &'a str,
    dictionary: bool,
    #[serde(flatten)]
    plan: TextPlan,
}

fn plan(
    input: &Example,
    fixed: &English<'_>,
    rules: &English<'_>,
) -> Result<TextPlan, &'static str> {
    let lexicon = if input.dictionary.unwrap_or(true) {
        fixed
    } else {
        rules
    };
    english::plan_phrases(
        lexicon.phrases(&input.text),
        english::START_SECONDS,
        1.0,
        english::MALE_F0_HZ,
    )
}

pub(super) fn from_text(text: &str) -> Result<(), Box<dyn Error>> {
    let plan = english::plan_phrases(
        dictionary()?.phrases(text),
        english::START_SECONDS,
        1.0,
        english::MALE_F0_HZ,
    )?;
    write_json(io::stdout().lock(), &plan)
}

pub(super) fn run(value: Value, destination: Destination<'_>) -> Result<(), Box<dyn Error>> {
    let data = Case::deserialize(&value)?.english_text;
    let fixed = dictionary()?;
    let rules = English::default();
    match destination {
        Destination::Inspect => write_json(
            io::stdout().lock(),
            &json!({
                "phrase_inputs": data.inputs.len(), "word_inputs": data.words.len(),
                "arpabet_inputs": data.arpabet.len(), "dictionary_entries": fixed.dictionary_entries(),
            }),
        ),
        Destination::Trace(path) => {
            let entries = data
                .inputs
                .iter()
                .map(|input| {
                    Ok::<Entry<'_>, &'static str>(Entry {
                        id: &input.id,
                        dictionary: input.dictionary.unwrap_or(true),
                        plan: plan(input, fixed, &rules)?,
                    })
                })
                .collect::<Result<Vec<_>, _>>()?;
            let words = data.words.iter().map(|word| json!({
                "word": word, "dict": {"reduce": fixed.pronounce(word,true), "full": fixed.pronounce(word,false)},
                "noDict": {"reduce": rules.pronounce(word,true), "full": rules.pronounce(word,false)},
                "lts": english::letter_to_sound(word),
            })).collect::<Vec<_>>();
            let arpabet = data
                .arpabet
                .iter()
                .map(|input| {
                    json!({
                        "p":input, "segments":english::arpabet(input),
                    })
                })
                .collect::<Vec<_>>();
            let data = json!({"entries":entries,"words":words,"arpabet":arpabet});
            write_json(BufWriter::new(File::create_new(path)?), &data)
        }
        Destination::Pcm { .. } => {
            Err("WAVの生成には speech_voice の英語ケースを指定してください".into())
        }
    }
}
