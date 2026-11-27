"""制御境界の口腔形状目標と、各内部標本の更新前形状を採る。"""

from tsp_fk61_lip_observation import insert_before
from tsp_fk61_terminal_branch_observation import prepare as prepare_branches


TARGET_FIELDS = ('area', 'minimum', 'length', 'anatomical_length', 'simulation_length')
STEP_FIELDS = ('area', 'minimum', 'length', 'area_step', 'minimum_step', 'length_step')

EMITTER = '''
    pub(crate) fn research_oral_ramp(&self, tag: &str, sample: usize, node: usize, values: &[f64]) {
        use std::io::Write as _;
        let mut out = std::io::stdout().lock();
        write!(out, "{tag},{sample},{node}").expect("口腔形状を書き出せません");
        for value in values {
            write!(out, ",{value:?}").expect("口腔形状を書き出せません");
        }
        writeln!(out).expect("口腔形状を書き出せません");
    }
'''


def prepare(root, fixed, window, execute, *, measure):
    nodes = measure['nodes']
    source = prepare_branches(root, fixed, window, execute, cell_indices=nodes, branch_left_indices=nodes[:-1],
                              wall_indices=nodes[1:], compliance_indices=measure['pressure_nodes'])
    if fixed:
        base = root / 'crates/chimera/src'
        human = base / 'voice/human_airway.rs'
        target_anchor = '        self.net.set_tube_targets(self.oral, &self.or_areas, Some(or_sim), Some(&self.or_min));'
        target = '''        for i in 0..self.n_or {
            self.net.research_oral_ramp("ramp-target", sample, self.oral.node(i),
                &[self.or_areas[i], self.or_min[i], or_sim / self.n_or as f64, or_len, or_sim]);
        }'''
        target_net = 'self.net'
        step_anchor = '        let sq = self.squeeze_area;'
        values = '''&[self.area[node], self.amin[node], self.dx[node], self.area_step[node],
                    self.amin_step[node], self.dx_step[node]]'''
    else:
        base = root / 'crates/vocal-core/src'
        human = base / 'airway/human.rs'
        target_anchor = '        self.network.set_geometry_targets('
        target = '''        for node in tube_targets[1].0.nodes.clone() {
            let [area, minimum] = self.target_areas_cm2[node];
            self.network.research_oral_ramp("ramp-target", sample, node,
                &[area, minimum, self.target_lengths_cm[node], targets.raw.oral.length_cm,
                    targets.oral_simulation_length_cm]);
        }'''
        target_net = 'self.network'
        step_anchor = '        let sections_changed = self.moving_areas.step('
        values = '''&{
                    let s = self.sections[node];
                    let [_, _, _, da, dl, dm, ..] = self.moving_areas.observe(node);
                    [s.area_cm2, s.minimum_area_cm2, s.length_cm, da, dm, dl]
                }'''
    network = base / 'airway/network.rs'
    boundaries = ' | '.join(map(str, measure['control_boundaries']))
    control_probe = f'''
    pub(crate) fn research_oral_boundary(&self) -> Option<usize> {{
        (self.probe_lip_node.is_some() && matches!(self.probe_cell_sample, {boundaries}))
            .then_some(self.probe_cell_sample)
    }}
'''
    insert_before(network, '    pub fn set_port_area(', EMITTER + control_probe)
    insert_before(human, target_anchor, f'''        if let Some(sample) = {target_net}.research_oral_boundary() {{
{target}
        }}
''')
    insert_before(network, step_anchor, f'''        if let Some((sample, ..)) = probe_cells.as_ref() {{
            for node in {nodes[1]}..={nodes[-1]} {{
                self.research_oral_ramp("ramp-step", *sample, node, {values});
            }}
        }}
''')
    return source
