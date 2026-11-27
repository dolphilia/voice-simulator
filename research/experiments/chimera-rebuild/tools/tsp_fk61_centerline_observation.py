"""中心線の区間距離を記録し、登録済みの1中心点を距離計算だけで交換する。"""

import tsp_fk61_lip_area_observation as area
from tsp_fk61_lip_observation import edit


ACCUMULATION = '''        samples.extend(contacts.iter().copied().map(|contact| {
            let mid = contact.ray.mid;
            if let Some(previous) = previous {
                s_cm += (mid - previous).norm();
            }
            previous = Some(mid);'''

DISTANCE = '''            let axial_distance = previous.map_or(0.0, |previous| (axial_mid - previous).norm());
            if previous.is_some() {
                s_cm += axial_distance;
            }
            previous = Some(axial_mid);'''


class CenterlineObservation:
    def __init__(self, settings):
        self.index = settings['focus_ray']
        self.replacement = settings['trial_input']

    def apply_trial(self, root):
        before_x, before_y = self.replacement['previous_midpoint_cm']
        this_x, this_y = self.replacement['standard_midpoint_cm']
        fixed_y = self.replacement['upstream_y_cm']
        target = root / 'crates/vocal-core/src/anatomy/area.rs'
        edit(target, ACCUMULATION, f'''        samples.extend(contacts.iter().copied().enumerate().map(|(index, contact)| {{
            let mid = contact.ray.mid;
            let mut axial_mid = mid;
            if index == {self.index}
                && mid.x == {this_x!r}
                && mid.y == {this_y!r}
                && contacts[index - 1].ray.mid.x == {before_x!r}
                && contacts[index - 1].ray.mid.y == {before_y!r}
            {{
                axial_mid.y = {fixed_y!r};
            }}
''' + DISTANCE)

    def prepare(self, root, fixed, requested, trial=False):
        probe = area.prepare(root, fixed, requested)
        if fixed:
            observe_upstream(root)
        else:
            observe_candidate(root, trial)
        return probe


def observe_upstream(root):
    source = root / 'crates/chimera/src/anatomy/human.rs'
    grid = '    pub grid: Vec<GridSample>,'
    edit(source, grid, grid + '\n    #[serde(skip)]\n    pub probe_axial_distances: Vec<f64>,')
    edit(source, '''        let mut s = epi_len;
        for i in 0..grid.len() {
            if i > 0 {
                s += dist(grid[i].mid, grid[i - 1].mid);
            }
            grid[i].s = s;
        }''', '''        let mut s = epi_len;
        f.probe_axial_distances.clear();
        for i in 0..grid.len() {
            let step = if i == 0 { 0.0 } else { dist(grid[i].mid, grid[i - 1].mid) };
            if i > 0 {
                s += step;
            }
            grid[i].s = s;
            f.probe_axial_distances.push(step);
        }''')
    probe = root / 'tools' / area.SNAPSHOT.name
    edit(probe, '        "area_inputs": airway.probe_lip_area_inputs(&voice.artic.x),', '''
        "area_inputs": airway.probe_lip_area_inputs(&voice.artic.x),
        "centerline": frame.grid.iter().zip(&frame.probe_axial_distances).map(|(g, &step)| {
            [g.mid.x, g.mid.y, step]
        }).collect::<Vec<_>>(),'''.lstrip('\n'))


def observe_candidate(root, trial):
    source = root / 'crates/vocal-core/src/anatomy/area.rs'
    field = '    pub s_cm: f64,'
    edit(source, field, field + '\n    pub probe_axial_cm: [f64; 3],')
    if not trial:
        edit(source, ACCUMULATION, '''        samples.extend(contacts.iter().copied().map(|contact| {
            let mid = contact.ray.mid;
            let axial_mid = mid;
''' + DISTANCE)
    edit(source, '                s_cm,\n            }',
         '                s_cm,\n                probe_axial_cm: [axial_mid.x, axial_mid.y, axial_distance],\n            }')
    probe = root / 'tools' / area.SNAPSHOT.name
    entry = '        "current": [current.area_cm2, current.minimum_area_cm2, current.length_cm], "area_inputs": area_inputs,'
    edit(probe, entry, entry + '''
        "centerline": voice.tract_area_samples().iter().map(|sample| sample.probe_axial_cm).collect::<Vec<_>>(),''')
