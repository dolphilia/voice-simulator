//! 姿勢ケースの輪郭を部位名と点番号付きで出力する。

use serde::Deserialize;
use serde_json::{Value, json};
use std::error::Error;
use std::fs::File;
use std::io::{self, BufWriter, Write};
use std::num::NonZeroUsize;
use std::path::Path;
use std::slice::from_ref;
use vocal_core::airway::human::HumanAirway;
use vocal_core::anatomy::{
    Articulation, BodyMix, BodyName, GridSample, Point, RoofContact, SagittalFrame, SagittalModel,
};
use vocal_core::phonetics::vowels::{fixed_vowel_posture, vowel_targets};
use vocal_core::score::Targets;

mod transfer;
pub(crate) mod voice;

use crate::network_case::Destination;

#[derive(Deserialize)]
#[serde(untagged, deny_unknown_fields)]
pub(super) enum BodyInput {
    Named(BodyName),
    Mix {
        #[serde(default)]
        female: f64,
        #[serde(default)]
        child: f64,
    },
}

impl From<BodyInput> for BodyMix {
    fn from(input: BodyInput) -> Self {
        match input {
            BodyInput::Named(name) => name.into(),
            BodyInput::Mix { female, child } => Self::new(female, child),
        }
    }
}

#[derive(Clone, Copy, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Pose {
    jaw_cm: f64,
    tongue_body_cm: [f64; 2],
    tongue_tip_cm: [f64; 2],
    tongue_root_cm: f64,
    tip_curl: f64,
    dorsum: f64,
    lip_aperture_cm: f64,
    lip_protrusion_cm: f64,
    lip_spread: f64,
    labiodental: f64,
    velum_cm2: f64,
    larynx_cm: f64,
    #[serde(default)]
    lateral: f64,
    #[serde(default)]
    epilarynx: f64,
    #[serde(default)]
    ventricular: f64,
}

impl From<Pose> for Articulation {
    fn from(p: Pose) -> Self {
        Self {
            jaw_cm: p.jaw_cm,
            tongue_body_cm: Point::new(p.tongue_body_cm[0], p.tongue_body_cm[1]),
            tongue_tip_cm: Point::new(p.tongue_tip_cm[0], p.tongue_tip_cm[1]),
            tongue_root_cm: p.tongue_root_cm,
            tip_curl: p.tip_curl,
            dorsum: p.dorsum,
            lip_aperture_cm: p.lip_aperture_cm,
            lip_protrusion_cm: p.lip_protrusion_cm,
            lip_spread: p.lip_spread,
            labiodental: p.labiodental,
            velum_cm2: p.velum_cm2,
            larynx_cm: p.larynx_cm,
            lateral: p.lateral,
            epilarynx: p.epilarynx,
            ventricular: p.ventricular,
        }
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct GeometryCase<'a> {
    id: &'a str,
    upstream_revision: &'a str,
    hypothesis: &'a str,
    body: BodyInput,
    posture: Posture<'a>,
    cells: Option<CellCounts>,
    fixed_airway: Option<FixedAirwaySettings>,
    fixed_airway_periodic_flow: Option<PeriodicFlowInput>,
    transfer: Option<transfer::Sweep>,
    voice: Option<voice::Settings>,
    fixed_voice_probe: Option<voice::Probe>,
    #[serde(default)]
    gate_events: Vec<voice::GateEvent>,
    measurement: Measurement,
}

#[derive(Deserialize)]
#[serde(untagged, deny_unknown_fields)]
enum Posture<'a> {
    Explicit(Pose),
    Calibrated { vowel: &'a str },
}

#[derive(Clone, Copy, Deserialize)]
#[serde(deny_unknown_fields)]
struct CellCounts {
    pharynx: NonZeroUsize,
    oral: NonZeroUsize,
}

#[derive(Deserialize)]
struct Measurement {
    frames: usize,
}

#[derive(Clone, Copy, Deserialize)]
#[serde(deny_unknown_fields)]
struct FixedAirwaySettings {
    sample_rate_hz: u32,
    impulse_volume_cm3: f64,
    sample_count: NonZeroUsize,
    #[serde(default)]
    impulse_sample: usize,
    #[serde(default)]
    steady_flow_cm3_s: f64,
    trace_state_samples: Option<[usize; 2]>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PeriodicFlowInput {
    start_sample: usize,
    flow_cm3_s: Vec<String>,
}

struct PeriodicFlow {
    start_sample: usize,
    samples: Vec<f64>,
}

impl PeriodicFlowInput {
    fn parse(self, settings: FixedAirwaySettings) -> Result<PeriodicFlow, &'static str> {
        let remaining = settings
            .sample_count
            .get()
            .saturating_sub(self.start_sample);
        if self.flow_cm3_s.is_empty() || self.flow_cm3_s.len() > remaining {
            return Err("周期流量の1ブロックを計算区間内に指定してください");
        }
        if settings.impulse_volume_cm3 != 0.0 {
            return Err("周期流量のケースでは注入体積をゼロにしてください");
        }
        let samples = self
            .flow_cm3_s
            .iter()
            .map(|value| {
                value
                    .parse::<f64>()
                    .ok()
                    .filter(|value| value.is_finite())
                    .ok_or("周期流量には有限の10進数文字列が必要です")
            })
            .collect::<Result<Vec<_>, _>>()?;
        Ok(PeriodicFlow {
            start_sample: self.start_sample,
            samples,
        })
    }
}

impl FixedAirwaySettings {
    fn impulse_flow(self) -> f64 {
        self.impulse_volume_cm3 * f64::from(self.sample_rate_hz)
    }

    fn build(
        self,
        model: &SagittalModel,
        frame: &SagittalFrame,
    ) -> Result<HumanAirway, &'static str> {
        if !self.impulse_flow().is_finite() {
            return Err("体積のインパルスは有限な流量へ換算できる値で指定してください");
        }
        if self.impulse_sample >= self.sample_count.get() {
            return Err("インパルスの標本番号は計算区間内で指定してください");
        }
        if !(self.steady_flow_cm3_s + self.impulse_flow()).is_finite() {
            return Err("定常流量とインパルス流量の和は有限である必要があります");
        }
        if let Some([start, end]) = self.trace_state_samples
            && (start >= end || end > self.sample_count.get())
        {
            return Err("節点と枝の観測区間は計算区間内の空でない半開区間を指定してください");
        }
        HumanAirway::fixed_from_profile(
            self.sample_rate_hz,
            &model.area_profile(frame)?,
            frame.velum_port_cm2,
        )
    }
}

struct PoseGeometry {
    body: BodyMix,
    model: SagittalModel,
    frame: SagittalFrame,
    vowel_targets: Option<Targets>,
    cells: Option<CellCounts>,
    fixed_airway: Option<FixedAirwaySettings>,
    fixed_airway_periodic_flow: Option<PeriodicFlow>,
    transfer: Option<transfer::Sweep>,
    voice: Option<voice::Settings>,
    fixed_voice_probe: Option<voice::Probe>,
    gate_events: Vec<voice::GateEvent>,
}

fn compute(input: &Value) -> Result<PoseGeometry, Box<dyn Error>> {
    let case = GeometryCase::deserialize(input)?;
    if case.id.is_empty() || case.upstream_revision.is_empty() || case.hypothesis.is_empty() {
        return Err("姿勢ケースにID、上流版、仮説を指定してください".into());
    }
    if case.measurement.frames != 1 {
        return Err("姿勢ケースは1フレームを指定してください".into());
    }
    if case.transfer.is_some() && case.fixed_airway.is_none() {
        return Err("伝達関数には固定姿勢の気道条件も指定してください".into());
    }
    if case.voice.is_some() && case.fixed_airway.is_none() {
        return Err("母音発声には固定姿勢の気道条件も指定してください".into());
    }
    if !case.gate_events.is_empty() && case.voice.is_none() {
        return Err("呼気イベントには固定発声の設定が必要です".into());
    }
    if case.fixed_voice_probe.is_some() && case.voice.is_none() {
        return Err("発声の計測条件には固定発声の設定が必要です".into());
    }
    let fixed_airway_periodic_flow = match case.fixed_airway_periodic_flow {
        Some(flow) => {
            let settings = case
                .fixed_airway
                .ok_or("周期流量には固定姿勢の気道条件も指定してください")?;
            if case.voice.is_some() || case.transfer.is_some() {
                return Err("周期流量は固定気道の時系列描画で指定してください".into());
            }
            Some(flow.parse(settings)?)
        }
        None => None,
    };
    let body = BodyMix::from(case.body);
    let (posture, vowel_targets) = match case.posture {
        Posture::Explicit(pose) => (pose.into(), None),
        Posture::Calibrated { vowel } => {
            let targets = vowel_targets(vowel, body)
                .ok_or_else(|| format!("固定姿勢に使える較正済み単母音がありません ({vowel})"))?;
            (fixed_vowel_posture(&targets), Some(targets))
        }
    };
    let model = SagittalModel::new(body);
    let mut frame = model.compute(posture);
    if let Some(area) = case
        .fixed_voice_probe
        .as_ref()
        .and_then(|probe| probe.velum_area_override_cm2)
    {
        if !area.is_finite() || area < 0.0 {
            return Err("口蓋帆ポートの上書きには有限の非負面積を指定してください".into());
        }
        // 輪郭を計算した後に音響ポートだけを置き換える。
        frame.velum_port_cm2 = area;
    }
    if sections(&model, &frame)
        .into_iter()
        .flat_map(|(_, points)| points)
        .any(|point| !point.x.is_finite() || !point.y.is_finite())
    {
        return Err("輪郭の座標が有限範囲を超えました".into());
    }
    Ok(PoseGeometry {
        body,
        model,
        frame,
        vowel_targets,
        cells: case.cells,
        fixed_airway: case.fixed_airway,
        fixed_airway_periodic_flow,
        transfer: case.transfer,
        voice: case.voice,
        fixed_voice_probe: case.fixed_voice_probe,
        gate_events: case.gate_events,
    })
}

fn sections<'a>(
    model: &'a SagittalModel,
    frame: &'a SagittalFrame,
) -> [(&'static str, &'a [Point]); 15] {
    [
        ("outer", &frame.outer),
        ("inner", &frame.inner),
        ("tongue", &frame.tongue),
        ("velum", &frame.velum),
        ("upper_lip", &frame.upper_lip),
        ("lower_lip", &frame.lower_lip),
        ("upper_teeth", &frame.upper_teeth),
        ("lower_teeth", &frame.lower_teeth),
        ("jaw_bone", &frame.jaw_bone),
        ("epiglottis", &frame.epiglottis),
        ("nasal_cavity", model.nasal_cavity()),
        ("palate", model.palate()),
        ("glottis", from_ref(&frame.glottis)),
        ("tongue_center", from_ref(&frame.tongue_center)),
        ("tip", from_ref(&frame.tip)),
    ]
}

pub(super) fn inspect(input: &Value) -> Result<(), Box<dyn Error>> {
    let PoseGeometry {
        body,
        model,
        frame,
        vowel_targets,
        cells,
        fixed_airway,
        transfer,
        voice,
        fixed_voice_probe,
        gate_events,
        ..
    } = compute(input)?;
    let point_counts: serde_json::Map<_, _> = sections(&model, &frame)
        .into_iter()
        .map(|(name, points)| (name.to_owned(), json!(points.len())))
        .collect();
    let mut settings = json!({
            "case": input,
            "unit_system": "CGS",
            "coordinates": {"x": "forward", "y": "up", "origin": "neutral_glottis"},
            "point_counts": point_counts,
    });
    if let Some(targets) = vowel_targets {
        settings["vowel_targets"] = json!(targets);
    }
    if input["body"].as_str() != Some("male") || input.pointer("/measurement/body").is_some() {
        let parameters = body.parameters();
        settings["body"] = json!({
            "weights": body.weights().map(|(_, weight)| weight),
            "preset": body.preset(),
            "nearest": body.nearest(),
            "parameters": parameters,
            "default_f0_hz": body.default_f0_hz(),
            "tongue_radius_cm": frame.tongue_radius_cm,
            "lip_width_cm": frame.lip_width_cm,
            "velum_port_cm2": frame.velum_port_cm2,
            "epilarynx_length_cm": parameters.epilarynx_length_cm(),
        });
    }
    if input.pointer("/measurement/contact").is_some() {
        let contact = model.contact_grid(&frame);
        let report = |point: RoofContact| {
            json!({
                "distance_cm": point.distance_cm,
                "normal": [point.normal.x, point.normal.y],
            })
        };
        settings["contact"] = json!({"tip": report(contact.tip), "body": report(contact.body)});
    }
    let report_area = input.pointer("/measurement/area").is_some();
    if report_area || cells.is_some() {
        let profile = model.area_profile(&frame)?;
        if report_area {
            settings["area"] = json!({
                "length_cm": profile.length_cm,
                "pharynx_length_cm": profile.pharynx_length_cm,
                "teeth_s_cm": profile.teeth_s_cm,
                "lip_s_cm": profile.length_cm,
                "lip_area_cm2": profile.lip_area_cm2,
                "split_index": profile.split_index.map_or(-1, |index| index as i32),
            });
        }
        if let Some(cells) = cells {
            let tract = profile.resample(cells.pharynx, cells.oral)?;
            settings["resample"] = json!({
                "pharynx_length_cm": tract.pharynx.length_cm,
                "oral_length_cm": tract.oral.length_cm,
                "pharynx_cells": tract.pharynx.cells.len(),
                "oral_cells": tract.oral.cells.len(),
            });
        }
    }
    if let Some(fixed) = fixed_airway {
        let airway = fixed.build(&model, &frame)?;
        if let Some(sweep) = transfer {
            settings["transfer"] = sweep.inspect(&airway)?;
        }
        let network = &airway.network;
        let tubes: Vec<_> = airway
            .tubes
            .iter()
            .map(|tube| {
                json!({
                    "name": tube.name, "first_node": tube.nodes.start, "cells": tube.nodes.len(),
                    "anatomical_length_cm": tube.anatomical_length_cm,
                    "simulation_length_cm": tube.simulation_length_cm,
                })
            })
            .collect();
        let sections: Vec<_> = airway
            .tubes
            .iter()
            .flat_map(|tube| tube.nodes.clone())
            .map(|node| {
                let section = network.section(node);
                json!({
                    "node": node, "cell_length_cm": section.length_cm, "area_cm2": section.area_cm2,
                    "minimum_area_cm2": section.minimum_area_cm2,
                    "geometric_compliance": network.compliance(node).geometric,
                })
            })
            .collect();
        settings["fixed_airway"] = json!({
            "courant": network.courant(), "velum_port_cm2": airway.velum_area_cm2,
            "node_count": sections.len(), "branch_count": network.branch_count(),
            "tubes": tubes, "sections": sections,
        });
        if let Some(voice) = voice {
            settings["voice"] = voice.inspect(
                fixed,
                airway,
                body.default_f0_hz(),
                &gate_events,
                fixed_voice_probe.as_ref(),
            )?;
        }
    }
    let mut output = io::stdout().lock();
    serde_json::to_writer_pretty(&mut output, &settings)?;
    writeln!(output)?;
    Ok(())
}

pub(super) fn render_fixed_voice(
    input: &Value,
    destination: Destination<'_>,
) -> Result<(), Box<dyn Error>> {
    let PoseGeometry {
        body,
        model,
        frame,
        fixed_airway,
        voice,
        fixed_voice_probe,
        gate_events,
        ..
    } = compute(input)?;
    let fixed = fixed_airway.ok_or("固定姿勢の気道条件を指定してください")?;
    let voice = voice.ok_or("母音発声の音源条件を指定してください")?;
    voice.render(
        fixed,
        fixed.build(&model, &frame)?,
        body.default_f0_hz(),
        &gate_events,
        fixed_voice_probe.as_ref(),
        destination,
    )
}

pub(super) fn render_transfer(input: &Value, path: &Path) -> Result<(), Box<dyn Error>> {
    let PoseGeometry {
        model,
        frame,
        fixed_airway,
        transfer,
        ..
    } = compute(input)?;
    let settings = fixed_airway.ok_or("固定姿勢の気道条件を指定してください")?;
    let sweep = transfer.ok_or("伝達関数の周波数範囲と測定点数を指定してください")?;
    let airway = settings.build(&model, &frame)?;
    sweep.write(&airway, path)
}

pub(super) fn render(input: &Value, path: &Path) -> Result<(), Box<dyn Error>> {
    let PoseGeometry { model, frame, .. } = compute(input)?;
    let mut output = BufWriter::new(File::create_new(path)?);
    writeln!(output, "part,index,x_cm,y_cm")?;
    for (part, points) in sections(&model, &frame) {
        for (index, Point { x, y }) in points.iter().enumerate() {
            writeln!(output, "{part},{index},{x},{y}")?;
        }
    }
    output.flush()?;
    Ok(())
}

pub(super) fn render_grid(input: &Value, path: &Path) -> Result<(), Box<dyn Error>> {
    let PoseGeometry { model, frame, .. } = compute(input)?;
    write_grid(
        path,
        model
            .measurement_grid(&frame)
            .into_iter()
            .map(|ray| (ray, [])),
        "",
    )
}

pub(super) fn render_contact(input: &Value, path: &Path) -> Result<(), Box<dyn Error>> {
    let PoseGeometry { model, frame, .. } = compute(input)?;
    let samples = model.contact_grid(&frame).samples;
    write_grid(
        path,
        samples
            .into_iter()
            .map(|sample| (sample.ray, [sample.gap_cm])),
        ",gap_cm",
    )
}

pub(super) fn render_area(input: &Value, path: &Path) -> Result<(), Box<dyn Error>> {
    let PoseGeometry { model, frame, .. } = compute(input)?;
    let profile = model.area_profile(&frame)?;
    write_grid(
        path,
        profile.samples.into_iter().map(|sample| {
            (
                sample.contact.ray,
                [sample.contact.gap_cm, sample.area_cm2, sample.s_cm],
            )
        }),
        ",gap_cm,area_cm2,s_cm",
    )
}

pub(super) fn render_resampled(input: &Value, path: &Path) -> Result<(), Box<dyn Error>> {
    let PoseGeometry {
        model,
        frame,
        cells,
        ..
    } = compute(input)?;
    let counts = cells.ok_or("セルへ割り当てるには咽頭・口腔のセル数を指定してください")?;
    let tract = model
        .area_profile(&frame)?
        .resample(counts.pharynx, counts.oral)?;
    let mut output = BufWriter::new(File::create_new(path)?);
    writeln!(
        output,
        "tube,cell,start_cm,end_cm,area_cm2,minimum_area_cm2"
    )?;
    for (name, start, tube) in [
        ("pharynx", 0.0, &tract.pharynx),
        ("oral", tract.pharynx.length_cm, &tract.oral),
    ] {
        let width = tube.length_cm / tube.cells.len() as f64;
        for (index, cell) in tube.cells.iter().enumerate() {
            writeln!(
                output,
                "{name},{index},{},{},{},{}",
                start + width * index as f64,
                start + width * (index + 1) as f64,
                cell.area_cm2,
                cell.minimum_area_cm2
            )?;
        }
    }
    output.flush()?;
    Ok(())
}

pub(super) fn render_fixed_airway(input: &Value, path: &Path) -> Result<(), Box<dyn Error>> {
    let PoseGeometry {
        model,
        frame,
        fixed_airway,
        fixed_airway_periodic_flow,
        ..
    } = compute(input)?;
    let settings = fixed_airway.ok_or("固定姿勢の計算条件を指定してください")?;
    let mut airway = settings.build(&model, &frame)?;
    let network = &mut airway.network;
    let trace = settings.trace_state_samples.map(|[start, end]| start..end);
    let (nodes, branches) = if trace.is_some() {
        (
            network.linear_elements().nodes.len(),
            network.branch_count(),
        )
    } else {
        (0, 0)
    };
    let mut output = BufWriter::new(File::create_new(path)?);
    write!(
        output,
        concat!(
            "sample,pressure_pharynx_entry,pressure_junction,pressure_lips,pressure_nose,pressure_sinus,",
            "flow_oral_link,flow_velum,flow_sinus_neck,flow_lips,flow_nose,flow_walls,radiation_derivative",
        )
    )?;
    for node in 0..nodes {
        write!(output, ",pressure_node_{node}")?;
    }
    for branch in 0..branches {
        write!(output, ",flow_branch_{branch}")?;
    }
    writeln!(output)?;
    for sample in 0..settings.sample_count.get() {
        let periodic = fixed_airway_periodic_flow.as_ref().and_then(|flow| {
            sample
                .checked_sub(flow.start_sample)
                .map(|offset| (flow, offset))
        });
        let excitation = if let Some((flow, offset)) = periodic {
            flow.samples[offset % flow.samples.len()]
        } else if sample == settings.impulse_sample {
            settings.steady_flow_cm3_s + settings.impulse_flow()
        } else {
            settings.steady_flow_cm3_s
        };
        let radiation = network.step(airway.pharynx_entry, excitation);
        if trace.as_ref().is_some_and(|range| !range.contains(&sample)) {
            continue;
        }
        write!(
            output,
            "{sample},{},{},{},{},{},{},{},{},{},{},{},{}",
            network.pressure(airway.pharynx_entry),
            network.pressure(airway.pharynx_end),
            network.pressure(airway.lips),
            network.pressure(airway.nostrils),
            network.pressure(airway.sinus),
            network.branch_flow(airway.oral_link),
            network.branch_flow(airway.velum_port),
            network.branch_flow(airway.sinus_neck),
            network.radiation_flow(airway.lips).expect("口端の放射負荷"),
            network
                .radiation_flow(airway.nostrils)
                .expect("鼻端の放射負荷"),
            radiation.wall_radiation_flow_cm3_s,
            radiation.radiation_flow_derivative_cm3_s2,
        )?;
        for node in 0..nodes {
            write!(output, ",{}", network.pressure(node))?;
        }
        for branch in 0..branches {
            write!(output, ",{}", network.branch_flow(branch))?;
        }
        writeln!(output)?;
    }
    output.flush()?;
    Ok(())
}

fn write_grid<const N: usize>(
    path: &Path,
    rows: impl Iterator<Item = (GridSample, [f64; N])>,
    columns: &str,
) -> Result<(), Box<dyn Error>> {
    let mut output = BufWriter::new(File::create_new(path)?);
    writeln!(
        output,
        "index,region,inner_x_cm,inner_y_cm,outer_x_cm,outer_y_cm,mid_x_cm,mid_y_cm,ray_cm{columns}"
    )?;
    for (index, (sample, extras)) in rows.enumerate() {
        let values = [
            sample.inner.x,
            sample.inner.y,
            sample.outer.x,
            sample.outer.y,
            sample.mid.x,
            sample.mid.y,
            sample.gap_cm,
        ]
        .into_iter()
        .chain(extras);
        if !values.clone().all(f64::is_finite) {
            return Err(format!("測定線 {index} の計測値が非有限です").into());
        }
        write!(output, "{index},{}", sample.region as u8)?;
        for value in values {
            write!(output, ",{value}")?;
        }
        writeln!(output)?;
    }
    output.flush()?;
    Ok(())
}
