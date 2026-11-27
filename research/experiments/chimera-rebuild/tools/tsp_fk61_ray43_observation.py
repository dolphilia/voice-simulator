"""一時ビルドの測定線43に光線と交差前後の輪郭を記録する。"""

import tsp_fk61_node42_area_observation as base
from tsp_fk61_lip_observation import edit, insert_before


apply_trial = base.apply_trial


def prepare(root, fixed, requested, trial=False):
    source = base.prepare(root, fixed, requested, trial)
    snapshot = root / 'tools' / base.front.area.SNAPSHOT.name
    if fixed:
        anatomy = root / 'crates/chimera/src/anatomy/human.rs'
        field = '    pub ray: f64,'
        edit(anatomy, field, field + '\n    #[serde(skip)]\n    pub research_ray: [f64; 7],')
        field = '    d: f64,\n}\n\n#[derive(Clone, Debug, Default)]\nstruct Scratch'
        edit(anatomy, field, field.replace('    d: f64,', '    d: f64,\n    research_ray: [f64; 7],'))
        edit(anatomy, '                Some(Measured { inner: p_in, outer: p_out, d })',
             '''                Some(Measured { inner: p_in, outer: p_out, d,
                    research_ray: [o.x, o.y, dir.x, dir.y, max_len, t_in, t_out],
                })''')
        edit(anatomy, 'region, ray: m.d };', 'region, ray: m.d, research_ray: m.research_ray };')
        anchor = '    let watched = airway.oral.node(i);'
        prelude = '''    let ray = frame.grid[43].research_ray;
    let inner: Vec<_> = frame.inner.iter().map(|p| [p.x, p.y]).collect();
    let outer: Vec<_> = frame.outer.iter().map(|p| [p.x, p.y]).collect();
    let teeth: Vec<_> = frame.lower_teeth.iter().map(|p| [p.x, p.y]).collect();
    let lip: Vec<_> = frame.lower_lip.iter().take(7).map(|p| [p.x, p.y]).collect();
    let jaw = voice.artic.x.jaw;
'''
    else:
        src = root / 'crates/vocal-core/src'
        grid = src / 'anatomy/grid.rs'
        field = '    pub gap_cm: f64,'
        edit(grid, field, field + '\n    pub research_ray: [f64; 7],')
        edit(grid, '            gap_cm,\n            region,', '            gap_cm,\n            research_ray: [0.0; 7],\n            region,')
        anchor = '''    Some(GridSample::new(
        ray.point_at(floor.min(roof)),
        ray.point_at(roof),
        (roof - floor).max(0.0),
        region,
    ))'''
        edit(grid, anchor, '''    let mut measured = GridSample::new(
        ray.point_at(floor.min(roof)),
        ray.point_at(roof),
        (roof - floor).max(0.0),
        region,
    );
    measured.research_ray = [ray.origin.x, ray.origin.y, ray.direction.x, ray.direction.y, limit, floor, roof];
    Some(measured)''')
        insert_before(src / 'airway/tract_control.rs', '    pub fn targets(&self)', '''    pub(crate) fn research_frame(&self) -> &SagittalFrame {
        &self.frame
    }

''')
        insert_before(src / 'voice.rs', '    pub fn tract_area_samples(&self)', '''    pub fn research_sagittal_frame(&self) -> &crate::anatomy::SagittalFrame {
        self.tract.research_frame()
    }

''')
        anchor = '    let current_cell = airway.network.section(watched);'
        prelude = '''    let frame = voice.research_sagittal_frame();
    let ray = voice.tract_area_samples()[43].contact.ray.research_ray;
    let inner: Vec<_> = frame.inner.iter().map(|p| [p.x, p.y]).collect();
    let outer: Vec<_> = frame.outer.iter().map(|p| [p.x, p.y]).collect();
    let teeth: Vec<_> = frame.lower_teeth.iter().map(|p| [p.x, p.y]).collect();
    let lip: Vec<_> = frame.lower_lip.iter().take(7).map(|p| [p.x, p.y]).collect();
    let jaw = voice.articulators().posture().jaw_cm;
'''
    payload = '''    let ray43 = json!({
        "ray": ray, "inner": inner, "outer": outer, "lower_teeth": teeth, "lower_lip": lip, "jaw_cm": jaw,
    });
'''
    insert_before(snapshot, anchor, prelude + payload)
    text = snapshot.read_text()
    anchor = '        "before_lip": before_lip,'
    if text.count(anchor) != 2:
        raise ValueError('測定線の記録場所を同定できません')
    snapshot.write_text(text.replace(anchor, '        "ray43": ray43,\n' + anchor))
    return source
