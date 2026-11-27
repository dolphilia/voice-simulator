//! 発話中の線形応答プローブが共有する計測時刻と周波数格子。

use serde_json::Value;
use std::{error::Error, fs};

pub struct TransferRequest {
    pub completed_frames: usize,
    pub frequencies: Vec<f64>,
}

impl TransferRequest {
    pub fn read(path: &str) -> Result<Self, Box<dyn Error>> {
        let data: Value = serde_json::from_slice(&fs::read(path)?)?;
        let frames = data["observation"]["completed_pcm_frames"]
            .as_u64()
            .ok_or("観測までの出力フレーム数がありません")?;
        let sweep = &data["transfer"];
        let start = sweep["start_hz"].as_u64().ok_or("開始周波数がありません")?;
        let end = sweep["end_hz"].as_u64().ok_or("終了周波数がありません")?;
        let step = sweep["step_hz"].as_u64().ok_or("周波数刻みがありません")?;
        if step == 0 || start == 0 || end < start + 2 * step || (end - start) % step != 0 {
            return Err("観測時刻または周波数格子が不正です".into());
        }
        Ok(Self {
            completed_frames: usize::try_from(frames)?,
            frequencies: (start..=end).step_by(usize::try_from(step)?).map(|f| f as f64).collect(),
        })
    }
}
