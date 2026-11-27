//! 肺・声門と口鼻腔をつなぐ動物の気道。出典は notes/{seal-airway,alligator-fixed-voice,elephant-fixed-voice}.md。

use super::network::{AirwayNetwork, Boundaries, NoiseSpec, Port, Section};
use super::{AIR_DENSITY, SOUND_SPEED, WallParameters};
use crate::glottis::Glottis;
use serde::Serialize;

pub(super) struct MammalSpec {
    pub tubes: [(f64, f64); 4],
    pub coarse: f64,
    pub wall_radiation: f64,
    pub oral_tip_from: f64,
    pub oral_tip_area_cm2: f64,
    pub velum_area_cm2: f64,
    pub glottal_noise_gain: f64,
    pub oral_noise_gain: Option<f64>,
    pub trunk: Option<TrunkSpec>,
}

pub(super) struct TrunkSpec {
    pub length_cm: f64,
    pub base_area_cm2: f64,
    pub taper_cm2: f64,
    pub coarse: f64,
    pub max_cells: usize,
    pub perimeter_factor: f64,
}

const LUNG_CELL: Section = Section {
    length_cm: 1.0,
    area_cm2: 100.0,
    minimum_area_cm2: 100.0,
    perimeter_factor: 1.0,
    viscous_factor: 1.0,
    wall: None,
};
const TRACHEA_WALL: WallParameters = WallParameters {
    mass_g_cm2: 0.6,
    resistance_dyn_s_cm3: 1000.0,
    stiffness_dyn_cm3: 1.0e6,
    radiation_fraction: 0.0,
};
const SOFT_WALL: WallParameters = WallParameters {
    mass_g_cm2: 1.5,
    resistance_dyn_s_cm3: 1600.0,
    stiffness_dyn_cm3: 3.0e5,
    radiation_fraction: 0.0,
};
const NASAL_WALL: WallParameters = WallParameters {
    mass_g_cm2: 1.0,
    resistance_dyn_s_cm3: 3000.0,
    stiffness_dyn_cm3: 1.0e6,
    radiation_fraction: 0.0,
};

struct Tube {
    first: usize,
    count: usize,
    first_branch: usize,
}

impl Tube {
    fn last(&self) -> usize {
        self.first + self.count - 1
    }
}

struct Trunk {
    tube: Tube,
    valve: usize,
}

#[derive(Serialize)]
pub(super) struct TrunkGeometry {
    trunk_cells: usize,
    trunk_inlet_area_cm2: f64,
    trunk_tip_area_cm2: f64,
    trunk_valve_area_cm2: f64,
}

#[derive(Clone, Copy, Default)]
pub struct TrunkSample {
    pub nasal_base_pressure_dyn_cm2: f64,
    pub trunk_inlet_pressure_dyn_cm2: f64,
    pub trunk_tip_pressure_dyn_cm2: f64,
    pub trunk_valve_area_cm2: f64,
    pub trunk_valve_flow_cm3_s: f64,
}

#[derive(Serialize)]
pub struct MammalGeometry {
    pub trachea_cells: usize,
    pub pharynx_cells: usize,
    pub oral_cells: usize,
    pub nasal_cells: usize,
    pub oral_tip_area_cm2: f64,
    pub courant: f64,
}

#[derive(Clone, Copy, Default)]
pub struct MammalAirwaySample {
    pub lung_pressure_dyn_cm2: f64,
    pub lung_flow_cm3_s: f64,
    pub trachea_inlet_pressure_dyn_cm2: f64,
    pub trachea_end_pressure_dyn_cm2: f64,
    pub pharynx_pressure_dyn_cm2: f64,
    pub glottis_drive_dyn_cm2: f64,
    pub glottis_area_cm2: f64,
    pub glottis_flow_cm3_s: f64,
    pub glottis_voicing: f64,
    pub glottis_f0_hz: f64,
    pub glottis_phase: f64,
    pub velum_area_cm2: f64,
    pub velum_flow_cm3_s: f64,
    pub oral_tip_area_cm2: f64,
    pub wall_radiation_cm3_s: f64,
    pub oral_radiation_cm3_s: f64,
    pub nasal_radiation_cm3_s: f64,
    pub radiation_derivative_cm3_s2: f64,
    pub glottal_noise_level_dyn_cm2: f64,
    pub glottal_noise_pressure_dyn_cm2: f64,
    pub oral_noise_level_dyn_cm2: f64,
}

pub(super) struct MammalAirway {
    net: AirwayNetwork,
    glottis: Glottis,
    trachea: Tube,
    pharynx: Tube,
    oral: Tube,
    nasal: Tube,
    trunk: Option<Trunk>,
    lung: usize,
    lung_port: usize,
    glottis_port: usize,
    velum_port: usize,
    area_targets: Vec<[f64; 2]>,
    oral_tip_start: usize,
    glottal_noise: NoiseSpec,
    oral_noise_gain: Option<f64>,
    oral_noise_cell: Option<usize>,
}

impl MammalAirway {
    /// 初期制御の断面を使い、静止した気道を組み立てる。
    pub(super) fn new(
        rate_hz: u32,
        glottis: Glottis,
        spec: MammalSpec,
    ) -> Result<Self, &'static str> {
        let dx_min = SOUND_SPEED / f64::from(rate_hz) / 0.93;
        let mut sections = Vec::new();
        let mut connections = Vec::new();
        let soft_wall = WallParameters {
            radiation_fraction: spec.wall_radiation,
            ..SOFT_WALL
        };
        let tubes = [
            (spec.coarse.max(1.6), 60.0, 1.0, 1.0, TRACHEA_WALL),
            (spec.coarse, 120.0, 1.3, 1.0, soft_wall),
            (spec.coarse, 120.0, 1.5, 1.0, soft_wall),
            (spec.coarse, 120.0, 2.6, 2.0, NASAL_WALL),
        ];
        let [trachea, pharynx, oral, nasal] = std::array::from_fn(|tube_index| {
            let (length, area) = spec.tubes[tube_index];
            let (coarse, max, perimeter, viscosity, wall) = tubes[tube_index];
            let count = (length / (dx_min * coarse)).floor().clamp(3.0, max) as usize;
            let first = sections.len();
            let first_branch = connections.len();
            for index in 0..count {
                let center = (index as f64 + 0.5) / count as f64;
                let area = if tube_index == 2 && center > spec.oral_tip_from {
                    spec.oral_tip_area_cm2
                } else {
                    area
                };
                sections.push(Section {
                    length_cm: length / count as f64,
                    area_cm2: area,
                    minimum_area_cm2: area,
                    perimeter_factor: perimeter,
                    viscous_factor: viscosity,
                    wall: Some(wall),
                });
                if index > 0 {
                    connections.push([first + index - 1, first + index]);
                }
            }
            Tube {
                first,
                count,
                first_branch,
            }
        });
        let lung = sections.len();
        sections.push(LUNG_CELL);
        let trunk = spec.trunk.map(|spec| {
            let count = (spec.length_cm / (dx_min * spec.coarse))
                .floor()
                .clamp(3.0, spec.max_cells as f64) as usize;
            let first = sections.len();
            let first_branch = connections.len();
            for index in 0..count {
                let center = (index as f64 + 0.5) / count as f64;
                let area = spec.base_area_cm2 + spec.taper_cm2 * center;
                sections.push(Section {
                    length_cm: spec.length_cm / count as f64,
                    area_cm2: area,
                    minimum_area_cm2: area,
                    perimeter_factor: spec.perimeter_factor,
                    viscous_factor: 1.0,
                    wall: Some(NASAL_WALL),
                });
                if index > 0 {
                    connections.push([first + index - 1, first + index]);
                }
            }
            Tube {
                first,
                count,
                first_branch,
            }
        });
        connections.push([pharynx.last(), oral.first]);
        let port = |nodes, area_cm2, length_cm, entrance_loss, expansion_loss| Port {
            nodes,
            area_cm2,
            length_cm,
            entrance_loss,
            expansion_loss,
            slit_width_cm: 0.0,
            include_half_sections: true,
            extra_resistance: 0.0,
        };
        let trachea_area = spec.tubes[0].1;
        let mut ports = vec![
            Port {
                extra_resistance: 0.5 * AIR_DENSITY * SOUND_SPEED / trachea_area,
                ..port([lung, trachea.first], trachea_area, 1.0, 0.0, 0.0)
            },
            Port {
                slit_width_cm: trachea_area.sqrt() * 0.9,
                ..port([trachea.last(), pharynx.first], 0.0, 0.4, 0.37, 1.0)
            },
            port(
                [pharynx.last(), nasal.first],
                spec.velum_area_cm2,
                1.0,
                0.3,
                0.8,
            ),
        ];
        let nasal_radiator = trunk.as_ref().map_or(nasal.last(), Tube::last);
        let trunk = trunk.map(|tube| {
            let valve = connections.len() + ports.len();
            ports.push(port([nasal.last(), tube.first], 0.0, 0.6, 0.3, 1.0));
            Trunk { tube, valve }
        });
        let mut net = AirwayNetwork::new(
            rate_hz,
            &sections,
            &connections,
            Boundaries {
                radiation_nodes: &[oral.last(), nasal_radiator],
                fixed_pressure_nodes: &[lung],
                ports: &ports,
            },
        )?;
        net.reserve_noise_sources(1 + usize::from(spec.oral_noise_gain.is_some()));
        let lung_port = connections.len();
        let glottis_port = lung_port + 1;
        let glottal_noise = NoiseSpec {
            source: glottis_port,
            forward: pharynx.first_branch + 1,
            reverse: trachea.first_branch + trachea.count - 2,
            gain: spec.glottal_noise_gain,
            lowpass_hz: 4000.0,
            highpass_hz: 250.0,
        };
        let oral_tip_start = oral.first
            + (0..oral.count)
                .find(|&index| (index as f64 + 0.5) / oral.count as f64 > spec.oral_tip_from)
                .unwrap_or(oral.count);
        let mut airway = Self {
            net,
            glottis,
            trachea,
            pharynx,
            oral,
            nasal,
            trunk,
            lung,
            lung_port,
            glottis_port,
            velum_port: lung_port + 2,
            area_targets: sections
                .iter()
                .map(|section| [section.area_cm2; 2])
                .collect(),
            oral_tip_start,
            glottal_noise,
            oral_noise_gain: spec.oral_noise_gain,
            oral_noise_cell: None,
        };
        airway.update_noise()?;
        Ok(airway)
    }

    fn update_noise(&mut self) -> Result<(), &'static str> {
        // 口端セルを除き、最も細い断面が複数あれば上流側のものを選ぶ。
        let mut minimum = 2.0;
        let mut selected = None;
        if let Some(gain) = self.oral_noise_gain {
            for cell in 0..self.oral.count - 1 {
                let area = self.area_targets[self.oral.first + cell][0];
                if area > 0.0 && area < minimum {
                    minimum = area;
                    selected = Some((cell, gain));
                }
            }
        }
        let index = selected.map(|(cell, _)| cell);
        if index == self.oral_noise_cell && self.net.noise_spec(0).is_some() {
            return Ok(());
        }
        let mut sources = [self.glottal_noise; 2];
        let count = if let Some((cell, gain)) = selected {
            sources[1] = NoiseSpec {
                source: self.oral.first_branch + cell,
                forward: self.oral.first_branch + (cell + 1).min(self.oral.count - 2),
                reverse: self.oral.first_branch + cell.saturating_sub(1),
                gain,
                lowpass_hz: 5000.0,
                highpass_hz: 600.0,
            };
            2
        } else {
            1
        };
        self.net.set_noise_sources(&sources[..count])?;
        self.oral_noise_cell = index;
        Ok(())
    }

    pub(super) fn set_articulation(
        &mut self,
        oral_area_cm2: f64,
        velum_area_cm2: f64,
        samples: usize,
    ) -> Result<(), &'static str> {
        self.area_targets[self.oral_tip_start..self.oral.last() + 1].fill([oral_area_cm2; 2]);
        self.net.set_geometry_targets(
            &self.area_targets,
            None,
            &[(self.velum_port, velum_area_cm2)],
            samples,
        )?;
        self.update_noise()
    }

    pub(super) fn set_source(
        &mut self,
        pitch_hz: f64,
        amplitude_cm2: f64,
        variation: [f64; 3],
    ) -> Result<(), &'static str> {
        self.glottis
            .set_dynamic_source(pitch_hz, amplitude_cm2, variation)
    }

    pub(super) fn set_glottal_noise_gain(&mut self, gain: f64) -> Result<(), &'static str> {
        if self.glottal_noise.gain != gain {
            self.net.set_noise_gain(0, gain)?;
            self.glottal_noise.gain = gain;
        }
        Ok(())
    }

    pub fn geometry(&self) -> MammalGeometry {
        MammalGeometry {
            trachea_cells: self.trachea.count,
            pharynx_cells: self.pharynx.count,
            oral_cells: self.oral.count,
            nasal_cells: self.nasal.count,
            oral_tip_area_cm2: self.net.area(self.oral.last()),
            courant: self.net.courant(),
        }
    }

    pub(super) fn initial_velum_area(&self) -> f64 {
        self.net.branch_area(self.velum_port)
    }

    pub(super) fn trunk_geometry(&self) -> Option<TrunkGeometry> {
        self.trunk.as_ref().map(|trunk| TrunkGeometry {
            trunk_cells: trunk.tube.count,
            trunk_inlet_area_cm2: self.net.area(trunk.tube.first),
            trunk_tip_area_cm2: self.net.area(trunk.tube.last()),
            trunk_valve_area_cm2: self.net.branch_area(trunk.valve),
        })
    }

    pub(super) fn set_trunk_valve_area(&mut self, area_cm2: f64) -> Result<(), &'static str> {
        let trunk = self.trunk.as_ref().ok_or("鼻の入口の弁がありません")?;
        self.net.set_port_area(trunk.valve, area_cm2)
    }

    pub(super) fn trunk_pressure_difference(&self) -> Option<f64> {
        self.trunk
            .as_ref()
            .map(|trunk| self.net.pressure(self.nasal.last()) - self.net.pressure(trunk.tube.first))
    }

    pub(super) fn trunk_sample(&self) -> Option<TrunkSample> {
        self.trunk.as_ref().map(|trunk| TrunkSample {
            nasal_base_pressure_dyn_cm2: self.net.pressure(self.nasal.last()),
            trunk_inlet_pressure_dyn_cm2: self.net.pressure(trunk.tube.first),
            trunk_tip_pressure_dyn_cm2: self.net.pressure(trunk.tube.last()),
            trunk_valve_area_cm2: self.net.branch_area(trunk.valve),
            trunk_valve_flow_cm3_s: self.net.branch_flow(trunk.valve),
        })
    }

    pub(super) fn oral_noise_cell(&self) -> Option<usize> {
        self.oral_noise_cell
    }

    pub(super) fn set_pitch(&mut self, pitch_hz: f64) -> Result<(), &'static str> {
        self.glottis.set_pitch(pitch_hz)
    }

    pub(crate) fn set_roughness(&mut self, roughness: f64) {
        self.glottis.set_chaos(roughness);
    }

    /// 制御境界で肺圧を設定し、無励振に近い状態を整理する。
    pub fn set_lung_pressure(&mut self, pressure_dyn_cm2: f64) -> Result<(), &'static str> {
        self.net.set_fixed_pressure(self.lung, pressure_dyn_cm2)?;
        self.glottis.trim_tail();
        self.net.trim_creature_tail();
        Ok(())
    }

    pub fn step(&mut self, abduction_cm2: f64) -> Result<MammalAirwaySample, &'static str> {
        let subglottal = self.trachea.last();
        let supraglottal = self.pharynx.first;
        let drive = self.net.pressure(subglottal) - self.net.pressure(supraglottal);
        let source = self.glottis.step(drive, abduction_cm2);
        self.net.set_port_area(self.glottis_port, source.area_cm2)?;
        let radiation = self.net.step(self.lung, 0.0);
        Ok(MammalAirwaySample {
            lung_pressure_dyn_cm2: self.net.pressure(self.lung),
            lung_flow_cm3_s: self.net.branch_flow(self.lung_port),
            trachea_inlet_pressure_dyn_cm2: self.net.pressure(self.trachea.first),
            trachea_end_pressure_dyn_cm2: self.net.pressure(subglottal),
            pharynx_pressure_dyn_cm2: self.net.pressure(supraglottal),
            glottis_drive_dyn_cm2: drive,
            glottis_area_cm2: self.net.branch_area(self.glottis_port),
            glottis_flow_cm3_s: self.net.branch_flow(self.glottis_port),
            glottis_voicing: source.voicing,
            glottis_f0_hz: source.f0_hz,
            glottis_phase: source.phase,
            velum_area_cm2: self.net.branch_area(self.velum_port),
            velum_flow_cm3_s: self.net.branch_flow(self.velum_port),
            oral_tip_area_cm2: self.net.area(self.oral.last()),
            wall_radiation_cm3_s: radiation.wall_radiation_flow_cm3_s,
            oral_radiation_cm3_s: self
                .net
                .radiation_flow(self.oral.last())
                .unwrap_or_default(),
            nasal_radiation_cm3_s: self
                .net
                .radiation_flow(
                    self.trunk
                        .as_ref()
                        .map_or(self.nasal.last(), |t| t.tube.last()),
                )
                .unwrap_or_default(),
            radiation_derivative_cm3_s2: radiation.radiation_flow_derivative_cm3_s2,
            glottal_noise_level_dyn_cm2: self.net.noise_level(0).unwrap_or_default(),
            glottal_noise_pressure_dyn_cm2: self
                .net
                .branch_noise_pressure(self.glottal_noise.forward)
                + self.net.branch_noise_pressure(self.glottal_noise.reverse),
            oral_noise_level_dyn_cm2: self.net.noise_level(1).unwrap_or_default(),
        })
    }
}
