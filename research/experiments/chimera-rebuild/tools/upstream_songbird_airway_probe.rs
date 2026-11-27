//! 固定上流の鳴禽を公開インターフェースで一サンプルずつ観測する。

use chimera::creatures::songbird;
use serde_json::Value;
use std::collections::BTreeSet;
use std::env;
use std::fs;
use std::io::{self, BufWriter, Write};

fn controls(input: &Value) -> [f64; 9] {
    [
        "pitch_hz",
        "interval_semitones",
        "voices",
        "drive",
        "tension",
        "pressure_kpa",
        "purity",
        "oec_cm3",
        "gape",
    ]
    .map(|key| input[key].as_f64().expect("比較ケースの制御値"))
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let input = env::args().nth(1).ok_or("比較ケースが必要です")?;
    let json: Value = serde_json::from_slice(&fs::read(input)?)?;
    let case = &json["songbird_airway"];
    let fs = case["sample_rate_hz"]
        .as_f64()
        .ok_or("内部レートが必要です")?;
    let samples = case["sample_count"]
        .as_u64()
        .ok_or("サンプル数が必要です")? as usize;
    let block = case["control_block_samples"]
        .as_u64()
        .ok_or("制御ブロック長が必要です")? as usize;
    let observe_beak = case["observe_beak"] == true;
    let observe_oec = case["observe_oec"] == true;
    let observe_oec_neck = case["observe_oec_neck"] == true;
    let observe_trachea_end_balance = case["observe_trachea_end_balance"] == true;
    let observe_bronchus_end_balance = case["observe_bronchus_end_balance"] == true;
    let interior_cells: Vec<usize> = case
        .get("observe_trachea_interior_cells")
        .map(|value| serde_json::from_value(value.clone()))
        .transpose()?
        .unwrap_or_default();
    let bronchus_cells: Vec<usize> = case
        .get("observe_bronchus_interior_cells")
        .map(|value| serde_json::from_value(value.clone()))
        .transpose()?
        .unwrap_or_default();
    let (mut p, mut breath) = (
        controls(&case["controls"]),
        case["breath_gate"].as_f64().ok_or("呼気ゲートが必要です")?,
    );
    let mut events = case["events"]
        .as_array()
        .ok_or("制御イベント列が必要です")?
        .iter()
        .peekable();
    let mut bird = songbird::def().create(fs);
    let dt = block as f64 / fs;
    bird.control(&p, 0.0, dt);
    let net = bird.net_mut().expect("鳴禽の気道");
    net.snap_to_targets();
    assert_eq!(
        net.tube_names,
        [
            "bronchusL",
            "bronchusR",
            "trachea",
            "air sac",
            "oec",
            "beak"
        ]
    );
    let [left, right, trachea, sac, oec, beak] = net.tubes[..] else {
        return Err("上流の気道の管数が変わりました".into());
    };
    let mut seen = BTreeSet::new();
    for &index in &interior_cells {
        if index == 0 || index >= trachea.n - 1 || !seen.insert(index) {
            return Err(format!(
                "気管の内部セルに重複しない0始まりの番号を指定してください ({index})"
            )
            .into());
        }
    }
    seen.clear();
    for &index in &bronchus_cells {
        if index >= left.n.min(right.n) - 1 || !seen.insert(index) {
            return Err(format!(
                "気管支セルには入口の0から末端の手前までの重複しない番号を指定してください ({index})"
            )
            .into());
        }
    }
    let mut beak_branches = Vec::new();
    let mut cavity_branches = None;
    if observe_beak || observe_oec || observe_oec_neck {
        let graph = net.linear_elements();
        let inlet = graph
            .a
            .iter()
            .zip(&graph.b)
            .position(|(&a, &b)| a == oec.first_node() && b == beak.first_node())
            .ok_or("口腔食道腔からくちばしへの枝がありません")?;
        if observe_beak {
            beak_branches.push(inlet);
            beak_branches.extend((0..beak.n - 1).map(|index| beak.branch(index)));
        }
        if observe_oec || observe_oec_neck {
            let neck = graph
                .a
                .iter()
                .zip(&graph.b)
                .position(|(&a, &b)| a == trachea.last_node() && b == oec.first_node())
                .ok_or("気管から口腔食道腔への枝がありません")?;
            cavity_branches = Some((neck, inlet));
        }
    }
    // 気管内の枝の直後に、空気嚢の2ポートと鳴管の2ポートが並ぶ。
    let first_syrinx = trachea.branch(trachea.n - 2) + 3;
    let trachea_out = trachea.branch(0);
    let [left_port, right_port] = [first_syrinx, first_syrinx + 1];
    let sac_ports = [first_syrinx - 2, first_syrinx - 1];
    let mut openings = Vec::with_capacity(2);
    let mut output = BufWriter::new(io::stdout().lock());
    write!(
        output,
        concat!(
            "sample,left_opening,right_opening,left_port_area_cm2,right_port_area_cm2,",
            "left_flow_cm3_s,right_flow_cm3_s,left_bronchus_pressure_dyn_cm2,right_bronchus_pressure_dyn_cm2,",
            "sac_pressure_dyn_cm2,trachea_pressure_dyn_cm2,trachea_out_flow_cm3_s,trachea_wall_flow_cm3_s,",
            "oec_area_cm2,oec_pressure_dyn_cm2,beak_tip_area_cm2,radiation_flow_cm3_s,radiation_derivative_cm3_s2"
        )
    )?;
    for index in 0..beak_branches.len() {
        write!(
            output,
            ",beak_{index}_pressure_dyn_cm2,beak_{index}_inflow_cm3_s,beak_{index}_area_cm2"
        )?;
    }
    if observe_oec {
        write!(
            output,
            ",oec_length_cm,oec_neck_inflow_cm3_s,oec_beak_outflow_cm3_s,oec_neck_precedes_beak"
        )?;
    }
    if observe_oec_neck {
        write!(
            output,
            concat!(
                ",trachea_end_pressure_dyn_cm2,trachea_end_area_cm2,trachea_end_cell_length_cm,",
                "oec_neck_area_cm2,oec_neck_noise_pressure_dyn_cm2"
            )
        )?;
    }
    if observe_trachea_end_balance {
        write!(
            output,
            concat!(
                ",trachea_penultimate_pressure_dyn_cm2,trachea_end_inflow_cm3_s,",
                "trachea_end_wall_flow_cm3_s,trachea_end_wall_displacement_cm,",
                "trachea_end_inlet_noise_pressure_dyn_cm2"
            )
        )?;
    }
    for index in &interior_cells {
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
    if observe_bronchus_end_balance {
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
    for index in &bronchus_cells {
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
    for sample in 0..samples {
        if sample.is_multiple_of(block) {
            if let Some(event) =
                events.next_if(|event| event["sample"].as_u64() == Some(sample as u64))
            {
                p = controls(&event["controls"]);
                breath = event["breath_gate"].as_f64().expect("呼気ゲート");
            }
            bird.control(&p, breath, dt);
            bird.net_mut().expect("鳴禽の気道").begin_block(block);
        }
        let output_derivative = bird.sample();
        bird.source_state(&mut openings);
        let net = bird.net().expect("鳴禽の気道");
        let values = [
            openings[0].1,
            openings[1].1,
            net.port_area[left_port],
            net.port_area[right_port],
            net.u[left_port],
            net.u[right_port],
            net.p[left.last_node()],
            net.p[right.last_node()],
            net.p[sac.first_node()],
            net.p[trachea.first_node()],
            net.u[trachea_out],
            net.wall_u[trachea.first_node()],
            net.area[oec.first_node()],
            net.p[oec.first_node()],
            net.area[beak.last_node()],
            net.radiated_flow(0),
            output_derivative,
        ];
        write!(output, "{sample}")?;
        for value in values {
            write!(output, ",{value}")?;
        }
        for (index, &branch) in beak_branches.iter().enumerate() {
            let node = beak.first_node() + index;
            write!(
                output,
                ",{},{},{}",
                net.p[node], net.u[branch], net.area[node]
            )?;
        }
        if let Some((neck, inlet)) = cavity_branches {
            if observe_oec {
                write!(
                    output,
                    ",{},{},{},{}",
                    net.dx[oec.first_node()],
                    net.u[neck],
                    net.u[inlet],
                    u8::from(neck < inlet),
                )?;
            }
            if observe_oec_neck {
                let end = trachea.last_node();
                write!(
                    output,
                    ",{},{},{},{},{}",
                    net.p[end], net.area[end], net.dx[end], net.port_area[neck], net.psrc[neck]
                )?;
            }
        }
        if observe_trachea_end_balance {
            let end = trachea.last_node();
            let inlet = trachea.branch(trachea.n - 2);
            write!(
                output,
                ",{},{},{},{},{}",
                net.p[end - 1],
                net.u[inlet],
                net.wall_u[end],
                net.wall_y[end],
                net.psrc[inlet]
            )?;
        }
        for &index in &interior_cells {
            let node = trachea.first_node() + index;
            let inlet = trachea.branch(index - 1);
            let outlet = trachea.branch(index);
            for value in [
                net.p[node],
                net.p[node - 1],
                net.u[inlet],
                net.u[outlet],
                net.wall_u[node],
                net.wall_y[node],
                net.area[node],
                net.dx[node],
                net.psrc[inlet],
            ] {
                write!(output, ",{value}")?;
            }
        }
        if observe_bronchus_end_balance {
            for tube in [left, right] {
                let end = tube.last_node();
                let inlet = tube.branch(tube.n - 2);
                write!(
                    output,
                    ",{},{},{},{}",
                    net.p[end - 1],
                    net.u[inlet],
                    net.area[end],
                    net.dx[end]
                )?;
            }
        }
        for &index in &bronchus_cells {
            for (tube, sac_port) in [left, right].into_iter().zip(sac_ports) {
                let node = tube.node(index);
                let (upstream, inlet) = if index == 0 {
                    (sac.first_node(), sac_port)
                } else {
                    (node - 1, tube.branch(index - 1))
                };
                for value in [
                    net.p[node],
                    net.u[tube.branch(index)],
                    net.p[upstream],
                    net.u[inlet],
                    net.area[node],
                    net.dx[node],
                ] {
                    write!(output, ",{value}")?;
                }
            }
        }
        writeln!(output)?;
    }
    output.flush()?;
    Ok(())
}
