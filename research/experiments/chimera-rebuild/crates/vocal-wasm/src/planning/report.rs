//! 計画ABIのJSONを、従来と同じキー順で直接書き出す。

use serde::{Serialize, Serializer, ser::SerializeMap};
use vocal_core::score::{CONTROL_COUNT, ControlKey, Gesture, Targets};

mod english;
pub(super) use english::EnglishReport;

#[derive(Serialize)]
pub(super) struct ErrorReport<'a> {
    pub(super) error: &'a str,
}

#[derive(Serialize)]
pub(super) struct PlanReport<'a, P> {
    gestures: OrderedGestures<'a>,
    plan: &'a P,
}

impl<'a, P> PlanReport<'a, P> {
    pub(super) fn new(plan: &'a P, gestures: &'a [Gesture]) -> Self {
        Self {
            gestures: OrderedGestures::new(gestures),
            plan,
        }
    }
}

struct OrderedGestures<'a> {
    gestures: &'a [Gesture],
    target_order: [ControlKey; CONTROL_COUNT],
}

impl<'a> OrderedGestures<'a> {
    fn new(gestures: &'a [Gesture]) -> Self {
        let mut keys = ControlKey::all();
        let mut target_order = std::array::from_fn(|_| keys.next().expect("調音成分数が一致する"));
        // 以前の serde_json::Value の辞書順を保つ。各列の全ジェスチャーで順序を共有する。
        target_order.sort_unstable_by_key(|key| key.name());
        Self {
            gestures,
            target_order,
        }
    }
}

impl Serialize for OrderedGestures<'_> {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        serializer.collect_seq(self.gestures.iter().map(|gesture| OrderedGesture {
            label: gesture.label.as_deref(),
            ramp_in: gesture.ramp_in,
            ramp_out: gesture.ramp_out,
            release_hold: gesture.release_hold,
            speed: gesture.speed,
            strength: gesture.strength,
            t0: gesture.t0,
            t1: gesture.t1,
            targets: OrderedTargets {
                targets: &gesture.targets,
                order: &self.target_order,
            },
        }))
    }
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct OrderedGesture<'a> {
    #[serde(skip_serializing_if = "Option::is_none")]
    label: Option<&'a str>,
    ramp_in: f64,
    ramp_out: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    release_hold: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    speed: Option<f64>,
    strength: f64,
    t0: f64,
    t1: f64,
    targets: OrderedTargets<'a>,
}

struct OrderedTargets<'a> {
    targets: &'a Targets,
    order: &'a [ControlKey],
}

impl Serialize for OrderedTargets<'_> {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        let mut map = serializer.serialize_map(None)?;
        for &key in self.order {
            if let Some(value) = self.targets.get(key) {
                map.serialize_entry(key.name(), &value)?;
            }
        }
        map.end()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::planning::{MAX_GESTURES, PlanBuffers};
    use serde_json::json;

    fn gesture() -> Gesture {
        Gesture {
            t0: -0.0,
            t1: 0.32401500000000005,
            ramp_in: 0.07,
            ramp_out: 0.04,
            strength: 1.0,
            targets: Targets::default(),
            speed: None,
            release_hold: None,
            label: None,
        }
    }

    #[test]
    fn direct_report_matches_value_with_every_target_and_optional_field() {
        let mut full = gesture();
        for (i, key) in ControlKey::all().enumerate() {
            full.targets.set(key, (i as f64 - 8.0) / 9.0);
        }
        full.label = Some("ɪ\"階\n".into());
        full.speed = Some(1e-10);
        full.release_hold = Some(0.0);
        let gestures = [gesture(), full];
        let plan = json!({"z": [], "a": {"y": -0.0, "x": null}});
        let expected = json!({"plan": &plan, "gestures": &gestures}).to_string();
        assert_eq!(
            serde_json::to_vec(&PlanReport::new(&plan, &gestures)).unwrap(),
            expected.as_bytes()
        );
    }

    #[test]
    fn store_reports_errors_and_empty_scores_in_the_existing_format() {
        let mut buffers = PlanBuffers::default();
        buffers.store(Ok((json!({}), vec![gesture()])));
        assert!(!buffers.score.is_empty());
        for (prepared, expected) in [
            (
                Err("不正な入力 \"?\"".into()),
                json!({"error": "不正な入力 \"?\""}),
            ),
            (
                Ok((json!(null), vec![gesture(); MAX_GESTURES + 1])),
                json!({"error":"調音ジェスチャー数が上限を超えました"}),
            ),
            (
                Ok((json!([{"text": "ラ"}]), Vec::new())),
                json!({"gestures": [], "plan": [{"text": "ラ"}]}),
            ),
        ] {
            assert_eq!(buffers.store(prepared), expected.to_string().len());
            assert_eq!(buffers.report, expected.to_string().as_bytes());
            assert!(buffers.score.is_empty());
        }
    }

    #[test]
    fn failed_serialization_discards_partial_report_and_score() {
        struct PartialReport;

        impl Serialize for PartialReport {
            fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
                let mut map = serializer.serialize_map(Some(1))?;
                map.serialize_entry("途中のフィールド", "書き出し済み")?;
                Err(serde::ser::Error::custom("報告の生成に失敗"))
            }
        }

        let mut buffers = PlanBuffers::default();
        buffers.store(Ok((PartialReport, vec![gesture()])));
        let expected = json!({"error": "調音スコアの報告をJSONに変換できません"}).to_string();
        assert_eq!(buffers.report, expected.as_bytes());
        assert!(buffers.score.is_empty());

        let plan = json!({"text": "回復"});
        let gestures = vec![gesture()];
        let expected = json!({"plan": &plan, "gestures": &gestures}).to_string();
        assert_eq!(buffers.store(Ok((plan, gestures))), expected.len());
        assert_eq!(buffers.report, expected.as_bytes());
        assert_eq!(buffers.score.len(), crate::planning::SCORE_WORDS);
    }
}
