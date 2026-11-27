"""唇前端の体型変換を採取し、一時ビルドで上流の演算順序を試す。"""

import tsp_fk61_lip_area_observation as area
from tsp_fk61_lip_observation import edit, insert_before


CANDIDATE_SCALED = '    let scaled_x = body.point(template_x, 0.0).x;'
FIXED_ORDER_SCALED = '    let scaled_x = (0.5 + (template_x - 0.5) * 0.86) * k;'
ORIGINAL_FRONT = '    let front_x = body.point(8.15 + 0.12 * (1.0 - spreading), 0.0).x + 0.95 * protrusion;'
NEW_FRONT = '''    let template_x = 8.15 + 0.12 * (1.0 - spreading);
{scaled}
    let front_x = scaled_x + 0.95 * protrusion;'''


def apply_trial(root):
    edit(root / 'crates/vocal-core/src/anatomy.rs', ORIGINAL_FRONT, NEW_FRONT.format(scaled=FIXED_ORDER_SCALED))


def prepare(root, fixed, requested, trial=False):
    probe = area.prepare(root, fixed, requested)
    if fixed:
        observe_upstream(root)
    else:
        observe_candidate(root, trial)
    return probe


def observe_upstream(root):
    anatomy = root / 'crates/chimera/src/anatomy/human.rs'
    field = '    pub lip_area: f64,'
    edit(anatomy, field, field + '\n    #[serde(skip)]\n    pub probe_front_coordinates: [f64; 5],')
    edit(anatomy,
         '        let lip_front_x = this.p(8.15 + 0.12 * (1.0 - spread_w), 0.0).x + prot * 0.95;',
         '''        let template_x = 8.15 + 0.12 * (1.0 - spread_w);
        let scaled_x = this.p(template_x, 0.0).x;
        let lip_front_x = scaled_x + prot * 0.95;''')
    insert_before(anatomy, '        let ul_base = this.p(7.32, 8.35);',
                  '        f.probe_front_coordinates = [template_x, scaled_x, lip_front_x, ul_edge.x, ll_edge.x];\n')
    probe = root / 'tools' / area.SNAPSHOT.name
    edit(probe, '        "area_inputs": airway.probe_lip_area_inputs(&voice.artic.x),',
         '''        "area_inputs": airway.probe_lip_area_inputs(&voice.artic.x),
        "front_coordinates": frame.probe_front_coordinates,
        "lip_controls": [voice.artic.x.lip_ap, voice.artic.x.lip_prot, voice.artic.x.lip_width, voice.artic.x.labiodental],''')


def observe_candidate(root, trial):
    src = root / 'crates/vocal-core/src'
    anatomy = src / 'anatomy.rs'
    field = '    pub lip_width_cm: f64,'
    edit(anatomy, field, field + '\n    pub(crate) probe_front_coordinates: [f64; 5],')
    if not trial:
        edit(anatomy, ORIGINAL_FRONT, NEW_FRONT.format(scaled=CANDIDATE_SCALED))
    edit(anatomy, '        lips(\n', '        frame.probe_front_coordinates = lips(\n')
    edit(anatomy, '    lower: &mut Vec<Point>,\n) {', '    lower: &mut Vec<Point>,\n) -> [f64; 5] {')
    edit(anatomy, '    );\n}\n\nfn direction', '''
    );
    [template_x, scaled_x, front_x, upper_edge.x, lower_edge.x]
}

fn direction'''.lstrip('\n'))
    insert_before(src / 'airway/tract_control.rs', '    pub(crate) fn probe_lip_area_inputs', '''    pub(crate) fn probe_front_coordinates(&self) -> [f64; 5] {
        self.frame.probe_front_coordinates
    }

''')
    insert_before(src / 'voice.rs', '    pub fn probe_lip_geometry', '''    pub fn probe_front_coordinates(&self) -> [f64; 5] {
        self.tract.probe_front_coordinates()
    }

''')
    probe = root / 'tools' / area.SNAPSHOT.name
    edit(probe, '    let current = airway.network.section(airway.lips);', '''    let current = airway.network.section(airway.lips);
    let posture = voice.articulators().posture();''')
    edit(probe, '        "current": [current.area_cm2, current.minimum_area_cm2, current.length_cm], "area_inputs": area_inputs,',
         '''        "current": [current.area_cm2, current.minimum_area_cm2, current.length_cm], "area_inputs": area_inputs,
        "front_coordinates": voice.probe_front_coordinates(),
        "lip_controls": [posture.lip_aperture_cm, posture.lip_protrusion_cm, posture.lip_spread, posture.labiodental],''')
