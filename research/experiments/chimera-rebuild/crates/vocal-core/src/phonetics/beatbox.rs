//! ビートボックスの準備姿勢と打音。目標とタイミングはCHIMERA由来（MIT）。

use super::{
    song::midi_to_hz,
    speech::{
        alveolar_body_gesture, closure_gesture, nonclosing_oral_gesture, sibilant_oral_gesture,
        single,
    },
    vowels::male_vowel_targets,
};
use crate::{
    anatomy::BodyName,
    articulators::Articulator,
    score::{ControlKey, ControlKey::Artic, Gesture, Targets},
};
use serde::Serialize;

mod player;
pub use player::{BeatPlayer, BeatStep, ScheduledStep};

const DEFAULT_HUM_MIDI_NOTE: f64 = 40.0;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
pub enum BeatSound {
    #[serde(rename = "B")]
    Kick,
    #[serde(rename = "t")]
    Hat,
    #[serde(rename = "tss")]
    OpenHat,
    #[serde(rename = "Pf")]
    Snare,
    #[serde(rename = "K")]
    Rimshot,
    #[serde(rename = "^K")]
    InwardSnare,
    #[serde(rename = "!")]
    TongueClick,
    #[serde(rename = "P!")]
    LipPop,
    #[serde(rename = "kch")]
    Crash,
    #[serde(rename = "m")]
    Hum,
}

impl BeatSound {
    pub const MAX_GESTURES: usize = 8;

    /// 記譜の音色IDを正規化する。
    pub fn from_id(id: &str) -> Option<Self> {
        match id {
            "B" | "b" => Some(Self::Kick),
            "t" | "T" => Some(Self::Hat),
            id if id.eq_ignore_ascii_case("tss") => Some(Self::OpenHat),
            id if id.eq_ignore_ascii_case("Pf") => Some(Self::Snare),
            "K" | "k" => Some(Self::Rimshot),
            "^K" | "^k" => Some(Self::InwardSnare),
            "!" => Some(Self::TongueClick),
            "P!" | "p!" => Some(Self::LipPop),
            id if id.eq_ignore_ascii_case("kch") => Some(Self::Crash),
            "m" | "M" => Some(Self::Hum),
            _ => None,
        }
    }

    /// 単発とパターンの両方で同じレシピを使い、呼び出し元のバッファに追加する。
    pub fn append_gestures(
        self,
        hit_seconds: f64,
        accent: f64,
        step_seconds: f64,
        output: &mut Vec<Gesture>,
    ) -> Result<(), &'static str> {
        self.append_notated_gestures(hit_seconds, accent, step_seconds, None, output)
    }

    fn append_notated_gestures(
        self,
        hit_seconds: f64,
        accent: f64,
        step_seconds: f64,
        midi_note: Option<f64>,
        output: &mut Vec<Gesture>,
    ) -> Result<(), &'static str> {
        if !step_seconds.is_finite() || step_seconds <= 0.0 {
            return Err("有限の正のステップ長を指定してください");
        }
        if midi_note.is_some_and(|note| !note.is_finite()) {
            return Err("MIDI音高には有限値を指定してください");
        }
        match self {
            Self::Kick => output.extend(male_kick_gestures(hit_seconds, accent)?),
            Self::Hat => output.extend(male_hat_gestures(hit_seconds, accent)?),
            Self::OpenHat => {
                output.extend(male_open_hat_gestures(hit_seconds, accent, step_seconds)?)
            }
            Self::Snare => output.extend(male_snare_gestures(hit_seconds, accent)?),
            Self::Rimshot => output.extend(male_rimshot_gestures(hit_seconds, accent)?),
            Self::InwardSnare => output.extend(male_inward_snare_gestures(hit_seconds, accent)?),
            Self::TongueClick => output.extend(male_tongue_click_gestures(hit_seconds, accent)?),
            Self::LipPop => output.extend(male_lip_pop_gestures(hit_seconds, accent)?),
            Self::Crash => output.extend(male_crash_gestures(hit_seconds, accent, step_seconds)?),
            Self::Hum => output.extend(male_hum_gestures(
                hit_seconds,
                accent,
                step_seconds,
                midi_note.unwrap_or(DEFAULT_HUM_MIDI_NOTE),
            )?),
        }
        Ok(())
    }

    pub fn is_hat(self) -> bool {
        matches!(self, Self::Hat | Self::OpenHat | Self::Crash)
    }

    pub fn has_velar_closure(self) -> bool {
        matches!(
            self,
            Self::Rimshot | Self::InwardSnare | Self::TongueClick | Self::LipPop | Self::Crash
        )
    }

    pub fn has_oral_pocket(self) -> bool {
        matches!(self, Self::TongueClick | Self::LipPop)
    }
}

/// 舌を少し上げ、顎を閉じ気味にした /ə/ を基準目標にする。
pub fn male_ready_targets() -> Targets {
    let mut targets = *male_vowel_targets("ə").expect("固定版の /ə/ の調音目標");
    let tongue_body_y = Artic(Articulator::TongueBodyY);
    targets.set(
        tongue_body_y,
        targets.get(tongue_body_y).unwrap_or(6.85) + 0.1,
    );
    targets.set(Artic(Articulator::Jaw), 0.4);
    targets.set(Artic(Articulator::LipAperture), 0.25);
    targets.set(Artic(Articulator::LipProtrusion), 0.1);
    targets
}

/// 成人男性の放出音キック `B` を、音が鳴る予定時刻へ移した4ジェスチャーにする。
pub fn male_kick_gestures(hit_seconds: f64, accent: f64) -> Result<[Gesture; 4], &'static str> {
    validate_hit(hit_seconds, accent)?;
    let closing = -0.075;
    let lips = snap_release(closure_gesture("B", closing, 0.0, false));
    let jaw = single(
        "B",
        (closing, 0.0),
        (0.05, 0.05),
        2.2,
        Artic(Articulator::Jaw),
        0.3,
    );
    let [glottal_seal, larynx] = ejective("B", closing, accent);
    place([lips, jaw, glottal_seal, larynx], hit_seconds - 0.010)
}

fn ejective(label: &str, closing: f64, accent: f64) -> [Gesture; 2] {
    let glottal_seal = single(
        label,
        (closing - 0.012, 0.030),
        (0.012, 0.030),
        8.0,
        ControlKey::Closure,
        1.0,
    );
    let mut larynx = single(
        label,
        (-0.05, 0.004),
        (0.03, 0.08),
        40.0,
        Artic(Articulator::Larynx),
        (1.25 + 0.3 * accent).min(1.6),
    );
    larynx.speed = Some(3.0);
    [glottal_seal, larynx]
}

/// 成人男性のハイハット `t`。歯茎閉鎖のあと、遅い立上りを短縮した摩擦を加える。
pub fn male_hat_gestures(hit_seconds: f64, accent: f64) -> Result<[Gesture; 7], &'static str> {
    hat_gestures(
        "t",
        hit_seconds,
        accent,
        HatRecipe {
            frication_end: 0.03,
            frication_speed: 1.6,
            breath_end: 0.026,
            breath_gain: 1.25,
            opening_cm2: 0.36,
            breath_tail: 0.02,
        },
    )
}

fn male_open_hat_gestures(
    hit_seconds: f64,
    accent: f64,
    step_seconds: f64,
) -> Result<[Gesture; 7], &'static str> {
    let end = (step_seconds * 1.6).clamp(0.09, 0.26);
    hat_gestures(
        "tss",
        hit_seconds,
        accent,
        HatRecipe {
            frication_end: end,
            frication_speed: 1.4,
            breath_end: end,
            breath_gain: 1.2,
            opening_cm2: 0.4,
            breath_tail: 0.09,
        },
    )
}

struct HatRecipe {
    frication_end: f64,
    frication_speed: f64,
    breath_end: f64,
    breath_gain: f64,
    opening_cm2: f64,
    breath_tail: f64,
}

fn hat_gestures(
    label: &str,
    hit_seconds: f64,
    accent: f64,
    recipe: HatRecipe,
) -> Result<[Gesture; 7], &'static str> {
    validate_hit(hit_seconds, accent)?;
    let seal = snap_release(closure_gesture(label, -0.05, 0.0, true));
    let body_before_release = alveolar_body_gesture(label, -0.05, 0.0);
    let jaw = single(
        label,
        (-0.05, 0.0),
        (0.05, 0.05),
        2.2,
        Artic(Articulator::Jaw),
        0.3,
    );

    let mut frication = sibilant_oral_gesture(
        label,
        0.012,
        recipe.frication_end,
        true,
        BodyName::Male.into(),
    );
    frication.speed = Some(recipe.frication_speed);
    frication.ramp_in = 0.008;
    let mut body_during_frication = alveolar_body_gesture(label, 0.012, recipe.frication_end);
    body_during_frication.ramp_in = 0.008;
    let [opening, breath] = blow(
        label,
        (-0.03, recipe.breath_end),
        recipe.breath_gain * accent,
        recipe.opening_cm2,
        recipe.breath_tail,
    );
    place(
        [
            seal,
            body_before_release,
            jaw,
            frication,
            body_during_frication,
            opening,
            breath,
        ],
        hit_seconds - (-0.005),
    )
}

/// 両唇の破裂から、下唇を上切歯に寄せる /f/ の狭窄へ移る。
fn male_snare_gestures(hit_seconds: f64, accent: f64) -> Result<[Gesture; 4], &'static str> {
    validate_hit(hit_seconds, accent)?;
    let seal = snap_release(closure_gesture("Pf", -0.06, 0.0, false));
    let mut frication = nonclosing_oral_gesture(
        "Pf",
        0.018,
        0.08,
        &[
            (Articulator::Labiodental, 1.0),
            (Articulator::LipAperture, 0.016),
        ],
    );
    frication.ramp_in = 0.008;
    frication.speed = Some(1.6);
    let [opening, breath] = blow("Pf", (-0.045, 0.075), 1.7 * accent, 0.45, 0.04);
    place([seal, frication, opening, breath], hit_seconds - 0.018)
}

/// 舌体で軟口蓋付近を閉じ、喉頭上昇による圧力を開口時に逃がす。
fn male_rimshot_gestures(hit_seconds: f64, accent: f64) -> Result<[Gesture; 5], &'static str> {
    validate_hit(hit_seconds, accent)?;
    let closing = -0.08;
    let [dorsal_seal, jaw, tongue_x] = snapped_velar_closure("K", closing, 0.35);
    let [glottal_seal, larynx] = ejective("K", closing, accent);
    place(
        [dorsal_seal, jaw, tongue_x, glottal_seal, larynx],
        hit_seconds - (-0.0165),
    )
}

/// /k/ の閉鎖をほどいて /x/ の狭窄に移り、肺の負圧で空気を引き込む。
fn male_inward_snare_gestures(hit_seconds: f64, accent: f64) -> Result<[Gesture; 7], &'static str> {
    let label = "^K";
    validate_hit(hit_seconds, accent)?;
    let [dorsal_seal, jaw, tongue_x] = snapped_velar_closure(label, -0.06, 0.35);
    let [frication, frication_x] = velar_frication(label, (0.012, 0.085), 7.35, 1.4);
    let opening = single(
        label,
        (-0.05, 0.085),
        (0.02, 0.04),
        6.0,
        ControlKey::Abduction,
        0.5,
    );
    let suction = single(
        label,
        (-0.035, 0.085),
        (0.015, 0.05),
        2.0,
        ControlKey::Breath,
        -1.7 * accent,
    );
    place(
        [
            dorsal_seal,
            jaw,
            tongue_x,
            frication,
            frication_x,
            opening,
            suction,
        ],
        hit_seconds - (-0.014),
    )
}

/// 舌先と奥舌で囲んだ空洞を、舌背を下げて広げる。
fn male_tongue_click_gestures(hit_seconds: f64, accent: f64) -> Result<[Gesture; 5], &'static str> {
    validate_hit(hit_seconds, accent)?;
    let label = "!";
    let tip = snap_release(closure_gesture(label, -0.12, 0.0, true));
    let [rear, jaw, tongue_x] = velar_closure(label, (-0.12, 0.035), 7.85, 0.4);
    let mut dorsum = single(
        label,
        (-0.03, 0.006),
        (0.04, 0.03),
        40.0,
        Artic(Articulator::Dorsum),
        1.0,
    );
    dorsum.speed = Some(2.0);
    place([tip, rear, jaw, tongue_x, dorsum], hit_seconds + 0.007)
}

/// 唇と奥舌で囲んだ空洞を、顎と舌背の下降で広げる。
fn male_lip_pop_gestures(hit_seconds: f64, accent: f64) -> Result<[Gesture; 5], &'static str> {
    validate_hit(hit_seconds, accent)?;
    let label = "P!";
    let mut lips = closure_gesture(label, -0.12, 0.0, false);
    lips.targets.set(Artic(Articulator::LipAperture), -0.08);
    lips.speed = Some(5.0);
    lips.ramp_out = 0.006;
    let [rear, jaw, tongue_x] = velar_closure(label, (-0.12, 0.030), 8.35, 0.7);
    let mut expand = single(
        label,
        (-0.07, 0.004),
        (0.04, 0.05),
        40.0,
        Artic(Articulator::Dorsum),
        1.0,
    );
    expand.targets.set(Artic(Articulator::Jaw), 1.6);
    expand.speed = Some(2.0);
    place([lips, rear, jaw, tongue_x, expand], hit_seconds + 0.001)
}

/// 奥舌の破裂から /x/、さらに唇を丸めた /ʃ/ の摩擦へ移る。
fn male_crash_gestures(
    hit_seconds: f64,
    accent: f64,
    step_seconds: f64,
) -> Result<[Gesture; 8], &'static str> {
    validate_hit(hit_seconds, accent)?;
    let label = "kch";
    let end = (2.0 * step_seconds).clamp(0.14, 0.34);
    let [seal, jaw, tongue_x] = snapped_velar_closure(label, -0.06, 0.7);
    // 固定版の成人男性の較正表から /x/ の舌体Yと /ʃ/ の舌先Yを使う。
    let [rear_frication, rear_place] = velar_frication(label, (0.002, 0.045), 7.365, 2.0);
    let mut rounded_frication = nonclosing_oral_gesture(
        label,
        0.025,
        end,
        &[
            (Articulator::TongueTipX, 5.7),
            (Articulator::TongueTipY, 9.512),
            (Articulator::Jaw, 0.35),
            (Articulator::LipProtrusion, 0.75),
            (Articulator::LipSpread, 0.2),
        ],
    );
    rounded_frication.ramp_in = 0.008;
    rounded_frication.speed = Some(1.4);
    let [opening, breath] = blow(label, (-0.035, end), 1.75 * accent, 0.45, 0.14);
    place(
        [
            seal,
            jaw,
            tongue_x,
            rear_frication,
            rear_place,
            rounded_frication,
            opening,
            breath,
        ],
        hit_seconds + 0.013,
    )
}

fn velar_frication(
    label: &str,
    (start, end): (f64, f64),
    body_y_cm: f64,
    speed: f64,
) -> [Gesture; 2] {
    let mut frication =
        nonclosing_oral_gesture(label, start, end, &[(Articulator::TongueBodyY, body_y_cm)]);
    frication.ramp_in = 0.008;
    frication.ramp_out = 0.030;
    frication.speed = Some(1.0 + (speed - 1.0) * 0.35);
    let tongue_x = single(
        label,
        (start, end),
        (0.008, 0.05),
        0.25,
        Artic(Articulator::TongueBodyX),
        2.3,
    );
    [frication, tongue_x]
}

/// 先に閉唇して鼻腔を開き、スコアの呼気と音高で鼻音を伸ばす。
fn male_hum_gestures(
    hit_seconds: f64,
    accent: f64,
    step_seconds: f64,
    midi_note: f64,
) -> Result<[Gesture; 5], &'static str> {
    let label = "m";
    validate_hit(hit_seconds, accent)?;
    let f0_hz = midi_to_hz(midi_note);
    if !f0_hz.is_finite() || f0_hz <= 0.0 {
        return Err("MIDI音高を有限の正の周波数に変換できません");
    }
    let end = (0.92 * step_seconds).max(0.06);
    let mut lips = closure_gesture(label, -0.03, end, false);
    lips.speed = Some(1.6);
    let nasal = single(
        label,
        (-0.02, end),
        (0.03, 0.03),
        4.0,
        Artic(Articulator::Velum),
        0.9,
    );
    let opening = single(
        label,
        (-0.08, -0.03),
        (0.02, 0.02),
        5.0,
        ControlKey::Abduction,
        0.3,
    );
    let breath = single(
        label,
        (-0.01, end),
        (0.02, 0.04),
        1.0,
        ControlKey::Breath,
        0.95 * accent,
    );
    let pitch = single(
        label,
        (-0.02, end),
        (0.015, 0.02),
        8.0,
        ControlKey::F0,
        f0_hz,
    );
    place([lips, nasal, opening, breath, pitch], hit_seconds - 0.0056)
}

fn snapped_velar_closure(label: &str, closing: f64, jaw_cm: f64) -> [Gesture; 3] {
    let [mut seal, jaw, tongue_x] = velar_closure(label, (closing, 0.0), 8.35, jaw_cm);
    seal.speed = Some(4.0);
    seal.ramp_out = 0.008;
    [seal, jaw, tongue_x]
}

fn velar_closure(
    label: &str,
    (closing, release): (f64, f64),
    body_y_cm: f64,
    jaw_cm: f64,
) -> [Gesture; 3] {
    let mut dorsal_seal = single(
        label,
        (closing - 0.024, (closing + 0.01).max(release - 0.034)),
        (0.03, 0.030),
        40.0,
        Artic(Articulator::TongueBodyY),
        body_y_cm,
    );
    dorsal_seal.speed = Some(1.35);
    dorsal_seal.release_hold = Some(0.045);
    let jaw = single(
        label,
        (closing, release),
        (0.05, 0.05),
        2.2,
        Artic(Articulator::Jaw),
        jaw_cm,
    );
    let tongue_x = single(
        label,
        (closing, release),
        (0.05, 0.05),
        0.25,
        Artic(Articulator::TongueBodyX),
        2.3,
    );
    [dorsal_seal, jaw, tongue_x]
}

fn snap_release(mut closure: Gesture) -> Gesture {
    closure.speed = Some(3.5);
    closure.ramp_out = 0.01;
    closure
}

fn blow(
    label: &str,
    (start, end): (f64, f64),
    level: f64,
    area_cm2: f64,
    tail: f64,
) -> [Gesture; 2] {
    [
        single(
            label,
            (start, end + tail + 0.02),
            (0.02, 0.03),
            6.0,
            ControlKey::Abduction,
            area_cm2,
        ),
        single(
            label,
            (start - 0.01, end),
            (0.02, tail),
            1.0,
            ControlKey::Breath,
            level,
        ),
    ]
}

fn validate_hit(hit_seconds: f64, accent: f64) -> Result<(), &'static str> {
    if !hit_seconds.is_finite() || !(0.5..=1.5).contains(&accent) {
        return Err("打音時刻には有限値、アクセントには0.5〜1.5を指定してください");
    }
    Ok(())
}

fn place<const N: usize>(
    mut gestures: [Gesture; N],
    offset: f64,
) -> Result<[Gesture; N], &'static str> {
    for gesture in &mut gestures {
        gesture.t0 += offset;
        gesture.t1 += offset;
        gesture.validate()?;
    }
    Ok(gestures)
}
