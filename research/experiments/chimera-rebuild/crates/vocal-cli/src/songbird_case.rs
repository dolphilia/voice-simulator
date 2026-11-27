use crate::{Destination, write_json};
use serde::Deserialize;
use serde_json::{Value, json};
use std::collections::BTreeSet;
use std::error::Error;
use std::fs::File;
use std::io::{self, BufWriter, Write};
use vocal_core::airway::songbird::{SongbirdAirway, SongbirdControls};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Case {
    sample_rate_hz: u32,
    sample_count: usize,
    control_block_samples: usize,
    controls: SongbirdControls,
    breath_gate: f64,
    #[serde(default)]
    events: Vec<Event>,
    #[serde(default)]
    observe_beak: bool,
    #[serde(default)]
    observe_oec: bool,
    #[serde(default)]
    observe_oec_neck: bool,
    #[serde(default)]
    observe_trachea_end_balance: bool,
    #[serde(default)]
    observe_trachea_interior_cells: Vec<usize>,
    #[serde(default)]
    observe_bronchus_end_balance: bool,
    #[serde(default)]
    observe_bronchus_interior_cells: Vec<usize>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Event {
    sample: usize,
    controls: SongbirdControls,
    breath_gate: f64,
}

pub fn run(settings: &Value, destination: Destination<'_>) -> Result<(), Box<dyn Error>> {
    let case: Case = serde_json::from_value(settings.clone())?;
    let block = case.control_block_samples;
    if block == 0 || case.sample_count == 0 {
        return Err("鳴禽には正の制御ブロック長と観測サンプル数が必要です".into());
    }
    case.controls.validate(case.breath_gate)?;
    let mut previous = 0;
    for event in &case.events {
        if event.sample <= previous
            || event.sample >= case.sample_count
            || !event.sample.is_multiple_of(block)
        {
            return Err(
                "鳴禽の制御イベントは初期化の後、観測範囲内の制御境界に昇順で置いてください".into(),
            );
        }
        event.controls.validate(event.breath_gate)?;
        previous = event.sample;
    }
    let mut bird = SongbirdAirway::new(case.sample_rate_hz, case.controls)?;
    let mut seen = BTreeSet::new();
    for &index in &case.observe_trachea_interior_cells {
        if index == 0 || index >= bird.geometry().trachea_cells - 1 || !seen.insert(index) {
            return Err(format!(
                "気管の内部セルに重複しない0始まりの番号を指定してください ({index})"
            )
            .into());
        }
    }
    seen.clear();
    for &index in &case.observe_bronchus_interior_cells {
        if index >= bird.geometry().bronchus_cells_per_side - 1 || !seen.insert(index) {
            return Err(format!(
                "気管支セルには入口の0から末端の手前までの重複しない番号を指定してください ({index})"
            )
            .into());
        }
    }
    let path = match destination {
        Destination::Inspect => {
            return write_json(
                io::stdout().lock(),
                &json!({
                    "songbird_airway": settings, "geometry": bird.geometry(),
                }),
            );
        }
        Destination::Trace(path) => path,
        Destination::Pcm { .. } => return Err("鳴禽気道の内部系列は render で保存できます".into()),
    };
    let mut output = BufWriter::new(File::create_new(path)?);
    write!(
        output,
        concat!(
            "sample,left_opening,right_opening,left_port_area_cm2,right_port_area_cm2,",
            "left_flow_cm3_s,right_flow_cm3_s,left_bronchus_pressure_dyn_cm2,right_bronchus_pressure_dyn_cm2,",
            "sac_pressure_dyn_cm2,trachea_pressure_dyn_cm2,trachea_out_flow_cm3_s,trachea_wall_flow_cm3_s,",
            "oec_area_cm2,oec_pressure_dyn_cm2,beak_tip_area_cm2,radiation_flow_cm3_s,radiation_derivative_cm3_s2"
        )
    )?;
    if case.observe_beak {
        for index in 0..bird.geometry().beak_cells {
            write!(
                output,
                ",beak_{index}_pressure_dyn_cm2,beak_{index}_inflow_cm3_s,beak_{index}_area_cm2"
            )?;
        }
    }
    if case.observe_oec {
        write!(
            output,
            concat!(
                ",oec_length_cm,oec_neck_inflow_cm3_s,oec_beak_outflow_cm3_s,oec_neck_precedes_beak,",
                "oec_filtered_injection_cm3_s,oec_compliance_cm5_per_dyn"
            )
        )?;
    }
    if case.observe_oec_neck {
        write!(
            output,
            concat!(
                ",trachea_end_pressure_dyn_cm2,trachea_end_area_cm2,trachea_end_cell_length_cm,",
                "oec_neck_area_cm2,oec_neck_noise_pressure_dyn_cm2"
            )
        )?;
    }
    if case.observe_trachea_end_balance {
        write!(
            output,
            concat!(
                ",trachea_penultimate_pressure_dyn_cm2,trachea_end_inflow_cm3_s,",
                "trachea_end_wall_flow_cm3_s,trachea_end_wall_displacement_cm,",
                "trachea_end_inlet_noise_pressure_dyn_cm2"
            )
        )?;
    }
    for index in &case.observe_trachea_interior_cells {
        for field in [
            "pressure_dyn_cm2",
            "upstream_pressure_dyn_cm2",
            "inflow_cm3_s",
            "outflow_cm3_s",
            "wall_flow_cm3_s",
            "wall_displacement_cm",
            "area_cm2",
            "length_cm",
            "inlet_noise_pressure_dyn_cm2",
        ] {
            write!(output, ",trachea_{index}_{field}")?;
        }
    }
    if case.observe_bronchus_end_balance {
        for side in ["left", "right"] {
            for field in [
                "upstream_pressure_dyn_cm2",
                "inflow_cm3_s",
                "area_cm2",
                "length_cm",
            ] {
                write!(output, ",{side}_bronchus_end_{field}")?;
            }
        }
    }
    for index in &case.observe_bronchus_interior_cells {
        for side in ["left", "right"] {
            for field in [
                "pressure_dyn_cm2",
                "outflow_cm3_s",
                "upstream_pressure_dyn_cm2",
                "inflow_cm3_s",
                "area_cm2",
                "length_cm",
            ] {
                write!(output, ",{side}_bronchus_{index}_{field}")?;
            }
        }
    }
    writeln!(output)?;
    let (mut controls, mut breath) = (case.controls, case.breath_gate);
    let mut events = case.events.iter().peekable();
    for sample in 0..case.sample_count {
        if sample.is_multiple_of(block) {
            if let Some(event) = events.next_if(|event| event.sample == sample) {
                (controls, breath) = (event.controls, event.breath_gate);
            }
            bird.control(controls, breath, block)?;
        }
        let state = bird.step()?;
        let values = [
            state.opening[0],
            state.opening[1],
            state.port_area_cm2[0],
            state.port_area_cm2[1],
            state.port_flow_cm3_s[0],
            state.port_flow_cm3_s[1],
            state.bronchus_end_pressure_dyn_cm2[0],
            state.bronchus_end_pressure_dyn_cm2[1],
            state.sac_pressure_dyn_cm2,
            state.trachea_pressure_dyn_cm2,
            state.trachea_out_flow_cm3_s,
            state.trachea_wall_flow_cm3_s,
            state.oec_area_cm2,
            state.oec_pressure_dyn_cm2,
            state.beak_tip_area_cm2,
            state.radiation_flow_cm3_s,
            state.radiation_derivative_cm3_s2,
        ];
        if !values.into_iter().all(f64::is_finite) {
            return Err(format!("鳴禽のサンプル {sample} に非有限値があります").into());
        }
        write!(output, "{sample}")?;
        for value in values {
            write!(output, ",{value}")?;
        }
        if case.observe_beak {
            for cell in bird.beak_samples() {
                let values = [cell.pressure_dyn_cm2, cell.inflow_cm3_s, cell.area_cm2];
                if !values.into_iter().all(f64::is_finite) {
                    return Err(format!("くちばしのサンプル {sample} に非有限値があります").into());
                }
                for value in values {
                    write!(output, ",{value}")?;
                }
            }
        }
        if case.observe_oec {
            let state = bird.oec_sample();
            let values = [
                state.length_cm,
                state.neck_inflow_cm3_s,
                state.beak_outflow_cm3_s,
                u8::from(state.neck_precedes_beak).into(),
                state.filtered_injection_cm3_s,
                state.compliance_cm5_per_dyn,
            ];
            if !values.into_iter().all(f64::is_finite) {
                return Err(format!("口腔食道腔のサンプル {sample} に非有限値があります").into());
            }
            for value in values {
                write!(output, ",{value}")?;
            }
        }
        if case.observe_oec_neck {
            let state = bird.neck_sample();
            let values = [
                state.trachea_pressure_dyn_cm2,
                state.trachea_area_cm2,
                state.trachea_cell_length_cm,
                state.neck_area_cm2,
                state.noise_pressure_dyn_cm2,
            ];
            if !values.into_iter().all(f64::is_finite) {
                return Err(format!("気管側首部のサンプル {sample} に非有限値があります").into());
            }
            for value in values {
                write!(output, ",{value}")?;
            }
        }
        if case.observe_trachea_end_balance {
            let state = bird.trachea_end_sample();
            let values = [
                state.previous_cell_pressure_dyn_cm2,
                state.inflow_cm3_s,
                state.wall_flow_cm3_s,
                state.wall_displacement_cm,
                state.inlet_noise_pressure_dyn_cm2,
            ];
            if !values.into_iter().all(f64::is_finite) {
                return Err(format!("気管末端のサンプル {sample} に非有限値があります").into());
            }
            for value in values {
                write!(output, ",{value}")?;
            }
        }
        for &index in &case.observe_trachea_interior_cells {
            let state = bird
                .trachea_interior_sample(index)
                .ok_or("気管の内部セルを取得できません")?;
            let inlet = state.inflow_state;
            let values = [
                state.pressure_dyn_cm2,
                inlet.previous_cell_pressure_dyn_cm2,
                inlet.inflow_cm3_s,
                state.outflow_cm3_s,
                inlet.wall_flow_cm3_s,
                inlet.wall_displacement_cm,
                state.area_cm2,
                state.length_cm,
                inlet.inlet_noise_pressure_dyn_cm2,
            ];
            if !values.into_iter().all(f64::is_finite) {
                return Err(
                    format!("気管セル {index} のサンプル {sample} に非有限値があります").into(),
                );
            }
            for value in values {
                write!(output, ",{value}")?;
            }
        }
        if case.observe_bronchus_end_balance {
            for end in bird.bronchus_end_samples() {
                let values = [
                    end.upstream_pressure_dyn_cm2,
                    end.inflow_cm3_s,
                    end.area_cm2,
                    end.length_cm,
                ];
                if !values.into_iter().all(f64::is_finite) {
                    return Err(
                        format!("気管支末端のサンプル {sample} に非有限値があります").into(),
                    );
                }
                for value in values {
                    write!(output, ",{value}")?;
                }
            }
        }
        for &index in &case.observe_bronchus_interior_cells {
            let cells = bird
                .bronchus_interior_samples(index)
                .ok_or("気管支の内部セルを取得できません")?;
            for cell in cells {
                let values = [
                    cell.pressure_dyn_cm2,
                    cell.outflow_cm3_s,
                    cell.inflow_state.upstream_pressure_dyn_cm2,
                    cell.inflow_state.inflow_cm3_s,
                    cell.inflow_state.area_cm2,
                    cell.inflow_state.length_cm,
                ];
                if !values.into_iter().all(f64::is_finite) {
                    return Err(format!(
                        "気管支セル {index} のサンプル {sample} に非有限値があります"
                    )
                    .into());
                }
                for value in values {
                    write!(output, ",{value}")?;
                }
            }
        }
        writeln!(output)?;
    }
    output.flush()?;
    Ok(())
}
