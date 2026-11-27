//! 読み取った音素の時間を配分し、調音計画へ渡す秒単位の区間を作る。

mod durations;

use super::{
    Manner, Segment,
    catalog::{self, TIMING},
};
use serde::Serialize;

pub(super) const BREATH_LEAD_SECONDS: f64 = 0.06;

#[derive(Debug, Serialize)]
pub struct Timing {
    /// 話速と二重母音の配分を適用する前の、入力音素ごとの長さ。
    pub durations_seconds: Vec<f64>,
    pub segments: Vec<TimedSegment>,
    pub end_seconds: f64,
    #[serde(skip)]
    pub(super) rate: f64,
}

#[derive(Debug, Serialize)]
pub struct TimedSegment {
    pub input_index: usize,
    /// 展開済みの音素と話速を適用する前の配分長。
    pub segment: Segment,
    pub manner: Option<Manner>,
    pub start_seconds: f64,
    pub end_seconds: f64,
    pub glide_from_previous: bool,
}

pub fn plan(input: &[Segment], start_seconds: f64, rate: f64) -> Result<Timing, &'static str> {
    if !start_seconds.is_finite() || !rate.is_finite() || rate <= 0.0 {
        return Err("開始時刻は有限値、話速は有限の正の値を指定してください");
    }
    if input.iter().any(|segment| {
        segment
            .duration_seconds
            .is_some_and(|seconds| !seconds.is_finite() || seconds < 0.0)
    }) {
        return Err("明示された音素長は有限の非負値を指定してください");
    }

    let durations_seconds = durations::estimate(input);
    let mut parts = Vec::<TimedSegment>::with_capacity(input.len());
    let mut t = start_seconds + BREATH_LEAD_SECONDS;
    for (input_index, (segment, &seconds)) in input.iter().zip(&durations_seconds).enumerate() {
        let expanded = expand(segment, seconds);
        for (part_index, part) in expanded.into_iter().enumerate() {
            let mut manner = if catalog::is_calibrated_vowel(&part.ipa) {
                Some(Manner::Vowel)
            } else {
                catalog::consonant(&part.ipa).map(|entry| entry.manner)
            };
            if part.ipa == "ð"
                && parts.last().is_none_or(|previous| {
                    previous.segment.ipa == "_"
                        || matches!(
                            previous.manner,
                            Some(Manner::Stop | Manner::Affricate | Manner::Fricative)
                        )
                })
            {
                manner = Some(Manner::Stop);
            }
            let start_seconds = t;
            t += part.duration_seconds.unwrap() / rate;
            if !t.is_finite() {
                return Err("音素区間が有限の時刻に収まりません");
            }
            parts.push(TimedSegment {
                input_index,
                segment: part,
                manner,
                start_seconds,
                end_seconds: t,
                glide_from_previous: part_index > 0,
            });
        }
    }
    Ok(Timing {
        durations_seconds,
        segments: parts,
        end_seconds: t,
        rate,
    })
}

fn expand(segment: &Segment, seconds: f64) -> Vec<Segment> {
    let Some(expansion) = TIMING.expansions.get(&segment.ipa) else {
        return vec![Segment {
            duration_seconds: Some(seconds),
            ..segment.clone()
        }];
    };
    let shares: &[f64] = match (expansion.parts.len(), expansion.rising) {
        (1, _) => &[1.0],
        (2, false) => &[0.55, 0.45],
        (2, true) => &[0.30, 0.70],
        (3, _) => &[0.25, 0.45, 0.30],
        _ => unreachable!("固定版の展開は3要素まで"),
    };
    expansion
        .parts
        .iter()
        .zip(shares)
        .map(|(ipa, share)| Segment {
            ipa: ipa.clone(),
            duration_seconds: Some(seconds * share),
            stress: segment.stress,
            f0_hz: segment.f0_hz,
            nasalized: segment.nasalized,
            breathy: segment.breathy,
            ..Segment::default()
        })
        .collect()
}
