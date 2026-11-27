//! IPAの入力位置、発話区間とレンダー長を計画する。
use serde::Serialize;

use super::{
    Segment,
    ipa::{self, Diagnostic, SourceSpan},
    timing::{self, Timing},
};

const DEFAULT_START_SECONDS: f64 = 0.05;
const UTTERANCE_PAUSE_SECONDS: f64 = 0.35;
const RENDER_TAIL_SECONDS: f64 = 0.20;

#[derive(Serialize)]
pub struct Utterance<'a> {
    text: Option<&'a str>,
    source_span: Option<SourceSpan>,
    input_segments: Vec<Segment>,
    input_spans: Vec<SourceSpan>,
    diagnostics: Vec<Diagnostic>,
    pub start_seconds: f64,
    #[serde(flatten)]
    pub timing: Timing,
}

#[derive(Serialize)]
pub struct IpaTiming<'a> {
    pub utterances: Vec<Utterance<'a>>,
    pub render_end_seconds: f64,
}

pub fn plan<'a>(
    text: Option<&'a str>,
    segments: Option<&[Segment]>,
    start: Option<f64>,
    rate: f64,
) -> Result<IpaTiming<'a>, &'static str> {
    let mut next_start = start.unwrap_or(DEFAULT_START_SECONDS);
    if !next_start.is_finite() || !rate.is_finite() || rate <= 0.0 {
        return Err("開始時刻は有限値、話速は有限の正の値を指定してください");
    }

    let mut utterances = Vec::new();
    let mut add = |text, source_span, input_segments: Vec<Segment>, input_spans, diagnostics| {
        let start_seconds = next_start;
        let timing = timing::plan(&input_segments, start_seconds, rate)?;
        next_start = timing.end_seconds + UTTERANCE_PAUSE_SECONDS;
        utterances.push(Utterance {
            text,
            source_span,
            input_segments,
            input_spans,
            diagnostics,
            start_seconds,
            timing,
        });
        Ok::<_, &'static str>(())
    };

    match (text, segments) {
        (Some(text), None) => {
            for (span, input) in ipa::analyze_utterances(text) {
                add(
                    Some(&text[span.start_byte..span.end_byte]),
                    Some(span),
                    input.segments,
                    input.segment_spans,
                    input.diagnostics,
                )?;
            }
        }
        (None, Some(segments)) => add(None, None, segments.to_vec(), Vec::new(), Vec::new())?,
        _ => return Err("IPA文字列か構造化音素列の一方を指定してください"),
    }

    Ok(IpaTiming {
        utterances,
        render_end_seconds: next_start + RENDER_TAIL_SECONDS,
    })
}
