//! 固定上流の較正済み姿勢・線形要素・放射応答・ピークを保存する。

use chimera::airway::frequency::{find_peaks, transfer_function};
use chimera::anatomy::human::{BODY_MALE, BodyMix, HumanArtic, NEUTRAL};
use chimera::math::{PI, pow, sqrt};
use chimera::phonetics::planner::vowel_table;
use chimera::physics::{C_SOUND, RHO};
use chimera::voice::human_airway::HumanAirway;
use serde_json::Value;
use std::error::Error;
use std::fs::File;
use std::io::{BufWriter, Write};
use std::path::Path;

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let mut port_override = None;
    let (pose, body, rate, start, end, points, peak_min, directory) = match args.as_slice() {
        [flag, path, directory] if flag == "--case" => {
            let input: Value = serde_json::from_reader(File::open(path)?)?;
            let mix: BodyMix = serde_json::from_value(input["body"].clone())?;
            let number = |path: &str| {
                input
                    .pointer(path)
                    .and_then(Value::as_f64)
                    .ok_or_else(|| format!("数値設定がありません ({path})"))
            };
            let pose = HumanArtic {
                jaw: number("/posture/jaw_cm")?,
                tb_x: number("/posture/tongue_body_cm/0")?,
                tb_y: number("/posture/tongue_body_cm/1")?,
                tt_x: number("/posture/tongue_tip_cm/0")?,
                tt_y: number("/posture/tongue_tip_cm/1")?,
                root: number("/posture/tongue_root_cm")?,
                tt_curl: number("/posture/tip_curl")?,
                dorsum: number("/posture/dorsum")?,
                lip_ap: number("/posture/lip_aperture_cm")?,
                lip_prot: number("/posture/lip_protrusion_cm")?,
                lip_width: number("/posture/lip_spread")?,
                labiodental: number("/posture/labiodental")?,
                velum: number("/posture/velum_cm2")?,
                larynx: number("/posture/larynx_cm")?,
                lateral: input["posture"]["lateral"].as_f64().unwrap_or(0.0),
                epilarynx: input["posture"]["epilarynx"].as_f64().unwrap_or(0.0),
                ventricular: input["posture"]["ventricular"].as_f64().unwrap_or(0.0),
            };
            port_override = input
                .pointer("/fixed_voice_probe/velum_area_override_cm2")
                .map(|value| {
                    value
                        .as_f64()
                        .filter(|area| area.is_finite() && *area >= 0.0)
                        .ok_or("口蓋帆ポートの上書きには有限の非負面積を指定してください")
                })
                .transpose()?;
            (
                pose,
                mix.body(),
                number("/fixed_airway/sample_rate_hz")?,
                number("/transfer/start_hz")?,
                number("/transfer/end_hz")?,
                usize::try_from(
                    input["transfer"]["points"]
                        .as_u64()
                        .ok_or("周波数点数がありません")?,
                )?,
                number("/measurement/peak_search_min_hz")?,
                directory,
            )
        }
        [ipa, rate, start, end, points, peak_min, velum, directory] => {
            let mut pose = vowel_table()["male"]
                .get(ipa.as_str())
                .ok_or("較正表に母音がありません")?
                .artic
                .apply_to(&NEUTRAL);
            pose.velum = velum.parse()?;
            (
                pose,
                BODY_MALE,
                rate.parse()?,
                start.parse()?,
                end.parse()?,
                points.parse()?,
                peak_min.parse()?,
                directory,
            )
        }
        _ => {
            return Err(
                "較正済み母音と測定設定、または --case と入力・保存先を指定してください".into(),
            );
        }
    };
    let mut airway = HumanAirway::new(rate, body);
    airway.apply(&pose, 0.0);
    if let Some(area) = port_override {
        airway.net.set_port_target(airway.velum_port, area);
    }
    let elements = airway.net.linear_elements();
    let freqs: Vec<_> = (0..points)
        .map(|i| start * pow(end / start, i as f64 / (points - 1) as f64))
        .collect();
    let inject = airway.pharynx.first_node();
    let cut = airway.glottis_port;
    let response = transfer_function(&elements, inject, &freqs, &[cut]);

    let make = |name| File::create_new(Path::new(directory).join(name)).map(BufWriter::new);
    let mut configuration = make("upstream-vowel-settings.csv")?;
    writeln!(
        configuration,
        "inject,cut_left,cut_right,lips,nose,minimum_cm2"
    )?;
    let minimum = airway
        .ph_min
        .iter()
        .chain(&airway.or_min)
        .copied()
        .fold(f64::INFINITY, f64::min);
    writeln!(
        configuration,
        "{inject},{},{},{},{},{minimum}",
        elements.a[cut],
        elements.b[cut],
        airway.oral.last_node(),
        airway.nasal.last_node()
    )?;
    configuration.flush()?;

    let mut pose_csv = make("upstream-pose.csv")?;
    writeln!(
        pose_csv,
        "jaw_cm,tb_x_cm,tb_y_cm,tt_x_cm,tt_y_cm,tongue_root_cm,tip_curl,dorsum,lip_aperture_cm,lip_protrusion_cm,lip_spread,labiodental,velum_cm2,larynx_cm"
    )?;
    writeln!(
        pose_csv,
        "{},{},{},{},{},{},{},{},{},{},{},{},{},{}",
        pose.jaw,
        pose.tb_x,
        pose.tb_y,
        pose.tt_x,
        pose.tt_y,
        pose.root,
        pose.tt_curl,
        pose.dorsum,
        pose.lip_ap,
        pose.lip_prot,
        pose.lip_width,
        pose.labiodental,
        pose.velum,
        pose.larynx
    )?;
    pose_csv.flush()?;

    let mut nodes = make("upstream-linear-nodes.csv")?;
    writeln!(
        nodes,
        concat!(
            "node,compliance,fixed_pressure,wall_area_cm2,wall_mass,wall_resistance,",
            "wall_stiffness,wall_radiation_fraction,radiation_inertance,radiation_resistance"
        )
    )?;
    for i in 0..elements.n_nodes {
        let (inertance, resistance) = elements
            .rad_nodes
            .iter()
            .position(|&node| node == i)
            .map_or((0.0, 0.0), |index| {
                let area = elements.rad_area[index];
                (
                    8.0 * RHO / (3.0 * PI * sqrt(PI * area)),
                    128.0 * RHO * C_SOUND / (9.0 * PI * PI * area),
                )
            });
        writeln!(
            nodes,
            "{i},{},{},{},{},{},{},{},{inertance},{resistance}",
            elements.c[i],
            u8::from(elements.fixed[i]),
            elements.wall_area[i],
            elements.wall_m[i],
            elements.wall_r[i],
            elements.wall_k[i],
            elements.wall_rad[i]
        )?;
    }
    nodes.flush()?;
    let mut edges = make("upstream-linear-branches.csv")?;
    writeln!(edges, "left,right,open,inertance,resistance")?;
    for index in 0..elements.n_branches {
        writeln!(
            edges,
            "{},{},{},{},{}",
            elements.a[index],
            elements.b[index],
            u8::from(elements.open[index]),
            elements.l[index],
            elements.r[index]
        )?;
    }
    edges.flush()?;

    let mut trace = make("upstream-trace.csv")?;
    writeln!(trace, "frequency_hz,flow_magnitude,pressure_db")?;
    for (i, frequency) in freqs.iter().enumerate() {
        writeln!(
            trace,
            "{frequency},{},{}",
            response.mag[i], response.pressure_db[i]
        )?;
    }
    trace.flush()?;
    let mut peaks = make("upstream-peaks.csv")?;
    writeln!(peaks, "frequency_hz,bandwidth_hz,flow_level_db")?;
    for peak in find_peaks(&freqs, &response.mag, peak_min) {
        let bandwidth = if peak.bw.is_finite() {
            peak.bw.to_string()
        } else {
            String::new()
        };
        writeln!(peaks, "{},{bandwidth},{}", peak.freq, peak.db)?;
    }
    peaks.flush()?;
    Ok(())
}
