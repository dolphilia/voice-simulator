//! 研究版の発話状態を固定し、音響セルと線形応答を保存する。

use crate::tsp_transfer_request::TransferRequest;
use serde_json::json;
use std::{error::Error, fs};
use vocal_core::voice::ArticulatedVoice;

pub fn options(args: &[String]) -> Result<((TransferRequest, &str), &[String]), Box<dyn Error>> {
    let [original @ .., requested, output] = args else {
        return Err("計測条件と断面の出力先を指定してください".into());
    };
    Ok(((TransferRequest::read(requested)?, output), original))
}

pub fn write(voice: &ArticulatedVoice, request: &TransferRequest, output: &str) -> Result<(), Box<dyn Error>> {
    let airway = voice.airway();
    let network = &airway.network;
    let el = network.linear_elements();
    let inject = airway.pharynx_entry;
    let cut = airway.glottis_port;
    let lips = airway.lips;
    let nose = airway.nostrils;
    let response = el.transfer(inject, &[cut], &request.frequencies)?;
    let nodes: Vec<_> = el.nodes.iter().map(|node| {
        let wall = node.wall.map_or([0.0; 5], |wall| {
            let p = wall.parameters;
            [wall.area_cm2, p.mass_g_cm2, p.resistance_dyn_s_cm3, p.stiffness_dyn_cm3, p.radiation_fraction]
        });
        let [inertance, resistance] = node.radiation.unwrap_or([0.0; 2]);
        json!([node.compliance, u8::from(node.fixed_pressure), wall[0], wall[1], wall[2], wall[3],
               wall[4], inertance, resistance])
    }).collect();
    let branches: Vec<_> = el.branches.iter().map(|branch| json!([
        branch.nodes[0], branch.nodes[1], u8::from(branch.open), branch.inertance, branch.resistance
    ])).collect();
    let [pharynx, _] = airway.tract_section_counts();
    let sections: Vec<_> = airway.tract_sections().enumerate().map(|(i, cell)| {
        let (name, index) = if i < pharynx { ("pharynx", i) } else { ("oral", i - pharynx) };
        json!([name, index, cell.length_cm, cell.area_cm2, cell.minimum_area_cm2])
    }).collect();
    let magnitude: Vec<_> = response.iter().map(|point| point.total.magnitude()).collect();
    let complex: Vec<_> = response.iter().map(|point| [point.total.real, point.total.imaginary]).collect();
    let snapshot = json!({"completed_frames": request.completed_frames, "sections": sections, "nodes": nodes,
                          "branches": branches, "inject": inject, "cut": el.branches[cut].nodes,
                          "lips": lips, "nose": nose, "velum_cm2": network.port_area(airway.velum_port),
                          "frequencies_hz": request.frequencies, "magnitude": magnitude, "complex": complex});
    fs::write(output, serde_json::to_vec(&snapshot)?)?;
    Ok(())
}
