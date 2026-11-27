//! 調音を進める発声ケースのPCMと内部サンプルを保存する。

use super::{FrameChanges, PressureOverride, Simulation, VoiceSettings};
use crate::network_case::{Destination, pcm};
use serde_json::{Value, json};
use std::error::Error;
use std::fs::File;
use std::io::{BufWriter, Write};
use std::iter::Peekable;
use std::path::Path;
use vocal_core::articulators::Articulator;
use vocal_core::output::OutputStage;
use vocal_core::voice::{ArticulatedVoice, VoiceSample};

struct Render {
    voice: ArticulatedVoice,
    events: Peekable<std::vec::IntoIter<FrameChanges>>,
    sample: usize,
    block: usize,
    count: usize,
    pressure_override: Option<PressureOverride>,
    observe_pressure: bool,
}

impl Render {
    fn new(
        simulation: Simulation,
        internal_rate_hz: u32,
        project_contacts: bool,
        settings: VoiceSettings,
    ) -> Result<(Self, OutputStage), &'static str> {
        let stage = settings.output_stage(internal_rate_hz)?;
        if !simulation.block.is_multiple_of(stage.factor()) {
            return Err("調音周期は間引き率の整数倍にしてください");
        }
        let voice = ArticulatedVoice::for_tract(
            internal_rate_hz,
            simulation.block,
            simulation.bank,
            simulation.base_weight,
            project_contacts,
            settings.source(Some(simulation.body.default_f0_hz()))?,
            (simulation.body, simulation.oral_cells),
        )?;
        Ok((
            Self {
                voice,
                events: simulation.events.into_iter().peekable(),
                sample: 0,
                block: simulation.block,
                count: simulation.block * simulation.frames,
                pressure_override: simulation.pressure_override,
                observe_pressure: simulation.observe_pressure,
            },
            stage,
        ))
    }

    fn apply_event(&mut self) -> Result<bool, &'static str> {
        if self.sample.is_multiple_of(self.block)
            && self
                .events
                .peek()
                .is_some_and(|event| event.frame == self.sample / self.block)
        {
            let event = self.events.next().expect("このフレームのイベント");
            if let Some(gate) = event.gate {
                self.voice.set_performer_gate(gate)?;
            }
            if let Some(f0_hz) = event.f0_hz {
                self.voice.set_base_pitch(f0_hz)?;
            }
            let body = event.body;
            let (bank, blend) = self.voice.control_inputs();
            event.apply(bank, blend)?;
            if let Some(body) = body {
                self.voice.switch_manual_body(body)?;
                return Ok(true);
            }
        }
        Ok(false)
    }

    fn advance(&mut self) -> Result<VoiceSample, &'static str> {
        let pressure = self.pressure_override.as_ref().and_then(|input| {
            let offset = self.sample.checked_sub(input.start_sample)?;
            input.values_dyn_cm2.get(offset).copied()
        });
        let value = self.voice.step_with_glottal_pressure(pressure)?;
        self.sample += 1;
        Ok(value)
    }

    fn trace(mut self, path: &Path, observed_oral_cells: &[usize]) -> Result<(), Box<dyn Error>> {
        let oral_count = self.voice.airway().tubes[2].nodes.len();
        if observed_oral_cells
            .iter()
            .enumerate()
            .any(|(i, cell)| *cell >= oral_count || observed_oral_cells[..i].contains(cell))
        {
            return Err("計測する口腔セルは有効な番号を重複なしで指定してください".into());
        }
        let mut out = BufWriter::new(File::create_new(path)?);
        write!(
            out,
            concat!(
                "internal_sample,control_frame,jaw_cm,tongue_tip_y_cm,",
                "pharynx_dx_cm,oral_dx_cm,oral_area_cm2,oral_minimum_cm2,velum_area_cm2,",
                "gate,lung_boundary_dyn_cm2,pressure_sub_dyn_cm2,pressure_supra_dyn_cm2,",
                "glottal_area_cm2,glottal_flow_cm3_s,glottal_phase,glottal_voicing,glottal_f0_hz,",
                "velum_flow_cm3_s,lip_flow_cm3_s,nose_flow_cm3_s,radiation_derivative_cm3_s2,",
                "tongue_body_x_cm,tongue_body_y_cm,lip_aperture_cm,lip_minimum_cm2",
            )
        )?;
        if !observed_oral_cells.is_empty() {
            write!(
                out,
                ",labiodental,lip_pressure_dyn_cm2,wall_radiation_cm3_s"
            )?;
            for cell in observed_oral_cells {
                write!(
                    out,
                    ",oral_{cell}_applied_area_cm2,oral_{cell}_applied_minimum_cm2,oral_{cell}_pressure_dyn_cm2"
                )?;
            }
        }
        if self.observe_pressure {
            write!(
                out,
                ",glottal_physical_pressure_dyn_cm2,glottal_input_pressure_dyn_cm2,glottal_filtered_pressure_dyn_cm2,glottal_effort,glottal_abduction_cm2,glottal_closure_command"
            )?;
        }
        writeln!(out)?;
        for index in 0..self.count {
            self.apply_event()?;
            let s = self.advance()?;
            let airway = self.voice.airway();
            let net = &airway.network;
            let ph = airway.pharynx_entry;
            let oral_tube = &airway.tubes[2];
            let oral = oral_tube.nodes.start + oral_tube.nodes.len() / 2 - 1;
            let velum = airway.velum_port;
            let center = net.section(oral);
            let bank = self.voice.articulators();
            write!(out, "{index},{}", index / self.block)?;
            for value in [
                bank.state(Articulator::Jaw).position,
                bank.state(Articulator::TongueTipY).position,
                net.section(ph).length_cm,
                center.length_cm,
                center.area_cm2,
                center.minimum_area_cm2,
                net.port_area(velum).expect("軟口蓋ポート"),
                s.breath.gate,
                s.breath.boundary_pressure_dyn_cm2,
                s.subglottal_pressure_dyn_cm2,
                s.supraglottal_pressure_dyn_cm2,
                s.glottis.area_cm2,
                s.glottal_flow_cm3_s,
                s.glottis.phase,
                s.glottis.voicing,
                s.glottis.f0_hz,
                net.branch_flow(velum),
                s.lip_flow_cm3_s,
                s.nose_flow_cm3_s,
                s.radiation.radiation_flow_derivative_cm3_s2,
                bank.state(Articulator::TongueBodyX).position,
                bank.state(Articulator::TongueBodyY).position,
                bank.state(Articulator::LipAperture).position,
                net.section(self.voice.airway().lips).minimum_area_cm2,
            ] {
                write!(out, ",{value}")?;
            }
            if !observed_oral_cells.is_empty() {
                write!(
                    out,
                    ",{},{},{}",
                    bank.state(Articulator::Labiodental).position,
                    net.pressure(airway.lips),
                    s.radiation.wall_radiation_flow_cm3_s
                )?;
                for &cell in observed_oral_cells {
                    if cell >= oral_tube.nodes.len() {
                        return Err("体型変更後の口腔セル数を計測設定に照合してください".into());
                    }
                    let node = oral_tube.nodes.start + cell;
                    let section = net.section(node);
                    write!(
                        out,
                        ",{},{},{}",
                        section.area_cm2,
                        section.minimum_area_cm2,
                        net.pressure(node)
                    )?;
                }
            }
            if self.observe_pressure {
                write!(
                    out,
                    ",{},{},{},{},{},{}",
                    s.glottal_physical_pressure_dyn_cm2,
                    s.glottal_input_pressure_dyn_cm2,
                    s.glottis.filtered_pressure_drop_dyn_cm2,
                    s.breath.effort,
                    s.abduction_cm2,
                    s.glottis.closure_command
                )?;
            }
            writeln!(out)?;
        }
        out.flush()?;
        Ok(())
    }
}

pub(super) fn inspect(
    simulation: Simulation,
    internal_rate_hz: u32,
    project_contacts: bool,
    settings: VoiceSettings,
) -> Result<Value, &'static str> {
    let (render, stage) = Render::new(simulation, internal_rate_hz, project_contacts, settings)?;
    Ok(json!({
        "sample_rate_hz": settings.output_sample_rate_hz,
        "frames": render.count / stage.factor(),
        "decimation_factor": stage.factor(),
        "control_block_internal_samples": render.block,
        "filter_coefficients": stage.coefficients(),
    }))
}

pub(super) fn render(
    simulation: Simulation,
    internal_rate_hz: u32,
    project_contacts: bool,
    settings: VoiceSettings,
    destination: Destination<'_>,
    observed_oral_cells: &[usize],
) -> Result<(), Box<dyn Error>> {
    let (mut render, mut stage) =
        Render::new(simulation, internal_rate_hz, project_contacts, settings)?;
    let count = render.count;
    let factor = stage.factor();
    match destination {
        Destination::Trace(path) => render.trace(path, observed_oral_cells),
        Destination::Pcm {
            wave,
            trace,
            block_frames,
        } => pcm::write_frames(
            || {
                if render.apply_event()? {
                    stage.reset();
                }
                stage
                    .render_frame(|| {
                        render
                            .advance()
                            .map(|sample| (sample.radiation.radiation_flow_derivative_cm3_s2, ()))
                    })
                    .map(|(frame, ())| frame)
            },
            settings.output_sample_rate_hz,
            count / factor,
            factor,
            block_frames,
            wave,
            trace,
        ),
        Destination::Inspect => unreachable!(),
    }
}
