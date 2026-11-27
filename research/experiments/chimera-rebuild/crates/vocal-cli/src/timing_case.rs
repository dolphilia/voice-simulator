//! 発話計画を単独で実行し、IPAの入力位置と時間区間をJSONに保存する。

use crate::{network_case::Destination, write_json};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::HashSet;
use std::error::Error;
use std::fs::File;
use std::io::{self, BufWriter};
use vocal_core::{
    phonetics::{
        Segment,
        gestures::male_vowel_gestures,
        ipa_plan::{self, Utterance},
    },
    score::Gesture,
};

mod observed_score;
pub(crate) mod speech_voice;
use observed_score::{Observation, ObservedScore};

#[derive(Deserialize)]
struct Case {
    id: String,
    upstream_revision: String,
    hypothesis: String,
    speech_timing: Inputs,
}

#[derive(Deserialize)]
struct Inputs {
    inputs: Vec<Example>,
    observe_score: Option<Observation>,
}

#[derive(Deserialize)]
struct Example {
    id: String,
    rate: Option<f64>,
    start_seconds: Option<f64>,
    text: Option<String>,
    segments: Option<Vec<Segment>>,
    #[serde(default)]
    additional_gestures: Vec<Gesture>,
}

#[derive(Serialize)]
struct Entry<'a> {
    id: &'a str,
    rate: f64,
    utterances: Vec<Utterance<'a>>,
    render_end_seconds: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    score: Option<ObservedScore>,
}

#[derive(Serialize)]
struct CaseReport<'a> {
    entries: Vec<Entry<'a>>,
}

fn report<'a>(
    example: &'a Example,
    observation: Option<&Observation>,
) -> Result<Entry<'a>, Box<dyn Error>> {
    let rate = example.rate.unwrap_or(1.0);
    let ipa_plan::IpaTiming {
        utterances,
        render_end_seconds,
    } = ipa_plan::plan(
        example.text.as_deref(),
        example.segments.as_deref(),
        example.start_seconds,
        rate,
    )?;
    if observation.is_none() && !example.additional_gestures.is_empty() {
        return Err("追加ジェスチャーには observe_score を指定してください".into());
    }
    let score = observation
        .map(|observation| {
            let gestures = utterances
                .iter()
                .flat_map(|row| male_vowel_gestures(&row.timing))
                .chain(example.additional_gestures.iter().cloned())
                .collect();
            observation.observe(gestures)
        })
        .transpose()?;

    Ok(Entry {
        id: &example.id,
        rate,
        utterances,
        render_end_seconds,
        score,
    })
}

pub(super) fn from_text(text: &str, rate: f64) -> Result<(), Box<dyn Error>> {
    let example = Example {
        id: "ipa".to_owned(),
        rate: Some(rate),
        start_seconds: None,
        text: Some(text.to_owned()),
        segments: None,
        additional_gestures: Vec::new(),
    };
    write_json(io::stdout().lock(), &report(&example, None)?)
}

pub(super) fn run(input: Value, destination: Destination<'_>) -> Result<(), Box<dyn Error>> {
    let case = Case::deserialize(&input)?;
    let examples = &case.speech_timing.inputs;
    let unique: HashSet<_> = examples.iter().map(|example| &example.id).collect();
    if [&case.id, &case.upstream_revision, &case.hypothesis]
        .into_iter()
        .any(|value| value.is_empty())
        || examples.is_empty()
        || unique.len() != examples.len()
        || unique.iter().any(|id| id.is_empty())
    {
        return Err("ケースのID、上流版、仮説と、重複のない入力IDを指定してください".into());
    }
    let observation = case.speech_timing.observe_score.as_ref();
    let entries = examples
        .iter()
        .map(|example| report(example, observation))
        .collect::<Result<Vec<_>, _>>()?;
    match destination {
        Destination::Inspect => write_json(
            io::stdout().lock(),
            &json!({"case": input, "input_count": examples.len(), "time_unit": "seconds",
                    "source_offsets": "utf8_bytes"}),
        ),
        Destination::Trace(path) => write_json(
            BufWriter::new(File::create_new(path)?),
            &CaseReport { entries },
        ),
        Destination::Pcm { .. } => Err("発話区間は render でJSONへ出力してください".into()),
    }
}
