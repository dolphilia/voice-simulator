//! 体型別の母音と対応する子音から、調音・開大・呼気・ピッチのスコアを作る。

use crate::anatomy::{BodyMix, BodyName};
use crate::articulators::Articulator;
use crate::score::{ControlKey, Gesture, Targets};

use super::{
    Intonation, Manner, catalog,
    gestures::vowel_gestures,
    timing::{TimedSegment, Timing},
    vowels::vowel_targets,
};

const DEFAULT_VOT_SECONDS: f64 = 0.05;
pub(super) const ALVEOLAR_TIP_X_CM: f64 = 6.25;
pub(super) const ALVEOLAR_TIP_Y_CM: f64 = 9.68;
pub(super) const BILABIAL_CLOSURE_CM: f64 = -0.25;
pub(super) const VELAR_CLOSURE_Y_CM: f64 = 8.35;

pub fn male_speech_gestures(
    timing: &Timing,
    start: f64,
    f0: f64,
) -> Result<Vec<Gesture>, &'static str> {
    male_speech_gestures_with_intonation(timing, start, f0, Intonation::Statement)
}

pub fn male_speech_gestures_with_intonation(
    timing: &Timing,
    start: f64,
    f0: f64,
    intonation: Intonation,
) -> Result<Vec<Gesture>, &'static str> {
    speech_gestures_with_intonation(timing, start, f0, intonation, BodyName::Male.into())
}

pub fn speech_gestures(
    timing: &Timing,
    start: f64,
    f0: f64,
    body: BodyMix,
) -> Result<Vec<Gesture>, &'static str> {
    speech_gestures_with_intonation(timing, start, f0, Intonation::Statement, body)
}

pub(super) fn speech_gestures_with_intonation(
    timing: &Timing,
    start: f64,
    f0: f64,
    intonation: Intonation,
    body: BodyMix,
) -> Result<Vec<Gesture>, &'static str> {
    let mut gestures = segment_gestures(timing, body)?;
    append_breath_and_release(timing, start, false, &mut gestures);
    append_pitch(
        &timing.segments,
        start,
        timing.end_seconds,
        f0,
        intonation,
        &mut gestures,
    );
    Ok(gestures)
}

pub(super) fn sung_phrase_gestures(
    timing: &Timing,
    start: f64,
    body: BodyMix,
) -> Result<Vec<Gesture>, &'static str> {
    let mut gestures = segment_gestures(timing, body)?;
    append_breath_and_release(timing, start, true, &mut gestures);
    Ok(gestures)
}

pub(super) fn segment_gestures(
    timing: &Timing,
    body: BodyMix,
) -> Result<Vec<Gesture>, &'static str> {
    let mut gestures = vowel_gestures(timing, body);
    let vowel_count = gestures.len();
    let parts = &timing.segments;
    for (i, part) in parts.iter().enumerate() {
        let t0 = part.start_seconds;
        let t1 = part.end_seconds;
        let next = parts.get(i + 1);
        if part.manner == Some(Manner::Vowel) && !part.glide_from_previous {
            let end = parts[i + 1..]
                .iter()
                .take_while(|p| p.glide_from_previous)
                .last()
                .map_or(t1, |p| p.end_seconds);
            if part.segment.nasalized == Some(true) {
                gestures.push(single(
                    "velum",
                    (t0, end),
                    (0.04, 0.04),
                    4.0,
                    Artic(Articulator::Velum),
                    0.3,
                ));
            }
            if part.segment.breathy == Some(true) {
                gestures.push(single(
                    "breathy",
                    (t0, end),
                    (0.03, 0.03),
                    5.0,
                    ControlKey::Abduction,
                    0.1,
                ));
            }
        }
        match part.segment.ipa.as_str() {
            "p" | "b" | "t" | "d" | "k" | "g" | "m" | "n" | "ŋ" => {
                closure_gestures(part, &parts[..i], next, timing.rate, body, &mut gestures);
            }
            "ts" | "tɕ" | "dʑ" | "tʃ" | "dʒ" | "tʂ" => {
                affricate_gestures(
                    part,
                    i.checked_sub(1).map(|j| &parts[j]),
                    next,
                    timing.rate,
                    body,
                    &mut gestures,
                );
            }
            "s" | "z" | "ʃ" | "ɕ" | "ʑ" | "ʂ" | "f" | "v" | "θ" | "x" => {
                fricative_gestures(part, body, &mut gestures)
            }
            "ð" => dental_gestures(part, &parts[..i], next, body, &mut gestures),
            "w" => gestures.push(labial_velar_gesture(t0, t1)),
            "j" | "ɰ" => tongue_glide_gestures(part.segment.ipa.as_str(), t0, t1, &mut gestures),
            "ɾ" => alveolar_tap_gestures(part, &mut gestures),
            "ɹ" => english_rhotic_gestures(part, &mut gestures),
            "ɻ" => retroflex_approximant_gestures(part, &mut gestures),
            "l" | "ɫ" => lateral_gestures(part, &mut gestures),
            "h" => gestures.push(single(
                "h",
                (t0 - 0.01, t1 - 0.01),
                (0.03, 0.035),
                5.0,
                ControlKey::Abduction,
                0.33,
            )),
            "ɦ" => gestures.push(single(
                "ɦ",
                (t0, t1),
                (0.03, 0.03),
                5.0,
                ControlKey::Abduction,
                0.10,
            )),
            "ʔ" => gestures.push(single(
                "ʔ",
                (t0, t1),
                (0.012, 0.015),
                8.0,
                ControlKey::Closure,
                1.0,
            )),
            _ if part.manner.is_none() || is_vowel(part) => {}
            _ => {
                return Err(
                    "この発話レンダーでは、母音・休止・子音 /p b t d k g m n ŋ s z ʃ ɕ ʑ ʂ f v θ ð x ts tɕ dʑ tʃ dʒ tʂ h ɦ ʔ w j ɰ ɾ ɹ ɻ l ɫ/ を指定してください",
                );
            }
        }
    }

    for gesture in &mut gestures[vowel_count..] {
        gesture.shorten_for_rate(timing.rate);
    }
    Ok(gestures)
}

fn is_sonorant_consonant(part: &TimedSegment) -> bool {
    matches!(
        part.manner,
        Some(Manner::Nasal | Manner::Approximant | Manner::Lateral | Manner::Tap | Manner::Trill)
    )
}

pub(super) fn append_breath_and_release(
    timing: &Timing,
    start: f64,
    sung: bool,
    gestures: &mut Vec<Gesture>,
) {
    const RELEASE_LEAD: f64 = 0.06;
    const RELEASE_RAMP: f64 = 0.15;
    let end = timing.end_seconds;
    let parts = &timing.segments;
    let sonorant = parts
        .last()
        .is_some_and(|p| is_vowel(p) || is_sonorant_consonant(p));
    let gradual =
        sung && sonorant && final_voiced_span(parts, end) >= 2.0 * (RELEASE_RAMP - RELEASE_LEAD);
    let (breath_end, opening_offset, opening_ramp, strength) = if gradual {
        (end + 0.015, RELEASE_LEAD, RELEASE_RAMP, 2.0)
    } else {
        (end, if sonorant { 0.045 } else { 0.015 }, 0.03, 6.0)
    };
    gestures.push(single(
        "breath",
        (start + if sung { 0.06 } else { 0.04 }, breath_end),
        (0.04, 0.05),
        1.0,
        ControlKey::Breath,
        1.0,
    ));
    let mut exhale = single(
        "exhale",
        (end + opening_offset, end + 0.1),
        (opening_ramp, 0.06),
        strength,
        ControlKey::Abduction,
        0.22,
    );
    exhale.shorten_for_rate(timing.rate);
    gestures.push(exhale);
}

fn final_voiced_span(parts: &[TimedSegment], end: f64) -> f64 {
    let mut preceding = parts.iter().rev().peekable();
    let mut start = end;
    while preceding.peek().is_some_and(|p| is_sonorant_consonant(p)) {
        start = preceding.next().expect("末尾の共鳴音").start_seconds;
    }
    if let Some(vowel) = preceding.peek().filter(|p| is_vowel(p)) {
        let hz = vowel.segment.f0_hz;
        while preceding
            .peek()
            .is_some_and(|p| is_vowel(p) && p.segment.f0_hz == hz)
        {
            start = preceding.next().expect("同じ音高の末尾母音").start_seconds;
        }
    }
    end - start
}

use ControlKey::Artic;

/// 発話の調音スコアを生成できる音素と休止。
pub fn supported_speech_symbol(part: &TimedSegment) -> bool {
    is_vowel(part)
        || matches!(
            part.segment.ipa.as_str(),
            "_" | "p"
                | "b"
                | "t"
                | "d"
                | "k"
                | "g"
                | "m"
                | "n"
                | "ŋ"
                | "s"
                | "z"
                | "ʃ"
                | "ɕ"
                | "ʑ"
                | "ʂ"
                | "f"
                | "v"
                | "θ"
                | "ð"
                | "x"
                | "ts"
                | "tɕ"
                | "dʑ"
                | "tʃ"
                | "dʒ"
                | "tʂ"
                | "h"
                | "ɦ"
                | "ʔ"
                | "w"
                | "j"
                | "ɰ"
                | "ɾ"
                | "ɹ"
                | "ɻ"
                | "l"
                | "ɫ"
        )
}

fn is_vowel(part: &TimedSegment) -> bool {
    part.manner == Some(Manner::Vowel)
}

fn closure_gestures(
    part: &TimedSegment,
    prior: &[TimedSegment],
    next: Option<&TimedSegment>,
    rate: f64,
    body: BodyMix,
    gestures: &mut Vec<Gesture>,
) {
    let t0 = part.start_seconds;
    let t1 = part.end_seconds;
    let duration = t1 - t0;
    let ipa = part.segment.ipa.as_str();
    let previous = prior.last();
    let nasal = part.manner == Some(Manner::Nasal);
    let on_tip = matches!(ipa, "t" | "d" | "n");
    let on_dorsum = matches!(ipa, "k" | "g" | "ŋ");
    let delay: f64 = if nasal {
        match ipa {
            "n" => 0.015,
            "ŋ" => 0.02,
            _ => 0.01,
        }
    } else {
        match previous {
            Some(part) if is_vowel(part) => {
                if on_tip {
                    0.019
                } else if on_dorsum {
                    0.015
                } else {
                    0.005
                }
            }
            Some(part) if matches!(part.segment.ipa.as_str(), "s" | "z" | "ʃ" | "ʒ") => {
                if on_tip { 0.03 } else { 0.02 }
            }
            Some(part)
                if on_tip
                    && part.manner == Some(Manner::Stop)
                    && matches!(part.segment.ipa.as_str(), "b" | "p" | "ð")
                    && prior
                        .len()
                        .checked_sub(2)
                        .is_some_and(|index| raises_tip_for_closure(&prior[index], body)) =>
            {
                0.025
            }
            Some(part)
                if on_dorsum
                    && part.manner == Some(Manner::Stop)
                    && matches!(part.segment.ipa.as_str(), "b" | "p" | "ð" | "t" | "d")
                    && prior
                        .len()
                        .checked_sub(2)
                        .is_some_and(|index| raises_dorsum_for_closure(&prior[index], body)) =>
            {
                0.025
            }
            _ => 0.0,
        }
    };
    let aim = t0 + delay.min((duration - 0.03).max(0.0));
    if on_dorsum {
        velar_closure_gestures(ipa, aim, t1, gestures);
    } else {
        gestures.push(closure_gesture(ipa, aim, t1, on_tip));
        if on_tip {
            gestures.push(alveolar_body_gesture(ipa, aim, t1));
        }
    }
    let mut voiced_again = t1;

    if nasal {
        let before_voiced_stop = next.is_some_and(|part| {
            part.manner == Some(Manner::Stop)
                && catalog::consonant(&part.segment.ipa).is_some_and(|definition| definition.voiced)
        });
        let seal = t1 - if before_voiced_stop { 0.005 } else { 0.02 };
        gestures.push(single(
            "velum",
            (t0 - 0.02, seal),
            (0.05, 0.03),
            4.0,
            Artic(Articulator::Velum),
            0.45,
        ));
    } else if matches!(ipa, "p" | "t" | "k") {
        let aspiration = stop_aspiration(part, previous, next, rate);
        // 口蓋化の終端は、話速によるランプの後処理前の開大から決まる。
        voiced_again = aspiration.speed_end();
        gestures.push(aspiration);
    } else if part.segment.breathy == Some(true) {
        gestures.push(breathy_release(t1, next));
    }
    if part.segment.palatalized == Some(true) {
        gestures.push(palatalized_gesture(t0, voiced_again, !on_dorsum));
    }
}

fn stop_aspiration(
    part: &TimedSegment,
    previous: Option<&TimedSegment>,
    next: Option<&TimedSegment>,
    rate: f64,
) -> Gesture {
    let t0 = part.start_seconds;
    let t1 = part.end_seconds;
    let aspirated = part.segment.aspirated.unwrap_or_else(|| {
        next.is_some_and(is_vowel) && previous.is_none_or(|p| p.segment.ipa != "s")
    });
    let (opening, past, release) = if aspirated {
        let past = match part.segment.vot_seconds {
            Some(vot) => (0.4 * DEFAULT_VOT_SECONDS + vot - DEFAULT_VOT_SECONDS).max(0.0) / rate,
            None => DEFAULT_VOT_SECONDS / rate * 0.4,
        };
        (0.36, past, 0.045)
    } else {
        (0.22, 0.012 * 0.4, 0.02)
    };
    single(
        "aspiration",
        (t0 + 0.25 * (t1 - t0), t1 + past),
        (0.035, release),
        6.0,
        ControlKey::Abduction,
        opening,
    )
}

fn breathy_release(end: f64, next: Option<&TimedSegment>) -> Gesture {
    let until = next.map_or(end + 0.08, |p| (end + 0.08).min(p.end_seconds));
    single(
        "breathy",
        (end - 0.02, until),
        (0.03, 0.03),
        5.0,
        ControlKey::Abduction,
        0.1,
    )
}

fn affricate_gestures(
    part: &TimedSegment,
    previous: Option<&TimedSegment>,
    next: Option<&TimedSegment>,
    rate: f64,
    body: BodyMix,
    gestures: &mut Vec<Gesture>,
) {
    let ipa = part.segment.ipa.as_str();
    let t0 = part.start_seconds;
    let t1 = part.end_seconds;
    let duration = t1 - t0;
    let split = t0 + 0.45 * duration;
    let voiceless = !matches!(ipa, "dʑ" | "dʒ");
    let alveolar = ipa == "ts";
    // 閉鎖と解放の調音目標は固定版CHIMERA由来（Jameson Hodge、MIT）。
    let closure: &[(Articulator, f64)] = match ipa {
        "ts" => &[
            (Articulator::TongueTipX, ALVEOLAR_TIP_X_CM),
            (Articulator::TongueTipY, ALVEOLAR_TIP_Y_CM),
        ],
        "tʂ" => &[
            (Articulator::TongueTipX, 5.45),
            (Articulator::TongueTipY, 10.05),
            (Articulator::TipCurl, 0.95),
        ],
        "tʃ" | "dʒ" => &[
            (Articulator::TongueTipX, 5.75),
            (Articulator::TongueTipY, 10.0),
            (Articulator::LipProtrusion, 0.75),
            (Articulator::LipSpread, 0.2),
        ],
        _ => &[
            (Articulator::TongueTipX, 5.85),
            (Articulator::TongueTipY, 10.0),
            (Articulator::TongueBodyX, 3.6),
            (Articulator::TongueBodyY, 8.1),
            (Articulator::LipProtrusion, 0.0),
            (Articulator::LipSpread, 0.7),
        ],
    };
    gestures.push(dominant_oral_gesture(
        ipa,
        (t0 - 0.031, (t0 + 0.01).max(split - 0.02)),
        2.0,
        closure,
    ));
    let release_start = (split - 0.015).max(t0);
    let release_time = (release_start - 0.008, t1.max(release_start + 0.010));
    if alveolar {
        gestures.push(alveolar_body_gesture(ipa, t0, split));
        gestures.push(dominant_oral_gesture(
            ipa,
            release_time,
            1.4,
            &sibilant_targets(true, body),
        ));
        gestures.push(alveolar_body_gesture(ipa, release_start, t1));
    } else if ipa == "tʂ" {
        gestures.push(dominant_oral_gesture(
            ipa,
            release_time,
            1.4,
            &retroflex_frication_targets(body),
        ));
    } else if matches!(ipa, "tʃ" | "dʒ") {
        let release_ipa = if voiceless { "ʃ" } else { "ʒ" };
        gestures.push(dominant_oral_gesture(
            ipa,
            release_time,
            1.4,
            &postalveolar_frication_targets(release_ipa, body),
        ));
    } else {
        let release_ipa = if voiceless { "ɕ" } else { "ʑ" };
        gestures.push(alveolopalatal_frication(
            ipa,
            release_ipa,
            release_start,
            t1,
            1.4,
            body,
        ));
    }

    let folds =
        if voiceless && (part.segment.aspirated.is_some() || part.segment.vot_seconds.is_some()) {
            stop_aspiration(part, previous, next, rate)
        } else {
            let (onset, label) = if voiceless {
                (t0 + 0.15 * duration, "aspiration")
            } else {
                (split, "voiced affricate")
            };
            let hold = (t1 - 0.03).max(onset);
            single(
                label,
                (onset, hold),
                (0.035, (t1 - onset).min(0.03)),
                6.0,
                ControlKey::Abduction,
                0.36,
            )
        };
    let voiced_again = folds.t1 + folds.ramp_out;
    gestures.push(folds);
    if !voiceless && part.segment.breathy == Some(true) {
        gestures.push(breathy_release(t1, next));
    }
    if matches!(ipa, "ts" | "tʃ" | "dʒ" | "tʂ") && part.segment.palatalized == Some(true) {
        gestures.push(palatalized_gesture(t0, voiced_again, true));
    }
}

/// 舌背Yで閉じ、顎と舌背Xは別の強さで母音に重ねる。係数は固定版CHIMERA（MIT）。
fn velar_closure_gestures(ipa: &str, aim: f64, end: f64, gestures: &mut Vec<Gesture>) {
    let mut height = single(
        ipa,
        (aim - 0.024, (aim + 0.010).max(end - 0.034)),
        (0.03, 0.03),
        40.0,
        Artic(Articulator::TongueBodyY),
        VELAR_CLOSURE_Y_CM,
    );
    height.speed = Some(1.0 + (1.55 - 1.0) * 0.35);
    height.release_hold = Some(0.045);
    gestures.push(height);
    gestures.push(single(
        ipa,
        (aim, end),
        (0.05, 0.05),
        2.2,
        Artic(Articulator::Jaw),
        0.7,
    ));
    gestures.push(single(
        ipa,
        (aim, end),
        (0.05, 0.05),
        0.25,
        Artic(Articulator::TongueBodyX),
        2.3,
    ));
}

/// 両唇または舌先の移動時間を見込んだ閉鎖。発話とビートボックスで使う。
pub(super) fn closure_gesture(label: &str, start: f64, end: f64, on_tip: bool) -> Gesture {
    let (lead, early, primary, target) = if on_tip {
        (0.02, 0.031, Articulator::TongueTipX, ALVEOLAR_TIP_X_CM)
    } else {
        (0.019, 0.022, Articulator::LipAperture, BILABIAL_CLOSURE_CM)
    };
    let mut closure = single(
        label,
        (start - early, (start + 0.01).max(end - lead)),
        (0.03, 0.018),
        40.0,
        Artic(primary),
        target,
    );
    closure.speed = Some(1.55);
    closure.release_hold = Some(0.045);
    if on_tip {
        closure
            .targets
            .set(Artic(Articulator::TongueTipY), ALVEOLAR_TIP_Y_CM);
    }
    closure
}

fn raises_tip_for_closure(part: &TimedSegment, body: BodyMix) -> bool {
    matches!(
        part.segment.ipa.as_str(),
        "d" | "t"
            | "n"
            | "s"
            | "z"
            | "ʃ"
            | "θ"
            | "ð"
            | "ɕ"
            | "ʑ"
            | "ʂ"
            | "ts"
            | "tɕ"
            | "dʑ"
            | "tʃ"
            | "dʒ"
            | "tʂ"
            | "ɾ"
            | "ɹ"
            | "ɻ"
            | "l"
            | "ɫ"
    ) || (is_vowel(part)
        && vowel_targets(&part.segment.ipa, body).is_some_and(|vowel| {
            vowel
                .get(Artic(Articulator::TipCurl))
                .is_some_and(|curl| curl > 0.05)
                && vowel.get(Artic(Articulator::TongueTipX)).is_some()
                && vowel.get(Artic(Articulator::TongueTipY)).is_some()
        }))
}

fn raises_dorsum_for_closure(part: &TimedSegment, body: BodyMix) -> bool {
    matches!(
        part.segment.ipa.as_str(),
        "w" | "j" | "ɰ" | "ɹ" | "ɫ" | "k" | "g" | "ŋ" | "ɕ" | "ʑ" | "tɕ" | "dʑ" | "x"
    ) || (is_vowel(part)
        && vowel_targets(&part.segment.ipa, body).is_some_and(|vowel| {
            vowel
                .get(Artic(Articulator::TipCurl))
                .is_some_and(|curl| curl > 0.05)
                && vowel.get(Artic(Articulator::TongueBodyY)).is_some()
        }))
}

pub(super) fn nonclosing_oral_gesture(
    ipa: &str,
    start: f64,
    end: f64,
    axes: &[(Articulator, f64)],
) -> Gesture {
    dominant_oral_gesture(ipa, (start - 0.008, end.max(start + 0.010)), 1.3, axes)
}

fn dominant_oral_gesture(
    label: &str,
    (t0, t1): (f64, f64),
    speed: f64,
    axes: &[(Articulator, f64)],
) -> Gesture {
    let mut targets = Targets::default();
    for &(axis, target) in axes {
        targets.set(Artic(axis), target);
    }
    Gesture {
        t0,
        t1,
        ramp_in: 0.030,
        ramp_out: 0.018,
        strength: 40.0,
        targets,
        speed: Some(speed),
        release_hold: Some(0.045),
        label: Some(label.to_owned()),
    }
}

fn labial_velar_gesture(start: f64, end: f64) -> Gesture {
    nonclosing_oral_gesture(
        "w",
        start,
        end,
        &[
            (Articulator::LipAperture, 0.28),
            (Articulator::LipProtrusion, 1.0),
            (Articulator::LipSpread, 0.05),
            (Articulator::TongueBodyX, 2.45),
            (Articulator::TongueBodyY, 7.45),
        ],
    )
}

/// 舌背だけを支配軸とする接近音。目標と速度は固定版CHIMERA（MIT）に合わせる。
fn tongue_glide_gestures(ipa: &str, start: f64, end: f64, gestures: &mut Vec<Gesture>) {
    let palatal = ipa == "j";
    let (x, y) = if palatal { (3.8, 7.95) } else { (2.35, 7.45) };
    let mut tongue = nonclosing_oral_gesture(
        ipa,
        start,
        end,
        &[(Articulator::TongueBodyX, x), (Articulator::TongueBodyY, y)],
    );
    // 舌背は支配軸が唇や舌先の場合より解放が遅い。
    tongue.ramp_out = 0.030;
    tongue.speed = Some(1.0 + (1.3 - 1.0) * 0.35);
    gestures.push(tongue);
    if palatal {
        gestures.push(single(
            ipa,
            (start, end),
            (0.05, 0.05),
            2.2,
            Artic(Articulator::Jaw),
            0.25,
        ));
    }
}

fn alveolar_tap_gestures(part: &TimedSegment, gestures: &mut Vec<Gesture>) {
    let start = part.start_seconds;
    let end = part.end_seconds;
    gestures.push(dominant_oral_gesture(
        "ɾ",
        (start - 0.008, end.max(start + 0.010)),
        2.8,
        &[
            (Articulator::TongueTipX, ALVEOLAR_TIP_X_CM),
            (Articulator::TongueTipY, ALVEOLAR_TIP_Y_CM),
        ],
    ));
    gestures.push(alveolar_body_gesture("ɾ", start, end));
    if part.segment.palatalized == Some(true) {
        gestures.push(palatalized_gesture(start, end, true));
    }
}

fn english_rhotic_gestures(part: &TimedSegment, gestures: &mut Vec<Gesture>) {
    let start = part.start_seconds;
    let end = part.end_seconds;
    // 固定版CHIMERA（Jameson Hodge、MIT）の支配軸と補助軸を別々に動かす。
    gestures.push(nonclosing_oral_gesture(
        "ɹ",
        start,
        end,
        &[
            (Articulator::TongueTipX, 5.35),
            (Articulator::TongueTipY, 9.35),
            (Articulator::TipCurl, 0.85),
            (Articulator::LipProtrusion, 0.5),
            (Articulator::LipSpread, 0.3),
            (Articulator::TongueRoot, -0.6),
        ],
    ));
    let mut tongue_body = single(
        "ɹ",
        (start, end),
        (0.05, 0.05),
        2.2,
        Artic(Articulator::TongueBodyX),
        2.3,
    );
    tongue_body
        .targets
        .set(Artic(Articulator::TongueBodyY), 7.1);
    gestures.push(tongue_body);
    if part.segment.palatalized == Some(true) {
        gestures.push(palatalized_gesture(start, end, true));
    }
}

fn retroflex_approximant_gestures(part: &TimedSegment, gestures: &mut Vec<Gesture>) {
    let start = part.start_seconds;
    let end = part.end_seconds;
    // 舌先の座標と反りは固定版CHIMERA由来（Jameson Hodge、MIT）。
    gestures.push(nonclosing_oral_gesture(
        "ɻ",
        start,
        end,
        &[
            (Articulator::TongueTipX, 5.4),
            (Articulator::TongueTipY, 9.55),
            (Articulator::TipCurl, 1.0),
        ],
    ));
    if part.segment.palatalized == Some(true) {
        gestures.push(palatalized_gesture(start, end, true));
    }
}

fn lateral_gestures(part: &TimedSegment, gestures: &mut Vec<Gesture>) {
    let ipa = part.segment.ipa.as_str();
    let start = part.start_seconds;
    let end = part.end_seconds;
    let mut gesture = nonclosing_oral_gesture(
        ipa,
        start,
        end,
        &[
            (Articulator::TongueTipX, ALVEOLAR_TIP_X_CM),
            (Articulator::TongueTipY, ALVEOLAR_TIP_Y_CM),
            (Articulator::Lateral, 1.0),
        ],
    );
    if ipa == "ɫ" {
        gesture.targets.set(Artic(Articulator::TongueBodyX), 1.9);
        gesture.targets.set(Artic(Articulator::TongueBodyY), 6.8);
    }
    gestures.push(gesture);
    if ipa == "l" && part.segment.palatalized == Some(true) {
        gestures.push(palatalized_gesture(start, end, true));
    }
}

pub(super) fn alveolar_body_gesture(ipa: &str, t0: f64, t1: f64) -> Gesture {
    let mut body = single(
        ipa,
        (t0, t1),
        (0.05, 0.05),
        1.2,
        Artic(Articulator::TongueBodyX),
        3.2,
    );
    body.targets.set(Artic(Articulator::TongueBodyY), 7.4);
    body
}

pub(super) fn sibilant_oral_gesture(
    label: &str,
    t0: f64,
    t1: f64,
    voiceless: bool,
    body: BodyMix,
) -> Gesture {
    nonclosing_oral_gesture(label, t0, t1, &sibilant_targets(voiceless, body))
}

fn sibilant_targets(voiceless: bool, body: BodyMix) -> [(Articulator, f64); 3] {
    let ipa = if voiceless { "s" } else { "z" };
    let tip_y = catalog::calibrated_tip_height(ipa, 9.15, body);
    [
        (Articulator::TongueTipX, 6.3),
        (Articulator::TongueTipY, tip_y),
        (Articulator::Jaw, 0.3),
    ]
}

fn postalveolar_frication_targets(ipa: &str, body: BodyMix) -> [(Articulator, f64); 5] {
    // 固定版CHIMERA（Jameson Hodge、MIT）。/tʃ/ と /dʒ/ の解放は各摩擦音の較正を使う。
    [
        (Articulator::TongueTipX, 5.7),
        (
            Articulator::TongueTipY,
            catalog::calibrated_tip_height(ipa, 9.5, body),
        ),
        (Articulator::Jaw, 0.35),
        (Articulator::LipProtrusion, 0.75),
        (Articulator::LipSpread, 0.2),
    ]
}

fn retroflex_frication_targets(body: BodyMix) -> [(Articulator, f64); 3] {
    // 舌先の座標と反りは固定版CHIMERA由来（Jameson Hodge、MIT）。
    [
        (Articulator::TongueTipX, 5.45),
        (
            Articulator::TongueTipY,
            catalog::calibrated_tip_height("ʂ", 9.7, body),
        ),
        (Articulator::TipCurl, 0.9),
    ]
}

/// 固定版CHIMERA（Jameson Hodge、MIT）の歯摩擦音の舌先目標。
fn dental_frication_targets(ipa: &str, body: BodyMix) -> [(Articulator, f64); 2] {
    [
        (Articulator::TongueTipX, 6.85),
        (
            Articulator::TongueTipY,
            catalog::calibrated_tip_height(ipa, 8.5, body),
        ),
    ]
}

/// 固定版CHIMERA（Jameson Hodge、MIT）の歯音目標と文脈別の開大を適用する。
fn dental_gestures(
    part: &TimedSegment,
    prior: &[TimedSegment],
    next: Option<&TimedSegment>,
    body: BodyMix,
    gestures: &mut Vec<Gesture>,
) {
    let t0 = part.start_seconds;
    let t1 = part.end_seconds;
    let closed = part.manner == Some(Manner::Stop);
    let previous = prior.last();
    let (label, strength, opening) = if closed {
        let delay: f64 = match prior {
            [.., before, last]
                if matches!(last.segment.ipa.as_str(), "p" | "b")
                    && raises_tip_for_closure(before, body) =>
            {
                0.025
            }
            [.., last] if matches!(last.segment.ipa.as_str(), "s" | "z" | "ʃ" | "ʒ") => 0.03,
            _ => 0.0,
        };
        let aim = t0 + delay.min((t1 - t0 - 0.03).max(0.0));
        gestures.push(dominant_oral_gesture(
            "ð",
            (aim - 0.031, (aim + 0.010).max(t1 - 0.020)),
            1.55,
            &[
                (Articulator::TongueTipX, 6.85),
                (Articulator::TongueTipY, 9.0),
            ],
        ));
        ("stop-like ð", 6.0, 0.09)
    } else {
        gestures.push(nonclosing_oral_gesture(
            "ð",
            t0,
            t1,
            &dental_frication_targets("ð", body),
        ));
        let after_nasal = previous.is_some_and(|p| p.manner == Some(Manner::Nasal));
        (
            "voiced frication",
            3.0,
            if after_nasal { 0.035 } else { 0.09 },
        )
    };
    gestures.push(single(
        label,
        (t0 - 0.015, t1),
        (0.03, 0.03),
        strength,
        ControlKey::Abduction,
        opening,
    ));
    if closed && part.segment.breathy == Some(true) {
        gestures.push(breathy_release(t1, next));
    }
    if part.segment.palatalized == Some(true) {
        gestures.push(palatalized_gesture(t0, t1, true));
    }
}

fn fricative_gestures(part: &TimedSegment, body: BodyMix, gestures: &mut Vec<Gesture>) {
    let t0 = part.start_seconds;
    let t1 = part.end_seconds;
    let ipa = part.segment.ipa.as_str();
    let voiceless = matches!(ipa, "s" | "ʃ" | "ɕ" | "ʂ" | "f" | "θ" | "x");
    let alveolopalatal = matches!(ipa, "ɕ" | "ʑ");
    match ipa {
        "ʃ" => gestures.push(nonclosing_oral_gesture(
            ipa,
            t0,
            t1,
            &postalveolar_frication_targets(ipa, body),
        )),
        "ɕ" | "ʑ" => gestures.push(alveolopalatal_frication(ipa, ipa, t0, t1, 1.3, body)),
        "ʂ" => gestures.push(nonclosing_oral_gesture(
            ipa,
            t0,
            t1,
            &retroflex_frication_targets(body),
        )),
        "θ" => gestures.push(nonclosing_oral_gesture(
            ipa,
            t0,
            t1,
            &dental_frication_targets(ipa, body),
        )),
        "f" | "v" => {
            let fallback = if voiceless { 0.05 } else { 0.06 };
            let aperture = catalog::calibrated_lip_aperture(ipa, fallback, body);
            gestures.push(nonclosing_oral_gesture(
                ipa,
                t0,
                t1,
                &[
                    (Articulator::Labiodental, 1.0),
                    (Articulator::LipAperture, aperture),
                ],
            ));
        }
        "x" => {
            let height = catalog::calibrated_body_height(ipa, 7.7, body);
            // 舌背は開放が遅く、前後の位置は母音と重なって決まる。
            let mut dorsum = dominant_oral_gesture(
                ipa,
                (t0 - 0.008, t1.max(t0 + 0.010)),
                1.0 + (1.3 - 1.0) * 0.35,
                &[(Articulator::TongueBodyY, height)],
            );
            dorsum.ramp_out = 0.030;
            gestures.push(dorsum);
            gestures.push(single(
                ipa,
                (t0, t1),
                (0.05, 0.05),
                0.25,
                Artic(Articulator::TongueBodyX),
                2.3,
            ));
        }
        _ => {
            gestures.push(sibilant_oral_gesture(ipa, t0, t1, voiceless, body));
            gestures.push(alveolar_body_gesture(ipa, t0, t1));
        }
    }
    let (label, end, strength, opening) = if voiceless {
        ("voiceless", t1 + 0.005, 6.0, 0.30)
    } else {
        ("voiced frication", t1, 3.0, 0.09)
    };
    gestures.push(single(
        label,
        (t0 - 0.015, end),
        (0.03, 0.03),
        strength,
        ControlKey::Abduction,
        opening,
    ));
    if !alveolopalatal && part.segment.palatalized == Some(true) {
        gestures.push(palatalized_gesture(t0, t1, ipa != "x"));
    }
}

fn alveolopalatal_frication(
    label: &str,
    ipa: &str,
    start: f64,
    end: f64,
    speed: f64,
    body: BodyMix,
) -> Gesture {
    dominant_oral_gesture(
        label,
        (start - 0.008, end.max(start + 0.010)),
        speed,
        &[
            (Articulator::TongueTipX, 5.85),
            (
                Articulator::TongueTipY,
                catalog::calibrated_tip_height(ipa, 9.5, body),
            ),
            (Articulator::TongueBodyX, 3.6),
            (Articulator::TongueBodyY, 7.75),
            (Articulator::Jaw, 0.3),
            (Articulator::LipProtrusion, 0.0),
            (Articulator::LipSpread, 0.7),
        ],
    )
}

fn palatalized_gesture(start: f64, end: f64, include_height: bool) -> Gesture {
    let mut gesture = single(
        "palatalized",
        (start, end),
        (0.04, 0.04),
        3.0,
        Artic(Articulator::TongueBodyX),
        3.8,
    );
    if include_height {
        gesture.targets.set(Artic(Articulator::TongueBodyY), 7.95);
    }
    gesture
}

pub fn pitch_gestures(
    timing: &Timing,
    start: f64,
    f0: f64,
    intonation: Intonation,
) -> Vec<Gesture> {
    let mut gestures = Vec::new();
    append_pitch(
        &timing.segments,
        start,
        timing.end_seconds,
        f0,
        intonation,
        &mut gestures,
    );
    gestures
}

fn append_pitch(
    parts: &[TimedSegment],
    start: f64,
    end: f64,
    f0: f64,
    intonation: Intonation,
    gestures: &mut Vec<Gesture>,
) {
    let mut vowels = parts
        .iter()
        .enumerate()
        .filter(|(_, p)| is_vowel(p))
        .peekable();
    let nuclear = parts
        .iter()
        .rposition(|p| is_vowel(p) && p.segment.stress == Some(1) && !p.glide_from_previous);
    let total = (end - start).max(0.2);
    while let Some((i, vowel)) = vowels.next() {
        let t0 = vowel.start_seconds;
        let t1 = vowel.end_seconds;
        if let Some(frequency) = vowel.segment.f0_hz.filter(|&x| x != 0.0) {
            gestures.push(single(
                "pitch",
                (t0, t1),
                (0.06, 0.06),
                6.0,
                ControlKey::F0,
                frequency,
            ));
            continue;
        }
        let is_nuclear = nuclear == Some(i);
        let declination = 1.0 - 0.1 * ((t0 - start) / total);
        let accent = match vowel.segment.stress {
            Some(1) if is_nuclear => 1.0 + 0.14 * 1.8,
            Some(1) => 1.0 + 0.14,
            Some(2) => 1.0 + 0.14 * 0.5,
            _ => 1.0,
        };
        let target = f0 * declination * accent;
        if let Some((_, next)) = vowels.peek() {
            gestures.push(single(
                "pitch",
                (t0, t1.max(next.start_seconds - 0.03)),
                (0.06, 0.06),
                1.0,
                ControlKey::F0,
                target,
            ));
        } else if intonation == Intonation::Statement && is_nuclear && t1 - t0 > 0.08 {
            gestures.push(single(
                "pitch",
                (t0, t0 + 0.35 * (t1 - t0)),
                (0.05, 0.05),
                1.0,
                ControlKey::F0,
                target,
            ));
            gestures.push(single(
                "pitch",
                (t0 + 0.55 * (t1 - t0), t1),
                (0.06, 0.06),
                1.0,
                ControlKey::F0,
                f0 * 0.82,
            ));
        } else {
            gestures.push(single(
                "pitch",
                (t0, t1),
                (0.06, 0.06),
                1.0,
                ControlKey::F0,
                match intonation {
                    Intonation::Question => f0 * 1.35,
                    Intonation::Statement => f0 * 0.82,
                    Intonation::Flat => target,
                },
            ));
        }
    }
}

pub(super) fn single(
    label: &str,
    (t0, t1): (f64, f64),
    (ramp_in, ramp_out): (f64, f64),
    strength: f64,
    key: ControlKey,
    value: f64,
) -> Gesture {
    let mut targets = Targets::default();
    targets.set(key, value);
    Gesture {
        t0,
        t1,
        ramp_in,
        ramp_out,
        strength,
        targets,
        speed: None,
        release_hold: None,
        label: Some(label.to_owned()),
    }
}
