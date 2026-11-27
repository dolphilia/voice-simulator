//! 固定上流の女性発声器で、最初の制御更新より前の調音座標を取得する。

use chimera::{
    anatomy::human::{ArticKey, BODY_FEMALE},
    voice::human_voice::HumanVoice,
};

fn main() {
    let voice = HumanVoice::new(48_000.0, BODY_FEMALE, 2);
    let posture = voice.artic.x;
    println!(
        "[{},{},{},{},{}]",
        posture.get(ArticKey::Jaw),
        posture.get(ArticKey::TbX),
        posture.get(ArticKey::TbY),
        posture.get(ArticKey::TtX),
        posture.get(ArticKey::TtY),
    );
}
