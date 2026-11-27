"""発話開始の短い区間だけ全節点の流量収支を採取する。"""

from tsp_fk61_lip_observation import PAIR_SHIFT, edit, insert_before, prepare as prepare_lip


FIELDS = (
    'sample', 'node', 'is_mouth', 'geometry_enabled', 'old_volume_cm3', 'volume_cm3',
    'area_cm2', 'minimum_cm2', 'length_cm', 'spill_cm3_s', 'pole1_cm3_s', 'pole2_cm3_s',
    'initial_inflow_cm3_s', 'before_wall_cm3_s', 'inflow_cm3_s',
    'wall_cm3_s', 'wall_fraction', 'old_pressure_dyn_cm2', 'new_pressure_dyn_cm2',
)


def prepare(root, fixed, window, execute, *, cell_indices=None):
    source = prepare_lip(root, fixed, window, execute)
    observe(root, fixed, window, cell_indices=cell_indices)
    return source


def observe(root, fixed, window, *, cell_indices=None):
    if fixed:
        network = root / 'crates/chimera/src/airway/network.rs'
        old_volumes = 'self.vol.clone()'
        pressure = 'self.p'
        flow = 'self.flow_sum'
        end = '        let out = (rad_total - self.rad_prev_total) * inv_t;'
        values = '''u8::from(self.probe_lip_node == Some(node)).into(), u8::from(vol_on).into(),
                    volume[node], self.vol[node], self.area[node], self.amin[node], self.dx[node],
                    self.spill[node], self.vol_src1[node], self.vol_src2[node],
                    initial[node], before_wall[node], self.flow_sum[node],
                    self.wall_u[node], self.wall_rad[node], pressure[node], self.p[node]'''
        node_count = 'self.n_nodes'
    else:
        network = root / 'crates/vocal-core/src/airway/network.rs'
        old_volumes = '(0..self.sections.len()).map(|node| self.moving_areas.observe(node)[2]).collect::<Vec<_>>()'
        pressure = 'self.pressure'
        flow = 'self.net_flow'
        end = '        let derivative = (radiation_flow - self.previous_radiation_flow) / self.dt;'
        values = '''u8::from(self.probe_lip_node == Some(node)).into(), geometry[0],
                    volume[node], geometry[2], section.area_cm2, section.minimum_area_cm2, section.length_cm,
                    geometry[9], geometry[7], geometry[8],
                    initial[node], before_wall[node], self.net_flow[node], self.wall_motion[node].flow_cm3_s,
                    section.wall.map_or(0.0, |wall| wall.radiation_fraction), pressure[node], self.pressure[node]'''
        node_count = 'self.sections.len()'
    storage = '    pub probe_lip_node: Option<usize>,'
    edit(network, storage, storage + '\n    probe_cell_sample: usize,')
    storage_start = '            probe_lip_node: None,'
    edit(network, storage_start, storage_start + '\n            probe_cell_sample: 0,')
    start, stop = window
    insert_before(network, PAIR_SHIFT, f'''        let probe_cells = self.probe_lip_node.and_then(|_| {{
            let sample = self.probe_cell_sample;
            self.probe_cell_sample += 1;
            ({start}..{stop}).contains(&sample).then(|| (sample, {old_volumes}, {pressure}.clone()))
        }});
''')
    insert_before(network, '        let probe_geometry_inflow =',
                  f'        let probe_initial = probe_cells.as_ref().map(|_| {flow}.clone());\n')
    insert_before(network, '        let probe_before_wall =',
                  f'        let probe_wall_in = probe_cells.as_ref().map(|_| {flow}.clone());\n')
    candidate_locals = '' if fixed else '''                let section = self.sections[node];
                let geometry = self.moving_areas.observe(node);
'''
    selected_nodes = f'0..{node_count}' if cell_indices is None else '[' + ', '.join(map(str, cell_indices)) + ']'
    insert_before(network, end, f'''        if let (Some((sample, volume, pressure)), Some(initial), Some(before_wall)) =
            (probe_cells, probe_initial, probe_wall_in)
        {{
            let mut out = std::io::stdout().lock();
            use std::io::Write as _;
            for node in {selected_nodes} {{
{candidate_locals}                let values: [f64; {len(FIELDS) - 2}] = [{values}];
                write!(out, "{{sample}},{{node}}").expect("節点観測を書き出せません");
                for value in values {{
                    write!(out, ",{{value:?}}").expect("節点観測を書き出せません");
                }}
                writeln!(out).expect("節点観測を書き出せません");
            }}
        }}
''')
