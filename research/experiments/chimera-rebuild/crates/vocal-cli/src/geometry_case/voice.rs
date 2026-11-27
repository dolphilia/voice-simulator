//! 固定母音の波形と、出力フレーム時刻に対応する気道の観測値。

use super::FixedAirwaySettings;
use crate::network_case::{Destination, pcm};
use serde::Deserialize;
use serde_json::{Value, json};
use std::error::Error;
use std::fs::File;
use std::io::{BufWriter, Write};
use vocal_core::airway::human::HumanAirway;
use vocal_core::output::OutputStage;
use vocal_core::voice::{FixedVoice, FixedVoiceSettings};

#[derive(Clone, Copy, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Settings {
    pressure_cm_h2o: f64,
    gate: f64,
    f0_hz: Option<f64>,
    breathiness: f64,
    tension: f64,
    pub(crate) output_sample_rate_hz: u32,
    output_gain: f64,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct GateEvent {
    frame: usize,
    goal: f64,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Probe {
    #[serde(default)]
    internal_trace: bool,
    #[serde(default)]
    pharynx_entry_balance: bool,
    #[serde(default)]
    radiation_components: bool,
    #[serde(default)]
    velum_port: bool,
    network_trace_range: Option<[usize; 2]>,
    pub(super) velum_area_override_cm2: Option<f64>,
    prescribed_flow_cm3_s: Option<Vec<String>>,
}

fn network_trace_range(
    probe: Option<&Probe>,
    sample_count: usize,
) -> Result<Option<[usize; 2]>, &'static str> {
    let Some(probe) = probe else {
        return Ok(None);
    };
    if let Some([start, end]) = probe.network_trace_range
        && (!probe.internal_trace || start >= end || end > sample_count)
    {
        return Err("気道全体の観測には内部サンプルの指定と有効な半開区間が必要です");
    }
    Ok(probe.network_trace_range)
}

fn prescribed_flow(
    probe: Option<&Probe>,
    sample_count: usize,
) -> Result<Option<Vec<f64>>, &'static str> {
    let Some(values) = probe.and_then(|probe| probe.prescribed_flow_cm3_s.as_ref()) else {
        return Ok(None);
    };
    if values.len() != sample_count {
        return Err("指定する声門流量の点数は内部サンプル数に合わせてください");
    }
    // 逐次再入力では観測CSVの10進表記を同じ f64 に戻す。
    values
        .iter()
        .map(|value| {
            value
                .parse::<f64>()
                .ok()
                .filter(|value| value.is_finite())
                .ok_or("指定する声門流量には有限の10進数文字列が必要です")
        })
        .collect::<Result<Vec<_>, _>>()
        .map(Some)
}

fn validate_events(events: &[GateEvent], frames: usize) -> Result<(), &'static str> {
    if events
        .iter()
        .any(|e| e.frame >= frames || !(0.0..=1.5).contains(&e.goal))
        || events.windows(2).any(|pair| pair[0].frame >= pair[1].frame)
    {
        return Err("呼気イベントには範囲内で重複しない昇順の出力フレームと0〜1.5の目標が必要です");
    }
    Ok(())
}

impl Settings {
    pub(crate) fn output_stage(self, internal_rate_hz: u32) -> Result<OutputStage, &'static str> {
        OutputStage::new(
            internal_rate_hz,
            self.output_sample_rate_hz,
            self.output_gain,
        )
    }

    pub(crate) fn source(
        self,
        body_f0_hz: Option<f64>,
    ) -> Result<FixedVoiceSettings, &'static str> {
        Ok(FixedVoiceSettings {
            pressure_cm_h2o: self.pressure_cm_h2o,
            gate: self.gate,
            f0_hz: self
                .f0_hz
                .or(body_f0_hz)
                .ok_or("発声には基準音高を指定してください")?,
            breathiness: self.breathiness,
            tension: self.tension,
        })
    }

    fn build(
        self,
        fixed: FixedAirwaySettings,
        airway: HumanAirway,
        body_f0_hz: f64,
    ) -> Result<(FixedVoice, OutputStage), &'static str> {
        let stage = self.output_stage(fixed.sample_rate_hz)?;
        if fixed.impulse_volume_cm3 != 0.0
            || !fixed.sample_count.get().is_multiple_of(stage.factor())
        {
            return Err(
                "母音発声にはインパルスを0、内部サンプル数を間引き率の整数倍にしてください",
            );
        }
        let voice = FixedVoice::new(
            airway,
            fixed.sample_rate_hz,
            64 * stage.factor(),
            self.source(Some(body_f0_hz))?,
        )?;
        Ok((voice, stage))
    }

    pub(super) fn inspect(
        self,
        fixed: FixedAirwaySettings,
        airway: HumanAirway,
        body_f0_hz: f64,
        events: &[GateEvent],
        probe: Option<&Probe>,
    ) -> Result<Value, &'static str> {
        let (_, stage) = self.build(fixed, airway, body_f0_hz)?;
        validate_events(events, fixed.sample_count.get() / stage.factor())?;
        let network_range = network_trace_range(probe, fixed.sample_count.get())?;
        let mut report = json!({
            "sample_rate_hz":self.output_sample_rate_hz,
            "frames":fixed.sample_count.get() / stage.factor(),
            "decimation_factor":stage.factor(),
            "control_block_internal_samples":64 * stage.factor(),
            "filter_coefficients": stage.coefficients(),
        });
        if let Some(probe) = probe {
            let forcing = prescribed_flow(Some(probe), fixed.sample_count.get())?.is_some();
            report["probe"] = json!({
                "internal_trace": probe.internal_trace,
                "prescribed_glottal_flow": forcing,
                "glottal_area_drives_port": !forcing
            });
            if probe.pharynx_entry_balance {
                report["probe"]["pharynx_entry_balance"] = json!(true);
            }
            if probe.radiation_components {
                report["probe"]["radiation_components"] = json!(true);
            }
            if probe.velum_port {
                report["probe"]["velum_port"] = json!(true);
            }
            if let Some(range) = network_range {
                report["probe"]["network_trace_range"] = json!(range);
            }
            if let Some(area) = probe.velum_area_override_cm2 {
                report["probe"]["velum_area_override_cm2"] = json!(area);
            }
        }
        Ok(report)
    }

    pub(super) fn render(
        self,
        fixed: FixedAirwaySettings,
        airway: HumanAirway,
        body_f0_hz: f64,
        events: &[GateEvent],
        probe: Option<&Probe>,
        destination: Destination<'_>,
    ) -> Result<(), Box<dyn Error>> {
        let (mut voice, stage) = self.build(fixed, airway, body_f0_hz)?;
        let factor = stage.factor();
        validate_events(events, fixed.sample_count.get() / factor)?;
        let flow = prescribed_flow(probe, fixed.sample_count.get())?;
        let network_range = network_trace_range(probe, fixed.sample_count.get())?;
        let mut events = events.iter().peekable();
        let mut sample_index = 0;
        let mut next_sample = |voice: &mut FixedVoice| {
            if let Some(event) = events.next_if(|event| event.frame * factor == sample_index) {
                voice.set_performer_gate(event.goal)?;
            }
            let sample = match &flow {
                Some(flow) => voice.step_with_prescribed_glottal_flow(flow[sample_index]),
                None => voice.step(),
            };
            sample_index += 1;
            sample
        };
        match destination {
            Destination::Pcm {
                wave,
                trace,
                block_frames,
            } => pcm::write(
                || {
                    next_sample(&mut voice)
                        .map(|sample| sample.radiation.radiation_flow_derivative_cm3_s2)
                },
                stage,
                self.output_sample_rate_hz,
                fixed.sample_count.get(),
                block_frames,
                wave,
                trace,
            ),
            Destination::Trace(path) => {
                let hop = if probe.is_some_and(|probe| probe.internal_trace) {
                    1
                } else {
                    factor
                };
                let mut out = BufWriter::new(File::create_new(path)?);
                let pharynx_balance = probe.is_some_and(|probe| probe.pharynx_entry_balance);
                let radiation_components = probe.is_some_and(|probe| probe.radiation_components);
                let velum_port = probe.is_some_and(|probe| probe.velum_port);
                write!(
                    out,
                    concat!(
                        "frame,internal_sample,gate,lung_boundary_dyn_cm2,pressure_sub_dyn_cm2,pressure_supra_dyn_cm2,",
                        "glottal_area_cm2,glottal_flow_cm3_s,glottal_phase,glottal_voicing,glottal_f0_hz,",
                        "lip_flow_cm3_s,nose_flow_cm3_s,radiation_derivative_cm3_s2",
                    )
                )?;
                if pharynx_balance {
                    write!(
                        out,
                        concat!(
                            ",pharynx_next_pressure_dyn_cm2,pharynx_outflow_cm3_s,pharynx_wall_flow_cm3_s,",
                            "pharynx_volume_source_cm3_s,pharynx_area_cm2,pharynx_length_cm,pharynx_compliance_cgs",
                        )
                    )?;
                }
                if radiation_components {
                    write!(out, ",wall_radiation_flow_cm3_s,radiation_flow_cm3_s")?;
                }
                if velum_port {
                    write!(
                        out,
                        ",velum_area_cm2,velum_flow_cm3_s,velum_pharynx_pressure_dyn_cm2,velum_nasal_pressure_dyn_cm2"
                    )?;
                }
                let node_count = voice
                    .airway()
                    .tubes
                    .iter()
                    .map(|tube| tube.nodes.len())
                    .sum();
                let branch_count = voice.airway().network.branch_count();
                if network_range.is_some() {
                    for node in 0..node_count {
                        write!(out, ",node_{node}_pressure_dyn_cm2")?;
                    }
                    for branch in 0..branch_count {
                        write!(out, ",branch_{branch}_flow_cm3_s")?;
                    }
                }
                writeln!(out)?;
                let end_frame =
                    network_range.map_or(fixed.sample_count.get() / hop, |[_, end]| end);
                for frame in 0..end_frame {
                    for _ in 1..hop {
                        next_sample(&mut voice)?;
                    }
                    let s = next_sample(&mut voice)?;
                    let index = (frame + 1) * hop - 1;
                    if network_range.is_some_and(|[start, _]| index < start) {
                        continue;
                    }
                    write!(
                        out,
                        "{frame},{index},{},{},{},{},{},{},{},{},{},{},{},{}",
                        s.breath.gate,
                        s.breath.boundary_pressure_dyn_cm2,
                        s.subglottal_pressure_dyn_cm2,
                        s.supraglottal_pressure_dyn_cm2,
                        s.glottis.area_cm2,
                        s.glottal_flow_cm3_s,
                        s.glottis.phase,
                        s.glottis.voicing,
                        s.glottis.f0_hz,
                        s.lip_flow_cm3_s,
                        s.nose_flow_cm3_s,
                        s.radiation.radiation_flow_derivative_cm3_s2,
                    )?;
                    if pharynx_balance {
                        let airway = voice.airway();
                        let node = airway.pharynx_entry;
                        let net = &airway.network;
                        let section = net.section(node);
                        write!(
                            out,
                            ",{},{},{},{},{},{},{}",
                            net.pressure(node + 1),
                            net.branch_flow(airway.tubes[1].branches.start),
                            net.wall_motion(node).flow_cm3_s,
                            net.volume_source(node),
                            section.area_cm2,
                            section.length_cm,
                            net.compliance(node).effective,
                        )?;
                    }
                    if radiation_components {
                        write!(
                            out,
                            ",{},{}",
                            s.radiation.wall_radiation_flow_cm3_s, s.radiation.radiation_flow_cm3_s,
                        )?;
                    }
                    if velum_port {
                        let airway = voice.airway();
                        let net = &airway.network;
                        write!(
                            out,
                            ",{},{},{},{}",
                            net.branch_area(airway.velum_port),
                            net.branch_flow(airway.velum_port),
                            net.pressure(airway.pharynx_end),
                            net.pressure(airway.tubes[3].nodes.start),
                        )?;
                    }
                    if network_range.is_some() {
                        let net = &voice.airway().network;
                        for node in 0..node_count {
                            write!(out, ",{}", net.pressure(node))?;
                        }
                        for branch in 0..branch_count {
                            write!(out, ",{}", net.branch_flow(branch))?;
                        }
                    }
                    writeln!(out)?;
                }
                out.flush()?;
                Ok(())
            }
            Destination::Inspect => unreachable!(),
        }
    }
}
