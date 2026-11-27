//! 制御フレームごとに形状から確定した断面までを観測する。

use super::Simulation;
use serde::Deserialize;
use std::error::Error;
use std::fs::File;
use std::io::{BufWriter, Write};
use std::num::NonZeroUsize;
use std::path::Path;
use vocal_core::airway::human::HumanAirway;
use vocal_core::airway::tract_control::{HumanTractControl, TractTargets};
use vocal_core::articulators::ArticulatorBank;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Settings {
    pub(super) project_contacts: bool,
    pub(super) oral_cells: Option<NonZeroUsize>,
    #[serde(default)]
    pub(super) acoustics: bool,
}

pub(super) fn render(
    simulation: Simulation,
    sample_rate_hz: u32,
    settings: Settings,
    path: &Path,
) -> Result<(), Box<dyn Error>> {
    if settings.acoustics {
        return render_acoustics(simulation, sample_rate_hz, settings.project_contacts, path);
    }
    let mut control = HumanTractControl::with_oral_cells(
        sample_rate_hz,
        simulation.body,
        simulation.bank.posture(),
        simulation.oral_cells,
    )?;
    let mut out = BufWriter::new(File::create_new(path)?);
    writeln!(
        out,
        concat!(
            "frame,pass,tube,cell,raw_area_cm2,raw_minimum_cm2,area_cm2,minimum_cm2,",
            "anatomical_length_cm,simulation_length_cm,teeth_s_cm,lip_cell,",
            "tip_distance_cm,body_distance_cm,velum_cm2",
        )
    )?;
    write_pass(&mut out, -1, "seed", control.targets())?;
    let dt = simulation.dt;
    simulation.run_frames(|frame, bank| {
        update_geometry(
            &mut control,
            bank,
            dt,
            settings.project_contacts,
            |pass, targets| write_pass(&mut out, frame as i64, pass, targets),
        )
    })?;
    out.flush()?;
    Ok(())
}

fn update_geometry(
    control: &mut HumanTractControl,
    bank: &mut ArticulatorBank,
    dt: f64,
    project_contacts: bool,
    mut observe: impl FnMut(&str, &TractTargets) -> std::io::Result<()>,
) -> Result<(), Box<dyn Error>> {
    let targets = control.apply(bank.posture(), dt)?;
    observe("apply", targets)?;
    if project_contacts
        && bank.enforce_tongue_contacts(
            targets.tip_contact,
            targets.body_contact,
            targets.body_scale(),
        )
    {
        let targets = control.reapply(bank.posture())?;
        observe("reapply", targets)?;
    }
    Ok(())
}

fn render_acoustics(
    simulation: Simulation,
    sample_rate_hz: u32,
    project_contacts: bool,
    path: &Path,
) -> Result<(), Box<dyn Error>> {
    let mut control = HumanTractControl::with_oral_cells(
        sample_rate_hz,
        simulation.body,
        simulation.bank.posture(),
        simulation.oral_cells,
    )?;
    let mut airway = HumanAirway::from_targets(sample_rate_hz, control.targets())?;
    let mut out = BufWriter::new(File::create_new(path)?);
    writeln!(
        out,
        concat!(
            "sample,pharynx_area_cm2,pharynx_minimum_cm2,pharynx_dx_cm,",
            "oral_center_area_cm2,oral_center_minimum_cm2,oral_dx_cm,",
            "lips_area_cm2,lips_minimum_cm2,constriction_minimum_cm2,velum_area_cm2,",
            "pressure_pharynx,pressure_junction,pressure_oral_center,pressure_lips,pressure_nose,",
            "flow_center_in,flow_center_out,flow_wall_center,flow_velum,flow_lips,flow_nose,",
            "radiation_derivative",
        )
    )?;
    let (block, dt) = (simulation.block, simulation.dt);
    let oral_tube = &airway.tubes[2];
    let center = oral_tube.nodes.len() / 2 - 1;
    let oral = oral_tube.nodes.start + center;
    let constriction = oral_tube.nodes.start + 2 * oral_tube.nodes.len() / 3 - 1;
    let first_branch = oral_tube.branches.start;
    let ph = airway.pharynx_entry;
    let junction = airway.pharynx_end;
    let lips = airway.lips;
    let nose = airway.nostrils;
    let velum = airway.velum_port;
    simulation.run_frames(|frame, bank| {
        update_geometry(&mut control, bank, dt, project_contacts, |_, _| Ok(()))?;
        airway.begin_tract_block(control.targets(), block)?;
        let net = &mut airway.network;
        for offset in 0..block {
            let sample = frame * block + offset;
            let acoustics = net.step(ph, 0.0);
            let pharynx = net.section(ph);
            let center_section = net.section(oral);
            write!(out, "{sample}")?;
            for value in [
                pharynx.area_cm2,
                pharynx.minimum_area_cm2,
                pharynx.length_cm,
                center_section.area_cm2,
                center_section.minimum_area_cm2,
                center_section.length_cm,
                net.area(lips),
                net.minimum_area(lips),
                net.minimum_area(constriction),
                net.port_area(velum).expect("軟口蓋ポート"),
                net.pressure(ph),
                net.pressure(junction),
                net.pressure(oral),
                net.pressure(lips),
                net.pressure(nose),
                net.branch_flow(first_branch + center - 1),
                net.branch_flow(first_branch + center),
                net.wall_motion(oral).flow_cm3_s,
                net.branch_flow(velum),
                net.radiation_flow(lips).expect("口端放射"),
                net.radiation_flow(nose).expect("鼻端放射"),
                acoustics.radiation_flow_derivative_cm3_s2,
            ] {
                write!(out, ",{value}")?;
            }
            writeln!(out)?;
        }
        Ok(())
    })?;
    out.flush()?;
    Ok(())
}

fn write_pass(
    out: &mut impl Write,
    frame: i64,
    pass: &str,
    targets: &TractTargets,
) -> std::io::Result<()> {
    for (tube, raw, limited, length) in [
        (
            "pharynx",
            &targets.raw.pharynx,
            &targets.limited.pharynx,
            targets.pharynx_simulation_length_cm,
        ),
        (
            "oral",
            &targets.raw.oral,
            &targets.limited.oral,
            targets.oral_simulation_length_cm,
        ),
    ] {
        for (cell, (raw_cell, limited_cell)) in raw.cells.iter().zip(&limited.cells).enumerate() {
            let lip = u8::from(tube == "oral" && cell >= targets.lips_from);
            writeln!(
                out,
                "{frame},{pass},{tube},{cell},{},{},{},{},{},{length},{},{lip},{},{},{}",
                raw_cell.area_cm2,
                raw_cell.minimum_area_cm2,
                limited_cell.area_cm2,
                limited_cell.minimum_area_cm2,
                raw.length_cm,
                targets.teeth_s_cm,
                targets.tip_contact.distance_cm,
                targets.body_contact.distance_cm,
                targets.velum_cm2,
            )?;
        }
    }
    Ok(())
}
