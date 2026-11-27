//! 口端流量だけを持つCSVから、指定距離の軸上音圧を計算する。

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::error::Error;
use std::fs::File;
use std::path::Path;
use vocal_core::axial::AxialObserver;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Settings {
    sample_rate_hz: u32,
    aperture_area_cm2: f64,
    distance_m: f64,
    air_density_kg_m3: f64,
    sound_speed_m_s: f64,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct MouthSample {
    sample: usize,
    mouth_flow_cm3_s: f64,
}

#[derive(Serialize)]
struct Observation {
    sample: usize,
    mouth_flow_m3_s: f64,
    disk_pressure_pa: f64,
    far_backward_pressure_pa: f64,
    far_centered_pressure_pa: f64,
}

pub(super) fn observe(input: Value, source: &Path, output: &Path) -> Result<(), Box<dyn Error>> {
    let settings: Settings = serde_json::from_value(input)?;
    let mut observer = AxialObserver::new(
        settings.sample_rate_hz,
        settings.aperture_area_cm2 * 1e-4,
        settings.distance_m,
        settings.air_density_kg_m3,
        settings.sound_speed_m_s,
    )?;
    let mut source = csv::Reader::from_path(source)?;
    let mut flows = Vec::new();
    for (index, row) in source.deserialize::<MouthSample>().enumerate() {
        let row = row?;
        if row.sample != index || !row.mouth_flow_cm3_s.is_finite() {
            return Err("口端流量CSVには0から連続する番号と有限の流量が必要です".into());
        }
        flows.push(row.mouth_flow_cm3_s * 1e-6);
    }
    if flows.is_empty() {
        return Err("口端流量CSVに1点以上の流量が必要です".into());
    }
    let trailing_zeros = std::iter::repeat_n(0.0, observer.tail_samples());
    let mut writer = csv::Writer::from_writer(File::create_new(output)?);
    for (sample, mouth_flow_m3_s) in flows.into_iter().chain(trailing_zeros).enumerate() {
        let o = observer.step(mouth_flow_m3_s);
        if ![
            o.disk_pressure_pa,
            o.far_backward_pressure_pa,
            o.far_centered_pressure_pa,
        ]
        .into_iter()
        .all(f64::is_finite)
        {
            return Err(format!("サンプル {sample} の観測音圧が非有限になりました").into());
        }
        writer.serialize(Observation {
            sample,
            mouth_flow_m3_s,
            disk_pressure_pa: o.disk_pressure_pa,
            far_backward_pressure_pa: o.far_backward_pressure_pa,
            far_centered_pressure_pa: o.far_centered_pressure_pa,
        })?;
    }
    writer.flush()?;
    Ok(())
}
