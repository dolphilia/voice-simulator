//! 人間の声道の断面を気道グラフに接続する。管とポートの係数はCHIMERA由来（MIT）。

use std::ops::Range;

mod frication;
pub use frication::{FricationGeometry, TurbulenceSettings};

use super::network::{AirwayNetwork, Boundaries, Port, Section};
use super::tract_control::{TractSampling, TractTargets};
use super::{AIR_DENSITY, SOUND_SPEED, WallParameters};
use crate::anatomy::{AreaProfile, BodyParameters, ResampledTract, TractCell};
#[cfg(all(not(target_arch = "wasm32"), feature = "render-allocation-probe"))]
use crate::render_allocation_probe::{Phase as AllocationPhase, scope as allocation_scope};

const SOFT_WALL: WallParameters = WallParameters {
    mass_g_cm2: 1.5,
    resistance_dyn_s_cm3: 1600.0,
    stiffness_dyn_cm3: 3e5,
    radiation_fraction: 0.0,
};

pub struct AirwayTube {
    pub name: &'static str,
    pub nodes: Range<usize>,
    pub branches: Range<usize>,
    pub anatomical_length_cm: f64,
    pub simulation_length_cm: f64,
}

pub struct HumanAirway {
    pub network: AirwayNetwork,
    pub(crate) body: BodyParameters,
    pub(crate) lung_series_resistance_cgs: f64,
    pub tubes: [AirwayTube; 7],
    pub velum_area_cm2: f64,
    pub pharynx_entry: usize,
    pub pharynx_end: usize,
    pub lips: usize,
    pub nostrils: usize,
    pub sinus: usize,
    pub oral_link: usize,
    pub lungs: usize,
    pub lung_port: usize,
    pub subglottal: usize,
    pub glottis_port: usize,
    pub velum_port: usize,
    pub sinus_neck: usize,
    target_areas_cm2: Vec<[f64; 2]>,
    target_lengths_cm: Vec<f64>,
    frication_geometry: FricationGeometry,
}

impl HumanAirway {
    /// 固定姿勢から面積・最小断面・セル長を設定し、静止状態から計算を始める。
    pub fn fixed_from_profile(
        sample_rate_hz: u32,
        profile: &AreaProfile,
        velum_area_cm2: f64,
    ) -> Result<Self, &'static str> {
        let body = profile.body;
        let sampling = TractSampling::for_body(sample_rate_hz, body)?;
        let tract = sampling.resample(profile)?;
        Self::with_tract(sample_rate_hz, body, &sampling, &tract, velum_area_cm2)
    }

    /// 初期姿勢の目標を直接設定し、体積変化を加えずに気道を初期化する。
    pub fn from_targets(sample_rate_hz: u32, targets: &TractTargets) -> Result<Self, &'static str> {
        let sampling = TractSampling::with_oral_cells(
            sample_rate_hz,
            targets.body,
            targets.oral_cells_override,
        )?;
        if !sampling.matches(&targets.limited) {
            return Err("初期の断面目標は指定サンプルレートのセル数にそろえてください");
        }
        Self::with_tract(
            sample_rate_hz,
            targets.body,
            &sampling,
            &targets.limited,
            targets.velum_cm2,
        )
    }

    fn with_tract(
        sample_rate_hz: u32,
        body: BodyParameters,
        sampling: &TractSampling,
        tract: &ResampledTract,
        velum_area_cm2: f64,
    ) -> Result<Self, &'static str> {
        if !velum_area_cm2.is_finite() || velum_area_cm2 < 0.0 {
            return Err("軟口蓋ポートには有限の非負面積が必要です");
        }
        let k = body.scale;
        let trachea_length = 12.0 * k;
        let trachea_area = 2.5 * k * k;
        let lung_series_resistance_cgs = (0.5 * AIR_DENSITY * SOUND_SPEED) / trachea_area;
        let nasal_length = 11.4 * k;
        let fossa_length = 2.0 * k;
        let design_cell_length = sampling.design_cell_length_cm;
        let trachea_count =
            ((trachea_length / design_cell_length.max(0.9 * k)).floor() as usize).max(6);
        let nasal_count =
            ((nasal_length / design_cell_length.max(0.5 * k)).floor() as usize).max(8);
        let fossa_count = ((fossa_length / design_cell_length).floor() as usize).clamp(1, 3);
        let pharynx_count = tract.pharynx.cells.len();
        let oral_count = tract.oral.cells.len();
        let pharynx_length = sampling.simulation_length(&tract.pharynx);
        let oral_length = sampling.simulation_length(&tract.oral);
        let total = trachea_count + pharynx_count + oral_count + nasal_count + fossa_count + 2;
        let mut sections = Vec::with_capacity(total);
        let mut connections = Vec::with_capacity(total - 5);

        let trachea = add_tube(
            &mut sections,
            &mut connections,
            "trachea",
            trachea_length,
            section(
                trachea_length,
                trachea_count,
                1.0,
                1.0,
                Some(WallParameters {
                    mass_g_cm2: 0.6,
                    resistance_dyn_s_cm3: 1000.0,
                    stiffness_dyn_cm3: 1e6,
                    radiation_fraction: 0.0,
                }),
            ),
            uniform_cells(trachea_area, trachea_count),
        );
        let oral_wall = Some(WallParameters {
            radiation_fraction: 0.25,
            ..SOFT_WALL
        });
        let pharynx = add_tube(
            &mut sections,
            &mut connections,
            "pharynx",
            tract.pharynx.length_cm,
            section(pharynx_length, pharynx_count, 1.25, 1.0, oral_wall),
            tract.pharynx.cells.iter().copied(),
        );
        let oral = add_tube(
            &mut sections,
            &mut connections,
            "oral",
            tract.oral.length_cm,
            section(oral_length, oral_count, 1.5, 1.0, oral_wall),
            tract.oral.cells.iter().copied(),
        );
        let nasal = add_tube(
            &mut sections,
            &mut connections,
            "nasal",
            nasal_length,
            section(
                nasal_length,
                nasal_count,
                3.2,
                2.5,
                Some(WallParameters {
                    mass_g_cm2: 1.0,
                    resistance_dyn_s_cm3: 3000.0,
                    stiffness_dyn_cm3: 1e6,
                    radiation_fraction: 0.0,
                }),
            ),
            (0..nasal_count).map(|index| {
                let position = (index as f64 + 0.5) / nasal_count as f64;
                let area = if position < 0.18 {
                    2.6
                } else if position < 0.75 {
                    2.0 - 0.6 * (position - 0.18)
                } else if position < 0.9 {
                    1.4
                } else {
                    1.0
                };
                uniform_cell(area * k * k)
            }),
        );
        let fossa = add_tube(
            &mut sections,
            &mut connections,
            "piriform",
            fossa_length,
            section(fossa_length, fossa_count, 1.3, 1.0, Some(SOFT_WALL)),
            uniform_cells(0.9 * k * k, fossa_count),
        );
        let lungs = add_tube(
            &mut sections,
            &mut connections,
            "lungs",
            1.0,
            section(1.0, 1, 1.0, 1.0, None),
            uniform_cells(100.0, 1),
        );
        let sinus_volume = 14.0 * k * k * k;
        let sinus_length = libm::cbrt(sinus_volume);
        let sinus = add_tube(
            &mut sections,
            &mut connections,
            "sinus",
            sinus_length,
            section(sinus_length, 1, 1.2, 1.0, None),
            uniform_cells(sinus_volume / sinus_length, 1),
        );

        let pharynx_entry = pharynx.nodes.start;
        let pharynx_end = pharynx.nodes.end - 1;
        let lips = oral.nodes.end - 1;
        let nostrils = nasal.nodes.end - 1;
        let lungs_node = lungs.nodes.start;
        let sinus_node = sinus.nodes.start;
        let oral_link = connections.len();
        connections.push([pharynx_end, oral.nodes.start]);
        let fossa_offset = ((2.6 / 8.8) * pharynx_count as f64).round() as usize;
        connections.push([
            pharynx_entry + fossa_offset.min(pharynx_count - 1),
            fossa.nodes.start,
        ]);
        let ports_start = connections.len();
        let sinus_offset = (0.45 * nasal_count as f64).round() as usize;
        let ports = [
            Port {
                extra_resistance: lung_series_resistance_cgs,
                ..port(
                    [lungs_node, trachea.nodes.start],
                    1.0,
                    trachea_area,
                    [0.0, 0.0],
                )
            },
            Port {
                slit_width_cm: 1.4 * k,
                ..port(
                    [trachea.nodes.end - 1, pharynx_entry],
                    0.3 * k,
                    0.0,
                    [0.37, 1.0],
                )
            },
            port(
                [pharynx_end, nasal.nodes.start],
                1.0 * k,
                velum_area_cm2,
                [0.3, 0.8],
            ),
            Port {
                include_half_sections: false,
                ..port(
                    [nasal.nodes.start + sinus_offset, sinus_node],
                    0.5 * k,
                    0.12 * k * k,
                    [0.0, 0.0],
                )
            },
        ];
        let mut network = AirwayNetwork::new(
            sample_rate_hz,
            &sections,
            &connections,
            Boundaries {
                radiation_nodes: &[lips, nostrils],
                fixed_pressure_nodes: &[lungs_node],
                ports: &ports,
            },
        )?;
        network.reserve_noise_sources(frication::MAX_TURBULENCE_SOURCES);
        let subglottal = trachea.nodes.end - 1;
        Ok(Self {
            network,
            body,
            lung_series_resistance_cgs,
            tubes: [trachea, pharynx, oral, nasal, fossa, lungs, sinus],
            velum_area_cm2,
            pharynx_entry,
            pharynx_end,
            lips,
            nostrils,
            sinus: sinus_node,
            oral_link,
            lungs: lungs_node,
            lung_port: ports_start,
            subglottal,
            glottis_port: ports_start + 1,
            velum_port: ports_start + 2,
            sinus_neck: ports_start + 3,
            target_areas_cm2: sections
                .iter()
                .map(|s| [s.area_cm2, s.minimum_area_cm2])
                .collect(),
            target_lengths_cm: sections.iter().map(|s| s.length_cm).collect(),
            frication_geometry: FricationGeometry::default(),
        })
    }

    pub fn frication_geometry(&self) -> FricationGeometry {
        self.frication_geometry
    }

    pub fn tract_section_counts(&self) -> [usize; 2] {
        [self.tubes[1].nodes.len(), self.tubes[2].nodes.len()]
    }

    /// 補間を反映した咽頭と口腔のセルを、声門から口端の順に返す。
    pub fn tract_sections(&self) -> impl Iterator<Item = Section> + '_ {
        self.tubes[1..3]
            .iter()
            .flat_map(|tube| tube.nodes.clone())
            .map(|node| self.network.section(node))
    }

    /// 声道セルの中心圧力 dyn/cm² と口側境界の符号付き流量 cm³/s。
    /// 咽頭末尾は口腔への接続、口腔末尾は外気への放射を使う。
    pub fn tract_acoustics(&self) -> impl Iterator<Item = [f64; 2]> + '_ {
        let [_, pharynx, oral, ..] = &self.tubes;
        let flows = pharynx
            .branches
            .clone()
            .chain(std::iter::once(self.oral_link))
            .chain(oral.branches.clone())
            .map(|branch| self.network.branch_flow(branch))
            .chain(std::iter::once_with(|| {
                self.network
                    .radiation_flow(self.lips)
                    .expect("口端の放射負荷")
            }));
        pharynx
            .nodes
            .clone()
            .chain(oral.nodes.clone())
            .zip(flows)
            .map(|(node, flow)| [self.network.pressure(node), flow])
    }

    /// 接触補正まで終えた目標を受け取り、次の内部ブロックの補間を準備する。
    pub fn begin_tract_block(
        &mut self,
        targets: &TractTargets,
        samples: usize,
    ) -> Result<(), &'static str> {
        #[cfg(all(not(target_arch = "wasm32"), feature = "render-allocation-probe"))]
        let _allocation = allocation_scope(AllocationPhase::BeginTractBlock);
        let [_, pharynx, oral, ..] = &mut self.tubes;
        if pharynx.nodes.len() != targets.limited.pharynx.cells.len()
            || oral.nodes.len() != targets.limited.oral.cells.len()
        {
            return Err("断面目標のセル数は初期の気道グラフと一致させてください");
        }
        let tube_targets = [
            (
                pharynx,
                &targets.limited.pharynx,
                targets.pharynx_simulation_length_cm,
            ),
            (
                oral,
                &targets.limited.oral,
                targets.oral_simulation_length_cm,
            ),
        ];
        for (tube, profile, length) in &tube_targets {
            for (node, cell) in tube.nodes.clone().zip(&profile.cells) {
                self.target_areas_cm2[node] = [cell.area_cm2, cell.minimum_area_cm2];
            }
            let dx = *length / tube.nodes.len() as f64;
            self.target_lengths_cm[tube.nodes.clone()].fill(dx);
        }
        self.network.set_geometry_targets(
            &self.target_areas_cm2,
            Some(&self.target_lengths_cm),
            &[(self.velum_port, targets.velum_cm2)],
            samples,
        )?;
        for (tube, profile, length) in tube_targets {
            tube.anatomical_length_cm = profile.length_cm;
            tube.simulation_length_cm = length;
        }
        self.velum_area_cm2 = targets.velum_cm2;
        Ok(())
    }
}

fn section(
    length_cm: f64,
    count: usize,
    perimeter_factor: f64,
    viscous_factor: f64,
    wall: Option<WallParameters>,
) -> Section {
    Section {
        length_cm: length_cm / count as f64,
        area_cm2: 0.0,
        minimum_area_cm2: 0.0,
        perimeter_factor,
        viscous_factor,
        wall,
    }
}

fn add_tube(
    sections: &mut Vec<Section>,
    connections: &mut Vec<[usize; 2]>,
    name: &'static str,
    anatomical_length_cm: f64,
    template: Section,
    cells: impl ExactSizeIterator<Item = TractCell>,
) -> AirwayTube {
    let count = cells.len();
    let start = sections.len();
    sections.extend(cells.map(|cell| Section {
        area_cm2: cell.area_cm2,
        minimum_area_cm2: cell.minimum_area_cm2,
        ..template
    }));
    let end = sections.len();
    let branch_start = connections.len();
    connections.extend((start..end - 1).map(|node| [node, node + 1]));
    AirwayTube {
        name,
        nodes: start..end,
        branches: branch_start..connections.len(),
        anatomical_length_cm,
        simulation_length_cm: template.length_cm * count as f64,
    }
}

fn uniform_cell(area_cm2: f64) -> TractCell {
    TractCell {
        area_cm2,
        minimum_area_cm2: area_cm2,
    }
}

fn uniform_cells(area_cm2: f64, count: usize) -> impl ExactSizeIterator<Item = TractCell> {
    std::iter::repeat_n(uniform_cell(area_cm2), count)
}

fn port(nodes: [usize; 2], length_cm: f64, area_cm2: f64, losses: [f64; 2]) -> Port {
    Port {
        nodes,
        length_cm,
        area_cm2,
        entrance_loss: losses[0],
        expansion_loss: losses[1],
        slit_width_cm: 0.0,
        include_half_sections: true,
        extra_resistance: 0.0,
    }
}
