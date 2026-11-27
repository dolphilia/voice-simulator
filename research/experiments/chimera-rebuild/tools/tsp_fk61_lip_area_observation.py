"""一時チェックアウトの発話に口端の読み取りを追加する。"""

from measure_tsp_fine_variation import LOCAL, PROBE
from tsp_fk61_lip_observation import edit, insert_before
from upstream_baseline import WORKSPACE


SNAPSHOT = WORKSPACE / 'tools/tsp_fk61_lip_area_snapshot.rs'


def prepare(root, fixed, requested):
    voice = root / 'tools' / (PROBE if fixed else LOCAL).name
    declaration = 'mod tsp_fk61_lip_area_snapshot;\n\n'
    leading_use = 'use chimera::{' if fixed else 'use serde_json::Value;'
    insert_before(voice, leading_use, declaration)
    selection = '&[' + ', '.join(map(str, requested)) + ']'
    writer = 'voice' if fixed else '&spoken'
    init = ('    let mut out = BufWriter::new(File::create_new(trace)?);' if fixed else '    spoken.set_score(gestures)?;')
    edit(voice, init, init + f'\n    let lip_frames = {selection};\n'
         + f'    tsp_fk61_lip_area_snapshot::write({writer}, 0, lip_frames)?;')
    pcm = '        pcm.write_all(&sample[0].to_le_bytes())?;' if fixed else '        pcm.write_all(&out.pcm.to_le_bytes())?;'
    if fixed:
        # 通常観測の render_closure だけに追加する。
        pcm += '\n        let airway = &voice.airway;'
        edit(voice, pcm, pcm.replace('\n        let airway', '\n'
            + f'        tsp_fk61_lip_area_snapshot::write({writer}, frame + 1, lip_frames)?;\n        let airway'))
        observe_upstream(root)
    else:
        edit(voice, pcm, pcm + f'\n        tsp_fk61_lip_area_snapshot::write({writer}, frame + 1, lip_frames)?;')
        observe_candidate(root)
    return voice


def observe_upstream(root):
    airway = root / 'crates/chimera/src/voice/human_airway.rs'
    edit(airway, '    pub or_areas: Vec<f64>,', '    pub or_areas: Vec<f64>,\n    pub probe_lip_raw: [f64; 2],')
    edit(airway, '            scratch_frame: HumanFrame::with_capacity(),',
         '            scratch_frame: HumanFrame::with_capacity(),\n            probe_lip_raw: [0.0; 2],')
    anchor = '        let (ph_len, or_len) = self.tract.resample(a, &f, &mut self.ph_areas, &mut self.or_areas, Some(&mut self.ph_min), Some(&mut self.or_min));'
    edit(airway, anchor, anchor + '''
        self.probe_lip_raw = [self.or_areas[self.n_or - 1], self.or_min[self.n_or - 1]];''')
    insert_before(airway, '    /// Geometry → targets for the next block.', '''    pub fn probe_lip_area_inputs(&self, a: &HumanArtic) -> [f64; 4] {
        let k = self.body.scale;
        let spread = a.lip_width.clamp(0.0, 1.0);
        let width = (1.1 + (self.body.lip_width - 1.1) * spread) * k;
        [k, width, self.tract.palate().last().unwrap().x, spread]
    }

''')
    insert_before(root / 'crates/chimera/src/airway/network.rs', '    pub fn set_node_area_target', '''    pub fn probe_lip_target(&self, node: usize) -> [f64; 3] {
        [self.area_target[node], self.amin_target[node], self.dx_target[node]]
    }

''')


def observe_candidate(root):
    src = root / 'crates/vocal-core/src'
    insert_before(src / 'airway/tract_control.rs', '    pub fn targets(&self)', '''    pub(crate) fn probe_lip_area_inputs(&self) -> [f64; 3] {
        [self.current.body.scale, self.frame.lip_width_cm, self.model.palate().last().unwrap().x]
    }

''')
    insert_before(src / 'voice.rs', '    pub fn tract_area_samples(&self)', '''    pub fn probe_lip_geometry(&self) -> (&crate::airway::tract_control::TractTargets, [f64; 4]) {
        let [scale, width, teeth] = self.tract.probe_lip_area_inputs();
        (self.tract.targets(), [scale, width, teeth, self.bank.posture().lip_spread.clamp(0.0, 1.0)])
    }

''')
    insert_before(src / 'airway/human.rs', '    pub fn tract_section_counts', '''    pub fn probe_lip_target(&self) -> [f64; 3] {
        let [area, minimum] = self.target_areas_cm2[self.lips];
        [area, minimum, self.target_lengths_cm[self.lips]]
    }

''')
