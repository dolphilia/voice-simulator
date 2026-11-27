//! 英語計画に含まれる構造体を従来の辞書順で書く。

use serde::{Serialize, Serializer, ser::SerializeStruct};
use vocal_core::phonetics::{
    Segment,
    english::{PlannedPhrase, TextPlan},
    timing::{TimedSegment, Timing},
};

use super::OrderedGestures;

#[derive(Serialize)]
pub(in crate::planning) struct EnglishReport {
    pub(in crate::planning) base_pitch_hz: f64,
    pub(in crate::planning) initial_pitch_hz: f64,
    pub(in crate::planning) noise_scale: Option<f64>,
    #[serde(serialize_with = "serialize_plan")]
    pub(in crate::planning) speech: TextPlan,
}

fn serialize_plan<S: Serializer>(plan: &TextPlan, serializer: S) -> Result<S::Ok, S::Error> {
    let mut fields = serializer.serialize_struct("TextPlan", 5)?;
    fields.serialize_field("end_seconds", &plan.end_seconds)?;
    fields.serialize_field("phrases", &Ordered(plan.phrases.as_slice()))?;
    fields.serialize_field("render_end_seconds", &plan.render_end_seconds)?;
    fields.serialize_field("shown", &plan.shown)?;
    fields.serialize_field(
        "unavailable_speech_symbols",
        &plan.unavailable_speech_symbols,
    )?;
    fields.end()
}

struct Ordered<'a, T: ?Sized>(&'a T);

impl<'a, T> Serialize for Ordered<'a, [T]>
where
    Ordered<'a, T>: Serialize,
{
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        serializer.collect_seq(self.0.iter().map(Ordered))
    }
}

impl Serialize for Ordered<'_, PlannedPhrase> {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        let span = self.0;
        let phrase = &span.phrase;
        // コアの報告では `Phrase` が `PlannedPhrase` に平坦化される。
        let mut fields = serializer.serialize_struct("PlannedPhrase", 10)?;
        fields.serialize_field("end_seconds", &span.end_seconds)?;
        fields.serialize_field("intonation", &phrase.intonation)?;
        fields.serialize_field("pause", &phrase.pause)?;
        fields.serialize_field("pitch", &OrderedGestures::new(&span.pitch))?;
        fields.serialize_field("segments", &Ordered(phrase.segments.as_slice()))?;
        fields.serialize_field("shown", &span.shown)?;
        fields.serialize_field("sources", &phrase.sources)?;
        fields.serialize_field("start_seconds", &span.start_seconds)?;
        fields.serialize_field("timing", &Ordered(&span.timing))?;
        fields.serialize_field("words", &phrase.words)?;
        fields.end()
    }
}

impl Serialize for Ordered<'_, Timing> {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        let timing = self.0;
        let mut fields = serializer.serialize_struct("Timing", 3)?;
        fields.serialize_field("durations_seconds", &timing.durations_seconds)?;
        fields.serialize_field("end_seconds", &timing.end_seconds)?;
        fields.serialize_field("segments", &Ordered(timing.segments.as_slice()))?;
        fields.end()
    }
}

impl Serialize for Ordered<'_, TimedSegment> {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        let part = self.0;
        let mut fields = serializer.serialize_struct("TimedSegment", 6)?;
        fields.serialize_field("end_seconds", &part.end_seconds)?;
        fields.serialize_field("glide_from_previous", &part.glide_from_previous)?;
        fields.serialize_field("input_index", &part.input_index)?;
        fields.serialize_field("manner", &part.manner)?;
        fields.serialize_field("segment", &Ordered(&part.segment))?;
        fields.serialize_field("start_seconds", &part.start_seconds)?;
        fields.end()
    }
}

impl Serialize for Ordered<'_, Segment> {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        SegmentFields::serialize(self.0, serializer)
    }
}

#[derive(Serialize)]
#[serde(remote = "Segment", rename_all = "camelCase")]
struct SegmentFields {
    #[serde(skip_serializing_if = "Option::is_none")]
    aspirated: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    breathy: Option<bool>,
    #[serde(rename = "dur", skip_serializing_if = "Option::is_none")]
    duration_seconds: Option<f64>,
    #[serde(rename = "f0", skip_serializing_if = "Option::is_none")]
    f0_hz: Option<f64>,
    #[serde(rename = "glide", skip_serializing_if = "Option::is_none")]
    glide_seconds: Option<f64>,
    ipa: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    nasalized: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    palatalized: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    stress: Option<u8>,
    #[serde(rename = "vot", skip_serializing_if = "Option::is_none")]
    vot_seconds: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    word_end: Option<bool>,
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use vocal_core::phonetics::english::{self, English};

    #[test]
    fn direct_english_report_matches_value_with_flattened_phrases_and_optional_fields() {
        let dictionary = English::with_dictionary("wind\tW IH1 N D\nhello\tHH AH0 L OW1");
        let phrases = dictionary.phrases("Hello, wind? Zorblat.");
        let mut speech = english::plan_phrases(phrases, -0.0, 0.82, 167.5).unwrap();
        let first = &mut speech.phrases[0];
        let full = Segment {
            aspirated: Some(false),
            breathy: Some(true),
            duration_seconds: Some(0.32401500000000005),
            f0_hz: Some(123.5),
            glide_seconds: Some(-0.0),
            ipa: "ɪ\"階\n".into(),
            nasalized: Some(true),
            palatalized: Some(false),
            stress: Some(2),
            vot_seconds: Some(1e-10),
            word_end: Some(false),
        };
        first.phrase.segments.push(full.clone());
        first.timing.segments[0].segment = full;
        first.timing.segments[0].manner = None;
        speech.unavailable_speech_symbols.push("ʡ".into());
        let mut report = EnglishReport {
            base_pitch_hz: 167.5,
            initial_pitch_hz: 110.0,
            noise_scale: Some(0.75),
            speech,
        };
        for noise_scale in [Some(0.75), None] {
            report.noise_scale = noise_scale;
            let expected = json!({
                "base_pitch_hz": report.base_pitch_hz,
                "initial_pitch_hz": report.initial_pitch_hz,
                "noise_scale": noise_scale,
                "speech": &report.speech,
            });
            assert_eq!(
                serde_json::to_vec(&report).unwrap(),
                expected.to_string().as_bytes()
            );
        }
    }
}
