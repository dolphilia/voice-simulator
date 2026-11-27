//! CHIMERA の較正表（Jameson Hodge、MIT）から発話用の部分目標を得る。

use crate::anatomy::{Articulation, BodyMix, BodyName};
use crate::articulators::Articulator::{self, *};
use crate::score::{ControlKey::Artic, Targets};
use serde::Deserialize;
use std::{collections::BTreeMap, sync::LazyLock};

type PresetVowels = BTreeMap<String, Targets>;

#[derive(Deserialize)]
struct CalibratedVowel {
    artic: BTreeMap<String, f64>,
}

const VOWEL_AXES: [(Articulator, &str); 9] = [
    (TongueBodyX, "tbX"),
    (TongueBodyY, "tbY"),
    (Jaw, "jaw"),
    (LipAperture, "lipAp"),
    (LipProtrusion, "lipProt"),
    (LipSpread, "lipWidth"),
    (TongueRoot, "root"),
    (Larynx, "larynx"),
    (TipCurl, "ttCurl"),
];

static VOWELS: LazyLock<[PresetVowels; 3]> = LazyLock::new(|| {
    let mut table: BTreeMap<String, BTreeMap<String, CalibratedVowel>> =
        serde_json::from_str(include_str!("vowel-targets.generated.json"))
            .expect("固定版の母音較正表");
    ["male", "female", "child"].map(|preset| {
        table
            .remove(preset)
            .expect("較正表の体型")
            .into_iter()
            .map(|(ipa, row)| {
                let mut targets = Targets::default();
                for (axis, name) in VOWEL_AXES {
                    if let Some(&value) = row.artic.get(name) {
                        targets.set(Artic(axis), value);
                    }
                }
                // 巻き舌と非巻き舌の舌尖母音では、舌先座標も母音の目標になる。
                if targets.get(Artic(TipCurl)).unwrap_or(0.0) > 0.05 || ipa == "ɿ" {
                    for (axis, name) in [(TongueTipX, "ttX"), (TongueTipY, "ttY")] {
                        if let Some(&value) = row.artic.get(name) {
                            targets.set(Artic(axis), value);
                        }
                    }
                }
                (ipa, targets)
            })
            .collect()
    })
});

pub(super) fn male_vowel_targets(ipa: &str) -> Option<&'static Targets> {
    VOWELS[0].get(ipa)
}

fn preset_targets(ipa: &str, body: BodyName) -> Option<&'static Targets> {
    let index = match body {
        BodyName::Male => 0,
        BodyName::Female => 1,
        BodyName::Child => 2,
    };
    VOWELS[index].get(ipa).or_else(|| male_vowel_targets(ipa))
}

/// 単母音の調音目標。各成分は、その値を持つ端点の間で補間する。
pub fn vowel_targets(ipa: &str, body: BodyMix) -> Option<Targets> {
    if let Some(preset) = body.preset() {
        return preset_targets(ipa, preset).copied();
    }
    let mut parts = [None; 3];
    for (part, (preset, weight)) in parts.iter_mut().zip(body.weights()) {
        if weight > 0.0 {
            *part = Some((weight, preset_targets(ipa, preset)?));
        }
    }
    let mut combined = Targets::default();
    for axis in Articulator::ALL {
        let key = Artic(axis);
        let mut weighted_sum = 0.0;
        let mut weight_sum = 0.0;
        for (weight, target) in parts.into_iter().flatten() {
            if let Some(value) = target.get(key) {
                weighted_sum += weight * value;
                weight_sum += weight;
            }
        }
        if weight_sum > 0.0 {
            combined.set(key, weighted_sum / weight_sum);
        }
    }
    Some(combined)
}

/// 固定姿勢の基準座標に、指定された母音の成分だけを上書きする。
pub fn fixed_vowel_posture(targets: &Targets) -> Articulation {
    const NEUTRAL: [f64; Articulator::ALL.len()] = [
        0.6, 2.9, 6.85, 6.45, 7.3, 0.0, 0.0, 0.7, 0.2, 0.5, 0.0, -0.15, 0.0, 0.0, 0.0, 0.0, 0.0,
    ];
    Articulation::from_axis_values(
        Articulator::ALL.map(|axis| targets.get(Artic(axis)).unwrap_or(NEUTRAL[axis.index()])),
    )
}
