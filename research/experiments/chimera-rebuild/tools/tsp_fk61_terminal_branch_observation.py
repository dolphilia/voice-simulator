"""通常音声の口端2節点で枝・壁・圧力更新の入力と出力を採取する。"""

from tsp_fk61_lip_front_radiation_observation import prepare as prepare_cells
from tsp_fk61_lip_observation import insert_before


FIELDS = {
    'branch': ('sample', 'left', 'right', 'left_pressure', 'right_pressure', 'noise_pressure', 'inertance',
               'previous_inertance', 'previous_flow', 'previous_momentum', 'resistance',
               'forward_loss', 'reverse_loss', 'flow'),
    'wall': ('sample', 'node', 'mass', 'resistance', 'stiffness', 'surface', 'pressure',
             'previous_velocity', 'previous_displacement', 'velocity', 'displacement', 'flow'),
    'compliance': ('sample', 'node', 'value'),
}


def trace(kind, indices, values, selection, indent):
    length = len(FIELDS[kind]) - len(indices) - 1
    indices = ''.join(f',{{{index}}}' for index in indices)
    return ''.join(indent + line + '\n' for line in f'''if let Some(sample) = probe_cells.as_ref().map(|probe| probe.0) {{
    if {selection} {{
        let mut out = std::io::stdout().lock();
        use std::io::Write as _;
        let values: [f64; {length}] = [{values}];
        write!(out, "{kind},{{sample}}{indices}").expect("口端の観測を書き出せません");
        for value in values {{
            write!(out, ",{{value:?}}").expect("口端の観測を書き出せません");
        }}
        writeln!(out).expect("口端の観測を書き出せません");
    }}
}}'''.splitlines())


def prepare(root, fixed, window, execute, *, cell_indices=None, branch_left_indices=(41, 42),
            wall_indices=(42, 43), compliance_indices=(42,)):
    source = prepare_cells(root, fixed, window, execute, cell_indices=cell_indices)
    observe(root, fixed, branch_left_indices=branch_left_indices, wall_indices=wall_indices,
            compliance_indices=compliance_indices)
    return source


def observe(root, fixed, *, branch_left_indices, wall_indices, compliance_indices):
    branch_pattern = ' | '.join(map(str, branch_left_indices))
    wall_pattern = ' | '.join(map(str, wall_indices))
    compliance_pattern = ' | '.join(map(str, compliance_indices))
    if fixed:
        net = root / 'crates/chimera/src/airway/network.rs'
        insert_before(net, '                u_arr[j] = u;\n                mom[j] = l * u;',
                      trace('branch', ('a', 'b'),
                            'p[a], p[b], psrc[j], l, lp, u_arr[j], mom[j], r, kf, kb, u',
                            f'b_kind[j] == KIND_SERIES && b == a + 1 && matches!(a, {branch_pattern})', ' ' * 16))
        insert_before(net, '            let v = ((m * inv_t - 0.5 * r) * self.wall_v[k]',
                      '            let (probe_v, probe_y) = (self.wall_v[k], self.wall_y[k]);\n')
        insert_before(net, '            wall_rad_sum += uw * self.wall_rad[k];',
                      trace('wall', ('k',),
                            'm, r, self.wall_k[k], self.wall_perim[k] * sa * self.dx[k], '
                            'self.p[k], probe_v, probe_y, v, self.wall_y[k], uw',
                            f'matches!(k, {wall_pattern})', ' ' * 12))
        insert_before(net, '                self.p[k] += (t / c) * self.flow_sum[k];',
                      trace('compliance', ('k',), 'c', f'matches!(k, {compliance_pattern})', ' ' * 16))
    else:
        net = root / 'crates/vocal-core/src/airway/network.rs'
        insert_before(net, '            let flow = branch.step(self.dt, difference);',
                      '            let (probe_l, probe_u) = (branch.previous_inertance, branch.flow);\n')
        insert_before(net, '            self.net_flow[left] -= flow;\n            self.net_flow[right] += flow;\n        }',
                      trace('branch', ('left', 'right'),
                            'self.pressure[left], self.pressure[right], noise, branch.inertance, '
                            'probe_l, probe_u, probe_l * probe_u, branch.resistance, '
                            'branch.forward_loss, branch.reverse_loss, flow',
                            f'branch.port.is_none() && right == left + 1 && matches!(left, {branch_pattern})', ' ' * 12))
        insert_before(net, '                let flow = self.wall_motion[node].step(wall, self.dt, surface, self.pressure[node]);',
                      '                let probe_old_wall = self.wall_motion[node];\n')
        insert_before(net, '                self.net_flow[node] -= flow;',
                      trace('wall', ('node',),
                            'wall.mass_g_cm2, wall.resistance_dyn_s_cm3, wall.stiffness_dyn_cm3, surface, '
                            'self.pressure[node], probe_old_wall.velocity_cm_s, probe_old_wall.displacement_cm, '
                            'self.wall_motion[node].velocity_cm_s, self.wall_motion[node].displacement_cm, flow',
                            f'matches!(node, {wall_pattern})', ' ' * 16))
        insert_before(net, '                self.pressure[node] += self.dt / compliance * inflow;',
                      trace('compliance', ('node',), 'compliance', f'matches!(node, {compliance_pattern})', ' ' * 16))
