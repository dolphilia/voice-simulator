//! 発音記号と発話計画の入口。PCMのサンプル処理とは独立して実行する。

use serde::{Deserialize, Serialize};

pub mod beatbox;
mod catalog;
pub mod english;
pub mod gestures;
pub mod ipa;
pub mod ipa_plan;
pub mod live_song;
mod korean;
pub mod mandarin;
mod russian;
pub mod song;
pub mod speech;
pub mod syllables;
pub mod timing;
pub mod vowels;

pub use catalog::Manner;

/// 字句解析が発話計画へ渡す音素。長さは明示指定された場合だけ秒で保持する。
#[derive(Clone, Debug, Default, PartialEq, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Segment {
    pub ipa: String,
    #[serde(rename = "dur", skip_serializing_if = "Option::is_none")]
    pub duration_seconds: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub stress: Option<u8>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub word_end: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub aspirated: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub nasalized: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub palatalized: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub breathy: Option<bool>,
    #[serde(rename = "f0", skip_serializing_if = "Option::is_none")]
    pub f0_hz: Option<f64>,
    #[serde(rename = "vot", skip_serializing_if = "Option::is_none")]
    pub vot_seconds: Option<f64>,
    #[serde(rename = "glide", skip_serializing_if = "Option::is_none")]
    pub glide_seconds: Option<f64>,
}

/// 句末のピッチの扱い。
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Intonation {
    #[default]
    Statement,
    Question,
    Flat,
}
