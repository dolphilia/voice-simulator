"""一時ビルドの気道から幾何、体積速度、配分先を採取する。"""

from tsp_fk61_lip_front_radiation_observation import prepare as prepare_cells
from tsp_fk61_lip_observation import edit, insert_before


FIELDS = {
    'geometry': ('sample', 'node', 'enabled', 'advances', 'area', 'minimum', 'length', 'volume',
                 'area_step', 'minimum_step', 'length_step', 'target_minimum', 'coefficient',
                 'old_first', 'old_second', 'area_floor', 'squeeze'),
    'neighbor': ('sample', 'node', 'neighbor'),
    'raw': ('sample', 'node', 'flow'),
    'routed': ('sample', 'node', 'receiver', 'flow'),
}

EMIT = '''
fn research_volume_row(tag: &str, sample: usize, node: usize, values: &[f64]) {
    let mut out = std::io::stdout().lock();
    use std::io::Write as _;
    write!(out, "{tag},{sample},{node}").expect("体積源の観測を書き出せません");
    for value in values {
        write!(out, ",{value:?}").expect("体積源の観測を書き出せません");
    }
    writeln!(out).expect("体積源の観測を書き出せません");
}
'''


def prepare(root, fixed, window, execute):
    source = prepare_cells(root, fixed, window, execute)
    observe(root, fixed, window)
    return source


def observe(root, fixed, window):
    if fixed:
        network = root / 'crates/chimera/src/airway/network.rs'
        volume = network
        start = '        let sq = self.squeeze_area;'
        nodes = 'self.n_nodes'
        geometry = '''u8::from(self.enable_volume_source).into(), 1.0,
                self.area[node], self.amin[node], self.dx[node], self.vol[node], self.area_step[node],
                self.amin_step[node], self.dx_step[node], self.amin_target[node], self.vol_lp_coef,
                self.vol_src1[node], self.vol_src2[node], min_a, self.squeeze_area'''
        neighbors = '&self.nbr_list[self.nbr_start[node]..self.nbr_start[node + 1]]'
        actual_raw = '                    let raw = -(v - self.vol[k]) * inv_t;'
        routed = '                                    inj[m] += share;'
        owner, receiver, emit = 'k', 'm', 'research_volume_row'
    else:
        network = root / 'crates/vocal-core/src/airway/network.rs'
        volume = network.parent / 'network/geometry.rs'
        start = '        let sections_changed = self.moving_areas.step('
        nodes = 'self.sections.len()'
        geometry = 'self.moving_areas.research_cell(node, self.sections[node])'
        neighbors = '&self.neighbors[node]'
        actual_raw = '                let raw = (cell.volume_cm3 - next_volume) / dt;'
        routed = '                        self.spill[node] += share;'
        owner, receiver, emit = 'i', 'node', 'super::research_volume_row'
        insert_before(volume, '    pub(super) fn filtered_flow', '''    pub(super) fn research_cell(
        &self, node: usize, section: Section,
    ) -> [f64; 15] {
        let cell = self.cells[node];
        [u8::from(self.enabled).into(), u8::from(self.remaining > 0).into(), section.area_cm2,
            section.minimum_area_cm2, section.length_cm, cell.volume_cm3, cell.area_increment_cm2,
            cell.minimum_area_increment_cm2, cell.length_increment_cm, cell.target_minimum_area_cm2,
            self.coefficient, cell.first_pole, cell.filtered_flow, super::MIN_CELL_AREA_CM2, SQUEEZE_AREA_CM2]
    }

''')
        anchor = '        flow: &mut [f64],\n    ) -> bool {'
        edit(volume, anchor, '        flow: &mut [f64],\n        probe_volume_sample: Option<usize>,\n    ) -> bool {')
        anchor = '            &mut self.net_flow,\n        );'
        edit(network, anchor, '            &mut self.net_flow,\n            probe_volume_sample,\n        );')
    with network.open('a') as file:
        file.write(EMIT)
    values = f'&[{geometry}]' if fixed else f'&{geometry}'
    insert_before(network, start, f'''        let probe_volume_sample = probe_cells.as_ref().map(|probe| probe.0);
        if let Some(sample) = probe_volume_sample {{
            for node in 0..{nodes} {{
                research_volume_row("geometry", sample, node, {values});
                if sample == {window[0]} {{
                    for &other in {neighbors} {{
                        research_volume_row("neighbor", sample, node, &[other as f64]);
                    }}
                }}
            }}
        }}
''')
    for anchor, tag, row in ((actual_raw, 'raw', '&[raw]'), (routed, 'routed', f'&[{receiver} as f64, share]')):
        indent = ' ' * (len(anchor) - len(anchor.lstrip()))
        edit(volume, anchor, anchor + f'''
{indent}if let Some(sample) = probe_volume_sample {{
{indent}    {emit}("{tag}", sample, {owner}, {row});
{indent}}}''')
