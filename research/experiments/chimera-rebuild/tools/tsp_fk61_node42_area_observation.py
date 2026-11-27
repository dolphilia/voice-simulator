"""既存の発話観測に口端の一つ手前のセルを追加する。"""

import tsp_fk61_lip_front_observation as front
from tsp_fk61_lip_observation import edit, insert_before


apply_trial = front.apply_trial


def prepare(root, fixed, requested, trial=False):
    source = front.prepare(root, fixed, requested, trial)
    snapshot = root / 'tools' / front.area.SNAPSHOT.name
    if fixed:
        airway = root / 'crates/chimera/src/voice/human_airway.rs'
        field = '    pub probe_lip_raw: [f64; 2],'
        edit(airway, field, field + '\n    pub probe_before_lip_raw: [f64; 2],')
        initializer = '            probe_lip_raw: [0.0; 2],'
        edit(airway, initializer, initializer + '\n            probe_before_lip_raw: [0.0; 2],')
        raw = '        self.probe_lip_raw = [self.or_areas[self.n_or - 1], self.or_min[self.n_or - 1]];'
        edit(airway, raw, raw + '''
        let i = self.n_or - 2;
        self.probe_before_lip_raw = [self.or_areas[i], self.or_min[i]];
''')
        anchor = '    let end = airway.or_areas.len() - 1;'
        edit(snapshot, anchor, anchor + '''
    let i = end - 1;
    let watched = airway.oral.node(i);
    let before_lip = json!({
        "node": watched, "index": i, "raw": airway.probe_before_lip_raw,
        "limited": [airway.or_areas[i], airway.or_min[i]], "target": net.probe_lip_target(watched),
        "current": [net.area[watched], net.amin[watched], net.dx[watched]],
    });
''')
    else:
        airway = root / 'crates/vocal-core/src/airway/human.rs'
        insert_before(airway, '    pub fn probe_lip_target', '''    pub fn probe_before_lip(&self) -> (usize, [f64; 3]) {
        let node = self.lips - 1;
        let [area, minimum] = self.target_areas_cm2[node];
        (node, [area, minimum, self.target_lengths_cm[node]])
    }

''')
        anchor = '    let current = airway.network.section(airway.lips);'
        edit(snapshot, anchor, anchor + '''
    let (watched, target) = airway.probe_before_lip();
    let current_cell = airway.network.section(watched);
    let i = targets.raw.oral.cells.len() - 2;
    let a = targets.raw.oral.cells[i];
    let b = targets.limited.oral.cells[i];
    let before_lip = json!({
        "node": watched, "index": i, "raw": [a.area_cm2, a.minimum_area_cm2],
        "limited": [b.area_cm2, b.minimum_area_cm2], "target": target,
        "current": [current_cell.area_cm2, current_cell.minimum_area_cm2, current_cell.length_cm],
    });
''')
    text = snapshot.read_text()
    anchor = '        "grid": grid,'
    if text.count(anchor) != 2:
        raise ValueError('口端前の断面を採取する位置が2箇所ありません')
    snapshot.write_text(text.replace(anchor, '        "before_lip": before_lip,\n' + anchor))
    return source
