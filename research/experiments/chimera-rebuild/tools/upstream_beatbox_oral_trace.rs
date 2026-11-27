//! 固定上流の口腔セルを出力フレーム末尾で観測する。

use chimera::{
    anatomy::human::ArticKey,
    voice::{human_airway::HumanAirway, human_voice::HumanVoice},
};
use std::io::{self, Write};

pub fn header(trace: &mut impl Write, voice: &HumanVoice) -> io::Result<()> {
    let tube = &voice.airway.oral;
    write!(trace, ",dorsum")?;
    for cell in 0..=tube.last_node() - tube.first_node() {
        write!(
            trace,
            ",oral_cell_{cell}_minimum_cm2,oral_cell_{cell}_pressure_dyn_cm2,oral_cell_{cell}_volume_cm3"
        )?;
    }
    Ok(())
}

pub fn row(trace: &mut impl Write, voice: &HumanVoice) -> io::Result<()> {
    let airway = &voice.airway;
    let net = &airway.net;
    write!(trace, ",{}", voice.artic.x.get(ArticKey::Dorsum))?;
    for node in airway.oral.first_node()..=airway.oral.last_node() {
        write!(
            trace,
            ",{},{},{}",
            net.amin[node],
            net.p[node],
            net.area[node] * net.dx[node]
        )?;
    }
    Ok(())
}

pub fn minima_header(trace: &mut impl Write, voice: &HumanVoice) -> io::Result<()> {
    for cell in 0..voice.airway.oral.n {
        write!(trace, ",oral_cell_{cell}_minimum_cm2")?;
    }
    Ok(())
}

pub fn minima_row(trace: &mut impl Write, voice: &HumanVoice) -> io::Result<()> {
    let airway = &voice.airway;
    for node in airway.oral.first_node()..=airway.oral.last_node() {
        write!(trace, ",{}", airway.net.amin[node])?;
    }
    Ok(())
}

pub fn constriction_noise_tract_cell(airway: &HumanAirway) -> isize {
    let Some(source) = airway.net.noise_sources().get(1) else {
        return -1;
    };
    let mut offset = 0;
    for tube in [airway.pharynx, airway.oral] {
        let first = tube.branch(0);
        if (first..first + tube.n - 1).contains(&source.src) {
            return (offset + source.src - first) as isize;
        }
        offset += tube.n;
    }
    -1
}

pub fn nasal_header(trace: &mut impl Write) -> io::Result<()> {
    write!(
        trace,
        ",velum_position_cm2,velum_effective_cm2,velum_port_area_cm2,velum_flow_cm3_s,smoothed_f0_hz"
    )
}

pub fn nasal_row(trace: &mut impl Write, voice: &HumanVoice) -> io::Result<()> {
    let airway = &voice.airway;
    let port = airway.velum_port;
    write!(
        trace,
        ",{},{},{},{},{}",
        voice.artic.x.get(ArticKey::Velum),
        voice.artic.effective.get(ArticKey::Velum),
        airway.net.port_area[port],
        airway.net.u[port],
        voice.glottis.params.f0,
    )
}
