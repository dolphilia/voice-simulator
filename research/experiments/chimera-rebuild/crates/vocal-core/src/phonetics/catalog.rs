//! IPA字句解析と発話計画が参照する固定版目録。由来とライセンスは研究READMEに記録。

use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::sync::LazyLock;

use crate::anatomy::{BodyMix, BodyName};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Manner {
    Vowel,
    Stop,
    Nasal,
    Fricative,
    Affricate,
    Approximant,
    Lateral,
    Tap,
    Trill,
    Glottal,
}

#[derive(Deserialize)]
pub(super) struct Consonant {
    pub manner: Manner,
    pub voiced: bool,
}

#[derive(Deserialize)]
struct Catalog {
    consonants: BTreeMap<String, Consonant>,
    calibrated_vowels: BTreeSet<String>,
    expanded_vowels: BTreeSet<String>,
}

#[derive(Deserialize)]
pub(super) struct Expansion {
    pub parts: Vec<String>,
    pub rising: bool,
}

#[derive(Deserialize)]
pub(super) struct TimingCatalog {
    pub fallback_seconds: BTreeMap<String, f64>,
    pub expansions: BTreeMap<String, Expansion>,
    pub klatt_milliseconds: BTreeMap<String, [f64; 2]>,
}

static CATALOG: LazyLock<Catalog> = LazyLock::new(|| {
    serde_json::from_str(include_str!("ipa/catalog.generated.json")).expect("固定のIPA目録")
});
pub(super) static TIMING: LazyLock<TimingCatalog> = LazyLock::new(|| {
    serde_json::from_str(include_str!("timing.generated.json")).expect("固定の発話時刻目録")
});

#[derive(Deserialize)]
struct ConsonantCalibration {
    #[serde(rename = "ttY")]
    tip_height_cm: Option<f64>,
    #[serde(rename = "tbY")]
    body_height_cm: Option<f64>,
    #[serde(rename = "lipAp")]
    lip_aperture_cm: Option<f64>,
}

// 固定上流の子音較正表（Jameson Hodge、MIT）。
static CONSONANT_CALIBRATION: LazyLock<BTreeMap<String, BTreeMap<String, ConsonantCalibration>>> =
    LazyLock::new(|| {
        serde_json::from_str(include_str!("consonant-targets.generated.json"))
            .expect("固定の子音較正表")
    });

pub(super) fn calibrated_tip_height(ipa: &str, fallback: f64, body: BodyMix) -> f64 {
    calibrated_target(ipa, fallback, body, |target| target.tip_height_cm)
}

pub(super) fn calibrated_body_height(ipa: &str, fallback: f64, body: BodyMix) -> f64 {
    calibrated_target(ipa, fallback, body, |target| target.body_height_cm)
}

pub(super) fn calibrated_lip_aperture(ipa: &str, fallback: f64, body: BodyMix) -> f64 {
    calibrated_target(ipa, fallback, body, |target| target.lip_aperture_cm)
}

fn calibrated_target(
    ipa: &str,
    fallback: f64,
    body: BodyMix,
    select: impl Fn(&ConsonantCalibration) -> Option<f64>,
) -> f64 {
    let endpoint = |preset| {
        let name = match preset {
            BodyName::Male => "male",
            BodyName::Female => "female",
            BodyName::Child => "child",
        };
        CONSONANT_CALIBRATION
            .get(name)
            .and_then(|table| table.get(ipa))
            .and_then(&select)
            .unwrap_or(fallback)
    };
    if let Some(preset) = body.preset() {
        return endpoint(preset);
    }
    let weights = body.weights();
    let (sum, total) = weights
        .iter()
        .fold((0.0, 0.0), |(sum, total), &(preset, w)| {
            (sum + w * endpoint(preset), total + w)
        });
    sum / total
}

pub(super) fn consonant(ipa: &str) -> Option<&'static Consonant> {
    CATALOG.consonants.get(ipa)
}

pub(super) fn consonant_symbols() -> impl Iterator<Item = &'static str> {
    CATALOG.consonants.keys().map(String::as_str)
}

pub(super) fn is_calibrated_vowel(ipa: &str) -> bool {
    CATALOG.calibrated_vowels.contains(ipa)
}

pub(super) fn has_sound(ipa: &str) -> bool {
    consonant(ipa).is_some() || is_calibrated_vowel(ipa) || CATALOG.expanded_vowels.contains(ipa)
}
