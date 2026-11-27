//! 左右の鳴管から共通気管、口腔食道腔、くちばしへつながる気道。

use super::network::{AirwayNetwork, Boundaries, Port, Section};
use super::{SOUND_SPEED, WallParameters};
use crate::syrinx::{SyrinxControls, SyrinxLabia};
use serde::{Deserialize, Serialize};

const MAX_SYRINX_AREA_CM2: f64 = 0.03;
const OEC_NECK_AREA_CM2: f64 = 0.03;
const TRACHEA_WALL: WallParameters = WallParameters {
    mass_g_cm2: 0.6,
    resistance_dyn_s_cm3: 1000.0,
    stiffness_dyn_cm3: 1.0e6,
    radiation_fraction: 0.0,
};

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SongbirdControls {
    pub pitch_hz: f64,
    pub interval_semitones: f64,
    pub voices: f64,
    pub drive: f64,
    pub tension: f64,
    pub pressure_kpa: f64,
    pub purity: f64,
    pub oec_cm3: f64,
    pub gape: f64,
}

impl SongbirdControls {
    pub const PITCH_MIN_HZ: f64 = 400.0;
    pub const PITCH_MAX_HZ: f64 = 9000.0;

    pub(crate) fn values(self) -> [f64; 9] {
        [
            self.pitch_hz,
            self.interval_semitones,
            self.voices,
            self.drive,
            self.tension,
            self.pressure_kpa,
            self.purity,
            self.oec_cm3,
            self.gape,
        ]
    }

    pub fn validate(self, breath_gate: f64) -> Result<(), &'static str> {
        if !(Self::PITCH_MIN_HZ..=Self::PITCH_MAX_HZ).contains(&self.pitch_hz)
            || !(-12.0..=12.0).contains(&self.interval_semitones)
            || !(0.1..=2.0).contains(&self.pressure_kpa)
            || !(0.05..=2.0).contains(&self.oec_cm3)
            || !(0.0..=1.5).contains(&breath_gate)
            || [
                self.voices,
                self.drive,
                self.tension,
                self.purity,
                self.gape,
            ]
            .into_iter()
            .any(|value| !(0.0..=1.0).contains(&value))
        {
            return Err("鳴禽の制御値が定義された範囲外です");
        }
        Ok(())
    }

    fn labia(self) -> [SyrinxControls; 2] {
        let position = 2.0 * self.voices;
        let right_hz = self.pitch_hz * libm::pow(2.0, self.interval_semitones / 12.0);
        let side = |f0_hz, gate| SyrinxControls {
            drive: self.drive,
            tension: self.tension,
            f0_hz,
            gate,
        };
        [
            side(self.pitch_hz, (2.0 - position).min(1.0)),
            side(right_hz, position.min(1.0)),
        ]
    }

    fn oec_area(self, pitch_hz: f64, length_cm: f64) -> f64 {
        let tuned_cm3 = OEC_NECK_AREA_CM2 / (0.35 * libm::pow(pitch_hz / 5570.0, 2.0));
        let volume_cm3 =
            (self.purity * tuned_cm3 + (1.0 - self.purity) * self.oec_cm3).clamp(0.04, 2.5);
        volume_cm3 / length_cm
    }

    fn beak_area(self, index: usize, count: usize) -> f64 {
        let center = (index as f64 + 0.5) / count as f64;
        0.012 + self.gape * (0.05 + 0.22 * center)
    }
}

#[derive(Clone, Copy)]
struct Tube {
    first: usize,
    count: usize,
    first_branch: usize,
}

impl Tube {
    fn last(self) -> usize {
        self.first + self.count - 1
    }
}

#[derive(Clone, Copy, Serialize)]
pub struct SongbirdGeometry {
    pub bronchus_cells_per_side: usize,
    pub trachea_cells: usize,
    pub beak_cells: usize,
    pub trachea_cell_length_cm: f64,
    pub oec_length_cm: f64,
    pub courant: f64,
}

pub struct SongbirdSample {
    pub opening: [f64; 2],
    pub port_area_cm2: [f64; 2],
    pub port_flow_cm3_s: [f64; 2],
    pub bronchus_end_pressure_dyn_cm2: [f64; 2],
    pub sac_pressure_dyn_cm2: f64,
    pub trachea_pressure_dyn_cm2: f64,
    pub trachea_out_flow_cm3_s: f64,
    pub trachea_wall_flow_cm3_s: f64,
    pub oec_area_cm2: f64,
    pub oec_pressure_dyn_cm2: f64,
    pub beak_tip_area_cm2: f64,
    pub radiation_flow_cm3_s: f64,
    pub radiation_derivative_cm3_s2: f64,
}

pub struct SongbirdBeakSample {
    pub pressure_dyn_cm2: f64,
    pub inflow_cm3_s: f64,
    pub area_cm2: f64,
}

pub struct SongbirdBronchusEndSample {
    pub upstream_pressure_dyn_cm2: f64,
    pub inflow_cm3_s: f64,
    pub area_cm2: f64,
    pub length_cm: f64,
}

pub struct SongbirdBronchusInteriorSample {
    pub pressure_dyn_cm2: f64,
    pub outflow_cm3_s: f64,
    pub inflow_state: SongbirdBronchusEndSample,
}

pub struct SongbirdNeckSample {
    pub trachea_pressure_dyn_cm2: f64,
    pub trachea_area_cm2: f64,
    pub trachea_cell_length_cm: f64,
    pub neck_area_cm2: f64,
    pub noise_pressure_dyn_cm2: f64,
}

pub struct SongbirdTracheaEndSample {
    pub previous_cell_pressure_dyn_cm2: f64,
    pub inflow_cm3_s: f64,
    pub wall_flow_cm3_s: f64,
    pub wall_displacement_cm: f64,
    pub inlet_noise_pressure_dyn_cm2: f64,
}

pub struct SongbirdTracheaInteriorSample {
    pub pressure_dyn_cm2: f64,
    pub inflow_state: SongbirdTracheaEndSample,
    pub outflow_cm3_s: f64,
    pub area_cm2: f64,
    pub length_cm: f64,
}

pub struct SongbirdOecSample {
    pub length_cm: f64,
    pub neck_inflow_cm3_s: f64,
    pub beak_outflow_cm3_s: f64,
    pub filtered_injection_cm3_s: f64,
    pub compliance_cm5_per_dyn: f64,
    pub neck_precedes_beak: bool,
}

pub struct SongbirdAirway {
    net: AirwayNetwork,
    labia: [SyrinxLabia; 2],
    bronchi: [Tube; 2],
    trachea: Tube,
    beak: Tube,
    beak_inlet: usize,
    sac: usize,
    sac_ports: [usize; 2],
    oec: usize,
    oec_neck: usize,
    syrinx_ports: [usize; 2],
    area_targets: Vec<[f64; 2]>,
}

impl SongbirdAirway {
    /// 初期断面を設定値へそろえ、圧力と流量がゼロの状態から開始する。
    pub fn new(rate_hz: u32, controls: SongbirdControls) -> Result<Self, &'static str> {
        controls.validate(0.0)?;
        let [left, right] = controls.labia();
        let labia = [
            SyrinxLabia::new(rate_hz, 0.0, left)?,
            SyrinxLabia::new(rate_hz, 1.0, right)?,
        ];
        let min_dx = SOUND_SPEED / f64::from(rate_hz) / 0.93;
        let cells = |length: f64| (length / min_dx).floor().clamp(3.0, 120.0) as usize;
        let mut sections = Vec::new();
        let mut connections = Vec::new();
        let mut add_tube =
            |length_cm: f64, count: usize, area: &dyn Fn(usize) -> f64, perimeter_factor, wall| {
                let first = sections.len();
                let first_branch = connections.len();
                for index in 0..count {
                    let area_cm2 = area(index);
                    sections.push(Section {
                        length_cm: length_cm / count as f64,
                        area_cm2,
                        minimum_area_cm2: area_cm2,
                        perimeter_factor,
                        viscous_factor: 1.0,
                        wall,
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
            };
        let bronchi = std::array::from_fn(|_| add_tube(0.8, cells(0.8), &|_| 0.02, 1.0, None));
        let trachea = add_tube(3.6, cells(3.6), &|_| 0.045, 1.0, Some(TRACHEA_WALL));
        let sac = add_tube(1.0, 1, &|_| 100.0, 1.0, None).first;
        let cavity_length = libm::cbrt(0.4);
        let oec = add_tube(
            cavity_length,
            1,
            &|_| controls.oec_area(left.f0_hz.min(right.f0_hz), cavity_length),
            1.2,
            None,
        )
        .first;
        let beak_cells = cells(1.3);
        let beak = add_tube(
            1.3,
            beak_cells,
            &|index| controls.beak_area(index, beak_cells),
            1.0,
            None,
        );
        let beak_inlet = connections.len();
        connections.push([oec, beak.first]);
        let port = |nodes, area_cm2, length_cm, entrance_loss, expansion_loss| Port {
            nodes,
            length_cm,
            area_cm2,
            entrance_loss,
            expansion_loss,
            slit_width_cm: 0.0,
            include_half_sections: true,
            extra_resistance: 0.0,
        };
        let ports = [
            port([sac, bronchi[0].first], 0.05, 0.4, 0.4, 1.0),
            port([sac, bronchi[1].first], 0.05, 0.4, 0.4, 1.0),
            port([bronchi[0].last(), trachea.first], 0.0, 0.08, 0.5, 1.0),
            port([bronchi[1].last(), trachea.first], 0.0, 0.08, 0.5, 1.0),
            port([trachea.last(), oec], OEC_NECK_AREA_CM2, 0.25, 0.3, 0.8),
        ];
        let net = AirwayNetwork::new(
            rate_hz,
            &sections,
            &connections,
            Boundaries {
                radiation_nodes: &[beak.last()],
                fixed_pressure_nodes: &[sac],
                ports: &ports,
            },
        )?;
        let area_targets = sections
            .iter()
            .map(|section| [section.area_cm2; 2])
            .collect();
        Ok(Self {
            net,
            labia,
            bronchi,
            trachea,
            beak,
            beak_inlet,
            sac,
            sac_ports: [connections.len(), connections.len() + 1],
            oec,
            oec_neck: connections.len() + 4,
            syrinx_ports: [connections.len() + 2, connections.len() + 3],
            area_targets,
        })
    }

    pub fn geometry(&self) -> SongbirdGeometry {
        SongbirdGeometry {
            bronchus_cells_per_side: self.bronchi[0].count,
            trachea_cells: self.trachea.count,
            beak_cells: self.beak.count,
            trachea_cell_length_cm: self.net.section(self.trachea.first).length_cm,
            oec_length_cm: self.net.section(self.oec).length_cm,
            courant: self.net.courant(),
        }
    }

    pub(crate) fn trim_creature_tail(&mut self) {
        self.net.trim_creature_tail();
    }

    /// 腔に近い順に、各くちばしセルの状態と直前の枝からの流入を返す。
    pub fn beak_samples(&self) -> impl Iterator<Item = SongbirdBeakSample> + '_ {
        let branches = std::iter::once(self.beak_inlet)
            .chain(self.beak.first_branch..self.beak.first_branch + self.beak.count - 1);
        (self.beak.first..=self.beak.last())
            .zip(branches)
            .map(|(node, branch)| SongbirdBeakSample {
                pressure_dyn_cm2: self.net.pressure(node),
                inflow_cm3_s: self.net.branch_flow(branch),
                area_cm2: self.net.area(node),
            })
    }

    /// 更新済みの左右の気管支末端について、直列枝からの流入と断面を返す。
    pub fn bronchus_end_samples(&self) -> [SongbirdBronchusEndSample; 2] {
        self.bronchi.map(|tube| {
            let end = tube.last();
            self.bronchus_inflow_sample(end, end - 1, tube.first_branch + tube.count - 2)
        })
    }

    /// 左右の気管支で同じ番号のセルを観測する。セル0への流入は空気嚢ポートを通る。
    pub fn bronchus_interior_samples(
        &self,
        index: usize,
    ) -> Option<[SongbirdBronchusInteriorSample; 2]> {
        if index >= self.bronchi[0].count - 1 {
            return None;
        }
        Some(std::array::from_fn(|side| {
            let tube = self.bronchi[side];
            let node = tube.first + index;
            let outlet = tube.first_branch + index;
            let (upstream, inlet) = if index == 0 {
                (self.sac, self.sac_ports[side])
            } else {
                (node - 1, outlet - 1)
            };
            SongbirdBronchusInteriorSample {
                pressure_dyn_cm2: self.net.pressure(node),
                outflow_cm3_s: self.net.branch_flow(outlet),
                inflow_state: self.bronchus_inflow_sample(node, upstream, inlet),
            }
        }))
    }

    fn bronchus_inflow_sample(
        &self,
        node: usize,
        upstream: usize,
        inlet: usize,
    ) -> SongbirdBronchusEndSample {
        let section = self.net.section(node);
        SongbirdBronchusEndSample {
            upstream_pressure_dyn_cm2: self.net.pressure(upstream),
            inflow_cm3_s: self.net.branch_flow(inlet),
            area_cm2: section.area_cm2,
            length_cm: section.length_cm,
        }
    }

    /// 次の首部流量の計算に使われる気管端の状態と、更新済みの首部断面を返す。
    pub fn neck_sample(&self) -> SongbirdNeckSample {
        let end = self.trachea.last();
        SongbirdNeckSample {
            trachea_pressure_dyn_cm2: self.net.pressure(end),
            trachea_area_cm2: self.net.area(end),
            trachea_cell_length_cm: self.net.section(end).length_cm,
            neck_area_cm2: self.net.branch_area(self.oec_neck),
            noise_pressure_dyn_cm2: self.net.branch_noise_pressure(self.oec_neck),
        }
    }

    /// 更新済みの気管端について、流入と壁の運動を観測する。
    pub fn trachea_end_sample(&self) -> SongbirdTracheaEndSample {
        self.trachea_inflow_sample(self.trachea.count - 1)
    }

    /// 気管内の直列枝2本が接続するセルの圧力収支を観測する。
    pub fn trachea_interior_sample(&self, index: usize) -> Option<SongbirdTracheaInteriorSample> {
        if index == 0 || index >= self.trachea.count - 1 {
            return None;
        }
        let node = self.trachea.first + index;
        let section = self.net.section(node);
        Some(SongbirdTracheaInteriorSample {
            pressure_dyn_cm2: self.net.pressure(node),
            inflow_state: self.trachea_inflow_sample(index),
            outflow_cm3_s: self.net.branch_flow(self.trachea.first_branch + index),
            area_cm2: section.area_cm2,
            length_cm: section.length_cm,
        })
    }

    fn trachea_inflow_sample(&self, index: usize) -> SongbirdTracheaEndSample {
        let node = self.trachea.first + index;
        let inlet = self.trachea.first_branch + index - 1;
        let wall = self.net.wall_motion(node);
        SongbirdTracheaEndSample {
            previous_cell_pressure_dyn_cm2: self.net.pressure(node - 1),
            inflow_cm3_s: self.net.branch_flow(inlet),
            wall_flow_cm3_s: wall.flow_cm3_s,
            wall_displacement_cm: wall.displacement_cm,
            inlet_noise_pressure_dyn_cm2: self.net.branch_noise_pressure(inlet),
        }
    }

    /// 更新済みの口腔食道腔について、圧力の収支に使う流量と幾何を返す。
    pub fn oec_sample(&self) -> SongbirdOecSample {
        SongbirdOecSample {
            length_cm: self.net.section(self.oec).length_cm,
            neck_inflow_cm3_s: self.net.branch_flow(self.oec_neck),
            beak_outflow_cm3_s: self.net.branch_flow(self.beak_inlet),
            filtered_injection_cm3_s: self.net.volume_source(self.oec),
            compliance_cm5_per_dyn: self.net.compliance(self.oec).effective,
            neck_precedes_beak: self.oec_neck < self.beak_inlet,
        }
    }

    /// 平滑化済みの演奏パラメータを適用し、断面を制御ブロック内で補間する。
    pub fn control(
        &mut self,
        controls: SongbirdControls,
        breath_gate: f64,
        block_samples: usize,
    ) -> Result<(), &'static str> {
        controls.validate(breath_gate)?;
        if block_samples == 0 {
            return Err("鳴禽の制御ブロックには1以上のサンプルが必要です");
        }
        let [left, right] = controls.labia();
        self.labia[0].set_controls(left)?;
        self.labia[1].set_controls(right)?;
        let pressure = controls.pressure_kpa * 1000.0 * breath_gate * 10.0;
        self.net.set_fixed_pressure(self.sac, pressure)?;
        let area = controls.oec_area(
            left.f0_hz.min(right.f0_hz),
            self.net.section(self.oec).length_cm,
        );
        self.area_targets[self.oec] = [area; 2];
        for index in 0..self.beak.count {
            self.area_targets[self.beak.first + index] =
                [controls.beak_area(index, self.beak.count); 2];
        }
        self.net.set_area_targets(&self.area_targets, block_samples)
    }

    /// 左右の面積を反映してから共通の気道を一サンプル進める。
    pub fn step(&mut self) -> Result<SongbirdSample, &'static str> {
        let opening = self.labia.each_mut().map(|side| side.step().opening);
        for (branch, opening) in self.syrinx_ports.into_iter().zip(opening) {
            self.net
                .set_port_area(branch, MAX_SYRINX_AREA_CM2 * opening)?;
        }
        let acoustic = self.net.step(self.sac, 0.0);
        let trachea = self.trachea.first;
        Ok(SongbirdSample {
            opening,
            port_area_cm2: self.syrinx_ports.map(|index| self.net.branch_area(index)),
            port_flow_cm3_s: self.syrinx_ports.map(|index| self.net.branch_flow(index)),
            bronchus_end_pressure_dyn_cm2: self.bronchi.map(|tube| self.net.pressure(tube.last())),
            sac_pressure_dyn_cm2: self.net.pressure(self.sac),
            trachea_pressure_dyn_cm2: self.net.pressure(trachea),
            trachea_out_flow_cm3_s: self.net.branch_flow(self.trachea.first_branch),
            trachea_wall_flow_cm3_s: self.net.wall_motion(trachea).flow_cm3_s,
            oec_area_cm2: self.net.area(self.oec),
            oec_pressure_dyn_cm2: self.net.pressure(self.oec),
            beak_tip_area_cm2: self.net.area(self.beak.last()),
            radiation_flow_cm3_s: acoustic.radiation_flow_cm3_s,
            radiation_derivative_cm3_s2: acoustic.radiation_flow_derivative_cm3_s2,
        })
    }
}
