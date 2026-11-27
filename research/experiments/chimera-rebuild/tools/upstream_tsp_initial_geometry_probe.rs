//! 固定上流の発声器を作り、最初の制御更新より前の姿勢と断面を採る。

use chimera::{anatomy::human::BODY_MALE, voice::human_voice::HumanVoice};
use serde_json::json;

fn main() {
    let voice = HumanVoice::new(48_000.0, BODY_MALE, 2);
    let posture = voice.artic.x;
    let airway = &voice.airway;
    let sections: Vec<_> = [("pharynx", airway.pharynx), ("oral", airway.oral)].into_iter()
        .flat_map(|(tube, range)| (0..range.n).map(move |i| {
            let node = range.node(i);
            json!([tube, i, airway.net.dx[node], airway.net.area[node], airway.net.amin[node]])
        })).collect();
    println!("{}", json!({
        "completed_frames": 0,
        "tip_free": voice.artic.tip_free,
        "jaw_cm": posture.jaw,
        "tongue_body_cm": [posture.tb_x, posture.tb_y],
        "tongue_tip_cm": [posture.tt_x, posture.tt_y],
        "sections": sections
    }));
}
