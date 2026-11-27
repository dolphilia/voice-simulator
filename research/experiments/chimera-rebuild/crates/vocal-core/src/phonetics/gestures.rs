//! 計画時刻から体型別の母音ジェスチャーを組み立てる。目標表はCHIMERAの較正値（MIT）。

use crate::anatomy::{BodyMix, BodyName};
use crate::score::Gesture;

use super::{Manner, timing::Timing, vowels::vowel_targets};

pub fn male_vowel_gestures(timing: &Timing) -> Vec<Gesture> {
    vowel_gestures(timing, BodyName::Male.into())
}

pub(super) fn vowel_gestures(timing: &Timing, body: BodyMix) -> Vec<Gesture> {
    let segments = &timing.segments;
    let mut vowels = segments
        .iter()
        .enumerate()
        .filter(|(_, s)| s.manner == Some(Manner::Vowel))
        .peekable();
    let mut previous_end = None;
    let mut gestures = Vec::new();
    while let Some((index, vowel)) = vowels.next() {
        let t0 = vowel.start_seconds;
        let t1 = vowel.end_seconds;
        let attack_gap = t0 - previous_end.unwrap_or(t0 - 0.08);
        let release_gap = vowels
            .peek()
            .map_or(t1 + 0.08, |(_, next)| next.start_seconds)
            - t1;
        let mut ramp_in = (0.75 * attack_gap).max(0.03) + 0.01;
        let mut ramp_out = (0.4 * release_gap).max(0.03) + 0.01;
        if let Some(glide) = vowel.segment.glide_seconds
            && index > 0
            && segments[index - 1].manner == Some(Manner::Vowel)
        {
            ramp_in = glide.max(0.01);
        }
        if let Some(next) = segments.get(index + 1)
            && next.manner == Some(Manner::Vowel)
            && next.segment.glide_seconds.is_some()
        {
            ramp_out = (next.end_seconds - next.start_seconds).max(0.01);
        }
        let label = &vowel.segment.ipa;
        let mut gesture = Gesture {
            t0,
            t1,
            ramp_in,
            ramp_out,
            strength: 1.0,
            targets: vowel_targets(label, body).expect("固定版の母音目標がありません"),
            speed: None,
            release_hold: None,
            label: Some(label.clone()),
        };
        gesture.shorten_for_rate(timing.rate);
        gestures.push(gesture);
        previous_end = Some(t1);
    }
    gestures
}
