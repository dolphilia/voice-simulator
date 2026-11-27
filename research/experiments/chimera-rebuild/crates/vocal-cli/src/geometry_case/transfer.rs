//! 固定姿勢の線形伝達関数を観測する。

use serde::Deserialize;
use serde_json::{Value, json};
use std::fs::File;
use std::io::{BufWriter, Write};
use std::path::Path;
use vocal_core::airway::human::HumanAirway;

#[derive(Clone, Copy, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Sweep {
    start_hz: f64,
    end_hz: f64,
    points: usize,
}

impl Sweep {
    fn validate(self) -> Result<(), &'static str> {
        if !(self.start_hz > 0.0
            && self.start_hz < self.end_hz
            && (self.end_hz / self.start_hz).is_finite()
            && self.points >= 2)
        {
            return Err("伝達関数には有限の正の周波数範囲と2点以上の測定点を指定してください");
        }
        Ok(())
    }

    pub(super) fn inspect(self, airway: &HumanAirway) -> Result<Value, &'static str> {
        self.validate()?;
        let elements = airway.network.linear_elements();
        let nodes: Vec<_> = elements
            .nodes
            .into_iter()
            .map(|node| {
                let [inertance, resistance] = node.radiation.unwrap_or([0.0; 2]);
                let wall = node.wall.map_or([0.0; 5], |wall| {
                    [
                        wall.area_cm2,
                        wall.parameters.mass_g_cm2,
                        wall.parameters.resistance_dyn_s_cm3,
                        wall.parameters.stiffness_dyn_cm3,
                        wall.parameters.radiation_fraction,
                    ]
                });
                json!({
                    "compliance": node.compliance, "fixed_pressure": node.fixed_pressure,
                    "wall_area_cm2": wall[0], "wall_mass": wall[1], "wall_resistance": wall[2],
                    "wall_stiffness": wall[3], "wall_radiation_fraction": wall[4],
                    "radiation_inertance": inertance, "radiation_resistance": resistance,
                })
            })
            .collect();
        let branches: Vec<_> = elements
            .branches
            .into_iter()
            .map(|branch| {
                json!({
                    "nodes": branch.nodes, "open": branch.open,
                    "inertance": branch.inertance, "resistance": branch.resistance,
                })
            })
            .collect();
        Ok(json!({
            "inject": airway.pharynx_entry, "cut": [airway.glottis_port],
            "lips": airway.lips, "nose": airway.nostrils,
            "nodes": nodes, "branches": branches,
        }))
    }

    pub(super) fn write(
        self,
        airway: &HumanAirway,
        path: &Path,
    ) -> Result<(), Box<dyn std::error::Error>> {
        self.validate()?;
        let ratio = self.end_hz / self.start_hz;
        let frequencies: Vec<_> = (0..self.points)
            .map(|index| self.start_hz * ratio.powf(index as f64 / (self.points - 1) as f64))
            .collect();
        let response = airway.network.linear_elements().transfer(
            airway.pharynx_entry,
            &[airway.glottis_port],
            &frequencies,
        )?;
        let mut output = BufWriter::new(File::create_new(path)?);
        writeln!(
            output,
            concat!(
                "frequency_hz,total_real,total_imaginary,flow_magnitude,pressure_db,",
                "lips_real,lips_imaginary,nose_real,nose_imaginary,wall_real,wall_imaginary",
            )
        )?;
        for point in response {
            let [lips, nose] = point.radiators[..] else {
                return Err("口端と鼻端の放射負荷が必要です".into());
            };
            writeln!(
                output,
                "{},{},{},{},{},{},{},{},{},{},{}",
                point.frequency_hz,
                point.total.real,
                point.total.imaginary,
                point.total.magnitude(),
                point.pressure_db(),
                lips.real,
                lips.imaginary,
                nose.real,
                nose.imaginary,
                point.wall.real,
                point.wall.imaginary
            )?;
        }
        output.flush()?;
        Ok(())
    }
}
