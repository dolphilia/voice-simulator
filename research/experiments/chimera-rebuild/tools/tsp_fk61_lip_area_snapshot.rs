//! 口端セルに入る測定線、口端の目標値、気道の現在値を記録する。

use serde_json::{Value, json};
use std::error::Error;

#[cfg(lip_upstream)]
use chimera::voice::human_voice::HumanVoice as Voice;
#[cfg(not(lip_upstream))]
use vocal_core::voice::ArticulatedVoice as Voice;

pub fn write(voice: &Voice, completed: usize, requested: &[usize]) -> Result<(), Box<dyn Error>> {
    if requested.contains(&completed) {
        println!("{}", json!({"completed_frames": completed, "tract": snapshot(voice)?}));
    }
    Ok(())
}

#[cfg(lip_upstream)]
fn snapshot(voice: &Voice) -> Result<Value, Box<dyn Error>> {
    let airway = &voice.airway;
    let frame = airway.frame.as_ref().ok_or("断面のフレームがありません")?;
    let grid: Vec<_> = frame.grid.iter().map(|g| [
        g.s, g.area, f64::from(g.region), g.ray, g.d,
        g.inner.x, g.inner.y, g.outer.x, g.outer.y, g.mid.x, g.mid.y,
    ]).collect();
    let n = airway.oral.last_node();
    let net = &airway.net;
    let end = airway.or_areas.len() - 1;
    Ok(json!({
        "grid": grid, "origin_cm": frame.pharynx_length, "end_cm": frame.lip_s, "oral_cells": end + 1,
        "raw": airway.probe_lip_raw, "limited": [airway.or_areas[end], airway.or_min[end]],
        "target": net.probe_lip_target(n), "current": [net.area[n], net.amin[n], net.dx[n]],
        "area_inputs": airway.probe_lip_area_inputs(&voice.artic.x),
    }))
}

#[cfg(not(lip_upstream))]
fn snapshot(voice: &Voice) -> Result<Value, Box<dyn Error>> {
    let (targets, area_inputs) = voice.probe_lip_geometry();
    let grid: Vec<_> = voice.tract_area_samples().iter().map(|sample| {
        let g = &sample.contact.ray;
        [sample.s_cm, sample.area_cm2, f64::from(g.region as u8), g.gap_cm, sample.contact.gap_cm,
            g.inner.x, g.inner.y, g.outer.x, g.outer.y, g.mid.x, g.mid.y]
    }).collect();
    let last = grid.last().ok_or("断面の測定線がありません")?;
    let raw = targets.raw.oral.cells.last().ok_or("口腔セルがありません")?;
    let limited = targets.limited.oral.cells.last().ok_or("口腔セルがありません")?;
    let airway = voice.airway();
    let current = airway.network.section(airway.lips);
    Ok(json!({
        "grid": grid, "origin_cm": targets.raw.pharynx.length_cm, "end_cm": last[0],
        "oral_cells": targets.raw.oral.cells.len(), "raw": [raw.area_cm2, raw.minimum_area_cm2],
        "limited": [limited.area_cm2, limited.minimum_area_cm2], "target": airway.probe_lip_target(),
        "current": [current.area_cm2, current.minimum_area_cm2, current.length_cm], "area_inputs": area_inputs,
    }))
}
