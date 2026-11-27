//! ケースと任意のIPA入力を、同じ字句解析の入口へ渡す。

use crate::{network_case::Destination, write_json};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::HashSet;
use std::error::Error;
use std::fs::File;
use std::io::{self, BufWriter};
use vocal_core::phonetics::{
    Segment,
    ipa::{self, Analysis, SourceSpan},
};

#[derive(Deserialize)]
struct Case {
    id: String,
    upstream_revision: String,
    hypothesis: String,
    ipa: Inputs,
}

#[derive(Deserialize)]
struct Inputs {
    inputs: Vec<Example>,
}

#[derive(Deserialize)]
struct Example {
    id: String,
    text: String,
}

#[derive(Serialize)]
struct Report<'a> {
    #[serde(flatten)]
    analysis: Analysis,
    utterances: Vec<Utterance<'a>>,
}

#[derive(Serialize)]
struct Utterance<'a> {
    text: &'a str,
    span: SourceSpan,
    segments: Vec<Segment>,
    segment_spans: Vec<SourceSpan>,
}

impl<'a> Report<'a> {
    fn from_text(text: &'a str) -> Self {
        let analysis = ipa::analyze(text);
        let utterances = ipa::analyze_utterances(text)
            .map(|(span, parsed)| Utterance {
                text: &text[span.start_byte..span.end_byte],
                span,
                segments: parsed.segments,
                segment_spans: parsed.segment_spans,
            })
            .collect();
        Self {
            analysis,
            utterances,
        }
    }
}

#[derive(Serialize)]
struct Entry<'a> {
    id: &'a str,
    #[serde(flatten)]
    report: Report<'a>,
}

#[derive(Serialize)]
struct CaseReport<'a> {
    known_symbols: Vec<&'static str>,
    entries: Vec<Entry<'a>>,
}

pub(super) fn from_text(input: &str) -> Result<(), Box<dyn Error>> {
    write_json(io::stdout().lock(), &Report::from_text(input))
}

pub(super) fn run(input: Value, destination: Destination<'_>) -> Result<(), Box<dyn Error>> {
    let case = Case::deserialize(&input)?;
    let examples = &case.ipa.inputs;
    let unique: HashSet<_> = examples.iter().map(|example| &example.id).collect();
    if [&case.id, &case.upstream_revision, &case.hypothesis]
        .into_iter()
        .any(|value| value.is_empty())
        || examples.is_empty()
        || unique.len() != examples.len()
        || unique.iter().any(|id| id.is_empty())
    {
        return Err(
            "ケースのID、上流版、仮説と、重複しないIDを持つIPA入力を指定してください".into(),
        );
    }

    match destination {
        Destination::Inspect => write_json(
            io::stdout().lock(),
            &json!({
                "case": input,
                "input_count": examples.len(),
                "known_symbol_count": ipa::known_symbols().count(),
                "source_offsets": "utf8_bytes",
            }),
        ),
        Destination::Trace(path) => write_json(
            BufWriter::new(File::create_new(path)?),
            &CaseReport {
                known_symbols: ipa::known_symbols().collect(),
                entries: examples
                    .iter()
                    .map(|example| Entry {
                        id: &example.id,
                        report: Report::from_text(&example.text),
                    })
                    .collect(),
            },
        ),
        Destination::Pcm { .. } => {
            Err("IPA字句解析ケースは render でJSONへ出力してください".into())
        }
    }
}
